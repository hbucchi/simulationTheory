"""Game rules: every world-wide setting, chosen on the setup screen before a game starts.

A World owns one Rules object and keeps it for the whole game. Rules give the
defaults for new agents (each agent can still be edited individually) and the
world-wide mechanics (thresholds, prices, death, depression, meetings).

Per-agent values (marked "spread") are either a number or a distribution that
each new agent is drawn from; see distributions.py.
"""

import math
from dataclasses import asdict, dataclass, field, fields

from . import distributions
from .catalog import BY_ID, CAPITAL_GOODS, CATALOG, OWN_USE_GOODS, TECH_SERVICES, default_build_cost

GOODS = tuple(e["id"] for e in CATALOG)   # every good; each is made by its own industry (assets)
# Default split (a game's rules can change what each good does, see Rules.effects):
CONSUMABLES = tuple(e["id"] for e in CATALOG if any(f > 0 for f in e["effects"].values()))  # relieve a need
LABOR = "labor"                       # a capacity sold each step in the labour market; never held
RESOURCES = GOODS                     # what agents hold and trade face to face
PRICED = GOODS + (LABOR,)             # everything with a price (labour's price is the wage)
# Sleep is recovered by resting; every other need is relieved by consuming goods.
NEEDS = ("hunger", "sleep", "thirst", "boredom", "health", "energy", "shelter")
PRICE_MODES = ("scarcity", "fixed")
MAX_LAYERS = 10


def _catalog_layers(inputs):
    """{good: layer}: 1 for primary industries, else 1 + the deepest layer among its inputs.
    Raises ValueError on a cycle (a good that ends up being its own input)."""
    layers, visiting = {}, set()

    def layer(g):
        if g in layers:
            return layers[g]
        if g in visiting:
            raise ValueError(f"inputs form a loop through {g}")
        visiting.add(g)
        recipe = inputs.get(g, {})
        layers[g] = 1 + max((layer(i) for i in recipe), default=0)
        visiting.discard(g)
        return layers[g]

    for g in GOODS:
        layer(g)
    return layers


_DEFAULT_LAYERS = _catalog_layers({e["id"]: e["inputs"] for e in CATALOG if e["inputs"]})
RAW = tuple(g for g in GOODS if g not in CONSUMABLES)   # only used as industry inputs

# Labour per unit falls with depth: a layer-1 industry makes 4 units per unit of labour, each
# layer deeper 1 more (layer 6: 9), so deeper industries need less labour per unit on average.
# Labour-intensive exceptions set their own productivity in the catalog (housing, healthcare...).
BASE_PRODUCTIVITY = 4.0
PRODUCTIVITY_PER_LAYER = 1.0


def default_productivity(good, layer):
    override = BY_ID[good].get("productivity")
    return override if override is not None else BASE_PRODUCTIVITY + PRODUCTIVITY_PER_LAYER * (layer - 1)


def default_depreciation(good):
    """Yearly wear of an industry's plant (1-5%): buildings last longest, machines and technology
    wear out fastest."""
    if good in ("housing",):
        return 0.01
    if good in ("banking",) or good in CAPITAL_GOODS or good in TECH_SERVICES or good == "electronics":
        return 0.05 if good != "banking" else 0.02
    return 0.03 if _DEFAULT_LAYERS[good] == 1 else 0.04


def main_need(effects):
    """The need a good relieves most (its biggest positive effect), or None."""
    best = max(((f, n) for n, f in effects.items() if f > 0), default=None)
    return best[1] if best else None


