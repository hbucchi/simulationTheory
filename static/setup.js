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
// kind: "int" | "float" | "bool" | "choice" | "spread" (number or distribution, per agent).
// Spread fields: `whole` = whole numbers, `tiered` = may be shared out in tiers,
// `min`/`max` = the field's own limits. "seed" is not a rule but is sent with the rules.
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
    hint: "What each new agent begins with. Every row has its own distribution; “Copy to all resources” reuses one.", fields: [
    ...per(RESOURCES, r => ({ path: `inventory.${r}`, label: cap(r), kind: "spread", whole: true, tiered: true, min: 0 })),
    ...per(RESOURCES, r => ({ path: `assets.${r}`, label: `${cap(r)} assets (shares)`, kind: "spread", tiered: true,
      min: 0, step: 0.1 })),
    { path: "money", label: "Money", kind: "spread", tiered: true, min: 0, step: 0.01 },
    { path: "movement", label: "Movement (px)", kind: "spread", whole: true, min: 1, max: 200 },
    { path: "start_needs", label: "Starting needs", kind: "spread", min: 0, max: 1, step: 0.05 },
  ]},
  { title: "Resource production", wide: true, hint: "Each agent makes 1 unit every N steps (0 = never). Lower N = faster.", fields:
    per(RESOURCES, r => ({ path: `production.${r}`, label: cap(r), kind: "spread", whole: true, min: 0 })) },
  { title: "Resource consumption", wide: true, hint: "How fast each need grows per step, and how sleep recovers at rest.", fields: [
    ...per(NEEDS, n => ({ path: `rates.${n}`, label: `${cap(n)} / step`, kind: "spread", min: 0, max: 1, step: 0.001 })),
    { path: "sleep_recovery", label: "Sleep recovery", kind: "spread", min: 0, max: 1, step: 0.01 },
  ]},
  { title: "Trading", hint: "A buyer buys its need × a random multiplier between these two (stocking up), " +
      "limited by what the seller can spare and what the buyer can pay.", fields: [
    { path: "purchase_min", label: "Buy at least ×", kind: "float", min: 1, max: 10, step: 0.1 },
    { path: "purchase_max", label: "Buy at most ×", kind: "float", min: 1, max: 10, step: 0.1 },
  ]},
  { title: "Stock band", hint: "Agents keep between the floor and the cap of each resource: above the cap they go " +
      "out to sell the surplus (to make money for assets); below the floor they go out to buy back up to the cap.", fields: [
    { path: "selling_enabled", label: "Agents sell surplus and restock", kind: "bool", full: true },
    { path: "stock_cap", label: "Cap (units of each)", kind: "int", min: 1, enabledWhen: v => v.selling_enabled },
    { path: "restock_below", label: "Floor (0.5 = half the cap)", kind: "float", min: 0, max: 1, step: 0.05,
      enabledWhen: v => v.selling_enabled },
  ]},
  { title: "Market dynamics: stockpiling", hint: "When a resource's average per agent falls by the trigger " +
      "within the window, agents hoard it: they buy a reserve (paid in money, within a budget) and stop selling into it.", fields: [
    { path: "stockpiling_enabled", label: "Agents stockpile scarce resources", kind: "bool", full: true },
    { path: "scarcity_window", label: "Watch the last (steps)", kind: "int", min: 10, max: 500,
      enabledWhen: v => v.stockpiling_enabled },
    { path: "scarcity_trigger", label: "Scarce after a fall of (0.1 = 10%)", kind: "float", min: 0.01, max: 0.9, step: 0.01,
      enabledWhen: v => v.stockpiling_enabled },
    { path: "stockpile_steps", label: "Reserve (steps of own use)", kind: "int", min: 0, max: 5000,
      enabledWhen: v => v.stockpiling_enabled },
    { path: "stockpile_budget", label: "Spend at most (0.5 = half its money)", kind: "float", min: 0, max: 1, step: 0.05,
      enabledWhen: v => v.stockpiling_enabled },
  ]},
  { title: "Market dynamics: demand and concentration", hint: "Price = money ÷ units × (1 − share) × demand pressure × " +
      "concentration. Pressure = ((buyers+1) ÷ (sellers+1)) ^ elasticity. Concentration = 1 + weight × C, where C is 0 when the " +
      "sellable supply is spread evenly and 1 when one agent holds it all. Under pressure, each extra unit in a deal costs more.", fields: [
    { path: "demand_pricing_enabled", label: "Prices react to demand and concentration", kind: "bool", full: true },
    ...per(RESOURCES, r => ({ path: `price_elasticity.${r}`, label: `${cap(r)} elasticity (0 = none)`, kind: "float",
      min: 0, max: 3, step: 0.1, enabledWhen: v => v.demand_pricing_enabled })),
    ...per(RESOURCES, r => ({ path: `concentration_weight.${r}`, label: `${cap(r)} concentration weight`, kind: "float",
      min: 0, max: 10, step: 0.1, enabledWhen: v => v.demand_pricing_enabled })),
    { path: "price_adjust_speed", label: "Speed (share of gap per step)", kind: "float", min: 0.01, max: 1, step: 0.05,
      enabledWhen: v => v.demand_pricing_enabled },
    { path: "price_floor", label: "Never below base ×", kind: "float", min: 0.01, max: 1, step: 0.05,
      enabledWhen: v => v.demand_pricing_enabled },
    { path: "price_cap", label: "Never above base ×", kind: "float", min: 1, max: 100, step: 0.5,
      enabledWhen: v => v.demand_pricing_enabled },
    { path: "unit_markup", label: "Extra unit costs more (0.05 = +5%)", kind: "float", min: 0, max: 1, step: 0.01,
      full: true, enabledWhen: v => v.demand_pricing_enabled },
  ]},
  { title: "Investment", hint: "Each resource has its own asset. The only assets are the starting ones; " +
      "they change hands between agents and their output grows over time. Asset price = output per step × resource price " +
      "÷ return, so a dearer resource makes its assets dearer. Agents invest spare cash in assets of what they lack, " +
      "buying from owners that are short of cash or hold more than the stock cap of that resource.", fields: [
    { path: "investing_enabled", label: "Agents buy and sell assets", kind: "bool", full: true },
    ...per(RESOURCES, r => ({ path: `asset_output.${r}`, label: `${cap(r)} asset output/step`, kind: "float", min: 0,
      step: 0.01, enabledWhen: v => v.investing_enabled })),
    ...per(RESOURCES, r => ({ path: `asset_return.${r}`, label: `${cap(r)} return (0.01 = 1%)`, kind: "float",
      min: 0.0001, max: 10, step: 0.001, enabledWhen: v => v.investing_enabled })),
    ...per(RESOURCES, r => ({ path: `asset_growth.${r}`, label: `${cap(r)} output growth (0.05 = 5%)`, kind: "float",
      min: -0.99, max: 100, step: 0.01, enabledWhen: v => v.investing_enabled })),
    { path: "asset_growth_steps", label: "… every (steps)", kind: "int", min: 1, max: 100000,
      enabledWhen: v => v.investing_enabled },
    { path: "liquidity_units", label: "Keep cash for (units of each)", kind: "float", min: 0, step: 1,
      enabledWhen: v => v.investing_enabled },
    { path: "min_investment", label: "Invest once spare cash ≥", kind: "float", min: 0.01, step: 1,
      enabledWhen: v => v.investing_enabled },
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

const DISTS = [["fixed", "Fixed"], ["uniform", "Uniform"], ["normal", "Normal (Gaussian)"], ["tiered", "Tiered"]];
const PARAMS = {
  fixed: [["value", "value"]],
  uniform: [["min", "min"], ["max", "max"]],
  normal: [["mean", "mean"], ["std", "std"], ["limit", "cut at ± std"], ["skew", "skew"]],
  tiered: [["average", "average per agent"]],
};
const ALL_PARAMS = [...new Set(Object.values(PARAMS).flat().map(([p]) => p))];
const EXAMPLE_TIERS = [{ agents: 1, share: 50 }, { agents: 10, share: 20 }, { agents: 89, share: 30 }];

// Presets are changes on top of the factory rules.
const PRESETS = [
  ["current", "This game's rules"],
  ["factory", "Factory defaults", {}],
  ["balanced", "Balanced (no shortages)", { rates: { thirst: 0.01 } }],
  // Small stocks + production that differs between agents: some run short, others have surplus.
  ["lean", "Lean start (small stocks, varied production: lots of trading)", {
    inventory: { food: 10, water: 10, games: 10 }, rates: { thirst: 0.01 },
    production: Object.fromEntries(RESOURCES.map(r => [r, { dist: "normal", mean: 10, std: 5, limit: 3, skew: 0 }])) }],
  ["specialists", "Specialists (production varies a lot)", { production: Object.fromEntries(RESOURCES.map(r =>
    [r, { dist: "normal", mean: 12, std: 10, limit: 3, skew: 4 }])) }],
  ["unequal", "Unequal wealth (1% hold 50% of money)", { money: { dist: "tiered", average: 100, tiers: EXAMPLE_TIERS } }],
  ["drought", "Drought (water is rare)", { inventory: { water: 30 }, production: { water: 40 } }],
  ["easy", "Easy (no death or depression)", { death_enabled: false, depression_enabled: false }],
  ["barter", "Barter (fixed 1:1 prices)", { price_mode: "fixed", fixed_prices: { food: 1, water: 1, games: 1 } }],
];

let rulesInfo = null;   // {current, factory} from the server

const setupInput = (name) => setupUi.form.elements[name];
const param = (f, p) => setupInput(`${f.path}#${p}`);
const rowOf = (f) => setupUi.form.querySelector(`.spread-row[data-path="${f.path}"]`);
const roundTo = (v, f) => f.whole ? Math.round(v) : Number(Number(v).toPrecision(4));

function mergeRules(base, changes) {
  const out = structuredClone(base);
  for (const [k, v] of Object.entries(changes)) {
    out[k] = v && typeof v === "object" && !("dist" in v) ? { ...out[k], ...v } : v;
  }
  return out;
}

function numberInput(name, attrs) {
  const el = document.createElement("input");
  el.type = "number";
  el.name = name;
  for (const [k, v] of Object.entries(attrs)) if (v !== undefined) el[k] = v;
  return el;
}

// ---------- building the form ----------

function buildSpreadRow(f) {
  const row = document.createElement("div");
  row.className = "spread-row";
  row.dataset.path = f.path;
  const name = document.createElement("span");
  name.className = "spread-name";
  name.textContent = f.label;

  const dist = document.createElement("select");
  dist.name = `${f.path}#dist`;
  for (const [value, text] of DISTS) if (value !== "tiered" || f.tiered) dist.add(new Option(text, value));
  dist.onchange = () => switchDist(f);

  const params = document.createElement("div");
  params.className = "spread-params";
  const attrs = {
    value: { min: f.min, max: f.max, step: f.whole ? 1 : f.step },
    min: { min: f.min, max: f.max, step: f.whole ? 1 : f.step },
    max: { min: f.min, max: f.max, step: f.whole ? 1 : f.step },
    mean: { min: f.min, max: f.max, step: f.step },
    std: { min: 0, step: f.step },
    limit: { min: 0.1, max: 10, step: 0.5, title: "Values further than this many standard deviations from the mean are re-drawn" },
    skew: { min: -20, max: 20, step: 0.5, title: "0 = symmetric. Positive: most agents low, a few high. Negative: the opposite." },
    average: { min: f.min, max: f.max, step: f.step },
  };
  const labels = Object.fromEntries(Object.values(PARAMS).flat());
  for (const p of ALL_PARAMS) {
    const label = document.createElement("label");
    label.dataset.param = p;
    label.append(labels[p], numberInput(`${f.path}#${p}`, attrs[p]));
    params.append(label);
  }
  // Rows of the same group (inventory.*, production.*, rates.*) can share a distribution.
  const group = f.path.includes(".") ? f.path.split(".")[0] : null;
  const copy = document.createElement("button");
  copy.type = "button";
  copy.className = "copy-btn";
  copy.textContent = group === "rates" ? "Copy to all needs" : "Copy to all resources";
  copy.title = "Use this distribution for the other rows of this group";
  copy.onclick = () => copyToGroup(f);
  copy.hidden = !group;

  const hist = document.createElement("canvas");
  hist.className = "hist";
  hist.width = 120;
  hist.height = 30;
  hist.title = "Shape of the distribution (preview)";

  const tiers = document.createElement("div");
  tiers.className = "tiers";
  row.append(name, dist, params, hist, copy, tiers);
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
      f.section = section;
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
        el = numberInput(f.path, { min: f.min, max: f.max, step: f.kind === "int" ? 1 : f.step, placeholder: f.placeholder });
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

// ---------- tiers editor ----------
// The tiers you edit are the top groups; "everyone else" is whatever is left of the
// agents and of the total, so the percentages always add up to 100.

function renderTiers(f, tiers) {
  const box = rowOf(f).querySelector(".tiers");
  box.innerHTML = "";
  const editable = tiers.slice(0, -1);
  const head = document.createElement("div");
  head.className = "tier-row tier-head";
  head.append(...["Agents", "hold % of total", "with this many agents", ""].map(t => Object.assign(document.createElement("span"), { textContent: t })));
  box.append(head);
  editable.forEach((t, i) => {
    const row = document.createElement("div");
    row.className = "tier-row";
    const who = document.createElement("label");
    who.append(i === 0 ? "top" : "next", numberInput(`${f.path}#tier${i}agents`, { min: 0.001, max: 100, step: "any", value: t.agents }), "%");
    const share = document.createElement("label");
    share.append(numberInput(`${f.path}#tier${i}share`, { min: 0, max: 100, step: "any", value: t.share }), "%");
    const each = Object.assign(document.createElement("span"), { className: "tier-each" });
    const remove = Object.assign(document.createElement("button"), { type: "button", textContent: "✕", title: "Remove tier",
      className: "tier-remove" });
    remove.onclick = () => { const all = readTiers(f); all.splice(i, 1); renderTiers(f, normalizeTiers(all)); updateSetup(); };
    row.append(who, share, each, remove);
    box.append(row);
  });
  const rest = document.createElement("div");
  rest.className = "tier-row tier-rest";
  rest.append(Object.assign(document.createElement("span"), { className: "rest-agents" }),
              Object.assign(document.createElement("span"), { className: "rest-share" }),
              Object.assign(document.createElement("span"), { className: "tier-each" }));
  box.append(rest);
  const add = Object.assign(document.createElement("button"), { type: "button", textContent: "+ Add tier", className: "tier-add" });
  add.onclick = () => {
    const all = readTiers(f);
    const last = all[all.length - 1];
    // Split a slice off "everyone else": a tenth of its agents with a quarter of its share.
    const newTier = { agents: +(last.agents / 10).toPrecision(3), share: +(last.share / 4).toPrecision(3) };
    all.splice(all.length - 1, 0, newTier);
    renderTiers(f, normalizeTiers(all));
    updateSetup();
  };
  box.append(add);
}

// Make the last tier take whatever percentage is left.
function normalizeTiers(tiers) {
  const head = tiers.slice(0, -1);
  const used = (k) => head.reduce((s, t) => s + t[k], 0);
  return [...head, { agents: +(100 - used("agents")).toFixed(6), share: +(100 - used("share")).toFixed(6) }];
}

function readTiers(f) {
  const tiers = [];
  for (let i = 0; param(f, `tier${i}agents`); i++) {
    tiers.push({ agents: Number(param(f, `tier${i}agents`).value), share: Number(param(f, `tier${i}share`).value) });
  }
  return normalizeTiers([...tiers, { agents: 0, share: 0 }]);
}

// Agents per tier for n agents, as the server does it (simulation/distributions.py):
// largest-remainder rounding, at least one agent per tier while there are enough agents,
// and an empty tier's share moves to the next tier.
function tierSplit(spec, n) {
  const exact = spec.tiers.map(t => n * t.agents / 100);
  const counts = exact.map(Math.floor);
  const order = exact.map((e, i) => i).sort((a, b) => (exact[b] - counts[b]) - (exact[a] - counts[a]));
  order.slice(0, n - counts.reduce((a, b) => a + b, 0)).forEach(i => counts[i]++);
  counts.forEach((c, i) => {
    if (c === 0 && n >= counts.length) {
      const donor = counts.indexOf(Math.max(...counts));
      counts[donor]--;
      counts[i]++;
    }
  });
  const shares = spec.tiers.map(t => t.share);
  counts.forEach((c, i) => {
    if (c === 0 && shares[i]) {
      let j = counts.findIndex((k, idx) => idx > i && k > 0);
      if (j < 0) j = counts.map((k, idx) => k > 0 ? idx : -1).filter(x => x >= 0).pop();
      shares[j] += shares[i];
      shares[i] = 0;
    }
  });
  const total = spec.average * n;
  return counts.map((c, i) => ({ count: c, each: c ? total * shares[i] / 100 / c : 0 }));
}

function updateTierTexts(f, spec) {
  const box = rowOf(f).querySelector(".tiers");
  const tiers = spec.tiers;
  const last = tiers[tiers.length - 1];
  const n = Number(setupInput("agents").value) || 0;
  const split = n ? tierSplit(spec, n) : [];
  box.querySelector(".rest-agents").textContent = `everyone else (${+last.agents.toFixed(3)}%)`;
  box.querySelector(".rest-share").textContent = `${+last.share.toFixed(3)}%`;
  box.querySelectorAll(".tier-each").forEach((el, i) => {
    const s = split[i];
    el.textContent = !s ? "" : s.count === 0
      ? `no agents with ${n} agents (share goes to the next tier)`
      : `${s.count} agent${s.count === 1 ? "" : "s"} × ${roundTo(s.each, f)}`;
  });
}

// ---------- reading / writing a spread row ----------

// Default parameters for `dist` centred on value v.
function defaultsFor(dist, v, f) {
  const lo = Math.max(f.min ?? 0, v * 0.5), hi = Math.min(f.max ?? Infinity, v === 0 ? 1 : v * 1.5);
  if (dist === "fixed") return { value: roundTo(v, f) };
  if (dist === "uniform") return { min: roundTo(lo, f), max: roundTo(hi, f) };
  if (dist === "normal") return { mean: roundTo(v, f), std: roundTo((hi - lo) / 4, f) || (f.step ?? 1), limit: 3, skew: 0 };
  return { average: roundTo(v, f), tiers: EXAMPLE_TIERS };
}

function fillSpread(f, spec) {
  const dist = typeof spec === "number" ? "fixed" : spec.dist;
  param(f, "dist").value = dist;
  rowOf(f).dataset.dist = dist;
  const values = typeof spec === "number" ? { value: spec } : spec;
  for (const p of ALL_PARAMS) param(f, p).value = values[p] ?? "";
  if (dist === "tiered") renderTiers(f, spec.tiers);
  showParams(f);
}

// The distribution <select> changed: rebuild the row around the old distribution's average.
function switchDist(f) {
  const select = param(f, "dist");
  const dist = select.value;
  select.value = rowOf(f).dataset.dist;   // read the old values with the old distribution
  let center;
  try { center = spreadMean(readSpread(f)); } catch { center = f.min ?? 0; }
  fillSpread(f, dist === "fixed" ? roundTo(center, f) : { dist, ...defaultsFor(dist, center, f) });
  updateSetup();
}

function showParams(f) {
  const dist = param(f, "dist").value;
  const shown = PARAMS[dist].map(([p]) => p);
  const row = rowOf(f);
  for (const label of row.querySelectorAll(".spread-params label")) label.hidden = !shown.includes(label.dataset.param);
  row.querySelector(".hist").hidden = dist === "fixed" || dist === "tiered";
  row.querySelector(".tiers").hidden = dist !== "tiered";
}

function readSpread(f) {
  const dist = param(f, "dist").value;
  const value = {};
  for (const [p, label] of PARAMS[dist]) {
    const raw = param(f, p).value;
    if (raw === "") throw new Error(`${f.label}: ${label} can't be empty`);
    value[p] = Number(raw);
  }
  for (const p of ["value", "min", "max", "mean", "average"]) {
    if (p in value && ((f.min !== undefined && value[p] < f.min) || (f.max !== undefined && value[p] > f.max))) {
      throw new Error(`${f.label}: ${p} must be between ${f.min ?? "-∞"} and ${f.max ?? "∞"}`);
    }
  }
  if (dist === "fixed") return value.value;
  if (dist === "uniform" && value.min > value.max) throw new Error(`${f.label}: min can't be larger than max`);
  if (dist === "tiered") {
    value.tiers = readTiers(f);
    const last = value.tiers[value.tiers.length - 1];
    if (value.tiers.slice(0, -1).some(t => !(t.agents > 0) || !(t.share >= 0))) {
      throw new Error(`${f.label}: each tier needs agents % above 0 and a share % of 0 or more`);
    }
    if (last.agents <= 0) throw new Error(`${f.label}: the tiers cover more than 100% of agents`);
    if (last.share < 0) throw new Error(`${f.label}: the tiers hold more than 100% of the total`);
  }
  return { dist, ...value };
}

function copyToGroup(f) {
  let spec;
  try { spec = readSpread(f); } catch (err) { return setStatusSetup(err.message); }
  const group = f.path.split(".")[0] + ".";
  for (const other of SETUP_FIELDS) {
    if (other !== f && other.kind === "spread" && other.path.startsWith(group)) fillSpread(other, structuredClone(spec));
  }
  updateSetup();
}

// ---------- whole form ----------

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
  if (typeof spec === "number" || spec.dist === "tiered") return;
  const [lo, hi] = spreadBounds(spec, f.min ?? -Infinity, f.max ?? Infinity);
  if (!(hi > lo)) return;
  // Whole-number values get one bar per integer (up to 24) so bars don't alias.
  const count = f.whole ? Math.min(24, Math.round(hi - lo) + 1) : 24;
  const span = f.whole ? hi - lo + 1 : hi - lo;
  const bins = new Array(count).fill(0);
  for (let i = 0; i < 2000; i++) {
    let v = sampleSpread(spec, f.min ?? -Infinity, f.max ?? Infinity);
    if (f.whole) v = Math.round(v);
    bins[Math.max(0, Math.min(count - 1, Math.floor((v - lo) / span * count)))]++;
  }
  const top = Math.max(...bins);
  const w = canvas.width / count;
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
      try { spec = readSpread(f); } catch { /* reported in the preview */ }
      const row = rowOf(f);
      row.classList.toggle("changed", spec !== null && JSON.stringify(spec) !== JSON.stringify(factory));
      if (spec !== null) {
        drawHistogram(row.querySelector(".hist"), spec, f);
        if (spec.dist === "tiered") updateTierTexts(f, spec);
      }
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

function setStatusSetup(message) {
  setupUi.status.textContent = message;
  setupUi.status.hidden = !message;
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
    if (varies(r.production[res]) || varies(r.rates[need]) || varies(r.inventory[res])) {
      line(`   ${cap(res)} differs between agents, so some will have surplus to sell to others.`);
    }
  }
  const stock = RESOURCES.map(x => avg(r.inventory[x]));
  const needPerStep = Math.max(...RESOURCES.map(x => avg(r.rates[NEED_FOR[x]]) / r.relief_per_unit));
  if (Math.min(...stock) / needPerStep > 300) {
    line(`Agents start with enough of everything for ${Math.round(Math.min(...stock) / needPerStep)}+ steps, ` +
         "so they won't need to trade for a long time. Lower the starting inventory for more trading.");
  }

  if (r.stockpiling_enabled) {
    line(`Stockpiling: when a resource's average per agent falls ${(r.scarcity_trigger * 100).toFixed(0)}% within ` +
         `${r.scarcity_window} steps, agents short of it want ${r.stockpile_steps} steps of their own use in reserve ` +
         `(up to 3× if it falls faster), spending at most ${(r.stockpile_budget * 100).toFixed(0)}% of their money per trade.`);
  }

  if (r.demand_pricing_enabled) {
    const clamp = (v) => Math.min(Math.max(v, r.price_floor), r.price_cap);
    for (const x of RESOURCES) {
      const at = (b, s) => clamp(((b + 1) / (s + 1)) ** r.price_elasticity[x]);
      line(`${cap(x)}: 9 buyers for 1 seller → ×${at(9, 1).toFixed(2)}; 1 buyer for 9 sellers → ×${at(1, 9).toFixed(2)}; ` +
           `supply held by one agent → ×${clamp(1 + r.concentration_weight[x]).toFixed(2)}.`);
    }
    line(`Prices close ${(r.price_adjust_speed * 100).toFixed(0)}% of the gap each step` +
         (r.unit_markup ? `, and the 5th unit in one deal costs ×${((1 + r.unit_markup) ** 4).toFixed(2)} the first.` : "."));
  }

  if (r.investing_enabled) {
    // Starting prices as in the "Starting prices" line below.
    const stock = RESOURCES.map(x => avg(r.inventory[x]));
    const units = stock.reduce((a, b) => a + b, 0);
    const startPrices = RESOURCES.map((x, i) => r.price_mode === "fixed" ? r.fixed_prices[x]
      : units ? avg(r.money) / units * (1 - stock[i] / units) : 0);
    RESOURCES.forEach((x, i) => {
      const out = r.asset_output[x];
      const grown = out * (1 + r.asset_growth[x]) ** (500 / r.asset_growth_steps);
      const use = avg(r.rates[NEED_FOR[x]]) / r.relief_per_unit;
      line(`${cap(x)} asset: makes ${out} → ${grown.toFixed(3)} ${x}/step after 500 steps` +
           (use ? ` (${(out / use).toFixed(1)}× an average agent's use)` : "") +
           `; costs ${out} × ${startPrices[i].toFixed(3)} ÷ ${r.asset_return[x]} = ${(out * startPrices[i] / r.asset_return[x]).toFixed(2)} at starting prices.`,
           out / (use || 1) > 3 ? "short" : "");
    });
    const held = RESOURCES.reduce((sum, x) => sum + avg(r.assets[x]), 0);
    line(`Assets: an average agent starts with ${held.toFixed(2)} assets in total. No new assets are ever made, ` +
         (held ? "so investing means buying them from other agents." : "so with none to start, nobody can invest."),
         held ? "" : "short");
  }

  const g = avg(r.rates.sleep), rec = avg(r.sleep_recovery);
  line(rec
    ? `Sleep: an average agent rests about ${(100 * g / (g + rec || 1)).toFixed(0)}% of the time.`
    : "Sleep: recovery is 0, so a tired agent stops forever.", rec ? "" : "short");

  if (r.price_mode === "fixed") {
    line(`Prices are fixed: ${RESOURCES.map(x => `${x} ${r.fixed_prices[x]}`).join(", ")}.`);
  } else {
    const total = stock.reduce((a, b) => a + b, 0);
    const money = avg(r.money);
    const prices = RESOURCES.map((x, i) => total ? (money / total) * (1 - stock[i] / total) : 0);
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
  setStatusSetup("");
  setupUi.screen.hidden = false;
  document.body.classList.add("setup-open");
  fillSetup(rulesInfo.current, state?.seed ?? "");
}

function closeSetup() {
  setupUi.screen.hidden = true;
  document.body.classList.remove("setup-open");
}

setupUi.form.oninput = updateSetup;
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
    setStatusSetup(err.message);
  }
};

buildSetupForm();
openSetup();  // the setup screen is the first thing you see
