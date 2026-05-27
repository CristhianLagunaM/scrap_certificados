import re
import threading
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import fitz
from PIL import Image, ImageOps

from . import config
from .text_utils import strip_accents
from .validators import validate_credential


OCR_SEMAPHORE = threading.BoundedSemaphore(config.OCR_WORKERS)


@dataclass(frozen=True)
class CredentialExtraction:
    raw_credentials: list[str]
    normalized_credentials: list[str]
    source: str
    text: str
    transfer_inscription_type: str = ""
    academic_program: str = ""


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

            fallback_budget = ocr_page_budget(len(document))
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
        if "credencial" not in line.lower():
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


def find_transfer_inscription_type(text: str) -> str:
    normalized_lines = [normalize_line(line) for line in text.splitlines() if normalize_line(line)]
    for index, line in enumerate(normalized_lines):
        if "tipo de inscripcion" not in line.lower():
            continue

        nearby = [line]
        if index + 1 < len(normalized_lines):
            nearby.append(normalized_lines[index + 1])
        if index + 2 < len(normalized_lines):
            nearby.append(normalized_lines[index + 2])

        inscription_type = extract_transfer_type_from_segment(" ".join(nearby))
        if inscription_type:
            return inscription_type

    return extract_transfer_type_from_segment(normalize_line(text))


def find_academic_program(text: str) -> str:
    normalized_lines = [normalize_line(line) for line in text.splitlines() if normalize_line(line)]
    fallback_program = ""
    for index, line in enumerate(normalized_lines):
        if "programa academico" not in line.lower():
            continue

        nearby = [line]
        for offset in range(1, 4):
            if index + offset < len(normalized_lines):
                nearby.append(normalized_lines[index + offset])

        program = extract_academic_program_from_segment(" ".join(nearby))
        if academic_program_has_code(program):
            return program
        if program and not fallback_program:
            fallback_program = program

    normalized_text = normalize_line(text)
    option_program = extract_academic_program_option(normalized_text)
    if option_program:
        return option_program

    program = extract_academic_program_from_segment(normalized_text)
    if academic_program_has_code(program):
        return program

    return fallback_program or program


def extract_academic_program_from_segment(text: str) -> str:
    match = re.search(r"programa academico\s*:?\s*", normalize_line(text), re.IGNORECASE)
    if not match:
        return ""

    segment = text[match.end():].strip()
    next_label = re.search(
        r"\b(?:credencial|nombres y apellidos|tipo de documento|documento de identidad|fecha expedicion|correo electronico|telefono|medio por el cual|se presenta|tipo de inscripcion)\b\s*:?",
        segment,
        re.IGNORECASE,
    )
    if next_label:
        segment = segment[: next_label.start()]

    return segment.strip(" :-")


def extract_academic_program_option(text: str) -> str:
    match = re.search(r"\bopci[oó]n\s+\d+\s*:\s*\d{1,4}\s*-\s*", text, re.IGNORECASE)
    if not match:
        return ""

    segment = text[match.start():].strip()
    next_label = re.search(
        r"\b(?:credencial|nombres y apellidos|tipo de documento|documento de identidad|fecha expedicion|correo electronico|telefono|medio por el cual|se presenta|tipo de inscripcion|nombre del colegio)\b\s*:?",
        segment,
        re.IGNORECASE,
    )
    if next_label and next_label.start() > 0:
        segment = segment[: next_label.start()]

    segment = re.sub(r"\bprograma academico\s*:?\s*", "", segment, flags=re.IGNORECASE)
    return segment.strip(" :-")


def academic_program_has_code(program: str) -> bool:
    return bool(re.search(r"\bopci[oó]n\s+\d+\s*:\s*\d{1,4}\s*-", program, re.IGNORECASE) or re.match(r"^\d{1,4}\s*-", program))


def extract_transfer_type_from_segment(text: str) -> str:
    normalized = normalize_line(text).upper()
    if "TRANSFERENCIA INTERNA" in normalized:
        return "TRANSFERENCIA INTERNA"
    if "TRANSFERENCIA EXTERNA" in normalized:
        return "TRANSFERENCIA EXTERNA"
    return ""


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
        transfer_inscription_type=find_transfer_inscription_type(text),
        academic_program=find_academic_program(text),
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
        for image in build_ocr_images(page):
            for psm in config.OCR_PSM_MODES:
                text = run_tesseract(pytesseract, image, psm)
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
    match = re.search(r"credencial(?:es|\(es\))?\s*[:#=\-]?\s*", text, re.IGNORECASE)
    if not match:
        return text

    segment = text[match.end():]
    next_label = re.search(r"\b[a-z][a-z0-9 .()/-]{2,90}:", segment, re.IGNORECASE)
    if next_label:
        segment = segment[:next_label.start()]
    return segment