@dataclass
class Rules:
    # Starting agents (spreads)
    agents: int = 3
    inventory: dict = field(default_factory=lambda: {e["id"]: e["stock"] for e in CATALOG})
    # Starting asset shares: for each good, 10% of the agents own all its assets, drawn separately
    # per good, so most agents own none and live by selling labour. The average per agent comes
    # from the catalog (bigger industries for goods many people need).
    assets: dict = field(default_factory=lambda: {e["id"]: {"dist": "tiered", "average": e["shares"], "tiers": [
        {"agents": 10, "share": 100}, {"agents": 90, "share": 0}]} for e in CATALOG})
    # Starting money per agent. With money_velocity on it only sets the scale of prices (a
    # day's wage is roughly 6% of it); what makes agents rich or poor is velocity and how
    # money is shared out (try a tiered spread).
    money: object = 3000.0
    movement: object = field(default_factory=lambda: {"dist": "uniform", "min": 5, "max": 25})
    start_needs: object = field(default_factory=lambda: {"dist": "uniform", "min": 0.0, "max": 0.5})

    # Labour (see labor.py): every agent can work up to labor_capacity units per step (spread),
    # scaled by its efficiency. Labour is never stored: it is sold each step in the labour
    # market and anything unsold is lost. Goods are only made by assets worked by labour.
    labor_capacity: object = 0.5
    # Labour market: base wage = labor_share x value one unit of labour produces; an agent's
    # general need = money_weight x (how far its money is below comfort_steps steps of cost of
    # living) + (1 - money_weight) x its most pressing need. It offers
    # participation_floor + (1 - participation_floor) x need of its free capacity and asks
    # wage x (1 + bargaining_spread x (wellbeing - need)).
    labor_share: float = 0.6
    money_weight: float = 0.5
    comfort_steps: int = 50
    participation_floor: float = 0.2
    bargaining_spread: float = 0.5
    # Labour capacity module: efficiency = 1 - sum(weight x need) - depression penalty, at least
    # min_efficiency. Wellbeing uses the same weights.
    efficiency_weights: dict = field(default_factory=lambda: {"hunger": 0.3, "thirst": 0.3, "sleep": 0.2,
                                                              "boredom": 0.1, "health": 0.2, "energy": 0.1,
                                                              "shelter": 0.1})
    depression_penalty: float = 0.3
    min_efficiency: float = 0.2

    # Consumption: how fast needs grow (spreads), and what consuming does
    rates: dict = field(default_factory=lambda: {"hunger": 0.010, "sleep": 0.005, "thirst": 0.015,
                                                 "boredom": 0.008, "health": 0.003, "energy": 0.004,
                                                 "shelter": 0.002})
    # What consuming one unit of a good does to each need: effects[good] = {need: fit}, fit in
    # [-1, 1]. A positive fit relieves the need by
    #     relief_per_unit x fit x (1 + layer_bonus x (layer - 1))
    # so goods from deeper industry layers relieve more per unit (layer 1: x1, layer 3: x2 at 0.5);
    # a negative fit worsens it by relief_per_unit x |fit| (harm isn't scaled by layer). A good can
    # do several things at once: fast food relieves hunger and boredom but harms health. Goods
    # missing here do nothing to needs (pure industry inputs). Sleep can only be harmed (it is
    # recovered by resting). Sending this replaces the whole table.
    relief_per_unit: float = 0.1
    layer_bonus: float = 0.5
    effects: dict = field(default_factory=lambda: {e["id"]: dict(e["effects"]) for e in CATALOG if e["effects"]})
    seek_threshold: float = 0.5        # above this: consume / seek a trade / rest
    target_level: float = 0.3          # ... until the need is below this
    sleep_recovery: object = 0.05      # sleep recovered per step while resting (spread)
    # Personality: the share of its companies' profits an owner takes out as dividends; the rest
    # is retained by the company (company cash) to pay wages and build new capacity in its own
    # industries. Banks retain the rest as equity, which lets them lend more. (spread)
    payout_ratio: object = field(default_factory=lambda: {"dist": "uniform", "min": 0.2, "max": 0.8})
    # Personality: risk appetite (0 = cautious, 1 = entrepreneur): how big it builds and whether it
    # borrows to invest (from 0.3 up). (spread)
    risk_appetite: object = field(default_factory=lambda: {"dist": "uniform", "min": 0.0, "max": 1.0})

    # Trading: a buyer buys a random multiple of what it needs, in [purchase_min, purchase_max]
    purchase_min: float = 1.0
    purchase_max: float = 3.0

    # Market dynamics: stockpiling when a resource is becoming scarce. A resource is
    # "becoming scarce" when its average units per living agent fell by at least
    # scarcity_trigger over the last scarcity_window steps. Agents then want a reserve
    # of stockpile_steps steps of their own net use (more the faster it falls, up to 3x),
    # buy it with money only, spending at most stockpile_budget of their money per trade,
    # and don't sell into their reserve.
    # Modules (see MODULES below): switch whole parts of the economy on or off.
    commerce_enabled: bool = True      # agents trade goods with each other
    industries_enabled: bool = True    # assets make goods with labour (and the labour market)
    stockpiling_enabled: bool = True
    scarcity_window: int = 100
    scarcity_trigger: float = 0.1
    stockpile_steps: int = 100
    stockpile_budget: float = 0.5

    # Assets and production. Each good has its own asset type; the only assets are the
    # starting ones (``assets`` above) and they only change hands between agents.
    # One whole asset employs up to asset_labor[g] units of labour per step, and each unit of
    # labour makes productivity[g] units of the good, so
    #     output = productivity x min(labour available, shares x asset_labor).
    # Every productivity_growth_steps steps productivity grows by productivity_growth[g]
    # (0.05 = 5%) and the labour an asset needs falls by labor_saving[g] (0.03 = 3%), both
    # compounding a little each step: industries get less labour-intensive over time.
    # Asset price = profit per step at full capacity (output x price of g - labour x wage) /
    # asset_return[g] (or the government's minimum rate if higher), never below 0.
    # Agents hold shares (fractions). They keep cash for their needs plus liquidity_units of
    # every resource at current prices, and once at least min_investment is spare they buy
    # shares from owners that are short of cash.
    investing_enabled: bool = True
    # Extraction (layer 1) takes half the labour per unit of the other layers: a layer-1 asset
    # employs 0.1 labour and each unit of it extracts 4 units; other assets employ 0.2 labour
    # making 2 units each. Every asset makes 0.4 units per step when fully staffed. (Seven needs
    # served by 33 industries need about twice the output per worker of the old 3-good economy.)
    asset_labor: dict = field(default_factory=lambda: {g: BY_ID[g].get("asset_labor", 0.1 if _DEFAULT_LAYERS[g] == 1 else 0.2)
                                                       for g in GOODS})
    productivity: dict = field(default_factory=lambda: {g: default_productivity(g, _DEFAULT_LAYERS[g]) for g in GOODS})
    productivity_growth: dict = field(default_factory=lambda: {g: 0.05 for g in GOODS})
    productivity_growth_steps: int = 50
    labor_saving: dict = field(default_factory=lambda: {g: 0.03 for g in GOODS})
    # Depreciation: every industry's plant wears out by depreciation[g] a year (a year is
    # 12 x month_steps steps), so asset shares shrink unless they are replaced by building.
    depreciation: dict = field(default_factory=lambda: {g: default_depreciation(g) for g in GOODS})
    asset_return: dict = field(default_factory=lambda: {g: 0.01 for g in GOODS})

    # Industries. Every good is made by its own industry (its assets are the capital).
    #   primary (extraction):  capital + labour            -> output (no inputs)
    #   secondary:             capital + labour + inputs   -> output
    # inputs[g] = {input good: units used per unit of g made}; a good with no entry is primary.
    # Output is limited by whichever runs out first (fixed proportions, "Leontief"):
    #     output = min(productivity x labour used, input stock / units per output, ...)
    # Owners of secondary industries want input_buffer_steps steps of inputs at full capacity;
    # when their stock falls below input_reorder of that they go out and buy back up to it.
    inputs: dict = field(default_factory=lambda: {e["id"]: dict(e["inputs"]) for e in CATALOG if e["inputs"]})
    # Layers: primary industries are layer 1; an industry using layer-n goods is layer n + 1.
    # Industries deeper than industry_layers (1-10, chosen when the game starts) don't exist in
    # this game: nobody owns, holds or makes their goods.
    industry_layers: int = max(_DEFAULT_LAYERS.values())
    # Industries left out of this game by choice (a simpler game). Any industry whose recipe
    # needs a good that doesn't exist (excluded, or too deep) is left out too: see auto_excluded.
    excluded_industries: list = field(default_factory=list)
    # Building new capacity. New asset shares of industry g are built from capital goods:
    # build_cost[g] = {capital good: units per share} (machinery, construction, electronics).
    # An investor starts a project when an existing asset is worth at least build_min_q times
    # what building one costs (Tobin's q), buys the capital goods (activity "building"), and
    # turns them into new shares once it holds them all. Projects not finished within
    # project_steps are dropped (the goods bought so far stay with the agent).
    building_enabled: bool = True
    build_cost: dict = field(default_factory=lambda: {g: default_build_cost(g, _DEFAULT_LAYERS[g]) for g in GOODS})
    build_min_q: float = 1.0
    project_steps: int = 300
    # Expiry: a unit of good g is thrown away shelf_life[g] steps after it was made (0 = never).
    expiry_enabled: bool = True
    shelf_life: dict = field(default_factory=lambda: {e["id"]: e["shelf_life"] for e in CATALOG})
    input_buffer_steps: int = 20
    input_reorder: float = 0.5
    # Cost floor (scarcity prices only): a secondary good never sells below the cost of the inputs
    # it is made from, at current prices. (Labour isn't included: the wage itself is set from the
    # value labour adds, so including it would let wages and prices push each other up.)
    cost_floor: bool = True
    cost_floor_margin: float = 0.1     # floor = (inputs + labour per unit at the wage) x (1 + this)
    # An industry stops working while its owner holds this many units of what it makes, or more
    # than output_buffer_steps steps of its output (beyond its own input buffer): produce to demand
    # (0 = no limit).
    max_output_stock: int = 200
    output_buffer_steps: int = 30
    # Industries whose value added per unit of labour is below the wage stop hiring. Off by
    # default: while prices adjust, a high wage can stop cheap essentials (water) and starve agents.
    profit_check: bool = False
    # How labour is shared: "value" = employers and industries where labour creates the most value
    # (productivity x (price - inputs)) first; "even" = random employer order, and each owner
    # spreads its labour evenly over its industries.
    labor_priority: str = "even"
    liquidity_units: float = 3
    min_investment: float = 150
    # Capitalists keep cash to pay for the labour their assets need: a purchase must leave them
    # holding at least capital_cash_ratio x (value of all their assets, the new one included) in cash.
    capital_cash_ratio: float = 0.2

    # Stock band, per need: an agent keeps enough goods to cover stock_steps steps of that need's
    # own growth (e.g. 100 steps of hunger at 0.01/step = 1.0 of relief: about 7 food or 17 grain).
    # Below stock_steps x restock_below it goes out to buy back up to the cap (paid in money,
    # within stockpile_budget); goods above the cap are surplus it goes out to sell. It never
    # sells below the floor. Perishable goods are only stocked up to what it would use before
    # they expire.
    selling_enabled: bool = True
    stock_steps: int = 100
    restock_below: float = 0.5

    # Central government (see government.py): a minimum interest rate that no asset's return
    # may fall below, and units of labour bought every step with newly created money.
    # The central bank's Basel rule: a bank's equity >= capital_ratio x its loans (risk-weighted
    # assets). Off with the government.
    government_enabled: bool = True
    gov_min_rate: float = 0.0
    # Central bank rule (Taylor rule): once a month it sets the policy rate (per year) to
    # neutral real rate + inflation + 0.5 x (inflation - target) + 0.5 x output gap, the gap read
    # from unemployment (Okun's law: 2% of output per point above taylor_unemployment), within
    # 0-20% a year. Off: the policy rate stays where the player puts it (gov_min_rate).
    taylor_enabled: bool = True
    inflation_target: float = 0.02
    neutral_rate: float = 0.02
    taylor_unemployment: float = 0.05
    gov_labor_purchase: float = 0.0
    # Government bonds (bonds.py): when taxes can't pay for its policies and the benefit, the
    # government borrows, up to gov_debt_limit x a year's GDP, at the policy rate + gov_bond_spread
    # (per day; 1% a year), for gov_bond_days days.
    # Labour law: wages are paid "daily", "weekly" or "monthly" (earned every day, paid on payday,
    # salary tax withheld when paid). Can be changed during the game in the Government tab.
    pay_period: str = "daily"
    gov_bonds_enabled: bool = True
    gov_debt_limit: float = 0.6
    gov_bond_spread: float = (1.01 ** (1 / 360)) - 1
    gov_bond_days: int = 360
    gov_min_wage: float = 0.0          # lowest wage per unit of labour (a day's work); 0 = none
    # Public spending policies (see policies.py): what the treasury pays for, to whom, how shared.
    # Default: a safety net paying hungry or thirsty agents what they lack for food and water.
    gov_policies: list = field(default_factory=lambda: [dict(p) for p in _default_policies()])
    capital_ratio: float = 0.12
    # Central bank: banks keep reserve_ratio x deposits in an account at the central bank, which
    # pays reserve_rate on it; as lender of last resort it lends to solvent banks that run out of
    # cash, at the policy rate + llr_penalty (per step).
    reserve_ratio: float = 0.1
    reserve_rate: float = 0.0
    lender_of_last_resort: bool = True
    llr_penalty: float = 0.00005501       # 2% a year
    # Taxes (shares) and spending. Production tax: of the money of every sale of goods (seller
    # pays). Salary tax: of every wage. Profit tax: of company and bank profits. The treasury pays
    # public works, then an unemployment benefit of benefit_rate x the wage for labour offered and
    # not hired; with balanced_budget what is left hires more idle labour for public works.
    tax_production: float = 0.05
    tax_wage: float = 0.10
    tax_profit: float = 0.15
    benefit_rate: float = 0.4
    balanced_budget: bool = True

    # Banking (see banking.py). Banks are an industry ("banking"): its plant is built from capital
    # goods, runs on labour and electricity and makes the banking services that loans use up
    # (one unit per loan_per_service lent). A bank also needs its founder's own money: at least
    # bank_min_capital (Basel-style minimum capital) goes in as its equity before it can open.
    # Rates are per step; the deposit rate is never below the government's minimum rate.
    banking_enabled: bool = True
    starting_banks: int = 3            # agents that start with a banking plant (and open a bank)
    starting_bank_shares: float = 1.0  # banking shares each of them starts with
    bank_min_capital: float = 1000.0   # founder's own money a bank needs to open (and to lend)
    bank_liquidity: float = 0.05       # vault cash each bank keeps itself (x deposits) before lending
    deposit_rate: float = 0.00008211      # 3% a year (rates are per step = per day)
    loan_spread: float = 0.00013554       # 5% a year: loan rate = deposit rate + this
    loan_steps: int = 300              # loans are repaid over this many steps
    max_loan_to_value: float = 0.6     # debt <= this x the borrower's asset shares (+ what it builds)
    loan_per_service: float = 250.0    # money lent per unit of banking services used
    default_steps: int = 30            # unpaid steps in a row before a loan defaults
    deposit_share: float = 0.5         # share of spare cash agents deposit each step
    # Budget: every agent knows what living costs it (the cheapest goods for each need, housing
    # included) plus what its loans cost per step, and keeps budget_steps steps of that (a
    # "month") before it invests or builds with anything left over.
    budget_steps: int = 30
    # Consumer credit: an agent that can't pay for what it needs now may borrow the gap.
    consumer_credit: bool = True
    # Steps are days: a month is month_steps steps. Banks lend an agent at most loan_income_share
    # of its monthly income (income per step x month_steps) in total, for any purpose; loans for
    # building also need collateral (max_loan_to_value). Can be changed in the game.
    month_steps: int = 30
    # Starting stock of each good is at most this many months of an average agent's use of it
    # (0 = no cap): scarce goods then get dearer, which makes their industries worth building.
    max_stock_months: float = 6
    loan_income_share: float = 0.4

    # Prices
    price_mode: str = "scarcity"       # "scarcity": money/units*(1-share); "fixed": fixed_prices
    # Price level (quantity theory of money, M x V = P x Y): the scarcity formula sets relative
    # prices; all of them are then scaled so that a year of what people consume costs
    # money supply x money_velocity. With velocity 4, money changes hands 4 times a year and an
    # average agent's cash lasts about a quarter of a year. 0 = off (the plain scarcity formula,
    # where money is valued against every unit held, so agents hold years of living in cash).
    money_velocity: float = 4.0
    price_level_speed: float = 0.02    # share of the gap to the target level closed each day
    fixed_prices: dict = field(default_factory=lambda: {r: 50.0 for r in PRICED})

    # Market adjustment on top of the base price, per resource:
    #   demand pressure = ((buyers + 1) / (sellers + 1)) ** price_elasticity[r]
    #     buyers = agents that want it (need, reserve, below the stock floor);
    #     sellers = agents with some to spare.
    #   concentration  = 1 + concentration_weight[r] x C, where C is 0 when the available
    #     (sellable) supply is spread evenly over its holders and 1 when one agent holds it all.
    #   buying power  = 1 / (1 + buyer_power_weight[r] x B), where B is 0 when the money of the
    #     agents that want it is spread evenly over them and 1 when one buyer has it all: a few
    #     big buyers (monopsony) push prices down, as many sellers chase few customers.
    # Target multiplier = pressure x concentration x buying power, within [price_floor, price_cap]; the
    # multiplier moves price_adjust_speed of the way to the target each step. When buyers
    # outnumber sellers, each extra unit in the same deal costs unit_markup more (compounding).
    demand_pricing_enabled: bool = True
    price_elasticity: dict = field(default_factory=lambda: {r: 0.5 for r in PRICED})
    concentration_weight: dict = field(default_factory=lambda: {r: 1.0 for r in PRICED})
    buyer_power_weight: dict = field(default_factory=lambda: {r: 1.0 for r in PRICED})
    price_adjust_speed: float = 0.2
    # Sticky prices: 0 = perfectly flexible (default); 0.9 = posted prices close only 10% of the gap
    # to the market price each day (menu costs: why real inflation is slow). Changeable in game.
    price_stickiness: float = 0.0
    price_floor: float = 0.25
    price_cap: float = 4.0
    unit_markup: float = 0.05

    # Life
    death_enabled: bool = True         # hunger or thirst at 1.00 kills (and 180 days at health 1.00)
    # Unmet needs have consequences (penalties.py): slower walking, less labour, needs that make
    # others worse, illness that can kill.
    need_penalties_enabled: bool = True
    # How much each need counts when an agent decides what to see to first (Maslow: water and
    # food, then sleep, shelter, health, energy and boredom): urgency = level x priority.
    need_priority: dict = field(default_factory=lambda: {"thirst": 3.0, "hunger": 2.5, "sleep": 2.0, "shelter": 1.5,
                                                         "health": 1.3, "energy": 1.2, "boredom": 1.0})
    # Share of agents that start owning assets (industry shares, houses); the rest own nothing but
    # their labour (and their starting money and goods). 1 = everyone gets a draw. Only the start:
    # ownership then moves with the market.
    asset_owner_share: float = 0.1
    # Starting companies hold working capital: company cash for this many days of their full wage
    # bill at the starting wage, so owners can hire before their first sales come in. 0 = none.
    working_capital_days: int = 30
    # Agents offer all the labour they can spare once their money and the goods they hold for
    # their needs would cover fewer than labor_offer_months of living costs. At the start, agents
    # without assets hold at most start_months_cap months of them (money and goods cut in proportion).
    labor_offer_months: float = 6.0
    start_months_cap: float = 4.0
    # Housing market (housing.py): houses are whole assets; each houses one agent (its shelter
    # need is met every day); the homeless' shelter grows at homeless_shelter_rate. Homebuilders
    # (the housing industry) turn every house_units units of housing into a new house. A house is
    # worth a year's rent / rent_yield (6% a year), the rent being rent_income_share of the median
    # income x demand; never below house_min_multiple x the price of food. A tenant who can't pay for eviction_days is evicted.
    housing_enabled: bool = True
    starting_houses: float = 0.95          # houses per agent at the start
    house_units: int = 20
    house_min_multiple: float = 100.0     # minimum house price: x the price of food
    rent_income_share: float = 0.3        # rent people can pay: share of the median income
    rent_yield: float = (1.06 ** (1 / 360)) - 1
    eviction_days: int = 30
    homeless_shelter_rate: float = 0.01
    house_relief: float = 0.02             # shelter relieved per day by living in a house
    # Subsistence: an agent with no assets can use the labour nobody hired to make a little of a
    # basic good on its own (fetch water, a garden, gather wood or herbs, collect stone), at
    # these units per unit of labour (an industry worker makes about 4). See labor.py.
    subsistence_enabled: bool = True
    subsistence_rates: dict = field(default_factory=lambda: {"water": 0.4, "grain": 0.4, "wood": 0.4, "herbs": 0.4,
                                                             "stone": 0.2})
    depression_enabled: bool = True    # boredom at 1.00 depresses
    depression_factor: float = 0.5     # depressed speed and sleep recovery are multiplied by this

    # Meetings
    contact_distance: float = 12       # px between centres to count as touching
    # Buyers trade with sellers up to this far away (px) without walking to them (like shops and
    # deliveries; the map is 1024 px wide). 0 = only when they touch.
    trade_radius: float = 600
    # (Steps are days: walking apart for weeks after every deal, or ignoring the only water
    # seller nearby for two months, let agents die of thirst next to plenty of water.)
    depart_steps: int = 2              # days two traders walk apart
    cooldown_steps: int = 7            # days a pair ignores each other after a deal
    retry_steps: int = 2               # ... and after a meeting where nothing could be traded

    # ---- derived tables (layers, relief per unit, which goods relieve which need) ----
    # Cached; assigning any field clears the cache. Change dicts by assigning a new dict.

    def __post_init__(self):
        object.__setattr__(self, "_cache", None)

    def __setattr__(self, name, value):
        object.__setattr__(self, name, value)
        if name != "_cache":
            object.__setattr__(self, "_cache", None)

    def _derived(self):
        cache = getattr(self, "_cache", None)
        if cache is None:
            layers = _catalog_layers(self.inputs)
            excluded = set(self.excluded_industries)
            exists = set()
            # Shallow layers first, so an industry's inputs are already decided.
            for g in sorted(GOODS, key=lambda g: layers[g]):
                if (layers[g] <= self.industry_layers and g not in excluded
                        and all(item in exists for item in self.inputs.get(g, {}))):
                    exists.add(g)
            active = tuple(g for g in GOODS if g in exists)
            effect, need_of, goods_for = {}, {}, {}
            for g in active:
                signed = {}
                # With the housing market on, houses (housing.py) meet shelter: the housing good is
                # only what homebuilders make houses from, not something people consume.
                effects = {} if (g == "housing" and self.housing_enabled) else self.effects.get(g, {})
                for need, fit in effects.items():
                    if fit > 0:
                        signed[need] = self.relief_per_unit * fit * (1 + self.layer_bonus * (layers[g] - 1))
                        goods_for.setdefault(need, []).append(g)
                    elif fit < 0:
                        signed[need] = self.relief_per_unit * fit
                if signed:
                    effect[g] = signed
                main = main_need(effects)
                if main:
                    need_of[g] = main
            for need, goods in goods_for.items():
                goods.sort(key=lambda g: effect[g][need], reverse=True)   # most effective first
            cache = {"layers": layers, "active": active, "active_set": frozenset(active),
                     "effect": effect, "need_of": need_of, "goods_for": goods_for}
            object.__setattr__(self, "_cache", cache)
        return cache

    def layer(self, good):
        return self._derived()["layers"][good]

    @property
    def active_goods(self):
        """Goods whose industry exists in this game: layer <= industry_layers, not excluded, and
        every input of its recipe exists too."""
        return (self._cache or self._derived())["active"]

    @property
    def auto_excluded(self):
        """Industries within the game's layers, not excluded by choice, that are still left out
        because their recipe needs a good that doesn't exist in this game."""
        cache = self._cache or self._derived()
        if "auto_excluded" not in cache:
            chosen = set(self.excluded_industries)
            cache["auto_excluded"] = tuple(g for g in GOODS if cache["layers"][g] <= self.industry_layers
                                           and g not in chosen and g not in cache["active_set"])
        return cache["auto_excluded"]

    def is_active(self, good):
        return good in (self._cache or self._derived())["active_set"]

    def relief(self, good, need=None):
        """How much one unit of ``good`` lowers ``need`` (default: its main need); negative when it
        makes the need worse, 0 when it doesn't touch it."""
        cache = self._cache or self._derived()
        need = need or cache["need_of"].get(good)
        return cache["effect"].get(good, {}).get(need, 0.0)

    def effects_of(self, good):
        """{need: change per unit}: positive relieves, negative worsens (active goods only)."""
        return (self._cache or self._derived())["effect"].get(good, {})

    def need_of(self, good):
        """The need ``good`` relieves most (its main need), or None."""
        return (self._cache or self._derived())["need_of"].get(good)

    def goods_for(self, need):
        """Active goods that relieve ``need`` (as a main need or a side benefit), most effective first."""
        return (self._cache or self._derived())["goods_for"].get(need, [])

    def main_goods_for(self, need):
        """Active goods whose main need is ``need``."""
        cache = self._cache or self._derived()
        if "main_goods" not in cache:
            main = {}
            for g in cache["active"]:
                if g in cache["need_of"]:
                    main.setdefault(cache["need_of"][g], []).append(g)
            cache["main_goods"] = main
        return cache["main_goods"].get(need, ())

    @property
    def consumer_needs(self):
        """Needs some good in this game can relieve."""
        cache = self._cache or self._derived()
        if "consumer_needs" not in cache:
            cache["consumer_needs"] = tuple(n for n in NEEDS if cache["goods_for"].get(n))
        return cache["consumer_needs"]

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data):
        """Build Rules from (possibly partial) JSON, validating every value.

        Missing keys keep their default. Raises ValueError with a readable message.
        """
        if not isinstance(data, dict):
            raise ValueError("rules must be an object")
        known = {f.name for f in fields(cls)}
        unknown = set(data) - known
        if unknown:
            raise ValueError(f"unknown rule(s): {', '.join(sorted(unknown))}")
        rules = cls()
        for key, value in data.items():
            if key in SPREADS:
                names, low, high, whole, tiered = SPREADS[key]
                if names is None:
                    setattr(rules, key, distributions.normalize(value, key, low, high, whole, tiered))
                    continue
                if not isinstance(value, dict) or set(value) - set(names):
                    raise ValueError(f"{key} must map {', '.join(names)} to values")
                setattr(rules, key, {**getattr(rules, key), **{
                    n: distributions.normalize(v, f"{key}.{n}", low, high, whole, tiered) for n, v in value.items()}})
                continue
            low, high, kind = LIMITS[key]
            if kind == "recipes":
                setattr(rules, key, _recipes(value))
            elif kind == "build_cost":
                setattr(rules, key, {**rules.build_cost, **_build_costs(value)})
            elif kind == "effects":
                setattr(rules, key, _effects(value))
            elif kind == "map":
                names, low, high, whole = low
                setattr(rules, key, {**getattr(rules, key), **_number_map(value, key, names, low, high, whole)})
            elif kind == "goods":
                if not isinstance(value, list) or any(g not in GOODS for g in value):
                    raise ValueError(f"{key} must be a list of industries ({', '.join(GOODS)})")
                setattr(rules, key, sorted(set(value), key=GOODS.index))
            elif kind == "policies":
                from .policies import clean
                if not isinstance(value, list) or len(value) > 50:
                    raise ValueError(f"{key} must be a list of at most 50 policies")
                setattr(rules, key, [clean(p) for p in value])
            elif kind == "bool":
                if not isinstance(value, bool):
                    raise ValueError(f"{key} must be true or false")
                setattr(rules, key, value)
            elif kind == "choice":
                if value not in low:
                    raise ValueError(f"{key} must be one of {', '.join(low)}")
                setattr(rules, key, value)
            else:
                setattr(rules, key, _number(value, key, low, high, whole=kind == "int"))
        # Starting stock of goods that don't exist in this game (fewer layers, or left out)
        # becomes the same relief in the most effective good that does exist for that need.
        stock = dict(rules.inventory)
        for g, spec in rules.inventory.items():
            need = main_need(BY_ID[g]["effects"])
            if rules.is_active(g) or not need or not isinstance(spec, (int, float)) or not spec:
                continue
            best = next(iter(rules.goods_for(need)), None)
            if best and isinstance(stock.get(best), (int, float)):
                fit = BY_ID[g]["effects"][need]
                default_relief = rules.relief_per_unit * fit * (1 + rules.layer_bonus * (_DEFAULT_LAYERS[g] - 1))
                stock[best] += round(spec * default_relief / rules.relief(best, need))
            stock[g] = 0
        rules.inventory = stock
        if rules.max_stock_months > 0:
            # Nobody starts with more than max_stock_months of what an average agent uses of each
            # good (needs + industry inputs), so stocks run down and production matters early.
            use = daily_use(rules)
            days = rules.max_stock_months * rules.month_steps
            rules.inventory = {g: (min(spec, math.ceil(use.get(g, 0.0) * days))
                                   if isinstance(spec, (int, float)) else spec)
                               for g, spec in rules.inventory.items()}
        if "assets" not in data:
            # No starting industries given: size them for this game (its layers, recipes, rates).
            sized = demand_sized_shares(rules)
            rules.assets = {g: {**spec, "average": sized[g]} if isinstance(spec, dict) and spec.get("dist") == "tiered"
                            else spec for g, spec in rules.assets.items()}
        layers = _catalog_layers(rules.inputs)   # raises on loops
        deepest = max(layers.values())
        if deepest > MAX_LAYERS:
            raise ValueError(f"recipes are {deepest} layers deep; at most {MAX_LAYERS} are allowed")
        if rules.target_level >= rules.seek_threshold:
            raise ValueError("target_level must be below seek_threshold")
        if rules.purchase_min > rules.purchase_max:
            raise ValueError("purchase_min can't be larger than purchase_max")
        rules.module_notes = apply_module_dependencies(rules)
        return rules


