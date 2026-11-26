const canvas = document.getElementById("world");
const ctx = canvas.getContext("2d");
const $ = (id) => document.getElementById(id);
const ui = {
  tick: $("tick"),
  step: $("step"),
  play: $("play"),
  run100: $("run100"),
  interval: $("interval"),
  stepsPerTick: $("steps-per-tick"),
  intervalLabel: $("interval-label"),
  agentCount: $("agent-count"),
  pageTitle: $("page-title"), calDate: $("cal-date"),
  dashKpis: $("dash-kpis"), dashCharts: $("dash-charts"), dashAlerts: $("dash-alerts"),
  dashMovers: $("dash-movers"), dashEvents: $("dash-events"),
  seed: $("seed"),
  reset: $("reset"),
  showRange: $("show-range"),
  agents: $("agents"),
  agentShown: $("agent-shown"),
  agentSearch: $("agent-search"),
  agentFilter: $("agent-filter"),
  agentSort: $("agent-sort"),
  agentSortDir: $("agent-sort-dir"),
  market: $("market"),
  events: $("events"),
  tabs: document.querySelectorAll(".tabs button"),
  newAgent: $("new-agent"),
  chips: $("agent-chips"),
  form: $("agent-form"),
  formTitle: $("form-title"),
  formFields: $("form-fields"),
  formRemove: $("form-remove"),
  formRevert: $("form-revert"),
  formSubmit: $("form-submit"),
  formStatus: $("form-status"),
  balance: document.querySelector("#agent-form .balance"),
  govForm: $("gov-form"),
  govRate: $("gov-rate"),
  govRateRange: $("gov-rate-range"),
  govRateLabel: $("gov-rate-label"),
  govBuy: $("gov-buy"),
  govBuyRange: $("gov-buy-range"),
  govBuyLabel: $("gov-buy-label"),
  govRevert: $("gov-revert"),
  govStatus: $("gov-status"),
  govStats: $("gov-stats"),
  policyAdd: $("policy-add"),
  policyBudget: $("policy-budget"),
  policyList: $("policy-list"),
  policyStatus: $("policy-status"),
  productSearch: $("product-search"),
  productSummary: $("product-summary"), productTable: $("product-table"),
  bankForm: $("bank-form"), bankEnabled: $("bank-enabled"), bankDeposit: $("bank-deposit"),
  bankSpread: $("bank-spread"), bankReserve: $("bank-reserve"),
  govEnabled: $("gov-enabled"), govBasel: $("gov-basel"),
  bankMinCapital: $("bank-min-capital"), bankIncomeShare: $("bank-income-share"), bankRevert: $("bank-revert"), bankStatus: $("bank-status"),
  bankStats: $("bank-stats"), bankList: $("bank-list"),
};

