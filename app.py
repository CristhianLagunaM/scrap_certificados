import os
import asyncio
import threading
import zipfile
import shutil
import subprocess
import tempfile
import re
import fitz
from dataclasses import asdict, dataclass
from pathlib import Path
from queue import Empty, Queue
from uuid import uuid4
from flask import Flask, request, render_template, send_file, send_from_directory, Response, jsonify, stream_with_context
from werkzeug.utils import secure_filename

# --- Certificados ---
from utils.logger_sse import log, set_log_queue
from utils.loader import cargar_excel
from utils.excel import generar_excel_coloreado
from scrapers.scraper_minorias import scrap_minorias
from scrapers.scraper_indigenas import scrap_indigenas
from legalizacion.cancellation import ProcessingCancelled
from legalizacion.processor import ProcessingSummary as LegalizacionSummary
from legalizacion.processor import process_excel as process_legalizacion_excel
from legalizacion.soportes_processor import ProcessingSummary as LegalizacionSoportesSummary
from legalizacion.soportes_processor import process_excel as process_legalizacion_soportes_excel

# --- Estudios Previos ---
from utils.estudios_previos import EstudiosPreviosGenerator

# --------------------------------------------------------------
# Carpetas internas
# --------------------------------------------------------------
APP_ROOT = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(APP_ROOT, "uploads")
OUTPUT_FOLDER = os.path.join(APP_ROOT, "salidas")
LEGALIZACION_UPLOAD_FOLDER = os.path.join(UPLOAD_FOLDER, "legalizacion")
LEGALIZACION_DEFAULT_OUTPUT = os.path.join(OUTPUT_FOLDER, "legalizacion")
PDFA_UPLOAD_FOLDER = os.path.join(UPLOAD_FOLDER, "pdfa")
PDFA_OUTPUT_FOLDER = os.path.join(OUTPUT_FOLDER, "pdfa")

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)
os.makedirs(LEGALIZACION_UPLOAD_FOLDER, exist_ok=True)
os.makedirs(LEGALIZACION_DEFAULT_OUTPUT, exist_ok=True)
os.makedirs(PDFA_UPLOAD_FOLDER, exist_ok=True)
os.makedirs(PDFA_OUTPUT_FOLDER, exist_ok=True)

# --------------------------------------------------------------
# Estado SOLO para certificados
# --------------------------------------------------------------
ARCHIVOS_GENERADOS = {
    "zip_full": None
}
ESTADO_PROCESO = {
    "activo": False,
    "run_id": None,
    "log_queue": None,
}
LEGALIZACION_JOBS = {}
PDFA_JOBS = {}

# --------------------------------------------------------------
# App Flask
# --------------------------------------------------------------
app = Flask(__name__)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024


@dataclass
class LegalizacionJobState:
    id: str
    status: str = "pending"
    current: int = 0
    total: int = 0
    message: str = "Esperando inicio"
    logs: list[str] | None = None
    error: str = ""
    summary: dict[str, object] | None = None
    zip_path: str = ""
    report_path: str = ""
    cancel_requested: bool = False

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["download_url"] = f"/legalizacion/jobs/{self.id}/download" if self.zip_path else ""
        data["cancel_url"] = f"/legalizacion/jobs/{self.id}/cancel"
        return data


@dataclass
class PdfaJobState:
    id: str
    status: str = "pending"
    current: int = 0
    total: int = 0
    message: str = "Esperando inicio"
    logs: list[str] | None = None
    error: str = ""
    summary: dict[str, object] | None = None
    zip_path: str = ""

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["download_url"] = f"/pdfa/jobs/{self.id}/download" if self.zip_path else ""
        return data


def limpiar_logs_pendientes():
    queue = ESTADO_PROCESO.get("log_queue")
    if queue is None:
        return

    while True:
        try:
            queue.get_nowait()
        except Empty:
            break


def preparar_salida():
    for nombre in os.listdir(OUTPUT_FOLDER):
        ruta = os.path.join(OUTPUT_FOLDER, nombre)

        if os.path.isfile(ruta):
            os.remove(ruta)
            continue

        if os.path.isdir(ruta) and nombre in {"MINORIAS", "INDIGENAS"}:
            import shutil

            shutil.rmtree(ruta)


