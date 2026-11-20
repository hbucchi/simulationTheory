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
    { path: "movement", label: "Movement (px/step)", min: 1, max: 200, step: 1, get: a => a.movement, placeholder: "from rules" },
    { path: "money", label: "Money", min: 0, step: 0.01, get: a => a.money },
    { path: "x", label: "X", min: 0, max: 1024, step: 1, get: a => Math.round(a.x), placeholder: "random" },
    { path: "y", label: "Y", min: 0, max: 1024, step: 1, get: a => Math.round(a.y), placeholder: "random" },
  ]},
  { legend: "Current needs (0 = satisfied, 1 = desperate)", fields: NEEDS.map(n => (
    { path: `needs.${n}`, label: cap(n), min: 0, max: 1, step: 0.01, get: a => a.needs[n], placeholder: "random" }))},
  { legend: "Need growth per step", fields: NEEDS.map(n => (
    { path: `rates.${n}`, label: cap(n), min: 0, max: 1, step: 0.001, get: a => a.modules.NeedsDecay.rates[n] }))},
  { legend: "Rest: sleep recovered per step while standing still", fields: [
    { path: "sleep_recovery", label: "Sleep recovery", min: 0, max: 1, step: 0.01, get: a => a.modules.Rest.recovery }]},
  { legend: "Inventory (every good)", collapsed: true, fields: RESOURCES.map(r => (
    { path: `inventory.${r}`, label: label(r), min: 0, step: 1, get: a => a.inventory[r] ?? 0 }))},
  { legend: "Labour", fields: [
    { path: "labor_capacity", label: "Labour capacity per step", min: 0, step: 0.05, get: a => a.labor.capacity }]},
  { legend: "Personality", fields: [
    { path: "payout_ratio", label: "Pays out as dividends (share of profits)", min: 0, max: 1, step: 0.05,
      get: a => a.personality.payout_ratio, placeholder: "from rules" }]},
  { legend: "Industries owned (asset shares; 1 = one whole asset)", collapsed: true, fields: GOODS.map(r => (
    { path: `assets.${r}`, label: label(r), min: 0, step: 0.01, get: a => +(a.assets[r] ?? 0).toFixed(4) }))},
];
const FIELDS = FIELD_GROUPS.flatMap(g => g.fields);

let state = null;
let selectedId = null;
let editingId = null;   // agent shown in the Manage form; null = creating a new one
let activeTab = "overview";
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
  if (typeof refreshReport === "function") refreshReport();
  if (typeof reportVisible !== "undefined" && reportVisible) return;
  draw();
  if (activeTab === "overview") {
    renderMarket();
    renderAgents();
    renderEvents();
  } else if (activeTab === "banks") {
    renderBanking();
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
        `making ${made.toFixed(2)}/step` + (lost >= 0.005 ? ` · ${lost.toFixed(2)}/step expiring` : "") }));
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
    (flows[3] >= 0.005 ? ` · expired ${flows[3].toFixed(2)}` : "") + " /step · " +
    `${m.assets[g].toFixed(2)} shares (asset ${usd(m.asset_prices[g])})` });
  numbers.title = `Averages over the last 20 steps. Capacity ${m.asset_output[g].toFixed(2)}/step when fully staffed; ` +
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
    ["Capacity", `${L.capacity.toFixed(2)}/step · own assets ${L.own_use.toFixed(2)} · offered ${L.offered.toFixed(2)}`],
    ["Jobs", `${L.wanted.toFixed(2)} wanted · ${L.hired.toFixed(2)} hired (${L.workers_hired} workers)` +
      (L.gov_hired ? ` · government ${L.gov_hired.toFixed(2)}` : "")],
    ["Unused", `${L.unused.toFixed(2)}/step: ${L.withheld.toFixed(2)} not offered (no need to work) · ` +
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
        `Keeps ${usd(a.budget.total)} before investing: cash for what it needs now + ${a.budget.steps} steps × ` +
        `(living ${usd(a.budget.living)} + loan payments ${usd(a.budget.loans)} per step). ` +
        `Income ${usd(a.income)}/step.`],
        [a.budget.spare >= 0 ? "left to invest" : "short of budget", usd(Math.abs(a.budget.spare))]] : []),
      ["movement", a.depressed ? `${a.speed} px (depressed, ${a.movement} normally)` : `${a.speed} px`],
      ...GOODS.filter(r => a.assets[r]).map(r => {
        const price = state.market.asset_prices[r];
        return [`${label(r).toLowerCase()} industry`, `${a.assets[r].toFixed(2)} (worth ${usd(a.assets[r] * price)}, ` +
          `${(a.assets[r] * state.market.asset_output_each[r]).toFixed(2)}/step)`,
          `One whole ${r} asset costs ${usd(price)} now`];
      }),
      // Building project: capital goods held / needed.
      ...(a.project ? [["building", `${a.project.shares.toFixed(2)} ${label(a.project.good).toLowerCase()} asset(s): ` +
        Object.entries(a.project.need).map(([k, n]) => `${label(k).toLowerCase()} ${Math.min(a.inventory[k] ?? 0, n)}/${n}`).join(", "),
        `Started at step ${a.project.started}; dropped after ${state.rules.project_steps} steps`]] : []),
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
    const prod = !lab ? "details load when shown" : `labour ${lab.capacity_now.toFixed(2)}/step (capacity ${lab.capacity.toFixed(2)} × efficiency ` +
      `${lab.efficiency.toFixed(2)}) · wellbeing ${lab.wellbeing.toFixed(2)} · need for a job ${lab.job_need.toFixed(2)}` +
      (lab.offered ? ` · offers ${lab.offered.toFixed(2)} at ${usd(lab.asking_wage)}` : "") +
      (worked ? ` · worked ${worked}` : "") +
      (owned.length ? ` · its assets employ ${a.labor_need.toFixed(2)}/step` +
        (lab.bought ? ` (hired ${lab.bought.toFixed(2)})` : "") : "");
    activity.append(act);
    if (a.depressed) {
      const sad = document.createElement("b");
      sad.className = "depressed";
      sad.textContent = "depressed";
      activity.append(" · ", sad);
    }
    activity.append(` · ${prod}`);

    card.append(head, stats, meta, activity);
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
    li.append(`t${ev.tick}: `, msg);
    ui.events.append(li);
  }
}