const DOT_RADIUS = 6;
// The industry catalog and the needs come from the server (catalog.js, loaded before this file).
const CATALOG_INFO = Object.fromEntries(window.CATALOG.goods.map(e => [e.id, e]));
const NEEDS = window.CATALOG.needs;                 // hunger, sleep, thirst, boredom, health, energy, shelter
const GOODS = window.CATALOG.goods.map(e => e.id);  // every good is made by its own industry (assets)
const RESOURCES = GOODS;                            // what agents hold and trade face to face
const PRICED = [...GOODS, "labor"];                 // everything with a price (labour's is the wage)
const CONSUMABLES = GOODS.filter(g => Object.values(CATALOG_INFO[g].effects).some(f => f > 0));   // relieve a need by default
const label = (g) => CATALOG_INFO[g]?.label ?? cap(g);
// This game's industries (from the state): layer, whether it exists, need relieved, relief per unit.
const industry = (g) => state.industries[g];
const activeGoods = () => GOODS.filter(g => state.industries[g].active);
const needOf = (g) => state.industries[g]?.need;
const cap = (w) => w[0].toUpperCase() + w.slice(1);
// Prices and money are shown in dollars, two decimals.
const usd = (v) => `${v < 0 ? "−" : ""}$${Math.abs(v).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const getPath = (obj, path) => path.split(".").reduce((o, k) => o?.[k], obj);

// A rule "spread" is a number (every agent gets it) or one of
//   {dist: "uniform", min, max}
//   {dist: "normal", mean, std, limit (cut at mean ± limit·std), skew}
//   {dist: "tiered", average, tiers: [{agents: %, share: %}, ...]}
// Same meaning as simulation/distributions.py.
function spreadMean(spec) {
  if (typeof spec === "number") return spec;
  if (spec.dist === "uniform") return (spec.min + spec.max) / 2;
  return spec.dist === "tiered" ? spec.average : spec.mean;
}

const tierAmount = (spec, tier) => spec.average * tier.share / tier.agents;

function gauss() {
  let u = 0;
  while (!u) u = Math.random();
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * Math.random());
}

// Skew-normal draw rescaled to mean 0 / std 1.
function skewNormal(alpha) {
  const delta = alpha / Math.sqrt(1 + alpha * alpha);
  const u0 = gauss(), v = gauss();
  const u1 = delta * u0 + Math.sqrt(1 - delta * delta) * v;
  const z = u0 >= 0 ? u1 : -u1;
  const m = delta * Math.sqrt(2 / Math.PI);
  return (z - m) / Math.sqrt(1 - m * m);
}

// Range a spread's values fall in, within the field's own limits.
function spreadBounds(spec, low = -Infinity, high = Infinity) {
  if (spec.dist === "uniform") return [spec.min, spec.max];
  if (spec.dist === "normal") {
    const reach = spec.limit * spec.std;
    return [Math.max(low, spec.mean - reach), Math.min(high, spec.mean + reach)];
  }
  const amounts = spec.tiers.map(t => tierAmount(spec, t));
  return [Math.min(...amounts), Math.max(...amounts)];
}

function sampleSpread(spec, low = -Infinity, high = Infinity) {
  if (typeof spec === "number") return spec;
  if (spec.dist === "uniform") return spec.min + Math.random() * (spec.max - spec.min);
  if (spec.dist === "tiered") {
    let pick = Math.random() * 100;
    const tier = spec.tiers.find(t => (pick -= t.agents) < 0) || spec.tiers[spec.tiers.length - 1];
    return tierAmount(spec, tier);
  }
  const [lo, hi] = spreadBounds(spec, low, high);
  for (let i = 0; i < 100; i++) {
    const v = spec.mean + spec.std * (spec.skew ? skewNormal(spec.skew) : gauss());
    if (v >= lo && v <= hi) return v;
  }
  return Math.min(Math.max(spec.mean, lo), hi);
}

// Every editable agent field. `path` is "field" or "group.key" (matches the API body),
// `get` reads the current value from an agent in the state payload.
const FIELD_GROUPS = [
  { legend: "General", fields: [
    { path: "name", label: "Name", type: "text", full: true, get: a => a.name, placeholder: "auto" },
    { path: "movement", label: "Movement (px/day)", min: 1, max: 200, step: 1, get: a => a.movement, placeholder: "from rules" },
    { path: "money", label: "Money", min: 0, step: 0.01, get: a => a.money },
    { path: "x", label: "X", min: 0, max: 1024, step: 1, get: a => Math.round(a.x), placeholder: "random" },
    { path: "y", label: "Y", min: 0, max: 1024, step: 1, get: a => Math.round(a.y), placeholder: "random" },
  ]},
  { legend: "Current needs (0 = satisfied, 1 = desperate)", fields: NEEDS.map(n => (
    { path: `needs.${n}`, label: cap(n), min: 0, max: 1, step: 0.01, get: a => a.needs[n], placeholder: "random" }))},
  { legend: "Need growth per day", fields: NEEDS.map(n => (
    { path: `rates.${n}`, label: cap(n), min: 0, max: 1, step: 0.001, get: a => a.modules.NeedsDecay.rates[n] }))},
  { legend: "Rest: sleep recovered per day while standing still", fields: [
    { path: "sleep_recovery", label: "Sleep recovery", min: 0, max: 1, step: 0.01, get: a => a.modules.Rest.recovery }]},
  { legend: "Inventory (every good)", collapsed: true, fields: RESOURCES.map(r => (
    { path: `inventory.${r}`, label: label(r), min: 0, step: 1, get: a => a.inventory[r] ?? 0 }))},
  { legend: "Labour", fields: [
    { path: "labor_capacity", label: "Labour capacity per day", min: 0, step: 0.05, get: a => a.labor.capacity }]},
  { legend: "Personality", fields: [
    { path: "payout_ratio", label: "Pays out as dividends (share of profits)", min: 0, max: 1, step: 0.05,
      get: a => a.personality.payout_ratio, placeholder: "from rules" },
    { path: "risk_appetite", label: "Risk appetite (0 cautious, 1 entrepreneur)", min: 0, max: 1, step: 0.05,
      get: a => a.personality.risk_appetite ?? 0, placeholder: "from rules" },
    { path: "lavishness", label: "Frugal (0) – lavish (1)", min: 0, max: 1, step: 0.05,
      get: a => a.personality.lavishness ?? 0, placeholder: "from rules" }]},
  { legend: "Industries owned (asset shares; 1 = one whole asset)", collapsed: true, fields: GOODS.map(r => (
    { path: `assets.${r}`, label: label(r), min: 0, step: 0.01, get: a => +(a.assets[r] ?? 0).toFixed(4) }))},
];
const FIELDS = FIELD_GROUPS.flatMap(g => g.fields);

let state = null;
let selectedId = null;
let editingId = null;   // agent shown in the Manage form; null = creating a new one
let activeTab = "dashboard";
let playing = false;
let busy = false;     // a request is in flight; skip timer ticks instead of queueing them
let timer = null;

// Big games: the server describes in full only the agents the UI shows (cards on screen, the
// selected one, the one being edited); the rest come as a compact entry (position, needs, goods,
// activity). This keeps each frame's download small, so the game stays quick with 1000+ agents.
const FULL_DETAIL_AGENTS = 100;   // up to this many agents everyone is sent in full (server default)
const CARD_LIMIT = 40;            // most agent cards / chips drawn at once (search or sort to find others)

function detailIds() {
  if (!state || state.agents.length <= FULL_DETAIL_AGENTS) return null;
  const ids = new Set(visibleAgents().slice(0, CARD_LIMIT).map(a => a.id));
  for (const id of [selectedId, editingId]) if (id !== null) ids.add(id);
  return [...ids];
}

// The selected / edited agent may only have its compact entry: fetch it in full.
async function ensureDetail() {
  const ids = detailIds();
  const need = [selectedId, editingId].some(id => id !== null && agentById(id) && !agentById(id).full);
  if (!ids || !need || busy) return;
  render(await api(`/api/state?detail=${ids.join(",")}`));
}

async function api(path, body, method = body === undefined ? "GET" : "POST") {
  const ids = detailIds();
  if (body !== undefined && ids) body = { ...body, detail: ids };
  const res = await fetch(path, {
    method,
    headers: body === undefined ? {} : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data;
}

async function step(steps = 1) {
  if (busy) return;
  busy = true;
  try {
    render(await api("/api/step", { steps }));
  } catch (err) {
    console.error(err);
    setPlaying(false);
  } finally {
    busy = false;
  }
}

function setPlaying(on) {
  playing = on;
  clearInterval(timer);
  if (on) timer = setInterval(() => step(Number(ui.stepsPerTick.value) || 1), Number(ui.interval.value));
  ui.play.textContent = on ? "Pause" : "Play";
  ui.play.classList.toggle("active", on);
  ui.step.disabled = on;
  ui.run100.disabled = on;
}

function render(next) {
  state = next;
  if (editingId !== null && !agentById(editingId)) editingId = null;
  ui.tick.textContent = state.tick;
  ui.calDate.textContent = calendar(state.tick);
  updateRegimeBadge();
  recordTrend();
  if (typeof refreshReport === "function") refreshReport();
  if (typeof reportVisible !== "undefined" && reportVisible) return;
  if (activeTab === "dashboard") renderDashboard();
  if (activeTab === "overview") {
    draw();
    renderMarket();
    renderAgents();
    renderEvents();
  } else if (activeTab === "products") {
    fillStickiness();
    fillClearance();
    fillPricing();
    renderProducts();
  } else if (activeTab === "banks") {
    renderBanking();
  } else if (activeTab === "housing") {
    renderHousing();
  } else if (activeTab === "government") {
    renderGovernment();
  } else {
    renderChips();
    refreshForm();
  }
}

const agentById = (id) => state.agents.find(a => a.id === id);

function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function draw() {
  const { width, height } = state;
  // The 1024px world is shrunk to fit the screen (to ~330px on a phone): grow dots and
  // labels so they stay about 4px / 11px on screen.
  const scale = Math.max(1, width / (canvas.clientWidth || width));
  const R = Math.max(DOT_RADIUS, 4 * scale);
  const labelPx = Math.round(Math.max(14, 11 * scale));
  canvas.width = width;
  canvas.height = height;
  ctx.clearRect(0, 0, width, height);

  // Light grid every 128px so distances are readable.
  ctx.strokeStyle = cssVar("--border");
  ctx.lineWidth = 1;
  for (let g = 128; g < width; g += 128) {
    ctx.beginPath(); ctx.moveTo(g, 0); ctx.lineTo(g, height); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(0, g); ctx.lineTo(width, g); ctx.stroke();
  }

  const inContact = new Set(state.contacts.flat());
  const byId = Object.fromEntries(state.agents.map(a => [a.id, a]));

  // Dashed line from each seeking/meeting agent to the agent it is heading for.
  ctx.setLineDash([6, 6]);
  for (const agent of state.agents) {
    const target = byId[agent.target_id];
    if (!target) continue;
    ctx.strokeStyle = agent.color + "aa";
    ctx.lineWidth = 1.5;
    ctx.beginPath(); ctx.moveTo(agent.x, agent.y); ctx.lineTo(target.x, target.y); ctx.stroke();
  }
  ctx.setLineDash([]);

  for (const [a, b] of state.contacts) {
    ctx.strokeStyle = cssVar("--accent");
    ctx.lineWidth = 2;
    ctx.beginPath(); ctx.moveTo(byId[a].x, byId[a].y); ctx.lineTo(byId[b].x, byId[b].y); ctx.stroke();
  }

  const filtering = isFiltering();
  for (const agent of state.agents) {
    // Agents hidden by the Overview filter are faded so the matching ones stand out.
    ctx.globalAlpha = filtering && !matchesFilter(agent) ? 0.15 : 1;
    if (ui.showRange.checked) {
      ctx.fillStyle = agent.color + "18";
      ctx.strokeStyle = agent.color + "55";
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.arc(agent.x, agent.y, agent.speed, 0, Math.PI * 2);
      ctx.fill(); ctx.stroke();
    }
    ctx.fillStyle = agent.color;
    ctx.beginPath();
    ctx.arc(agent.x, agent.y, R, 0, Math.PI * 2);
    ctx.fill();
    if (agent.depressed) {
      ctx.strokeStyle = cssVar("--muted");
      ctx.lineWidth = 2;
      ctx.setLineDash([2, 2]);
      ctx.beginPath();
      ctx.arc(agent.x, agent.y, R + 2, 0, Math.PI * 2);
      ctx.stroke();
      ctx.setLineDash([]);
    }
    if (agent.activity === "sleeping") {
      ctx.fillStyle = cssVar("--muted");
      ctx.font = `italic ${Math.round(labelPx * 0.85)}px Inter, system-ui, sans-serif`;
      ctx.fillText("z z", agent.x - 8, agent.y + R + 14);
    }
    if (agent.id === selectedId || inContact.has(agent.id)) {
      ctx.strokeStyle = cssVar("--text");
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.arc(agent.x, agent.y, R + 4, 0, Math.PI * 2);
      ctx.stroke();
    }
    ctx.fillStyle = cssVar("--muted");
    ctx.font = `500 ${labelPx}px Inter, system-ui, sans-serif`;
    // Keep labels inside the box near the right/top edges.
    const labelWidth = ctx.measureText(agent.name).width;
    const lx = agent.x + R + 4 + labelWidth > width ? agent.x - R - 4 - labelWidth : agent.x + R + 4;
    const ly = agent.y - R - 2 < labelPx ? agent.y + R + labelPx : agent.y - R - 2;
    ctx.fillText(agent.name, lx, ly);
  }
  ctx.globalAlpha = 1;
}

function needColor(v) {
  // green (satisfied) -> amber -> red (desperate)
  const hue = 150 - v * 145;
  return `hsl(${hue} 55% 55%)`;
}

// The economy, one row per industry (= per good), grouped by industry layer:
// price (base × demand multiplier), units held, what is made / consumed / used as input /
// thrown away per step (last 20 steps), the recipe, what it relieves and how long it keeps.
function renderMarket() {
  const m = state.market;
  const goods = activeGoods();
  const total = goods.reduce((sum, r) => sum + m.units[r], 0);
  ui.market.innerHTML = "";
  ui.market.append(Object.assign(document.createElement("div"), { className: "market-title",
    textContent: `Market · ${usd(m.money)} / ${total} units = ${usd(total ? m.money / total : 0)} per unit · ` +
      `${goods.length} industries in ${state.rules.industry_layers} layers` }));
  const deepest = Math.max(...goods.map(g => industry(g).layer));
  for (let layer = 1; layer <= deepest; layer++) {
    const inLayer = goods.filter(g => industry(g).layer === layer);
    if (!inLayer.length) continue;
    const box = Object.assign(document.createElement("details"), { className: "layer-group" });
    box.open = openLayers.has(layer);
    box.ontoggle = () => box.open ? openLayers.add(layer) : openLayers.delete(layer);
    const made = inLayer.reduce((s, g) => s + (m.produced_recent?.[g] || 0), 0);
    const lost = inLayer.reduce((s, g) => s + (m.expired_recent?.[g] || 0), 0);
    box.append(Object.assign(document.createElement("summary"), {
      textContent: `Layer ${layer} · ${layer === 1 ? "extraction" : `uses layer ${layer - 1}`} · ${inLayer.length} industries · ` +
        `making ${made.toFixed(2)}/day` + (lost >= 0.005 ? ` · ${lost.toFixed(2)}/day expiring` : "") }));
    for (const g of inLayer) box.append(industryRow(g));
    ui.market.append(box);
  }
  if (state.rules.investing_enabled) {
    const inv = document.createElement("div");
    inv.className = "market-title invest";
    const built = Object.entries(m.assets_built || {}).sort((a, b) => b[1] - a[1]);
    const total = built.reduce((s, [, v]) => s + v, 0);
    const projects = state.agents.filter(a => a.project).length;
    inv.textContent = `Asset trades between agents: ${m.asset_trades} (${usd(m.asset_trade_money)}) · ` +
      `new assets built from capital goods: ${total.toFixed(2)} shares` +
      (built.length ? ` (${built.slice(0, 4).map(([g, v]) => `${label(g).toLowerCase()} ${v.toFixed(2)}`).join(", ")}` +
        `${built.length > 4 ? ", …" : ""})` : "") + ` · ${projects} project${projects === 1 ? "" : "s"} under way`;
    ui.market.append(inv);
  }
  renderLaborCard();
}

const openLayers = new Set([1, 2]);   // which layer groups are unfolded (kept across redraws)

function recipeText(good) {
  const inputs = Object.entries(state.rules.inputs[good] || {});
  return inputs.length ? `1 unit = ${inputs.map(([i, q]) => `${+q.toFixed(3)} ${label(i).toLowerCase()}`).join(" + ")} + labour`
    : "extracted with labour";
}

// "hunger +0.200 · boredom +0.080 · health −0.040 per unit", main need first.
function effectsText(effects) {
  const parts = Object.entries(effects || {}).sort((a, b) => b[1] - a[1])
    .map(([need, v]) => `${need} ${v > 0 ? "+" : "−"}${Math.abs(v).toFixed(3)}`);
  return parts.length ? `${parts.join(", ")} per unit` : "not consumed (input only)";
}

function industryRow(g) {
  const m = state.market;
  const info = industry(g);
  const row = Object.assign(document.createElement("div"), { className: "industry-row" });
  const head = Object.assign(document.createElement("div"), { className: "industry-head" });
  const mult = m.multiplier[g];
  const arrow = mult > 1.02 ? "▲" : mult < 0.98 ? "▼" : "";
  head.append(
    Object.assign(document.createElement("b"), { textContent: label(g) }),
    Object.assign(document.createElement("span"), { className: "sector", textContent: CATALOG_INFO[g].sector }),
    ...(CATALOG_INFO[g].capital ? [Object.assign(document.createElement("span"), { className: "industry-tag secondary", textContent: "capital good" })] : []),
    Object.assign(document.createElement("span"), { className: "price", textContent: `${usd(m.prices[g])} ` }),
    Object.assign(document.createElement("span"), { className: `price-move ${arrow === "▲" ? "up" : arrow ? "down" : ""}`, textContent: arrow }));
  head.title = `Price = base ${usd(m.base_prices[g])} × ${mult.toFixed(2)} (demand ${m.pressure[g].toFixed(2)}: ` +
    `${m.buyers[g]} want / ${m.sellers[g]} sell · concentration ${m.concentration_factor[g].toFixed(2)})`;
  const life = state.rules.expiry_enabled ? state.rules.shelf_life[g] : 0;
  const relieves = CATALOG_INFO[g].capital ? "capital good: new assets are built from it" : effectsText(info.effects);
  const flows = ["produced_recent", "consumed_recent", "used_recent", "expired_recent"].map(k => m[k]?.[g] || 0);
  const detail = Object.assign(document.createElement("div"), { className: "industry-stats", textContent:
    `${recipeText(g)} · ${relieves} · ${life ? `keeps ${life} steps` : "never expires"}` });
  const numbers = Object.assign(document.createElement("div"), { className: "industry-stats", textContent:
    `${m.units[g]} held · made ${flows[0].toFixed(2)} · eaten ${flows[1].toFixed(2)} · as input ${flows[2].toFixed(2)}` +
    (flows[3] >= 0.005 ? ` · expired ${flows[3].toFixed(2)}` : "") + " /day · " +
    `${m.assets[g].toFixed(2)} shares (asset ${usd(m.asset_prices[g])})` });
  numbers.title = `Averages over the last 20 days. Capacity ${m.asset_output[g].toFixed(2)}/day when fully staffed; ` +
    `productivity ${m.productivity[g].toFixed(2)} units per labour.`;
  row.append(head, detail, numbers);
  const cost = Object.entries(state.rules.build_cost[g] || {});
  if (state.rules.building_enabled && cost.length) {
    const money = m.build_cost_money?.[g];
    const q = money ? m.asset_prices[g] / money : 0;
    row.append(Object.assign(document.createElement("div"), { className: "industry-stats", textContent:
      `New asset: ${cost.map(([k, n]) => `${+n.toFixed(2)} ${label(k).toLowerCase()}`).join(" + ")}` +
      (money ? ` (${usd(money)}; worth ${q.toFixed(1)}× that)` : " (can't be built in this game)") +
      (m.assets_built?.[g] ? ` · ${m.assets_built[g].toFixed(2)} built` : "") }));
  }
  if (m.stockpiling[g]) row.append(Object.assign(document.createElement("span"), { className: "badge", textContent: "agents stockpiling" }));
  return row;
}

// Labour market: wage, capacity offered vs labour wanted, who got hired, workers' condition.
function renderLaborCard() {
  const L = state.market.labor;
  const agents = state.agents;
  const avg = (fn) => agents.length ? agents.reduce((s, a) => s + fn(a), 0) / agents.length : 0;
  const card = document.createElement("div");
  card.className = "labor-card";
  const head = document.createElement("div");
  head.className = "labor-head";
  const name = Object.assign(document.createElement("span"), { className: "res-name", textContent: "Labour market" });
  const wage = Object.assign(document.createElement("b"), { textContent: usd(L.wage) });
  const unit = Object.assign(document.createElement("span"), { className: "unit", textContent: "wage per unit" });
  head.append(name, wage, unit);
  const rows = [
    ["Wage", `base ${usd(L.base_wage)} × ${L.multiplier.toFixed(2)} (labour wanted ÷ offered → ${L.pressure.toFixed(2)})`],
    ["Capacity", `${L.capacity.toFixed(2)}/day · own assets ${L.own_use.toFixed(2)} · offered ${L.offered.toFixed(2)}`],
    ["Jobs", `${L.wanted.toFixed(2)} wanted · ${L.hired.toFixed(2)} hired (${L.workers_hired} workers)` +
      (L.gov_hired ? ` · government ${L.gov_hired.toFixed(2)}` : "")],
    ["Unused", `${L.unused.toFixed(2)}/day: ${L.withheld.toFixed(2)} not offered (no need to work) · ` +
      `${L.idle.toFixed(2)} offered but not hired`],
    ["Workers", `efficiency ${avg(a => a.labor.efficiency).toFixed(2)} · wellbeing ${avg(a => a.labor.wellbeing).toFixed(2)} · ` +
      `need for a job ${avg(a => a.labor.job_need).toFixed(2)}`],
  ];
  const list = document.createElement("dl");
  for (const [k, v] of rows) {
    list.append(Object.assign(document.createElement("dt"), { textContent: k }),
                Object.assign(document.createElement("dd"), { textContent: v }));
  }
  card.append(head, list);
  ui.market.append(card);
}

// ---------- Overview: search, filter and sort agents ----------

const agentView = { query: "", filter: "all", sort: "id", desc: true };

const SORT_VALUE = {
  id: a => a.id,
  name: a => a.name.toLowerCase(),
  money: a => a.money,
  movement: a => a.movement,
  reserve: a => RESOURCES.reduce((sum, r) => sum + (a.reserve?.[r] || 0), 0),
  assets: a => GOODS.reduce((sum, r) => sum + (a.assets?.[r] || 0), 0),
  urgency: a => Math.max(...NEEDS.map(n => a.needs[n])),
  ...Object.fromEntries(RESOURCES.map(r => [r, a => a.inventory[r] ?? 0])),
  labor: a => a.labor.sold,
  ...Object.fromEntries(NEEDS.map(n => [n, a => a.needs[n]])),
};

const isFiltering = () => agentView.query !== "" || agentView.filter !== "all";

function matchesFilter(a) {
  if (agentView.query && !a.name.toLowerCase().includes(agentView.query)) return false;
  switch (agentView.filter) {
    case "all": return true;
    case "needy": return a.wants.length > 0 || a.activity === "sleeping";
    case "depressed": return a.depressed;
    default: return a.activity === agentView.filter;
  }
}

function visibleAgents() {
  const key = SORT_VALUE[agentView.sort];
  const dir = agentView.desc ? -1 : 1;
  return state.agents.filter(matchesFilter).sort((a, b) => {
    const x = key(a), y = key(b);
    return (x < y ? -1 : x > y ? 1 : a.id - b.id) * dir;
  });
}

function onAgentViewChange() {
  agentView.query = ui.agentSearch.value.trim().toLowerCase();
  agentView.filter = ui.agentFilter.value;
  agentView.sort = ui.agentSort.value;
  ui.agentSortDir.textContent = agentView.desc ? "↓ desc" : "↑ asc";
  renderAgents();
  draw();
}
ui.agentSearch.oninput = onAgentViewChange;
ui.agentFilter.onchange = onAgentViewChange;
ui.agentSort.onchange = () => {
  // Text and IDs read best A→Z / 1→n; amounts read best largest first.
  agentView.desc = !["id", "name"].includes(ui.agentSort.value);
  onAgentViewChange();
};
ui.agentSortDir.onclick = () => { agentView.desc = !agentView.desc; onAgentViewChange(); };
agentView.desc = false;  // default: ID ascending

// Small line chart of a series (oldest first). The axis starts at 0 so a line only
// slopes as much as the value really changed.
function sparkline(values) {
  const canvas = document.createElement("canvas");
  canvas.className = "spark";
  canvas.width = 110;
  canvas.height = 24;
  if (values.length < 2) return canvas;
  const c = canvas.getContext("2d");
  const lo = 0, span = Math.max(...values) || 1;
  c.strokeStyle = cssVar("--accent");
  c.lineWidth = 1.5;
  c.beginPath();
  values.forEach((v, i) => {
    const x = (i / (values.length - 1)) * (canvas.width - 2) + 1;
    const y = canvas.height - 2 - ((v - lo) / span) * (canvas.height - 4);
    i ? c.lineTo(x, y) : c.moveTo(x, y);
  });
  c.stroke();
  return canvas;
}

function renderAgents() {
  ui.agents.innerHTML = "";
  const matching = visibleAgents();
  ui.agentShown.textContent = matching.length === state.agents.length
    ? `(${matching.length})` : `(${matching.length} of ${state.agents.length})`;
  // Only the first CARD_LIMIT cards (plus the selected agent) are drawn.
  const shown = matching.slice(0, CARD_LIMIT);
  const selected = selectedId !== null && agentById(selectedId);
  if (selected && !shown.includes(selected)) shown.unshift(selected);
  if (!shown.length) {
    const empty = document.createElement("p");
    empty.className = "empty-list";
    empty.textContent = "No agents match.";
    ui.agents.append(empty);
  }
  for (const a of shown) {
    const card = document.createElement("div");
    card.className = "agent" + (a.id === selectedId ? " selected" : "");
    card.onclick = () => { selectedId = selectedId === a.id ? null : a.id; render(state); };

    const head = document.createElement("div");
    head.className = "agent-head";
    const dot = document.createElement("span");
    dot.className = "dot";
    dot.style.background = a.color;
    const name = document.createElement("span");
    name.textContent = a.name;
    const pos = document.createElement("span");
    pos.className = "pos";
    pos.textContent = `(${a.x.toFixed(0)}, ${a.y.toFixed(0)})`;
    const edit = document.createElement("button");
    edit.className = "edit-btn";
    edit.textContent = "Edit";
    edit.onclick = (e) => { e.stopPropagation(); openEditor(a.id); };
    head.append(dot, name, edit, pos);

    const stats = document.createElement("div");
    stats.className = "stats";
    for (const need of NEEDS) {
      const v = a.needs[need];
      const label = document.createElement("span");
      label.className = "name";
      label.textContent = need;
      const bar = document.createElement("div");
      bar.className = "bar";
      const fill = document.createElement("div");
      fill.style.width = `${v * 100}%`;
      fill.style.background = needColor(v);
      bar.append(fill);
      const val = document.createElement("span");
      val.className = "val";
      val.textContent = v.toFixed(2);
      stats.append(label, bar, val);
    }

    const lab = a.full ? a.labor : null;   // compact entries carry only a few labour figures
    const meta = document.createElement("div");
    meta.className = "meta";
    const held = RESOURCES.filter(r => a.inventory[r]);
    const fields = [
      ...(held.length ? held.map(r => [label(r).toLowerCase(), a.inventory[r]]) : [["goods", "none"]]),
      ["money", usd(a.money)],
      ...(a.deposits ? [["in the bank", usd(a.deposits)]] : []),
      ...(a.debt ? [["owes the bank", usd(a.debt)]] : []),
      ...(a.company_cash ? [["company cash", usd(a.company_cash), "Retained earnings of its companies: pays wages and builds new capacity"]] : []),
      ...(Object.keys(a.assets).length ? [["pays out", `${Math.round(a.personality.payout_ratio * 100)}% of profits`,
        "Personality: share of its companies' profits it takes as dividends; the rest is reinvested"]] : []),
      ...(a.budget ? [["monthly budget", usd(a.budget.total),
        `Keeps ${usd(a.budget.total)} before investing: cash for what it needs now + ${a.budget.steps} days × ` +
        `(living ${usd(a.budget.living)} + loan payments ${usd(a.budget.loans)} per day). ` +
        `Income ${usd(a.income)}/day.`],
        [a.budget.spare >= 0 ? "left to invest" : "short of budget", usd(Math.abs(a.budget.spare))]] : []),
      ...(state.housing ? [["home", !a.home ? "homeless" : a.home.owns ? `its own house (#${a.home.house})`
        : `rents house #${a.home.house} from ${a.home.landlord}`]] : []),
      ...Object.entries(a.experience || {}).map(([g, x]) => {
        const r = state.rules;
        const skill = r?.specialization_enabled ? 1 + (r.skill_max - 1) * (1 - Math.exp(-x / r.skill_scale)) : 1;
        return [`skill in ${label(g).toLowerCase()}`, `×${skill.toFixed(1)}`, `${x.toFixed(1)} units of labour worked there`];
      }),
      ...Object.entries(a.luck || {}).map(([g, l]) => ["lucky business", `${label(g).toLowerCase()} output ×${l.times} until day ${l.until}`,
        "A hit product or an invention: many times the output from the same labour and inputs, for a while"]),
      ...(a.houses ? [["houses", `${a.houses} owned` + (a.houses_let ? `, ${a.houses_let} let` : "")]] : []),
      ["movement", a.speed < a.movement ? `${a.speed} px (${a.movement} normally)` : `${a.speed} px`],
      ...Object.entries(a.subsistence || {}).map(([g, n]) => ["makes on its own", `${n.toFixed(2)} ${label(g).toLowerCase()}/day`,
        "Autonomous production: labour it had left (no job, own industries done) goes into making its own water or food"]),
      ...GOODS.filter(r => a.assets[r]).map(r => {
        const price = state.market.asset_prices[r];
        return [`${label(r).toLowerCase()} industry`, `${a.assets[r].toFixed(2)} (worth ${usd(a.assets[r] * price)}, ` +
          `${(a.assets[r] * state.market.asset_output_each[r]).toFixed(2)}/day)`,
          `One whole ${r} asset costs ${usd(price)} now`];
      }),
      // Building project: capital goods held / needed.
      ...(a.project ? [["building", `${a.project.shares.toFixed(2)} ${label(a.project.good).toLowerCase()} asset(s): ` +
        Object.entries(a.project.need).map(([k, n]) => `${label(k).toLowerCase()} ${Math.min(a.inventory[k] ?? 0, n)}/${n}`).join(", "),
        `Started at day ${a.project.started}; dropped after ${state.rules.project_steps} days`]] : []),
      // Inputs its secondary industries keep in stock.
      ...Object.entries(a.input_target || {}).map(([r, n]) => [`${label(r).toLowerCase()} input buffer`, n,
        `Keeps ${n} ${r} for its industries; buys more when below ${Math.round(n * state.rules.input_reorder)}`]),
      // Reserve it wants to hold because the resource is becoming scarce.
      ...RESOURCES.filter(r => a.reserve?.[r]).map(r => [`${label(r).toLowerCase()} reserve`, a.reserve[r],
        "Wants to hold this much because it is becoming scarce"]),
    ];
    for (const [label, value, title] of fields) {
      const span = document.createElement("span");
      const b = document.createElement("b");
      b.textContent = value;
      span.append(`${label} `, b);
      if (title) span.title = title;
      meta.append(span);
    }

    const activity = document.createElement("div");
    activity.className = "activity";
    const act = document.createElement("b");
    act.className = a.activity;
    const target = state.agents.find(o => o.id === a.target_id);
    act.textContent = a.activity === "seeking" && target ? `seeking ${target.name} to buy ${a.seeking_for}`
      : a.activity === "meeting" && target ? `meeting ${target.name}`
      : a.activity === "stockpiling" && target ? `stockpiling ${a.seeking_for} from ${target.name}`
      : a.activity === "restocking" && target ? `restocking ${a.seeking_for} from ${target.name}`
      : a.activity === "sourcing" && target ? `buying ${a.seeking_for} for its industries from ${target.name}`
      : a.activity === "building" && target ? `buying ${a.seeking_for} from ${target.name} to build ${a.project?.good} assets`
      : a.activity === "hiring" && target ? `hiring labour from ${target.name}`
      : a.activity === "selling" && target ? `selling ${a.seeking_for} to ${target.name}`
      : a.activity === "searching" ? `searching: nobody sells anything for ${a.wants.join(" or ")}`
      : a.activity;
    const owned = GOODS.filter(g => a.assets[g]);
    const worked = !lab ? "" : Object.entries(lab.employers).map(([who, u]) => `${u.toFixed(2)} for ${who}`).join(", ");
    const prod = !lab ? "details load when shown" : `labour ${lab.capacity_now.toFixed(2)}/day (capacity ${lab.capacity.toFixed(2)} × efficiency ` +
      `${lab.efficiency.toFixed(2)}) · wellbeing ${lab.wellbeing.toFixed(2)} · need for a job ${lab.job_need.toFixed(2)}` +
      (lab.offered ? ` · offers ${lab.offered.toFixed(2)} at ${usd(lab.asking_wage)}` : "") +
      (worked ? ` · worked ${worked}` : "") +
      (owned.length ? ` · its assets employ ${a.labor_need.toFixed(2)}/day` +
        (lab.bought ? ` (hired ${lab.bought.toFixed(2)})` : "") : "");
    activity.append(act);
    // Unmet needs and what they cost it (slower, less labour, illness); "depressed" is one of them.
    const hurts = a.penalties ?? (a.depressed ? ["depressed"] : []);
    if (hurts.length) {
      const sad = document.createElement("b");
      sad.className = "depressed";
      sad.textContent = hurts.join(" · ");
      activity.append(" · ", sad);
    }
    meta.append(Object.assign(document.createElement("span"), { className: "work-line", textContent: prod }));

    // At a glance: what it is doing, money and needs. Everything else is one click away.
    const summary = Object.assign(document.createElement("div"), { className: "agent-summary" });
    summary.append(Object.assign(document.createElement("span"), { textContent: `cash ${usd(a.money)}` }),
                   ...(a.deposits ? [Object.assign(document.createElement("span"), { textContent: `bank ${usd(a.deposits)}` })] : []),
                   ...(a.debt ? [Object.assign(document.createElement("span"), { className: "owes", textContent: `owes ${usd(a.debt)}` })] : []),
                   ...(Object.keys(a.assets).length ? [Object.assign(document.createElement("span"),
                     { textContent: `owns ${Object.keys(a.assets).length} industr${Object.keys(a.assets).length === 1 ? "y" : "ies"}` })] : []));
    const more = Object.assign(document.createElement("details"), { className: "agent-more" });
    more.append(Object.assign(document.createElement("summary"), { textContent: "Details: goods, industries, budget, work" }), meta);
    more.onclick = (e) => e.stopPropagation();
    card.append(head, activity, summary, stats, more);
    ui.agents.append(card);
  }
  if (matching.length > CARD_LIMIT) {
    const more = document.createElement("p");
    more.className = "empty-list";
    more.textContent = `Showing ${CARD_LIMIT} of ${matching.length}. Search, filter or sort to see others, ` +
      "or tap an agent on the map.";
    ui.agents.append(more);
  }
}

