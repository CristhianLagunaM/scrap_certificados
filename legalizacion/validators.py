import re
from urllib.parse import urlparse

from .text_utils import is_blank


def is_valid_url(value: object) -> bool:
    if is_blank(value):
        return False
    parsed = urlparse(str(value).strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def validate_credential(value: str) -> tuple[bool, str]:
    if value is None or value == "":
        return False, "Credencial vacia"
    if not value.isdigit():
        return False, "Credencial invalida: contiene caracteres no permitidos"
    if len(value) > 5:
        return False, "Credencial invalida: supera 5 digitos"
    return True, ""


def normalize_excel_credentials(value: object) -> list[str]:
    if is_blank(value):
        return []
    text = str(value).strip()
    parts = re.split(r"[;\n]+", text)
    credentials: list[str] = []
    for part in parts:
        candidate = part.strip()
        if not candidate:
            continue
        if re.fullmatch(r"\d{1,5}", candidate):
            credentials.append(candidate)
        else:
            return []
    return credentials


def compare_credentials(pdf_credentials: list[str], excel_credentials: list[str]) -> str:
    if not pdf_credentials:
        return "No se pudo identificar credencial en PDF"
    if not excel_credentials:
        return "Excel sin credencial para comparar"
    return "Coincide con Excel" if pdf_credentials == excel_credentials else "Difiere de Excel"


def sanitize_filename_part(value: str) -> str:
    from .config import INVALID_FILENAME_CHARS

    cleaned = "".join("_" if char in INVALID_FILENAME_CHARS else char for char in value)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or "archivo"