# Modules: the parts of the economy a game can switch on or off. Each is a boolean rule;
# a module only works when the modules it needs are on too (switching one off switches off
# what depends on it, and the setup screen says so).
#   key: (rule, label, needs, what it does)
MODULES = {
    "commerce": ("commerce_enabled", "Commerce", (),
                 "Agents trade goods with each other (money or barter). Off: they live on what they own and make."),
    "industries": ("industries_enabled", "Industries & labour", (),
                   "Asset shares make goods with labour, bought in the labour market. Off: no production, no jobs."),
    "selling": ("selling_enabled", "Selling surplus", ("commerce",),
                "Agents keep a stock band and go out to sell what is above it."),
    "pricing": ("demand_pricing_enabled", "Supply & demand pricing", ("commerce",),
                "Prices move with buyers vs sellers and how concentrated supply is."),
    "stockpiling": ("stockpiling_enabled", "Stockpiling", ("commerce",),
                    "Agents hoard goods that are becoming scarce."),
    "investing": ("investing_enabled", "Investing", ("industries",),
                  "Agents buy and sell asset shares with spare money."),
    "building": ("building_enabled", "Building new capacity", ("industries", "investing"),
                 "Investors and companies build new asset shares from capital goods."),
    "banking": ("banking_enabled", "Commercial banks", ("industries", "commerce"),
                "Banks take deposits and lend (banking is an industry)."),
    "consumer_credit": ("consumer_credit", "Consumer credit", ("banking",),
                        "Agents may borrow for what they need now."),
    "government": ("government_enabled", "Government & central bank", (),
                   "Policy rate, Basel capital rule for banks, buying labour with new money."),
    "expiry": ("expiry_enabled", "Expiry", (), "Goods go off after their shelf life."),
    "death": ("death_enabled", "Death", (), "Hunger or thirst at 1.00 kills (and six months too ill to work)."),
    "penalties": ("need_penalties_enabled", "Unmet needs hurt", (),
                  "Thirst slows walking; hunger, tiredness, illness and cold cut labour; no shelter makes illness worse."),
    "housing": ("housing_enabled", "Housing market", ("commerce",),
                "Houses are whole assets: owned, rented or empty; homebuilders add houses; the homeless suffer."),
    "subsistence": ("subsistence_enabled", "Subsistence", (),
                    "Agents with no assets make a little water, grain, wood, herbs or stone with the labour nobody hired."),
    "depression": ("depression_enabled", "Depression", (), "Boredom at 1.00 depresses (slower, less efficient)."),
}