function renderEvents() {
  ui.events.innerHTML = "";
  for (const ev of [...state.events].reverse()) {
    const li = document.createElement("li");
    li.value = ev.tick;
    const msg = document.createElement("span");
    msg.textContent = ev.message;
    li.append(Object.assign(document.createElement("span"), { className: "ev-day", textContent: calendar(ev.tick) }), msg);
    ui.events.append(li);
  }
}

// ---------- Tabs ----------

function showTab(name) {
  activeTab = name;
  for (const t of ui.tabs) {
    t.classList.toggle("active", t.dataset.tab === name);
    $(`tab-${t.dataset.tab}`).hidden = t.dataset.tab !== name;
    if (t.dataset.tab === name) ui.pageTitle.textContent = t.lastElementChild.textContent.trim();
  }
  if (typeof showView === "function") showView(name === "report" ? "report" : "simulation");
  if (name === "government") fillGovernment(true);
  if (name === "banks") fillBanking(true);
  if (name === "housing") fillHousing();
  render(state);
}
for (const t of ui.tabs) t.onclick = () => showTab(t.dataset.tab);

// ---------- Price stickiness (Products tab) ----------

$("price-stickiness").onchange = async (e) => {
  render(await api("/api/market", { price_stickiness: Number(e.target.value) }));
};

