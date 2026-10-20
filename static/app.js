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

  // Dashed line from each seeking agent to the agent it is heading for.
  ctx.setLineDash([6, 6]);
  for (const agent of state.agents) {
    const target = byId[agent.target_id];
    if (agent.activity !== "seeking" || !target) continue;
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
    head.append(dot, name, pos);

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
    act.textContent = a.activity === "seeking" && target ? `seeking ${target.name}` : a.activity;
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

function fillDefaults() {
  const d = state.defaults;
  const f = ui.addForm.elements;
  for (const r of RESOURCES) {
    f[r].value = d.inventory[r];
    f[`prod_${r}`].value = d.production[r];
  }
  f.money.value = d.money;
  f.movement.value = "";
  ui.addError.hidden = true;
}

ui.addDefaults.onclick = fillDefaults;
ui.addForm.onsubmit = async (e) => {
  e.preventDefault();
  const f = ui.addForm.elements;
  const body = {
    inventory: Object.fromEntries(RESOURCES.map(r => [r, Number(f[r].value)])),
    production: Object.fromEntries(RESOURCES.map(r => [r, Number(f[`prod_${r}`].value)])),
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
  try {
    render(await api("/api/reset", { agents: Number(ui.agentCount.value), seed: ui.seed.value }));
  } catch (err) {
    alert(err.message);
  }
};
ui.showRange.onchange = () => state && draw();
document.addEventListener("keydown", (e) => {
  if (e.target.tagName === "INPUT") return;
  if (e.code === "Space") { e.preventDefault(); setPlaying(!playing); }
  if (e.code === "ArrowRight" && !playing) step(1);
});

api("/api/state").then(s => { ui.agentCount.value = s.agents.length; render(s); fillDefaults(); });
