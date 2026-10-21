// Report view: a dashboard of the current game over a window of recent steps.
// Shares globals with app.js (api, state, $, RESOURCES, GOODS, cap, cssVar).

const reportUi = {
  simView: $("sim-view"),
  reportView: $("report-view"),
  viewButtons: document.querySelectorAll(".view-switch button"),
  windowButtons: document.querySelectorAll("#report-window button"),
  range: $("report-range"),
  kpis: $("report-kpis"),
};

let reportWindow = 100;
let reportVisible = false;
let reportBusy = false;
let reportLast = 0;

// Series colours: fixed categorical order (validated palette), never reassigned by rank.
const SERIES = ["var(--s1)", "var(--s2)", "var(--s3)", "var(--s4)"];

const fmt = {
  money: (v) => v.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
  num: (v, d = 2) => v.toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d }),
  pct: (v, d = 1) => `${(v * 100).toFixed(d)}%`,
  signedPct: (v) => `${v >= 0 ? "+" : ""}${(v * 100).toFixed(1)}%`,
};

// ---------- Small SVG line chart ----------

const SVG_NS = "http://www.w3.org/2000/svg";
const svgEl = (tag, attrs = {}) => {
  const el = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
  return el;
};

function niceTicks(max, count = 4) {
  if (!(max > 0)) return [0, 1];
  const raw = max / count;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map(m => m * mag).find(s => s >= raw);
  const ticks = [];
  for (let v = 0; v <= max + step * 0.001; v += step) ticks.push(+v.toPrecision(10));
  if (ticks[ticks.length - 1] < max) ticks.push(+(ticks[ticks.length - 1] + step).toPrecision(10));
  return ticks;
}

/**
 * Draw a line chart into ``host``.
 * opts: { x: [numbers], series: [{ label, values, color }], yFormat, xFormat, height,
 *         yMax (fixed top), reference: [[x, y], [x, y]] (dashed line), xLabel }
 */