function fillStickiness() {
  const sel = $("price-stickiness");
  if (document.activeElement === sel) return;
  const s = state.market.price_stickiness ?? 0;
  if (![...sel.options].some(o => Number(o.value) === s)) sel.append(new Option(`custom (${s})`, String(s)));
  sel.value = String([...sel.options].find(o => Number(o.value) === s).value);
}

// ---------- Clearance sales (Products tab) ----------

let clearDirty = false;

function clearRow(days, off) {
  const row = document.createElement("div");
  row.className = "clear-row";
  const d = Object.assign(document.createElement("input"), { type: "number", min: 0, max: 10000, step: 1, value: days });
  const o = Object.assign(document.createElement("input"), { type: "number", min: 0, max: 100, step: 5, value: off });
  const x = Object.assign(document.createElement("button"), { type: "button", className: "policy-close", textContent: "×", title: "Remove step" });
  x.onclick = () => { row.remove(); clearDirty = true; };
  row.append("From ", d, " days before expiry: ", o, " % off", x);
  row.oninput = () => { clearDirty = true; };
  return row;
}

function fillClearance(force = false) {
  if (clearDirty && !force) return;
  const m = state.market;
  $("clear-on").checked = !!m.clearance_enabled;
  const box = $("clear-steps");
  box.innerHTML = "";
  for (const [days, off] of m.clearance_schedule || []) box.append(clearRow(days, Math.round(off * 100)));
  clearDirty = false;
}

$("clear-add").onclick = () => { $("clear-steps").append(clearRow(10, 20)); clearDirty = true; };
$("clear-on").onchange = () => { clearDirty = true; };
$("clear-apply").onclick = async () => {
  const status = $("clear-status");
  const steps = [...$("clear-steps").querySelectorAll(".clear-row")].map(r => {
    const [d, o] = r.querySelectorAll("input");
    return [Number(d.value), Number(o.value) / 100];
  });
  try {
    render(await api("/api/market", { clearance_enabled: $("clear-on").checked, clearance_schedule: steps }));
    clearDirty = false;
    fillClearance(true);
    status.textContent = "Applied from tomorrow.";
    status.className = "status";
  } catch (err) {
    status.textContent = err.message;
    status.className = "status error";
  }
  status.hidden = false;
};

// ---------- Pricing settings (Products tab) ----------

let pricingDirty = false;
$("pricing-form").addEventListener("input", () => { pricingDirty = true; });

function fillPricing() {
  const p = state.market.pricing;
  if (!p || pricingDirty) return;
  for (const el of $("pricing-form").querySelectorAll("[data-pricing]")) {
    el.value = +(p[el.dataset.pricing] * Number(el.dataset.scale || 1)).toFixed(3);
  }
}

$("pricing-form").onsubmit = async (e) => {
  e.preventDefault();
  const status = $("pricing-status");
  try {
    render(await api("/api/market", Object.fromEntries([...$("pricing-form").querySelectorAll("[data-pricing]")]
      .map(el => [el.dataset.pricing, Number(el.value) / Number(el.dataset.scale || 1)]))));
    pricingDirty = false;
    status.textContent = "Applied from tomorrow.";
    status.className = "status";
  } catch (err) {
    status.textContent = err.message;
    status.className = "status error";
  }
  status.hidden = false;
};

// ---------- Personality of a group (Edit agents tab) ----------

$("group-apply").onclick = async () => {
  const status = $("group-status");
  try {
    render(await api("/api/personality", { group: $("group-who").value, trait: $("group-trait").value,
                                           value: Number($("group-value").value) }));
    status.textContent = "Applied.";
    status.className = "status";
  } catch (err) {
    status.textContent = err.message;
    status.className = "status error";
  }
  status.hidden = false;
};

// ---------- Housing tab ----------

function statCards(box, stats) {
  box.innerHTML = "";
  for (const [label, value, note] of stats) {
    const card = document.createElement("div");
    card.className = "stat";
    card.append(Object.assign(document.createElement("div"), { className: "stat-label", textContent: label }),
                Object.assign(document.createElement("div"), { className: "stat-value", textContent: value }),
                Object.assign(document.createElement("div"), { className: "stat-note", textContent: note }));
    box.append(card);
  }
}

function renderHousing() {
  const h = state.housing;
  $("housing-off").hidden = !!h;
  for (const id of ["housing-stats", "housing-landlords"]) $(id).hidden = !h;
  if (!h) return;
  const people = state.agents.length || 1;
  statCards($("housing-stats"), [
    ["Houses", `${h.houses}`, `${(h.houses / people).toFixed(2)} per agent · ${h.built_month} built in the last 30 days`],
    ["Homeless", `${h.homeless}`, `${Math.round(h.homeless / people * 100)}% of agents · ${h.evictions} evictions so far`],
    ["Live in their own house", `${h.owner_occupied}`, `${Math.round(h.owner_occupied / people * 100)}% of agents`],
    ["Renting", `${h.rented}`, `${h.public} public housing (rent goes to the treasury)`],
    ["Empty", `${h.vacant}`, `${h.for_sale} for sale`],
    ["House price", usd(h.price), `minimum ${usd(h.min_price)} (${h.min_multiple}× food)`],
    ["Rent", `${usd(h.rent * DAYS_PER_MONTH())} /month`, `${(perYear(h.rent_yield) * 100).toFixed(1)}% of the price a year · ${usd(h.rent_paid_day)} paid yesterday`],
    ["Sales", `${h.sold_month} in 30 days`, `${h.sales} houses sold so far`],
  ]);
  const box = $("housing-landlords");
  box.innerHTML = "";
  if (!h.landlords.length) box.append(Object.assign(document.createElement("p"), { className: "empty-list", textContent: "Nobody rents out a house yet." }));
  for (const [name, n] of h.landlords) {
    const d = document.createElement("div");
    d.append(name, Object.assign(document.createElement("b"), { textContent: `${n} let` }));
    box.append(d);
  }
}

function fillHousing() {
  const h = state.housing;
  if (!h) return;
  $("house-min").value = h.min_multiple;
  $("house-yield").value = +(perYear(h.rent_yield) * 100).toFixed(2);
  $("house-evict").value = h.eviction_days;
}

$("housing-form").onsubmit = async (e) => {
  e.preventDefault();
  const status = $("housing-status");
  try {
    render(await api("/api/housing", {
      min_multiple: Number($("house-min").value),
      rent_yield: perDay(Number($("house-yield").value) / 100),
      eviction_days: Number($("house-evict").value),
    }));
    status.textContent = "Applied from tomorrow.";
    status.className = "status";
  } catch (err) {
    status.textContent = err.message;
    status.className = "status error";
  }
  status.hidden = false;
};

// ---------- Government tab ----------

// The policy inputs only follow the live state until you start editing them.
let govDirty = false;

function fillGovernment(force = false) {
  if (govDirty && !force) return;
  govDirty = false;
  const g = state.government;
  setGovInputs(perYear(g.min_rate) * 100, g.labor_purchase);   // shown % a year, kept per day
  ui.govEnabled.checked = g.enabled;
  for (const el of ui.govForm.querySelectorAll("[data-policy]")) {
    const v = g[el.dataset.policy];
    if (el.type === "checkbox") el.checked = v;
    else if (el.dataset.choice) el.value = v || "daily";
    else el.value = +((el.dataset.yearly ? perYear(v) : v) * Number(el.dataset.scale || 1)).toFixed(3);
  }
  ui.govBasel.value = +(g.capital_ratio * 100).toFixed(2);
}

function setGovInputs(ratePct, buy) {
  ui.govRate.value = +ratePct.toFixed(4);
  ui.govRateRange.value = Math.min(ratePct, Number(ui.govRateRange.max));
  ui.govBuy.value = buy;
  ui.govBuyRange.value = Math.min(buy, Number(ui.govBuyRange.max));
  ui.govRateLabel.textContent = `${(+ratePct).toFixed(2)}%`;
  ui.govBuyLabel.textContent = `${buy}`;
}

// ---------- Public spending policies ----------

const policyCards = new Map();   // policy id -> card element

function policyStatus(message, error = false) {
  ui.policyStatus.textContent = message;
  ui.policyStatus.className = error ? "status error" : "status";
  ui.policyStatus.hidden = !message;
}

async function sendPolicy(body) {
  try {
    render(await api("/api/policies", body));
    policyStatus("");
  } catch (err) {
    policyStatus(err.message, true);
  }
}

function policySelect(options, value, field, id) {
  const sel = document.createElement("select");
  for (const [v, text] of options) sel.append(new Option(text, v, false, v === value));
  sel.dataset.field = field;
  sel.onchange = () => sendPolicy({ action: "update", id, policy: { [field]: sel.value } });
  return sel;
}

function policyField(label, control) {
  const l = document.createElement("label");
  l.append(label, control);
  return l;
}

