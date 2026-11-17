import asyncio
import os
import re
import shutil
from collections.abc import Awaitable, Callable

from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

from scrapers.identity import normalize_text as normalize_text
from scrapers.identity import validate_pdf_identity
from utils.logger_sse import log

# Chromium necesita varios procesos para mantener contextos aislados concurrentes.
CHROMIUM_ARGS = [
    "--disable-dev-shm-usage",
    "--disable-setuid-sandbox",
    "--no-sandbox",
]
BLOCKED_RESOURCE_TYPES = {"image", "media", "font"}
BLOCKED_URL_HINTS = (
    "googletagmanager",
    "google-analytics",
    "doubleclick",
    "facebook",
    "hotjar",
    "clarity",
)
DOWNLOAD_TIMEOUT_MS = 45000
DOWNLOAD_RETRIES = 2

DocumentHandler = Callable[[object, str], Awaitable[bool]]


def reset_output_folder(base_output: str, folder_name: str) -> str:
    folder = os.path.join(base_output, folder_name)
    if os.path.isdir(folder):
        shutil.rmtree(folder)
    os.makedirs(folder, exist_ok=True)
    return folder


def resolve_concurrency(default: int, folder_name: str) -> int:
    candidates = [
        os.getenv(f"SCRAPER_CONCURRENCY_{folder_name.upper()}"),
        os.getenv("SCRAPER_CONCURRENCY"),
    ]

    for raw_value in candidates:
        if not raw_value:
            continue
        try:
            parsed = int(raw_value)
            if parsed > 0:
                return parsed
        except ValueError:
            continue

    return default


def build_pdf_name(codes: list[str]) -> str:
    clean_codes = []
    for code in codes:
        value = str(code).strip()
        if value and value not in clean_codes:
            clean_codes.append(value)

    raw_name = "-".join(clean_codes) if clean_codes else "sin_codigo"
    sanitized = re.sub(r'[\\/:*?"<>|]+', "_", raw_name)
    return f"{sanitized[:180]}.pdf"


def extract_pdf_text(path: str) -> str:
    import fitz

    with fitz.open(path) as document:
        return "\n".join(page.get_text("text") for page in document)


def pdf_matches_expected_identity(
    pdf_text: str,
    expected_doc: str,
    expected_names: list[str] | None = None,
) -> tuple[bool, str]:
    validation = validate_pdf_identity(pdf_text, expected_doc, expected_names)
    return validation.status == "OK", validation.detail


async def select_bootstrap_option(page, selector: str, option_text: str) -> None:
    dropdown = page.locator(selector)
    await dropdown.click()
    await page.locator(".dropdown-menu.show, .dropdown-menu.open, .dropdown-menu").get_by_text(
        option_text,
        exact=True,
    ).click()


async def is_not_found(locator, timeout: int = 3000) -> bool:
    try:
        await locator.wait_for(state="visible", timeout=timeout)
        return True
    except PlaywrightTimeoutError:
        return False


