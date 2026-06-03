from __future__ import annotations

import shutil
import uuid
import re
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

import fitz
import pandas as pd

from . import config
from .cancellation import CancellationCallback, ProcessingCancelled
from .downloader import download_pdf
from .pdf_credential_extractor import extract_text_ocr_from_page, find_credentials
from .report_writer import write_report
from .text_utils import is_blank, normalize_header, normalize_key
from .validators import is_valid_url, sanitize_filename_part
from .zipper import create_zip


ProgressCallback = Callable[[int, int, str], None]

URL_COLUMN = "URL procesada"
WORK_DIR_PREFIX = "legalizacion_soportes_"
REPORT_FILENAME = "reporte_soportes_legalizacion.xlsx"
PENDING_CREDENTIAL_PREFIX = "pendiente_credencial"

REPORT_COLUMNS = [
    "Fila Excel",
    "Estado procesamiento",
    "Motivo",
    "Credencial PDF",
    "Fuente credencial",
    "Tiene comprobante inscripción",
    "Categoría destino",
    "Frase detectada",
    "Fuente texto",
    "Ruta relativa destino",
    "Nombre archivo generado",
    "URL procesada",
    "Fecha procesamiento",
]

CATEGORY_PHRASES = {
    "Desplazados": [
        "Unidad para las victimas",
        "Registro único de victimas",
        "Registro unico de victimas",
        "Desplazamiento forzado",
        "hechos victimizantes",
        "Unidad para la atención y reparación integral a las víctimas",
        "Unidad para la atencion y reparacion integral a las victimas",
    ],
    "Indigenas": [
        "Asuntos indígenas, rom y Minorías del ministerio del interior",
    ],
    "Ley 1084": [
        "Secretaria de gobierno municipal",
        "Alcalde municipal",
    ],
    "Mejor bachiller": [
        "Director local de educación",
        "Mejor bachiller",
    ],
    "Negritudes": [
        "La dirección de asuntos para las comunidades negras, afrocolombianas, raizales y palenqueras del ministerio del interior",
        "Comunidades negras, afrocolombianas, raizales y palenqueras del ministerio del interior",
    ],
    "Programa para la paz": [
        "Agencia para la Reincorporación y la normalizacion",
        "Agencia para la Reincorporación y la normalización",
    ],
}


@dataclass(frozen=True)
class SupportClassification:
    category: str
    phrase: str


@dataclass(frozen=True)
class ProcessingSummary:
    total_rows: int
    downloaded: int
    not_downloaded: int
    omitted: int
    zip_path: Path
    report_path: Path
    work_dir: Path


@dataclass(frozen=True)
class RowProcessingResult:
    index: int
    data: dict[str, str]
    temp_pdf_path: Path | None = None
    category: str = ""
    credentials: list[str] | None = None


def process_excel(
    excel_path: str,
    output_dir: str,
    progress_callback: ProgressCallback | None = None,
    should_cancel: CancellationCallback | None = None,
) -> ProcessingSummary:
    dataframe, url_column = read_excel(excel_path)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S_%f")
    output_root = Path(output_dir).resolve()
    work_dir = output_root / f"{WORK_DIR_PREFIX}{timestamp}"
    documents_dir = work_dir / "documentos"
    temp_dir = work_dir / config.TEMP_DIR_NAME
    report_path = work_dir / REPORT_FILENAME
    zip_path = output_root / f"{WORK_DIR_PREFIX}{timestamp}.zip"

    documents_dir.mkdir(parents=True, exist_ok=True)
    temp_dir.mkdir(parents=True, exist_ok=True)

    for report_column in REPORT_COLUMNS:
        if report_column not in dataframe.columns:
            dataframe[report_column] = ""

    total = len(dataframe)
    workers = min(config.PROCESSING_WORKERS, max(total, 1))
    filename_counts: dict[tuple[str, str], int] = {}
    pending_counts: dict[str, int] = {}
    downloaded = 0
    not_downloaded = 0
    omitted = 0

    rows = list(dataframe.iterrows())
    if progress_callback:
        progress_callback(0, total, f"Iniciando clasificación de soportes con {workers} workers")

    completed = 0
    executor = ThreadPoolExecutor(max_workers=workers)
    future_map = {
        executor.submit(process_row, index, row, url_column, temp_dir): (position, index)
        for position, (index, row) in enumerate(rows, start=1)
    }
    pending = set(future_map)

    try:
        while pending:
            if should_cancel and should_cancel():
                cancel_pending_futures(pending)
                raise ProcessingCancelled()

            done, pending = wait(pending, timeout=0.5, return_when=FIRST_COMPLETED)
            if not done:
                continue

            for future in done:
                position, index = future_map[future]
                row_result = future.result()

                if should_cancel and should_cancel():
                    cleanup_row_result(row_result)
                    cancel_pending_futures(pending)
                    raise ProcessingCancelled()

                final_result = finalize_row_result(row_result, documents_dir, filename_counts, pending_counts)

                for key, value in final_result.items():
                    dataframe.at[index, key] = value

                if final_result["Estado procesamiento"] == "Descargada":
                    downloaded += 1
                elif final_result["Estado procesamiento"] == "Omitida":
                    omitted += 1
                else:
                    not_downloaded += 1

                completed += 1
                if progress_callback:
                    excel_row = final_result.get("Fila Excel", str(index + 2))
                    category = final_result.get("Categoría destino", "")
                    category_text = f" [{category}]" if category else ""
                    progress_callback(completed, total, f"Fila Excel {excel_row} (registro {position}) completada{category_text}: {final_result['Motivo']}")
    except ProcessingCancelled:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise
    finally:
        executor.shutdown(wait=True, cancel_futures=True)

    write_report(build_report_dataframe(dataframe), report_path)
    create_zip(documents_dir, report_path, zip_path)
    shutil.rmtree(temp_dir, ignore_errors=True)

    return ProcessingSummary(
        total_rows=total,
        downloaded=downloaded,
        not_downloaded=not_downloaded,
        omitted=omitted,
        zip_path=zip_path,
        report_path=report_path,
        work_dir=work_dir,
    )


