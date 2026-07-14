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

  const response = await fetch("/pdfa/jobs", {
    method: "POST",
    body: new FormData(pdfaForm),
  });

  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    pdfaSubmit.disabled = false;
    pdfaTitle.textContent = "Error";
    pdfaText.textContent = payload.error || "No fue posible iniciar el proceso.";
    pdfaLogs.textContent += `${payload.error || "No fue posible iniciar el proceso."}\n`;
    return;
  }

  pollPdfaJob(payload.job_id);
});

function pollPdfaJob(jobId) {
  if (pdfaPollTimer) {
    clearInterval(pdfaPollTimer);
  }

  const refresh = async () => {
    const response = await fetch(`/pdfa/jobs/${jobId}`);
    const state = await response.json().catch(() => ({}));
    renderPdfaState(state);

    if (state.status === "done" || state.status === "error") {
      clearInterval(pdfaPollTimer);
      pdfaPollTimer = null;
      pdfaSubmit.disabled = false;
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
      <div><strong>Fallidos:</strong> ${state.summary.failed}</div>
      <div><strong>Ignorados:</strong> ${state.summary.ignored}</div>
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