function buildPolicyCard(p, opts) {
  const card = document.createElement("div");
  card.className = "policy";
  const head = document.createElement("div");
  head.className = "policy-head";
  const order = Object.assign(document.createElement("span"), { className: "order" });
  const name = Object.assign(document.createElement("input"), { className: "policy-name", type: "text",
    maxLength: 60, value: p.name, placeholder: p.label, title: "Name this policy" });
  name.dataset.field = "name";
  name.onchange = () => sendPolicy({ action: "update", id: p.id, policy: { name: name.value } });
  const close = Object.assign(document.createElement("button"), { type: "button", className: "policy-close",
    textContent: "×", title: "End this policy" });
  close.setAttribute("aria-label", `End policy ${p.label}`);
  close.onclick = () => sendPolicy({ action: "remove", id: p.id });
  head.append(order, name, close);

  const fields = document.createElement("div");
  fields.className = "policy-fields";
  fields.append(policyField("What", policySelect(Object.entries(opts.kinds), p.kind, "kind", p.id)));
  if (p.kind === "goods") {
    fields.append(policyField("Resource", policySelect(activeGoods().map(g => [g, g.replace(/_/g, " ")]),
      p.good, "good", p.id)));
  }
  if (p.kind === "service") {
    fields.append(policyField("Need it relieves", policySelect(NEEDS.filter(n => n !== "sleep").map(n => [n, n]),
      p.need, "need", p.id)));
  }
  fields.append(policyField("Who gets it", policySelect(Object.entries(opts.audiences), p.audience, "audience", p.id)));
  if (p.audience === "low_income") {
    const share = Object.assign(document.createElement("input"), { type: "number", min: 1, max: 100, step: 1,
      value: Math.round(p.share * 100) });
    share.dataset.field = "share";
    share.onchange = () => sendPolicy({ action: "update", id: p.id, policy: { share: Number(share.value) / 100 } });
    fields.append(policyField("Poorest % by income", share));
  }
  fields.append(policyField("How it is shared", policySelect(Object.entries(opts.distributions), p.distribution,
    "distribution", p.id)));
  const budget = Object.assign(document.createElement("input"), { type: "number", min: 0, step: 100, value: p.budget });
  budget.dataset.field = "budget";
  budget.onchange = () => sendPolicy({ action: "update", id: p.id, policy: { budget: Number(budget.value) } });
  fields.append(policyField("Budget ($ a month, 0 = as needed)", budget));

  const stats = document.createElement("div");
  stats.className = "policy-stats";
  card.append(head, fields, stats);
  card.dataset.shape = `${p.kind}|${p.audience}`;
  return card;
}

function fillPolicyCard(card, p, index) {
  card.querySelector(".order").textContent = `#${index + 1}`;
  const name = card.querySelector(".policy-name");
  name.placeholder = p.label;
  if (!card.contains(document.activeElement)) {
    name.value = p.name;
    for (const el of card.querySelectorAll(".policy-fields [data-field]")) {
      const f = el.dataset.field;
      el.value = f === "share" ? Math.round(p.share * 100) : p[f] ?? "";
    }
  }
  const what = p.kind === "goods" ? `${p.delivered.toFixed(0)} ${p.good.replace(/_/g, " ")} handed out`
    : p.kind === "service" ? `${p.hired.toFixed(2)} labour hired · ${p.delivered.toFixed(2)} of ${p.need} relieved`
    : `${p.recipients} paid`;
  const stats = card.querySelector(".policy-stats");
  stats.innerHTML = "";
  const funded = p.funded < 0.999;
  for (const [label, value, cls] of [
    ["Spent last 30 days", usd(p.spent_month)],
    ["Yesterday", what],
    ["Reached yesterday", `${p.recipients} agents`],
    ["Funded", funded ? `${Math.round(p.funded * 100)}% (treasury short)` : "fully", funded ? "short" : ""],
  ]) {
    const span = document.createElement("span");
    if (cls) span.className = cls;
    span.append(`${label}: `, Object.assign(document.createElement("b"), { textContent: value }));
    stats.append(span);
  }
}

function renderPolicies() {
  const g = state.government;
  const list = g.policies || [];
  const opts = g.policy_options;
  ui.policyAdd.disabled = !g.enabled;
  // Budget summary: what comes in, what is promised and what was spent.
  const promised = list.reduce((a, p) => a + p.budget, 0);
  const asNeeded = list.filter(p => p.budget === 0).length;
  const spent = list.reduce((a, p) => a + p.spent_month, 0);
  ui.policyBudget.innerHTML = "";
  for (const [label, value, warn] of [
    ["Taxes per month", usd(g.revenue_month)],
    ["Budgets promised per month", usd(promised) + (asNeeded ? ` + ${asNeeded} as needed` : ""), promised > g.revenue_month],
    ["Spent on policies, last 30 days", usd(spent)],
    ["Treasury now", usd(g.treasury)],
  ]) {
    const d = document.createElement("div");
    if (warn) d.className = "warn";
    d.append(label, Object.assign(document.createElement("b"), { textContent: value }));
    ui.policyBudget.append(d);
  }
  if (!list.length) {
    ui.policyList.innerHTML = `<p class="empty-list">No spending policies: taxes go to the benefit, public works and equal transfers.</p>`;
    policyCards.clear();
    return;
  }
  const seen = new Set();
  list.forEach((p, i) => {
    seen.add(p.id);
    let card = policyCards.get(p.id);
    const shape = `${p.kind}|${p.audience}`;
    if (!card || card.dataset.shape !== shape) {          // new, or its fields changed: rebuild
      const fresh = buildPolicyCard(p, opts);
      if (card) card.replaceWith(fresh);
      card = fresh;
      policyCards.set(p.id, card);
    }
    fillPolicyCard(card, p, i);
    if (ui.policyList.children[i] !== card) ui.policyList.insertBefore(card, ui.policyList.children[i] || null);
  });
  for (const [id, card] of policyCards) {
    if (!seen.has(id)) { card.remove(); policyCards.delete(id); }
  }
  for (const el of [...ui.policyList.children]) if (!el.classList.contains("policy")) el.remove();
}

ui.policyAdd.onclick = () => {
  const g = state.government;
  const budget = Math.max(100, Math.round((g.revenue_month || 0) * 0.1 / 100) * 100);
  sendPolicy({ action: "add", policy: { kind: "cash", audience: "low_income", share: 0.2, distribution: "equal", budget } });
};

function renderGovernment() {
  fillGovernment();
  renderPolicies();
  const g = state.government;
  const m = state.market;
  const stats = [
    ["Policy rate", pctYear(g.min_rate, 2), g.taylor_enabled
      ? (g.taylor ? `Taylor rule: inflation ${(g.taylor.inflation * 100).toFixed(1)}%, unemployment ${(g.taylor.unemployment * 100).toFixed(0)}%`
                  : "Taylor rule: from month 3 (needs a quarter of data)")
      : "set by you · minimum return on assets"],
    ["Labour hired", `${g.labor_purchase} /day`, "with newly created money"],
    ["Money created", usd(g.money_created), `${usd(g.last_spent)} yesterday`],
    ["Labour used up", g.labor_bought.toFixed(1), "in public works so far"],
    ["Money in the economy", usd(m.money), "held by agents"],
    ["Labour price", usd(m.prices.labor), `food ${usd(m.prices.food)} · water ${usd(m.prices.water)}`],
    ...(state.market.labor.wages_owed > 0.01 || g.pay_period !== "daily" ? [["Wages owed", usd(state.market.labor.wages_owed),
      `paid ${g.pay_period}` + (state.market.labor.unpaid_last > 0.01 ? ` · ${usd(state.market.labor.unpaid_last)} unpaid on the last payday` : "")]] : []),
    ["Taxes today", usd(Object.values(g.step_revenue).reduce((a, v) => a + v, 0)),
      `production ${usd(g.step_revenue.production)} · salary ${usd(g.step_revenue.wage)} · profit ${usd(g.step_revenue.profit)}`],
    ["Spending today", usd(g.step_spent.benefits + g.step_spent.public_works + g.step_spent.transfers + (g.step_spent.interest || 0)),
      `benefits ${usd(g.step_spent.benefits)} · public works ${usd(g.step_spent.public_works)} · transfers ${usd(g.step_spent.transfers)}` +
      (g.step_spent.interest ? ` · interest ${usd(g.step_spent.interest)}` : "")],
    ["Treasury", usd(g.treasury), `${usd(Object.values(g.revenue).reduce((a, v) => a + v, 0))} collected so far`],
    ["Central bank loans", usd(g.llr_outstanding), `to banks · ${usd(g.llr_lent)} lent so far`],
    ...(g.debt ? [
      ["Public debt", usd(g.debt.debt), g.debt.gdp_year > 0
        ? `${(g.debt.debt_to_gdp * 100).toFixed(1)}% of a year's real GDP (limit ${Math.round(g.debt_limit * 100)}%)`
        : `limit ${Math.round(g.debt_limit * 100)}% of GDP`],
      ["Bond rate", `${(g.debt.rate_year * 100).toFixed(2)}% a year`,
        `central bank rate + ${(perYear(g.bond_spread) * 100).toFixed(2)}% + risk ${(g.debt.risk_premium_year * 100).toFixed(2)}% · ${g.debt.bonds} bonds`],
      ["Interest on debt", `${usd(g.debt.step_interest)} /day`, `${usd(g.debt.interest_paid)} paid so far`],
      ["Who lent", `banks ${usd(g.debt.holders_banks)}`, `savers ${usd(g.debt.holders_agents)}` +
        (g.debt.step_borrowed ? ` · borrowed ${usd(g.debt.step_borrowed)} yesterday` : "") +
        (g.debt.step_repaid ? ` · repaid ${usd(g.debt.step_repaid)} yesterday` : "")],
    ] : []),
    ...(state.macro ? [
      ["GDP (last year)", usd(state.macro.gdp_nominal), `real ${usd(state.macro.gdp_real)} at year-ago prices`],
      ["Inflation", `${(state.macro.inflation * 100).toFixed(1)}%`, `CPI ${state.macro.cpi.toFixed(1)} · deflator ${state.macro.deflator.toFixed(1)}`],
    ] : []),
  ];
  ui.govStats.innerHTML = "";
  for (const [label, value, note] of stats) {
    const card = document.createElement("div");
    card.className = "stat";
    const l = Object.assign(document.createElement("div"), { className: "stat-label", textContent: label });
    const v = Object.assign(document.createElement("div"), { className: "stat-value", textContent: value });
    const n = Object.assign(document.createElement("div"), { className: "stat-note", textContent: note });
    card.append(l, v, n);
    ui.govStats.append(card);
  }
}

ui.govRateRange.oninput = () => { govDirty = true; setGovInputs(Number(ui.govRateRange.value), Number(ui.govBuy.value)); };
ui.govRate.oninput = () => { govDirty = true; ui.govRateLabel.textContent = `${Number(ui.govRate.value).toFixed(2)}%`;
  ui.govRateRange.value = ui.govRate.value; };
ui.govBuyRange.oninput = () => { govDirty = true; setGovInputs(Number(ui.govRate.value), Number(ui.govBuyRange.value)); };
ui.govBuy.oninput = () => { govDirty = true; ui.govBuyLabel.textContent = ui.govBuy.value; ui.govBuyRange.value = ui.govBuy.value; };
ui.govEnabled.onchange = () => { govDirty = true; };
ui.govForm.addEventListener("input", () => { govDirty = true; });
ui.govBasel.oninput = () => { govDirty = true; };
ui.govRevert.onclick = () => { ui.govStatus.hidden = true; fillGovernment(true); };
ui.govForm.onsubmit = async (e) => {
  e.preventDefault();
  try {
    const next = await api("/api/government", {
      enabled: ui.govEnabled.checked,
      ...Object.fromEntries([...ui.govForm.querySelectorAll("[data-policy]")].map(el =>
        [el.dataset.policy, el.type === "checkbox" ? el.checked : el.dataset.choice ? el.value
          : el.dataset.yearly ? perDay(Number(el.value) / Number(el.dataset.scale || 1)) : Number(el.value) / Number(el.dataset.scale || 1)])),
      min_rate: perDay(Number(ui.govRate.value) / 100),
      labor_purchase: Number(ui.govBuy.value),
      capital_ratio: Number(ui.govBasel.value) / 100,
    });
    govDirty = false;
    render(next);
    ui.govStatus.textContent = "Policy applied from tomorrow.";
    ui.govStatus.className = "status";
  } catch (err) {
    ui.govStatus.textContent = err.message;
    ui.govStatus.className = "status error";
  }
  ui.govStatus.hidden = false;
};

// ---------- Time: one step of the simulation is one day ----------

const DAYS_PER_MONTH = () => state?.rules?.month_steps || 30;
const DAYS_PER_YEAR = () => 12 * DAYS_PER_MONTH();

// "Year 2 · Month 3 · Day 14" for a day number (day 1 = Year 1, Month 1, Day 1).
function calendar(day) {
  const d = Math.max(0, day - 1), m = DAYS_PER_MONTH();
  return `Year ${Math.floor(d / (12 * m)) + 1} · Month ${Math.floor(d / m) % 12 + 1} · Day ${d % m + 1}`;
}