def crear_zip_resultados(zip_path):
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for nombre in sorted(os.listdir(OUTPUT_FOLDER)):
            ruta = os.path.join(OUTPUT_FOLDER, nombre)

            if os.path.isfile(ruta) and nombre.endswith(".xlsx"):
                z.write(ruta, nombre)
                continue

            if os.path.isdir(ruta) and nombre in {"MINORIAS", "INDIGENAS"}:
                for pdf in sorted(os.listdir(ruta)):
                    pdf_path = os.path.join(ruta, pdf)
                    if os.path.isfile(pdf_path) and pdf.lower().endswith(".pdf"):
                        z.write(pdf_path, f"{nombre.lower()}/{pdf}")

# --------------------------------------------------------------
# STREAM SSE (CERTIFICADOS)
# --------------------------------------------------------------
@app.route("/logs_stream")
def logs_stream():
    run_id = request.args.get("run_id")
    queue = ESTADO_PROCESO.get("log_queue")

    if not run_id or run_id != ESTADO_PROCESO.get("run_id") or queue is None:
        return jsonify({"error": "Stream no disponible para esa ejecución"}), 404

    @stream_with_context
    def stream():
        # Padding inicial para evitar buffering en proxies/navegador.
        yield ":" + (" " * 2048) + "\n\n"
        yield "retry: 1000\n\n"
        while True:
            msg = queue.get()
            yield f"data: {msg}\n\n"
            if msg == "__FIN__":
                break
    response = Response(stream(), mimetype="text/event-stream")
    response.headers["Cache-Control"] = "no-cache, no-transform"
    response.headers["X-Accel-Buffering"] = "no"
    response.headers["Connection"] = "keep-alive"
    return response

# --------------------------------------------------------------
# Descarga genérica
# --------------------------------------------------------------
@app.route("/salidas/<path:filename>")
def descargar_archivo(filename):
    return send_from_directory(OUTPUT_FOLDER, filename, as_attachment=True)

# --------------------------------------------------------------
# Descarga ZIP CERTIFICADOS
# --------------------------------------------------------------
@app.route("/descargar_zip")
def descargar_zip():
    zip_name = ARCHIVOS_GENERADOS.get("zip_full")
    if not zip_name:
        return jsonify({"error": "ZIP aún no disponible"}), 404

    return send_from_directory(
        OUTPUT_FOLDER,
        zip_name,
        as_attachment=True
    )

# --------------------------------------------------------------
# VISTAS
# --------------------------------------------------------------
@app.route("/")
def index():
    return render_template("index.html")  # Certificados

@app.route("/estudios-previos", methods=["GET"])
def estudios_previos_view():
    return render_template("estudios_previos.html")


@app.route("/legalizacion", methods=["GET"])
def legalizacion_view():
    return render_template("legalizacion.html")


@app.route("/pdfa", methods=["GET"])
def pdfa_view():
    return render_template("pdfa.html")