function lineChart(host, opts) {
  host.innerHTML = "";
  host.classList.add("chart");
  const series = opts.series.filter(s => s.values.length);
  if (!series.length || opts.x.length < 2) {
    host.append(Object.assign(document.createElement("p"), { className: "chart-empty", textContent: "Not enough data yet." }));
    return;
  }
  if (series.length > 1) {
    const legend = document.createElement("div");
    legend.className = "legend";
    for (const s of series) {
      const item = document.createElement("span");
      const sw = Object.assign(document.createElement("i"), { className: "swatch" });
      sw.style.background = s.color;
      item.append(sw, s.label);
      legend.append(item);
    }
    host.append(legend);
  }
  const width = Math.max(260, host.clientWidth);
  const height = opts.height || 200;
  const pad = { l: 52, r: series.length <= 4 ? 78 : 16, t: 10, b: 24 };
  const xs = opts.x;
  const xMin = xs[0], xMax = xs[xs.length - 1];
  const yTop = opts.yMax ?? Math.max(...series.flatMap(s => s.values), 0);
  const ticks = opts.yMax ? [0, opts.yMax * 0.25, opts.yMax * 0.5, opts.yMax * 0.75, opts.yMax] : niceTicks(yTop);
  const yMax = ticks[ticks.length - 1] || 1;
  const X = (v) => pad.l + (xMax === xMin ? 0 : (v - xMin) / (xMax - xMin)) * (width - pad.l - pad.r);
  const Y = (v) => pad.t + (1 - v / yMax) * (height - pad.t - pad.b);
  // Axis labels share one format (decimals only when the scale is small); tooltips show two decimals.
  const yFmt = opts.yFormat || ((v) => fmt.num(v, yMax < 10 ? 2 : 0));
  const tipFmt = opts.tipFormat || opts.yFormat || ((v) => fmt.num(v, 2));
  const xFmt = opts.xFormat || ((v) => `${Math.round(v)}`);

  const svg = svgEl("svg", { viewBox: `0 0 ${width} ${height}`, width, height, role: "img",
    "aria-label": opts.title || "chart" });
  for (const t of ticks) {
    svg.append(svgEl("line", { x1: pad.l, x2: width - pad.r, y1: Y(t), y2: Y(t), class: "grid" }));
    const label = svgEl("text", { x: pad.l - 8, y: Y(t) + 4, class: "axis", "text-anchor": "end" });
    label.textContent = yFmt(t);
    svg.append(label);
  }
  const xTicks = 5;
  for (let i = 0; i <= xTicks; i++) {
    const v = xMin + (xMax - xMin) * i / xTicks;
    const label = svgEl("text", { x: X(v), y: height - 6, class: "axis", "text-anchor": i === 0 ? "start" : i === xTicks ? "end" : "middle" });
    label.textContent = xFmt(v);
    svg.append(label);
  }
  if (opts.reference) {
    const [[x1, y1], [x2, y2]] = opts.reference;
    svg.append(svgEl("line", { x1: X(x1), y1: Y(y1), x2: X(x2), y2: Y(y2), class: "reference" }));
  }
  for (const s of series) {
    const d = s.values.map((v, i) => `${i ? "L" : "M"}${X(xs[i]).toFixed(1)},${Y(v).toFixed(1)}`).join("");
    svg.append(svgEl("path", { d, class: "line", stroke: s.color }));
  }
  // Direct end labels (<= 4 series), nudged apart so they don't collide.
  if (series.length <= 4) {
    const ends = series.map(s => ({ s, y: Y(s.values[s.values.length - 1]) })).sort((a, b) => a.y - b.y);
    for (let i = 1; i < ends.length; i++) ends[i].y = Math.max(ends[i].y, ends[i - 1].y + 13);
    for (const e of ends) {
      const x = X(xs[xs.length - 1]);
      svg.append(svgEl("circle", { cx: x, cy: Y(e.s.values[e.s.values.length - 1]), r: 3, fill: e.s.color, class: "end-dot" }));
      const t = svgEl("text", { x: x + 8, y: e.y + 4, class: "end-label" });
      t.textContent = series.length > 1 ? e.s.label : yFmt(e.s.values[e.s.values.length - 1]);
      svg.append(t);
    }
  }
  // Hover: crosshair + tooltip with every series at that point.
  const cross = svgEl("line", { y1: pad.t, y2: height - pad.b, class: "crosshair", visibility: "hidden" });
  const dots = series.map(s => svgEl("circle", { r: 4, fill: s.color, class: "hover-dot", visibility: "hidden" }));
  svg.append(cross, ...dots);
  const tip = Object.assign(document.createElement("div"), { className: "tooltip" });
  tip.hidden = true;
  const hit = svgEl("rect", { x: pad.l, y: pad.t, width: width - pad.l - pad.r, height: height - pad.t - pad.b, class: "hit" });
  hit.addEventListener("mousemove", (e) => {
    const box = svg.getBoundingClientRect();
    const px = (e.clientX - box.left) * (width / box.width);
    let i = 0, best = Infinity;
    xs.forEach((x, k) => { const d = Math.abs(X(x) - px); if (d < best) { best = d; i = k; } });
    cross.setAttribute("x1", X(xs[i])); cross.setAttribute("x2", X(xs[i])); cross.setAttribute("visibility", "visible");
    series.forEach((s, k) => {
      dots[k].setAttribute("cx", X(xs[i])); dots[k].setAttribute("cy", Y(s.values[i])); dots[k].setAttribute("visibility", "visible");
    });
    tip.innerHTML = "";
    tip.append(Object.assign(document.createElement("div"), { className: "tip-title", textContent: opts.xLabel ? `${opts.xLabel} ${xFmt(xs[i])}` : xFmt(xs[i]) }));
    for (const s of series) {
      const row = document.createElement("div");
      const sw = Object.assign(document.createElement("i"), { className: "swatch" });
      sw.style.background = s.color;
      const value = Object.assign(document.createElement("b"), { textContent: tipFmt(s.values[i]) });
      row.append(sw, `${s.label} `, value);
      tip.append(row);
    }
    tip.hidden = false;
    const left = (X(xs[i]) / width) * box.width;
    tip.style.left = `${Math.min(left + 12, box.width - tip.offsetWidth - 4)}px`;
    tip.style.top = `${(e.clientY - box.top) + 10}px`;
  });
  hit.addEventListener("mouseleave", () => {
    tip.hidden = true;
    cross.setAttribute("visibility", "hidden");
    dots.forEach(d => d.setAttribute("visibility", "hidden"));
  });
  svg.append(hit);
  const wrap = Object.assign(document.createElement("div"), { className: "chart-wrap" });
  wrap.append(svg, tip);
  host.append(wrap);
}

function table(host, headers, rows) {
  host.innerHTML = "";
  const t = document.createElement("table");
  t.className = "data-table";
  const head = t.createTHead().insertRow();
  for (const h of headers) head.append(Object.assign(document.createElement("th"), { textContent: h }));
  const body = t.createTBody();
  for (const r of rows) {
    const tr = body.insertRow();
    for (const cell of r) {
      const td = tr.insertCell();
      if (cell instanceof Node) td.append(cell); else td.textContent = cell;
    }
  }
  host.append(t);
}

function swatchLabel(text, color) {
  const span = document.createElement("span");
  span.className = "swatch-label";
  const sw = Object.assign(document.createElement("i"), { className: "swatch" });
  sw.style.background = color;
  span.append(sw, text);
  return span;
}