// ---------- Tabs ----------

function showTab(name) {
  activeTab = name;
  for (const t of ui.tabs) {
    t.classList.toggle("active", t.dataset.tab === name);
    $(`tab-${t.dataset.tab}`).hidden = t.dataset.tab !== name;
  }
  if (name === "government") fillGovernment(true);
  if (name === "banks") fillBanking(true);
  render(state);
}
for (const t of ui.tabs) t.onclick = () => showTab(t.dataset.tab);

// ---------- Government tab ----------

// The policy inputs only follow the live state until you start editing them.
let govDirty = false;

function fillGovernment(force = false) {
  if (govDirty && !force) return;
  govDirty = false;
  const g = state.government;
  setGovInputs(g.min_rate * 100, g.labor_purchase);
  ui.govEnabled.checked = g.enabled;
  for (const el of ui.govForm.querySelectorAll("[data-policy]")) {
    const v = g[el.dataset.policy];
    if (el.type === "checkbox") el.checked = v;
    else el.value = +(v * Number(el.dataset.scale || 1)).toFixed(4);
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

function renderGovernment() {
  fillGovernment();
  const g = state.government;
  const m = state.market;
  const stats = [
    ["Policy rate", `${(g.min_rate * 100).toFixed(2)}%`, "minimum return on assets"],
    ["Labour hired", `${g.labor_purchase} / step`, "with newly created money"],
    ["Money created", usd(g.money_created), `${usd(g.last_spent)} in the last step`],
    ["Labour used up", g.labor_bought.toFixed(1), "in public works so far"],
    ["Money in the economy", usd(m.money), "held by agents"],
    ["Labour price", usd(m.prices.labor), `food ${usd(m.prices.food)} · water ${usd(m.prices.water)}`],
    ["Taxes last step", usd(Object.values(g.step_revenue).reduce((a, v) => a + v, 0)),
      `production ${usd(g.step_revenue.production)} · salary ${usd(g.step_revenue.wage)} · profit ${usd(g.step_revenue.profit)}`],
    ["Spending last step", usd(g.step_spent.benefits + g.step_spent.public_works + g.step_spent.transfers),
      `benefits ${usd(g.step_spent.benefits)} · public works ${usd(g.step_spent.public_works)} · transfers ${usd(g.step_spent.transfers)}`],
    ["Treasury", usd(g.treasury), `${usd(Object.values(g.revenue).reduce((a, v) => a + v, 0))} collected so far`],
    ["Central bank loans", usd(g.llr_outstanding), `to banks · ${usd(g.llr_lent)} lent so far`],
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
        [el.dataset.policy, el.type === "checkbox" ? el.checked : Number(el.value) / Number(el.dataset.scale || 1)])),
      min_rate: Number(ui.govRate.value) / 100,
      labor_purchase: Number(ui.govBuy.value),
      capital_ratio: Number(ui.govBasel.value) / 100,
    });
    govDirty = false;
    render(next);
    ui.govStatus.textContent = "Policy applied from the next step.";
    ui.govStatus.className = "status";
  } catch (err) {
    ui.govStatus.textContent = err.message;
    ui.govStatus.className = "status error";
  }
  ui.govStatus.hidden = false;
};