# --------------------------------------------------------------
# SCRAPING CERTIFICADOS (NO TOCAR)
# --------------------------------------------------------------
async def job(path_excel, run_id):

    ARCHIVOS_GENERADOS["zip_full"] = None

    try:
        preparar_salida()
        log("📄 Leyendo archivo Excel...")
        df = cargar_excel(path_excel)

        df_min = df[df["Tipo Inscripcion"].str.contains("MINORIAS", na=False)].copy()
        df_ind = df[df["Tipo Inscripcion"].str.contains("INDIGENAS", na=False)].copy()

        total_encontrados = len(df_min) + len(df_ind)
        log(f"📊 Registros válidos encontrados para scraping: {total_encontrados}")

        if total_encontrados == 0:
            log("ℹ El Excel no contiene registros de MINORÍAS ni INDÍGENAS.")
            df_resultado = df.copy()
            df_resultado["EstadoDescarga"] = "NO_APLICA"
            df_resultado["DetalleDescarga"] = (
                "Tipo de inscripción no soportado por este módulo. "
                "Actualmente solo se procesan MINORIAS e INDIGENAS."
            )
            generar_excel_coloreado(
                df_resultado,
                os.path.join(OUTPUT_FOLDER, "resultado_sin_coincidencias.xlsx")
            )

        scraping_tasks = {}

        # ---------------- MINORÍAS ----------------
        if not df_min.empty:
            log(f"▶ Procesando {len(df_min)} registros MINORÍAS...")
            scraping_tasks["minorias"] = asyncio.create_task(
                scrap_minorias(df_min, OUTPUT_FOLDER)
            )
        else:
            log("ℹ No hay registros MINORÍAS")

        # ---------------- INDÍGENAS ----------------
        if not df_ind.empty:
            log(f"▶ Procesando {len(df_ind)} registros INDÍGENAS...")
            scraping_tasks["indigenas"] = asyncio.create_task(
                scrap_indigenas(df_ind, OUTPUT_FOLDER)
            )
        else:
            log("ℹ No hay registros INDÍGENAS")

        if scraping_tasks:
            scraping_results = await asyncio.gather(
                *scraping_tasks.values(),
                return_exceptions=True,
            )

            for key, result in zip(scraping_tasks.keys(), scraping_results):
                if isinstance(result, Exception):
                    raise result

                if key == "minorias":
                    generar_excel_coloreado(
                        result,
                        os.path.join(OUTPUT_FOLDER, "resultado_minorias.xlsx")
                    )
                    log("✔ MINORÍAS completado")
                    continue

                generar_excel_coloreado(
                    result,
                    os.path.join(OUTPUT_FOLDER, "resultado_indigenas.xlsx")
                )
                log("✔ INDÍGENAS completado")

        # ---------------- ZIP FINAL ----------------
        log("📦 Empaquetando ZIP final...")

        zip_name = "certificados.zip"
        zip_path = os.path.join(OUTPUT_FOLDER, zip_name)

        crear_zip_resultados(zip_path)

        ARCHIVOS_GENERADOS["zip_full"] = zip_name
        log("📦 ZIP generado correctamente")
        log("🎉 Proceso completado con éxito")

    except Exception as e:
        log(f"❌ Error inesperado: {e}")

    finally:
        if ESTADO_PROCESO.get("run_id") == run_id:
            ESTADO_PROCESO["activo"] = False
            log("__FIN__")

# --------------------------------------------------------------
# POST /procesar (CERTIFICADOS)
# --------------------------------------------------------------
@app.route("/procesar", methods=["POST"])
def procesar():

    if ESTADO_PROCESO["activo"]:
        return jsonify({"error": "Ya hay un procesamiento en curso"}), 409

    archivo = request.files.get("archivo")
    if not archivo or archivo.filename == "":
        return jsonify({"error": "Archivo inválido"}), 400

    run_id = uuid4().hex
    queue = Queue()
    ESTADO_PROCESO["run_id"] = run_id
    ESTADO_PROCESO["log_queue"] = queue
    set_log_queue(queue)
    limpiar_logs_pendientes()
    ESTADO_PROCESO["activo"] = True

    path_excel = os.path.join(UPLOAD_FOLDER, "entrada.xlsx")
    archivo.save(path_excel)

    thread = threading.Thread(
        target=lambda: asyncio.run(job(path_excel, run_id)),
        daemon=True
    )
    thread.start()

    return jsonify({"status": "procesando", "run_id": run_id})


@app.route("/legalizacion/jobs", methods=["POST"])
def legalizacion_create_job():
    uploaded_file = request.files.get("excel")
    if not uploaded_file or uploaded_file.filename == "":
        return jsonify({"error": "Selecciona un archivo Excel."}), 400

    suffix = Path(uploaded_file.filename).suffix.lower()
    if suffix not in {".xlsx", ".xls"}:
        return jsonify({"error": "El archivo debe ser .xlsx o .xls."}), 400

    mode = request.form.get("mode", "inscripcion").strip().lower()
    if mode not in {"inscripcion", "soportes"}:
        return jsonify({"error": "Modo de procesamiento no válido."}), 400

    job_id = uuid4().hex
    filename = secure_filename(uploaded_file.filename) or f"entrada{suffix}"
    excel_path = os.path.join(LEGALIZACION_UPLOAD_FOLDER, f"{job_id}_{filename}")
    uploaded_file.save(excel_path)

    output_dir_text = request.form.get("output_dir", "").strip()
    output_dir = Path(output_dir_text).expanduser() if output_dir_text else Path(LEGALIZACION_DEFAULT_OUTPUT)
    if not output_dir.is_absolute():
        output_dir = (Path(APP_ROOT) / output_dir).resolve()

    state = LegalizacionJobState(
        id=job_id,
        status="running",
        message="Archivo recibido. Iniciando procesamiento...",
        logs=["Archivo recibido. Iniciando procesamiento..."],
    )
    LEGALIZACION_JOBS[job_id] = state

    thread = threading.Thread(target=run_legalizacion_job, args=(job_id, excel_path, output_dir, mode), daemon=True)
    thread.start()
    return jsonify({"job_id": job_id})


