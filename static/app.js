const canvas = document.getElementById("world");
const ctx = canvas.getContext("2d");
const ui = {
  tick: document.getElementById("tick"),
  step: document.getElementById("step"),
  play: document.getElementById("play"),
  run100: document.getElementById("run100"),
  addForm: document.getElementById("add-form"),
  addDefaults: document.getElementById("add-defaults"),
  addError: document.getElementById("add-error"),
  editPanel: document.getElementById("edit-panel"),
  editForm: document.getElementById("edit-form"),
  editReload: document.getElementById("edit-reload"),
  editStatus: document.getElementById("edit-status"),
  interval: document.getElementById("interval"),
  intervalLabel: document.getElementById("interval-label"),
  agentCount: document.getElementById("agent-count"),
  seed: document.getElementById("seed"),
  reset: document.getElementById("reset"),
  showRange: document.getElementById("show-range"),
  agents: document.getElementById("agents"),
  events: document.getElementById("events"),
};

const DOT_RADIUS = 6;
const NEEDS = ["hunger", "sleep", "thirst", "boredom"];
const RESOURCES = ["food", "water", "games"];
const NEED_FOR = { food: "hunger", water: "thirst", games: "boredom" };
const RELIEF_PER_UNIT = 0.1;

let state = null;
let selectedId = null;
let playing = false;
let busy = false;     // a request is in flight; skip timer ticks instead of queueing them
let timer = null;

