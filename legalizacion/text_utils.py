import re
import unicodedata


def strip_accents(value: str) -> str:
    normalized = unicodedata.normalize("NFD", value)
    return "".join(char for char in normalized if unicodedata.category(char) != "Mn")


def normalize_header(value: object) -> str:
    text = "" if value is None else str(value)
    text = strip_accents(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip().casefold()


def normalize_key(value: object) -> str:
    text = "" if value is None else str(value)
    text = strip_accents(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip().upper()


def is_blank(value: object) -> bool:
    if value is None:
        return True
    text = str(value).strip()
    return text == "" or text.lower() == "nan"

