let eventSource = null;

document.getElementById("form-procesar").addEventListener("submit", function (e) {
  e.preventDefault();

  const logs = document.getElementById("logs-box");
  logs.style.display = "block";
  logs.innerHTML = "🔄 Iniciando proceso...\n";

  // Cerrar stream previo si existe
  if (eventSource) {
    eventSource.close();
    eventSource = null;
  }

  // Abrir stream SSE
  eventSource = new EventSource("/logs_stream");

  eventSource.onmessage = function (event) {

    if (event.data === "__FIN__") {
      logs.innerHTML += "\n✅ Proceso finalizado correctamente\n";
      logs.innerHTML += "📦 Preparando descarga del ZIP...\n";

      eventSource.close();
      eventSource = null;

      // ⬇️ Descargar ZIP automáticamente
      setTimeout(() => {
        window.location.href = "/descargar_zip";
      }, 800);

      return;
    }

    logs.innerHTML += event.data + "\n";
    logs.scrollTop = logs.scrollHeight;
  };

  eventSource.onerror = function () {
    logs.innerHTML += "\n❌ Error en el stream de logs\n";
    eventSource.close();
    eventSource = null;
  };

  // Enviar Excel al backend
  fetch("/procesar", {
    method: "POST",
    body: new FormData(this)
  }).catch(() => {
    logs.innerHTML += "\n❌ Error al iniciar el procesamiento\n";
  });
});
