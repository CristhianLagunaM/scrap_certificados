const pdfaForm = document.getElementById("form-pdfa");
const pdfaSubmit = document.getElementById("pdfa-submit");
const pdfaTitle = document.getElementById("pdfa-status-title");
const pdfaText = document.getElementById("pdfa-status-text");
const pdfaCounter = document.getElementById("pdfa-counter");
const pdfaProgress = document.getElementById("pdfa-progress");
const pdfaLogs = document.getElementById("pdfa-logs");
const pdfaSummary = document.getElementById("pdfa-summary");
const pdfaDownload = document.getElementById("pdfa-download");
const pdfaDownloadHint = document.getElementById("pdfa-download-hint");

let pdfaPollTimer = null;

pdfaForm.addEventListener("submit", async (event) => {
  event.preventDefault();

  pdfaSubmit.disabled = true;
  pdfaDownload.classList.add("hidden");
  pdfaSummary.classList.add("hidden");
  pdfaLogs.style.display = "block";
  pdfaLogs.textContent = "Subiendo ZIP...\n";
  pdfaTitle.textContent = "Iniciando";
  pdfaText.textContent = "Validando archivo y creando trabajo.";
  pdfaCounter.textContent = "0/0";
  pdfaProgress.value = 0;
  pdfaDownloadHint.textContent = "Preparando conversión. La descarga se habilitará al finalizar.";

  try {
    const response = await fetch("/pdfa/jobs", {
      method: "POST",
      body: new FormData(pdfaForm),
    });

    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      const detail = payload.error || (response.status === 413
        ? "El ZIP supera el tamaño permitido por el servidor. Revisa el límite indicado en el formulario; el servidor de acceso puede tener un límite menor."
        : "El servidor rechazó el inicio de la conversión.");
      const message = `${detail} (HTTP ${response.status})`;
      pdfaSubmit.disabled = false;
      pdfaTitle.textContent = "Error";
      pdfaText.textContent = message;
      pdfaLogs.textContent += `${message}\n`;
      return;
    }

    pollPdfaJob(payload.job_id);
  } catch (error) {
    pdfaSubmit.disabled = false;
    pdfaTitle.textContent = "Error";
    pdfaText.textContent = "No se pudo conectar con el servidor para iniciar la conversión. Revisa la conexión e intenta de nuevo.";
    pdfaLogs.textContent += `${error?.message || "Fallo de red al iniciar el proceso."}\n`;
  }
});

function pollPdfaJob(jobId) {
  if (pdfaPollTimer) {
    clearInterval(pdfaPollTimer);
  }

  const refresh = async () => {
    try {
      const response = await fetch(`/pdfa/jobs/${jobId}`);
      const state = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(state.error || "No fue posible consultar el estado del trabajo.");
      }

      renderPdfaState(state);

      if (state.status === "done" || state.status === "error") {
        clearInterval(pdfaPollTimer);
        pdfaPollTimer = null;
        pdfaSubmit.disabled = false;
      }
    } catch (error) {
      clearInterval(pdfaPollTimer);
      pdfaPollTimer = null;
      pdfaSubmit.disabled = false;
      renderPdfaState({
        status: "error",
        error: error?.message || "No fue posible consultar el estado del proceso.",
        message: "Proceso detenido por error",
        logs: [`${error?.message || "No fue posible consultar el estado del proceso."}`],
      });
    }
  };

  refresh();
  pdfaPollTimer = setInterval(refresh, 1000);
}

function renderPdfaState(state) {
  pdfaTitle.textContent = state.status === "error" ? "Error" : (state.message || state.status || "Procesando");
  pdfaText.textContent = state.message || "Procesando ZIP.";
  pdfaCounter.textContent = `${state.current || 0}/${state.total || 0}`;

  const total = state.total || 0;
  pdfaProgress.value = total ? Math.round(((state.current || 0) / total) * 100) : 0;

  if (Array.isArray(state.logs)) {
    pdfaLogs.textContent = state.logs.slice(-300).join("\n");
    pdfaLogs.scrollTop = pdfaLogs.scrollHeight;
  }

  if (state.status === "error") {
    pdfaSummary.classList.remove("hidden");
    pdfaSummary.innerHTML = `<strong>Error:</strong> ${escapeHtml(state.error || "Proceso detenido")}`;
    pdfaDownload.classList.add("hidden");
    pdfaDownloadHint.textContent = "No se generó ZIP descargable para esta ejecución.";
    return;
  }

  if (state.status === "done" && state.summary) {
    pdfaSummary.classList.remove("hidden");
    const failures = Array.isArray(state.summary.failures) && state.summary.failures.length
      ? `<div><strong>Fallos:</strong> ${escapeHtml(state.summary.failures.slice(0, 5).join(" | "))}</div>`
      : "";

    pdfaSummary.innerHTML = `
      <div><strong>PDFs encontrados:</strong> ${state.summary.total_pdfs}</div>
      <div><strong>Convertidos:</strong> ${state.summary.converted}</div>
      <div><strong>Válidos PDF/A:</strong> ${state.summary.valid_pdfa ?? 0}</div>
      <div><strong>No conformes PDF/A:</strong> ${state.summary.invalid_pdfa ?? 0}</div>
      <div><strong>Sin validar:</strong> ${state.summary.unvalidated ?? 0}</div>
      <div><strong>Fallidos:</strong> ${state.summary.failed}</div>
      <div><strong>Ignorados:</strong> ${state.summary.ignored}</div>
      <div><strong>Validación automática:</strong> ${state.summary.validation_available ? "veraPDF 2b" : "No disponible"}</div>
      ${failures}
    `;

    if (state.download_url) {
      pdfaDownload.href = state.download_url;
      pdfaDownload.classList.remove("hidden");
      pdfaDownloadHint.textContent = "Proceso finalizado. Ya puedes descargar el ZIP PDF/A.";
    }
  }
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}
