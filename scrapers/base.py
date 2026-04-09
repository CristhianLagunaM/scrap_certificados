import os
import re
import shutil
import asyncio
from typing import Awaitable, Callable

from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

from utils.logger_sse import log

# Flags seguros para entornos de contenedor.
CHROMIUM_ARGS = [
    "--disable-dev-shm-usage",
    "--disable-setuid-sandbox",
    "--no-sandbox",
    "--no-zygote",
    "--single-process",
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
        df.groupby("Nro Iden", dropna=True)["Cred"]
        .apply(lambda values: [str(value).strip() for value in values if str(value).strip()])
        .to_dict()
    )

    df = df.copy()
    df["EstadoDescarga"] = "PENDIENTE"
    df["DetalleDescarga"] = ""

    if not grouped:
        return df

    semaphore = asyncio.Semaphore(concurrency)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=CHROMIUM_ARGS)
        context = await browser.new_context(accept_downloads=True)
        context.set_default_timeout(45000)
        await context.route(
            "**/*",
            lambda route: route.abort()
            if route.request.resource_type in BLOCKED_RESOURCE_TYPES
            or any(hint in route.request.url.lower() for hint in BLOCKED_URL_HINTS)
            else route.continue_(),
        )

        log(
            f"[{source_label}] Concurrencia activa: {concurrency} documentos en paralelo"
        )

        async def process_document(doc: str, codes: list[str]) -> None:
            async with semaphore:
                pdf_name = build_pdf_name(codes)
                log(f"[{source_label}] Procesando documento {doc} ({len(codes)} credenciales)")

                download_success = False
                detail = "No fue posible descargar el certificado"
                attempted_types = []
                not_found_types = []

                for type_label, handler in document_handlers:
                    attempted_types.append(type_label)
                    page = await context.new_page()
                    try:
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
                                    await download.save_as(os.path.join(folder, pdf_name))
                                    detail = f"Descargado como {pdf_name}"
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
                                log(f"[{source_label}] Timeout descargando {doc} usando {type_label}")
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
                    except Exception as exc:
                        detail = (
                            f"Error con tipo {type_label}: {exc}. "
                            f"Intentos realizados: {', '.join(attempted_types)}"
                        )
                        log(f"[{source_label}] Error procesando {doc} con {type_label}: {exc}")
                    finally:
                        await page.close()

                if not download_success and not_found_types and len(not_found_types) == len(document_handlers):
                    detail = (
                        f"Documento {doc} no encontrado con TI ni CC"
                        if set(not_found_types) == {"TI", "CC"}
                        else f"Documento {doc} no encontrado con tipos {', '.join(not_found_types)}"
                    )

                df.loc[df["Nro Iden"] == doc, "EstadoDescarga"] = "OK" if download_success else "ERROR"
                df.loc[df["Nro Iden"] == doc, "DetalleDescarga"] = detail

        await asyncio.gather(
            *(process_document(doc, codes) for doc, codes in grouped.items())
        )
        await browser.close()

    return df
