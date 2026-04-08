document.addEventListener("DOMContentLoaded", () => {
  const btn = document.getElementById("theme-toggle");
  const body = document.body;

  const saved = localStorage.getItem("theme");
  if (saved === "light") {
    body.classList.add("light-mode");
    btn.textContent = "☀️";
  }

  btn.addEventListener("click", () => {
    const isLight = body.classList.toggle("light-mode");
    localStorage.setItem("theme", isLight ? "light" : "dark");
    btn.textContent = isLight ? "☀️" : "🌙";
  });
});