@app.route("/legalizacion/jobs/<job_id>", methods=["GET"])
def legalizacion_job_status(job_id):
    state = LEGALIZACION_JOBS.get(job_id)
    if not state:
        return jsonify({"error": "Trabajo no encontrado."}), 404
    return jsonify(state.to_dict())


@app.route("/legalizacion/jobs/<job_id>/cancel", methods=["POST"])
def legalizacion_cancel_job(job_id):
    state = LEGALIZACION_JOBS.get(job_id)
    if not state:
        return jsonify({"error": "Trabajo no encontrado."}), 404

    if state.status not in {"running", "cancelling"}:
        return jsonify(state.to_dict())

    state.cancel_requested = True
    state.status = "cancelling"
    state.message = "Cancelación solicitada. Deteniendo filas pendientes..."
    if state.logs is not None:
        state.logs.append("Cancelación solicitada por el usuario.")
    return jsonify(state.to_dict())


@app.route("/legalizacion/jobs/<job_id>/download", methods=["GET"])
def legalizacion_download_zip(job_id):
    state = LEGALIZACION_JOBS.get(job_id)
    if not state or not state.zip_path:
        return jsonify({"error": "ZIP no disponible."}), 404

    zip_path = Path(state.zip_path)
    if not zip_path.exists():
        return jsonify({"error": "El archivo ZIP ya no existe en disco."}), 404

    return send_file(zip_path, as_attachment=True, download_name=zip_path.name)

# --------------------------------------------------------------
# POST /estudios-previos (AISLADO)
# --------------------------------------------------------------
@app.route("/estudios-previos", methods=["POST"])
def estudios_previos_post():

    excel = request.files.get("excel")
    word = request.files.get("template")

    if not excel or not word:
        return jsonify({"error": "Debes subir Excel y Word"}), 400

    excel_path = os.path.join(UPLOAD_FOLDER, excel.filename)
    word_path = os.path.join(UPLOAD_FOLDER, word.filename)

    excel.save(excel_path)
    word.save(word_path)

    generator = EstudiosPreviosGenerator()
    zip_name = generator.generate(excel_path, word_path, OUTPUT_FOLDER)

    return jsonify({
        "status": "ok",
        "url": f"/salidas/{zip_name}"
    })


def run_legalizacion_job(job_id: str, excel_path: str, output_dir: Path, mode: str) -> None:
    state = LEGALIZACION_JOBS[job_id]

    def progress(current: int, total: int, message: str) -> None:
        state.current = current
        state.total = total
        state.message = message
        if state.logs is not None:
            state.logs.append(f"[{current}/{total}] {message}")

    def should_cancel() -> bool:
        return state.cancel_requested

    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        if mode == "soportes":
            summary = process_legalizacion_soportes_excel(excel_path, str(output_dir), progress, should_cancel)
        else:
            summary = process_legalizacion_excel(excel_path, str(output_dir), progress, should_cancel)
        state.status = "done"
        state.current = summary.total_rows
        state.total = summary.total_rows
        state.message = "Proceso finalizado"
        state.zip_path = str(summary.zip_path)
        state.report_path = str(summary.report_path)
        state.summary = legalizacion_summary_to_dict(summary)
        if state.logs is not None:
            state.logs.append(f"ZIP generado en: {summary.zip_path}")
            state.logs.append(f"Reporte generado en: {summary.report_path}")
    except ProcessingCancelled as exc:
        state.status = "cancelled"
        state.error = str(exc)
        state.message = "Proceso cancelado"
        if state.logs is not None:
            state.logs.append(str(exc))
    except Exception as exc:
        state.status = "error"
        state.error = str(exc)
        state.message = "Proceso detenido por error"
        if state.logs is not None:
            state.logs.append(str(exc))


