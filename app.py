import os
import asyncio
import threading
import zipfile
from flask import Flask, request, render_template, send_from_directory, Response, jsonify

# --- Certificados ---
from utils.logger_sse import log, log_queue
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

# --------------------------------------------------------------
# App Flask
# --------------------------------------------------------------
app = Flask(__name__)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# --------------------------------------------------------------
# STREAM SSE (CERTIFICADOS)
# --------------------------------------------------------------
@app.route("/logs_stream")
def logs_stream():
    def stream():
        while True:
            msg = log_queue.get()
            yield f"data: {msg}\n\n"
            if msg == "__FIN__":
                break
    return Response(stream(), mimetype="text/event-stream")

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
async def job(path_excel):

    ARCHIVOS_GENERADOS["zip_full"] = None

    try:
        log("📄 Leyendo archivo Excel...")
        df = cargar_excel(path_excel)

        df_min = df[df["Tipo Inscripcion"].str.contains("MINORIAS", na=False)].copy()
        df_ind = df[df["Tipo Inscripcion"].str.contains("INDIGENAS", na=False)].copy()

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

        with zipfile.ZipFile(zip_path, "w") as z:
            for f in os.listdir(OUTPUT_FOLDER):
                full = os.path.join(OUTPUT_FOLDER, f)

                if f.endswith(".xlsx"):
                    z.write(full, f)

                if os.path.isdir(full) and f in ["MINORIAS", "INDIGENAS"]:
                    for pdf in os.listdir(full):
                        z.write(
                            os.path.join(full, pdf),
                            f"{f.lower()}/{pdf}"
                        )

        ARCHIVOS_GENERADOS["zip_full"] = zip_name
        log("📦 ZIP generado correctamente")
        log("🎉 Proceso completado con éxito")

    except Exception as e:
        log(f"❌ Error inesperado: {e}")

    finally:
        log("__FIN__")

# --------------------------------------------------------------
# POST /procesar (CERTIFICADOS)
# --------------------------------------------------------------
@app.route("/procesar", methods=["POST"])
def procesar():

    archivo = request.files.get("archivo")
    if not archivo or archivo.filename == "":
        return jsonify({"error": "Archivo inválido"}), 400

    path_excel = os.path.join(UPLOAD_FOLDER, "entrada.xlsx")
    archivo.save(path_excel)

    thread = threading.Thread(
        target=lambda: asyncio.run(job(path_excel)),
        daemon=True
    )
    thread.start()

    return jsonify({"status": "procesando"})

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