// A number of days in the most natural unit: "5 days", "3 weeks", "4 months", "1.5 years".
function span(days) {
  const m = DAYS_PER_MONTH(), y = 12 * m;
  const fmt = (v, unit) => `${+v.toFixed(1)} ${unit}${Math.abs(v - 1) < 1e-9 ? "" : "s"}`;
  if (days < 14) return fmt(days, "day");
  if (days < 2 * m) return fmt(days / 7, "week");
  if (days < 2 * y) return fmt(days / m, "month");
  return fmt(days / y, "year");
}

// Rates: the simulation works per day; people think per year.
const perYear = (daily) => (1 + daily) ** DAYS_PER_YEAR() - 1;
const perDay = (yearly) => (1 + yearly) ** (1 / DAYS_PER_YEAR()) - 1;
const pctYear = (daily, digits = 1) => `${(perYear(daily) * 100).toFixed(digits)}% a year`;

// ---------- Dashboard: the economy at a glance ----------

// Key figures recorded each day while you play (for the dashboard's trend lines).
const trend = [];
function recordTrend() {
  if (!state || (trend.length && trend[trend.length - 1].day === state.tick)) return;
  if (trend.length && trend[trend.length - 1].day > state.tick) trend.length = 0;   // a new game
  const L = state.market.labor;
  trend.push({
    day: state.tick,
    gdp: state.macro?.gdp_real ?? 0,
    inflation: state.macro?.inflation ?? 0,
    unemployment: L.offered ? L.idle / L.offered : 0,
    wage: state.market.prices.labor,
    people: state.agents.length,
  });
  if (trend.length > 2000) trend.splice(0, trend.length - 2000);
}

// The record from about ``days`` ago (null until there is that much history).
const ago = (days) => {
  const now = trend[trend.length - 1];
  if (!now) return null;
  for (let i = trend.length - 1; i >= 0; i--) if (now.day - trend[i].day >= days) return trend[i];
  return null;
};

function gini(values) {
  const v = values.filter(x => x >= 0).sort((a, b) => a - b), n = v.length, total = v.reduce((a, b) => a + b, 0);
  if (n < 2 || total <= 0) return 0;
  return v.reduce((a, x, i) => a + (2 * (i + 1) - n - 1) * x, 0) / (n * total);
}

function kpiTile(label, value, note, delta = null, good = null) {
  const tile = Object.assign(document.createElement("div"), { className: "kpi" });
  tile.append(Object.assign(document.createElement("div"), { className: "kpi-label", textContent: label }),
              Object.assign(document.createElement("div"), { className: "kpi-value", textContent: value }));
  if (delta) {
    const tone = good === null ? "" : good ? " good" : " bad";
    tile.append(Object.assign(document.createElement("div"), { className: "kpi-delta" + tone, textContent: delta }));
  }
  tile.append(Object.assign(document.createElement("div"), { className: "kpi-note", textContent: note }));
  return tile;
}

function renderDashboard() {
  const m = state.market, macro = state.macro, b = state.banking, g = state.government;
  const L = m.labor;
  const month = ago(DAYS_PER_MONTH());
  const unemp = L.offered ? L.idle / L.offered : 0;
  const arrow = (now, then, fmt, upIsGood) => {
    if (then === undefined || then === null || !isFinite(then)) return [null, null];
    const d = now - then;
    if (Math.abs(d) < 1e-9) return ["no change this month", null];
    return [`${d > 0 ? "▲" : "▼"} ${fmt(Math.abs(d))} this month`, upIsGood === null ? null : (d > 0) === upIsGood];
  };
  const money = (v) => usd(v).replace(/\.\d\d$/, "");
  const tiles = [];
  const [popD, popG] = arrow(state.agents.length, month?.people, v => `${Math.round(v)}`, true);
  tiles.push(kpiTile("Population", `${state.agents.length}`, "people alive", popD, popG));
  if (macro) {
    const [gD, gG] = arrow(macro.gdp_real, month?.gdp, v => money(v), true);
    tiles.push(kpiTile("Real GDP", money(macro.gdp_real), "last year's output at year-ago prices", gD, gG));
    const sinceStart = macro.accounts_steps < DAYS_PER_YEAR();
    tiles.push(kpiTile("Inflation", `${(macro.inflation * 100).toFixed(1)}%`,
                       sinceStart ? `consumer prices vs day 1 (first year: ${span(macro.accounts_steps)} so far)` : "consumer prices vs a year ago", null,
                       Math.abs(macro.inflation) < 0.1 ? null : false));
  }
  const [uD, uG] = arrow(unemp * 100, month ? month.unemployment * 100 : null, v => `${v.toFixed(1)} pts`, false);
  tiles.push(kpiTile("Unemployment", `${(unemp * 100).toFixed(1)}%`, "work offered that nobody hired", uD, uG));
  const [wD, wG] = arrow(m.prices.labor, month?.wage, v => usd(v), true);
  tiles.push(kpiTile("Wage", usd(m.prices.labor), "per unit of labour (a day's work)", wD, wG));
  tiles.push(kpiTile("Inequality", gini(state.agents.map(a => a.money + (a.deposits || 0))).toFixed(2),
                     "Gini of money: 0 = equal, 1 = one person has it all"));
  if (b?.industry_active) tiles.push(kpiTile("Bank loans", money(b.loans), `${b.open} banks open · money supply ${money(b.money_supply)}`));
  if (g?.enabled) tiles.push(kpiTile("Taxes", money(Object.values(g.step_revenue).reduce((a, v) => a + v, 0)) + " / day",
                                     `treasury ${money(g.treasury)}`));
  ui.dashKpis.replaceChildren(...tiles);

  // Trend lines (as recorded while playing).
  const charts = [
    ["Real GDP", t => t.gdp, v => money(v)],
    ["Unemployment", t => t.unemployment, v => `${(v * 100).toFixed(0)}%`],
    ["Wage", t => t.wage, v => usd(v)],
    ["Inflation", t => t.inflation, v => `${(v * 100).toFixed(0)}%`],
  ];
  ui.dashCharts.replaceChildren(...charts.map(([title, f, fmt]) => {
    const box = Object.assign(document.createElement("div"), { className: "mini-chart" });
    const values = trend.map(f);
    const last = values.length ? values[values.length - 1] : 0;
    box.append(Object.assign(document.createElement("div"), { className: "mini-head",
      innerHTML: `<span>${title}</span><b>${fmt(last)}</b>` }));
    const canvas = Object.assign(document.createElement("canvas"), { width: 320, height: 70 });
    box.append(canvas);
    requestAnimationFrame(() => drawSpark(canvas, values, null));
    return box;
  }));

  // Alerts: plain-language things worth a look.
  const alerts = [];
  const needy = state.agents.filter(a => a.wants.length).length;
  if (needy / (state.agents.length || 1) > 0.25) alerts.push(["bad", `${needy} people can't meet a need right now (${Math.round(100 * needy / state.agents.length)}%).`]);
  if (unemp > 0.5) alerts.push(["warn", `Half or more of the work offered finds no employer (${(unemp * 100).toFixed(0)}%).`]);
  if (macro && macro.inflation > 0.2) alerts.push(["warn", `Prices rose ${(macro.inflation * 100).toFixed(0)}% over the last year.`]);
  if (macro && macro.inflation < -0.1) alerts.push(["warn", `Prices fell ${(-macro.inflation * 100).toFixed(0)}% over the last year (deflation).`]);
  if (b?.failed) alerts.push(["bad", `${b.failed} bank(s) have failed.`]);
  if (b?.cb_loans > 0) alerts.push(["warn", `Banks owe the central bank ${money(b.cb_loans)} (emergency loans).`]);
  if (!alerts.length) alerts.push(["good", "Nothing alarming: people can meet their needs and prices are steady."]);
  ui.dashAlerts.replaceChildren(...alerts.map(([tone, text]) =>
    Object.assign(document.createElement("li"), { className: tone, textContent: text })));

  // Price movers over the last month.
  const back = (h) => h.length > DAYS_PER_MONTH() ? h[h.length - 1 - DAYS_PER_MONTH()] : h[0];
  const moves = activeGoods().map(g2 => {
    const h = m.price_history[g2] || [];
    const then = back(h);
    return [g2, then ? m.prices[g2] / then - 1 : 0];
  }).sort((a, b2) => Math.abs(b2[1]) - Math.abs(a[1])).slice(0, 6);
  ui.dashMovers.replaceChildren(...moves.map(([g2, ch]) => {
    const row = Object.assign(document.createElement("div"), { className: "mover" });
    row.append(Object.assign(document.createElement("span"), { textContent: label(g2) }),
               Object.assign(document.createElement("span"), { className: "mono", textContent: usd(m.prices[g2]) }),
               Object.assign(document.createElement("b"), { className: ch >= 0 ? "up" : "down",
                 textContent: `${ch >= 0 ? "▲" : "▼"} ${Math.abs(ch * 100).toFixed(0)}%` }));
    return row;
  }));

  const sh = state.shocks;
  const dashShocks = $("dash-shocks");
  if (dashShocks && sh) {
    const active = [];
    for (const s of sh.shortages || []) active.push(`Shortage: ${s.goods.join(", ")} -${Math.round(s.severity * 100)}% (ends day ${s.ends})`);
    for (const e of sh.epidemics || []) active.push(`Epidemic: ${e.infected} infected, ${e.immune} immune, ${e.total_deaths} died`);
    dashShocks.textContent = active.length ? `Active: ${active.join(" · ")}` : "No active shocks.";
  }

  ui.dashEvents.replaceChildren(...[...state.events].reverse().slice(0, 6).map(ev => {
    const li = document.createElement("li");
    li.append(Object.assign(document.createElement("span"), { className: "ev-day", textContent: calendar(ev.tick) }),
              Object.assign(document.createElement("span"), { textContent: ev.message }));
    return li;
  }));
}

// ---------- Products tab: every product's KPIs ----------

// Sorted by layer until a column name is clicked: then by that column, low to high (A to Z),
// and high to low when it is clicked again.
const productView = { query: "", sort: null, desc: false, open: null };

// The table's columns: heading, sort value (text sorts A to Z), and cell text.
const PRODUCT_COLUMNS = [
  { key: "name", title: "Product", value: r => label(r.g).toLowerCase() },
  { key: "price", title: "Price", value: r => r.price },
  { key: "change", title: "20-day change", value: r => r.change },
  { key: "made", title: "Made /day", value: r => r.made },
  { key: "consumed", title: "Consumed /day", value: r => r.consumed },
  { key: "used", title: "Inputs /day", value: r => r.used },
  { key: "held", title: "Held", value: r => r.held },
  { key: "owners", title: "Producers", value: r => r.owners },
  { key: "pressure", title: "Buyers : sellers", value: r => r.pressure },
  { key: "yield", title: "Profit yield /yr", value: r => r.yield },
];

function productRows() {
  const m = state.market;
  const back = (g) => { const h = m.price_history[g] || []; return h.length > 20 ? h[h.length - 21] : h[0]; };
  return activeGoods().map(g => {
    const price = m.prices[g], before = back(g);
    return {
      g, info: industry(g), meta: CATALOG_INFO[g], price,
      change: before ? price / before - 1 : 0,
      made: m.produced_recent[g] || 0, consumed: m.consumed_recent[g] || 0,
      used: m.used_recent[g] || 0, expired: m.expired_recent[g] || 0,
      held: m.units[g] || 0, owners: m.owners?.[g] || 0, producing: m.producing?.[g] || 0,
      shares: m.assets[g] || 0, capacity: m.asset_output[g] || 0,
      buyers: m.buyers[g] || 0, sellers: m.sellers[g] || 0,
      pressure: ((m.buyers[g] || 0) + 1) / ((m.sellers[g] || 0) + 1),
      yield: m.industry_yield?.[g] ?? 0,
      concentration: m.concentration[g] || 0, buyerPower: m.buyer_concentration?.[g] || 0,
      depreciation: state.rules.depreciation?.[g] ?? 0, shelf: state.rules.expiry_enabled ? state.rules.shelf_life[g] : 0,
    };
  });
}

