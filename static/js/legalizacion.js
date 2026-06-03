const legalizacionForm = document.getElementById("form-legalizacion");
const legalizacionSubmit = document.getElementById("legalizacion-submit");
const legalizacionTitle = document.getElementById("legalizacion-status-title");
const legalizacionText = document.getElementById("legalizacion-status-text");
const legalizacionCounter = document.getElementById("legalizacion-counter");
const legalizacionProgress = document.getElementById("legalizacion-progress");
const legalizacionLogs = document.getElementById("legalizacion-logs");
const legalizacionSummary = document.getElementById("legalizacion-summary");
const legalizacionDownload = document.getElementById("legalizacion-download");
const legalizacionDownloadHint = document.getElementById("legalizacion-download-hint");
const legalizacionCancel = document.getElementById("legalizacion-cancel");

let legalizacionPollTimer = null;
let legalizacionCurrentJobId = null;

legalizacionForm.addEventListener("submit", async (event) => {
  event.preventDefault();

  legalizacionSubmit.disabled = true;
  legalizacionCancel.disabled = false;
  legalizacionCancel.classList.add("hidden");
  legalizacionSummary.classList.add("hidden");
  legalizacionDownload.classList.add("hidden");
  legalizacionDownloadHint.textContent = "Preparando procesamiento. La descarga se habilitará al finalizar.";
  legalizacionLogs.style.display = "block";
  legalizacionLogs.textContent = "Subiendo archivo...\n";
  legalizacionTitle.textContent = "Iniciando";
  legalizacionText.textContent = "Validando archivo y creando trabajo.";
  legalizacionCounter.textContent = "0/0";
  legalizacionProgress.value = 0;

  const response = await fetch("/legalizacion/jobs", {
    method: "POST",
    body: new FormData(legalizacionForm),
  });

  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    legalizacionSubmit.disabled = false;
    legalizacionTitle.textContent = "Error";
    legalizacionText.textContent = payload.error || "No fue posible iniciar el proceso.";
    legalizacionLogs.textContent += `${payload.error || "No fue posible iniciar el proceso."}\n`;
    return;
  }

  legalizacionCurrentJobId = payload.job_id;
  legalizacionCancel.classList.remove("hidden");
  pollLegalizacionJob(payload.job_id);
});

legalizacionCancel.addEventListener("click", async () => {
  if (!legalizacionCurrentJobId || legalizacionCancel.disabled) {
    return;
  }

  legalizacionCancel.disabled = true;
  legalizacionTitle.textContent = "Cancelando";
  legalizacionText.textContent = "Solicitando detener el proceso.";
  legalizacionLogs.textContent += "Solicitando cancelación...\n";

  const response = await fetch(`/legalizacion/jobs/${legalizacionCurrentJobId}/cancel`, {
    method: "POST",
  });
  const payload = await response.json().catch(() => ({}));

  if (!response.ok) {
    legalizacionCancel.disabled = false;
    legalizacionLogs.textContent += `${payload.error || "No fue posible cancelar el proceso."}\n`;
    return;
  }

  renderLegalizacionState(payload);
});

function pollLegalizacionJob(jobId) {
  if (legalizacionPollTimer) {
    clearInterval(legalizacionPollTimer);
  }

  const refresh = async () => {
    const response = await fetch(`/legalizacion/jobs/${jobId}`);
    const state = await response.json().catch(() => ({}));
    renderLegalizacionState(state);

    if (state.status === "done" || state.status === "error" || state.status === "cancelled") {
      clearInterval(legalizacionPollTimer);
      legalizacionPollTimer = null;
      legalizacionSubmit.disabled = false;
      legalizacionCancel.classList.add("hidden");
      legalizacionCurrentJobId = null;
    }
  };

  refresh();
  legalizacionPollTimer = setInterval(refresh, 1000);
}

function renderLegalizacionState(state) {
  legalizacionTitle.textContent = state.status === "error" ? "Error" : (state.message || state.status || "Procesando");
  legalizacionText.textContent = state.message || "Procesando archivo.";
  legalizacionCounter.textContent = `${state.current || 0}/${state.total || 0}`;

  const total = state.total || 0;
  legalizacionProgress.value = total ? Math.round(((state.current || 0) / total) * 100) : 0;

  if (Array.isArray(state.logs)) {
    legalizacionLogs.textContent = state.logs.slice(-300).join("\n");
    legalizacionLogs.scrollTop = legalizacionLogs.scrollHeight;
  }

  if (state.status === "running") {
    legalizacionCancel.disabled = false;
    legalizacionCancel.classList.remove("hidden");
  }

  if (state.status === "cancelling") {
    legalizacionCancel.disabled = true;
    legalizacionCancel.classList.remove("hidden");
    legalizacionDownloadHint.textContent = "Cancelación solicitada. El proceso se detendrá al cerrar las filas en curso.";
  }

  if (state.status === "error") {
    legalizacionSummary.classList.remove("hidden");
    legalizacionSummary.innerHTML = `<strong>Error:</strong> ${escapeHtml(state.error || "Proceso detenido")}`;
    legalizacionDownload.classList.add("hidden");
    legalizacionDownloadHint.textContent = "No se generó ZIP descargable para esta ejecución.";
    return;
  }

  if (state.status === "cancelled") {
    legalizacionSummary.classList.remove("hidden");
    legalizacionSummary.innerHTML = `<strong>Proceso cancelado:</strong> ${escapeHtml(state.error || "Cancelado por el usuario")}`;
    legalizacionDownload.classList.add("hidden");
    legalizacionCancel.classList.add("hidden");
    legalizacionDownloadHint.textContent = "Proceso detenido. No se generó ZIP final para esta ejecución.";
    return;
  }

  if (state.status === "done" && state.summary) {
    legalizacionSummary.classList.remove("hidden");
    legalizacionSummary.innerHTML = `
      <div><strong>Total de filas procesadas:</strong> ${state.summary.total_rows}</div>
      <div><strong>Documentos descargados:</strong> ${state.summary.downloaded}</div>
      <div><strong>Filas no descargadas:</strong> ${state.summary.not_downloaded}</div>
      <div><strong>Filas omitidas:</strong> ${state.summary.omitted}</div>
      <div><strong>Reporte:</strong> ${escapeHtml(state.summary.report_path)}</div>
    `;
    if (state.download_url) {
      legalizacionDownload.href = state.download_url;
      legalizacionDownload.classList.remove("hidden");
      legalizacionDownloadHint.textContent = "Proceso finalizado. Ya puedes descargar el ZIP consolidado.";
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
