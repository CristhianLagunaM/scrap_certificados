from pathlib import Path
import os


def int_env(name: str, default: int, minimum: int = 1) -> int:
    try:
        return max(minimum, int(os.getenv(name, str(default))))
    except ValueError:
        return default


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
    "Fila Excel",
    "Estado procesamiento",
    "Motivo",
    "Credencial PDF",
    "Credencial normalizada",
    "Fuente credencial",
    "Credencial Excel control",
    "Comparación credencial Excel",
    "Programa PDF",
    "Programa Excel control",
    "Programa usado para clasificación",
    "Fuente programa",
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
MAX_OCR_PAGES = int_env("LEGALIZACION_MAX_OCR_PAGES", 0, minimum=0)
PRIORITY_OCR_PAGES = int_env("LEGALIZACION_PRIORITY_OCR_PAGES", 1)
OCR_DPI_SCALE = int_env("LEGALIZACION_OCR_DPI_SCALE", 2)
OCR_VARIANT_LIMIT = int_env("LEGALIZACION_OCR_VARIANT_LIMIT", 1)
OCR_PSM_MODES = tuple(mode.strip() for mode in os.getenv("LEGALIZACION_OCR_PSM_MODES", "6").split(",") if mode.strip()) or ("6",)
OCR_WORKERS = int_env("LEGALIZACION_OCR_WORKERS", 4)
PROCESSING_WORKERS = int_env("LEGALIZACION_WORKERS", 6)
HTTP_POOL_SIZE = int_env("LEGALIZACION_HTTP_POOL_SIZE", 8)

TEMP_DIR_NAME = "_temporales"
WORK_DIR_PREFIX = "legalizacion_inscripcion_"
REPORT_FILENAME = "reporte_descargas.xlsx"

INVALID_FILENAME_CHARS = '<>:"/\\|?*'

PROJECT_ROOT = Path(__file__).resolve().parent
