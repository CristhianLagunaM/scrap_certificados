from scrapers.base import normalize_text, pdf_matches_expected_identity


def test_normalize_text_removes_accents_and_extra_spaces():
    assert normalize_text("  Dayra   Loréna  Jajoy ") == "DAYRA LORENA JAJOY"


def test_pdf_matches_expected_identity_accepts_matching_doc_and_name():
    pdf_text = """
    Se registra el Señor(a): DAYRA LORENA JAJOY TANDIOY,
    identificado con CC número 1014480663, Estado Activo.
    """

    matches, detail = pdf_matches_expected_identity(
        pdf_text,
        expected_doc="1014480663",
        expected_names=["DAYRA LORENA", "JAJOY TANDIOY"],
    )

    assert matches is True
    assert "coincidencia global 100.00%" in detail


def test_pdf_matches_expected_identity_rejects_mismatched_doc():
    pdf_text = """
    Se registra el Señor(a): TANIA SOFIA LOPEZ POLOCHE,
    identificado con CC número 1022948846, Estado Activo.
    """

    matches, detail = pdf_matches_expected_identity(
        pdf_text,
        expected_doc="1014480663",
        expected_names=["DAYRA LORENA", "JAJOY TANDIOY"],
    )

    assert matches is False
    assert "1014480663" in detail


def test_pdf_accepts_additional_given_name_with_matching_surnames():
    matches, _ = pdf_matches_expected_identity(
        'Señor, SAMUEL LINA GONZÁLEZ MARÍN. identificado con documento No. 1028489772',
        '1028489772',
        ['SAMUEL', 'GONZALEZ MARIN'],
    )
    assert matches


def test_pdf_rejects_different_identity_despite_additional_names():
    for name in (
        'SAMUEL LINA GONZALEZ LOPEZ',
        'SAMUEL LINA PEREZ MARIN',
        'MANUEL LINA GONZALEZ MARIN',
        'SAMUEL LINA GONZALEZ MARINA',
        'XSAMUEL LINA GONZALEZ MARIN',
        'SAMUEL figura en la solicitud. LINA GONZALEZ MARIN',
    ):
        matches, _ = pdf_matches_expected_identity(
            f'{name}. Documento 1028489772',
            '1028489772',
            ['SAMUEL', 'GONZALEZ MARIN'],
        )
        assert not matches, name


def test_rejected_certificate_keeps_validation_reason_in_report():
    import asyncio
    from pathlib import Path
    from tempfile import TemporaryDirectory
    from unittest.mock import AsyncMock, MagicMock, patch

    import pandas as pd

    from scrapers.base import run_grouped_scraper

    async def run():
        page = MagicMock()
        page.goto = AsyncMock()
        page.close = AsyncMock()
        page.get_by_role.return_value.click = AsyncMock()
        download = MagicMock()
        download.save_as = AsyncMock(side_effect=lambda path: Path(path).write_bytes(b"PDF de prueba"))
        download_info = MagicMock()
        download_info.value = asyncio.Future()
        download_info.value.set_result(download)
        page.expect_download.return_value.__aenter__ = AsyncMock(return_value=download_info)
        context = MagicMock()
        context.new_page = AsyncMock(return_value=page)
        context.route = AsyncMock()
        context.close = AsyncMock()
        browser = MagicMock()
        browser.new_context = AsyncMock(return_value=context)
        browser.close = AsyncMock()
        playwright = MagicMock()
        playwright.chromium.launch = AsyncMock(return_value=browser)
        manager = MagicMock()
        manager.__aenter__ = AsyncMock(return_value=playwright)
        frame = pd.DataFrame([{
            'Nro Iden': '1028489772', 'Cred': '7271',
            'Nombre': 'SAMUEL', 'Apellido': 'GONZALEZ MARIN',
        }])
        with TemporaryDirectory() as folder, patch(
            'scrapers.base.async_playwright', return_value=manager
        ), patch('scrapers.base.extract_pdf_text', return_value='OTRO NOMBRE 1028489773') as extract:
            async def scrape():
                return await run_grouped_scraper(
                    df=frame, base_output=folder, folder_name='MINORIAS',
                    source_label='MINORIAS', target_url='https://example.test',
                    document_handlers=[('TI', AsyncMock(return_value=True)),
                                       ('CC', AsyncMock(return_value=False))],
                )

            result = await scrape()
            assert result.iloc[0]['EstadoDescarga'] == 'ERROR'
            assert 'documento esperado 1028489772' in result.iloc[0]['DetalleDescarga']
            assert 'no encontrado' not in result.iloc[0]['DetalleDescarga']
            assert result.iloc[0]['CoincidenciaDocumento'] == 0

            extract.return_value = 'Señor, PEDRO LUIS GOMEZ PEREZ. identificado con documento No. 1028489772'
            result = await scrape()
            assert result.iloc[0]['EstadoDescarga'] == 'REVISAR'
            assert result.iloc[0]['RevisionIdentidad'] == 'SI'
            assert result.iloc[0]['CoincidenciaGlobal'] < 85
            assert (Path(folder) / 'MINORIAS/REVISION/TI_7271.pdf').exists()
            assert 'PDF conservado' in result.iloc[0]['DetalleDescarga']
            assert 'no encontrado' not in result.iloc[0]['DetalleDescarga']

            extract.return_value = 'Señor, SAMUEL LINA GONZALEZ MARIN. identificado con documento No. 1028489772'
            result = await scrape()
            assert result.iloc[0]['EstadoDescarga'] == 'OK'
            assert result.iloc[0]['RevisionIdentidad'] == 'SI'
            assert result.iloc[0]['CoincidenciaGlobal'] == 100
            assert result.iloc[0]['NombreCertificado'] == 'SAMUEL LINA GONZALEZ MARIN'
            assert 'coincidencia global' in result.iloc[0]['DetalleDescarga']
            assert (Path(folder) / 'MINORIAS/7271.pdf').exists()

    asyncio.run(run())


