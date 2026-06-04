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
    assert detail == "Identidad validada"


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
