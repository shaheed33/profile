// Keeps pages light. Any element with class "explain" is hidden and an (i) button
// is added to the heading above it; the button opens the text in a small pop-up.
// The text is read when the button is pressed, so text filled in later by a
// page's own script still shows.
(function () {
  var open = null;
  function close() { if (open) { open.btn.setAttribute("aria-expanded", "false"); open.box.remove(); open = null; } }
  function heading(el) {
    var n = el;
    for (var up = 0; up < 4 && n; up++, n = n.parentElement) {
      for (var s = n.previousElementSibling; s; s = s.previousElementSibling) {
        if (s.matches("h1,h2,h3,h4,.card-header,.h-ic")) return s.matches(".h-ic") ? s.querySelector("h2,h3") || s : s;
        var inner = s.querySelectorAll("h1,h2,h3,.card-header");
        if (inner.length && !s.matches("section,.card")) return inner[inner.length - 1];
      }
      var own = n.parentElement && n.parentElement.querySelector(":scope > .card-header, :scope > h2, :scope > h3");
      if (own && own !== n) return own;
    }
    return null;
  }
  function setup(el) {
    if (el.dataset.xdone) return; el.dataset.xdone = "1";
    var h = el.dataset.for ? document.getElementById(el.dataset.for) : heading(el); if (!h) return;
    el.hidden = true;
    // several explainers under one heading share a single button
    if (h._xi) { h._xi.push(el); return; }
    h._xi = [el];
    var b = document.createElement("button");
    b.type = "button"; b.className = "xi"; b.textContent = "i";
    b.setAttribute("aria-label", "More about " + (h.textContent || "this").trim().slice(0, 60));
    b.setAttribute("aria-expanded", "false");
    b.addEventListener("click", function (e) {
      e.stopPropagation(); e.preventDefault();
      if (open && open.btn === b) { close(); return; }
      close();
      var box = document.createElement("div"); box.className = "xpop"; box.setAttribute("role", "dialog");
      box.innerHTML = h._xi.filter(function (x) { return x.innerHTML.trim(); }).map(function (x) { return "<p>" + x.innerHTML + "</p>"; }).join("");
      document.body.appendChild(box);
      var r = b.getBoundingClientRect();
      box.style.left = Math.max(12, Math.min(r.left + scrollX - 12, scrollX + innerWidth - box.offsetWidth - 12)) + "px";
      box.style.top = (r.bottom + scrollY + 8) + "px";
      b.setAttribute("aria-expanded", "true");
      open = { btn: b, box: box };
    });
    h.appendChild(b);
  }
  function run() { document.querySelectorAll(".explain").forEach(setup); }
  document.addEventListener("click", function (e) { if (open && !open.box.contains(e.target)) close(); });
  document.addEventListener("keydown", function (e) { if (e.key === "Escape") close(); });
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", run); else run();
  // pages that draw sections later can call this again
  window.explainAll = run;
})();
