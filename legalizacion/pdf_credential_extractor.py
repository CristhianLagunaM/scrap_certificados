import re
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import fitz
from PIL import Image, ImageOps

from . import config
from .text_utils import strip_accents
from .validators import validate_credential


@dataclass(frozen=True)
class CredentialExtraction:
    raw_credentials: list[str]
    normalized_credentials: list[str]
    source: str
    text: str


def extract_credentials_from_pdf(path: Path) -> CredentialExtraction:
    try:
        with fitz.open(path) as document:
            collected_chunks: list[str] = []
            pages = []

            for index, page in enumerate(document):
                page_text = page.get_text("text")
                pages.append((index, page, page_text))
                if page_text.strip():
                    collected_chunks.append(page_text)
                    extraction = build_extraction(find_credentials(page_text), f"Texto PDF pagina {index + 1}", page_text)
                    if extraction:
                        return extraction

            ocr_candidates = prioritize_ocr_pages(pages)
            ocr_processed: set[int] = set()
            for index, page, page_text in ocr_candidates:
                ocr_processed.add(index)
                extraction, ocr_text = extract_with_ocr(page, page_text, index + 1)
                if ocr_text.strip():
                    collected_chunks.append(ocr_text)
                if extraction:
                    return extraction

            fallback_budget = max(len(document), config.MAX_OCR_PAGES)
            for index, page, page_text in pages:
                if index in ocr_processed:
                    continue
                if len(ocr_processed) >= fallback_budget:
                    break
                ocr_processed.add(index)
                if not should_try_ocr(page_text):
                    continue
                extraction, ocr_text = extract_with_ocr(page, page_text, index + 1)
                if ocr_text.strip():
                    collected_chunks.append(ocr_text)
                if extraction:
                    return extraction
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError("Archivo no utilizable") from exc

    combined_text = "\n".join(collected_chunks)
    if not combined_text.strip():
        raise RuntimeError("No se pudo extraer texto del PDF ni con OCR")

    extraction = build_extraction(find_credentials(combined_text), "Texto consolidado PDF/OCR", combined_text)
    if extraction:
        return extraction

    raise RuntimeError("No se pudo identificar credencial en PDF")


def extract_text_pdf(path: Path) -> str:
    try:
        with fitz.open(path) as document:
            return "\n".join(page.get_text("text") for page in document)
    except Exception as exc:
        raise RuntimeError("Archivo no utilizable") from exc


def extract_text_ocr(path: Path) -> str:
    try:
        import pytesseract
    except ImportError as exc:
        raise RuntimeError("No se pudo extraer texto del PDF ni con OCR: pytesseract no esta instalado") from exc

    try:
        chunks: list[str] = []
        with fitz.open(path) as document:
            for page in document:
                chunks.append(extract_text_ocr_from_page(page))
        return "\n".join(chunks)
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(f"No se pudo extraer texto del PDF ni con OCR: {exc}") from exc


def find_credentials(text: str) -> list[str]:
    credentials: list[str] = []
    seen: set[str] = set()
    normalized_lines = [normalize_line(line) for line in text.splitlines() if normalize_line(line)]

    for index, line in enumerate(normalized_lines):
        if "credencial" not in line:
            continue

        nearby = [line]
        if index + 1 < len(normalized_lines):
            nearby.append(normalized_lines[index + 1])
        if index + 2 < len(normalized_lines):
            nearby.append(normalized_lines[index + 2])

        segment = trim_after_keyword(" ".join(nearby))
        tokens = extract_digit_candidates(segment)
        for token in tokens:
            if token not in seen:
                credentials.append(token)
                seen.add(token)

    if credentials:
        return credentials

    searchable = normalize_line(strip_accents(text))
    for match in build_credential_pattern().finditer(searchable):
        segment = trim_after_keyword(match.group(0))
        for token in extract_digit_candidates(segment):
            if token not in seen:
                credentials.append(token)
                seen.add(token)
    return credentials


def build_extraction(credentials: list[str], source: str, text: str) -> CredentialExtraction | None:
    normalized: list[str] = []
    for credential in credentials:
        candidate = credential.strip()
        valid, reason = validate_credential(candidate)
        if not valid:
            if reason == "Credencial invalida: supera 5 digitos":
                continue
            if reason == "Credencial invalida: contiene caracteres no permitidos":
                continue
            continue
        normalized.append(candidate)

    if not normalized:
        return None

    return CredentialExtraction(
        raw_credentials=normalized,
        normalized_credentials=normalized,
        source=source,
        text=text,
    )


def should_try_ocr(text: str) -> bool:
    normalized = normalize_line(text)
    return (
        len(normalized) < config.MIN_TEXT_LENGTH_FOR_PDF_TEXT
        or "credencial" in normalized
        or "comprobante de inscripcion" in normalized
    )


