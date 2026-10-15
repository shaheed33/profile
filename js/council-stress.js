(function () {
  'use strict';
  const $ = id => document.getElementById(id);
  const data = window.COUNCIL_STRESS;
  const valid = value => typeof value === 'number' && Number.isFinite(value);
  const money = value => valid(value) ? `${value < 0 ? '−' : ''}$${(Math.abs(value) / 1e6).toLocaleString('en-AU', {maximumFractionDigits: 1, minimumFractionDigits: 1})}m` : 'Not reported';
  const pct = value => valid(value) ? `${(value * 100).toFixed(1)}%` : 'Not collected / reported';
  const fy = end => `${end - 1}–${String(end).slice(-2)}`;
  const number = value => value.toLocaleString('en-AU', {maximumFractionDigits: 1});
  $('year').textContent = new Date().getFullYear();
  if (!data || !Array.isArray(data.councils) || !data.councils.length || !window.CouncilStressMath) {
    $('load-error').hidden = false;
    $('load-error').textContent = 'Council data could not be loaded. Reload the page, or use the downloadable panel below.';
    return;
  }
  let council, base, result;
  const ids = ['grant-cut', 'wage-growth', 'renewal-share', 'payroll-share', 'horizon'];

  function cell(row, value, header = false) {
    const c = document.createElement(header ? 'th' : 'td');
    c.textContent = value;
    if (header) c.scope = 'row';
    row.appendChild(c);
    return c;
  }

  function selectCouncil() {
    council = data.councils.find(c => c.name === $('council').value);
    base = council.history.find(r => r.year === data.meta.latest_year);
    $('council-name').textContent = council.name;
    $('council-context').textContent = `${council.group} · ${valid(base.population) ? number(base.population) + ' residents (OLG population field)' : 'Population not reported'}`;
    $('base-revenue').textContent = money(base.revenue);
    $('base-expenses').textContent = money(base.expenses);
    $('base-grants').textContent = pct(base.grant_share);
    document.querySelectorAll('.base-year').forEach(el => { el.textContent = `${fy(base.year)} · reported base`; });
    const tbody = $('history-rows');
    tbody.replaceChildren();
    council.history.forEach(r => {
      const tr = document.createElement('tr');
      cell(tr, fy(r.year), true);
      cell(tr, pct(r.operating_ratio));
      cell(tr, valid(r.liquidity) ? r.liquidity.toFixed(2) : 'Not collected / reported');
      cell(tr, valid(r.cash_cover) ? `${r.cash_cover.toFixed(1)} months` : 'Not collected / reported');
      cell(tr, pct(r.renewal_ratio));
      tbody.appendChild(tr);
    });
    const cash = council.history.filter(r => valid(r.cash_cover)).at(-1);
    $('liquidity-note').textContent = cash ? `Latest reported cash expense cover: ${cash.cash_cover.toFixed(1)} months in ${fy(cash.year)}. This is historical context; it cannot establish the council’s current cash position or fund the scenario automatically.` : 'No reported cash expense cover is available in these files. A liquidity forecast cannot be calculated.';
    const url = new URL(location.href);
    url.searchParams.set('council', council.name);
    history.replaceState(null, '', url);
    update();
  }

  function assumptions() {
    return {grantCut: +$('grant-cut').value / 100, wageGrowth: +$('wage-growth').value / 100,
      payrollShare: +$('payroll-share').value / 100, renewalShare: +$('renewal-share').value / 100,
      years: +$('horizon').value};
  }

  function svg(tag, attributes, text) {
    const el = document.createElementNS('http://www.w3.org/2000/svg', tag);
    Object.entries(attributes).forEach(([k, v]) => el.setAttribute(k, v));
    if (text !== undefined) el.textContent = text;
    return el;
  }

  function chart(path) {
    const chart = $('scenario-chart');
    chart.replaceChildren(svg('title', {id: 'chart-title'}, 'Revenue less expenses under your scenario'),
      svg('desc', {id: 'chart-desc'}, path.map(p => `${fy(p.year)}: base ${money(p.baseline)}; scenario ${money(p.balance)}.`).join(' ')));
    const values = path.flatMap(p => [p.baseline / 1e6, p.balance / 1e6]);
    const lo = Math.min(0, ...values), hi = Math.max(0, ...values);
    const padding = Math.max((hi - lo) * .15, 1);
    const min = lo - padding, max = hi + padding;
    const y = value => 195 - (value - min) / (max - min) * 170;
    const y0 = y(0);
    [lo, (lo + hi) / 2, hi].filter((v, i, a) => a.indexOf(v) === i).forEach(value => {
      chart.appendChild(svg('line', {x1: 65, x2: 625, y1: y(value), y2: y(value), class: 'chart-grid'}));
      chart.appendChild(svg('text', {x: 55, y: y(value) + 4, 'text-anchor': 'end'}, `$${number(value)}m`));
    });
    chart.appendChild(svg('line', {x1: 65, x2: 625, y1: y0, y2: y0, class: 'chart-zero'}));
    path.forEach((p, i) => {
      const center = 65 + (i + .5) * 560 / path.length;
      [[p.baseline, -34, '#bbc6cf'], [p.balance, 2, '#397a67']].forEach(([value, offset, fill]) => {
        const top = y(value / 1e6);
        chart.appendChild(svg('rect', {x: center + offset, y: Math.min(top, y0), width: 30,
          height: Math.max(Math.abs(y0 - top), 1), fill, rx: 2}));
      });
      chart.appendChild(svg('text', {x: center, y: 226, 'text-anchor': 'middle'}, fy(p.year)));
    });
  }

  function update() {
    [['grant-cut', 'grant-value'], ['wage-growth', 'wage-value'], ['renewal-share', 'renewal-value'], ['payroll-share', 'payroll-value']]
      .forEach(([input, output]) => { $(output).textContent = `${$(input).value}%`; });
    result = window.CouncilStressMath.scenario(base, assumptions());
    $('missing-data').hidden = !!result;
    $('results').hidden = !result;
    $('scenario-inputs').disabled = !result;
    if (!result) return;
    const last = result.path.at(-1);
    $('balance-label').textContent = `${fy(last.year)} revenue less expenses`;
    $('scenario-balance').textContent = money(last.balance);
    $('scenario-balance').classList.toggle('negative', last.balance < 0);
    const delta = last.balance - result.baseline;
    $('balance-change').textContent = `${money(Math.abs(delta))} ${delta < 0 ? 'lower than' : delta > 0 ? 'higher than' : 'change from'} unchanged base`;
    $('funding-pressure').textContent = money(last.cumulativePressure);
    $('pressure-period').textContent = `Cumulative over ${result.path.length} years, including extra capital renewal`;
    chart(result.path);
    $('drivers').replaceChildren();
    const drivers = [['Grants lost', last.grantLoss], ['Extra wages', last.wageCost], ['Extra renewal', last.extraRenewal]];
    const largest = Math.max(1, ...drivers.map(d => d[1]));
    drivers.forEach(([name, value]) => {
      const row = document.createElement('div'); row.className = 'driver';
      const label = document.createElement('span'); label.textContent = name;
      const track = document.createElement('div'); track.className = 'driver-track'; track.setAttribute('aria-hidden', 'true');
      const fill = document.createElement('div'); fill.className = 'driver-fill'; fill.style.width = `${value / largest * 100}%`; track.appendChild(fill);
      const amount = document.createElement('strong'); amount.textContent = money(value);
      row.append(label, track, amount); $('drivers').appendChild(row);
    });
    $('scenario-rows').replaceChildren();
    result.path.forEach(r => {
      const tr = document.createElement('tr');
      cell(tr, fy(r.year), true);
      [r.baseline, r.balance, r.extraRenewal, r.fundingPressure].forEach(v => cell(tr, (v / 1e6).toFixed(3)));
      $('scenario-rows').appendChild(tr);
    });
  }

  data.councils.forEach(c => {
    const option = document.createElement('option'); option.value = c.name; option.textContent = c.name;
    $('council').appendChild(option);
  });
  $('council').options[0].remove();
  const requested = new URLSearchParams(location.search).get('council');
  $('council').value = data.councils.some(c => c.name === requested) ? requested : data.councils.some(c => c.name === 'Kiama') ? 'Kiama' : data.councils[0].name;
  $('council').disabled = false;
  $('tool').hidden = false;
  $('council').addEventListener('change', selectCouncil);
  ids.forEach(id => $(id).addEventListener('input', update));
  $('reset').addEventListener('click', () => {
    ['grant-cut', 'wage-growth', 'renewal-share'].forEach(id => { $(id).value = 0; }); update();
  });
  $('download').addEventListener('click', () => {
    if (!result) return;
    const header = ['council', 'base_year', 'scenario_year', 'grant_cut', 'annual_wage_growth', 'assumed_payroll_share', 'extra_renewal_share', 'base_revenue_aud', 'base_expenses_aud', 'base_grant_share', 'baseline_balance_aud', 'scenario_balance_aud', 'grant_loss_aud', 'extra_wages_aud', 'extra_renewal_aud', 'additional_funding_pressure_aud', 'cumulative_pressure_aud', 'interpretation'];
    const a = result.assumptions;
    const rows = result.path.map(r => [council.name, base.year, r.year, a.grantCut, a.wageGrowth, a.payrollShare, a.renewalShare,
      base.revenue, base.expenses, base.grant_share, r.baseline, r.balance, r.grantLoss, r.wageCost, r.extraRenewal, r.fundingPressure, r.cumulativePressure, 'Conditional flat-base accounting sensitivity; not a forecast, cash balance or OLG operating ratio']);
    const csv = [header, ...rows].map(r => r.map(v => `"${String(v).replaceAll('"', '""')}"`).join(',')).join('\r\n');
    const url = URL.createObjectURL(new Blob([csv], {type: 'text/csv;charset=utf-8'}));
    const link = document.createElement('a'); link.href = url; link.download = `council-stress-${council.name.toLowerCase().replace(/[^a-z0-9]+/g, '-')}.csv`;
    document.body.appendChild(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
  data.meta.sources.forEach(source => {
    const c = document.createElement('div'); c.className = 'coverage-cell';
    const title = document.createElement('strong'); title.textContent = fy(source.year);
    const label = document.createElement('span');
    const reported = source.councils - source.missing.operating_ratio;
    label.textContent = `${reported} / ${source.councils} operating ratios reported`;
    const track = document.createElement('div'); track.className = 'coverage-bar';
    const fill = document.createElement('i'); fill.style.width = `${reported / source.councils * 100}%`; track.appendChild(fill);
    c.append(title, label, track); $('coverage').appendChild(c);
  });
  data.models.forEach(model => {
    const tr = document.createElement('tr');
    cell(tr, `${model.horizon} years`, true); cell(tr, model.pairs); cell(tr, model.folds.length);
    cell(tr, model.status === 'insufficient_history' ? 'Insufficient history' : 'Retrospective research only');
    $('model-rows').appendChild(tr);
  });
  selectCouncil();
})();
