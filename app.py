import os
import asyncio
import threading
import zipfile
from queue import Empty, Queue
from uuid import uuid4
from flask import Flask, request, render_template, send_from_directory, Response, jsonify, stream_with_context

# --- Certificados ---
from utils.logger_sse import log, set_log_queue
from utils.loader import cargar_excel
from utils.excel import generar_excel_coloreado
from scrapers.scraper_minorias import scrap_minorias
from scrapers.scraper_indigenas import scrap_indigenas

# --- Estudios Previos ---
from utils.estudios_previos import EstudiosPreviosGenerator

# --------------------------------------------------------------
# Carpetas internas
# --------------------------------------------------------------
APP_ROOT = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(APP_ROOT, "uploads")
OUTPUT_FOLDER = os.path.join(APP_ROOT, "salidas")

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

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

# --------------------------------------------------------------
# App Flask
# --------------------------------------------------------------
app = Flask(__name__)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024


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

        # ---------------- MINORÍAS ----------------
        if not df_min.empty:
            log(f"▶ Procesando {len(df_min)} registros MINORÍAS...")
            df_min_r = await scrap_minorias(df_min, OUTPUT_FOLDER)
            generar_excel_coloreado(
                df_min_r,
                os.path.join(OUTPUT_FOLDER, "resultado_minorias.xlsx")
            )
            log("✔ MINORÍAS completado")
        else:
            log("ℹ No hay registros MINORÍAS")

        # ---------------- INDÍGENAS ----------------
        if not df_ind.empty:
            log(f"▶ Procesando {len(df_ind)} registros INDÍGENAS...")
            df_ind_r = await scrap_indigenas(df_ind, OUTPUT_FOLDER)
            generar_excel_coloreado(
                df_ind_r,
                os.path.join(OUTPUT_FOLDER, "resultado_indigenas.xlsx")
            )
            log("✔ INDÍGENAS completado")
        else:
            log("ℹ No hay registros INDÍGENAS")

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

# --------------------------------------------------------------
# MAIN
# --------------------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