async def run_grouped_scraper(
    *,
    df,
    base_output: str,
    folder_name: str,
    source_label: str,
    target_url: str,
    document_handlers: list[tuple[str, DocumentHandler]],
    concurrency: int = 4,
):
    folder = reset_output_folder(base_output, folder_name)
    concurrency = resolve_concurrency(concurrency, folder_name)
    grouped = (
        df.groupby("Nro Iden", dropna=True)
        .apply(
            lambda group: {
                "codes": [
                    str(value).strip()
                    for value in group["Cred"]
                    if str(value).strip()
                ],
                "names": [
                    str(group.iloc[0].get("Nombre", "")).strip(),
                    str(group.iloc[0].get("Apellido", "")).strip(),
                ],
            }
        )
        .to_dict()
    )

    df = df.copy()
    df["EstadoDescarga"] = "PENDIENTE"
    df["DetalleDescarga"] = ""
    for column in ("CoincidenciaDocumento", "CoincidenciaApellidos", "CoincidenciaNombres", "CoincidenciaGlobal"):
        df[column] = float("nan")
    df["NombreCertificado"] = ""
    df["RevisionIdentidad"] = ""


    if not grouped:
        return df

    semaphore = asyncio.Semaphore(concurrency)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=CHROMIUM_ARGS)
        log(
            f"[{source_label}] Concurrencia activa: {concurrency} documentos en paralelo"
        )

        async def process_document(doc: str, payload: dict[str, list[str]]) -> None:
            async with semaphore:
                codes = payload["codes"]
                expected_names = payload.get("names", [])
                pdf_name = build_pdf_name(codes)
                pdf_path = os.path.join(folder, pdf_name)
                log(f"[{source_label}] Procesando documento {doc} ({len(codes)} credenciales)")

                download_success = False
                detail = "No fue posible descargar el certificado"
                attempted_types = []
                not_found_types = []
                failure_details = []
                best_validation = None
                review_paths = []

                for type_label, handler in document_handlers:
                    attempted_types.append(type_label)
                    # El portal puede guardar el certificado consultado en la sesión.
                    # Cada intento necesita cookies y estado independientes.
                    context = await browser.new_context(accept_downloads=True)
                    try:
                        context.set_default_timeout(45000)
                        await context.route(
                            "**/*",
                            lambda route: route.abort()
                            if route.request.resource_type in BLOCKED_RESOURCE_TYPES
                            or any(hint in route.request.url.lower() for hint in BLOCKED_URL_HINTS)
                            else route.continue_(),
                        )
                        page = await context.new_page()
                        await page.goto(target_url, wait_until="domcontentloaded")
                        log(f"[{source_label}] Intentando {doc} con tipo {type_label}")
                        record_found = await handler(page, doc)

                        if record_found:
                            last_timeout_error = None

                            for attempt in range(1, DOWNLOAD_RETRIES + 1):
                                try:
                                    if attempt > 1:
                                        log(
                                            f"[{source_label}] Reintentando descarga de {doc} "
                                            f"con tipo {type_label} (intento {attempt}/{DOWNLOAD_RETRIES})"
                                        )

                                    async with page.expect_download(timeout=DOWNLOAD_TIMEOUT_MS) as download_info:
                                        await page.get_by_role("button", name="Aceptar").click(timeout=5000)

                                    download = await download_info.value
                                    await download.save_as(pdf_path)
                                    pdf_text = extract_pdf_text(pdf_path)
                                    validation = validate_pdf_identity(
                                        pdf_text,
                                        expected_doc=doc,
                                        expected_names=expected_names,
                                    )
                                    if best_validation is None or (
                                        validation.document_matches,
                                        validation.overall_score if validation.overall_score is not None else -1,
                                    ) > (
                                        best_validation.document_matches,
                                        best_validation.overall_score if best_validation.overall_score is not None else -1,
                                    ):
                                        best_validation = validation
                                    validation_detail = validation.detail
                                    if validation.status != "OK":
                                        if validation.status == "REVISAR":
                                            review_folder = os.path.join(folder, "REVISION")
                                            os.makedirs(review_folder, exist_ok=True)
                                            review_path = os.path.join(review_folder, f"{type_label}_{pdf_name}")
                                            shutil.move(pdf_path, review_path)
                                            review_paths.append(review_path)
                                        elif os.path.exists(pdf_path):
                                            os.remove(pdf_path)
                                        detail = (
                                            f"Certificado descargado no coincide con documento consultado {doc}. "
                                            f"{validation_detail}"
                                        )
                                        failure_details.append(f"Tipo {type_label}: {detail}")
                                        log(
                                            f"[{source_label}] Validación {validation.status} para {doc}: "
                                            f"{validation_detail}"
                                        )
                                        break

                                    best_validation = validation
                                    for review_path in review_paths:
                                        os.remove(review_path)
                                    detail = f"Descargado como {pdf_name}. {validation_detail}"
                                    download_success = True
                                    log(f"[{source_label}] Descargado {pdf_name}")
                                    break
                                except PlaywrightTimeoutError as exc:
                                    last_timeout_error = exc
                                    detail = (
                                        f"Timeout descargando {doc} con tipo {type_label} "
                                        f"(intento {attempt}/{DOWNLOAD_RETRIES})"
                                    )

                            if download_success:
                                break

                            if last_timeout_error is not None:
                                failure_details.append(detail)
                                log(f"[{source_label}] Timeout descargando {doc} usando {type_label}")
                                continue

                            continue

                        not_found_types.append(type_label)
                        detail = (
                            f"Documento {doc} no encontrado con tipos "
                            f"{', '.join(not_found_types)}"
                        )
                    except PlaywrightTimeoutError:
                        detail = (
                            f"Timeout procesando {doc} con tipo {type_label}. "
                            f"Intentos realizados: {', '.join(attempted_types)}"
                        )
                        log(f"[{source_label}] Timeout con {doc} usando {type_label}")
                        failure_details.append(detail)
                    except Exception as exc:
                        detail = (
                            f"Error con tipo {type_label}: {exc}. "
                            f"Intentos realizados: {', '.join(attempted_types)}"
                        )
                        log(f"[{source_label}] Error procesando {doc} con {type_label}: {exc}")
                        failure_details.append(detail)
                    finally:
                        await context.close()

                if not download_success and failure_details:
                    detail = "; ".join(failure_details)
                elif not download_success and not_found_types and len(not_found_types) == len(document_handlers):
                    detail = (
                        f"Documento {doc} no encontrado con TI ni CC"
                        if set(not_found_types) == {"TI", "CC"}
                        else f"Documento {doc} no encontrado con tipos {', '.join(not_found_types)}"
                    )

                status = "OK" if download_success else "ERROR"
                if best_validation is not None:
                    if not download_success and best_validation.status == "REVISAR":
                        status = "REVISAR"
                        detail = best_validation.detail + "; PDF conservado en carpeta REVISION. " + detail
                    mask = df["Nro Iden"] == doc
                    for column, value in {
                        "CoincidenciaDocumento": 100.0 if best_validation.document_matches else 0.0,
                        "CoincidenciaApellidos": best_validation.surnames_score,
                        "CoincidenciaNombres": best_validation.names_score,
                        "CoincidenciaGlobal": best_validation.overall_score,
                        "NombreCertificado": best_validation.certificate_name,
                        "RevisionIdentidad": "SI" if best_validation.review else "NO",
                    }.items():
                        if value is not None:
                            df.loc[mask, column] = value
                df.loc[df["Nro Iden"] == doc, "EstadoDescarga"] = status
                df.loc[df["Nro Iden"] == doc, "DetalleDescarga"] = detail

        await asyncio.gather(
            *(process_document(doc, payload) for doc, payload in grouped.items())
        )
        await browser.close()

    return df
