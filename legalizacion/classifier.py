import re
from dataclasses import dataclass

from . import config
from .text_utils import normalize_key


@dataclass(frozen=True)
class Classification:
    category: str
    subcategory: str
    program_code: str
    relative_folder: str


def extract_program_code(program_value: object) -> str:
    text = "" if program_value is None else str(program_value).strip()
    match = re.match(r"^\((\d+)\)", text)
    if match:
        return match.group(1)

    match = re.search(r"\bopci[oó]n\s+\d+\s*:\s*(\d{1,4})\s*-", text, re.IGNORECASE)
    if match:
        return match.group(1)

    match = re.match(r"^(\d{1,4})\s*-", text)
    return match.group(1) if match else ""


def classify(program_value: object, inscription_type_value: object) -> Classification:
    program_code = extract_program_code(program_value)
    if not program_code:
        raise ValueError("No se pudo extraer codigo de programa")

    if program_code in config.PROFESIONALIZACION_INGENIERIAS_TECNOLOGICA:
        return Classification(
            "PROFESIONALIZACION",
            "Ingenierias tecnologica",
            program_code,
            f"PROFESIONALIZACION/Ingenierias tecnologica/{program_code}",
        )

    if program_code in config.PROFESIONALIZACION_MEDIO_AMBIENTE:
        return Classification(
            "PROFESIONALIZACION",
            "Profesionalizacion medio ambiente",
            program_code,
            f"PROFESIONALIZACION/Profesionalizacion medio ambiente/{program_code}",
        )

    normalized_type = normalize_key(inscription_type_value)
    if normalized_type in config.CUPO_ESPECIAL:
        subcategory = config.CUPO_ESPECIAL[normalized_type]
        return Classification("CUPO ESPECIAL", subcategory, program_code, f"CUPO ESPECIAL/{subcategory}")

    if normalized_type.startswith("MEJOR BACHILLER"):
        subcategory = "Mejor Bachiller"
        return Classification("CUPO ESPECIAL", subcategory, program_code, f"CUPO ESPECIAL/{subcategory}")

    if normalized_type in config.TRANSFERENCIA:
        subcategory = config.TRANSFERENCIA[normalized_type]
        return Classification("TRANSFERENCIA", subcategory, program_code, f"TRANSFERENCIA/{subcategory}/{program_code}")

    if normalized_type == "NORMAL" and config.NORMAL_CATEGORY_ENABLED:
        return Classification("NORMAL", "", program_code, f"NORMAL/{program_code}")

    program_key = normalize_key(program_value)
    if "CICLOS PROPEDÉUTICOS" in str(program_value).upper() or "PROFESIONALIZACION" in program_key or "PROF. TECNOLOGOS" in program_key:
        raise ValueError("Programa no configurado para clasificacion automatica")

    raise ValueError("Tipo de inscripcion no configurado")