def test_parallel_documents_use_independent_sessions():
    import asyncio
    from pathlib import Path
    from tempfile import TemporaryDirectory
    from unittest.mock import AsyncMock, MagicMock, patch

    import pandas as pd

    from scrapers.base import run_grouped_scraper

    async def run():
        contexts = []
        both_requested = asyncio.Event()
        requested = 0

        async def new_context(**kwargs):
            context = MagicMock()
            context.document = ''
            context.route = AsyncMock()
            context.close = AsyncMock()
            contexts.append(context)

            async def new_page():
                page = MagicMock()
                page.session = context
                page.goto = AsyncMock()
                page.close = AsyncMock()
                page.get_by_role.return_value.click = AsyncMock()
                download = MagicMock()

                async def save_as(path):
                    # Simula portal: PDF depende del último documento de la sesión.
                    Path(path).write_text(f'Señor, PERSONA PRUEBA. identificado con documento No. {context.document}')

                download.save_as = AsyncMock(side_effect=save_as)
                info = MagicMock()
                info.value = asyncio.Future()
                info.value.set_result(download)
                page.expect_download.return_value.__aenter__ = AsyncMock(return_value=info)
                return page

            context.new_page = AsyncMock(side_effect=new_page)
            return context

        async def handler(page, doc):
            nonlocal requested
            page.session.document = doc
            requested += 1
            if requested == 2:
                both_requested.set()
            await asyncio.wait_for(both_requested.wait(), timeout=2)
            return True

        browser = MagicMock()
        browser.new_context = AsyncMock(side_effect=new_context)
        browser.close = AsyncMock()
        playwright = MagicMock()
        playwright.chromium.launch = AsyncMock(return_value=browser)
        manager = MagicMock()
        manager.__aenter__ = AsyncMock(return_value=playwright)
        frame = pd.DataFrame([
            {'Nro Iden': doc, 'Cred': str(i), 'Nombre': 'PERSONA', 'Apellido': 'PRUEBA'}
            for i, doc in enumerate(['1125848987', '1028489772'])
        ])
        with TemporaryDirectory() as folder, patch(
            'scrapers.base.async_playwright', return_value=manager
        ), patch('scrapers.base.extract_pdf_text', side_effect=lambda path: Path(path).read_text()):
            result = await run_grouped_scraper(
                df=frame, base_output=folder, folder_name='INDIGENAS',
                source_label='INDIGENAS', target_url='https://example.test',
                document_handlers=[('TI', handler)], concurrency=2,
            )
        assert result['EstadoDescarga'].tolist() == ['OK', 'OK']
        assert len(contexts) == 2
        for context in contexts:
            context.close.assert_awaited_once()

    asyncio.run(run())
