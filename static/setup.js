// Setup screen: choose the game rules, then start a new game.
// Shares globals with app.js (api, render, state, setPlaying, refreshForm, spreadMean, ...).

const setupUi = {
  screen: $("setup"),
  form: $("setup-form"),
  sections: $("setup-sections"),
  preview: $("setup-preview"),
  preset: $("setup-preset"),
  status: $("setup-status"),
  factory: $("setup-factory"),
  close: $("setup-close"),
  open: $("open-setup"),
};

// Each field's `path` matches the rules JSON ("money", "rates.thirst", ...).
// kind: "int" | "float" | "bool" | "choice" | "spread" (number or distribution, drawn per agent).
// "seed" is not a rule but is sent along with the rules.
const per = (names, fn) => names.map(fn);
const SETUP_SECTIONS = [
  { title: "World", hint: "How many agents, and how meetings work.", fields: [
    { path: "agents", label: "Agents", kind: "int", min: 1, max: 500 },
    { path: "seed", label: "Seed", kind: "int", optional: true, placeholder: "random" },
    { path: "contact_distance", label: "Touch distance (px)", kind: "float", min: 1, max: 200, step: 1 },
    { path: "depart_steps", label: "Walk apart (steps)", kind: "int", min: 0, max: 1000 },
    { path: "cooldown_steps", label: "Ignore each other (steps)", kind: "int", min: 0, max: 10000 },
  ]},
  { title: "Prices", hint: "Scarcity: total money ÷ total units × (1 − share of that resource). Fixed: the prices below.", fields: [
    { path: "price_mode", label: "Price rule", kind: "choice", full: true,
      options: [["scarcity", "Scarcity (changes with supply)"], ["fixed", "Fixed prices"]] },
    ...per(RESOURCES, r => ({ path: `fixed_prices.${r}`, label: `${cap(r)} price`, kind: "float", min: 0, step: 0.01,
      enabledWhen: v => v.price_mode === "fixed" })),
  ]},
  { title: "Starting agents", wide: true,
    hint: "What each new agent begins with. Pick a distribution to make agents differ: min and max are hard limits.", fields: [
    ...per(RESOURCES, r => ({ path: `inventory.${r}`, label: cap(r), kind: "spread", whole: true, min: 0 })),
    { path: "money", label: "Money", kind: "spread", min: 0, step: 0.01 },
    { path: "movement", label: "Movement (px)", kind: "spread", whole: true, min: 1, max: 200 },
    { path: "start_needs", label: "Starting needs", kind: "spread", min: 0, max: 1, step: 0.05 },
  ]},
  { title: "Resource production", wide: true, hint: "Each agent makes 1 unit every N steps (0 = never).", fields:
    per(RESOURCES, r => ({ path: `production.${r}`, label: cap(r), kind: "spread", whole: true, min: 0 })) },
  { title: "Resource consumption", wide: true, hint: "How fast each need grows per step, and how sleep recovers at rest.", fields: [
    ...per(NEEDS, n => ({ path: `rates.${n}`, label: `${cap(n)} / step`, kind: "spread", min: 0, max: 1, step: 0.001 })),
    { path: "sleep_recovery", label: "Sleep recovery", kind: "spread", min: 0, max: 1, step: 0.01 },
  ]},
  { title: "Need thresholds", hint: "When agents act on a need, and what consuming does.", fields: [
    { path: "seek_threshold", label: "Act above", kind: "float", min: 0, max: 1, step: 0.05 },
    { path: "target_level", label: "Until below", kind: "float", min: 0, max: 1, step: 0.05 },
    { path: "relief_per_unit", label: "1 unit relieves", kind: "float", min: 0.001, max: 1, step: 0.01, full: true },
  ]},
  { title: "Life and death", hint: "What happens when a need reaches 1.00.", fields: [
    { path: "death_enabled", label: "Hunger or thirst at 1.00 kills", kind: "bool", full: true },
    { path: "depression_enabled", label: "Boredom at 1.00 depresses", kind: "bool", full: true },
    { path: "depression_factor", label: "Depressed speed & sleep recovery ×", kind: "float", min: 0, max: 1, step: 0.05,
      full: true, enabledWhen: v => v.depression_enabled },
  ]},
];
const SETUP_FIELDS = SETUP_SECTIONS.flatMap(s => s.fields);
const DISTS = [["fixed", "Fixed"], ["uniform", "Uniform"], ["normal", "Normal (Gaussian)"], ["skewed", "Skewed"]];
const DIST_PARAMS = { fixed: ["value"], uniform: ["min", "max"], normal: ["min", "max", "mean", "std"],
                      skewed: ["min", "max", "mean", "std", "skew"] };
