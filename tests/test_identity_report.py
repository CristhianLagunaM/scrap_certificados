from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd
from openpyxl import load_workbook

from utils.excel import generar_excel_coloreado


def test_identity_report_preserves_scores_and_highlights_review():
    frame = pd.DataFrame([
        {'EstadoDescarga': 'OK', 'DetalleDescarga': 'Aceptado con diferencias', 'CoincidenciaGlobal': 93.88, 'RevisionIdentidad': 'SI'},
        {'EstadoDescarga': 'REVISAR', 'DetalleDescarga': 'Bajo umbral', 'CoincidenciaGlobal': 60.0, 'RevisionIdentidad': 'SI'},
        {'EstadoDescarga': 'OK', 'DetalleDescarga': 'Exacto', 'CoincidenciaGlobal': 100.0, 'RevisionIdentidad': 'NO'},
        {'EstadoDescarga': 'ERROR', 'DetalleDescarga': 'Documento distinto', 'CoincidenciaGlobal': None, 'RevisionIdentidad': 'NO'},
    ])
    with TemporaryDirectory() as folder:
        path = Path(folder) / 'reporte.xlsx'
        generar_excel_coloreado(frame, path)
        book = load_workbook(path)
        sheet = book['RESULTADOS']
        headers = [cell.value for cell in sheet[1]]
        assert headers[:3] == ['EstadoDescarga', 'DetalleDescarga', 'CoincidenciaGlobal']
        assert sheet.cell(2, 3).value == 93.88
        assert sheet.cell(5, 3).value is None
        assert sheet['A2'].fill.fgColor.rgb.endswith('FCE8B2')
        assert sheet['A3'].fill.fgColor.rgb.endswith('FCE8B2')
        assert sheet['A4'].fill.fgColor.rgb.endswith('D9EAF7')
        assert sheet['A5'].fill.fgColor.rgb.endswith('F4CCCC')
        book.close()
