/* State Budget Resilience Monitor: page behaviour.
 * The arithmetic lives in state-budget-math.js; this file reads the controls,
 * draws the results and explains terms. */
(function () {
  'use strict';
  var $ = function (id) { return document.getElementById(id); };
  var data = window.STATE_BUDGET;
  var M = window.StateBudgetMath;
  var yearEl = $('year'); if (yearEl) yearEl.textContent = new Date().getFullYear();

  /* ---------- Glossary pop-ups ---------- */
  var GLOSSARY = {
    'budget': ['2026-27 budget', 'The financial plan each government published between May and June 2026. It sets spending for 2026-27, the budget year, and projects the three years after.'],
    'forward-estimates': ['Forward estimates', 'Projections for the three years after the budget year, here 2027-28 to 2029-30. They assume current policies continue and are revised at every budget and mid-year update. They are not promises.'],
    'general-government': ['General government sector', 'The part of the public sector paid for mainly by taxes and grants: departments, public schools, hospitals and police. It leaves out government businesses such as water, power and transport companies that charge for what they sell. Using this sector for every government keeps the comparison like for like.'],
    'nob': ['Operating balance', 'The net operating balance: revenue minus the cost of running services in a year, before spending on new roads, buildings and equipment. A surplus means day-to-day costs are covered. A deficit means the government is borrowing to pay some running costs. It is the main result each government reports.'],
    'net-debt': ['Net debt', 'What the government owes in borrowings, deposits it holds and lease liabilities, minus its cash, investments and the loans it has made to others. Measured at 30 June. It does not include unfunded superannuation.'],
    'interest-to-revenue': ['Interest cost', 'Interest paid on borrowings and leases in the year, also shown as a share of total revenue: how many cents of each revenue dollar go on interest. Credit rating agencies watch this share closely.'],
    'debt-to-revenue': ['Net debt to revenue', 'Net debt divided by a year’s total revenue. A figure of 100% means debt equals one year of revenue. Dividing by revenue lets large and small governments be compared.'],
    'gst': ['GST revenue', 'The Commonwealth collects the goods and services tax and passes all of it to the states and territories. The Commonwealth Grants Commission decides each one’s share so they can all provide similar services. For most governments it is the biggest single source of revenue.'],
    'other-grants': ['Other Commonwealth grants', 'Money from the Commonwealth for set purposes, such as public hospitals, schools, skills, housing and roads, plus a small amount from other sources. Some passes straight on to councils and non-government schools.'],
    'payroll-tax': ['Payroll tax', 'A tax on employers’ wage bills above a tax-free threshold. It rises and falls with jobs and pay. Figures here include levies charged on payrolls, such as Victoria’s Mental Health and Wellbeing Levy.'],
    'transfer-duty': ['Property stamp duty', 'Transfer duty (also called conveyance or stamp duty), paid when property is bought. It moves with both house prices and the number of sales, which makes it one of the most volatile state taxes.'],
    'royalties': ['Mining royalties', 'What mining and petroleum companies pay for the minerals and gas they take out of the ground. They depend on commodity prices, the exchange rate and volumes. Very large for Western Australia and Queensland, small elsewhere, and nil in the ACT.'],
    'employee': ['Wages', 'Employee expenses: salaries, wages and superannuation for public servants, including nurses, teachers and police. Usually a government’s largest cost.'],
    'other-spending': ['Other running costs', 'Every operating expense except wages, superannuation and interest: grants to councils and non-government schools, payments to contractors and service providers, supplies, and depreciation.'],
    'capex': ['Infrastructure spending', 'Purchases of non-financial assets: roads, rail, hospitals, schools and equipment. It is not a running cost, so it does not reduce the operating balance. But whatever an operating surplus does not cover is borrowed, so it adds to net debt.'],
    'percentage-point': ['Percentage points', 'An absolute change in a rate. Pay growth going from 3% to 4% a year is a rise of 1 percentage point.'],
    'repricing': ['Debt refinanced each year', 'Governments borrow for fixed terms. When interest rates rise, only debt that is refinanced or newly borrowed pays the higher rate. This is the share of the budget’s net debt refinanced each year. After two years at 20%, 40% of it pays the higher rate.'],
    'borrowing-rate': ['Cost of extra borrowing', 'The average interest rate on any extra debt the scenario creates, before any rate shock. 5% is this tool’s assumption; change it to test your own.'],
    'upf': ['Uniform Presentation Framework', 'An agreement between the Commonwealth, states and territories to publish budget statements in a common format, with common definitions. It is what makes these figures comparable.'],
    'revised': ['Revised estimate', 'The latest estimate for 2025-26, published with the 2026-27 budget. Governments call it the revised, estimated actual, estimated result or estimated outcome. Audited final results come later.'],
    'scenario': ['Scenario, not a forecast', 'A “what if” calculation: what would happen to the published budget if your shocks happened and nothing else changed. It does not say how likely the shocks are, and it assumes the government does not respond.']
  };

  var pop = $('term-pop');
  var openTerm = null;
  var hoverTimer = null;
  function placePop(btn) {
    var r = btn.getBoundingClientRect();
    var w = Math.min(340, document.documentElement.clientWidth - 24);
    pop.style.width = w + 'px';
    var left = Math.min(Math.max(12, r.left + r.width / 2 - w / 2), document.documentElement.clientWidth - w - 12);
    pop.style.left = (left + window.scrollX) + 'px';
    pop.hidden = false;
    var below = r.bottom + 10;
    var h = pop.offsetHeight;
    var top = (below + h > window.innerHeight - 8 && r.top - h - 10 > 8) ? r.top - h - 10 : below;
    pop.style.top = (top + window.scrollY) + 'px';
  }
  function showTerm(btn) {
    var entry = GLOSSARY[btn.dataset.term];
    if (!entry) return;
    if (openTerm && openTerm !== btn) openTerm.setAttribute('aria-expanded', 'false');
    pop.replaceChildren();
    var h = document.createElement('strong'); h.textContent = entry[0];
    var p = document.createElement('span'); p.textContent = entry[1];
    pop.append(h, p);
    pop.id = 'term-pop';
    btn.setAttribute('aria-describedby', 'term-pop');
    btn.setAttribute('aria-expanded', 'true');
    openTerm = btn;
    placePop(btn);
  }
  function hideTerm() {
    if (!openTerm) return;
    openTerm.setAttribute('aria-expanded', 'false');
    openTerm.removeAttribute('aria-describedby');
    openTerm = null;
    pop.hidden = true;
  }
  function wireTerms(scope) {
    (scope || document).querySelectorAll('.term').forEach(function (btn) {
      if (btn.dataset.wired) return;
      btn.dataset.wired = '1';
      btn.setAttribute('aria-expanded', 'false');
      btn.addEventListener('click', function (e) {
        e.preventDefault(); e.stopPropagation();
        if (openTerm === btn) hideTerm(); else showTerm(btn);
      });
      btn.addEventListener('mouseenter', function () {
        if (!window.matchMedia('(hover: hover)').matches) return;
        clearTimeout(hoverTimer); hoverTimer = setTimeout(function () { showTerm(btn); }, 120);
      });
      btn.addEventListener('mouseleave', function () {
        if (!window.matchMedia('(hover: hover)').matches) return;
        clearTimeout(hoverTimer); hoverTimer = setTimeout(function () { if (!pop.matches(':hover')) hideTerm(); }, 180);
      });
      // Keyboard users: moving focus away closes this term's pop-up, but never one opened since.
      btn.addEventListener('blur', function () { setTimeout(function () { if (openTerm === btn && document.activeElement !== btn) hideTerm(); }, 100); });
    });
  }
  pop.addEventListener('mouseleave', function () { if (window.matchMedia('(hover: hover)').matches) hideTerm(); });
  document.addEventListener('click', function (e) { if (openTerm && !pop.contains(e.target)) hideTerm(); });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && openTerm) { var b = openTerm; hideTerm(); b.focus(); } });
  var resizeTimer = null;
  window.addEventListener('resize', function () {
    if (openTerm) placePop(openTerm);
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(function () { if (typeof redraw === 'function') redraw(); }, 150);
  });
  var redraw = null;
  wireTerms();

  if (!data || !Array.isArray(data.jurisdictions) || !data.jurisdictions.length || !M) {
    $('load-error').hidden = false;
    $('load-error').textContent = 'The budget data could not be loaded. Reload the page, or download the figures from the sources section below.';
    return;
  }

  /* ---------- Formatting ---------- */
  var MINUS = '−';
  function money(v) {
    if (typeof v !== 'number' || !isFinite(v)) return 'Not available';
    var a = Math.abs(v), s = v < 0 ? MINUS : '';
    if (a >= 1000) return s + '$' + (a / 1000).toLocaleString('en-AU', { minimumFractionDigits: 1, maximumFractionDigits: 1 }) + 'bn';
    if (a >= 10) return s + '$' + Math.round(a).toLocaleString('en-AU') + 'm';
    return s + '$' + a.toFixed(1) + 'm';
  }
  function signedMoney(v) { return (v > 0.0005 ? '+' : v < -0.0005 ? '' : '') + (Math.abs(v) < 0.05 ? '$0m' : money(v)); }
  function pct(v, d) { return (typeof v === 'number' && isFinite(v)) ? (v * 100).toFixed(d === undefined ? 1 : d) + '%' : 'Not available'; }
  function signedPts(v) { var x = v * 100; return (x > 0.005 ? '+' : x < -0.005 ? MINUS : '') + Math.abs(x).toFixed(1) + ' pts'; }
  function balanceWords(v) { return v >= 0 ? money(v) + ' surplus' : money(-v) + ' deficit'; }
  var YEARS = data.meta.years; // ["2025-26", ... "2029-30"]

  /* ---------- Controls ---------- */
  var CONTROLS = {
    gst: { scale: 100, unit: '%' }, otherGrants: { scale: 100, unit: '%' }, payroll: { scale: 100, unit: '%' },
    duty: { scale: 100, unit: '%' }, royalties: { scale: 100, unit: '%' },
    wages: { scale: 100, unit: 'pts', dp: 2 }, otherSpending: { scale: 100, unit: '%', dp: 1 }, capex: { scale: 100, unit: '%' },
    rateShock: { scale: 100, unit: 'pts', dp: 2 }, borrowingRate: { scale: 100, unit: '%', dp: 2, plain: true }, repricing: { scale: 100, unit: '%', plain: true }
  };
  /* Ready-made scenarios. Sizes come from each government's own history (data/shock_history.js). */
  var HIST = window.SHOCK_HISTORY || null;
  var HIST_KEYS = { gst: 'gst', payroll: 'payroll', duty: 'duty', royalties: 'royalties', wages: 'wages', rateShock: 'rates' };
  var HIST_NAMES = { gst: 'GST', payroll: 'payroll tax', duty: 'stamp duty', royalties: 'royalties', wages: 'public sector pay growth', rateShock: 'the 10-year bond yield' };
  function histOf(key, jid) {
    if (!HIST || !HIST_KEYS[key]) return null;
    if (key === 'gst') return HIST.national.gst;
    if (key === 'rateShock') return HIST.national.rates;
    var st = HIST.states[jid];
    var m = st && st[HIST_KEYS[key]];
    if (key === 'royalties' && (!m || !(byIdEarly[jid] && byIdEarly[jid].series.royalties[1] > 0))) return null;
    return m || null;
  }
  function sizeOf(key, m, level) {
    var v = m[level];
    return m.unit === 'rate' ? Math.round(v * 1000) / 10 : Math.round(v * 100);
  }
  var byIdEarly = {};
  data.jurisdictions.forEach(function (j) { byIdEarly[j.id] = j; });
  var PRESETS = [
    { id: 'published', name: 'Budget as published', keys: [], level: null },
    { id: 'property', name: 'Property slump', keys: ['duty'], level: 'worst' },
    { id: 'commodity', name: 'Commodity price fall', keys: ['royalties'], level: 'worst' },
    { id: 'gst', name: 'GST shortfall', keys: ['gst'], level: 'worst' },
    { id: 'wages', name: 'Wage breakout', keys: ['wages'], level: 'worst' },
    { id: 'rates', name: 'Interest rate jump', keys: ['rateShock'], level: 'worst' },
    { id: 'badyear', name: 'Bad year, all revenue', keys: ['gst', 'payroll', 'duty', 'royalties'], level: 'bad_year' },
    { id: 'severe', name: 'Severe downturn', keys: ['gst', 'payroll', 'duty', 'royalties'], level: 'worst' }
  ];
  function presetValues(p, jid) {
    var set = {};
    p.keys.forEach(function (k) { var m = histOf(k, jid); if (m) set[k] = sizeOf(k, m, p.level); });
    return set;
  }
  function presetAvailable(p, jid) { return !p.keys.length || Object.keys(presetValues(p, jid)).length > 0; }
  function shortName(j) { return j.kind === 'territory' ? 'the ' + j.short : j.name; }
  function sizeText(k, v) { var sign = v > 0 ? '+' : v < 0 ? MINUS : ''; return k === 'wages' || k === 'rateShock' ? sign + Math.abs(v).toFixed(1) + ' percentage points' : sign + Math.abs(v) + '%'; }
  function presetDesc(p, jid) {
    var j = byIdEarly[jid], set = presetValues(p, jid);
    if (p.id === 'published') return 'No shocks. The figures are ' + shortName(j) + '\u2019s own budget.';
    if (!Object.keys(set).length) return 'Not available for ' + shortName(j) + '.';
    if (p.keys.length === 1) {
      var k = p.keys[0], m = histOf(k, jid);
      var what = { duty: 'Stamp duty falls ' + Math.abs(set[k]) + '% below the budget', royalties: 'Royalties fall ' + Math.abs(set[k]) + '% below the budget',
        gst: 'GST falls ' + Math.abs(set[k]) + '% below the budget', wages: 'Public sector pay grows ' + set[k].toFixed(1) + ' percentage points a year faster than budgeted',
        rateShock: 'Borrowing costs rise ' + set[k].toFixed(1) + ' percentage points' }[k];
      var whose = k === 'gst' ? 'the national GST pool' : k === 'rateShock' ? 'the 10-year bond yield' : shortName(j) + '\u2019s ' + HIST_NAMES[k];
      return what + ': a repeat of ' + m.worst_year + ', the worst year for ' + whose + ' in records from ' + m.years[0] + '.';
    }
    var parts = Object.keys(set).map(function (k) { return HIST_NAMES[k] + ' ' + sizeText(k, set[k]); });
    return (p.level === 'worst'
      ? 'Every revenue line at its worst year on record, all at once, which has never happened in a single year: '
      : 'Each revenue line has a year as bad as roughly one in five, at the same time: ') + parts.join(', ') + '.';
  }
  var defaultsUi = {};
  Object.keys(CONTROLS).forEach(function (k) { defaultsUi[k] = +$('s-' + k).value; });

  function decimals(k) { var st = String($('s-' + k).step); return st.indexOf('.') > -1 ? st.split('.')[1].length : 0; }
  function showValue(k) {
    var c = CONTROLS[k], v = +$('s-' + k).value, a = Math.abs(v);
    var txt = c.unit === 'pts' ? a.toFixed(1) : k === 'borrowingRate' ? (Math.round(a * 4) % 2 ? a.toFixed(2) : a.toFixed(1)) : (a % 1 ? a.toFixed(1) : a.toFixed(0));
    var sign = c.plain ? '' : (v > 0 ? '+' : v < 0 ? MINUS : '');
    var text = sign + txt + (c.unit === 'pts' ? ' percentage points' : '%');
    var box = $('n-' + k);
    if (box && document.activeElement !== box) box.value = String(+v.toFixed(decimals(k)));
    $('s-' + k).setAttribute('aria-valuetext', text);
    var ctl = $('s-' + k).closest('.control');
    if (ctl) {
      ctl.classList.toggle('changed', Math.abs(v - defaultsUi[k]) > 1e-9);
      ctl.classList.toggle('down', v < defaultsUi[k] - 1e-9);
      ctl.classList.toggle('up', v > defaultsUi[k] + 1e-9);
    }
  }
  /* Typed values: clamp to the slider's range and round to its step. */
  function fromBox(k, final) {
    var box = $('n-' + k), input = $('s-' + k);
    var raw = String(box.value).replace('\u2212', '-').trim();
    if (raw === '' || raw === '-' || isNaN(+raw)) { if (final) showValueForce(k); return; }
    var st = +input.step, v = Math.round(+raw / st) * st;
    v = Math.min(+input.max, Math.max(+input.min, v));
    input.value = v;
    if (final) showValueForce(k);
    update();
    if (final) syncUrl();
  }
  function showValueForce(k) { var box = $('n-' + k); box.value = String(+(+$('s-' + k).value).toFixed(decimals(k))); }
  var SCALE_WORDS = {
    gst: ['Below budget', 'Above budget'], otherGrants: ['Below budget', 'Above budget'], payroll: ['Below budget', 'Above budget'],
    duty: ['Below budget', 'Above budget'], royalties: ['Below budget', 'Above budget'], wages: ['Slower pay growth', 'Faster pay growth'],
    otherSpending: ['Less spending', 'More spending'], capex: ['Less spending', 'More spending'], rateShock: ['Lower rates', 'Higher rates']
  };
  function assumptions() {
    var a = {};
    Object.keys(CONTROLS).forEach(function (k) { a[k] = +$('s-' + k).value / CONTROLS[k].scale; });
    return a;
  }
  function setControls(values) {
    Object.keys(CONTROLS).forEach(function (k) {
      var input = $('s-' + k);
      var v = values[k] !== undefined ? values[k] : defaultsUi[k];
      v = Math.min(+input.max, Math.max(+input.min, v));
      input.value = v;
      showValue(k);
    });
  }
  function activePreset(jid) {
    var cur = {};
    jid = jid || (current && current.id);
    Object.keys(CONTROLS).forEach(function (k) { cur[k] = +$('s-' + k).value; });
    for (var i = 0; i < PRESETS.length; i++) {
      var p = PRESETS[i];
      if (!presetAvailable(p, jid)) continue;
      var set = presetValues(p, jid);
      var match = Object.keys(CONTROLS).every(function (k) {
        if (k === 'borrowingRate' || k === 'repricing') return true;
        var want = set[k] !== undefined ? set[k] : defaultsUi[k];
        return Math.abs(cur[k] - want) < 1e-9;
      });
      if (match) return p;
    }
    return null;
  }

  /* ---------- Jurisdiction choice ---------- */
  var current = null;
  var byId = {};
  data.jurisdictions.forEach(function (j) { byId[j.id] = j; });
  var chips = $('chips'), select = $('jurisdiction');
  select.replaceChildren();
  data.jurisdictions.forEach(function (j) {
    var b = document.createElement('button');
    b.type = 'button'; b.className = 'chip'; b.setAttribute('role', 'radio'); b.dataset.id = j.id;
    b.textContent = j.short; b.title = j.name; b.setAttribute('aria-label', j.name);
    b.addEventListener('click', function () { choose(j.id, true); });
    b.addEventListener('keydown', function (e) {
      var keys = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 };
      if (!keys[e.key]) return;
      e.preventDefault();
      var list = data.jurisdictions, i = list.indexOf(j);
      var next = list[(i + keys[e.key] + list.length) % list.length];
      choose(next.id, true);
      chips.querySelector('[data-id="' + next.id + '"]').focus();
    });
    chips.appendChild(b);
    var o = document.createElement('option'); o.value = j.id; o.textContent = j.name; select.appendChild(o);
  });
  select.disabled = false;
  select.addEventListener('change', function () { choose(select.value, true); });

  function choose(id, push) {
    var was = current ? activePreset(current.id) : null;
    current = byId[id] || data.jurisdictions[0];
    if (was && was.id !== 'published') applyPreset(was, false);
    select.value = current.id;
    chips.querySelectorAll('.chip').forEach(function (b) {
      var on = b.dataset.id === current.id;
      b.classList.toggle('on', on); b.setAttribute('aria-checked', on ? 'true' : 'false'); b.tabIndex = on ? 0 : -1;
    });
    if ($('bar-jur')) $('bar-jur').value = current.id;
    renderBaseline();
    renderHistory();
    update();
    if (push) syncUrl();
  }

  /* ---------- Baseline ---------- */
  var MIX_LABELS = {
    gst: ['GST', 'gst'], otherGrants: ['Other Commonwealth grants', 'other-grants'], payroll: ['Payroll tax', 'payroll-tax'],
    duty: ['Property stamp duty', 'transfer-duty'], otherTax: ['Other state taxes', null], royalties: ['Mining royalties', 'royalties'],
    other: ['Fees, sales, interest, dividends and other', null]
  };
  function renderBaseline() {
    var j = current, s = j.series;
    $('j-name').textContent = j.name;
    $('j-source-line').textContent = 'Source: ' + j.document.title + '.';
    $('b-revenue').textContent = money(s.revenue[1]);
    $('b-revenue-note').textContent = 'Budget year';
    $('b-nob').textContent = money(s.nob[1]);
    $('b-nob').classList.toggle('negative', s.nob[1] < 0);
    $('b-nob-note').textContent = (s.nob[1] >= 0 ? 'Surplus' : 'Deficit') + '; ' + balanceWords(s.nob[4]) + ' planned for 2029-30';
    $('b-debt').textContent = money(s.net_debt[1]);
    $('b-debt-note').textContent = pct(s.net_debt[1] / s.revenue[1], 0) + ' of a year’s revenue';
    $('b-interest').textContent = money(s.interest[1]);
    $('b-interest-note').textContent = pct(s.interest[1] / s.revenue[1]) + ' of revenue';
    var notes = [];
    Object.keys(j.sources).forEach(function (k) { if (j.sources[k].note) notes.push(j.sources[k].note); });
    if (j.own_net_debt) notes.push('The ACT’s own headline net debt for June 2027 is ' + money(j.own_net_debt.values[1]) + '. ' + j.own_net_debt.note);
    $('j-note').hidden = !notes.length;
    $('j-note').textContent = notes.length ? 'Notes for ' + j.short + ': ' + notes.join(' ') : '';
    // Revenue mix
    var mix = M.revenueMix(s, 1), total = s.revenue[1];
    var bar = $('mix-bar'), legend = $('mix-legend');
    bar.replaceChildren(); legend.replaceChildren();
    var desc = [];
    mix.forEach(function (m) {
      var share = Math.max(0, m.value) / total;
      desc.push(MIX_LABELS[m.key][0] + ' ' + pct(share, 0));
      if (share > 0.0005) {
        var seg = document.createElement('i'); seg.className = 'mx mx-' + m.key; seg.style.width = (share * 100) + '%';
        bar.appendChild(seg);
      }
      var li = document.createElement('li');
      var sw = document.createElement('i'); sw.className = 'sw mx-' + m.key; sw.setAttribute('aria-hidden', 'true');
      var name = document.createElement('span'); name.className = 'mx-name';
      var label = MIX_LABELS[m.key];
      if (label[1]) { var t = document.createElement('button'); t.type = 'button'; t.className = 'term'; t.dataset.term = label[1]; t.textContent = label[0]; name.appendChild(t); }
      else name.textContent = label[0];
      var val = document.createElement('span'); val.className = 'mx-val'; val.textContent = pct(share, 0) + ' · ' + money(m.value);
      li.append(sw, name, val); legend.appendChild(li);
    });
    bar.setAttribute('aria-label', 'Revenue mix, 2026-27: ' + desc.join(', '));
    wireTerms(legend);
  }

  /* ---------- Charts ---------- */
  var SVGNS = 'http://www.w3.org/2000/svg';
  function el(tag, attrs, text) {
    var e = document.createElementNS(SVGNS, tag);
    Object.keys(attrs).forEach(function (k) { e.setAttribute(k, attrs[k]); });
    if (text !== undefined) e.textContent = text;
    return e;
  }
  function niceStep(range) {
    var raw = range / 4, mag = Math.pow(10, Math.floor(Math.log10(raw || 1)));
    var n = raw / mag;
    return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 2.5 ? 2.5 : n <= 5 ? 5 : 10) * mag;
  }
  function tick(v, step) {
    if (Math.abs(v) < 1e-9) return '$0';
    var a = Math.abs(v), s = v < 0 ? MINUS : '';
    if (a >= 1000) { var bn = a / 1000; return s + '$' + bn.toFixed(step >= 1000 && Math.abs(bn - Math.round(bn)) < 1e-9 ? 0 : 1) + 'bn'; }
    return s + '$' + Math.round(a) + 'm';
  }
  function axis(svg, lo, hi, y, x0, x1) {
    var step = niceStep(hi - lo);
    for (var v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) {
      var yy = y(v);
      svg.appendChild(el('line', { x1: x0, x2: x1, y1: yy, y2: yy, 'class': Math.abs(v) < 1e-9 ? 'c-zero' : 'c-grid' }));
      svg.appendChild(el('text', { x: x0 - 8, y: yy + 4, 'text-anchor': 'end', 'class': 'c-tick' }, tick(v, step)));
    }
  }
  /* Draw in the chart's real pixel width so labels stay readable on phones. */
  function frame(svg) {
    var w = Math.round(Math.max(300, Math.min(680, svg.getBoundingClientRect().width || 640)));
    var h = w < 480 ? 230 : 250;
    svg.setAttribute('viewBox', '0 0 ' + w + ' ' + h);
    return { w: w, h: h, x0: w < 480 ? 58 : 78, x1: w - 12, top: 16, bottom: h - 40 };
  }
  function resetSvg(svg) {
    var keep = Array.prototype.filter.call(svg.childNodes, function (n) { return n.nodeName === 'title' || n.nodeName === 'desc'; });
    svg.replaceChildren.apply(svg, keep);
  }
  function drawNob(result) {
    var svg = $('nob-chart'); resetSvg(svg);
    var ys = result.years;
    var vals = [];
    ys.forEach(function (y) { vals.push(y.published.nob, y.nob); });
    var lo = Math.min(0, Math.min.apply(null, vals)), hi = Math.max(0, Math.max.apply(null, vals));
    var pad = Math.max((hi - lo) * 0.12, Math.abs(hi) * 0.05 + 1);
    lo -= (lo < 0 ? pad : 0); hi += (hi > 0 ? pad : 0); if (hi - lo < 1) hi = lo + 1;
    var f = frame(svg), top = f.top, bottom = f.bottom, x0 = f.x0, x1 = f.x1;
    var y = function (v) { return bottom - (v - lo) / (hi - lo) * (bottom - top); };
    axis(svg, lo, hi, y, x0, x1);
    var slot = (x1 - x0) / ys.length, bw = Math.min(34, slot * 0.28);
    ys.forEach(function (d, i) {
      var cx = x0 + slot * (i + 0.5);
      [[d.published.nob, cx - bw - 3, 'b-pub'], [d.nob, cx + 3, 'b-scn']].forEach(function (b) {
        var yy = y(b[0]), y0 = y(0);
        svg.appendChild(el('rect', { x: b[1], y: Math.min(yy, y0), width: bw, height: Math.max(1, Math.abs(y0 - yy)), rx: 2, 'class': b[2] }));
      });
      svg.appendChild(el('text', { x: cx, y: bottom + 26, 'text-anchor': 'middle', 'class': 'c-tick' }, YEARS[d.index]));
    });
    $('nob-chart-desc').textContent = ys.map(function (d) { return YEARS[d.index] + ': published ' + balanceWords(d.published.nob) + ', scenario ' + balanceWords(d.nob) + '.'; }).join(' ');
  }
  function drawDebt(result) {
    var svg = $('debt-chart'); resetSvg(svg);
    var s = current.series, ys = result.years;
    var pub = [s.net_debt[0]].concat(ys.map(function (d) { return d.published.netDebt; }));
    var scn = [s.net_debt[0]].concat(ys.map(function (d) { return d.netDebt; }));
    var all = pub.concat(scn);
    var lo = Math.min.apply(null, all), hi = Math.max.apply(null, all);
    var span = Math.max(hi - lo, Math.abs(hi) * 0.1, 1);
    lo = Math.min(lo - span * 0.15, lo < 0 ? lo : Math.max(0, lo - span * 0.6)); hi = hi + span * 0.15;
    if (lo > 0 && lo < span * 0.6) lo = 0;
    var f = frame(svg), top = f.top, bottom = f.bottom, x0 = f.x0, x1 = f.x1;
    var y = function (v) { return bottom - (v - lo) / (hi - lo) * (bottom - top); };
    axis(svg, lo, hi, y, x0, x1);
    var x = function (i) { return x0 + 14 + i * (x1 - x0 - 28) / (pub.length - 1); };
    function path(series) { return series.map(function (v, i) { return (i ? 'L' : 'M') + x(i).toFixed(1) + ' ' + y(v).toFixed(1); }).join(' '); }
    svg.appendChild(el('path', { d: path(pub), 'class': 'l-pub' }));
    svg.appendChild(el('path', { d: path(scn), 'class': 'l-scn' }));
    scn.forEach(function (v, i) { svg.appendChild(el('circle', { cx: x(i), cy: y(v), r: 3.5, 'class': 'p-scn' })); });
    pub.forEach(function (v, i) { svg.appendChild(el('text', { x: x(i), y: bottom + 26, 'text-anchor': i === pub.length - 1 ? 'end' : i === 0 ? 'start' : 'middle', 'class': 'c-tick' }, (f.w < 480 ? '' : 'Jun ') + (2026 + i))); });
    var last = scn.length - 1;
    svg.appendChild(el('text', { x: x(last) - 6, y: y(scn[last]) - 10, 'text-anchor': 'end', 'class': 'c-label' }, money(scn[last])));
    $('debt-chart-desc').textContent = pub.map(function (v, i) { return 'June ' + (2026 + i) + ': published ' + money(v) + ', scenario ' + money(scn[i]) + '.'; }).join(' ');
  }

  /* ---------- Drivers ---------- */
  var DRIVER_LABELS = [
    ['gst', 'GST'], ['otherGrants', 'Other grants'], ['payroll', 'Payroll tax'], ['duty', 'Stamp duty'], ['royalties', 'Royalties'],
    ['wages', 'Extra wages'], ['other', 'Other running costs'], ['interest', 'Extra interest']
  ];
  function drawDrivers(last) {
    var vals = {
      gst: last.revenueParts.gst, otherGrants: last.revenueParts.otherGrants, payroll: last.revenueParts.payroll,
      duty: last.revenueParts.duty, royalties: last.revenueParts.royalties,
      wages: -last.wageCost, other: -last.otherCost, interest: -last.interestChange
    };
    var box = $('drivers'); box.replaceChildren();
    var max = Math.max.apply(null, DRIVER_LABELS.map(function (d) { return Math.abs(vals[d[0]]); }));
    var shown = DRIVER_LABELS.filter(function (d) { return Math.abs(vals[d[0]]) >= 0.05; });
    if (!shown.length) {
      var p = document.createElement('p'); p.className = 'empty-note'; p.textContent = 'No shocks yet. Choose a scenario or move a slider.'; box.appendChild(p); return;
    }
    shown.forEach(function (d) {
      var v = vals[d[0]];
      var row = document.createElement('div'); row.className = 'driver';
      var name = document.createElement('span'); name.textContent = d[1];
      var track = document.createElement('div'); track.className = 'driver-track'; track.setAttribute('aria-hidden', 'true');
      var fill = document.createElement('i'); fill.className = v < 0 ? 'neg' : 'pos';
      var w = Math.abs(v) / max * 50;
      fill.style.width = w + '%'; fill.style.left = v < 0 ? (50 - w) + '%' : '50%';
      track.appendChild(fill);
      var amount = document.createElement('strong'); amount.textContent = signedMoney(v);
      row.append(name, track, amount); box.appendChild(row);
    });
    var total = document.createElement('div'); total.className = 'driver total';
    var tn = document.createElement('span'); tn.textContent = 'Total change';
    var spacer = document.createElement('div');
    var ta = document.createElement('strong'); ta.textContent = signedMoney(last.balanceChange);
    total.append(tn, spacer, ta); box.appendChild(total);
  }

  /* ---------- Main update ---------- */
  var lastResult = null;
  function update() {
    Object.keys(CONTROLS).forEach(showValue);
    var a = assumptions();
    var p = activePreset();
    document.querySelectorAll('.preset').forEach(function (b) {
      var on = !!p && b.dataset.id === p.id;
      b.classList.toggle('on', on); b.setAttribute('aria-pressed', on ? 'true' : 'false');
    });
    $('preset-desc').textContent = p ? presetDesc(p, current.id) : 'Your own scenario. Every slider goes both ways; the Good year, Bad year and Worst buttons under each one size it from history.';
    if ($('bar-scn')) $('bar-scn').textContent = p ? p.name : 'Your own scenario';
    var r;
    try { r = M.scenario(current.series, a); } catch (e) { r = null; }
    if (!r) {
      $('verdict').textContent = 'The figures needed for this scenario are not available for ' + current.name + '.';
      return;
    }
    lastResult = r;
    var last = r.years[3];
    var pub = last.published;
    $('r-nob').textContent = money(last.nob);
    $('r-nob').classList.toggle('negative', last.nob < 0);
    var same = function (d) { return Math.abs(d) < 1e-9; };
    var asPub = 'Same as the published budget';
    $('r-nob-change').textContent = same(Math.round(last.balanceChange * 10)) ? asPub : signedMoney(last.balanceChange) + ' against a ' + balanceWords(pub.nob) + ' published';
    $('r-debt').textContent = money(last.netDebt);
    $('r-debt-change').textContent = same(Math.round(last.extraDebt * 10)) ? asPub : signedMoney(last.extraDebt) + ' against ' + money(pub.netDebt) + ' published';
    $('r-ratio').textContent = pct(last.debtToRevenue, 0);
    var dr = last.debtToRevenue - pub.debtToRevenue, ir = last.interestToRevenue - pub.interestToRevenue;
    $('r-ratio-change').textContent = Math.abs(dr) < 0.0005 ? asPub : signedPts(dr) + ' against ' + pct(pub.debtToRevenue, 0) + ' published';
    $('r-int').textContent = pct(last.interestToRevenue);
    $('r-int-change').textContent = Math.abs(ir) < 0.0005 ? asPub : signedPts(ir) + ' against ' + pct(pub.interestToRevenue) + ' published';
    if ($('bar-out')) {
      $('bar-out').replaceChildren();
      var lab = document.createElement('span'); lab.className = 'bar-lab'; lab.textContent = '2029-30 operating balance ';
      var val = document.createElement('strong'); val.textContent = balanceWords(last.nob); val.classList.toggle('negative', last.nob < 0);
      var chg = document.createElement('span'); chg.className = 'bar-chg';
      chg.textContent = same(Math.round(last.balanceChange * 10)) ? ' as published' : ' (' + signedMoney(last.balanceChange) + ')';
      $('bar-out').append(lab, val, chg);
    }
    // Plain-English verdict
    var name = current.short === 'ACT' || current.short === 'NT' ? 'the ' + current.short : current.name;
    var any = Math.abs(last.balanceChange) >= 0.05 || Math.abs(last.extraDebt) >= 0.05;
    var v;
    if (!any) {
      v = 'With no shocks, these are ' + (current.kind === 'territory' ? 'the territory’s' : 'the state’s') + ' own figures: a ' + balanceWords(pub.nob) + ' in 2029-30 and net debt of ' + money(pub.netDebt) + ' by June 2030. Choose a scenario or move a slider.';
    } else {
      var worse = last.balanceChange < 0;
      v = 'Under this scenario, ' + name + '’s 2029-30 operating balance would be ' + money(Math.abs(last.balanceChange)) + (worse ? ' weaker' : ' stronger') +
        ': a ' + balanceWords(last.nob) + ' instead of a ' + balanceWords(pub.nob) + '. ';
      if (pub.nob >= 0 && last.nob < 0) v += 'The planned surplus turns into a deficit. ';
      if (pub.nob < 0 && last.nob >= 0) v += 'The planned deficit becomes a surplus. ';
      v += 'Net debt would be ' + money(Math.abs(last.extraDebt)) + (last.extraDebt >= 0 ? ' higher' : ' lower') + ' by June 2030, at ' + pct(last.debtToRevenue, 0) + ' of revenue.';
    }
    $('verdict').textContent = v;
    drawNob(r); drawDebt(r); drawDrivers(last);
    redraw = function () { if (lastResult) { drawNob(lastResult); drawDebt(lastResult); } };
    // Table
    var tb = $('year-rows'); tb.replaceChildren();
    r.years.forEach(function (y) {
      var tr = document.createElement('tr');
      var th = document.createElement('th'); th.scope = 'row'; th.textContent = YEARS[y.index]; tr.appendChild(th);
      [y.revenueChange, -(y.wageCost + y.otherCost), -y.interestChange, y.published.nob, y.nob, y.published.netDebt, y.netDebt].forEach(function (x) {
        var td = document.createElement('td'); td.textContent = x.toLocaleString('en-AU', { minimumFractionDigits: 1, maximumFractionDigits: 1 }); tr.appendChild(td);
      });
      tb.appendChild(tr);
    });
    compareAll(a);
    renderChecks();
  }

  /* ---------- Compare all eight ---------- */
  function compareAll(a) {
    var rows = data.jurisdictions.map(function (j) {
      var r = M.scenario(j.series, a);
      if (!r) return { j: j, missing: true };
      var y = r.years[3];
      return { j: j, change: y.balanceChange, share: y.balanceChange / j.series.revenue[4], nob: y.nob, debt: y.debtToRevenue, int: y.interestToRevenue };
    });
    rows.sort(function (x, y) { return (x.missing ? 1 : 0) - (y.missing ? 1 : 0) || x.share - y.share || x.j.name.localeCompare(y.j.name); });
    var max = Math.max(0.001, Math.max.apply(null, rows.filter(function (r) { return !r.missing; }).map(function (r) { return Math.abs(r.share); })));
    var chart = $('compare-chart'); chart.replaceChildren();
    var tb = $('compare-rows'); tb.replaceChildren();
    rows.forEach(function (r) {
      var line = document.createElement('button'); line.type = 'button'; line.className = 'cmp' + (r.j.id === current.id ? ' on' : '');
      line.setAttribute('aria-label', r.j.name + ': ' + (r.missing ? 'not available' : pct(r.share) + ' of revenue') + '. Switch to ' + r.j.name);
      var nm = document.createElement('span'); nm.className = 'cmp-name'; nm.textContent = r.j.short;
      var tr0 = document.createElement('span'); tr0.className = 'cmp-track'; tr0.setAttribute('aria-hidden', 'true');
      var fill = document.createElement('i');
      if (!r.missing) {
        var w = Math.abs(r.share) / max * 50;
        fill.className = r.share < 0 ? 'neg' : 'pos'; fill.style.width = w + '%'; fill.style.left = r.share < 0 ? (50 - w) + '%' : '50%';
      }
      tr0.appendChild(fill);
      var val = document.createElement('span'); val.className = 'cmp-val';
      val.textContent = r.missing ? 'n/a' : (r.share > 0.00005 ? '+' : r.share < -0.00005 ? MINUS : '') + Math.abs(r.share * 100).toFixed(1) + '%';
      line.append(nm, tr0, val);
      line.addEventListener('click', function () { choose(r.j.id, true); document.getElementById('pick-title').scrollIntoView({ behavior: 'smooth', block: 'start' }); });
      chart.appendChild(line);
      var tr = document.createElement('tr'); if (r.j.id === current.id) tr.className = 'on';
      var th = document.createElement('th'); th.scope = 'row'; th.textContent = r.j.name; tr.appendChild(th);
      (r.missing ? ['Not available', '', '', '', ''] : [signedMoney(r.change), (r.share >= 0 ? '' : MINUS) + Math.abs(r.share * 100).toFixed(1) + '%', balanceWords(r.nob), pct(r.debt, 0), pct(r.int)]).forEach(function (x) {
        var td = document.createElement('td'); td.textContent = x; tr.appendChild(td);
      });
      tb.appendChild(tr);
    });
  }

  /* ---------- Presets, reset, URL, download ---------- */
  var presetBox = $('presets');
  function applyPreset(p, sync) {
    var keep = { borrowingRate: +$('s-borrowingRate').value, repricing: +$('s-repricing').value };
    setControls(Object.assign({}, presetValues(p, current.id), keep));
    if (sync !== false) { update(); syncUrl(); }
  }
  PRESETS.forEach(function (p) {
    var b = document.createElement('button'); b.type = 'button'; b.className = 'preset'; b.dataset.id = p.id; b.textContent = p.name;
    b.setAttribute('aria-pressed', 'false');
    if (p.level) { var tag = document.createElement('span'); tag.className = 'hk ' + (p.level === 'worst' ? 'hk-worst' : 'hk-bad'); tag.textContent = p.level === 'worst' ? 'Worst' : 'Bad year'; tag.setAttribute('aria-hidden', 'true'); b.appendChild(tag); }
    b.addEventListener('click', function () { applyPreset(p); });
    presetBox.appendChild(b);
  });

  /* History buttons under each slider: one tap sets a bad year or the worst on record. */
  function renderHistory() {
    document.querySelectorAll('.hist').forEach(function (box) {
      var k = box.dataset.for, m = histOf(k, current.id);
      box.replaceChildren();
      if (!m) {
        if (k === 'royalties') { var none = document.createElement('span'); none.className = 'hist-none'; none.textContent = shortName(current) === 'the ACT' ? 'The ACT collects no mining royalties.' : 'No usable history.'; box.appendChild(none); }
        return;
      }
      var label = document.createElement('span'); label.className = 'hist-label';
      label.textContent = (k === 'gst' ? 'National GST, ' : k === 'rateShock' ? '10-year bond yield, ' : current.short + ', ') + m.years[0] + ' to ' + m.years[1] + ':';
      box.appendChild(label);
      [['good_year', 'Good year', 'hk-good'], ['bad_year', 'Bad year', 'hk-bad'], ['worst', 'Worst', 'hk-worst']].forEach(function (lv) {
        var v = sizeOf(k, m, lv[0]);
        var btn = document.createElement('button'); btn.type = 'button'; btn.className = 'hist-btn ' + lv[2];
        var unit = m.unit === 'rate' ? ' pts' : '%';
        btn.textContent = lv[1] + ' ' + (v > 0 ? '+' : v < 0 ? MINUS : '') + Math.abs(m.unit === 'rate' ? v : v).toFixed(m.unit === 'rate' ? 1 : 0) + unit + (lv[0] === 'worst' ? ' (' + m.worst_year + ')' : '');
        btn.setAttribute('aria-label', 'Set ' + HIST_NAMES[k] + ' to ' + btn.textContent);
        btn.addEventListener('click', function () { var input = $('s-' + k); input.value = v; update(); syncUrl(); });
        box.appendChild(btn);
      });
    });
    // Disable presets that do not apply to this government (e.g. royalties in the ACT).
    document.querySelectorAll('.preset').forEach(function (b) {
      var p = PRESETS.filter(function (x) { return x.id === b.dataset.id; })[0];
      var ok = presetAvailable(p, current.id); b.disabled = !ok; b.title = ok ? '' : 'Not available for ' + shortName(current);
    });
    renderEvidence();
  }

  function renderEvidence() {
    if (!HIST || !$('ev-rows')) return;
    $('ev-name').textContent = current.name;
    var tb = $('ev-rows'); tb.replaceChildren();
    [['gst', 'GST (national pool)'], ['payroll', 'Payroll tax'], ['duty', 'Property stamp duty'], ['royalties', 'Mining royalties'], ['wages', 'Extra public sector pay growth'], ['rateShock', 'Interest rate rise (10-year yield)']].forEach(function (r) {
      var m = histOf(r[0], current.id);
      var tr = document.createElement('tr');
      var th = document.createElement('th'); th.scope = 'row'; th.textContent = r[1]; tr.appendChild(th);
      var cells = m ? [sizeText(r[0], sizeOf(r[0], m, 'good_year')), sizeText(r[0], sizeOf(r[0], m, 'bad_year')), sizeText(r[0], sizeOf(r[0], m, 'worst')), m.worst_year, m.years[0] + ' to ' + m.years[1] + ' (' + m.observations + ' changes)', m.source]
        : ['Not applicable', '', '', '', '', r[0] === 'royalties' ? 'No mining royalties in this budget' : ''];
      cells.forEach(function (c, i) { var td = document.createElement('td'); td.textContent = c; if (i === 5) td.className = 'src-cell'; tr.appendChild(td); });
      tb.appendChild(tr);
    });
  }

  function renderChecks() {
    if (!HIST || !HIST.sensitivities || !$('check-rows')) return;
    var tb = $('check-rows'); tb.replaceChildren();
    var base = assumptions(), sources = {};
    HIST.sensitivities.rows.forEach(function (row) {
      var j = byId[row.jurisdiction];
      var a = { borrowingRate: base.borrowingRate, repricing: base.repricing };
      Object.keys(row.tool).forEach(function (k) { a[k] = row.tool[k]; });
      var r = M.scenario(j.series, a);
      var tr = document.createElement('tr');
      var th = document.createElement('th'); th.scope = 'row'; th.textContent = j.short + ': ' + row.label; tr.appendChild(th);
      var fmt = function (v) { return (v < 0 ? MINUS : '') + Math.abs(Math.round(v)).toLocaleString('en-AU'); };
      [row.published[0], r.years[0].balanceChange, row.published[3], r.years[3].balanceChange].forEach(function (v, i) {
        var td = document.createElement('td'); td.textContent = fmt(v); if (i % 2) td.className = 'tool-cell'; tr.appendChild(td);
      });
      tb.appendChild(tr);
      sources[row.source] = 1;
    });
    $('check-sources').textContent = 'Sources: ' + Object.keys(sources).join('; ') + '. Tool figures use the borrowing assumptions currently set.';
  }

  Object.keys(CONTROLS).forEach(function (k) {
    var input = $('s-' + k), box = $('n-' + k);
    input.addEventListener('input', function () { update(); });
    input.addEventListener('change', syncUrl);
    if (box) {
      box.min = input.min; box.max = input.max; box.step = input.step;
      box.addEventListener('input', function () { fromBox(k, false); });
      box.addEventListener('change', function () { fromBox(k, true); });
      box.addEventListener('keydown', function (e) { if (e.key === 'Enter') { e.preventDefault(); fromBox(k, true); box.blur(); } });
    }
    // A labelled scale under the slider: where the budget sits, and which way is which.
    if (SCALE_WORDS[k]) {
      var lo = +input.min, hi = +input.max, zero = (0 - lo) / (hi - lo) * 100;
      var sc = document.createElement('div'); sc.className = 'scale'; sc.setAttribute('aria-hidden', 'true');
      var l = document.createElement('span'); l.className = 'sc-l'; l.textContent = '\u2190 ' + SCALE_WORDS[k][0];
      var r = document.createElement('span'); r.className = 'sc-r'; r.textContent = SCALE_WORDS[k][1] + ' \u2192';
      var z = document.createElement('i'); z.className = 'sc-zero'; z.style.left = zero + '%';
      var zt = document.createElement('span'); zt.className = 'sc-zt'; zt.textContent = 'Budget'; zt.style.left = zero + '%';
      sc.append(z, zt, l, r);
      input.insertAdjacentElement('afterend', sc);
    }
  });
  $('reset').addEventListener('click', function () { setControls({}); update(); syncUrl(); });

  function syncUrl() {
    try {
      var url = new URL(location.href);
      url.search = '';
      url.searchParams.set('j', current.id);
      Object.keys(CONTROLS).forEach(function (k) {
        var v = +$('s-' + k).value;
        if (Math.abs(v - defaultsUi[k]) > 1e-9) url.searchParams.set(k, String(v));
      });
      history.replaceState(null, '', url);
    } catch (e) { /* history unavailable: the tool still works */ }
  }
  $('share').addEventListener('click', function () {
    syncUrl();
    var msg = $('share-status');
    var done = function (ok) { msg.textContent = ok ? 'Link copied.' : 'Copy the address in your browser bar to share this scenario.'; setTimeout(function () { msg.textContent = ''; }, 4000); };
    if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(location.href).then(function () { done(true); }, function () { done(false); });
    else done(false);
  });

  $('download').addEventListener('click', function () {
    if (!lastResult) return;
    var a = lastResult.assumptions;
    var header = ['jurisdiction', 'financial_year', 'gst_change', 'other_grants_change', 'payroll_tax_change', 'stamp_duty_change', 'royalties_change',
      'extra_wage_growth', 'other_running_costs_change', 'infrastructure_change', 'interest_rate_shock', 'borrowing_rate', 'debt_refinanced_per_year',
      'revenue_change_aud_m', 'extra_wages_aud_m', 'extra_running_costs_aud_m', 'extra_interest_aud_m', 'extra_infrastructure_aud_m',
      'operating_balance_published_aud_m', 'operating_balance_scenario_aud_m', 'net_debt_published_aud_m', 'net_debt_scenario_aud_m', 'basis'];
    var rows = lastResult.years.map(function (y) {
      return [current.name, YEARS[y.index], a.gst, a.otherGrants, a.payroll, a.duty, a.royalties, a.wages, a.otherSpending, a.capex, a.rateShock, a.borrowingRate, a.repricing,
        y.revenueChange, y.wageCost, y.otherCost, y.interestChange, y.capexChange, y.published.nob, y.nob, y.published.netDebt, y.netDebt,
        'Scenario applied to the published 2026-27 budget, general government sector. Not a forecast.'];
    });
    var csv = [header].concat(rows).map(function (r) {
      return r.map(function (v) { return typeof v === 'number' ? String(Math.round(v * 1000) / 1000) : '"' + String(v).replace(/"/g, '""') + '"'; }).join(',');
    }).join('\r\n');
    var url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }));
    var link = document.createElement('a'); link.href = url; link.download = 'state-budget-scenario-' + current.id + '.csv';
    document.body.appendChild(link); link.click(); link.remove();
    setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
  });

  /* ---------- Sources ---------- */
  var ITEM_NAMES = {
    revenue: 'Total revenue', taxation: 'Taxation', payroll_tax: 'Payroll tax', transfer_duty: 'Property stamp duty', grants: 'Grants', gst: 'GST',
    royalties: 'Royalties', expenses: 'Total expenses', employee: 'Employee and superannuation expenses', interest: 'Interest expense',
    nob: 'Net operating balance', capex: 'Purchases of non-financial assets', net_debt: 'Net debt'
  };
  var list = $('source-list');
  data.jurisdictions.forEach(function (j) {
    var d = document.createElement('details'); d.className = 'source';
    var s = document.createElement('summary');
    var strong = document.createElement('strong'); strong.textContent = j.name;
    var small = document.createElement('span'); small.textContent = j.document.title;
    s.append(strong, small); d.appendChild(s);
    var p = document.createElement('p');
    var link = document.createElement('a'); link.href = j.document.url; link.target = '_blank'; link.rel = 'noopener'; link.textContent = 'Open the budget paper ↗';
    p.appendChild(link);
    if (j.document.sha256) {
      var code = document.createElement('span'); code.className = 'hash'; code.textContent = ' SHA-256 of the file used: ' + j.document.sha256;
      p.appendChild(code);
    }
    d.appendChild(p);
    var ul = document.createElement('ul');
    Object.keys(ITEM_NAMES).forEach(function (k) {
      var src = j.sources[k]; if (!src) return;
      var li = document.createElement('li');
      var b = document.createElement('b'); b.textContent = ITEM_NAMES[k] + ': ';
      var where = src.components ? src.components : src.table + (src.pdf_page ? ' (PDF page ' + src.pdf_page + (src.file ? ', ' + (src.file.indexOf('bp5') > -1 ? 'BP5' : 'BP2') : '') + ')' : '');
      li.append(b, document.createTextNode(where + (src.note ? ' ' + src.note : '')));
      ul.appendChild(li);
    });
    d.appendChild(ul);
    list.appendChild(d);
  });

  /* ---------- Sticky summary bar: appears once the government picker scrolls away ---------- */
  var bar = $('sb-bar'), barJur = $('bar-jur');
  if (bar && barJur) {
    data.jurisdictions.forEach(function (j) { var o = document.createElement('option'); o.value = j.id; o.textContent = j.name; barJur.appendChild(o); });
    barJur.addEventListener('change', function () { choose(barJur.value, true); });
    var setBarH = function () { document.documentElement.style.setProperty('--bar-h', bar.hidden ? '0px' : bar.offsetHeight + 'px'); };
    // Show the bar once the government picker has scrolled up under the site header.
    var pick = $('tool-start'), ticking = false;
    var checkBar = function () {
      ticking = false;
      var hdr = document.querySelector('.site-header');
      var limit = hdr ? hdr.getBoundingClientRect().bottom : 64;
      var show = pick.getBoundingClientRect().bottom < limit;
      if (bar.hidden === show) { bar.hidden = !show; setBarH(); }
    };
    window.addEventListener('scroll', function () { if (!ticking) { ticking = true; requestAnimationFrame(checkBar); } }, { passive: true });
    checkBar();
    window.addEventListener('resize', setBarH);
  }

  /* ---------- Start ---------- */
  var params = new URLSearchParams(location.search);
  var start = {};
  Object.keys(CONTROLS).forEach(function (k) {
    if (!params.has(k)) return;
    var v = Number(params.get(k));
    if (isFinite(v)) start[k] = v;
  });
  setControls(start);
  $('tool').hidden = false;
  choose(byId[params.get('j')] ? params.get('j') : 'nsw', false);
})();