def apply_module_dependencies(rules):
    """Switch off modules whose required modules are off. Returns notes saying what was switched
    off and why (for the setup screen)."""
    notes = []
    changed = True
    while changed:
        changed = False
        for key, (rule, label, needs, _) in MODULES.items():
            if not getattr(rules, rule):
                continue
            missing = [MODULES[n][1] for n in needs if not getattr(rules, MODULES[n][0])]
            if missing:
                setattr(rules, rule, False)
                notes.append(f"{label} is off because it needs {' and '.join(missing)}.")
                changed = True
    return notes


# Per-agent values ("spreads"): key -> (sub-keys or None, low, high, whole number, tiered allowed).
# Only amounts that can be shared out between agents (inventory, money) may be tiered.
SPREADS = {
    "inventory": (GOODS, 0, 1e9, True, True),
    "assets": (GOODS, 0, 1e9, False, True),   # shares of assets: fractions allowed
    "money": (None, 0, 1e12, False, True),
    "movement": (None, 1, 200, True, False),
    "start_needs": (None, 0, 1, False, False),
    "labor_capacity": (None, 0, 1e6, False, False),
    "rates": (NEEDS, 0, 1, False, False),
    "sleep_recovery": (None, 0, 1, False, False),
    "payout_ratio": (None, 0, 1, False, False),
    "risk_appetite": (None, 0, 1, False, False),
}


