from scrapers.base import is_not_found, run_grouped_scraper, select_bootstrap_option

async def scrap_minorias(df_minorias, base_output):
    async def handle_ti(page, doc: str) -> bool:
        await select_bootstrap_option(
            page,
            'button[data-id="IdTipoDocumento"]',
            "Tarjeta de identidad",
        )
        await page.locator("#NumeroIdentificacion").fill(str(doc))
        await select_bootstrap_option(
            page,
            'button[data-id="IdTipoCertificacion"]',
            "Solicitud de autoreconocimiento",
        )
        await page.locator("#SubmitBtn").click()
        return not await is_not_found(page.locator("#MsjNoEncontrado-Label"))

    async def handle_cc(page, doc: str) -> bool:
        await select_bootstrap_option(
            page,
            'button[data-id="IdTipoDocumento"]',
            "Cédula de ciudadanía",
        )
        await page.locator("#NumeroIdentificacion").fill(str(doc))
        await select_bootstrap_option(
            page,
            'button[data-id="IdTipoCertificacion"]',
            "Solicitud de autoreconocimiento",
        )
        await page.locator("#SubmitBtn").click()
        return not await is_not_found(page.locator("#MsjNoEncontrado-Label"))

    return await run_grouped_scraper(
        df=df_minorias,
        base_output=base_output,
        folder_name="MINORIAS",
        source_label="MINORIAS",
        target_url="https://datos.mininterior.gov.co/VentanillaUnica/Dacnrp/auto-reconocimiento/certificado",
        document_handlers=[
            ("TI", handle_ti),
            ("CC", handle_cc),
        ],
        concurrency=4,
    )
