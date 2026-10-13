// "More tools" strip at the foot of each project page, so readers can move
// between projects without going back to the home page.
(function () {
  var P = [
    ["vic-housing.html", "Is Victoria building enough homes?", "Housing"],
    ["local-economy.html", "What makes your local economy tick?", "Local economies"],
    ["councils.html", "How does your council compare?", "Councils"],
    ["roadmap.html", "Is NSW on track for 2030?", "Energy"],
    ["simulator.html", "Could the NEM run without coal?", "Energy"],
    ["prices.html", "When is electricity cheap?", "Energy"],
    ["wa-economy.html", "How fast is WA growing right now?", "Economy"],
    ["maldives-loans.html", "Who lends to Maldives, and for what?", "Public money"]
  ];
  var here = location.pathname.split("/").pop() || "index.html";
  var foot = document.querySelector("footer");
  if (!foot) return;
  var box = document.createElement("nav");
  box.className = "more-projects container-xl";
  box.setAttribute("aria-label", "More tools");
  box.innerHTML = '<h2>More tools</h2><ul>' + P.filter(function (p) { return p[0] !== here && here.indexOf(p[0].replace(".html", "")) !== 0; })
    .map(function (p) { return '<li><a href="' + p[0] + '"><span>' + p[2] + '</span>' + p[1] + '</a></li>'; }).join("") +
    '</ul><a class="home" href="index.html#tools">All tools and about me →</a>';
  foot.parentNode.insertBefore(box, foot);
})();