async function api(path, body) {
  const res = await fetch(path, body === undefined ? {} : {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
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
  ui.tick.textContent = state.tick;
  syncEditAgents();
  draw();
  renderAgents();
  renderEvents();
}

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

  for (const agent of state.agents) {
    if (ui.showRange.checked) {
      ctx.fillStyle = agent.color + "18";
      ctx.strokeStyle = agent.color + "55";
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.arc(agent.x, agent.y, agent.movement, 0, Math.PI * 2);
      ctx.fill(); ctx.stroke();
    }
    ctx.fillStyle = agent.color;
    ctx.beginPath();
    ctx.arc(agent.x, agent.y, DOT_RADIUS, 0, Math.PI * 2);
    ctx.fill();
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
}

function needColor(v) {
  // green (satisfied) -> amber -> red (desperate)
  const hue = 120 - v * 120;
  return `hsl(${hue} 60% 48%)`;
}

function renderAgents() {
  ui.agents.innerHTML = "";
  for (const a of state.agents) {
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
      ["movement", `${a.movement} px`],
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
    act.textContent = !target ? a.activity
      : a.activity === "seeking" ? `seeking ${target.name} (needs ${a.wants.join(", ")})`
      : `meeting ${target.name}`;
    const prod = RESOURCES.map(r => production[r] ? `${r} 1/${production[r]}` : `${r} –`).join(" · ");
    activity.append(act, ` · produces ${prod}`);

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
  selectedId = best ? best.id : null;
  render(state);
});

ui.step.onclick = () => step(1);
ui.run100.onclick = () => step(100);

// Production / need-rate fields are shared by the add and edit forms.
function fillRates(form, production, rates) {
  for (const r of RESOURCES) form.elements[`prod_${r}`].value = production[r];
  for (const n of NEEDS) form.elements[`rate_${n}`].value = rates[n];
  updateBalance(form);
}

function readRates(form) {
  return {
    production: Object.fromEntries(RESOURCES.map(r => [r, Number(form.elements[`prod_${r}`].value)])),
    rates: Object.fromEntries(NEEDS.map(n => [n, Number(form.elements[`rate_${n}`].value)])),
  };
}

// Per resource: units used per step (need rate / 0.1) vs units made per step (1 / N).
function updateBalance(form) {
  const box = document.querySelector(`.balance[data-for="${form.id}"]`);
  const { production, rates } = readRates(form);
  box.innerHTML = "";
  for (const r of RESOURCES) {
    const used = rates[NEED_FOR[r]] / RELIEF_PER_UNIT;
    const made = production[r] ? 1 / production[r] : 0;
    const net = made - used;
    const line = document.createElement("span");
    line.className = Math.abs(net) < 1e-9 ? "" : net < 0 ? "short" : "surplus";
    const verdict = Math.abs(net) < 1e-9 ? "balanced" : net < 0 ? `short ${(-net).toFixed(3)}/step` : `surplus ${net.toFixed(3)}/step`;
    line.textContent = `${r}: uses ${used.toFixed(3)} · makes ${made.toFixed(3)} per step → ${verdict}`;
    box.append(line);
  }
}

function fillDefaults() {
  const d = state.defaults;
  const f = ui.addForm.elements;
  for (const r of RESOURCES) f[r].value = d.inventory[r];
  f.money.value = d.money;
  f.movement.value = "";
  fillRates(ui.addForm, d.production, d.rates);
  ui.addError.hidden = true;
}

// The editor is only rebuilt when the agent list changes, so typing isn't
// wiped out by the re-render on every step.
let editAgentIds = "";
function syncEditAgents() {
  const ids = state.agents.map(a => a.id).join(",");
  if (ids === editAgentIds) return;
  editAgentIds = ids;
  const select = ui.editForm.elements.agent;
  const current = select.value;
  select.innerHTML = "";
  for (const a of state.agents) select.add(new Option(a.name, a.id));
  if (current && state.agents.some(a => String(a.id) === current)) select.value = current;
  loadEditor();
}

function loadEditor() {
  const agent = state.agents.find(a => String(a.id) === ui.editForm.elements.agent.value);
  if (!agent) return;
  fillRates(ui.editForm, agent.modules.Production.intervals, agent.modules.NeedsDecay.rates);
  ui.editStatus.hidden = true;
}

function openEditor(id) {
  ui.editPanel.open = true;
  ui.editForm.elements.agent.value = id;
  selectedId = id;
  loadEditor();
  render(state);
  ui.editPanel.scrollIntoView({ block: "nearest" });
}

ui.editForm.elements.agent.onchange = loadEditor;
ui.editReload.onclick = loadEditor;
ui.editForm.oninput = () => updateBalance(ui.editForm);
ui.addForm.oninput = () => updateBalance(ui.addForm);
ui.editForm.onsubmit = async (e) => {
  e.preventDefault();
  const id = ui.editForm.elements.agent.value;
  try {
    render(await api(`/api/agents/${id}`, readRates(ui.editForm)));
    ui.editStatus.textContent = "Saved.";
    ui.editStatus.className = "error ok";
  } catch (err) {
    ui.editStatus.textContent = err.message;
    ui.editStatus.className = "error";
  }
  ui.editStatus.hidden = false;
};

ui.addDefaults.onclick = fillDefaults;
ui.addForm.onsubmit = async (e) => {
  e.preventDefault();
  const f = ui.addForm.elements;
  const body = {
    inventory: Object.fromEntries(RESOURCES.map(r => [r, Number(f[r].value)])),
    ...readRates(ui.addForm),
    money: Number(f.money.value),
    movement: f.movement.value === "" ? null : Number(f.movement.value),
  };
  try {
    render(await api("/api/agents", body));
    ui.agentCount.value = state.agents.length;
    ui.addError.hidden = true;
  } catch (err) {
    ui.addError.textContent = err.message;
    ui.addError.hidden = false;
  }
};
ui.play.onclick = () => setPlaying(!playing);
ui.interval.oninput = () => {
  ui.intervalLabel.textContent = `${ui.interval.value} ms`;
  if (playing) setPlaying(true);
};
ui.reset.onclick = async () => {
  setPlaying(false);
  selectedId = null;
  editAgentIds = "";  // new world: reload the editor even if the ids are the same
  try {
    render(await api("/api/reset", { agents: Number(ui.agentCount.value), seed: ui.seed.value }));
  } catch (err) {
    alert(err.message);
  }
};
ui.showRange.onchange = () => state && draw();
document.addEventListener("keydown", (e) => {
  if (["INPUT", "SELECT", "BUTTON"].includes(e.target.tagName)) return;
  if (e.code === "Space") { e.preventDefault(); setPlaying(!playing); }
  if (e.code === "ArrowRight" && !playing) step(1);
});

api("/api/state").then(s => { ui.agentCount.value = s.agents.length; render(s); fillDefaults(); });