def read_excel(path: str) -> tuple[pd.DataFrame, str]:
    dataframe = pd.read_excel(path, dtype=str)
    normalized_columns = {normalize_header(column): column for column in dataframe.columns}
    url_column = normalized_columns.get(normalize_header(URL_COLUMN))
    if not url_column:
        raise ValueError(f"Falta la columna obligatoria: {URL_COLUMN}")
    return dataframe, url_column


def build_report_dataframe(dataframe: pd.DataFrame) -> pd.DataFrame:
    columns = [column for column in REPORT_COLUMNS if column in dataframe.columns]
    return dataframe.loc[:, columns].copy()


def cancel_pending_futures(futures: set[object]) -> None:
    for future in futures:
        future.cancel()


def cleanup_row_result(row_result: RowProcessingResult) -> None:
    if row_result.temp_pdf_path is not None and row_result.temp_pdf_path.exists():
        row_result.temp_pdf_path.unlink(missing_ok=True)


def process_row(index: int, row: pd.Series, url_column: str, temp_dir: Path) -> RowProcessingResult:
    processed_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    url = value_as_text(row.get(url_column))
    temp_pdf: Path | None = None
    base_result = {
        "Fila Excel": str(index + 2),
        "Estado procesamiento": "No descargada",
        "Motivo": "",
        "Credencial PDF": "",
        "Fuente credencial": "No identificada",
        "Tiene comprobante inscripción": "No",
        "Categoría destino": "",
        "Frase detectada": "",
        "Fuente texto": "",
        "Ruta relativa destino": "",
        "Nombre archivo generado": "",
        "URL procesada": url,
        "Fecha procesamiento": processed_at,
    }

    try:
        if not url:
            raise RuntimeError("URL procesada vacia")
        if not is_valid_url(url):
            raise RuntimeError("URL procesada invalida")

        temp_pdf = temp_dir / f"fila_{uuid.uuid4().hex}.pdf"
        download_pdf(url, temp_pdf)

        text_result = extract_document_text(temp_pdf)
        classification = classify_support(text_result.text)
        if not classification:
            raise RuntimeError("No se encontro ninguna frase configurada para clasificar el soporte")

        credentials = find_credentials(text_result.text)
        credentials = remove_redundant_short_credentials(credentials)
        has_receipt = has_inscription_receipt(text_result.text)
        base_result.update(
            {
                "Credencial PDF": ";".join(credentials),
                "Fuente credencial": text_result.source if credentials else "No identificada",
                "Tiene comprobante inscripción": "Si" if has_receipt else "No",
                "Categoría destino": classification.category,
                "Frase detectada": classification.phrase,
                "Fuente texto": text_result.source,
            }
        )

        return RowProcessingResult(
            index=index,
            data=base_result,
            temp_pdf_path=temp_pdf,
            category=classification.category,
            credentials=credentials,
        )
    except Exception as exc:
        if temp_pdf is not None and temp_pdf.exists():
            temp_pdf.unlink(missing_ok=True)
        base_result["Motivo"] = str(exc)
        return RowProcessingResult(index=index, data=base_result)