// ---------- Banking (in the Government tab) ----------

let bankDirty = false;   // the banking form has unsaved edits: don't overwrite them

function fillBanking(force = false) {
  if (bankDirty && !force) return;
  bankDirty = false;
  const b = state.banking;
  ui.bankEnabled.checked = b.enabled;
  ui.bankDeposit.value = +(b.deposit_rate * 100).toFixed(4);
  ui.bankSpread.value = +(b.loan_spread * 100).toFixed(4);
  ui.bankReserve.value = +(b.liquidity * 100).toFixed(2);
  ui.bankMinCapital.value = b.min_capital;
  ui.bankIncomeShare.value = +(b.loan_income_share * 100).toFixed(2);
}

function renderBanking() {
  const b = state.banking;
  fillBanking();
  ui.bankForm.querySelectorAll("input, button").forEach(el => { el.disabled = !b.industry_active; });
  const stats = b.industry_active ? [
    ["Banks", `${b.open} open`, `${b.closed} closed · ${b.failed} failed`],
    ["Rates", `${(b.deposit_rate_now * 100).toFixed(2)}% / ${(b.loan_rate_now * 100).toFixed(2)}%`, "deposits / loans, per step"],
    ["Deposits", usd(b.deposits), `${usd(b.reserves)} held as reserves`],
    ["Loans", usd(b.loans), "outstanding"],
    ["Money supply", usd(b.money_supply), "cash (people + companies) + deposits"],
    ["Money multiplier", `×${b.multiplier.toFixed(2)}`, "money supply ÷ (cash + reserves)"],
    ["Credit limit", `${(b.loan_income_share * 100).toFixed(0)}% of a month`, `of each borrower's income (${b.month_steps} days)`],
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
    const lines = [
      `Equity ${usd(bank.equity)} (${ratio}; founder put in ${usd(bank.capital_in)})`,
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
      deposit_rate: Number(ui.bankDeposit.value) / 100,
      loan_spread: Number(ui.bankSpread.value) / 100,
      liquidity: Number(ui.bankReserve.value) / 100,
      min_capital: Number(ui.bankMinCapital.value),
      loan_income_share: Number(ui.bankIncomeShare.value) / 100,
    });
    bankDirty = false;
    render(next);
    ui.bankStatus.textContent = "Banking settings apply from the next step.";
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
const RULE_BACKED = ["inventory", "assets", "labor_capacity", "rates", "money", "sleep_recovery", "movement", "payout_ratio"];
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
    line.textContent = `${need}: grows ${grows.toFixed(3)} · its industries make ${made.toFixed(3)} of relief per step → ` +
      (even ? "balanced" : net < 0 ? `buys ${(-net).toFixed(3)}/step` : `sells ${net.toFixed(3)}/step`);
    ui.balance.append(line);
  }
  const jobs = GOODS.reduce((sum, g) => sum + fieldValue(`assets.${g}`) * state.market.asset_labor[g], 0);
  const work = fieldValue("labor_capacity");
  const labourLine = document.createElement("span");
  labourLine.textContent = `labour: makes ${work.toFixed(3)} · its assets employ ${jobs.toFixed(3)} per step → ` +
    (work >= jobs ? `sells ${(work - jobs).toFixed(3)}/step` : `hires ${(jobs - work).toFixed(3)}/step`);
  ui.balance.append(labourLine);
  // Sleep rises at g while awake (0.3 -> 0.5) and falls at r while resting (0.5 -> 0.3),
  // so the agent spends g / (g + r) of its time asleep.
  const g = fieldValue("rates.sleep");
  const r = fieldValue("sleep_recovery");
  const line = document.createElement("span");
  line.className = r ? "" : "short";
  line.textContent = r
    ? `sleep: rises ${g.toFixed(3)} · recovers ${r.toFixed(3)} per step at rest → asleep ${(100 * g / (g + r || 1)).toFixed(0)}% of the time`
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
ui.run100.onclick = () => step(100);
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

buildForm();
api("/api/state").then(s => {
  ui.agentCount.value = s.agents.length;
  state = s;
  refreshForm(true);
  render(s);
});
