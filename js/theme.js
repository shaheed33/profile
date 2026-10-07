(function () {
  var root = document.documentElement;
  var btn = document.querySelector(".theme-toggle");
  function label() {
    if (!btn) return;
    var dark = root.getAttribute("data-theme") === "dark";
    btn.setAttribute("aria-label", dark ? "Switch to light theme" : "Switch to dark theme");
    btn.title = dark ? "Light theme" : "Dark theme";
  }
  label();
  if (!btn) return;
  btn.addEventListener("click", function () {
    var next = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
    root.setAttribute("data-theme", next);
    root.setAttribute("data-bs-theme", next);
    try { localStorage.setItem("theme", next); } catch (e) {}
    label();
    if (typeof window.onThemeChange === "function") window.onThemeChange();
    else if (document.querySelector(".js-plotly-plot")) location.reload();
  });
})();