def finalize_row_result(
    row_result: RowProcessingResult,
    documents_dir: Path,
    filename_counts: dict[tuple[str, str], int],
    pending_counts: dict[str, int],
) -> dict[str, str]:
    result = dict(row_result.data)
    if row_result.temp_pdf_path is None or not row_result.category or row_result.credentials is None:
        return result

    filename = build_filename(row_result.category, row_result.credentials, filename_counts, pending_counts)
    destination = documents_dir / row_result.category / filename
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(row_result.temp_pdf_path), destination)

    result.update(
        {
            "Estado procesamiento": "Descargada",
            "Motivo": "Documento descargado y clasificado correctamente",
            "Ruta relativa destino": destination.relative_to(documents_dir).as_posix(),
            "Nombre archivo generado": filename,
        }
    )
    return result


def build_filename(
    category: str,
    credentials: list[str],
    filename_counts: dict[tuple[str, str], int],
    pending_counts: dict[str, int],
) -> str:
    if credentials:
        safe_base = sanitize_filename_part("-".join(credentials))
        key = (category, safe_base)
        count = filename_counts.get(key, 0)
        filename_counts[key] = count + 1
        return f"{safe_base}{'.' * count}.pdf"

    count = pending_counts.get(category, 0) + 1
    pending_counts[category] = count
    return f"{PENDING_CREDENTIAL_PREFIX}_{count}.pdf"


@dataclass(frozen=True)
class DocumentText:
    text: str
    source: str


def extract_document_text(path: Path) -> DocumentText:
    chunks: list[str] = []
    sources: list[str] = []
    try:
        with fitz.open(path) as document:
            pages = [(index, page, page.get_text("text")) for index, page in enumerate(document)]
            pdf_text = "\n".join(page_text for _, _, page_text in pages if page_text.strip())
            if pdf_text.strip():
                chunks.append(pdf_text)
                sources.append("Texto PDF")

            if should_try_ocr_for_support(pdf_text):
                ocr_chunks = []
                for index, page, _ in pages[: ocr_page_budget(len(pages))]:
                    ocr_text = extract_text_ocr_from_page(page)
                    if ocr_text.strip():
                        ocr_chunks.append(ocr_text)
                        sources.append(f"OCR pagina {index + 1}")
                if ocr_chunks:
                    chunks.append("\n".join(ocr_chunks))
    except RuntimeError:
        if chunks:
            return DocumentText("\n".join(chunks), ", ".join(dict.fromkeys(sources)))
        raise
    except Exception as exc:
        raise RuntimeError("Archivo no utilizable") from exc

    text = "\n".join(chunks)
    if not text.strip():
        raise RuntimeError("No se pudo extraer texto del PDF ni con OCR")
    return DocumentText(text, ", ".join(dict.fromkeys(sources)) or "Texto PDF/OCR")


def should_try_ocr_for_support(text: str) -> bool:
    return (
        len(normalize_key(text)) < config.MIN_TEXT_LENGTH_FOR_PDF_TEXT
        or classify_support(text) is None
        or not find_credentials(text)
    )


def ocr_page_budget(page_count: int) -> int:
    if config.MAX_OCR_PAGES <= 0:
        return page_count
    return min(page_count, config.MAX_OCR_PAGES)


def classify_support(text: str) -> SupportClassification | None:
    normalized_text = normalize_for_match(text)
    for category, phrases in CATEGORY_PHRASES.items():
        for phrase in phrases:
            if phrase_matches(normalized_text, phrase):
                return SupportClassification(category, phrase)
    return None


def phrase_matches(normalized_text: str, phrase: str) -> bool:
    normalized_phrase = normalize_for_match(phrase)
    if not normalized_phrase:
        return False
    pattern = rf"(?<!\w){re.escape(normalized_phrase)}(?!\w)"
    return bool(re.search(pattern, normalized_text))


def has_inscription_receipt(text: str) -> bool:
    normalized = normalize_for_match(text)
    return phrase_matches(normalized, "comprobante de inscripcion")


def normalize_for_match(value: object) -> str:
    normalized = normalize_key(value)
    normalized = re.sub(r"[^0-9A-Z]+", " ", normalized)
    return " ".join(normalized.casefold().split())


def remove_redundant_short_credentials(credentials: list[str]) -> list[str]:
    if len(credentials) <= 1:
        return credentials
    longest = max((len(credential) for credential in credentials), default=0)
    if longest <= 1:
        return credentials
    filtered = [credential for credential in credentials if len(credential) > 1]
    return filtered or credentials


def value_as_text(value: object) -> str:
    if is_blank(value):
        return ""
    return str(value).strip()
