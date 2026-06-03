from __future__ import annotations

import shutil
import uuid
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

import pandas as pd

from . import config
from .cancellation import CancellationCallback, ProcessingCancelled
from .classifier import Classification, classify, extract_program_code
from .downloader import download_pdf
from .excel_reader import read_excel
from .pdf_credential_extractor import extract_credentials_from_pdf
from .report_writer import write_report
from .validators import compare_credentials, is_valid_url, normalize_excel_credentials, sanitize_filename_part
from .zipper import create_zip


ProgressCallback = Callable[[int, int, str], None]


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
    normalized_name: str = ""
    excel_credentials: list[str] | None = None
    raw_credentials: list[str] | None = None
    normalized_credentials: list[str] | None = None
    extraction_source: str = ""
    classification: Classification | None = None


def process_excel(
    excel_path: str,
    output_dir: str,
    progress_callback: ProgressCallback | None = None,
    should_cancel: CancellationCallback | None = None,
) -> ProcessingSummary:
    excel_data = read_excel(excel_path)
    dataframe = excel_data.dataframe.copy()
    columns = excel_data.columns

    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S_%f")
    output_root = Path(output_dir).resolve()
    work_dir = output_root / f"{config.WORK_DIR_PREFIX}{timestamp}"
    documents_dir = work_dir / "documentos"
    temp_dir = work_dir / config.TEMP_DIR_NAME
    report_path = work_dir / config.REPORT_FILENAME
    zip_path = output_root / f"{config.WORK_DIR_PREFIX}{timestamp}.zip"

    documents_dir.mkdir(parents=True, exist_ok=True)
    temp_dir.mkdir(parents=True, exist_ok=True)

    for report_column in config.REPORT_COLUMNS:
        if report_column not in dataframe.columns:
            dataframe[report_column] = ""

    filename_counts: dict[str, int] = {}
    total = len(dataframe)
    downloaded = 0
    not_downloaded = 0
    omitted = 0

    rows = list(dataframe.iterrows())
    workers = min(config.PROCESSING_WORKERS, max(total, 1))

    if progress_callback:
        progress_callback(0, total, f"Iniciando procesamiento concurrente con {workers} workers")

    completed = 0
    executor = ThreadPoolExecutor(max_workers=workers)
    future_map = {
        executor.submit(process_row, index, row, columns, temp_dir): (position, index)
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

                final_result = finalize_row_result(row_result, documents_dir, filename_counts)

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
                    progress_callback(completed, total, f"Fila Excel {excel_row} (registro {position}) completada: {final_result['Motivo']}")
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


def build_report_dataframe(dataframe: pd.DataFrame) -> pd.DataFrame:
    columns = [column for column in config.REPORT_COLUMNS if column in dataframe.columns]
    return dataframe.loc[:, columns].copy()


def cancel_pending_futures(futures: set[object]) -> None:
    for future in futures:
        future.cancel()


def cleanup_row_result(row_result: RowProcessingResult) -> None:
    if row_result.temp_pdf_path is not None and row_result.temp_pdf_path.exists():
        row_result.temp_pdf_path.unlink(missing_ok=True)


def process_row(
    index: int,
    row: pd.Series,
    columns: dict[str, str],
    temp_dir: Path,
) -> RowProcessingResult:
    processed_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    url = value_as_text(row.get(columns[config.COLUMN_PDF_URL]))
    temp_pdf: Path | None = None
    base_result = {
        "Fila Excel": str(index + 2),
        "Estado procesamiento": "No descargada",
        "Motivo": "",
        "Credencial PDF": "",
        "Credencial normalizada": "",
        "Fuente credencial": "No identificada",
        "Credencial Excel control": "",
        "Comparación credencial Excel": "No se pudo identificar credencial en PDF",
        "Programa PDF": "",
        "Programa Excel control": value_as_text(row.get(columns[config.COLUMN_PROGRAM])),
        "Programa usado para clasificación": "",
        "Fuente programa": "No identificado",
        "Código programa": "",
        "Categoría destino": "",
        "Subcategoría destino": "",
        "Ruta relativa destino": "",
        "Nombre archivo generado": "",
        "URL procesada": url,
        "Fecha procesamiento": processed_at,
    }

    try:
        if not url:
            raise RuntimeError("URL de documento vacia")
        if not is_valid_url(url):
            raise RuntimeError("URL de documento invalida")

        temp_pdf = temp_dir / f"fila_{uuid.uuid4().hex}.pdf"
        download_pdf(url, temp_pdf)

        extraction = extract_credentials_from_pdf(temp_pdf)
        inscription_type = extraction.transfer_inscription_type or row.get(columns[config.COLUMN_INSCRIPTION_TYPE])
        excel_program = value_as_text(row.get(columns[config.COLUMN_PROGRAM]))
        pdf_program = extraction.academic_program
        pdf_program_has_code = bool(extract_program_code(pdf_program))
        program = pdf_program if pdf_program_has_code else excel_program
        base_result.update(
            {
                "Programa PDF": pdf_program,
                "Programa Excel control": excel_program,
                "Programa usado para clasificación": program,
                "Fuente programa": (
                    f"PDF ({extraction.source})"
                    if pdf_program_has_code
                    else ("Excel (programa PDF sin codigo)" if pdf_program and excel_program else ("Excel" if excel_program else "No identificado"))
                ),
            }
        )
        classification = classify(program, inscription_type)
        base_result.update(classification_to_report(classification))

        normalized_credentials = extraction.normalized_credentials
        raw_credentials = extraction.raw_credentials
        excel_credentials = get_excel_credentials(row, columns)
        normalized_credentials = reconcile_credentials(normalized_credentials, excel_credentials)
        raw_credentials = reconcile_credentials(raw_credentials, excel_credentials)
        normalized_name = "-".join(normalized_credentials)
        return RowProcessingResult(
            index=index,
            data=base_result,
            temp_pdf_path=temp_pdf,
            normalized_name=normalized_name,
            excel_credentials=excel_credentials,
            raw_credentials=raw_credentials,
            normalized_credentials=normalized_credentials,
            extraction_source=extraction.source,
            classification=classification,
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
) -> dict[str, str]:
    result = dict(row_result.data)

    if (
        row_result.temp_pdf_path is None
        or row_result.classification is None
        or not row_result.normalized_name
        or row_result.normalized_credentials is None
        or row_result.raw_credentials is None
        or row_result.excel_credentials is None
    ):
        return result

    comparison = compare_credentials(row_result.normalized_credentials, row_result.excel_credentials)
    folder_key = row_result.classification.relative_folder
    filename = build_unique_filename(row_result.normalized_name, folder_key, filename_counts)
    destination = documents_dir / row_result.classification.relative_folder / filename
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(row_result.temp_pdf_path), destination)
    relative_path = destination.relative_to(documents_dir).as_posix()

    result.update(
        {
            "Estado procesamiento": "Descargada",
            "Motivo": "Documento descargado correctamente",
            "Credencial PDF": ";".join(row_result.raw_credentials),
            "Credencial normalizada": row_result.normalized_name,
            "Fuente credencial": row_result.extraction_source,
            "Credencial Excel control": ";".join(row_result.excel_credentials),
            "Comparación credencial Excel": comparison,
            "Ruta relativa destino": relative_path,
            "Nombre archivo generado": filename,
        }
    )
    return result