def extract_digit_candidates(text: str) -> list[str]:
    candidates: list[str] = []
    normalized = strip_accents(text or "")
    candidate_pattern = re.compile(r"(?<![a-z0-9])(?:[0-9OoQDIliSsB][\s.\-_:;]?){1,5}(?![a-z0-9])")
    for match in candidate_pattern.finditer(normalized):
        raw_token = re.sub(r"[\s.\-_:;]", "", match.group(0))
        if not re.search(r"\d", raw_token):
            continue
        token = normalize_numeric_ocr(raw_token)
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
    blank_pages: list[tuple[int, fitz.Page, str]] = []
    other_pages: list[tuple[int, fitz.Page, str]] = []

    for index, page, page_text in pages:
        normalized = normalize_line(page_text).lower()
        if index == 0:
            priority.append((index, page, page_text))
            continue
        if "credencial" in normalized or "comprobante" in normalized or "inscripcion" in normalized:
            priority.append((index, page, page_text))
            continue
        if len(normalized) < config.MIN_TEXT_LENGTH_FOR_PDF_TEXT:
            blank_pages.append((index, page, page_text))
            continue
        other_pages.append((index, page, page_text))

    ordered = priority[: config.PRIORITY_OCR_PAGES] + blank_pages + priority[config.PRIORITY_OCR_PAGES:] + other_pages
    budget = ocr_page_budget(len(pages))
    return ordered[:budget]


def ocr_page_budget(page_count: int) -> int:
    if config.MAX_OCR_PAGES <= 0:
        return page_count
    return min(page_count, config.MAX_OCR_PAGES)


def build_ocr_images(page: fitz.Page) -> list[Image.Image]:
    matrix = fitz.Matrix(config.OCR_DPI_SCALE, config.OCR_DPI_SCALE)
    images: list[Image.Image] = []

    for clip in build_ocr_regions(page.rect)[: config.OCR_VARIANT_LIMIT]:
        pixmap = page.get_pixmap(matrix=matrix, alpha=False, clip=clip)
        image = Image.open(BytesIO(pixmap.tobytes("png")))
        images.append(preprocess_for_ocr(image))

    return images


def build_ocr_regions(rect: fitz.Rect) -> list[fitz.Rect]:
    width = rect.width
    height = rect.height
    return [
        fitz.Rect(rect.x0, rect.y0, rect.x1, rect.y0 + height * 0.45),
        fitz.Rect(rect.x0 + width * 0.04, rect.y0 + height * 0.05, rect.x0 + width * 0.92, rect.y0 + height * 0.38),
        rect,
    ]


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

    fallback_text = ""
    best_extraction: CredentialExtraction | None = None
    for image in build_ocr_images(page):
        for psm in config.OCR_PSM_MODES:
            text = run_tesseract(pytesseract, image, psm)
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
                if academic_program_has_code(extraction.academic_program):
                    return extraction, text
                if best_extraction is None:
                    best_extraction = extraction

    if best_extraction:
        enhanced = enhance_program_extraction(page, page_text, best_extraction.text, page_number, pytesseract)
        if enhanced:
            return enhanced, fallback_text
        return best_extraction, fallback_text

    return None, fallback_text


def enhance_program_extraction(
    page: fitz.Page,
    page_text: str,
    ocr_text: str,
    page_number: int,
    pytesseract_module: object,
) -> CredentialExtraction | None:
    matrix = fitz.Matrix(max(config.OCR_DPI_SCALE, 3), max(config.OCR_DPI_SCALE, 3))
    for clip in build_ocr_regions(page.rect)[: max(config.OCR_VARIANT_LIMIT, 2)]:
        pixmap = page.get_pixmap(matrix=matrix, alpha=False, clip=clip)
        image = preprocess_for_ocr(Image.open(BytesIO(pixmap.tobytes("png"))))
        text = run_tesseract(pytesseract_module, image, "11")
        if not text.strip():
            continue

        combined_page_text = "\n".join(chunk for chunk in [page_text, ocr_text, text] if chunk.strip())
        extraction = build_extraction(
            find_credentials(combined_page_text),
            f"OCR pagina {page_number} (programa reforzado)",
            combined_page_text,
        )
        if extraction and academic_program_has_code(extraction.academic_program):
            return extraction

    return None


def run_tesseract(pytesseract_module: object, image: Image.Image, psm: str) -> str:
    with OCR_SEMAPHORE:
        return pytesseract_module.image_to_string(
            image,
            lang="spa+eng",
            config=f"--psm {psm} --oem 1",
        )