// Trailing moving average, so per-step flows of whole units read as a rate, not spikes.
function smooth(values, w) {
  if (w <= 1) return values;
  let sum = 0;
  return values.map((v, i) => {
    sum += v;
    if (i >= w) sum -= values[i - w];
    return sum / Math.min(i + 1, w);
  });
}

// ---------- The report ----------

function kpi(label, value, note, tone = "") {
  const card = Object.assign(document.createElement("div"), { className: "kpi" });
  card.append(Object.assign(document.createElement("div"), { className: "kpi-label", textContent: label }),
              Object.assign(document.createElement("div"), { className: "kpi-value", textContent: value }));
  if (note) card.append(Object.assign(document.createElement("div"), { className: `kpi-note ${tone}`, textContent: note }));
  return card;
}

function renderReport(r) {
  const t = r.totals, c = r.current, s = r.series;
  const x = s.map(p => p.tick);
  // Flows (production, labour, trades, income) are averaged over ~5% of the window.
  const w = Math.max(1, Math.round(s.length / 20));
  const steps = s.length > 1 ? Math.round((x[x.length - 1] - x[0]) / (s.length - 1)) || 1 : 1;
  const avgNote = w > 1 ? `${w * steps}-step average` : "per step";
  const flow = (fn) => smooth(s.map(fn), w);
  for (const el of document.querySelectorAll(".avg-note")) el.textContent = avgNote;
  reportUi.range.textContent = t.steps
    ? `Steps ${t.from_tick}–${r.tick} · ${t.steps} steps${t.steps < reportWindow ? " (all recorded so far)" : ""}`
    : "No steps recorded yet: press Step or Play.";

  // Headline numbers.
  reportUi.kpis.innerHTML = "";
  const n = c.population || 1;
  reportUi.kpis.append(
    kpi("Population", `${c.population}`, t.deaths ? `${t.deaths} died in this window` : "no deaths in this window",
        t.deaths ? "bad" : "good"),
    kpi("Total wealth", fmt.money(c.wealth), `${fmt.signedPct(t.wealth_change)} over the window`,
        t.wealth_change >= 0 ? "good" : "bad"),
    kpi("Wealth per agent", fmt.money(c.wealth / n), `money ${fmt.money(c.money / n)} · assets ${fmt.money(c.asset_value / n)}`),
    kpi("Income per agent", fmt.money(t.income_per_agent_step), "per step, from sales and government"),
    kpi("Wealth inequality", c.gini_wealth.toFixed(2), `Gini · top 10% hold ${fmt.pct(c.top10_wealth)}`),
    kpi("Money inequality", c.gini_money.toFixed(2), "Gini of money held"),
    kpi("Asset concentration", c.gini_assets.toFixed(2), `Gini · ${c.owners} of ${c.population} agents own assets`),
    kpi("Government money", fmt.money(t.gov_money), `created in this window · ${fmt.num(t.labor_gov, 1)} labour bought`),
  );

  // Prices.
  lineChart($("chart-prices"), { x, xLabel: "Step", title: "Prices", tipFormat: fmt.money,
    series: RESOURCES.map((res, i) => ({ label: cap(res), color: SERIES[i], values: s.map(p => p.prices[res]) })) });
  table($("table-prices"), ["", "Now", "Min", "Avg", "Max", "Change"], RESOURCES.map((res, i) => {
    const p = r.prices[res];
    const change = Object.assign(document.createElement("span"), { className: p.change >= 0 ? "up" : "down",
      textContent: fmt.signedPct(p.change) });
    return [swatchLabel(cap(res), SERIES[i]), fmt.money(p.now), fmt.money(p.min), fmt.money(p.avg), fmt.money(p.max), change];
  }));

  // Production vs consumption, one small chart per good (same scale for fair comparison).
  const flows = Object.fromEntries(GOODS.map(g => [g, { produced: flow(p => p.produced[g]), consumed: flow(p => p.consumed[g]) }]));
  const flowMax = Math.max(1e-9, ...GOODS.flatMap(g => [...flows[g].produced, ...flows[g].consumed]));
  const flowTicks = niceTicks(flowMax);
  for (const g of GOODS) {
    lineChart($(`chart-flow-${g}`), { x, xLabel: "Step", height: 150, yMax: flowTicks[flowTicks.length - 1], title: `${g} flow`,
      series: [{ label: "Produced", color: SERIES[0], values: flows[g].produced },
               { label: "Consumed", color: SERIES[1], values: flows[g].consumed }] });
  }
  table($("table-flows"), ["Good", "Produced", "Consumed", "Net"], GOODS.map(g => {
    const net = t.produced[g] - t.consumed[g];
    const netCell = Object.assign(document.createElement("span"), { className: net >= 0 ? "up-good" : "down-bad",
      textContent: `${net >= 0 ? "+" : ""}${fmt.num(net, 0)}` });
    return [cap(g), fmt.num(t.produced[g], 0), fmt.num(t.consumed[g], 0), netCell];
  }));

  // Labour.
  lineChart($("chart-labor"), { x, xLabel: "Step", title: "Labour per step",
    series: [{ label: "Made", color: SERIES[0], values: flow(p => p.labor_made) },
             { label: "Used in production", color: SERIES[1], values: flow(p => p.labor_used) },
             { label: "Expired", color: SERIES[2], values: flow(p => p.labor_expired) },
             { label: "Bought by government", color: SERIES[3], values: flow(p => p.labor_gov) }] });
  const made = t.labor_made || 1;
  table($("table-labor"), ["Labour", "Units", "Share of made"], [
    ["Made", fmt.num(t.labor_made, 1), "100%"],
    ["Used in production", fmt.num(t.labor_used, 1), fmt.pct(t.labor_used / made)],
    ["Expired unused", fmt.num(t.labor_expired, 1), fmt.pct(t.labor_expired / made)],
    ["Bought by government", fmt.num(t.labor_gov, 1), fmt.pct(t.labor_gov / made)],
  ]);

  // Inequality.
  const gFmt = (v) => v.toFixed(2);
  lineChart($("chart-gini"), { x, xLabel: "Step", yMax: 1, yFormat: gFmt, title: "Inequality (Gini)",
    series: [{ label: "Money", color: SERIES[0], values: s.map(p => p.gini_money) },
             { label: "Assets", color: SERIES[1], values: s.map(p => p.gini_assets) },
             { label: "Wealth", color: SERIES[2], values: s.map(p => p.gini_wealth) }] });
  const lx = r.lorenz.wealth.map(p => p[0]);
  lineChart($("chart-lorenz"), { x: lx, yMax: 1, reference: [[0, 0], [1, 1]], title: "Lorenz curves",
    xFormat: (v) => fmt.pct(v, 0), yFormat: (v) => fmt.pct(v, 0), xLabel: "Poorest",
    series: [{ label: "Money", color: SERIES[0], values: r.lorenz.money.map(p => p[1]) },
             { label: "Assets", color: SERIES[1], values: r.lorenz.assets.map(p => p[1]) },
             { label: "Wealth", color: SERIES[2], values: r.lorenz.wealth.map(p => p[1]) }] });

  // Wealth and income.
  lineChart($("chart-wealth"), { x, xLabel: "Step", title: "Total wealth", tipFormat: fmt.money,
    series: [{ label: "Total wealth", color: SERIES[0], values: s.map(p => p.wealth) }] });
  lineChart($("chart-income"), { x, xLabel: "Step", title: "Income per step",
    series: [{ label: "Income per step", color: SERIES[0], values: flow(p => p.income) }] });
  table($("table-top"), ["Agent", "Wealth", "Share", "Money", "Assets"], r.top_agents.map(a =>
    [swatchLabel(a.name, a.color), fmt.money(a.wealth), fmt.pct(a.share), fmt.money(a.money), fmt.money(a.assets)]));

  // Activity.
  lineChart($("chart-trades"), { x, xLabel: "Step", title: "Trades per step",
    series: [{ label: "Goods deals", color: SERIES[0], values: flow(p => p.goods_deals) },
             { label: "Labour deals", color: SERIES[1], values: flow(p => p.labor_deals) },
             { label: "Asset trades", color: SERIES[2], values: flow(p => p.asset_trades) }] });
  lineChart($("chart-population"), { x, xLabel: "Step", title: "Population",
    yFormat: (v) => `${Math.round(v)}`,
    series: [{ label: "Population", color: SERIES[0], values: s.map(p => p.population) }] });
}

async function refreshReport(force = false) {
  if (!reportVisible || reportBusy) return;
  const now = Date.now();
  if (!force && now - reportLast < 1000) return;   // at most once a second while playing
  reportBusy = true;
  reportLast = now;
  try {
    renderReport(await api(`/api/report${reportWindow ? `?window=${reportWindow}` : ""}`));
  } catch (err) {
    console.error(err);
  } finally {
    reportBusy = false;
  }
}

function showView(name) {
  reportVisible = name === "report";
  reportUi.simView.hidden = reportVisible;
  reportUi.reportView.hidden = !reportVisible;
  for (const b of reportUi.viewButtons) b.classList.toggle("active", b.dataset.view === name);
  if (reportVisible) refreshReport(true);
  else draw();
}

for (const b of reportUi.viewButtons) b.onclick = () => showView(b.dataset.view);
for (const b of reportUi.windowButtons) {
  b.onclick = () => {
    reportWindow = Number(b.dataset.window);
    for (const o of reportUi.windowButtons) o.classList.toggle("active", o === b);
    refreshReport(true);
  };
}
window.addEventListener("resize", () => reportVisible && refreshReport(true));