function renderProducts() {
  let rows = productRows();
  const all = rows;
  const q = productView.query;
  if (q) rows = rows.filter(r => label(r.g).toLowerCase().includes(q) || r.meta.sector.toLowerCase().includes(q));
  const column = PRODUCT_COLUMNS.find(c => c.key === productView.sort);
  if (column) {
    const dir = productView.desc ? -1 : 1;
    rows.sort((a, b) => {
      const x = column.value(a), y = column.value(b);
      const order = typeof x === "string" ? x.localeCompare(y) : x - y;
      return (order || label(a.g).localeCompare(label(b.g))) * dir;
    });
  } else {
    rows.sort((a, b) => a.info.layer - b.info.layer || label(a.g).localeCompare(label(b.g)));   // by layer
  }

  // Summary cards for the whole market.
  const sum = (f) => all.reduce((a, r) => a + f(r), 0);
  const cards = [
    ["Products", `${all.length}`, `${new Set(all.map(r => r.info.layer)).size} layers`],
    ["Output", usd(sum(r => r.made * r.price)), "value made per day"],
    ["Consumed", usd(sum(r => r.consumed * r.price)), "value used up by people per day"],
    ["Rising / falling", `${all.filter(r => r.change > 0.02).length} / ${all.filter(r => r.change < -0.02).length}`,
      "prices up / down over 20 days"],
  ];
  ui.productSummary.innerHTML = "";
  for (const [l, v, n] of cards) {
    const c = Object.assign(document.createElement("div"), { className: "stat" });
    c.append(Object.assign(document.createElement("div"), { className: "stat-label", textContent: l }),
             Object.assign(document.createElement("div"), { className: "stat-value", textContent: v }),
             Object.assign(document.createElement("div"), { className: "stat-note", textContent: n }));
    ui.productSummary.append(c);
  }

  const t = ui.productTable;
  t.innerHTML = "";
  const head = t.createTHead().insertRow();
  for (const c of PRODUCT_COLUMNS) {
    const sorted = productView.sort === c.key;
    const th = Object.assign(document.createElement("th"), { className: "sortable" + (sorted ? " sorted" : ""),
      textContent: c.title + (sorted ? (productView.desc ? " ▼" : " ▲") : ""),
      title: sorted ? (productView.desc ? "High to low: click for low to high" : "Low to high: click for high to low")
                    : "Click to sort low to high (A to Z)" });
    th.setAttribute("aria-sort", sorted ? (productView.desc ? "descending" : "ascending") : "none");
    th.onclick = () => {
      productView.desc = productView.sort === c.key ? !productView.desc : false;
      productView.sort = c.key;
      renderProducts();
    };
    head.append(th);
  }
  const body = t.createTBody();
  const pct = (v) => `${v >= 0 ? "+" : ""}${(v * 100).toFixed(1)}%`;
  for (const r of rows) {
    const tr = body.insertRow();
    tr.className = "product-row" + (productView.open === r.g ? " open" : "");
    tr.onclick = () => { productView.open = productView.open === r.g ? null : r.g; renderProducts(); };
    const name = document.createElement("td");
    name.append(Object.assign(document.createElement("b"), { textContent: label(r.g) }),
                Object.assign(document.createElement("small"), { textContent: ` L${r.info.layer} · ${r.meta.sector}` }));
    const change = Object.assign(document.createElement("td"), { textContent: pct(r.change),
      className: r.change > 0.02 ? "up" : r.change < -0.02 ? "down" : "" });
    tr.append(name, Object.assign(document.createElement("td"), { textContent: usd(r.price) }), change,
      ...[r.made.toFixed(2), r.consumed.toFixed(2), r.used.toFixed(2), Math.round(r.held),
          `${r.producing} of ${r.owners}`, `${r.buyers} : ${r.sellers}`, pct(r.yield)].map(v => Object.assign(document.createElement("td"), { textContent: v })));
    if (productView.open === r.g) {
      const d = body.insertRow();
      d.className = "product-detail";
      const cell = d.insertCell();
      cell.colSpan = 10;
      const recipe = Object.entries(state.rules.inputs[r.g] || {}).map(([k, n]) => `${n} ${label(k).toLowerCase()}`).join(" + ");
      const effects = Object.entries(r.info.effects || {}).map(([n, v]) => `${n} ${v > 0 ? "−" : "+"}${Math.abs(v).toFixed(3)}`).join(", ");
      const lines = [
        `${r.meta.industry} (${r.meta.sector}) · layer ${r.info.layer} · made from ${recipe || "labour and capital only (primary)"}`,
        `Effect per unit: ${effects || "none (an input only)"}${r.shelf ? ` · keeps ${r.shelf} steps` : " · never expires"}`,
        `Industry: ${r.shares.toFixed(2)} asset shares owned by ${r.owners} agents (${r.producing} produced today) · ` +
          `can make ${r.capacity.toFixed(2)} /day fully staffed · wears out ${(r.depreciation * 100).toFixed(0)}% a year`,
        `Market: ${r.buyers} buyers vs ${r.sellers} sellers (pressure ×${Math.pow(r.pressure, state.rules.price_elasticity[r.g]).toFixed(2)}) · ` +
          `seller concentration ${r.concentration.toFixed(2)} · buyer power ${r.buyerPower.toFixed(2)} · expired ${r.expired.toFixed(2)} /day`,
      ];
      for (const text of lines) cell.append(Object.assign(document.createElement("div"), { textContent: text }));
      const canvas = Object.assign(document.createElement("canvas"), { className: "product-spark", width: 600, height: 80 });
      cell.append(canvas);
      drawSpark(canvas, state.market.price_history[r.g] || []);
    }
  }
}

// A small price chart (no axes): the line, its min and max.
function drawSpark(canvas, values, caption = "price") {
  const c = canvas.getContext("2d");
  if (values.length < 2) return;
  const lo = Math.min(...values), hi = Math.max(...values), span = hi - lo || 1;
  c.strokeStyle = cssVar("--accent");
  c.lineWidth = 2;
  c.beginPath();
  values.forEach((v, i) => {
    const x = i / (values.length - 1) * (canvas.width - 4) + 2, y = canvas.height - 14 - (v - lo) / span * (canvas.height - 24);
    i ? c.lineTo(x, y) : c.moveTo(x, y);
  });
  c.stroke();
  c.fillStyle = cssVar("--muted");
  c.font = "11px sans-serif";
  if (caption) c.fillText(`${caption}: ${usd(lo)} – ${usd(hi)} over the last ${span(values.length)}`, 2, canvas.height - 2);
}

ui.productSearch.oninput = () => { productView.query = ui.productSearch.value.trim().toLowerCase(); renderProducts(); };

// ---------- Banking (in the Government tab) ----------

let bankDirty = false;   // the banking form has unsaved edits: don't overwrite them

function fillBanking(force = false) {
  if (bankDirty && !force) return;
  bankDirty = false;
  const b = state.banking;
  ui.bankEnabled.checked = b.enabled;
  $("bank-compete").checked = !!b.rate_competition;
  ui.bankDeposit.value = +(perYear(b.deposit_rate) * 100).toFixed(2);   // shown % a year, kept per day
  ui.bankSpread.value = +(perYear(b.loan_spread) * 100).toFixed(2);
  ui.bankReserve.value = +(b.liquidity * 100).toFixed(2);
  ui.bankMinCapital.value = b.min_capital;
  ui.bankIncomeShare.value = +(b.loan_income_share * 100).toFixed(2);
  $("mort-years").value = b.mortgage_years;
  $("mort-dti").value = +(b.mortgage_dti * 100).toFixed(1);
  $("mort-ltv").value = +(b.mortgage_ltv * 100).toFixed(1);
  $("mort-premium").value = +(perYear(b.mortgage_premium) * 100).toFixed(2);
  $("mort-default").value = b.mortgage_default_days;
}

function renderBanking() {
  const b = state.banking;
  fillBanking();
  ui.bankForm.querySelectorAll("input, button").forEach(el => { el.disabled = !b.industry_active; });
  const stats = b.industry_active ? [
    ["Banks", `${b.open} open`, `${b.closed} closed · ${b.failed} failed`],
    ["Rates", `${(perYear(b.deposit_rate_now) * 100).toFixed(1)}% / ${(perYear(b.loan_rate_now) * 100).toFixed(1)}%`, "deposits / loans, a year"],
    ["Deposits", usd(b.deposits), `${usd(b.reserves)} held as reserves`],
    ["Loans", usd(b.loans), "outstanding"],
    ["Money supply", usd(b.money_supply), "cash (people + companies) + deposits"],
    ["Money multiplier", `×${b.multiplier.toFixed(2)}`, "money supply ÷ (cash + reserves)"],
    ["Credit limit", `${(b.loan_income_share * 100).toFixed(0)}% of a month`, `of each borrower's income (${b.month_steps} days)`],
    ["Mortgages", `${b.mortgages}`, `${usd(b.mortgage_debt)} owed · ${(perYear(b.mortgage_rate_now) * 100).toFixed(1)}% a year over ` +
      `${b.mortgage_years} years · ${b.foreclosures} foreclosures`],
    ["Reserves at the central bank", usd(b.cb_reserves), `required: ${(b.reserve_requirement * 100).toFixed(0)}% of deposits` +
      (b.cb_loans ? ` · owe it ${usd(b.cb_loans)}` : "")],
    ["Basel (central bank)", b.capital_ratio ? `${(b.capital_ratio * 100).toFixed(1)}% of loans` : "none",
      b.capital_ratio ? "equity a bank must hold; set in the Government tab" : "government off: no capital rule"],
    ["Kept by companies", usd(state.market.company_cash), `${usd(state.market.retained_total)} of profits retained so far`],
  ] : [["Banking", "not in this game", "the banking industry was left out (setup screen)"]];
  ui.bankStats.innerHTML = "";
  for (const [label, value, note] of stats) {
    const card = Object.assign(document.createElement("div"), { className: "stat" });
    card.append(Object.assign(document.createElement("div"), { className: "stat-label", textContent: label }),
                Object.assign(document.createElement("div"), { className: "stat-value", textContent: value }),
                Object.assign(document.createElement("div"), { className: "stat-note", textContent: note }));
    ui.bankStats.append(card);
  }
  ui.bankList.innerHTML = "";
  for (const bank of b.banks) {
    const card = Object.assign(document.createElement("div"), { className: `bank-card ${bank.status.replace(" ", "-")}` });
    const head = Object.assign(document.createElement("div"), { className: "bank-head" });
    head.append(Object.assign(document.createElement("b"), { textContent: bank.name }),
                Object.assign(document.createElement("span"), { className: "bank-status", textContent: bank.status }));
    const ratio = bank.loans > 0 ? `${(bank.equity / bank.loans * 100).toFixed(0)}% of loans` : "no loans";
    const depRate = `${(perYear(bank.deposit_rate ?? b.deposit_rate_now) * 100).toFixed(2)}%/yr`;
    const lines = [
      `Equity ${usd(bank.equity)} (${ratio}; founder put in ${usd(bank.capital_in)}) · deposit rate ${depRate}`,
      `Deposits ${usd(bank.deposits)} from ${bank.depositors} · reserves ${usd(bank.reserves)}`,
      `Loans ${usd(bank.loans)} to ${bank.borrowers} · banking services ${bank.services} units · plant ${bank.shares} shares`,
      `Interest in ${usd(bank.interest_received)} · out ${usd(bank.interest_paid)} · dividends ${usd(bank.dividends)}` +
        ` · retained ${usd(bank.retained)} (owner pays out ${Math.round((bank.payout_ratio ?? 0) * 100)}% of profit)` +
        (bank.written_off ? ` · written off ${usd(bank.written_off)}` : ""),
    ];
    card.append(head, ...lines.map(t => Object.assign(document.createElement("div"), { className: "bank-line", textContent: t })));
    ui.bankList.append(card);
  }
}

ui.bankForm.oninput = () => { bankDirty = true; };
ui.bankRevert.onclick = () => { ui.bankStatus.hidden = true; fillBanking(true); };
ui.bankForm.onsubmit = async (e) => {
  e.preventDefault();
  try {
    const next = await api("/api/banking", {
      enabled: ui.bankEnabled.checked,
      rate_competition: $("bank-compete").checked,
      deposit_rate: perDay(Number(ui.bankDeposit.value) / 100),
      loan_spread: perDay(Number(ui.bankSpread.value) / 100),
      liquidity: Number(ui.bankReserve.value) / 100,
      min_capital: Number(ui.bankMinCapital.value),
      loan_income_share: Number(ui.bankIncomeShare.value) / 100,
      mortgage_years: Number($("mort-years").value),
      mortgage_dti: Number($("mort-dti").value) / 100,
      mortgage_ltv: Number($("mort-ltv").value) / 100,
      mortgage_premium: perDay(Number($("mort-premium").value) / 100),
      mortgage_default_days: Number($("mort-default").value),
    });
    bankDirty = false;
    render(next);
    ui.bankStatus.textContent = "Banking settings apply from tomorrow.";
    ui.bankStatus.className = "status";
  } catch (err) {
    ui.bankStatus.textContent = err.message;
    ui.bankStatus.className = "status error";
  }
  ui.bankStatus.hidden = false;
};

