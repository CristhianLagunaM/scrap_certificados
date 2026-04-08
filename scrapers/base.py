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

DocumentHandler = Callable[[object, str], Awaitable[bool]]


def reset_output_folder(base_output: str, folder_name: str) -> str:
    folder = os.path.join(base_output, folder_name)
    if os.path.isdir(folder):
        shutil.rmtree(folder)
    os.makedirs(folder, exist_ok=True)
    return folder


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

        async def process_document(doc: str, codes: list[str]) -> None:
            async with semaphore:
                pdf_name = build_pdf_name(codes)
                log(f"[{source_label}] Procesando documento {doc} ({len(codes)} credenciales)")

                success = False
                detail = "No fue posible descargar el certificado"

                for type_label, handler in document_handlers:
                    page = await context.new_page()
                    try:
                        await page.goto(target_url, wait_until="domcontentloaded")
                        log(f"[{source_label}] Intentando {doc} con tipo {type_label}")
                        success = await handler(page, doc)

                        if success:
                            async with page.expect_download(timeout=30000) as download_info:
                                await page.get_by_role("button", name="Aceptar").click(timeout=5000)
                            download = await download_info.value
                            await download.save_as(os.path.join(folder, pdf_name))
                            detail = f"Descargado como {pdf_name}"
                            log(f"[{source_label}] Descargado {pdf_name}")
                            break

                        detail = f"Documento {doc} no encontrado con tipo {type_label}"
                    except PlaywrightTimeoutError:
                        detail = f"Timeout procesando {doc} con tipo {type_label}"
                        log(f"[{source_label}] Timeout con {doc} usando {type_label}")
                    except Exception as exc:
                        detail = f"Error con tipo {type_label}: {exc}"
                        log(f"[{source_label}] Error procesando {doc} con {type_label}: {exc}")
                    finally:
                        await page.close()

                df.loc[df["Nro Iden"] == doc, "EstadoDescarga"] = "OK" if success else "ERROR"
                df.loc[df["Nro Iden"] == doc, "DetalleDescarga"] = detail

        await asyncio.gather(
            *(process_document(doc, codes) for doc, codes in grouped.items())
        )
        await browser.close()

    return df
