// Gentle moving backgrounds behind page headings.
// Use: <canvas class="ambient" data-mode="grid|bubbles|wave|wind"></canvas> inside a .hero-wrap.
// Stops when off screen or in a background tab, and draws a single still frame for reduced motion.
(function () {
  var calm = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var root = document.documentElement;

  function colours() {
    var cs = getComputedStyle(root), g = function (n, d) { return cs.getPropertyValue(n).trim() || d; };
    return {
      dark: root.getAttribute("data-theme") === "dark",
      ink: g("--muted", "#56627A"), accent: g("--accent", "#1F3D73"),
      tech: [g("--c-wind", "#2a78d6"), g("--c-solar", "#eda100"), g("--c-battery", "#e87ba4"), g("--c-hydro", "#008300")]
    };
  }
  function rgba(hex, a) {
    var h = hex.replace("#", ""); if (h.length === 3) h = h.replace(/./g, "$&$&");
    var n = parseInt(h, 16); return "rgba(" + (n >> 16 & 255) + "," + (n >> 8 & 255) + "," + (n & 255) + "," + a + ")";
  }
  var rand = function (a, b) { return a + Math.random() * (b - a); };

  // A drifting network of points, with pulses of energy running along the links
  function grid(w, h) {
    var n = Math.round(Math.min(70, w * h / 16000)), pts = [], pulses = [];
    for (var i = 0; i < n; i++) pts.push({ x: rand(0, w), y: rand(0, h), vx: rand(-.15, .15), vy: rand(-.1, .1), c: i % 4 });
    return function (ctx, C, dt) {
      var link = Math.min(170, w / 6);
      pts.forEach(function (p) {
        p.x += p.vx * dt; p.y += p.vy * dt;
        if (p.x < -20) p.x = w + 20; if (p.x > w + 20) p.x = -20; if (p.y < -20) p.y = h + 20; if (p.y > h + 20) p.y = -20;
      });
      ctx.lineWidth = 1;
      for (var i = 0; i < pts.length; i++) for (var j = i + 1; j < pts.length; j++) {
        var a = pts[i], b = pts[j], d = Math.hypot(a.x - b.x, a.y - b.y);
        if (d < link) {
          ctx.strokeStyle = rgba(C.accent, (1 - d / link) * (C.dark ? .22 : .16));
          ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
          if (!calm && Math.random() < .0009 * dt) pulses.push({ a: a, b: b, t: 0, c: a.c });
        }
      }
      pulses = pulses.filter(function (q) { return (q.t += .012 * dt) < 1; });
      pulses.forEach(function (q) {
        var x = q.a.x + (q.b.x - q.a.x) * q.t, y = q.a.y + (q.b.y - q.a.y) * q.t;
        ctx.fillStyle = rgba(C.tech[q.c], .85); ctx.beginPath(); ctx.arc(x, y, 2.4, 0, 7); ctx.fill();
      });
      pts.forEach(function (p) { ctx.fillStyle = rgba(C.tech[p.c], C.dark ? .55 : .45); ctx.beginPath(); ctx.arc(p.x, p.y, 2.2, 0, 7); ctx.fill(); });
    };
  }

  // Bubbles rising in the wind, solar, battery and hydro colours
  function bubbles(w, h) {
    var n = Math.round(Math.min(46, w / 28)), bs = [];
    var make = function (y) { return { x: rand(0, w), y: y, r: rand(3, 16), v: rand(.15, .5), ph: rand(0, 6), c: Math.floor(rand(0, 4)) }; };
    for (var i = 0; i < n; i++) bs.push(make(rand(0, h)));
    return function (ctx, C, dt, t) {
      bs.forEach(function (b, i) {
        b.y -= b.v * dt; if (b.y < -20) bs[i] = b = make(h + 20);
        var x = b.x + Math.sin(t / 900 + b.ph) * 10, a = C.dark ? .22 : .18;
        ctx.fillStyle = rgba(C.tech[b.c], a); ctx.strokeStyle = rgba(C.tech[b.c], a * 2.2);
        ctx.beginPath(); ctx.arc(x, b.y, b.r, 0, 7); ctx.fill(); ctx.stroke();
      });
    };
  }

  // Daily price curves drifting across: a midday dip and an evening peak, like the real NEM
  function wave(w, h) {
    var lines = [0, 1, 2, 3, 4].map(function (i) { return { off: i * 0.9, amp: 0.55 + i * 0.12, c: i % 4 }; });
    return function (ctx, C, dt, t) {
      var period = Math.max(w * .55, 380);
      lines.forEach(function (L, k) {
        ctx.strokeStyle = rgba(k % 2 ? C.tech[1] : C.tech[0], C.dark ? .32 : .24); ctx.lineWidth = 1.6;
        ctx.beginPath();
        for (var x = 0; x <= w; x += 6) {
          var u = ((x + t * .03 + L.off * 120) % period) / period;          // position within the day, 0 to 1
          var dip = -Math.exp(-Math.pow((u - .5) / .12, 2));                  // midday solar dip
          var peak = 1.3 * Math.exp(-Math.pow((u - .76) / .06, 2));           // evening peak
          var y = h * (.5 + k * .06) - (dip + peak) * h * .16 * L.amp;
          x ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
        }
        ctx.stroke();
      });
    };
  }

  // Streaks of wind blowing across
  function wind(w, h) {
    var n = Math.round(Math.min(40, w / 30)), s = [];
    var make = function (x) { return { x: x, y: rand(0, h), len: rand(40, 140), v: rand(1, 2.6), ph: rand(0, 6) }; };
    for (var i = 0; i < n; i++) s.push(make(rand(-w, w)));
    return function (ctx, C, dt, t) {
      ctx.lineCap = "round";
      s.forEach(function (q, i) {
        q.x += q.v * dt; if (q.x - q.len > w) s[i] = q = make(-rand(20, 200));
        var y = q.y + Math.sin(t / 700 + q.ph) * 6;
        var g = ctx.createLinearGradient(q.x - q.len, 0, q.x, 0);
        g.addColorStop(0, rgba(C.tech[0], 0)); g.addColorStop(1, rgba(C.tech[0], C.dark ? .45 : .32));
        ctx.strokeStyle = g; ctx.lineWidth = 1.6;
        ctx.beginPath(); ctx.moveTo(q.x - q.len, y); ctx.quadraticCurveTo(q.x - q.len / 2, y - 6, q.x, y); ctx.stroke();
      });
    };
  }

  var MODES = { grid: grid, bubbles: bubbles, wave: wave, wind: wind };

  document.querySelectorAll("canvas.ambient").forEach(function (cv) {
    var ctx = cv.getContext("2d"), mode = MODES[cv.dataset.mode] || grid, step, C = colours(), w, h, visible = true, last = 0, raf = 0;
    function size() {
      var r = cv.getBoundingClientRect(), dpr = Math.min(window.devicePixelRatio || 1, 2);
      w = r.width; h = r.height; cv.width = w * dpr; cv.height = h * dpr; ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      step = mode(w, h);
    }
    function frame(t) {
      var dt = last ? Math.min((t - last) / 16.7, 3) : 1; last = t;
      ctx.clearRect(0, 0, w, h); step(ctx, C, dt, t);
      if (!calm && visible && !document.hidden) raf = requestAnimationFrame(frame); else raf = 0;
    }
    function start() { if (!raf) { last = 0; raf = requestAnimationFrame(frame); } }
    size();
    if (calm) { for (var k = 0; k < 120; k++) step(ctx, C, 1, k * 16); ctx.clearRect(0, 0, w, h); step(ctx, C, 1, 2000); return; }
    window.addEventListener("resize", function () { size(); start(); });
    document.addEventListener("visibilitychange", start);
    if ("IntersectionObserver" in window) new IntersectionObserver(function (e) { visible = e[0].isIntersecting; if (visible) start(); }).observe(cv);
    new MutationObserver(function () { C = colours(); }).observe(root, { attributes: true, attributeFilter: ["data-theme"] });
    start();
  });
})();