# Other rules: key -> (low, high, kind). For "map": ((names, low, high, whole), None, "map").
LIMITS = {
    "agents": (1, 5000, "int"),
    "relief_per_unit": (0.001, 1, "float"),
    "seek_threshold": (0, 1, "float"),
    "target_level": (0, 1, "float"),
    "stockpiling_enabled": (None, None, "bool"),
    "scarcity_window": (10, 500, "int"),
    "scarcity_trigger": (0.01, 0.9, "float"),
    "stockpile_steps": (0, 5000, "int"),
    "stockpile_budget": (0, 1, "float"),
    "demand_pricing_enabled": (None, None, "bool"),
    "price_elasticity": ((PRICED, 0, 3, False), None, "map"),
    "concentration_weight": ((PRICED, 0, 10, False), None, "map"),
    "buyer_power_weight": ((PRICED, 0, 10, False), None, "map"),
    "money_velocity": (0, 1000, "float"),
    "price_level_speed": (0.001, 1, "float"),
    "price_adjust_speed": (0.01, 1, "float"),
    "price_stickiness": (0, 0.99, "float"),
    "price_floor": (0.01, 1, "float"),
    "price_cap": (1, 100, "float"),
    "unit_markup": (0, 1, "float"),
    "investing_enabled": (None, None, "bool"),
    "asset_labor": ((GOODS, 0, 1e6, False), None, "map"),
    "productivity": ((GOODS, 0, 1e6, False), None, "map"),
    "asset_return": ((GOODS, 0.0001, 10, False), None, "map"),
    "productivity_growth": ((GOODS, -0.99, 100, False), None, "map"),
    "depreciation": ((GOODS, 0, 1, False), None, "map"),
    "labor_saving": ((GOODS, -1, 0.99, False), None, "map"),
    "labor_share": (0, 1, "float"),
    "money_weight": (0, 1, "float"),
    "comfort_steps": (0, 100000, "int"),
    "participation_floor": (0, 1, "float"),
    "bargaining_spread": (0, 2, "float"),
    "efficiency_weights": ((NEEDS, 0, 5, False), None, "map"),
    "depression_penalty": (0, 1, "float"),
    "min_efficiency": (0, 1, "float"),
    "productivity_growth_steps": (1, 100000, "int"),
    "min_investment": (0.01, 1e9, "float"),
    "liquidity_units": (0, 1e6, "float"),
    "capital_cash_ratio": (0, 100, "float"),
    "selling_enabled": (None, None, "bool"),
    "stock_steps": (1, 1e6, "int"),
    "restock_below": (0, 1, "float"),
    "inputs": (None, None, "recipes"),
    "input_buffer_steps": (1, 10000, "int"),
    "industry_layers": (1, MAX_LAYERS, "int"),
    "banking_enabled": (None, None, "bool"),
    "starting_banks": (0, 1000, "int"),
    "starting_bank_shares": (0.05, 1000, "float"),
    "bank_min_capital": (0, 1e12, "float"),
    "capital_ratio": (0, 1, "float"),
    "government_enabled": (None, None, "bool"),
    "bank_liquidity": (0, 1, "float"),
    "reserve_rate": (0, 1, "float"),
    "lender_of_last_resort": (None, None, "bool"),
    "llr_penalty": (0, 1, "float"),
    "tax_production": (0, 1, "float"),
    "tax_wage": (0, 1, "float"),
    "tax_profit": (0, 1, "float"),
    "benefit_rate": (0, 10, "float"),
    "balanced_budget": (None, None, "bool"),
    "commerce_enabled": (None, None, "bool"),
    "industries_enabled": (None, None, "bool"),
    "reserve_ratio": (0, 1, "float"),
    "deposit_rate": (0, 1, "float"),
    "loan_spread": (0, 1, "float"),
    "loan_steps": (1, 100000, "int"),
    "max_loan_to_value": (0, 10, "float"),
    "loan_per_service": (0.01, 1e9, "float"),
    "default_steps": (1, 100000, "int"),
    "deposit_share": (0, 1, "float"),
    "budget_steps": (0, 100000, "int"),
    "consumer_credit": (None, None, "bool"),
    "month_steps": (1, 100000, "int"),
    "max_stock_months": (0, 1200, "float"),
    "loan_income_share": (0, 100, "float"),
    "excluded_industries": (None, None, "goods"),
    "building_enabled": (None, None, "bool"),
    "build_cost": (None, None, "build_cost"),
    "build_min_q": (0, 100, "float"),
    "project_steps": (1, 100000, "int"),
    "layer_bonus": (0, 10, "float"),
    "effects": (None, None, "effects"),
    "expiry_enabled": (None, None, "bool"),
    "shelf_life": ((GOODS, 0, 1e6, True), None, "map"),
    "input_reorder": (0, 1, "float"),
    "cost_floor": (None, None, "bool"),
    "max_output_stock": (0, 1e9, "int"),
    "output_buffer_steps": (0, 100000, "int"),
    "profit_check": (None, None, "bool"),
    "labor_priority": (("value", "even"), None, "choice"),
    "gov_min_rate": (0, 10, "float"),
    "taylor_enabled": (None, None, "bool"),
    "inflation_target": (-0.5, 1, "float"),
    "neutral_rate": (-0.5, 1, "float"),
    "taylor_unemployment": (0, 1, "float"),
    "gov_labor_purchase": (0, 1e6, "float"),
    "gov_bonds_enabled": (None, None, "bool"),
    "pay_period": (("daily", "weekly", "monthly"), None, "choice"),
    "gov_debt_limit": (0, 10, "float"),
    "gov_bond_spread": (0, 0.01, "float"),
    "gov_bond_days": (1, 3600, "int"),
    "gov_min_wage": (0, 1e9, "float"),
    "gov_policies": (None, None, "policies"),
    "cost_floor_margin": (0, 10, "float"),
    "purchase_min": (1, 10, "float"),
    "purchase_max": (1, 10, "float"),
    "price_mode": (PRICE_MODES, None, "choice"),
    "fixed_prices": ((PRICED, 0, 1e9, False), None, "map"),
    "death_enabled": (None, None, "bool"),
    "need_penalties_enabled": (None, None, "bool"),
    "need_priority": ((NEEDS, 0.1, 10, False), None, "map"),
    "subsistence_enabled": (None, None, "bool"),
    "asset_owner_share": (0.001, 1, "float"),
    "working_capital_days": (0, 3600, "int"),
    "labor_offer_months": (0, 1000, "float"),
    "start_months_cap": (0, 1000, "float"),
    "housing_enabled": (None, None, "bool"),
    "starting_houses": (0, 5, "float"),
    "house_units": (1, 10000, "int"),
    "house_min_multiple": (0, 1e6, "float"),
    "rent_income_share": (0, 1, "float"),
    "rent_yield": (0, 0.01, "float"),
    "eviction_days": (1, 3600, "int"),
    "homeless_shelter_rate": (0, 1, "float"),
    "house_relief": (0, 1, "float"),
    "subsistence_rates": ((GOODS, 0, 10, False), None, "map"),
    "depression_enabled": (None, None, "bool"),
    "depression_factor": (0, 1, "float"),
    "contact_distance": (1, 200, "float"),
    "trade_radius": (0, 5000, "float"),
    "depart_steps": (0, 1000, "int"),
    "cooldown_steps": (0, 10000, "int"),
    "retry_steps": (0, 10000, "int"),
}


