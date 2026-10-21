const canvas = document.getElementById("world");
const ctx = canvas.getContext("2d");
const $ = (id) => document.getElementById(id);
const ui = {
  tick: $("tick"),
  step: $("step"),
  play: $("play"),
  run100: $("run100"),
  interval: $("interval"),
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
};

const DOT_RADIUS = 6;
const NEEDS = ["hunger", "sleep", "thirst", "boredom"];
const RESOURCES = ["food", "water", "games"];
const NEED_FOR = { food: "hunger", water: "thirst", games: "boredom" };
const cap = (w) => w[0].toUpperCase() + w.slice(1);
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
  { legend: "Inventory", fields: RESOURCES.map(r => (
    { path: `inventory.${r}`, label: cap(r), min: 0, step: 1, get: a => a.inventory[r] ?? 0 }))},
  { legend: "Production: 1 unit every N steps (0 = never)", fields: RESOURCES.map(r => (
    { path: `production.${r}`, label: cap(r), min: 0, step: 1, get: a => a.modules.Production.intervals[r] }))},
];
const FIELDS = FIELD_GROUPS.flatMap(g => g.fields);

let state = null;
let selectedId = null;
let editingId = null;   // agent shown in the Manage form; null = creating a new one
let activeTab = "overview";
let playing = false;
let busy = false;     // a request is in flight; skip timer ticks instead of queueing them
let timer = null;

async function api(path, body, method = body === undefined ? "GET" : "POST") {
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
  if (on) timer = setInterval(() => step(1), Number(ui.interval.value));
  ui.play.textContent = on ? "Pause" : "Play";
  ui.play.classList.toggle("active", on);
  ui.step.disabled = on;
  ui.run100.disabled = on;
}

function render(next) {
  state = next;
  if (editingId !== null && !agentById(editingId)) editingId = null;
  ui.tick.textContent = state.tick;
  draw();
  if (activeTab === "overview") {
    renderMarket();
    renderAgents();
    renderEvents();
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
    ctx.arc(agent.x, agent.y, DOT_RADIUS, 0, Math.PI * 2);
    ctx.fill();
    if (agent.depressed) {
      ctx.strokeStyle = "#555";
      ctx.lineWidth = 2;
      ctx.setLineDash([2, 2]);
      ctx.beginPath();
      ctx.arc(agent.x, agent.y, DOT_RADIUS + 2, 0, Math.PI * 2);
      ctx.stroke();
      ctx.setLineDash([]);
    }
    if (agent.activity === "sleeping") {
      ctx.fillStyle = cssVar("--muted");
      ctx.font = "italic 12px system-ui, sans-serif";
      ctx.fillText("z z", agent.x - 8, agent.y + DOT_RADIUS + 14);
    }
    if (agent.id === selectedId || inContact.has(agent.id)) {
      ctx.strokeStyle = cssVar("--text");
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.arc(agent.x, agent.y, DOT_RADIUS + 4, 0, Math.PI * 2);
      ctx.stroke();
    }
    ctx.fillStyle = cssVar("--muted");
    ctx.font = "14px system-ui, sans-serif";
    // Keep labels inside the box near the right/top edges.
    const labelWidth = ctx.measureText(agent.name).width;
    const lx = agent.x + DOT_RADIUS + 4 + labelWidth > width ? agent.x - DOT_RADIUS - 4 - labelWidth : agent.x + DOT_RADIUS + 4;
    const ly = agent.y - DOT_RADIUS - 2 < 14 ? agent.y + DOT_RADIUS + 14 : agent.y - DOT_RADIUS - 2;
    ctx.fillText(agent.name, lx, ly);
  }
  ctx.globalAlpha = 1;
}

function needColor(v) {
  // green (satisfied) -> amber -> red (desperate)
  const hue = 120 - v * 120;
  return `hsl(${hue} 60% 48%)`;
}

// Price of each resource: total money / total units * (1 - that resource's share of units).
function renderMarket() {
  const m = state.market;
  const total = RESOURCES.reduce((sum, r) => sum + m.units[r], 0);
  ui.market.innerHTML = "";
  const title = document.createElement("div");
  title.className = "market-title";
  title.textContent = `Market · ${m.money.toFixed(2)} money / ${total} units = ${(total ? m.money / total : 0).toFixed(3)} per unit`;
  ui.market.append(title);
  const row = document.createElement("div");
  row.className = "market-row";
  for (const r of RESOURCES) {
    const share = total ? m.units[r] / total : 0;
    const cell = document.createElement("div");
    const price = document.createElement("b");
    price.textContent = m.prices[r].toFixed(3);
    cell.append(`${r} `, price);
    const detail = document.createElement("span");
    detail.textContent = `${m.units[r]} units · ${(share * 100).toFixed(0)}% share`;
    cell.append(detail);
    row.append(cell);
  }
  ui.market.append(row);
}