def extract_text_ocr_from_page(page: fitz.Page) -> str:
    try:
        import pytesseract
    except ImportError as exc:
        raise RuntimeError("No se pudo extraer texto del PDF ni con OCR: pytesseract no esta instalado") from exc

    try:
        matrix = fitz.Matrix(config.OCR_DPI_SCALE, config.OCR_DPI_SCALE)
        pixmap = page.get_pixmap(matrix=matrix, alpha=False)
        base_image = Image.open(BytesIO(pixmap.tobytes("png")))

        for image in build_ocr_variants(base_image):
            for psm in ("6", "11"):
                text = pytesseract.image_to_string(
                    image,
                    lang="spa+eng",
                    config=f"--psm {psm} --oem 1",
                )
                if text.strip():
                    return text

        return ""
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(f"No se pudo extraer texto del PDF ni con OCR: {exc}") from exc


def build_credential_pattern() -> re.Pattern[str]:
    return re.compile(
        r"(?:no\.?|nro\.?|numero(?:s)?(?:\s+de)?)?\s*credencial(?:es|\(es\))?[\s:#=\-]{0,8}[^\n]{0,80}",
        re.IGNORECASE,
    )


def trim_after_keyword(text: str) -> str:
    match = re.search(r"credencial(?:es|\(es\))?", text, re.IGNORECASE)
    if not match:
        return text

    segment = text[match.end():]
    next_label = re.search(r"\b[a-z][a-z0-9 .()/-]{2,40}:", segment, re.IGNORECASE)
    if next_label:
        segment = segment[:next_label.start()]
    return segment


def extract_digit_candidates(text: str) -> list[str]:
    candidates: list[str] = []
    normalized = normalize_numeric_ocr(text)
    for match in re.finditer(r"(?<!\d)(?:[0-9][\s.\-_:;]?){1,5}(?!\d)", normalized):
        token = re.sub(r"[\s.\-_:;]", "", match.group(0))
        if 1 <= len(token) <= 5:
            candidates.append(token)
    return candidates


def normalize_line(text: str) -> str:
    return re.sub(r"\s+", " ", strip_accents(text or "")).strip()


def normalize_numeric_ocr(text: str) -> str:
    normalized = strip_accents(text or "")
    replacements = str.maketrans({
        "O": "0",
        "o": "0",
        "Q": "0",
        "D": "0",
        "I": "1",
        "l": "1",
        "i": "1",
        "S": "5",
        "s": "5",
        "B": "8",
    })
    return normalized.translate(replacements)


def prioritize_ocr_pages(pages: list[tuple[int, fitz.Page, str]]) -> list[tuple[int, fitz.Page, str]]:
    priority: list[tuple[int, fitz.Page, str]] = []
    fallback: list[tuple[int, fitz.Page, str]] = []

    for index, page, page_text in pages:
        normalized = normalize_line(page_text).lower()
        if index == 0:
            priority.append((index, page, page_text))
            continue
        if "credencial" in normalized or "comprobante" in normalized or "inscripcion" in normalized:
            priority.append((index, page, page_text))
            continue
        if len(normalized) < config.MIN_TEXT_LENGTH_FOR_PDF_TEXT:
            fallback.append((index, page, page_text))

    selected = priority[: config.PRIORITY_OCR_PAGES]
    remaining_slots = max(config.MAX_OCR_PAGES - len(selected), 0)
    if remaining_slots:
        selected.extend(fallback[:remaining_slots])
    return selected


def build_ocr_variants(image: Image.Image) -> list[Image.Image]:
    width, height = image.size
    top_region = image.crop((0, 0, width, max(int(height * 0.45), 1)))
    focus_region = image.crop((
        max(int(width * 0.04), 0),
        max(int(height * 0.05), 0),
        min(int(width * 0.92), width),
        min(int(height * 0.38), height),
    ))

    variants = [
        preprocess_for_ocr(top_region),
        preprocess_for_ocr(focus_region),
        preprocess_for_ocr(image),
    ]
    return variants


def preprocess_for_ocr(image: Image.Image) -> Image.Image:
    grayscale = ImageOps.grayscale(image)
    enhanced = ImageOps.autocontrast(grayscale)
    binary = enhanced.point(lambda value: 255 if value > 185 else 0)
    return binary


def extract_with_ocr(page: fitz.Page, page_text: str, page_number: int) -> tuple[CredentialExtraction | None, str]:
    try:
        import pytesseract
    except ImportError as exc:
        raise RuntimeError("No se pudo extraer texto del PDF ni con OCR: pytesseract no esta instalado") from exc

    matrix = fitz.Matrix(config.OCR_DPI_SCALE, config.OCR_DPI_SCALE)
    pixmap = page.get_pixmap(matrix=matrix, alpha=False)
    base_image = Image.open(BytesIO(pixmap.tobytes("png")))

    fallback_text = ""
    for image in build_ocr_variants(base_image):
        for psm in ("6", "11"):
            text = pytesseract.image_to_string(
                image,
                lang="spa+eng",
                config=f"--psm {psm} --oem 1",
            )
            if not text.strip():
                continue
            if not fallback_text:
                fallback_text = text

            combined_page_text = "\n".join(chunk for chunk in [page_text, text] if chunk.strip())
            extraction = build_extraction(
                find_credentials(combined_page_text),
                f"OCR pagina {page_number}",
                combined_page_text,
            )
            if extraction:
                return extraction, text

    return None, fallback_text