def get_excel_credentials(row: pd.Series, columns: dict[str, str]) -> list[str]:
    main = normalize_excel_credentials(row.get(columns[config.COLUMN_CREDENTIALS_MAIN]))
    if main:
        return main
    return normalize_excel_credentials(row.get(columns[config.COLUMN_CREDENTIALS_FALLBACK]))


def reconcile_credentials(pdf_credentials: list[str], excel_credentials: list[str]) -> list[str]:
    if not pdf_credentials:
        return pdf_credentials

    cleaned = remove_redundant_short_credentials(pdf_credentials)
    return cleaned


def remove_redundant_short_credentials(credentials: list[str]) -> list[str]:
    if len(credentials) <= 1:
        return credentials

    longest = max((len(credential) for credential in credentials), default=0)
    if longest <= 1:
        return credentials

    filtered = [credential for credential in credentials if len(credential) > 1]
    return filtered or credentials


def classification_to_report(classification: Classification) -> dict[str, str]:
    return {
        "Código programa": classification.program_code,
        "Categoría destino": classification.category,
        "Subcategoría destino": classification.subcategory,
    }


def build_unique_filename(
    normalized_credential: str,
    folder_key: str,
    filename_counts: dict[tuple[str, str], int],
) -> str:
    safe_base = sanitize_filename_part(normalized_credential)
    key = (folder_key, safe_base)
    count = filename_counts.get(key, 0)
    filename_counts[key] = count + 1
    return f"{safe_base}{'.' * count}.pdf"


def value_as_text(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() == "nan" else text
