import pandas as pd

from legalizacion.classifier import classify, extract_program_code
from legalizacion.pdf_credential_extractor import find_academic_program, find_credentials, find_transfer_inscription_type, prioritize_ocr_pages
from legalizacion.processor import build_report_dataframe, build_unique_filename, reconcile_credentials
from legalizacion.validators import compare_credentials, normalize_excel_credentials, validate_credential


def test_extract_program_code():
    assert extract_program_code("(678) Ingenieria en Telematica (Ciclos Propedeuticos)") == "678"
    assert extract_program_code("Opcion 1: 579 - INGENIERIA CIVIL (CICLOS PROPEDEUTICOS)") == "579"
    assert extract_program_code("579 - INGENIERIA CIVIL (CICLOS PROPEDEUTICOS)") == "579"
    assert extract_program_code("Ingenieria Ambiental") == ""


def test_profesionalizacion_priority():
    result = classify("(678) Ingenieria en Telematica (Ciclos Propedeuticos)", "DESPLAZADO")
    assert result.relative_folder == "PROFESIONALIZACION/Ingenierias tecnologica/678"
    pdf_result = classify("Opcion 1: 579 - INGENIERIA CIVIL (CICLOS PROPEDEUTICOS)", "NORMAL")
    assert pdf_result.relative_folder == "PROFESIONALIZACION/Ingenierias tecnologica/579"


def test_cupo_especial_and_transferencia():
    assert classify("(180) Ingenieria Ambiental", "DESPLAZADO").relative_folder == "CUPO ESPECIAL/Desplazado"
    assert classify("(10) Ingenieria Forestal", "TRANSFERENCIA INTERNA").relative_folder == "TRANSFERENCIA/Transferencia interna/10"
    pdf_type = find_transfer_inscription_type("Tipo de inscripcion:\nTRANSFERENCIA INTERNA")
    assert classify("(180) Ingenieria Ambiental", pdf_type).relative_folder == "TRANSFERENCIA/Transferencia interna/180"


def test_credentials_from_text():
    assert find_credentials("Credencial: 00443\nCredencial: 00444") == ["00443", "00444"]
    assert find_credentials("No. Credencial: 02120") == ["02120"]
    assert find_credentials("COMPROBANTE DE INSCRIPCION\nCredencial:\n06846\nTipo de inscripcion: TRANSFERENCIA") == ["06846"]
    assert find_credentials("Credenciales: 00443, 00444 y 123") == ["00443", "00444", "123"]
    assert find_credentials("Credencial: 1031803905\nDocumento: 999") == []
    assert find_credentials("Credencial: O6846") == ["06846"]
    assert find_credentials("Credencial: 0684 6") == ["06846"]
    assert find_credentials("Credencial:\nPrograma Academico:\nCredencial:\nNombre del colegio donde culmino el grado 11:") == []
    assert find_credentials("Credencial: 15123\nPrograma Academico: X\nCredencial: 15124") == ["15123", "15124"]


def test_transfer_inscription_type_from_pdf_text():
    assert find_transfer_inscription_type("Tipo de inscripción: TRANSFERENCIA INTERNA") == "TRANSFERENCIA INTERNA"
    assert find_transfer_inscription_type("Tipo de inscripcion:\nTRANSFERENCIA EXTERNA") == "TRANSFERENCIA EXTERNA"
    assert find_transfer_inscription_type("Tipo de inscripción: INDIGENA") == ""


def test_academic_program_from_pdf_text():
    text = (
        "Programa Académico:\n"
        "Opción 1: 579 - INGENIERIA CIVIL (CICLOS\n"
        "PROPEDEUTICOS)\n"
        "Credencial:\n"
        "03335"
    )
    assert find_academic_program(text) == "Opcion 1: 579 - INGENIERIA CIVIL (CICLOS PROPEDEUTICOS)"


def test_ocr_candidates_include_all_pages_by_default():
    pages = [(index, None, "") for index in range(10)]
    assert len(prioritize_ocr_pages(pages)) == 10


def test_validate_credentials():
    assert validate_credential("00158")[0]
    assert validate_credential("1000992090")[1] == "Credencial invalida: supera 5 digitos"
    assert validate_credential("501-502")[1] == "Credencial invalida: contiene caracteres no permitidos"


def test_excel_comparison_and_repeated_names():
    assert normalize_excel_credentials("00443 ; 00444") == ["00443", "00444"]
    assert compare_credentials(["02120"], ["2120"]) == "Difiere de Excel"
    assert reconcile_credentials(["15123", "15124", "15125"], ["15125"]) == ["15123", "15124", "15125"]
    assert reconcile_credentials(["06366", "0"], []) == ["06366"]
    counts = {}
    assert build_unique_filename("501", "NORMAL/10", counts) == "501.pdf"
    assert build_unique_filename("501", "NORMAL/10", counts) == "501..pdf"
    assert build_unique_filename("501", "NORMAL/10", counts) == "501...pdf"
    assert build_unique_filename("501", "CUPO ESPECIAL/Indigenas", counts) == "501.pdf"


def test_report_keeps_only_curated_columns():
    dataframe = pd.DataFrame(
        {
            "Serial number": ["1"],
            "Documento de identidad": ["123"],
            "Fila Excel": ["2"],
            "Estado procesamiento": ["Descargada"],
            "Motivo": ["OK"],
            "Credencial PDF": ["03335"],
        }
    )

    report = build_report_dataframe(dataframe)

    assert "Serial number" not in report.columns
    assert "Documento de identidad" not in report.columns
    assert list(report.columns) == ["Fila Excel", "Estado procesamiento", "Motivo", "Credencial PDF"]
