document.addEventListener("DOMContentLoaded", () => {
  const form = document.querySelector("form");
  if (!form) return;

  form.addEventListener("submit", () => {
    setTimeout(() => {
      Swal.fire({
        icon: "success",
        title: "🧠 Trabajo completado",
        html: "Tus documentos han sido generados exitosamente.",
        confirmButtonText: "Perfecto 😎",
        background: "#1e1e2f",
        color: "#fff",
        confirmButtonColor: "#ff00cc"
      });
    }, 1200);
  });
});