def _number(value, name, low, high, whole=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number")
    if not low <= value <= high:
        raise ValueError(f"{name} must be between {low:g} and {high:g}")
    if whole:
        if value != int(value):
            raise ValueError(f"{name} must be a whole number")
        return int(value)
    return float(value)


def _recipes(value):
    """Validate {good: {input good: units per unit of output}}. Replaces the whole table, so
    sending {} makes every industry primary. A good can't be its own input."""
    if not isinstance(value, dict) or set(value) - set(GOODS):
        raise ValueError(f"inputs must map goods ({', '.join(GOODS)}) to their inputs")
    recipes = {}
    for good, recipe in value.items():
        if isinstance(recipe, dict) and good in recipe:
            raise ValueError(f"inputs.{good}: {good} can't be an input of itself")
        allowed = [g for g in GOODS if g != good]
        parsed = {k: v for k, v in _number_map(recipe, f"inputs.{good}", allowed, 0, 1e6, False).items() if v > 0}
        if parsed:
            recipes[good] = parsed
    return recipes


# Default industries get this many times the capacity an average agent's needs take.
SIZING_HEADROOM = 2.0
MIN_DEFAULT_SHARES = 0.02
CAPITAL_DEFAULT_SHARES = 0.1
# Inputs that also relieve a need get this many times the capacity their industries' use takes.
INPUT_LEAKAGE = 2.0   # capital industries: no consumers, but new capacity is built from them


def _default_policies():
    from .policies import DEFAULTS
    return DEFAULTS


def daily_use(rules, leak=1.0):
    """Units per agent per day of each good in this game: what needs call for (each need split
    over its goods by the catalog's plan) plus the inputs those goods take, down the layers.
    ``leak``: extra weight on inputs people can also consume (see INPUT_LEAKAGE)."""
    active = rules.active_goods
    units = {g: 0.0 for g in active}
    for need in rules.consumer_needs:
        goods = rules.goods_for(need)
        plan = {g: BY_ID[g]["plan"] for g in goods if BY_ID[g]["plan"] > 0 and rules.need_of(g) == need}
        if not plan:
            plan = {g: 1.0 for g in goods}
        total = sum(plan.values())
        rate = distributions.mean(rules.rates[need])
        for g, p in plan.items():
            units[g] += rate * p / total / rules.relief(g, need)
    for g in sorted(active, key=rules.layer, reverse=True):   # deepest first: inputs flow down
        for item, per_unit in rules.inputs.get(g, {}).items():
            if item in units:
                units[item] += units[g] * per_unit * (leak if rules.need_of(item) else 1.0)
    return units


def demand_sized_shares(rules):
    """Asset shares per agent for each industry in this game, sized to what agents consume.

    Each need's growth (average of its spread) is split over the goods that exist in this game
    by the catalog's plan (renormalised); a need whose planned goods are all missing (e.g. a game
    with fewer layers) is split evenly over the goods that can still relieve it. The inputs those
    goods take are added down the layers, and every industry gets SIZING_HEADROOM times the
    capacity that takes (at least MIN_DEFAULT_SHARES). Inactive industries get 0."""
    # An input people can also consume (grain, livestock, water) gets eaten directly too, which
    # would starve the industries made from it: it gets INPUT_LEAKAGE x the capacity they use.
    units = daily_use(rules, INPUT_LEAKAGE)
    shares = {}
    for g in GOODS:
        per_share = rules.asset_labor[g] * rules.productivity[g]
        if g not in units or per_share <= 0 or g in OWN_USE_GOODS:
            shares[g] = 0.0   # (banks come from starting_banks instead)
        else:
            least = CAPITAL_DEFAULT_SHARES if g in CAPITAL_GOODS else MIN_DEFAULT_SHARES
            shares[g] = round(max(least, units[g] * SIZING_HEADROOM / per_share), 2)
    return shares


def _build_costs(value):
    """Validate {good: {capital good: units per share}}. Goods sent replace their own cost."""
    if not isinstance(value, dict) or set(value) - set(GOODS):
        raise ValueError("build_cost must map goods to {capital good: units per share}")
    return {good: {k: v for k, v in _number_map(cost, f"build_cost.{good}", GOODS, 0, 1e6, False).items() if v > 0}
            for good, cost in value.items()}


def _effects(value):
    """Validate {good: {need: fit}} with fit in [-1, 1]; replaces the whole table. Zero fits are
    dropped. Sleep can only be harmed (fit <= 0): it is recovered by resting."""
    if not isinstance(value, dict) or set(value) - set(GOODS):
        raise ValueError(f"effects must map goods to {{need: fit}}")
    out = {}
    for good, spec in value.items():
        if spec in (None, {}):
            continue
        if not isinstance(spec, dict) or set(spec) - set(NEEDS):
            raise ValueError(f"effects.{good} must map needs ({', '.join(NEEDS)}) to a fit between -1 and 1")
        parsed = {}
        for need, fit in spec.items():
            if fit is None or fit == "":
                continue
            fit = _number(fit, f"effects.{good}.{need}", -1, 1)
            if need == "sleep" and fit > 0:
                raise ValueError(f"effects.{good}.sleep can only be negative: sleep is recovered by resting")
            if fit:
                parsed[need] = fit
        if parsed:
            out[good] = parsed
    return out


def is_primary(good, rules):
    return not rules.inputs.get(good)


def _number_map(values, name, names, low, high, whole):
    if not isinstance(values, dict) or set(values) - set(names):
        raise ValueError(f"{name} must map {', '.join(names)} to numbers")
    return {k: _number(v, f"{name}.{k}", low, high, whole) for k, v in values.items()}


DEFAULT_RULES = Rules()
