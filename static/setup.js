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
// Layer of a good under the default recipes (used to group fields; the game's own layers follow its recipes).
function catalogLayer(g, inputs = Object.fromEntries(GOODS.map(x => [x, CATALOG_INFO[x].inputs])), seen = new Set()) {
  if (seen.has(g)) return 1;
  seen.add(g);
  const recipe = inputs[g] || {};
  return 1 + Math.max(0, ...Object.keys(recipe).map(i => catalogLayer(i, inputs, new Set(seen))));
}
// Industries that exist in a game (as rules.py): layer <= industry_layers, not excluded, and
// every input of the recipe exists too. Returns {active: Set, auto: {good: missing input}}.
function gameIndustries(r) {
  const inputs = r.inputs || {};
  const layerOf = (g) => catalogLayer(g, inputs);
  const excluded = new Set(r.excluded_industries || []);
  const active = new Set(), auto = {};
  for (const g of [...GOODS].sort((a, b) => layerOf(a) - layerOf(b))) {
    if (layerOf(g) > r.industry_layers || excluded.has(g)) continue;
    const missing = Object.keys(inputs[g] || {}).find(i => !active.has(i));
    if (missing) auto[g] = missing; else active.add(g);
  }
  return { active, auto };
}

// Quick starts for the industry picker: how many layers, every industry in them included.
const GAME_SIZES = [[1, "Simple · layer 1"], [2, "Basic · layers 1–2"], [3, "Standard · layers 1–3"], [10, "Full · every layer"]];

