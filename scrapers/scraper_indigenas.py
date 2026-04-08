from scrapers.base import is_not_found, run_grouped_scraper, select_bootstrap_option

async def scrap_indigenas(df_ind, base_output):
    async def handle_ti(page, doc: str) -> bool:
        await select_bootstrap_option(
            page,
            'button[data-id="IdTipoDocumento"]',
            "TI",
        )
        await page.locator("#NumeroDocumento").fill(str(doc))
        await page.locator("#btnGenerarCertificado").click()
        return not await is_not_found(page.locator("#MsjNoEncontrado-Label"))

    async def handle_cc(page, doc: str) -> bool:
        await select_bootstrap_option(
            page,
            'button[data-id="IdTipoDocumento"]',
            "CC",
        )
        await page.locator("#NumeroDocumento").fill(str(doc))
        await page.locator("#btnGenerarCertificado").click()
        return not await is_not_found(page.locator("#MsjNoEncontrado-Label"))

    return await run_grouped_scraper(
        df=df_ind,
        base_output=base_output,
        folder_name="INDIGENAS",
        source_label="INDIGENAS",
        target_url="https://datos.mininterior.gov.co/VentanillaUnica/indigenas/censos/Persona",
        document_handlers=[
            ("TI", handle_ti),
            ("CC", handle_cc),
        ],
        concurrency=4,
    )