const PARAM_LABELS = { value: "value", min: "min", max: "max", mean: "mean", std: "std", skew: "skew" };

// Presets are changes on top of the factory rules.
const PRESETS = [
  ["current", "This game's rules"],
  ["factory", "Factory defaults", {}],
  ["balanced", "Balanced (no shortages)", { rates: { thirst: 0.01 } }],
  ["specialists", "Specialists (production varies a lot)", { production: {
    food: { dist: "skewed", min: 2, max: 60, mean: 12, std: 10, skew: 4 },
    water: { dist: "skewed", min: 2, max: 60, mean: 10, std: 10, skew: 4 },
    games: { dist: "skewed", min: 2, max: 60, mean: 12, std: 10, skew: 4 } } }],
  ["unequal", "Unequal wealth (skewed money)", { money: { dist: "skewed", min: 0, max: 1000, mean: 100, std: 120, skew: 8 } }],
  ["drought", "Drought (water is rare)", { inventory: { water: 30 }, production: { water: 40 } }],
  ["easy", "Easy (no death or depression)", { death_enabled: false, depression_enabled: false }],
  ["barter", "Barter (fixed 1:1 prices)", { price_mode: "fixed", fixed_prices: { food: 1, water: 1, games: 1 } }],
];

let rulesInfo = null;   // {current, factory} from the server

const setupInput = (name) => setupUi.form.elements[name];
const spreadInput = (f, param) => setupInput(`${f.path}#${param}`);

function mergeRules(base, changes) {
  const out = structuredClone(base);
  for (const [k, v] of Object.entries(changes)) {
    out[k] = v && typeof v === "object" && !("dist" in v) ? { ...out[k], ...v } : v;
  }
  return out;
}

function numberInput(name, f) {
  const el = document.createElement("input");
  el.type = "number";
  el.name = name;
  if (f.kind === "int" || f.whole) el.step = 1;
  for (const attr of ["min", "max", "step", "placeholder"]) if (f[attr] !== undefined) el[attr] = f[attr];
  return el;
}

function buildSpreadRow(f) {
  const row = document.createElement("div");
  row.className = "spread-row";
  row.dataset.path = f.path;
  const name = document.createElement("span");
  name.className = "spread-name";
  name.textContent = f.label;
  const dist = document.createElement("select");
  dist.name = `${f.path}#dist`;
  for (const [value, text] of DISTS) dist.add(new Option(text, value));
  dist.onchange = () => switchDist(f);
  const params = document.createElement("div");
  params.className = "spread-params";
  for (const param of Object.keys(PARAM_LABELS)) {
    const label = document.createElement("label");
    label.dataset.param = param;
    const el = param === "skew"
      ? Object.assign(numberInput(`${f.path}#skew`, {}), { min: -20, max: 20, step: 0.5 })
      : param === "std" ? Object.assign(numberInput(`${f.path}#std`, { step: f.step }), { min: 0 })
      : numberInput(`${f.path}#${param}`, f);
    label.append(PARAM_LABELS[param], el);
    params.append(label);
  }
  const hist = document.createElement("canvas");
  hist.className = "hist";
  hist.width = 120;
  hist.height = 30;
  hist.title = "Shape of the distribution (preview)";
  row.append(name, dist, params, hist);
  return row;
}