// ---------- Manage tab: one form for creating and editing ----------

function buildForm() {
  for (const group of FIELD_GROUPS) {
    const fs = document.createElement("fieldset");
    const legend = document.createElement("legend");
    legend.textContent = group.legend;
    fs.append(legend);
    for (const f of group.fields) {
      const label = document.createElement("label");
      if (f.full) label.className = "full";
      const input = document.createElement("input");
      input.name = f.path;
      input.type = f.type || "number";
      for (const attr of ["min", "max", "step"]) if (f[attr] !== undefined) input[attr] = f[attr];
      input.oninput = () => { input.classList.add("dirty"); updateBalance(); };
      label.append(f.label, input);
      fs.append(label);
    }
    if (group.collapsed) {   // long lists (one field per good) start folded away
      const box = Object.assign(document.createElement("details"), { className: "field-group" });
      box.append(Object.assign(document.createElement("summary"), { textContent: group.legend }));
      legend.remove();
      box.append(fs);
      ui.formFields.append(box);
      continue;
    }
    ui.formFields.append(fs);
  }
}

const input = (path) => ui.form.elements[path];

function renderChips() {
  ui.chips.innerHTML = "";
  ui.newAgent.classList.toggle("active", editingId === null);
  const editing = editingId !== null && agentById(editingId);
  let list = state.agents.slice(0, CARD_LIMIT);
  if (editing && !list.includes(editing)) list = [editing, ...list];
  for (const a of list) {
    const chip = document.createElement("button");
    chip.className = "chip" + (a.id === editingId ? " active" : "");
    const dot = document.createElement("span");
    dot.className = "dot";
    dot.style.background = a.color;
    chip.append(dot, a.name);
    chip.onclick = () => openEditor(a.id);
    ui.chips.append(chip);
  }
  if (state.agents.length > list.length) {
    const more = document.createElement("span");
    more.className = "count";
    more.textContent = `+${state.agents.length - list.length} more: tap one on the map or use Edit on its card`;
    ui.chips.append(more);
  }
}

// Fill the form. Untouched ("clean") fields follow the live state; edited ones are left alone.
function refreshForm(force = false) {
  const agent = editingId === null ? null : agentById(editingId);
  if (agent && !agent.full) { ensureDetail(); return; }   // its full details are on the way
  ui.formTitle.textContent = agent ? `Edit ${agent.name}` : "New agent";
  ui.formSubmit.textContent = agent ? "Save changes" : "Create agent";
  ui.formRemove.hidden = !agent;
  for (const f of FIELDS) {
    const el = input(f.path);
    if ((el.classList.contains("dirty") || el === document.activeElement) && !force) continue;
    el.classList.remove("dirty");
    el.placeholder = agent ? "" : (f.placeholder || "from rules");
    el.value = agent ? f.get(agent) : defaultValue(f.path);
  }
  updateBalance();
}

// New agents start from the game's rules (set on the setup screen). A rule that is a
// distribution shows blank: the server draws a value from it.
const RULE_BACKED = ["inventory", "assets", "labor_capacity", "rates", "money", "sleep_recovery", "movement", "payout_ratio", "risk_appetite", "lavishness"];
function defaultValue(path) {
  if (!RULE_BACKED.includes(path.split(".")[0])) return "";  // name, x, y, needs: server picks
  const spec = getPath(state.rules, path);
  return typeof spec === "number" ? spec : "";
}

// A blank field counts as the rule's average (for the balance preview).
function fieldValue(path) {
  const value = input(path).value;
  return value === "" ? spreadMean(getPath(state.rules, path)) : Number(value);
}

function openEditor(id) {
  editingId = id;
  selectedId = id;
  setStatus("");
  if (activeTab !== "manage") showTab("manage");
  refreshForm(true);
  render(state);
}

// Body for the API: when editing, only changed fields; when creating, every non-blank field.
function formBody() {
  const body = {};
  for (const f of FIELDS) {
    const el = input(f.path);
    if (editingId !== null && !el.classList.contains("dirty")) continue;
    if (el.value === "") {
      if (editingId !== null) throw new Error(`${f.label} can't be empty`);
      continue;
    }
    const value = f.type === "text" ? el.value : Number(el.value);
    const [group, key] = f.path.split(".");
    if (key) (body[group] ||= {})[key] = value;
    else body[group] = value;
  }
  return body;
}

function setStatus(message, isError = false) {
  ui.formStatus.hidden = !message;
  ui.formStatus.textContent = message;
  ui.formStatus.className = "status" + (isError ? " error" : "");
}

// Per resource: units used per step (need rate / relief per unit) vs units made per step (1 / N).
function updateBalance() {
  ui.balance.innerHTML = "";
  // Goods come only from its assets (when staffed); labour from the agent itself.
  // Per need: how fast it grows vs how much relief its own industries make (at full staffing).
  for (const need of state.consumer_needs) {
    const grows = fieldValue(`rates.${need}`);
    const made = activeGoods().filter(g => (industry(g).effects[need] || 0) > 0)
      .reduce((sum, g) => sum + fieldValue(`assets.${g}`) * state.market.asset_output_each[g] * (industry(g).effects[need] || 0), 0);
    const net = made - grows;
    const line = document.createElement("span");
    const even = Math.abs(net) < 1e-9;
    line.className = even ? "" : net < 0 ? "short" : "surplus";
    line.textContent = `${need}: grows ${grows.toFixed(3)} · its industries make ${made.toFixed(3)} of relief per day → ` +
      (even ? "balanced" : net < 0 ? `buys ${(-net).toFixed(3)}/day` : `sells ${net.toFixed(3)}/day`);
    ui.balance.append(line);
  }
  const jobs = GOODS.reduce((sum, g) => sum + fieldValue(`assets.${g}`) * state.market.asset_labor[g], 0);
  const work = fieldValue("labor_capacity");
  const labourLine = document.createElement("span");
  labourLine.textContent = `labour: makes ${work.toFixed(3)} · its assets employ ${jobs.toFixed(3)} per day → ` +
    (work >= jobs ? `sells ${(work - jobs).toFixed(3)}/day` : `hires ${(jobs - work).toFixed(3)}/day`);
  ui.balance.append(labourLine);
  // Sleep rises at g while awake (0.3 -> 0.5) and falls at r while resting (0.5 -> 0.3),
  // so the agent spends g / (g + r) of its time asleep.
  const g = fieldValue("rates.sleep");
  const r = fieldValue("sleep_recovery");
  const line = document.createElement("span");
  line.className = r ? "" : "short";
  line.textContent = r
    ? `sleep: rises ${g.toFixed(3)} · recovers ${r.toFixed(3)} per day at rest → asleep ${(100 * g / (g + r || 1)).toFixed(0)}% of the time`
    : "sleep: recovery is 0, so a tired agent stops forever";
  ui.balance.append(line);
}

ui.newAgent.onclick = () => { editingId = null; setStatus(""); refreshForm(true); render(state); };
ui.formRevert.onclick = () => { setStatus(""); refreshForm(true); };
ui.formRemove.onclick = async () => {
  const agent = agentById(editingId);
  if (!agent || !confirm(`Remove ${agent.name}?`)) return;
  try {
    const next = await api(`/api/agents/${agent.id}`, undefined, "DELETE");
    editingId = null;
    refreshForm(true);
    render(next);
    ui.agentCount.value = state.agents.length;
    setStatus(`Removed ${agent.name}.`);
  } catch (err) {
    setStatus(err.message, true);
  }
};
ui.form.onsubmit = async (e) => {
  e.preventDefault();
  try {
    const body = formBody();
    if (editingId !== null && !Object.keys(body).length) return setStatus("Nothing changed.");
    const path = editingId === null ? "/api/agents" : `/api/agents/${editingId}`;
    const next = await api(path, body);
    if (editingId === null) {
      editingId = next.agents[next.agents.length - 1].id;  // switch to editing the new agent
      setStatus(`Created ${next.agents[next.agents.length - 1].name}.`);
    } else {
      setStatus("Saved.");
    }
    state = next;
    refreshForm(true);
    render(next);
    ui.agentCount.value = state.agents.length;
  } catch (err) {
    setStatus(err.message, true);
  }
};

canvas.addEventListener("click", (e) => {
  if (!state) return;
  const rect = canvas.getBoundingClientRect();
  const x = (e.clientX - rect.left) * (state.width / rect.width);
  const y = (e.clientY - rect.top) * (state.height / rect.height);
  let best = null, bestDist = Math.max(20, 22 * state.width / rect.width);  // ~22px finger on screen
  for (const a of state.agents) {
    const d = Math.hypot(a.x - x, a.y - y);
    if (d < bestDist) { best = a; bestDist = d; }
  }
  if (best && activeTab === "manage") return openEditor(best.id);
  selectedId = best ? best.id : null;
  render(state);
  ensureDetail();
});

ui.step.onclick = () => step(1);
ui.run100.onclick = () => step(DAYS_PER_MONTH());   // one month
ui.play.onclick = () => setPlaying(!playing);
ui.stepsPerTick.onchange = () => { if (playing) setPlaying(true); };
ui.interval.oninput = () => {
  ui.intervalLabel.textContent = `${ui.interval.value} ms`;
  if (playing) setPlaying(true);
};
ui.reset.onclick = async () => {
  setPlaying(false);
  selectedId = null;
  editingId = null;
  try {
    render(await api("/api/reset", { agents: Number(ui.agentCount.value), seed: ui.seed.value }));
    refreshForm(true);
  } catch (err) {
    alert(err.message);
  }
};
ui.showRange.onchange = () => state && draw();
document.addEventListener("keydown", (e) => {
  if (["INPUT", "SELECT", "BUTTON"].includes(e.target.tagName) || document.body.classList.contains("setup-open")) return;
  if (e.code === "Space") { e.preventDefault(); setPlaying(!playing); }
  if (e.code === "ArrowRight" && !playing) step(1);
});

function updateRegimeBadge() {
  const el = $("regime-badge");
  if (!el || !state) return;
  const macro = state.macro;
  const l = state.market?.labor;
  const unemp = l && l.offered > 0 ? Math.max(0, l.idle) / l.offered : 0;
  let labelText = "Early cycle", tone = "neutral";
  if (macro && macro.accounts_steps >= DAYS_PER_MONTH()) {
    const inf = macro.inflation || 0;
    if (inf > 0.12 && unemp > 0.15) { labelText = "Stagflation"; tone = "bad"; }
    else if (inf > 0.12) { labelText = "Overheating"; tone = "warn"; }
    else if (unemp > 0.15) { labelText = "Recession"; tone = "bad"; }
    else if (inf < -0.02) { labelText = "Deflation"; tone = "warn"; }
    else { labelText = "Expansion"; tone = "good"; }
  }
  el.textContent = labelText;
  el.className = `regime-badge ${tone}`;
}

const themeBtn = $("theme-toggle");
function applyTheme(mode) {
  document.documentElement.dataset.theme = mode;
  try { localStorage.setItem("econsim-theme", mode); } catch (_) {}
  if (themeBtn) themeBtn.textContent = mode === "dark" ? "Light mode" : "Dark mode";
}
if (themeBtn) {
  const saved = (() => { try { return localStorage.getItem("econsim-theme"); } catch (_) { return null; } })();
  const initial = saved || (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
  applyTheme(initial);
  themeBtn.onclick = () => applyTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark");
}

async function triggerShock(payload) {
  try {
    render(await api("/api/shock", payload));
  } catch (err) {
    alert(err.message);
  }
}
if ($("shock-shortage")) $("shock-shortage").onclick = () => triggerShock({ kind: "shortage", severity: 0.5, days: 60 });
if ($("shock-disaster")) $("shock-disaster").onclick = () => triggerShock({ kind: "disaster", house_loss: 0.2 });
if ($("shock-epidemic")) $("shock-epidemic").onclick = () => triggerShock({ kind: "epidemic", initial_infected: 3, contagion_rate: 0.15, lethality_rate: 0.01 });

buildForm();
api("/api/state").then(s => {
  ui.agentCount.value = s.agents.length;
  state = s;
  refreshForm(true);
  render(s);
  updateRegimeBadge();
});
