from pathlib import Path
import os


SHEET_NAME = "Worksheet"

COLUMN_CREDENTIALS_MAIN = "NÚMERO DE CREDENCIAL(ES) (APARECEN EN EL COMPROBANTE DE INSCRIPCIÓN)"
COLUMN_CREDENTIALS_FALLBACK = "NÚMERO DE CREDENCIAL DE INSCRIPCIÓN (APARECE EN EL COMPROBANTE DE INSCRIPCIÓN)"
COLUMN_PROGRAM = "PROGRAMA ACADÉMICO AL QUE REALIZO LA INSCRIPCIÓN"
COLUMN_INSCRIPTION_TYPE = "TIPO DE INSCRIPCIÓN"
COLUMN_PDF_URL = 'ADJUNTE EN "UN SOLO" ARCHIVO PDF LOS DOCUMENTOS DE LEGALIZACIÓN  DE LA INSCRIPCIÓN'

REQUIRED_COLUMNS = [
    COLUMN_CREDENTIALS_MAIN,
    COLUMN_CREDENTIALS_FALLBACK,
    COLUMN_PROGRAM,
    COLUMN_INSCRIPTION_TYPE,
    COLUMN_PDF_URL,
]

REPORT_COLUMNS = [
    "Estado procesamiento",
    "Motivo",
    "Credencial PDF",
    "Credencial normalizada",
    "Fuente credencial",
    "Credencial Excel control",
    "Comparación credencial Excel",
    "Código programa",
    "Categoría destino",
    "Subcategoría destino",
    "Ruta relativa destino",
    "Nombre archivo generado",
    "URL procesada",
    "Fecha procesamiento",
]

CUPO_ESPECIAL = {
    "DESPLAZADO": "Desplazado",
    "INDIGENA": "Indígenas",
    "NEGRITUDES": "Negritudes",
    "LEY 1084": "Ley 1084",
    "PROGRAMA PARA LA PAZ": "Programa para la paz",
}

TRANSFERENCIA = {
    "TRANSFERENCIA INTERNA": "Transferencia interna",
    "TRANSFERENCIA EXTERNA": "Transferencia externa",
}

PROFESIONALIZACION_INGENIERIAS_TECNOLOGICA = {"372", "373", "375", "377", "583", "579", "678"}
PROFESIONALIZACION_MEDIO_AMBIENTE = {"710", "732", "780", "781", "785"}

NORMAL_CATEGORY_ENABLED = True

MIN_TEXT_LENGTH_FOR_PDF_TEXT = 40
DOWNLOAD_TIMEOUT_SECONDS = 45
MAX_OCR_PAGES = 3
PRIORITY_OCR_PAGES = 2
OCR_DPI_SCALE = 2
PROCESSING_WORKERS = max(2, int(os.getenv("LEGALIZACION_WORKERS", "6")))
HTTP_POOL_SIZE = max(8, int(os.getenv("LEGALIZACION_HTTP_POOL_SIZE", "16")))

TEMP_DIR_NAME = "_temporales"
WORK_DIR_PREFIX = "legalizacion_inscripcion_"
REPORT_FILENAME = "reporte_descargas.xlsx"

INVALID_FILENAME_CHARS = '<>:"/\\|?*'

PROJECT_ROOT = Path(__file__).resolve().parent
