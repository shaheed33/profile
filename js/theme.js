(function () {
  var root = document.documentElement;
  // A soft shadow under the pinned header once the page has scrolled
  var hdr = document.querySelector(".site-header");
  if (hdr) {
    var onScroll = function () { hdr.classList.toggle("scrolled", window.scrollY > 4); };
    window.addEventListener("scroll", onScroll, { passive: true }); onScroll();
    root.style.setProperty("--hdr-h", hdr.offsetHeight + "px");
  }
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