function buildSetupForm() {
  for (const section of SETUP_SECTIONS) {
    const box = document.createElement("fieldset");
    box.className = "setup-section" + (section.wide ? " wide" : "");
    const h = document.createElement("h3");
    h.textContent = section.title;
    const hint = document.createElement("p");
    hint.className = "section-hint";
    hint.textContent = section.hint;
    const grid = document.createElement("div");
    grid.className = section.wide ? "spread-list" : "setup-fields";
    for (const f of section.fields) {
      if (f.kind === "spread") { grid.append(buildSpreadRow(f)); continue; }
      const label = document.createElement("label");
      if (f.full) label.classList.add("full");
      let el;
      if (f.kind === "choice") {
        el = document.createElement("select");
        for (const [value, text] of f.options) el.add(new Option(text, value));
      } else if (f.kind === "bool") {
        el = document.createElement("input");
        el.type = "checkbox";
      } else {
        el = numberInput(f.path, f);
      }
      el.name = f.path;
      label.append(f.label, el);
      grid.append(label);
    }
    box.append(h, hint, grid);
    setupUi.sections.append(box);
  }
  for (const [id, name] of PRESETS) setupUi.preset.add(new Option(name, id));
}

const roundTo = (v, f) => f.whole ? Math.round(v) : Number(v.toPrecision(4));

// Put a spread (number or distribution) into its row.
function fillSpread(f, spec) {
  const fixed = typeof spec === "number";
  spreadInput(f, "dist").value = fixed ? "fixed" : spec.dist;
  const center = spreadMean(spec);
  const values = fixed
    ? { value: spec, ...suggestedParams(f, spec) }
    : { value: roundTo(center, f), mean: center, std: roundTo((spec.max - spec.min) / 6, f), skew: 0, ...spec };
  for (const param of Object.keys(PARAM_LABELS)) spreadInput(f, param).value = values[param] ?? "";
  showParams(f);
}

// Sensible starting parameters around a value when switching away from "fixed".
function suggestedParams(f, v) {
  const lo = Math.max(f.min ?? 0, v * 0.5), hi = Math.min(f.max ?? Infinity, v === 0 ? 1 : v * 1.5);
  return { min: roundTo(lo, f), max: roundTo(hi, f), mean: v, std: roundTo((hi - lo) / 4, f) || (f.step ?? 1), skew: 2 };
}

function switchDist(f) {
  const dist = spreadInput(f, "dist").value;
  if (dist === "fixed") {
    const mean = Number(spreadInput(f, "mean").value);
    const lo = Number(spreadInput(f, "min").value), hi = Number(spreadInput(f, "max").value);
    const center = Number.isFinite(mean) && spreadInput(f, "mean").value !== "" ? mean : (lo + hi) / 2;
    spreadInput(f, "value").value = roundTo(center, f);
  } else if (spreadInput(f, "min").value === "") {
    const v = Number(spreadInput(f, "value").value) || 0;
    const s = suggestedParams(f, v);
    for (const p of ["min", "max", "mean", "std", "skew"]) spreadInput(f, p).value = s[p];
  }
  showParams(f);
  updateSetup();
}

function showParams(f) {
  const shown = DIST_PARAMS[spreadInput(f, "dist").value];
  const row = setupUi.form.querySelector(`.spread-row[data-path="${f.path}"]`);
  for (const label of row.querySelectorAll(".spread-params label")) label.hidden = !shown.includes(label.dataset.param);
  row.querySelector(".hist").hidden = shown.length === 1;
}

function readSpread(f) {
  const dist = spreadInput(f, "dist").value;
  const value = {};
  for (const param of DIST_PARAMS[dist]) {
    const raw = spreadInput(f, param).value;
    if (raw === "") throw new Error(`${f.label}: ${param} can't be empty`);
    value[param] = Number(raw);
  }
  if (dist === "fixed") return value.value;
  if (value.min > value.max) throw new Error(`${f.label}: min can't be larger than max`);
  if ("mean" in value && (value.mean < value.min || value.mean > value.max)) {
    throw new Error(`${f.label}: mean must be between min and max`);
  }
  return { dist, ...value };
}