def legalizacion_summary_to_dict(summary: LegalizacionSummary | LegalizacionSoportesSummary) -> dict[str, object]:
    return {
        "total_rows": summary.total_rows,
        "downloaded": summary.downloaded,
        "not_downloaded": summary.not_downloaded,
        "omitted": summary.omitted,
        "zip_path": str(summary.zip_path),
        "report_path": str(summary.report_path),
        "work_dir": str(summary.work_dir),
    }


def is_within_directory(base_dir: Path, candidate: Path) -> bool:
    try:
        candidate.resolve().relative_to(base_dir.resolve())
        return True
    except ValueError:
        return False


def extract_zip_safely(zip_path: Path, destination: Path) -> tuple[list[Path], int]:
    extracted_pdfs: list[Path] = []
    ignored_files = 0

    with zipfile.ZipFile(zip_path) as archive:
        for member in archive.infolist():
            member_name = member.filename.strip()
            if not member_name or member.is_dir():
                continue

            relative_path = Path(member_name)
            if relative_path.is_absolute():
                ignored_files += 1
                continue

            if relative_path.suffix.lower() != ".pdf":
                ignored_files += 1
                continue

            target_path = destination / relative_path
            if not is_within_directory(destination, target_path):
                ignored_files += 1
                continue

            target_path.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as source, open(target_path, "wb") as target:
                shutil.copyfileobj(source, target)
            extracted_pdfs.append(target_path)

    return extracted_pdfs, ignored_files


def build_pdfa_definition_file(temp_dir: Path, title: str) -> Path:
    template_path = resolve_pdfa_definition_template()
    icc_profile = "/usr/share/color/icc/ghostscript/srgb.icc"
    if not Path(icc_profile).exists():
        icc_profile = "/usr/share/color/icc/colord/sRGB.icc"

    raw_content = template_path.read_text(encoding="utf-8")
    safe_title = title.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    content = raw_content.replace("[ /Title (Title)", f"[ /Title ({safe_title})", 1)
    content = re.sub(r"/ICCProfile\s+\(.*?\)\s+% Customise", f"/ICCProfile ({icc_profile}) % Customise", content, count=1)
    content = re.sub(
        r"%% ----------8<--------------8<-------------8<--------------8<----------.*?%% ----------8<--------------8<-------------8<--------------8<----------",
        "  /N 3\n",
        content,
        count=1,
        flags=re.S,
    )
    definition_path = temp_dir / "pdfa_def.ps"
    definition_path.write_text(content, encoding="utf-8")
    return definition_path


def resolve_pdfa_definition_template() -> Path:
    candidates = [
        "/usr/share/ghostscript/10.02.1/lib/PDFA_def.ps",
        "/usr/share/ghostscript/9.53.3/lib/PDFA_def.ps",
        "/usr/share/ghostscript/9.53.3/Resource/Init/PDFA_def.ps",
    ]

    for candidate in candidates:
        path = Path(candidate)
        if path.exists():
            return path

    dynamic_root = Path("/usr/share/ghostscript")
    if dynamic_root.exists():
        matches = sorted(dynamic_root.glob("*/lib/PDFA_def.ps"))
        if matches:
            return matches[0]

    raise RuntimeError("No se encontro la plantilla oficial PDFA_def.ps en el sistema.")


def resolve_ghostscript_binary() -> str:
    configured = os.environ.get("GHOSTSCRIPT_BIN", "").strip()
    candidates = [configured, shutil.which("gs"), "/usr/bin/gs", "/usr/local/bin/gs"]

    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate

    raise RuntimeError(
        "Ghostscript no esta instalado o no esta disponible en PATH. "
        "Reconstruye el contenedor con la dependencia `ghostscript`."
    )


