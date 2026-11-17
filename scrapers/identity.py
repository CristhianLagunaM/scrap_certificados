import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from itertools import combinations

IDENTITY_MATCH_THRESHOLD = 85.0


def normalize_text(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", text).strip().upper()


@dataclass(frozen=True)
class IdentityValidation:
    status: str
    detail: str
    document_matches: bool
    surnames_score: float | None = None
    names_score: float | None = None
    certificate_name: str = ""
    review: bool = False
    overall_score: float | None = None


def validate_pdf_identity(
    pdf_text: str,
    expected_doc: str,
    expected_names: list[str] | None = None,
    *,
    threshold: float = IDENTITY_MATCH_THRESHOLD,
) -> IdentityValidation:
    """Documento exacto; evaluar apellidos, nombres y similitud global."""
    if not 0 <= threshold <= 100:
        raise ValueError("Umbral de nombres debe estar entre 0 y 100")
    text = normalize_text(pdf_text)
    doc = re.sub(r"\D", "", str(expected_doc or ""))
    # Los dígitos deben pertenecer a un número completo, no a un documento mayor.
    person = re.search(
        r"SENOR(?:\(A\)|A)?[\s,:]+(?P<name>[A-Z '\-]+?)[,.]?\s+"
        r"IDENTIFICAD[OA](?:\(A\))?\s+(?P<identity>[^,;]{1,180})",
        text,
    )
    identity_text = person.group("identity") if person else text
    numbers = re.findall(r"\d+(?:[ .-]+\d+)*", identity_text)
    documents = {
        re.sub(r"\D", "", value)
        for value in (numbers[:1] if person else numbers)
    }
    if not doc or doc not in documents:
        return IdentityValidation("ERROR", f"PDF no contiene documento esperado {doc}", False)

    parts = [normalize_text(value) for value in (expected_names or [])]
    if len(parts) != 2 or any(value in {"", "NAN", "NONE", "<NA>"} for value in parts):
        return IdentityValidation(
            "REVISAR", "Documento coincide; faltan nombres o apellidos para validar identidad",
            True, review=True,
        )
    given, surnames = parts
    if not person:
        return IdentityValidation(
            "REVISAR", "Documento coincide; no fue posible extraer nombre del titular",
            True, review=True,
        )

    certificate_name = person.group("name").strip()
    cert_tokens = certificate_name.split()
    surname_count = len(surnames.split())
    full_name = f"{given} {surnames}"
    layouts = [
        (cert_tokens[:-surname_count], cert_tokens[-surname_count:], False),
        (cert_tokens[surname_count:], cert_tokens[:surname_count], True),
    ]
    scored_layouts = []
    for given_tokens, surname_tokens, reversed_order in layouts:
        cert_surnames = " ".join(surname_tokens)
        surname_similarity = SequenceMatcher(None, surnames, cert_surnames).ratio() * 100
        candidates = [" ".join(given_tokens)]
        # El Excel puede omitir nombres adicionales; conservar palabras y orden interno.
        count = len(given.split())
        if count < len(given_tokens) <= 6:
            candidates.extend(" ".join(tokens) for tokens in combinations(given_tokens, count))
        name_similarity = max(SequenceMatcher(None, given, value).ratio() * 100 for value in candidates)
        global_similarity = max(
            SequenceMatcher(None, full_name, f"{value} {cert_surnames}").ratio() * 100
            for value in candidates
        )
        scored_layouts.append((global_similarity, surname_similarity, name_similarity, given_tokens, cert_surnames, reversed_order))
    raw_overall, raw_surnames, raw_names, cert_given, cert_surnames, reversed_order = max(
        scored_layouts, key=lambda item: (item[0], item[1], item[2]),
    )
    surname_score = round(raw_surnames, 2)
    score = round(raw_names, 2)
    overall = round(raw_overall, 2)
    accepted = raw_overall >= threshold
    # Una omisión o diferencia ortográfica queda visible, incluso si fue aceptada.
    review = full_name != f"{' '.join(cert_given)} {cert_surnames}"
    detail = (
        f"Documento exacto; apellidos {surname_score:.2f}%; nombres {score:.2f}%; "
        f"coincidencia global {overall:.2f}% (umbral {threshold:g}%); "
        f"Excel: {full_name}; certificado: {certificate_name}"
    )
    if reversed_order:
        detail += "; orden del certificado: apellidos y nombres"
    if not accepted:
        detail += "; requiere revisión manual"
    elif review:
        detail += "; aceptado con diferencias; revisar"
    return IdentityValidation(
        "OK" if accepted else "REVISAR", detail, True, surname_score, score,
        certificate_name, review or not accepted, overall,
    )