function fillSetup(rules, seed = "") {
  for (const f of SETUP_FIELDS) {
    if (f.kind === "spread") { fillSpread(f, getPath(rules, f.path)); continue; }
    const el = setupInput(f.path);
    const value = f.path === "seed" ? seed : getPath(rules, f.path);
    if (f.kind === "bool") el.checked = value;
    else el.value = value ?? "";
  }
  updateSetup();
}

// Read the form into a rules object. Throws on empty / invalid values.
function readSetup() {
  const rules = {};
  let seed = null;
  for (const f of SETUP_FIELDS) {
    let value;
    if (f.kind === "spread") value = readSpread(f);
    else {
      const el = setupInput(f.path);
      if (f.kind === "bool") value = el.checked;
      else if (f.kind === "choice") value = el.value;
      else {
        if (el.value === "") {
          if (f.optional) continue;
          throw new Error(`${f.label} can't be empty`);
        }
        value = Number(el.value);
      }
    }
    if (f.path === "seed") { seed = value; continue; }
    const [group, key] = f.path.split(".");
    if (key) (rules[group] ||= {})[key] = value;
    else rules[group] = value;
  }
  return { rules, seed };
}

function drawHistogram(canvas, spec, f) {
  const c = canvas.getContext("2d");
  c.clearRect(0, 0, canvas.width, canvas.height);
  if (typeof spec === "number" || spec.max <= spec.min) return;
  // Whole-number values get one bar per integer (up to 24) so bars don't alias.
  const count = f.whole ? Math.min(24, Math.round(spec.max - spec.min) + 1) : 24;
  const bins = new Array(count).fill(0);
  for (let i = 0; i < 2000; i++) {
    let v = sampleSpread(spec);
    if (f.whole) v = Math.round(v);
    const span = f.whole ? spec.max - spec.min + 1 : spec.max - spec.min;
    const b = Math.min(count - 1, Math.floor((v - spec.min) / span * count));
    bins[b]++;
  }
  const top = Math.max(...bins);
  const w = canvas.width / bins.length;
  c.fillStyle = cssVar("--accent");
  bins.forEach((n, i) => {
    const h = (n / top) * (canvas.height - 2);
    c.fillRect(i * w + 0.5, canvas.height - h, w - 1, h);
  });
}

// Enable/disable dependent fields, mark changes vs factory, redraw histograms and the preview.
function updateSetup() {
  let values = null, error = null;
  try { values = readSetup().rules; } catch (err) { error = err.message; }
  for (const f of SETUP_FIELDS) {
    const factory = f.path === "seed" ? undefined : getPath(rulesInfo.factory, f.path);
    if (f.kind === "spread") {
      let spec = null;
      try { spec = readSpread(f); } catch { /* shown in the preview */ }
      const row = setupUi.form.querySelector(`.spread-row[data-path="${f.path}"]`);
      row.classList.toggle("changed", spec !== null && JSON.stringify(spec) !== JSON.stringify(factory));
      if (spec !== null) drawHistogram(row.querySelector(".hist"), spec, f);
      continue;
    }
    const el = setupInput(f.path);
    const off = values && f.enabledWhen && !f.enabledWhen(values);
    el.disabled = !!off;
    el.closest("label").classList.toggle("disabled", !!off);
    const now = f.kind === "bool" ? el.checked : f.kind === "choice" ? el.value : Number(el.value);
    el.classList.toggle("changed", factory !== undefined && el.value !== "" && now !== factory);
  }
  renderPreview(values, error);
}

