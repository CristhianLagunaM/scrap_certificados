import os
from playwright.async_api import async_playwright
from utils.logger_sse import log   # <-- Importa la función de logs en tiempo real

# Flags necesarios para Chromium sin sandbox (Docker / Railway)
CHROMIUM_ARGS = [
    "--disable-dev-shm-usage",
    "--disable-setuid-sandbox",
    "--no-sandbox",
    "--no-zygote",
    "--single-process",
]

async def scrap_minorias(df_minorias, base_output):

    # Crear carpeta de salida
    folder = os.path.join(base_output, "MINORIAS")
    os.makedirs(folder, exist_ok=True)

    # Agrupar por documento
    grupos = df_minorias.groupby("Nro Iden")["Cred"].apply(list).to_dict()
    df_minorias["EstadoDescarga"] = "PENDIENTE"

    async with async_playwright() as p:

        # Lanzar Chromium con flags seguros para Docker
        browser = await p.chromium.launch(
            headless=True,
            args=CHROMIUM_ARGS
        )

        context = await browser.new_context(accept_downloads=True)

        for doc, codigos in grupos.items():

            log(f"[MINORIAS] Procesando documento {doc} → credenciales {codigos}")

            page = await context.new_page()

            try:
                await page.goto(
                    "https://datos.mininterior.gov.co/VentanillaUnica/Dacnrp/auto-reconocimiento/certificado",
                    timeout=120000
                )

                tipos = ["Tarjeta de identidad", "Cédula de ciudadanía"]
                exito = False

                for tipo in tipos:
                    log(f"[MINORIAS] Probando tipo de documento: {tipo}")

                    # Seleccionar tipo documento
                    dd = page.locator('button[data-id="IdTipoDocumento"]')
                    await dd.click()

                    await page.locator(".dropdown-menu").get_by_text(
                        tipo, exact=True
                    ).click()

                    # Número de identificación
                    await page.locator("#NumeroIdentificacion").fill(str(doc))

                    # Seleccionar tipo de certificación
                    await page.locator('button[data-id="IdTipoCertificacion"]').click()
                    await page.locator(".dropdown-menu").get_by_text(
                        "Solicitud de autoreconocimiento", exact=True
                    ).click()

                    # Click en Buscar
                    await page.locator("#SubmitBtn").click()

                    # No encontrado → probar otro tipo
                    try:
                        await page.wait_for_selector("#MsjNoEncontrado-Label", timeout=3000)
                        log(f"[MINORIAS] ❌ Documento {doc} NO encontrado usando {tipo}")
                        continue
                    except:
                        pass

                    # Cerrar modal si aparece
                    try:
                        await page.get_by_role("button", name="Aceptar").click()
                    except:
                        pass

                    # Esperar intento de descarga
                    try:
                        dl = await page.wait_for_event("download", timeout=30000)

                        filename = "-".join(codigos) + ".pdf"
                        save_path = os.path.join(folder, filename)

                        await dl.save_as(save_path)

                        log(f"[MINORIAS] ✔ Descargado {filename}")
                        exito = True
                        break

                    except Exception as e:
                        log(f"[MINORIAS] ⚠ Error descargando PDF: {e}")
                        continue

                # Marcar estado
                df_minorias.loc[df_minorias["Nro Iden"] == doc, "EstadoDescarga"] = (
                    "OK" if exito else "ERROR"
                )

            except Exception as e:
                log(f"[MINORIAS] ❌ Error general procesando {doc}: {e}")
                df_minorias.loc[df_minorias["Nro Iden"] == doc, "EstadoDescarga"] = "ERROR"

            await page.close()

        await browser.close()

    return df_minorias