const SETUP_SECTIONS = [
  { title: "World", hint: "How many agents, and how meetings work.", fields: [
    { path: "agents", label: "Agents", kind: "int", min: 1, max: 5000 },
    { path: "seed", label: "Seed", kind: "int", optional: true, placeholder: "random" },
    { path: "contact_distance", label: "Touch distance (px)", kind: "float", min: 1, max: 200, step: 1 },
    { path: "trade_radius", label: "Trading / perception radius (px; 0 = touch only)", kind: "float", min: 0, max: 5000, step: 25 },
    { path: "depart_steps", label: "Walk apart (days)", kind: "int", min: 0, max: 1000 },
    { path: "cooldown_steps", label: "Ignore each other after a deal (days)", kind: "int", min: 0, max: 10000 },
    { path: "retry_steps", label: "… after no deal (days)", kind: "int", min: 0, max: 10000 },
  ]},
  { title: "Modules: what this economy has", wide: true, hint: "Switch whole parts of the economy on or off. A module " +
      "only works with the modules it needs (greyed out otherwise). Quick starts below set a whole combination.",
    fields: [{ path: "#game-types", kind: "game-types" },
             ...window.CATALOG.modules.map(m => ({ path: m.rule, label: m.label, kind: "bool", module: m, full: true }))] },
  { title: "Game size: layers and industries", wide: true, fields: [
    { path: "industry_layers", label: "Industry layers in this game (1–10)", kind: "int", min: 1, max: 10, full: true },
    { path: "#autosize", label: "Size starting industries to this game (recommended when you change layers or industries)",
      kind: "bool", full: true, local: true },
    { path: "excluded_industries", label: "Industries in this game", kind: "industries", full: true },
  ], hint: "Pick a smaller economy for a simpler (and faster) game: fewer layers, or leave out single industries. " +
      "Every industry the game keeps still needs all the inputs of its recipe, so leaving one out also leaves out what " +
      "is made from it. Each good is checked against every agent each day, so fewer industries also run faster." },
  { title: "Prices", hint: "Relative prices follow scarcity: total money ÷ total units × (1 − share of that resource). " +
      "The price level follows the quantity theory of money, M × V = P × Y: all prices are scaled so a year of what " +
      "people consume costs the money supply × velocity. With velocity 4 money changes hands 4 times a year, so an " +
      "average agent's cash lasts about 3 months. Fixed: the prices below.", fields: [
    { path: "price_mode", label: "Price rule", kind: "choice", full: true,
      options: [["cost", "Cost + margin, × demand and inventory"], ["scarcity", "Scarcity (older formula)"], ["fixed", "Fixed prices"]] },
    { path: "cost_floor_margin", label: "Margin over cost (base price)", kind: "float", min: 0, max: 10, step: 0.01 },
    { path: "stock_target_days", label: "Inventory target (days of sales)", kind: "float", min: 0.1, step: 5,
      enabledWhen: v => v.price_mode === "cost" },
    { path: "stock_adjust_speed", label: "Prices move with inventory by up to (share a day)", kind: "float", min: 0, max: 1, step: 0.01,
      enabledWhen: v => v.price_mode === "cost" },
    { path: "distress_max", label: "Sellers short of cash give up to (share off)", kind: "float", min: 0, max: 1, step: 0.05 },
    { path: "distress_days", label: "… when cash can't cover (days of wages and loans)", kind: "float", min: 0, step: 1 },
    { path: "price_stickiness", label: "Price stickiness (0 = perfectly flexible; 0.8 = close 20% of the gap a day)",
      kind: "float", min: 0, max: 0.99, step: 0.05, enabledWhen: v => v.price_mode !== "fixed" },
    { path: "money_velocity", label: "Money velocity (times a year; 0 = off)", kind: "float", min: 0, max: 1000, step: 0.5,
      enabledWhen: v => v.price_mode !== "fixed" },
    { path: "fixed_prices.labor", label: "Wage", kind: "float", min: 0, step: 0.01, enabledWhen: v => v.price_mode === "fixed" },
  ]},
  { title: "Starting agents", wide: true,
    hint: "What each new agent begins with. Every row has its own distribution; “Copy to all resources” reuses one.", fields: [
    ...per(RESOURCES, r => ({ path: `inventory.${r}`, label: label(r), kind: "spread", whole: true, tiered: true, min: 0,
      group: `Starting stock · layer ${catalogLayer(r)} goods` })),
    ...per(GOODS, r => ({ path: `assets.${r}`, label: `${label(r)} (shares)`, kind: "spread", tiered: true,
      min: 0, step: 0.1, group: `Starting industries (asset shares) · layer ${catalogLayer(r)}` })),
    { path: "asset_owner_share", label: "Restrict all assets to a fixed share of agents (1 = follow each asset's distribution freely; 0.1 = 10% own all)",
      kind: "float", min: 0.001, max: 1, step: 0.05 },
    { path: "working_capital_days", label: "Companies start with working capital for (days of wages)", kind: "int", min: 0, max: 3600 },
    { path: "money", label: "Money", kind: "spread", tiered: true, min: 0, step: 0.01 },
    { path: "movement", label: "Movement (px)", kind: "spread", whole: true, min: 1, max: 200 },
    { path: "start_needs", label: "Starting needs", kind: "spread", min: 0, max: 1, step: 0.05 },
    { path: "risk_appetite", label: "Personality: risk appetite (0-1)", kind: "spread", min: 0, max: 1, step: 0.05 },
    { path: "lavishness", label: "Personality: frugal (0) – lavish (1)", kind: "spread", min: 0, max: 1, step: 0.05 },
    { path: "payout_ratio", label: "Personality: pays out (share of profits)", kind: "spread", min: 0, max: 1, step: 0.05 },
  ]},
  { title: "Labour capacity", wide: true, hint: "Labour is the only thing agents make themselves, and it is never stored: " +
      "each day agents can work up to their capacity (scaled by efficiency) and sell it in the labour market. Anything " +
      "unsold is lost. Every good is only made by its industry's assets worked by labour.", fields: [
    { path: "labor_capacity", label: "Capacity per day", kind: "spread", min: 0, step: 0.05 },
  ]},
  { title: "Housing market", hint: "Houses are whole assets, each housing one agent; homebuilders add new ones; the homeless " +
      "suffer. All but the starting stock can be changed in the Housing tab during the game.", fields: [
    { path: "starting_houses", label: "Houses per agent at the start", kind: "float", min: 0, max: 5, step: 0.05,
      enabledWhen: v => v.housing_enabled },
    { path: "house_min_multiple", label: "Minimum house price (× the price of food)", kind: "float", min: 0, step: 5,
      enabledWhen: v => v.housing_enabled },
    { path: "rent_yield", label: "Rent (% of the price a year)", kind: "float", min: 0, step: 0.5, yearly: true,
      enabledWhen: v => v.housing_enabled },
    { path: "eviction_days", label: "Evict after (days of unpaid rent)", kind: "int", min: 1, max: 3600,
      enabledWhen: v => v.housing_enabled },
    { path: "house_units", label: "Housing units per house", kind: "int", min: 1, max: 10000,
      enabledWhen: v => v.housing_enabled },
    { path: "homeless_shelter_rate", label: "Homeless: shelter grows per day", kind: "float", min: 0, max: 1, step: 0.005,
      enabledWhen: v => v.housing_enabled },
  ]},
  { title: "Labour market", hint: "Base wage = labour share × value one unit of labour makes. The wage then follows " +
      "labour wanted ÷ capacity offered (labour elasticity in Market dynamics). Agents offer more and ask less when they " +
      "need a job more; healthy agents ask more.", fields: [
    { path: "labor_share", label: "Labour share of output value (first day's wage)", kind: "float", min: 0, max: 1, step: 0.05 },
    { path: "wage_adjust_speed", label: "Wages move with supply and demand (base share a month; doubles each persistent month)", kind: "float", min: 0, max: 1, step: 0.005 },
    { path: "wage_down_speed", label: "… downward base share a month (same as upward by default)", kind: "float", min: 0, max: 1, step: 0.005 },
    { path: "wage_speed_max", label: "… cap on accelerated monthly wage adjustment", kind: "float", min: 0, max: 10, step: 0.05 },
    { path: "labor_offer_months", label: "Offer all spare labour below (months of living costs)", kind: "float", min: 0, max: 1000, step: 1 },
    { path: "skill_max", label: "… up to (× productivity in an industry)", kind: "float", min: 1, max: 1000, step: 0.5,
      enabledWhen: v => v.specialization_enabled },
    { path: "skill_scale", label: "… learning scale (units of labour for ~63% of it)", kind: "float", min: 0.01, step: 5,
      enabledWhen: v => v.specialization_enabled },
    { path: "auto_skill_floor", label: "… autonomous production falls to (share of the start)", kind: "float", min: 0, max: 1, step: 0.01,
      enabledWhen: v => v.specialization_enabled },
    { path: "subsistence_rates.water", label: "Autonomous production: water per unit of labour", kind: "float", min: 0, max: 10, step: 0.05 },
    { path: "subsistence_rates.food", label: "Autonomous production: food per unit of labour", kind: "float", min: 0, max: 10, step: 0.05 },
    { path: "survival_effort", label: "Autonomous production: share of labour a struggling agent can still use", kind: "float", min: 0, max: 1, step: 0.05 },
    { path: "participation_floor", label: "Offer at least (share of capacity)", kind: "float", min: 0, max: 1, step: 0.05 },
    { path: "bargaining_spread", label: "Bargaining spread", kind: "float", min: 0, max: 2, step: 0.05 },
    { path: "money_weight", label: "Need: weight of money (vs needs)", kind: "float", min: 0, max: 1, step: 0.05 },
    { path: "comfort_steps", label: "Comfortable cash (days of living)", kind: "int", min: 0, max: 100000 },
  ]},
  { title: "Efficiency and wellbeing", hint: "Efficiency = 1 − Σ weight × need − depression penalty (at least the minimum). " +
      "It scales how much labour an agent can give. Wellbeing uses the same weights and raises its asking wage.", fields: [
    ...per(NEEDS, n => ({ path: `efficiency_weights.${n}`, label: `${cap(n)} weight`, kind: "float", min: 0, max: 5, step: 0.05 })),
    { path: "depression_penalty", label: "Depression penalty", kind: "float", min: 0, max: 1, step: 0.05 },
    { path: "min_efficiency", label: "Minimum efficiency", kind: "float", min: 0, max: 1, step: 0.05 },
  ]},
  { title: "Resource consumption", wide: true, hint: "How fast each need grows per day, and how sleep recovers at rest.", fields: [
    ...per(NEEDS, n => ({ path: `rates.${n}`, label: `${cap(n)} /day`, kind: "spread", min: 0, max: 1, step: 0.001 })),
    { path: "sleep_recovery", label: "Sleep recovery", kind: "spread", min: 0, max: 1, step: 0.01 },
  ]},
  { title: "Trading", hint: "A buyer buys its need × a random multiplier between these two (stocking up), " +
      "limited by what the seller can spare and what the buyer can pay.", fields: [
    { path: "purchase_min", label: "Buy at least ×", kind: "float", min: 1, max: 10, step: 0.1 },
    { path: "purchase_max", label: "Buy at most ×", kind: "float", min: 1, max: 10, step: 0.1 },
  ]},
  { title: "Stock band", hint: "Agents keep between the floor and the cap of each resource: above the cap they go " +
      "out to sell the surplus (to make money for assets); below the floor they go out to buy back up to the cap.", fields: [
    { path: "stock_steps", label: "Cap (days of each need)", kind: "int", min: 1, enabledWhen: v => v.selling_enabled },
    { path: "restock_below", label: "Floor (0.5 = half the cap)", kind: "float", min: 0, max: 1, step: 0.05,
      enabledWhen: v => v.selling_enabled },
  ]},
  { title: "Market dynamics: stockpiling", hint: "When a resource's average per agent falls by the trigger " +
      "within the window, agents hoard it: they buy a reserve (paid in money, within a budget) and stop selling into it.", fields: [
    { path: "scarcity_window", label: "Watch the last (days)", kind: "int", min: 10, max: 500,
      enabledWhen: v => v.stockpiling_enabled },
    { path: "scarcity_trigger", label: "Scarce after a fall of (0.1 = 10%)", kind: "float", min: 0.01, max: 0.9, step: 0.01,
      enabledWhen: v => v.stockpiling_enabled },
    { path: "stockpile_steps", label: "Reserve (days of own use)", kind: "int", min: 0, max: 5000,
      enabledWhen: v => v.stockpiling_enabled },
    { path: "stockpile_budget", label: "Spend at most (0.5 = half its money)", kind: "float", min: 0, max: 1, step: 0.05,
      enabledWhen: v => v.stockpiling_enabled },
  ]},
  { title: "Market dynamics: demand and concentration", hint: "Price = money ÷ units × (1 − share) × demand pressure × " +
      "concentration. Pressure = ((buyers+1) ÷ (sellers+1)) ^ elasticity. Concentration = 1 + weight × C, where C is 0 when the " +
      "sellable supply is spread evenly and 1 when one agent holds it all. Under pressure, each extra unit in a deal costs more.", fields: [
    { path: "price_elasticity.labor", label: "Labour elasticity (0 = none)", kind: "float", min: 0, max: 3, step: 0.1,
      enabledWhen: v => v.demand_pricing_enabled },
    { path: "concentration_weight.labor", label: "Labour concentration weight", kind: "float", min: 0, max: 10, step: 0.1,
      enabledWhen: v => v.demand_pricing_enabled },
    { path: "price_adjust_speed", label: "Speed (share of gap per day)", kind: "float", min: 0.01, max: 1, step: 0.05,
      enabledWhen: v => v.demand_pricing_enabled },
    { path: "price_floor", label: "Never below base ×", kind: "float", min: 0.01, max: 1, step: 0.05,
      enabledWhen: v => v.demand_pricing_enabled },
    { path: "price_cap", label: "Never above base ×", kind: "float", min: 1, max: 100, step: 0.5,
      enabledWhen: v => v.demand_pricing_enabled },
    { path: "unit_markup", label: "Extra unit costs more (0.05 = +5%)", kind: "float", min: 0, max: 1, step: 0.01,
      full: true, enabledWhen: v => v.demand_pricing_enabled },
  ]},
  { title: "Industries and layers", hint: "Every good has its own industry (sector and industry names follow the " +
      "TRBC classification used by investing.com). Layer 1 industries extract (capital + labour); an industry that uses " +
      "layer-n goods is layer n + 1. Industries deeper than the number of layers chosen here don't exist in this game. " +
      "A unit relieves its need by base relief × fit × (1 + layer bonus × (layer − 1)), so deeper layers address needs " +
      "better. Every unit is thrown away once it is older than its shelf life. New industry capacity is built from capital " +
      "goods (machinery, construction), which are made very slowly, so building takes time.", fields: [
    { path: "build_min_q", label: "Build when an asset is worth ≥ (× its cost)", kind: "float", min: 0, step: 0.1,
      enabledWhen: v => v.building_enabled },
    { path: "project_steps", label: "Drop unfinished projects after (days)", kind: "int", min: 1,
      enabledWhen: v => v.building_enabled },
    { path: "layer_bonus", label: "Extra relief per layer (0.5 = +50%)", kind: "float", min: 0, max: 10, step: 0.1 },
    { path: "input_buffer_steps", label: "Owners keep inputs for (days)", kind: "int", min: 1, max: 10000 },
    { path: "input_reorder", label: "… and reorder below (share)", kind: "float", min: 0, max: 1, step: 0.05 },
    { path: "output_buffer_steps", label: "Stop producing above (days of output held)", kind: "int", min: 0 },
    { path: "max_output_stock", label: "… or above (units held, 0 = never)", kind: "int", min: 0 },
    { path: "cost_floor", label: "Secondary goods never sell below their inputs", kind: "bool", full: true },
    { path: "profit_check", label: "Industries stop hiring when labour costs more than it adds", kind: "bool", full: true },
    { path: "labor_priority", label: "Labour goes", kind: "choice", full: true,
      options: [["even", "Evenly over an owner's industries"], ["value", "To the most valuable industries first"]] },
  ]},
  { title: "Industry catalog", wide: true, hint: "One block per industry. Recipe: what one unit uses (e.g. “1 grain”; " +
      "empty = extraction). Effects: what consuming one unit does to each need, from −1 (harms) to +1 (fully relieves); " +
      "a good can help several needs and hurt others (fast food: hunger +, boredom +, health −). Benefits grow with the " +
      "layer, harm doesn't; sleep can only be harmed. New asset share costs: the capital goods (machinery, construction, " +
      "electronics) one new share of this industry is built from. Shelf life in days (0 = never " +
      "expires). Jobs per asset × units per labour = what one asset makes per day when fully staffed.", fields:
    GOODS.flatMap(g => {
      const e = CATALOG_INFO[g];
      const group = `${e.label} · layer ${catalogLayer(g)} · ${e.sector} · ${e.industry}`;
      return [
        { path: `inputs.${g}`, label: "Uses per unit", kind: "recipe", full: true, group },
        { path: `build_cost.${g}`, label: "New asset share costs", kind: "recipe", full: true, group, allowSelf: true },
        ...NEEDS.map(n => ({ path: `effects.${g}.${n}`, label: `Effect on ${n}`, kind: "float", group, optional: true,
          min: -1, max: n === "sleep" ? 0 : 1, step: 0.05, placeholder: "0" })),
        { path: `shelf_life.${g}`, label: "Shelf life (days)", kind: "int", min: 0, group },
        { path: `asset_labor.${g}`, label: "Jobs per asset", kind: "float", min: 0, step: 0.05, group },
        { path: `productivity.${g}`, label: "Units per labour", kind: "float", min: 0, step: 0.1, group },
        { path: `productivity_growth.${g}`, label: "Productivity growth", kind: "float", min: -0.99, max: 100, step: 0.01, group },
        { path: `labor_saving.${g}`, label: "Labour-saving", kind: "float", min: -1, max: 0.99, step: 0.01, group },
        { path: `asset_return.${g}`, label: "Asset return (per day)", kind: "float", min: 0.0001, max: 10, step: 0.001, group },
        { path: `fixed_prices.${g}`, label: "Fixed price", kind: "float", min: 0, step: 0.01, group,
          enabledWhen: v => v.price_mode === "fixed" },
        { path: `price_elasticity.${g}`, label: "Price elasticity", kind: "float", min: 0, max: 3, step: 0.1, group,
          enabledWhen: v => v.demand_pricing_enabled },
        { path: `concentration_weight.${g}`, label: "Concentration weight", kind: "float", min: 0, max: 10, step: 0.1, group,
          enabledWhen: v => v.demand_pricing_enabled },
      ];
    }) },
  { title: "Assets, productivity and investment", hint: "Each good has its own asset. One asset share employs up to " +
      "“jobs per asset” labour per day; each unit of labour makes “productivity” units of the good, and productivity grows " +
      "over time (per-industry numbers are in the Industry catalog). Output = productivity × min(labour, shares × jobs " +
      "per asset). The only assets are the starting ones; they " +
      "change hands between agents. Asset price = output per day × good price ÷ return. Agents invest spare cash in assets " +
      "of what they lack, buying from owners short of cash or holding more than the stock cap of that good.", fields: [
    { path: "productivity_growth_steps", label: "Productivity grows every (days)", kind: "int", min: 1, max: 100000 },
    { path: "liquidity_units", label: "Keep cash for (units of each)", kind: "float", min: 0, step: 1,
      enabledWhen: v => v.investing_enabled },
    { path: "min_investment", label: "Invest once spare cash ≥", kind: "float", min: 0.01, step: 1,
      enabledWhen: v => v.investing_enabled },
    { path: "capital_cash_ratio", label: "Capitalist keeps cash ÷ assets ≥", kind: "float", min: 0, max: 100, step: 0.05,
      enabledWhen: v => v.investing_enabled },
  ]},
  { title: "Banking", hint: "Banks are an industry. To open, a bank needs a banking plant (asset shares, built from " +
      "machinery and construction like any industry, run with labour and electricity) and its founder's own money: at least " +
      "the minimum capital goes in as the bank's equity. The plant makes banking services, and every loan uses them up " +
      "(one unit per “money lent per service unit”). Agents deposit spare cash; investors borrow to build when the asset " +
      "earns more than the loan costs, and agents short of cash borrow for what they need now. Nobody may " +
      "owe more than the chosen share of a month's income. A bank lends only while it keeps the reserve ratio of deposits " +
      "in cash and equity of at least the capital ratio of its loans (Basel). Each day the owner takes its payout share " +
      "(personality) of the bank's profit as dividends and the rest stays as equity, so the bank can lend more. " +
      "Rates are per year.", fields: [
    { path: "starting_banks", label: "Banks at the start", kind: "int", min: 0, max: 1000,
      enabledWhen: v => v.banking_enabled },
    { path: "starting_bank_shares", label: "… each with a plant of (shares)", kind: "float", min: 0.05, step: 0.1,
      enabledWhen: v => v.banking_enabled },
    { path: "bank_min_capital", label: "Minimum capital to open a bank ($)", kind: "float", min: 0, step: 500,
      enabledWhen: v => v.banking_enabled },
    { path: "bank_liquidity", label: "Vault cash each bank keeps (× deposits)", kind: "float", min: 0, max: 1, step: 0.01,
      enabledWhen: v => v.banking_enabled },
    { path: "deposit_rate", label: "Base deposit rate (% a year)", kind: "float", min: 0, step: 0.1, yearly: true,
      enabledWhen: v => v.banking_enabled },
    { path: "bank_rate_competition", label: "Banks compete on deposit rates automatically", kind: "bool",
      enabledWhen: v => v.banking_enabled },
    { path: "loan_spread", label: "Loan rate = deposit rate + (% a year)", kind: "float", min: 0, step: 0.1, yearly: true,
      enabledWhen: v => v.banking_enabled },
    { path: "loan_steps", label: "Loans repaid over (days)", kind: "int", min: 1, enabledWhen: v => v.banking_enabled },
    { path: "max_loan_to_value", label: "Debt ≤ (× value of its assets)", kind: "float", min: 0, max: 10, step: 0.05,
      enabledWhen: v => v.banking_enabled },
    { path: "loan_per_service", label: "Money lent per service unit ($)", kind: "float", min: 0.01, step: 100,
      enabledWhen: v => v.banking_enabled },
    { path: "default_steps", label: "Default after unpaid (days)", kind: "int", min: 1, enabledWhen: v => v.banking_enabled },
    { path: "deposit_share", label: "Share of spare cash deposited", kind: "float", min: 0, max: 1, step: 0.05,
      enabledWhen: v => v.banking_enabled },
    { path: "month_steps", label: "Days in a month", kind: "int", min: 1, enabledWhen: v => v.banking_enabled },
    { path: "loan_income_share", label: "Lend each agent up to (× its monthly income)", kind: "float", min: 0, max: 100,
      step: 0.05, enabledWhen: v => v.banking_enabled },
  ]},
  { title: "Budget", hint: "Every agent knows its budget: what living costs it per day (the cheapest goods for each " +
      "need, housing included, net of what its own industries make) plus its loan payments. It keeps that many days of " +
      "it (a “month”) on top of the cash it needs right now, and only invests or builds with what is left. " +
      "Loans are paid only out of money left after what it needs to buy now.", fields: [
    { path: "budget_steps", label: "Budget covers (days)", kind: "int", min: 0, max: 100000 },
    { path: "mortgage_years", label: "Mortgages: term (years; 0 = none)", kind: "float", min: 0, max: 100, step: 1 },
    { path: "mortgage_dti", label: "Mortgages: installments ≤ (share of income)", kind: "float", min: 0, max: 1, step: 0.05 },
    { path: "mortgage_ltv", label: "Mortgages: lend ≤ (share of the house price)", kind: "float", min: 0, max: 1, step: 0.05 },
    { path: "mortgage_premium", label: "Mortgages: rate = loan rate + (% a year)", kind: "float", min: 0, step: 0.25, yearly: true },
    { path: "mortgage_default_days", label: "Mortgages: foreclose after (days unpaid)", kind: "int", min: 1, max: 3600 },
  ]},
  { title: "Central government", hint: "A minimum interest rate that no asset's return can fall below (higher rates " +
      "make assets cheaper), and labour bought every day with newly created money. Both can be changed during the game " +
      "in the Government tab.", fields: [
    { path: "gov_min_rate", label: "Policy rate: minimum return (% a year)", kind: "float", min: 0, step: 0.25, yearly: true,
      enabledWhen: v => v.government_enabled },
    { path: "taylor_enabled", label: "Central bank sets its rate by the Taylor rule (monthly)", kind: "bool", full: true,
      enabledWhen: v => v.government_enabled },
    { path: "inflation_target", label: "… inflation target (share a year)", kind: "float", min: -0.5, max: 1, step: 0.005,
      enabledWhen: v => v.government_enabled && v.taylor_enabled },
    { path: "neutral_rate", label: "… neutral real rate (share a year)", kind: "float", min: -0.5, max: 1, step: 0.005,
      enabledWhen: v => v.government_enabled && v.taylor_enabled },
    { path: "taylor_unemployment", label: "… normal unemployment (share)", kind: "float", min: 0, max: 1, step: 0.01,
      enabledWhen: v => v.government_enabled && v.taylor_enabled },
    { path: "capital_ratio", label: "Central bank: bank equity ≥ (× loans, Basel)", kind: "float", min: 0, max: 1,
      step: 0.01, enabledWhen: v => v.government_enabled },
    { path: "reserve_ratio", label: "Central bank: reserves banks hold there (× deposits)", kind: "float", min: 0, max: 1,
      step: 0.01, enabledWhen: v => v.government_enabled },
    { path: "reserve_rate", label: "Central bank: interest on reserves (% a year)", kind: "float", min: 0, yearly: true,
      step: 0.0005, enabledWhen: v => v.government_enabled },
    { path: "lender_of_last_resort", label: "Central bank lends to solvent banks short of cash", kind: "bool", full: true,
      enabledWhen: v => v.government_enabled },
    { path: "llr_penalty", label: "… at the policy rate + (% a year)", kind: "float", min: 0, step: 0.1, yearly: true,
      enabledWhen: v => v.government_enabled && v.lender_of_last_resort },
    { path: "gov_bonds_enabled", label: "Government may borrow (bonds)", kind: "bool", full: true,
      enabledWhen: v => v.government_enabled },
    { path: "gov_debt_limit", label: "… debt limit (× a year's GDP)", kind: "float", min: 0, max: 10, step: 0.05,
      enabledWhen: v => v.government_enabled && v.gov_bonds_enabled },
    { path: "gov_bond_spread", label: "… bond rate = central bank rate + (% a year)", kind: "float", min: 0, step: 0.1,
      yearly: true, enabledWhen: v => v.government_enabled && v.gov_bonds_enabled },
    { path: "gov_bond_days", label: "… repaid after (days)", kind: "int", min: 1, max: 3600,
      enabledWhen: v => v.government_enabled && v.gov_bonds_enabled },
    { path: "pay_period", label: "Labour law: wages are paid", kind: "choice", full: true,
      options: [["daily", "Every day"], ["weekly", "Every week"], ["monthly", "Every month"]],
      enabledWhen: v => v.government_enabled },
    { path: "gov_min_wage", label: "Minimum wage ($ per day's work; 0 = none)", kind: "float", min: 0, step: 5,
      enabledWhen: v => v.government_enabled },
    { path: "tax_production", label: "Production tax (share of every sale)", kind: "float", min: 0, max: 1, step: 0.01,
      enabledWhen: v => v.government_enabled },
    { path: "tax_wage", label: "Salary tax (share of wages)", kind: "float", min: 0, max: 1, step: 0.01,
      enabledWhen: v => v.government_enabled },
    { path: "tax_profit", label: "Profit tax (share of profits)", kind: "float", min: 0, max: 1, step: 0.01,
      enabledWhen: v => v.government_enabled },
    { path: "benefit_rate", label: "Unemployment benefit (× the wage)", kind: "float", min: 0, max: 10, step: 0.05,
      enabledWhen: v => v.government_enabled },
    { path: "balanced_budget", label: "Spend all taxes (the rest buys public works)", kind: "bool", full: true,
      enabledWhen: v => v.government_enabled },
    { path: "gov_labor_purchase", label: "Labour bought per day", kind: "float", min: 0, step: 0.5,
      enabledWhen: v => v.government_enabled },
  ]},
  { title: "Need thresholds", hint: "When agents act on a need, and what consuming does.", fields: [
    { path: "seek_threshold", label: "Act above", kind: "float", min: 0, max: 1, step: 0.05 },
    { path: "target_level", label: "Until below", kind: "float", min: 0, max: 1, step: 0.05 },
    { path: "relief_per_unit", label: "1 unit relieves", kind: "float", min: 0.001, max: 1, step: 0.01, full: true },
  ]},
  { title: "Life and death", hint: "What happens when a need reaches 1.00.", fields: [
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
  // Small stocks: agents need each other (and owners need workers) from the start.
  ["lean", "Lean start (small stocks: lots of trading)", {
    inventory: { food: 10, water: 10, games: 10 }, stock_steps: 20,
    money: 1500 }],
  ["spread", "Spread ownership (everyone owns some assets)", { assets: Object.fromEntries(GOODS.map(g =>
    [g, { dist: "uniform", min: 0, max: 2 }])) }],
  ["unequal", "Unequal wealth (1% hold 50% of money)", { money: { dist: "tiered", average: 3000, tiers: EXAMPLE_TIERS } }],
  ["drought", "Drought (few water assets)", { inventory: { water: 30 }, assets: { water: { dist: "tiered", average: 0.4,
    tiers: [{ agents: 10, share: 100 }, { agents: 90, share: 0 }] } } }],
  ["easy", "Easy (no death or depression)", { death_enabled: false, depression_enabled: false }],
  ["barter", "Barter (fixed 1:1 prices)", { price_mode: "fixed", fixed_prices: { food: 20, water: 20, games: 20, labor: 20 } }],
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

// Recipes are typed as "1 grain + 0.5 wood" (amount, then good; "grain" alone means 1).
function formatRecipe(recipe) {
  return Object.entries(recipe || {}).map(([g, q]) => `${+Number(q).toFixed(4)} ${g}`).join(" + ");
}

function parseRecipe(text, good, allowSelf = false) {
  const recipe = {};
  for (const part of text.split("+").map(p => p.trim()).filter(Boolean)) {
    let amount, name, m;
    if ((m = part.match(/^(\d*\.?\d+)?\s*([a-z_]+)$/i))) [, amount, name] = m;        // "0.5 wood", "wood"
    else if ((m = part.match(/^([a-z_]+)\s+(\d*\.?\d+)$/i))) [, name, amount] = m;    // "wood 0.5"
    const input = name?.toLowerCase();
    if (!input || !GOODS.includes(input)) {
      throw new Error(`${label(good)} recipe: “${part}” isn't a good — use amounts of goods by id, e.g. “1 grain + 0.5 natural_gas”`);
    }
    if (input === good && !allowSelf) throw new Error(`${label(good)} can't be an input of itself`);
    const qty = amount === undefined ? 1 : Number(amount);
    if (!(qty >= 0)) throw new Error(`${label(good)} recipe: amount of ${input} must be ≥ 0`);
    if (qty > 0) recipe[input] = (recipe[input] || 0) + qty;
  }
  return recipe;
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
  // Rows of the same group (inventory.*, assets.*, rates.*) can share a distribution.
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

const SETUP_CATEGORIES = [
  { id: "modules",    label: "1. Modules",            match: ["Modules: what this economy has"] },
  { id: "world",      label: "2. World & People",     match: ["World", "Starting agents"] },
  { id: "industries", label: "3. Industries & Stock", match: ["Game size: layers and industries", "Industries", "Assets and investment", "Asset returns"] },
  { id: "labour",     label: "4. Labour & Needs",     match: ["Labour capacity", "Labour market", "Efficiency and wellbeing", "Resource consumption", "Need thresholds", "Life and death"] },
  { id: "markets",    label: "5. Markets & Housing",  match: ["Prices", "Trading", "Market dynamics", "Housing market"] },
  { id: "policy",     label: "6. Banks & Government", match: ["Banking", "Central government"] },
];

const MODULE_TAG = {
  commerce: "Core", industries: "Core", selling: "Markets", pricing: "Markets", stockpiling: "Markets",
  investing: "Capital", building: "Capital", banking: "Finance", consumer_credit: "Finance",
  government: "Policy", housing: "Markets", expiry: "Realism", death: "Realism", penalties: "Realism",
  personality: "Agents", specialization: "Agents", subsistence: "Core", depression: "Agents",
  inheritance: "Realism", shocks: "Trainer", expectations: "Macro", firms: "Corporate",
};

function categoryFor(title) {
  const found = SETUP_CATEGORIES.find(c => c.match.some(m => title.toLowerCase().includes(m.toLowerCase())));
  return found ? found.id : "markets";
}

let activeSetupCat = "modules";

function selectSetupCategory(catId) {
  activeSetupCat = catId;
  const nav = $("setup-nav");
  if (nav) {
    for (const btn of nav.querySelectorAll("button")) {
      btn.classList.toggle("active", btn.dataset.cat === catId);
    }
  }
  for (const box of setupUi.sections.querySelectorAll(".setup-section")) {
    const show = box.dataset.cat === catId;
    box.hidden = !show;
    if (show) box.open = true;
  }
}

function buildSetupForm() {
  const nav = $("setup-nav");
  if (nav) {
    nav.innerHTML = "";
    for (const cat of SETUP_CATEGORIES) {
      const btn = Object.assign(document.createElement("button"), {
        type: "button", className: "setup-nav-btn" + (cat.id === activeSetupCat ? " active" : ""),
        textContent: cat.label,
      });
      btn.dataset.cat = cat.id;
      btn.onclick = () => selectSetupCategory(cat.id);
      nav.append(btn);
    }
  }
  for (const section of SETUP_SECTIONS) {
    const catId = categoryFor(section.title);
    const box = document.createElement("details");
    box.open = true;
    box.dataset.cat = catId;
    box.hidden = catId !== activeSetupCat;
    box.className = "setup-section wide" + (catId === "modules" ? " modules-section" : "");
    const h = document.createElement("summary");
    h.className = "setup-section-title";
    h.textContent = section.title;
    const hint = document.createElement("p");
    hint.className = "section-hint";
    hint.textContent = section.hint;
    const grid = document.createElement("div");
    const isModules = section.fields.some(f => f.module);
    grid.className = isModules ? "module-cards" : (section.wide && section.fields.some(f => f.kind === "spread") ? "spread-list" : "setup-fields");
    // Fields with a `group` go into a collapsible block of that name inside the section.
    const groups = new Map();
    const gridFor = (f) => {
      if (!f.group) return grid;
      if (!groups.has(f.group)) {
        const details = Object.assign(document.createElement("details"), {
          className: "setup-group",
          open: f.group.includes("asset shares") && f.group.includes("layer 1"),
        });
        details.append(Object.assign(document.createElement("summary"), { textContent: f.group }));
        const inner = Object.assign(document.createElement("div"), { className: f.kind === "spread" ? "spread-list" : "setup-fields" });
        details.append(inner);
        grid.append(details);
        groups.set(f.group, inner);
      }
      return groups.get(f.group);
    };
    for (const f of section.fields) {
      f.section = section;
      if (f.kind === "spread") {
        const row = buildSpreadRow(f);
        if (f.path.startsWith("assets.")) {
          // Editing any asset's distribution unlocks full per-asset distribution (asset_owner_share = 1)
          // so the 10% owner cap doesn't silently overwrite custom distributions.
          row.addEventListener("change", () => {
            const shareEl = setupInput("asset_owner_share");
            if (shareEl && Number(shareEl.value) < 1) shareEl.value = 1;
          });
        }
        gridFor(f).append(row);
        continue;
      }
      if (f.kind === "industries") { gridFor(f).append(buildIndustryPicker(f)); continue; }
      if (f.kind === "game-types") { gridFor(f).append(buildGameTypes()); continue; }
      const label = document.createElement("label");
      if (f.full) label.classList.add("full");
      let el;
      if (f.kind === "choice") {
        el = document.createElement("select");
        for (const [value, text] of f.options) el.add(new Option(text, value));
      } else if (f.kind === "bool") {
        el = document.createElement("input");
        el.type = "checkbox";
      } else if (f.kind === "recipe") {
        el = document.createElement("input");
        el.type = "text";
        el.placeholder = "nothing (primary)";
        el.className = "recipe-input";
      } else {
        el = numberInput(f.path, { min: f.min, max: f.max, step: f.kind === "int" ? 1 : f.step, placeholder: f.placeholder });
      }
      el.name = f.path;
      if (f.module) {
        // A module card: category tag, toggle switch, title, description, and dependency note.
        label.classList.add("module-item", "module-card");
        const head = Object.assign(document.createElement("span"), { className: "module-card-head" });
        const tag = Object.assign(document.createElement("span"), {
          className: "module-tag", textContent: MODULE_TAG[f.module.key] || "Module",
        });
        head.append(tag, el);
        const text = Object.assign(document.createElement("span"), { className: "module-text" });
        text.append(Object.assign(document.createElement("b"), { textContent: f.label }),
                    Object.assign(document.createElement("small"), { textContent: f.module.about }),
                    Object.assign(document.createElement("small"), { className: "module-needs" }));
        label.append(head, text);
        gridFor(f).append(label);
        continue;
      }
      label.append(f.label, el);
      gridFor(f).append(label);
    }
    box.append(h, hint, grid);
    setupUi.sections.append(box);
  }
  for (const [id, name] of PRESETS) setupUi.preset.add(new Option(name, id));
}

// ---------- modules: quick starts ----------
// Combinations of modules for different kinds of economy.
const GAME_TYPES = [
  ["Survival: no production", "Nobody makes anything: agents trade what they start with until it runs out " +
   "(in a 1000-agent test everyone was gone by day 500). A challenge, not a working economy.",
   { commerce: true, industries: false, government: false }],
  ["Market of producers", "Industries and trade, no investing, banks or government.",
   { commerce: true, industries: true, investing: false, building: false, banking: false, government: false }],
  ["Capitalism without banks", "Industries, trade, investing and building; no banks.",
   { commerce: true, industries: true, investing: true, building: true, banking: false, government: false }],
  ["Full economy", "Everything on: banks, credit, government and central bank.",
   Object.fromEntries(window.CATALOG.modules.map(m => [m.key, true]))],
];

function buildGameTypes() {
  const box = Object.assign(document.createElement("div"), { className: "game-sizes full" });
  for (const [name, about, on] of GAME_TYPES) {
    const b = Object.assign(document.createElement("button"), { type: "button", className: "chip", textContent: name, title: about });
    b.onclick = () => {
      for (const m of window.CATALOG.modules) if (m.key in on) setupInput(m.rule).checked = on[m.key];
      updateSetup();
    };
    box.append(b);
  }
  return box;
}

// Grey out modules whose required modules are off, and say what they need.
function updateModules() {
  const on = Object.fromEntries(window.CATALOG.modules.map(m => [m.key, setupInput(m.rule).checked]));
  // Effective: a module works only when everything it needs works (needs come first in the list).
  const works = {};
  for (const m of window.CATALOG.modules) works[m.key] = on[m.key] && m.needs.every(n => works[n]);
  for (const m of window.CATALOG.modules) {
    const label = setupInput(m.rule).closest("label");
    const missing = m.needs.filter(n => !works[n]).map(n => window.CATALOG.modules.find(x => x.key === n).label);
    label.classList.toggle("disabled", missing.length > 0);
    label.querySelector(".module-needs").textContent = m.needs.length
      ? (missing.length ? `Needs ${missing.join(" and ")}: off in this game` : `Needs ${m.needs.map(n =>
          window.CATALOG.modules.find(x => x.key === n).label).join(", ")}`) : "";
  }
}

// ---------- industry picker ----------
// One checkbox per industry, grouped by layer: unticked industries are left out of the game.
// Industries deeper than the chosen layers, or whose recipe needs a missing good, are greyed out.

const industryBox = (g) => setupUi.form.elements[`industry#${g}`];

function buildIndustryPicker(f) {
  const box = Object.assign(document.createElement("div"), { className: "industry-picker full" });
  const sizes = Object.assign(document.createElement("div"), { className: "game-sizes" });
  for (const [layers, text] of GAME_SIZES) {
    const b = Object.assign(document.createElement("button"), { type: "button", className: "chip", textContent: text });
    b.onclick = () => {
      setupInput("industry_layers").value = layers;
      for (const g of GOODS) industryBox(g).checked = true;
      setupInput("#autosize").checked = true;
      updateSetup();
    };
    sizes.append(b);
  }
  box.append(Object.assign(document.createElement("p"), { className: "section-hint",
    textContent: "Untick an industry to leave it out. Anything made from it is left out too." }), sizes);
  const byLayer = {};
  for (const g of GOODS) (byLayer[catalogLayer(g)] ||= []).push(g);
  for (const [layer, goods] of Object.entries(byLayer)) {
    const details = Object.assign(document.createElement("details"), { className: "setup-group industry-layer", open: layer <= 2 });
    details.dataset.layer = layer;
    const summary = document.createElement("summary");
    summary.append(`Layer ${layer} `, Object.assign(document.createElement("span"), { className: "layer-count" }));
    const all = Object.assign(document.createElement("button"), { type: "button", className: "link-btn", textContent: "all" });
    const none = Object.assign(document.createElement("button"), { type: "button", className: "link-btn", textContent: "none" });
    all.onclick = (e) => { e.preventDefault(); goods.forEach(g => industryBox(g).checked = true); updateSetup(); };
    none.onclick = (e) => { e.preventDefault(); goods.forEach(g => industryBox(g).checked = false); updateSetup(); };
    summary.append(all, none);
    const grid = Object.assign(document.createElement("div"), { className: "industry-grid" });
    for (const g of goods) {
      const item = Object.assign(document.createElement("label"), { className: "industry-item" });
      const cb = Object.assign(document.createElement("input"), { type: "checkbox", name: `industry#${g}` });
      const need = mainNeedOf(g);
      item.append(cb, Object.assign(document.createElement("span"), { textContent: label(g) }),
                  Object.assign(document.createElement("small"), { className: "why", textContent: need || "input" }));
      grid.append(item);
    }
    details.append(summary, grid);
    box.append(details);
  }
  return box;
}

// The need a good relieves most under the catalog's effects (or null for pure inputs).
function mainNeedOf(g) {
  const effects = CATALOG_INFO[g].effects || {};
  const best = Object.entries(effects).filter(([, v]) => v > 0).sort((a, b) => b[1] - a[1])[0];
  return best ? best[0] : null;
}

function fillIndustryPicker(excluded) {
  const out = new Set(excluded || []);
  for (const g of GOODS) industryBox(g).checked = !out.has(g);
}

const readIndustryPicker = () => GOODS.filter(g => !industryBox(g).checked);

// Grey out industries that can't be in this game, and say why.
function updateIndustryPicker(values) {
  if (!values) return;
  const { active, auto } = gameIndustries(values);
  const layerOf = (g) => catalogLayer(g, values.inputs || {});
  for (const g of GOODS) {
    const item = industryBox(g).closest("label");
    const why = item.querySelector(".why");
    const deep = layerOf(g) > values.industry_layers;
    item.classList.toggle("deep", deep);
    item.classList.toggle("auto", !!auto[g]);
    item.classList.toggle("on", active.has(g));
    why.textContent = deep ? `layer ${layerOf(g)}: too deep`
      : auto[g] ? `needs ${label(auto[g]).toLowerCase()}` : (mainNeedOf(g) || "input");
  }
  for (const details of setupUi.form.querySelectorAll(".industry-layer")) {
    const goods = GOODS.filter(g => catalogLayer(g) === Number(details.dataset.layer));
    details.querySelector(".layer-count").textContent = `(${goods.filter(g => active.has(g)).length} of ${goods.length} in)`;
  }
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
    if (f.kind === "industries") { fillIndustryPicker(rules.excluded_industries); continue; }
    if (f.kind === "game-types") continue;
    if (f.path === "#autosize") { setupInput(f.path).checked = false; continue; }
    const el = setupInput(f.path);
    const value = f.path === "seed" ? seed : getPath(rules, f.path);
    if (f.kind === "bool") el.checked = value;
    else if (f.kind === "recipe") el.value = formatRecipe(value);
    else if (f.yearly && typeof value === "number") el.value = +(perYear(value) * 100).toFixed(3);   // % a year
    else el.value = value ?? "";
  }
  updateSetup();
}

// Read the form into a rules object. Throws on empty / invalid values.
function readSetup() {
  const rules = {};
  let seed = null;
  const autosize = setupInput("#autosize").checked;
  for (const f of SETUP_FIELDS) {
    let value;
    if (f.local || f.kind === "game-types") continue;
    // Auto-sized: the server sizes the starting industries for this game's layers and industries.
    if (autosize && f.path.startsWith("assets.")) continue;
    if (f.kind === "industries") value = readIndustryPicker();
    else if (f.kind === "spread") value = readSpread(f);
    else {
      const el = setupInput(f.path);
      if (f.kind === "bool") value = el.checked;
      else if (f.kind === "choice") value = el.value;
      else if (f.kind === "recipe") value = parseRecipe(el.value, f.path.split(".")[1], f.allowSelf);
      else {
        if (el.value === "") {
          if (f.optional) continue;
          throw new Error(`${f.label} can't be empty`);
        }
        value = f.yearly ? perDay(Number(el.value) / 100) : Number(el.value);   // shown % a year, kept per day
      }
    }
    if (f.path === "seed") { seed = value; continue; }
    // "a.b.c" -> rules.a.b.c
    const keys = f.path.split(".");
    let at = rules;
    for (const k of keys.slice(0, -1)) at = (at[k] ||= {});
    at[keys[keys.length - 1]] = value;
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
  updateIndustryPicker(values);
  const autosize = setupInput("#autosize").checked;
  for (const f of SETUP_FIELDS) {
    const factory = f.path === "seed" || f.local ? undefined : getPath(rulesInfo.factory, f.path);
    if (f.kind === "industries" || f.kind === "game-types") continue;
    if (f.kind === "spread") {
      if (f.path.startsWith("assets.")) {
        // While auto-sized these rows show what the server will use (read-only).
        const row = rowOf(f);
        row.classList.toggle("disabled", autosize);
        row.title = autosize ? "Sized for this game: untick “Size starting industries” to set it yourself" : "";
        for (const el of row.querySelectorAll("input, select")) el.disabled = autosize;
        if (autosize) continue;
      }
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
    if (f.kind === "recipe") {
      let now = null;
      try { now = parseRecipe(el.value, f.path.split(".")[1], f.allowSelf); } catch { /* reported in the preview */ }
      el.classList.toggle("changed", formatRecipe(now) !== formatRecipe(factory));
      continue;
    }
    const now = f.kind === "bool" ? el.checked : f.kind === "choice" ? el.value
      : f.yearly ? perDay(Number(el.value) / 100) : Number(el.value);
    const differs = f.yearly ? Math.abs(Number(el.value) - +(perYear(factory ?? 0) * 100).toFixed(3)) > 1e-9 : now !== factory;
    el.classList.toggle("changed", factory !== undefined && el.value !== "" && differs);
  }
  updateModules();   // after the loop above, which resets every label's disabled look
  if (!values) return renderPreview(null, error);
  resolvePreview(values);
}

// The preview shows the rules as the server will fill them in (industries sized for this game,
// stock of missing goods converted), asked for a moment after the last change.
let resolveTimer = null, resolveSeq = 0;
function resolvePreview(values) {
  clearTimeout(resolveTimer);
  resolveTimer = setTimeout(async () => {
    const seq = ++resolveSeq;
    try {
      const resolved = await api("/api/rules/resolve", { rules: values });
      if (seq !== resolveSeq) return;   // a newer change is on its way
      if (setupInput("#autosize").checked) {
        for (const f of SETUP_FIELDS) if (f.path.startsWith("assets.")) fillSpread(f, getPath(resolved.rules, f.path));
      }
      renderPreview({ ...values, ...Object.fromEntries(window.CATALOG.modules.map(m => [m.rule, resolved.rules[m.rule]])),
                      assets: resolved.rules.assets, inventory: resolved.rules.inventory }, null, resolved.module_notes);
    } catch (err) {
      if (seq === resolveSeq) renderPreview(null, err.message);
    }
  }, 150);
}

function setStatusSetup(message) {
  setupUi.status.textContent = message;
  setupUi.status.hidden = !message;
}

// Plain-language consequences of the rules for an average agent.
function renderPreview(r, error, moduleNotes = []) {
  setupUi.preview.innerHTML = "";
  const line = (text, cls = "") => {
    const el = document.createElement("span");
    el.textContent = text;
    if (cls) el.className = cls;
    setupUi.preview.append(el);
  };
  if (!r) return line(error || "Fill in every field to see the preview.", "short");
  const on = window.CATALOG.modules.filter(m => r[m.rule]).map(m => m.label);
  line(`Modules on: ${on.join(", ") || "none"}.`);
  for (const note of moduleNotes) line(note, "short");
  if (!r.industries_enabled) line("No industries: nothing is made, so agents live off their starting stock until it runs out.", "short");
  if (!r.commerce_enabled) line("No commerce: agents can't trade, so each lives on what it owns and makes.", "short");
  const avg = (spec) => spreadMean(spec);
  const varies = (spec) => typeof spec !== "number";

  // Industries in this game: layers from the recipes, cut at the chosen number of layers.
  const n = r.agents;
  const sharesPerAgent = (g) => avg(r.assets[g]);
  const perShare = (g) => r.asset_labor[g] * r.productivity[g];
  const layerOf = (g) => catalogLayer(g, r.inputs || {});
  const game = gameIndustries(r);
  const active = GOODS.filter(g => game.active.has(g));
  const deepest = Math.max(...GOODS.map(layerOf));
  // Relief one unit of good g gives need n (positive effects only), as in rules.py.
  const reliefFor = (g, n) => {
    const fit = r.effects?.[g]?.[n] || 0;
    return fit > 0 ? r.relief_per_unit * fit * (1 + r.layer_bonus * (layerOf(g) - 1)) : 0;
  };
  line(`Industries: ${active.length} of ${GOODS.length} exist (layers 1–${Math.min(r.industry_layers, deepest)} of the ` +
       `${deepest} the recipes use). A layer-${Math.min(r.industry_layers, deepest)} good relieves ` +
       `${(1 + r.layer_bonus * (Math.min(r.industry_layers, deepest) - 1)).toFixed(1)}× what a layer-1 good of the same fit does.`);
  const left = (r.excluded_industries || []).filter(g => layerOf(g) <= r.industry_layers);
  const autoOut = Object.entries(game.auto);
  if (left.length || autoOut.length) {
    line(`Left out: ${left.map(g => label(g).toLowerCase()).join(", ") || "none"}` +
         (autoOut.length ? `; and so also ${autoOut.map(([g, m]) => `${label(g).toLowerCase()} (needs ${label(m).toLowerCase()})`).join(", ")}` : "") + ".");
  }
  if (!r.assets) return;
  // Can the economy meet every need? Relief its industries can make at full staffing vs how fast needs grow.
  for (const need of NEEDS.filter(x => x !== "sleep")) {
    const relief = (g) => reliefFor(g, need);
    const goods = active.filter(g => relief(g) > 0).sort((a, b) => relief(b) - relief(a));
    const grows = avg(r.rates[need]) * n;
    if (!goods.length) {
      const deadly = (need === "hunger" || need === "thirst") && r.death_enabled && grows > 0;
      line(`${cap(need)}: nothing in this game relieves it (it grows ${grows.toFixed(3)}/day in total)` +
           (deadly ? ". ⚠ Agents will die of it: include an industry that relieves it." : "."), grows ? "short" : "");
      continue;
    }
    const capacity = goods.reduce((sum, g) => sum + sharesPerAgent(g) * n * perShare(g) * relief(g), 0);
    const best = goods[0];
    const head = `${cap(need)}: grows ${grows.toFixed(3)}/day in total; its ${goods.length} good${goods.length === 1 ? "" : "s"} (best: ${label(best).toLowerCase()}, ` +
                 `layer ${layerOf(best)}, ${relief(best).toFixed(3)}/unit) can relieve ${capacity.toFixed(3)}/day when fully staffed`;
    const deadly = (need === "hunger" || need === "thirst") && r.death_enabled;
    line(capacity >= grows ? `${head}.` : `${head} → short${deadly ? " (can kill)" : ""}.`, capacity >= grows ? "surplus" : "short");
  }
  if (r.expiry_enabled) {
    const quick = active.filter(g => r.shelf_life[g] > 0).sort((a, b) => r.shelf_life[a] - r.shelf_life[b]).slice(0, 4);
    if (quick.length) line(`Expiry: ${quick.map(g => `${label(g).toLowerCase()} ${r.shelf_life[g]}`).join(", ")} days keep the ` +
                           "shortest; agents only stock perishables they will use in time.");
  }
  const supply = avg(r.labor_capacity) * n;
  const jobs = active.reduce((sum, g) => sum + sharesPerAgent(g) * n * r.asset_labor[g], 0);
  const range = (vals) => { const lo = Math.min(...vals), hi = Math.max(...vals); return lo === hi ? `${lo}` : `${lo}–${hi}`; };
  line(`Labour: agents make ${supply.toFixed(2)}/day and assets can employ ${jobs.toFixed(2)}/day → ` +
       (supply >= jobs ? `${(supply - jobs).toFixed(2)}/day more work than jobs (labour will be cheap).`
                       : `${(jobs - supply).toFixed(2)}/day more jobs than workers, so assets can't all run.`),
       supply >= jobs ? "" : "short");
  line(`Labour is sold each day and never stored; owners first use their own. Over ${r.productivity_growth_steps} days ` +
       `industries need ${range(active.map(g => +(r.labor_saving[g] * 100).toFixed(0)))}% less labour per asset ` +
       `while each unit of labour makes ${range(active.map(g => +(r.productivity_growth[g] * 100).toFixed(0)))}% more.`);
  const stock = RESOURCES.map(x => avg(r.inventory[x]));
  const needPerStep = Math.max(avg(r.rates.hunger), avg(r.rates.thirst)) / r.relief_per_unit;
  const goodsStock = Math.min(...["food", "water"].map(x => avg(r.inventory[x])));
  if (goodsStock / needPerStep > 300) {
    line(`Agents start with enough of everything for ${Math.round(goodsStock / needPerStep)}+ days, ` +
         "so they won't need to trade goods for a long time. Lower the starting inventory for more trading.");
  }

  if (r.stockpiling_enabled) {
    line(`Stockpiling: when a resource's average per agent falls ${(r.scarcity_trigger * 100).toFixed(0)}% within ` +
         `${r.scarcity_window} days, agents short of it want ${r.stockpile_steps} days of their own use in reserve ` +
         `(up to 3× if it falls faster), spending at most ${(r.stockpile_budget * 100).toFixed(0)}% of their money per trade.`);
  }

  if (r.demand_pricing_enabled) {
    const clamp = (v) => Math.min(Math.max(v, r.price_floor), r.price_cap);
    const e = active.reduce((sum, x) => sum + r.price_elasticity[x], 0) / active.length;
    const w = active.reduce((sum, x) => sum + r.concentration_weight[x], 0) / active.length;
    const at = (b, s) => clamp(((b + 1) / (s + 1)) ** e);
    line(`At the average elasticity (${e.toFixed(2)}): 9 buyers for 1 seller → ×${at(9, 1).toFixed(2)}; 1 buyer for 9 ` +
         `sellers → ×${at(1, 9).toFixed(2)}; supply held by one agent → ×${clamp(1 + w).toFixed(2)}.`);
    line(`Prices close ${(r.price_adjust_speed * 100).toFixed(0)}% of the gap each day` +
         (r.unit_markup ? `, and the 5th unit in one deal costs ×${((1 + r.unit_markup) ** 4).toFixed(2)} the first.` : "."));
  }

  {
    // Starting prices as in the "Starting prices" line below.
    const units = stock.reduce((a, b) => a + b, 0);
    const startPrices = RESOURCES.map((x, i) => r.price_mode === "fixed" ? r.fixed_prices[x]
      : units ? avg(r.money) / units * (1 - stock[i] / units) : 0);
    const values = active.map(x => perShare(x) * startPrices[RESOURCES.indexOf(x)] / r.asset_return[x]);
    line(`One whole asset makes ${range(active.map(x => +perShare(x).toFixed(2)))} units/day when fully staffed and ` +
         `costs about ${usd(Math.min(...values))}–${usd(Math.max(...values))} at starting prices (before wages).`);
    const held = active.reduce((sum, x) => sum + avg(r.assets[x]), 0);
    line(`Assets: ${held.toFixed(2)} shares per agent on average. No new assets are ever made` +
         (held ? "; they only change hands between agents." : ", and with none to start nothing can be made."),
         held ? "" : "short");
  }

  // Starting wage: labour share x what one unit of labour makes at starting prices (or the fixed wage).
  const startLaborPrice = () => {
    if (r.price_mode === "fixed") return r.fixed_prices.labor;
    const units = RESOURCES.reduce((sum, x) => sum + avg(r.inventory[x]), 0);
    const price = (x) => units ? avg(r.money) / units * (1 - avg(r.inventory[x]) / units) : 0;
    return r.labor_share * GOODS.reduce((s, g) => s + r.productivity[g] * price(g), 0) / GOODS.length;
  };
  if (r.gov_min_rate || r.gov_labor_purchase) {
    line(`Government: no asset valued below a return of ${pctYear(r.gov_min_rate)}` +
         (r.gov_labor_purchase ? `; buys ${r.gov_labor_purchase} labour per day with new money ` +
          `(about ${usd(r.gov_labor_purchase * startLaborPrice())} created per day at the starting labour price).` : "."));
  }

  if (r.banking_enabled) {
    const rr = (r.government_enabled ? r.reserve_ratio : 0) + r.bank_liquidity;
    const multiplier = rr > 0 ? (1 / rr).toFixed(0) : "unlimited";
    line(game.active.has("banking")
      ? `Banking: ${r.starting_banks} bank${r.starting_banks === 1 ? "" : "s"} at the start, each needing ${usd(r.bank_min_capital)} ` +
        `of its founder's money; deposits ${pctYear(r.deposit_rate)}, loans ` +
        `${pctYear(r.deposit_rate + r.loan_spread)}. Each bank can lend up to ` +
        `${r.government_enabled && r.capital_ratio > 0 ? usd(r.bank_min_capital / r.capital_ratio) : "any amount (no central bank rule)"} on its minimum capital, and deposits can ` +
        `grow to about ${multiplier}× the cash put in (money multiplier).`
      : "Banking is on, but the banking industry isn't in this game (it needs electricity, layer 3).", game.active.has("banking") ? "" : "short");
  }

  const g = avg(r.rates.sleep), rec = avg(r.sleep_recovery);
  line(rec
    ? `Sleep: an average agent rests about ${(100 * g / (g + rec || 1)).toFixed(0)}% of the time.`
    : "Sleep: recovery is 0, so a tired agent stops forever.", rec ? "" : "short");

  if (r.price_mode === "fixed") {
    line(`Prices are fixed: ${["food", "water", "games"].map(x => `${x} ${usd(r.fixed_prices[x])}`).join(", ")}, … ` +
         "(each industry's price is in the Industry catalog).");
  } else {
    const total = stock.reduce((a, b) => a + b, 0);
    const money = avg(r.money);
    const prices = RESOURCES.map((x, i) => total ? (money / total) * (1 - stock[i] / total) : 0);
    const shown = ["water", "food", "games"].map(x => `${x} ${usd(prices[RESOURCES.indexOf(x)])}`);
    line(`Starting prices (roughly): ${shown.join(", ")}; goods nobody holds yet start dearest. ` +
         "Scarcer resources get dearer as stocks change, and a good never sells below its inputs.");
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
    const { active } = gameIndustries(rules);
    const fatal = ["hunger", "thirst"].filter(need => rules.death_enabled && spreadMean(rules.rates[need]) > 0 &&
      ![...active].some(g => (rules.effects?.[g]?.[need] || 0) > 0));
    if (fatal.length && !confirm(`Nothing in this game relieves ${fatal.join(" or ")}, so every agent will die. Start anyway?`)) return;
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