// Plain-language consequences of the rules for an average agent.
function renderPreview(r, error) {
  setupUi.preview.innerHTML = "";
  const line = (text, cls = "") => {
    const el = document.createElement("span");
    el.textContent = text;
    if (cls) el.className = cls;
    setupUi.preview.append(el);
  };
  if (!r) return line(error || "Fill in every field to see the preview.", "short");
  const avg = (spec) => spreadMean(spec);
  const varies = (spec) => typeof spec !== "number";

  for (const res of RESOURCES) {
    const need = NEED_FOR[res];
    const rate = avg(r.rates[need]);
    const every = avg(r.production[res]);
    const used = rate / r.relief_per_unit;
    const made = every ? 1 / every : 0;
    const net = made - used;
    const head = `${cap(res)}: an average agent uses ${used.toFixed(3)} and makes ${made.toFixed(3)} per step`;
    if (Math.abs(net) < 1e-9) line(`${head} → balanced.`);
    else if (net > 0) line(`${head} → surplus of ${net.toFixed(3)}/step to trade.`, "surplus");
    else {
      const lasts = Math.round(avg(r.inventory[res]) / -net);
      let text = `${head} → short ${(-net).toFixed(3)}/step. Its starting stock lasts ~${lasts} steps.`;
      const toCritical = rate ? Math.round((1 - r.seek_threshold) / rate) : Infinity;
      if (need !== "boredom" && r.death_enabled) text += ` Then ${need} kills in ~${toCritical} steps.`;
      if (need === "boredom" && r.depression_enabled) text += ` Then depression after ~${toCritical} steps.`;
      line(text, "short");
    }
    if (varies(r.production[res]) || varies(r.rates[need])) {
      line(`   ${cap(res)} production or use varies between agents, so some will have surplus to sell to others.`);
    }
  }

  const g = avg(r.rates.sleep), rec = avg(r.sleep_recovery);
  line(rec
    ? `Sleep: an average agent rests about ${(100 * g / (g + rec || 1)).toFixed(0)}% of the time.`
    : "Sleep: recovery is 0, so a tired agent stops forever.", rec ? "" : "short");

  if (r.price_mode === "fixed") {
    line(`Prices are fixed: ${RESOURCES.map(x => `${x} ${r.fixed_prices[x]}`).join(", ")}.`);
  } else {
    const units = RESOURCES.map(x => avg(r.inventory[x]));
    const total = units.reduce((a, b) => a + b, 0);
    const money = avg(r.money);
    const prices = RESOURCES.map((x, i) => total ? (money / total) * (1 - units[i] / total) : 0);
    line(`Starting prices (roughly): ${RESOURCES.map((x, i) => `${x} ${prices[i].toFixed(3)}`).join(", ")}. ` +
         "Scarcer resources get dearer as stocks change.");
  }
}

async function openSetup() {
  setPlaying(false);
  try {
    rulesInfo = await api("/api/rules");
  } catch (err) {
    return alert(err.message);
  }
  setupUi.preset.value = "current";
  setupUi.status.hidden = true;
  setupUi.screen.hidden = false;
  document.body.classList.add("setup-open");
  fillSetup(rulesInfo.current, state?.seed ?? "");
}

function closeSetup() {
  setupUi.screen.hidden = true;
  document.body.classList.remove("setup-open");
}

setupUi.form.oninput = updateSetup;
setupUi.form.onchange = updateSetup;
setupUi.open.onclick = openSetup;
setupUi.close.onclick = closeSetup;
setupUi.factory.onclick = () => { setupUi.preset.value = "factory"; fillSetup(rulesInfo.factory); };
setupUi.preset.onchange = () => {
  const [id, , changes] = PRESETS.find(p => p[0] === setupUi.preset.value);
  fillSetup(id === "current" ? rulesInfo.current : mergeRules(rulesInfo.factory, changes));
};
setupUi.form.onsubmit = async (e) => {
  e.preventDefault();
  try {
    const { rules, seed } = readSetup();
    const next = await api("/api/reset", { rules, seed });
    selectedId = null;
    editingId = null;
    render(next);
    refreshForm(true);
    ui.agentCount.value = next.agents.length;
    ui.seed.value = seed ?? "";
    closeSetup();
  } catch (err) {
    setupUi.status.textContent = err.message;
    setupUi.status.hidden = false;
  }
};

buildSetupForm();
openSetup();  // the setup screen is the first thing you see