def resolve_qpdf_binary() -> str:
    configured = os.environ.get("QPDF_BIN", "").strip()
    candidates = [configured, shutil.which("qpdf"), "/usr/bin/qpdf", "/usr/local/bin/qpdf"]

    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate

    raise RuntimeError(
        "qpdf no esta instalado o no esta disponible en PATH. "
        "Reconstruye el contenedor con la dependencia `qpdf`."
    )


def repair_pdf_with_qpdf(source_pdf: Path, repaired_pdf: Path) -> None:
    qpdf_binary = resolve_qpdf_binary()
    command = [
        qpdf_binary,
        "--object-streams=disable",
        str(source_pdf),
        str(repaired_pdf),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        details = "\n".join(part for part in [completed.stdout.strip(), completed.stderr.strip()] if part).strip()
        raise RuntimeError(details or "qpdf no pudo reparar el PDF.")


def sanitize_pdfa_annotations(source_pdf: Path, sanitized_pdf: Path) -> int:
    removed = 0
    document = fitz.open(source_pdf)
    try:
        for page in document:
            annot = page.first_annot
            while annot is not None:
                next_annot = annot.next
                annot_xref = annot.xref
                annot_type = (annot.type[1] or "").strip()
                has_ap, ap_value = document.xref_get_key(annot_xref, "AP")

                rect = annot.rect
                zero_rect = rect.x0 == rect.x1 and rect.y0 == rect.y1
                can_skip_ap = annot_type in {"Popup", "Link"} or zero_rect
                missing_ap = has_ap == "null" or ap_value in {"null", ""}

                if missing_ap and not can_skip_ap:
                    page.delete_annot(annot)
                    removed += 1

                annot = next_annot

        document.save(
            sanitized_pdf,
            garbage=4,
            deflate=True,
            clean=True,
            incremental=False,
        )
    finally:
        document.close()

    return removed


def convert_pdf_to_pdfa(source_pdf: Path, target_pdf: Path) -> None:
    target_pdf.parent.mkdir(parents=True, exist_ok=True)
    gs_binary = resolve_ghostscript_binary()

    with tempfile.TemporaryDirectory(prefix="pdfa_def_", dir=str(PDFA_OUTPUT_FOLDER)) as temp_dir_str:
        temp_dir = Path(temp_dir_str)
        definition_path = build_pdfa_definition_file(temp_dir, source_pdf.stem)
        repaired_pdf = temp_dir / "repaired.pdf"
        sanitized_pdf = temp_dir / "sanitized.pdf"
        repair_pdf_with_qpdf(source_pdf, repaired_pdf)
        sanitize_pdfa_annotations(repaired_pdf, sanitized_pdf)

        command = [
            gs_binary,
            "-dPDFA=2",
            "-dBATCH",
            "-dNOPAUSE",
            "-dNOOUTERSAVE",
            "-sProcessColorModel=DeviceRGB",
            "-sColorConversionStrategy=RGB",
            "-sDEVICE=pdfwrite",
            "-dPDFACompatibilityPolicy=1",
            f"-sOutputFile={target_pdf}",
            f"--permit-file-read={definition_path}",
            f"--permit-file-read={sanitized_pdf}",
            "--permit-file-read=/usr/share/color/icc/ghostscript/srgb.icc",
            "--permit-file-read=/usr/share/color/icc/colord/sRGB.icc",
            str(definition_path),
            str(sanitized_pdf),
        ]
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        if completed.returncode != 0:
            details = "\n".join(part for part in [completed.stdout.strip(), completed.stderr.strip()] if part).strip()
            raise RuntimeError(details)


def create_pdfa_zip(zip_path: Path, converted_dir: Path) -> None:
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for file_path in sorted(converted_dir.rglob("*")):
            if not file_path.is_file():
                continue
            archive.write(file_path, file_path.relative_to(converted_dir))


@app.route("/pdfa/jobs", methods=["POST"])
def pdfa_create_job():
    uploaded_file = request.files.get("zip_file")
    if not uploaded_file or uploaded_file.filename == "":
        return jsonify({"error": "Selecciona un archivo ZIP."}), 400

    suffix = Path(uploaded_file.filename).suffix.lower()
    if suffix != ".zip":
        return jsonify({"error": "El archivo debe ser .zip."}), 400

    job_id = uuid4().hex
    filename = secure_filename(uploaded_file.filename) or "entrada.zip"
    zip_path = os.path.join(PDFA_UPLOAD_FOLDER, f"{job_id}_{filename}")
    uploaded_file.save(zip_path)

    state = PdfaJobState(
        id=job_id,
        status="running",
        message="ZIP recibido. Preparando extracción...",
        logs=["ZIP recibido. Preparando extracción..."],
    )
    PDFA_JOBS[job_id] = state

    thread = threading.Thread(target=run_pdfa_job, args=(job_id, Path(zip_path), Path(filename).stem), daemon=True)
    thread.start()
    return jsonify({"job_id": job_id})


@app.route("/pdfa/jobs/<job_id>", methods=["GET"])
def pdfa_job_status(job_id):
    state = PDFA_JOBS.get(job_id)
    if not state:
        return jsonify({"error": "Trabajo no encontrado."}), 404
    return jsonify(state.to_dict())


@app.route("/pdfa/jobs/<job_id>/download", methods=["GET"])
def pdfa_download_zip(job_id):
    state = PDFA_JOBS.get(job_id)
    if not state or not state.zip_path:
        return jsonify({"error": "ZIP no disponible."}), 404

    zip_path = Path(state.zip_path)
    if not zip_path.exists():
        return jsonify({"error": "El ZIP ya no existe en disco."}), 404

    return send_file(zip_path, as_attachment=True, download_name=zip_path.name)


def run_pdfa_job(job_id: str, zip_path: Path, original_stem: str) -> None:
    state = PDFA_JOBS[job_id]
    work_dir = Path(PDFA_OUTPUT_FOLDER) / job_id
    extracted_dir = work_dir / "input"
    converted_dir = work_dir / "pdfa"
    output_zip = work_dir / f"{original_stem}_pdfa.zip"

    try:
        if work_dir.exists():
            shutil.rmtree(work_dir)
        extracted_dir.mkdir(parents=True, exist_ok=True)
        converted_dir.mkdir(parents=True, exist_ok=True)

        state.message = "Extrayendo ZIP..."
        if state.logs is not None:
            state.logs.append("Extrayendo contenido del ZIP...")

        pdf_files, ignored_files = extract_zip_safely(zip_path, extracted_dir)
        if not pdf_files:
            raise ValueError("El ZIP no contiene archivos PDF válidos.")

        pdf_files = sorted(pdf_files)
        state.total = len(pdf_files)
        if state.logs is not None and ignored_files:
            state.logs.append(f"Archivos ignorados por no ser PDF o por ruta inválida: {ignored_files}")

        converted = 0
        failed = 0
        failures: list[str] = []

        for index, source_pdf in enumerate(pdf_files, start=1):
            relative_path = source_pdf.relative_to(extracted_dir)
            target_pdf = converted_dir / relative_path
            state.current = index
            state.message = f"Convirtiendo {relative_path}"
            if state.logs is not None:
                state.logs.append(f"[{index}/{state.total}] Convirtiendo {relative_path}")

            try:
                convert_pdf_to_pdfa(source_pdf, target_pdf)
                converted += 1
            except Exception as exc:
                failed += 1
                failures.append(f"{relative_path}: {exc}")
                if state.logs is not None:
                    state.logs.append(f"[{index}/{state.total}] Error en {relative_path}: {exc}")

        if converted == 0:
            raise RuntimeError("No fue posible convertir ningún PDF a PDF/A.")

        create_pdfa_zip(output_zip, converted_dir)
        state.status = "done"
        state.current = state.total
        state.message = "Conversión finalizada"
        state.zip_path = str(output_zip)
        state.summary = {
            "total_pdfs": state.total,
            "converted": converted,
            "failed": failed,
            "ignored": ignored_files,
            "work_dir": str(work_dir),
            "failures": failures,
        }
        if state.logs is not None:
            state.logs.append(f"ZIP generado en: {output_zip}")
    except Exception as exc:
        state.status = "error"
        state.error = str(exc)
        state.message = "Proceso detenido por error"
        if state.logs is not None:
            state.logs.append(str(exc))

# --------------------------------------------------------------
# MAIN
# --------------------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