// ---------- Overview: search, filter and sort agents ----------

const agentView = { query: "", filter: "all", sort: "id", desc: true };

const SORT_VALUE = {
  id: a => a.id,
  name: a => a.name.toLowerCase(),
  money: a => a.money,
  movement: a => a.movement,
  urgency: a => Math.max(...NEEDS.map(n => a.needs[n])),
  ...Object.fromEntries(RESOURCES.map(r => [r, a => a.inventory[r] ?? 0])),
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

function renderAgents() {
  ui.agents.innerHTML = "";
  const shown = visibleAgents();
  ui.agentShown.textContent = shown.length === state.agents.length
    ? `(${shown.length})` : `(${shown.length} of ${state.agents.length})`;
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

    const production = a.modules.Production?.intervals || {};
    const meta = document.createElement("div");
    meta.className = "meta";
    const fields = [
      ...RESOURCES.map(r => [r, a.inventory[r] ?? 0, production[r] ? `+1 / ${production[r]} steps` : "no production"]),
      ["money", a.money.toFixed(2)],
      ["movement", a.depressed ? `${a.speed} px (depressed, ${a.movement} normally)` : `${a.speed} px`],
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
      : a.activity === "searching" ? `searching: nobody has ${a.wants.join(" or ")} to sell`
      : a.activity;
    const prod = RESOURCES.map(r => production[r] ? `${r} 1/${production[r]}` : `${r} –`).join(" · ");
    activity.append(act);
    if (a.depressed) {
      const sad = document.createElement("b");
      sad.className = "depressed";
      sad.textContent = "depressed";
      activity.append(" · ", sad);
    }
    activity.append(` · produces ${prod}`);

    card.append(head, stats, meta, activity);
    ui.agents.append(card);
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
  for (const t of ui.tabs) t.classList.toggle("active", t.dataset.tab === name);
  $("tab-overview").hidden = name !== "overview";
  $("tab-manage").hidden = name !== "manage";
  render(state);
}
for (const t of ui.tabs) t.onclick = () => showTab(t.dataset.tab);

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
    ui.formFields.append(fs);
  }
}

const input = (path) => ui.form.elements[path];

function renderChips() {
  ui.chips.innerHTML = "";
  ui.newAgent.classList.toggle("active", editingId === null);
  for (const a of state.agents) {
    const chip = document.createElement("button");
    chip.className = "chip" + (a.id === editingId ? " active" : "");
    const dot = document.createElement("span");
    dot.className = "dot";
    dot.style.background = a.color;
    chip.append(dot, a.name);
    chip.onclick = () => openEditor(a.id);
    ui.chips.append(chip);
  }
}

// Fill the form. Untouched ("clean") fields follow the live state; edited ones are left alone.
function refreshForm(force = false) {
  const agent = editingId === null ? null : agentById(editingId);
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
const RULE_BACKED = ["inventory", "production", "rates", "money", "sleep_recovery", "movement"];
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
  for (const r of RESOURCES) {
    const used = fieldValue(`rates.${NEED_FOR[r]}`) / state.rules.relief_per_unit;
    const every = fieldValue(`production.${r}`);
    const made = every ? 1 / every : 0;
    const net = made - used;
    const line = document.createElement("span");
    const even = Math.abs(net) < 1e-9;
    line.className = even ? "" : net < 0 ? "short" : "surplus";
    const verdict = even ? "balanced" : net < 0 ? `short ${(-net).toFixed(3)}/step` : `surplus ${net.toFixed(3)}/step`;
    line.textContent = `${r}: uses ${used.toFixed(3)} · makes ${made.toFixed(3)} per step → ${verdict}`;
    ui.balance.append(line);
  }
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
  let best = null, bestDist = 20;
  for (const a of state.agents) {
    const d = Math.hypot(a.x - x, a.y - y);
    if (d < bestDist) { best = a; bestDist = d; }
  }
  if (best && activeTab === "manage") return openEditor(best.id);
  selectedId = best ? best.id : null;
  render(state);
});

ui.step.onclick = () => step(1);
ui.run100.onclick = () => step(100);
ui.play.onclick = () => setPlaying(!playing);
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
