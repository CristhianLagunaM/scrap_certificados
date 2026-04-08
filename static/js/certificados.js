let eventSource = null;
let statusInterval = null;

function formatElapsed(seconds) {
  const mins = String(Math.floor(seconds / 60)).padStart(2, "0");
  const secs = String(seconds % 60).padStart(2, "0");
  return `${mins}:${secs}`;
}

function iniciarEstado() {
  const panel = document.getElementById("status-panel");
  const title = document.getElementById("status-title");
  const text = document.getElementById("status-text");
  const timer = document.getElementById("status-timer");
  const etapas = [
    "Preparando solicitud y validando archivo...",
    "El servidor está leyendo el Excel...",
    "El proceso sigue activo. Esperando avances del scraping...",
    "Seguimos trabajando. Esto puede tardar varios minutos.",
    "El navegador automatizado continúa procesando registros.",
  ];

  let elapsed = 0;
  panel.style.display = "flex";
  panel.classList.remove("done", "error");
  title.textContent = "Procesando";
  text.textContent = etapas[0];
  timer.textContent = "00:00";

  if (statusInterval) {
    clearInterval(statusInterval);
  }

  statusInterval = setInterval(() => {
    elapsed += 1;
    timer.textContent = formatElapsed(elapsed);
    text.textContent = etapas[Math.min(Math.floor(elapsed / 4), etapas.length - 1)];
  }, 1000);
}

function actualizarEstadoDesdeLog(message) {
  const title = document.getElementById("status-title");
  const text = document.getElementById("status-text");

  if (message.includes("Leyendo archivo Excel")) {
    text.textContent = "Leyendo y validando el archivo Excel...";
  } else if (message.includes("Procesando") && message.includes("MINOR")) {
    title.textContent = "Procesando MINORÍAS";
    text.textContent = message;
  } else if (message.includes("Procesando") && message.includes("INDÍGEN")) {
    title.textContent = "Procesando INDÍGENAS";
    text.textContent = message;
  } else if (message.includes("Empaquetando ZIP")) {
    title.textContent = "Empaquetando";
    text.textContent = "Armando el archivo ZIP final...";
  } else if (message.includes("ZIP generado correctamente")) {
    title.textContent = "ZIP Listo";
    text.textContent = "La descarga está por comenzar.";
  } else if (message.startsWith("❌")) {
    title.textContent = "Error";
    text.textContent = message;
  } else if (!message.startsWith("[") && !message.startsWith("__")) {
    text.textContent = message;
  }
}

function finalizarEstado(tipo, mensaje) {
  const panel = document.getElementById("status-panel");
  const title = document.getElementById("status-title");
  const text = document.getElementById("status-text");

  if (statusInterval) {
    clearInterval(statusInterval);
    statusInterval = null;
  }

  panel.classList.remove("done", "error");
  if (tipo === "done") {
    panel.classList.add("done");
    title.textContent = "Proceso finalizado";
  } else if (tipo === "error") {
    panel.classList.add("error");
    title.textContent = "Proceso terminado con novedad";
  }

  text.textContent = mensaje;
}

async function descargarZipSiExiste(logs) {
  try {
    const response = await fetch("/descargar_zip");

    if (!response.ok) {
      logs.innerHTML += "\n❌ El proceso terminó sin generar ZIP descargable\n";
      return;
    }

    const blob = await response.blob();
    const url = window.URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    const disposition = response.headers.get("Content-Disposition") || "";
    const match = disposition.match(/filename="?([^"]+)"?/);

    anchor.href = url;
    anchor.download = match ? match[1] : "certificados.zip";
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    window.URL.revokeObjectURL(url);

    logs.innerHTML += "✅ ZIP descargado\n";
  } catch {
    logs.innerHTML += "\n❌ No fue posible descargar el ZIP\n";
  }
}

document.getElementById("form-procesar").addEventListener("submit", function (e) {
  e.preventDefault();

  const logs = document.getElementById("logs-box");
  let zipListo = false;
  let ultimoMensajeError = "";
  logs.style.display = "block";
  logs.innerHTML = "🔄 Iniciando proceso...\n";
  iniciarEstado();

  // Cerrar stream previo si existe
  if (eventSource) {
    eventSource.close();
    eventSource = null;
  }

  function abrirStream(runId) {
    eventSource = new EventSource(`/logs_stream?run_id=${encodeURIComponent(runId)}`);

    eventSource.onmessage = function (event) {
      if (event.data.includes("ZIP generado correctamente")) {
        zipListo = true;
      }
      if (event.data.startsWith("❌")) {
        ultimoMensajeError = event.data;
      }

      if (event.data === "__FIN__") {
        logs.innerHTML += "\n🏁 Proceso finalizado\n";

        eventSource.close();
        eventSource = null;

        if (zipListo) {
          finalizarEstado("done", "Proceso completado. Preparando descarga...");
          logs.innerHTML += "📦 Preparando descarga del ZIP...\n";
          setTimeout(() => {
            descargarZipSiExiste(logs);
          }, 800);
        } else {
          finalizarEstado("error", ultimoMensajeError || "El proceso terminó sin generar ZIP.");
          logs.innerHTML += "❌ El proceso terminó sin generar ZIP\n";
        }

        return;
      }

      actualizarEstadoDesdeLog(event.data);
      logs.innerHTML += event.data + "\n";
      logs.scrollTop = logs.scrollHeight;
    };

    eventSource.onerror = function () {
      finalizarEstado("error", "Se perdió la conexión de seguimiento con el servidor.");
      logs.innerHTML += "\n❌ Error en el stream de logs\n";
      eventSource.close();
      eventSource = null;
    };
  }

  // Enviar Excel al backend
  fetch("/procesar", {
    method: "POST",
    body: new FormData(this)
  })
    .then(async (response) => {
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        finalizarEstado("error", data.error || "No fue posible iniciar el procesamiento.");
        logs.innerHTML += `\n❌ ${data.error || "Error al iniciar el procesamiento"}\n`;
        return;
      }

      const data = await response.json().catch(() => ({}));
      if (!data.run_id) {
        finalizarEstado("error", "No se recibió identificador de ejecución.");
        logs.innerHTML += "\n❌ No se recibió identificador de ejecución\n";
        return;
      }

      abrirStream(data.run_id);
    })
    .catch(() => {
      finalizarEstado("error", "Error iniciando la solicitud al servidor.");
      logs.innerHTML += "\n❌ Error al iniciar el procesamiento\n";
  });
});
