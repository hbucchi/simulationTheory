"""Game rules: every world-wide setting, chosen on the setup screen before a game starts.

A World owns one Rules object and keeps it for the whole game. Rules give the
defaults for new agents (each agent can still be edited individually) and the
world-wide mechanics (thresholds, prices, death, depression, meetings).

Per-agent values (marked "spread") are either a number or a distribution that
each new agent is drawn from; see distributions.py.
"""

from dataclasses import asdict, dataclass, field, fields

from . import distributions

CONSUMABLES = ("food", "water", "games")  # consumed for needs
RAW = ("grain", "wood")                    # raw materials: no need of their own, only industry inputs
GOODS = CONSUMABLES + RAW                  # everything an industry (asset) makes
LABOR = "labor"                       # a capacity sold each step in the labour market; never held
RESOURCES = GOODS                     # what agents hold and trade face to face
PRICED = GOODS + (LABOR,)             # everything with a price (labour's price is the wage)
NEEDS = ("hunger", "sleep", "thirst", "boredom")
PRICE_MODES = ("scarcity", "fixed")


@dataclass
class Rules:
    # Starting agents (spreads)
    agents: int = 3
    inventory: dict = field(default_factory=lambda: {"food": 100, "water": 100, "games": 100,
                                                     "grain": 20, "wood": 20})
    # Starting asset shares: for each good, 10% of the agents own all its assets (10 shares each
    # on average), drawn separately per good, so about a quarter of the agents own something.
    # Most agents own none and live by selling labour.
    assets: dict = field(default_factory=lambda: {g: {"dist": "tiered", "average": 1.0, "tiers": [
        {"agents": 10, "share": 100}, {"agents": 90, "share": 0}]} for g in GOODS})
    money: object = 22500.0           # 22,500 / 300 units x (1 - 1/3) = $50 starting price at the default stock
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
                                                              "boredom": 0.1})
    depression_penalty: float = 0.3
    min_efficiency: float = 0.2

    # Consumption: how fast needs grow (spreads), and what consuming does
    rates: dict = field(default_factory=lambda: {"hunger": 0.010, "sleep": 0.005, "thirst": 0.015,
                                                 "boredom": 0.008})
    relief_per_unit: float = 0.1       # consuming 1 unit lowers its need by this
    seek_threshold: float = 0.5        # above this: consume / seek a trade / rest
    target_level: float = 0.3          # ... until the need is below this
    sleep_recovery: object = 0.05      # sleep recovered per step while resting (spread)

    # Trading: a buyer buys a random multiple of what it needs, in [purchase_min, purchase_max]
    purchase_min: float = 1.0
    purchase_max: float = 3.0

    # Market dynamics: stockpiling when a resource is becoming scarce. A resource is
    # "becoming scarce" when its average units per living agent fell by at least
    # scarcity_trigger over the last scarcity_window steps. Agents then want a reserve
    # of stockpile_steps steps of their own net use (more the faster it falls, up to 3x),
    # buy it with money only, spending at most stockpile_budget of their money per trade,
    # and don't sell into their reserve.
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
    # Extraction of raw materials takes half the labour per unit: a raw asset employs 0.1 labour
    # and each unit of that labour extracts 2 units, so an asset still makes 0.2 units per step.
    asset_labor: dict = field(default_factory=lambda: {g: 0.1 if g in RAW else 0.2 for g in GOODS})
    productivity: dict = field(default_factory=lambda: {g: 2.0 if g in RAW else 1.0 for g in GOODS})
    productivity_growth: dict = field(default_factory=lambda: {g: 0.05 for g in GOODS})
    productivity_growth_steps: int = 50
    labor_saving: dict = field(default_factory=lambda: {g: 0.03 for g in GOODS})
    asset_return: dict = field(default_factory=lambda: {g: 0.01 for g in GOODS})

    # Industries. Every good is made by its own industry (its assets are the capital).
    #   primary (extraction):  capital + labour            -> output (no inputs)
    #   secondary:             capital + labour + inputs   -> output
    # inputs[g] = {input good: units used per unit of g made}; a good with no entry is primary.
    # Output is limited by whichever runs out first (fixed proportions, "Leontief"):
    #     output = min(productivity x labour used, input stock / units per output, ...)
    # Owners of secondary industries want input_buffer_steps steps of inputs at full capacity;
    # when their stock falls below input_reorder of that they go out and buy back up to it.
    inputs: dict = field(default_factory=lambda: {"food": {"grain": 1.0}, "games": {"wood": 1.0}})
    input_buffer_steps: int = 20
    input_reorder: float = 0.5
    # Cost floor (scarcity prices only): a secondary good never sells below its unit cost,
    # i.e. its inputs at current prices plus the labour per unit at the current wage.
    cost_floor: bool = True
    # An industry stops hiring while its owner holds this many units of what it makes (0 = never).
    max_output_stock: int = 200
    liquidity_units: float = 3
    min_investment: float = 1000
    # Capitalists keep cash to pay for the labour their assets need: a purchase must leave them
    # holding at least capital_cash_ratio x (value of all their assets, the new one included) in cash.
    capital_cash_ratio: float = 0.2

    # Stock band: agents keep between stock_cap x restock_below and stock_cap units of each
    # resource. Above the cap they go out to sell the surplus to agents that want it; below
    # the floor they go out to buy back up to the cap (paid in money, within stockpile_budget).
    # They never sell below the floor.
    selling_enabled: bool = True
    stock_cap: int = 100
    restock_below: float = 0.5

    # Central government (see government.py): a minimum interest rate that no asset's return
    # may fall below, and units of labour bought every step with newly created money.
    gov_min_rate: float = 0.0
    gov_labor_purchase: float = 0.0

    # Prices
    price_mode: str = "scarcity"       # "scarcity": money/units*(1-share); "fixed": fixed_prices
    fixed_prices: dict = field(default_factory=lambda: {r: 50.0 for r in PRICED})

    # Market adjustment on top of the base price, per resource:
    #   demand pressure = ((buyers + 1) / (sellers + 1)) ** price_elasticity[r]
    #     buyers = agents that want it (need, reserve, below the stock floor);
    #     sellers = agents with some to spare.
    #   concentration  = 1 + concentration_weight[r] x C, where C is 0 when the available
    #     (sellable) supply is spread evenly over its holders and 1 when one agent holds it all.
    # Target multiplier = pressure x concentration, kept within [price_floor, price_cap]; the
    # multiplier moves price_adjust_speed of the way to the target each step. When buyers
    # outnumber sellers, each extra unit in the same deal costs unit_markup more (compounding).
    demand_pricing_enabled: bool = True
    price_elasticity: dict = field(default_factory=lambda: {r: 0.5 for r in PRICED})
    concentration_weight: dict = field(default_factory=lambda: {r: 1.0 for r in PRICED})
    price_adjust_speed: float = 0.2
    price_floor: float = 0.25
    price_cap: float = 4.0
    unit_markup: float = 0.05

    # Life
    death_enabled: bool = True         # hunger or thirst at 1.00 kills
    depression_enabled: bool = True    # boredom at 1.00 depresses
    depression_factor: float = 0.5     # depressed speed and sleep recovery are multiplied by this

    # Meetings
    contact_distance: float = 12       # px between centres to count as touching
    depart_steps: int = 15             # steps two traders walk apart
    cooldown_steps: int = 60           # steps a pair ignores each other after a deal
    retry_steps: int = 10              # ... and after a meeting where nothing could be traded

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
            elif kind == "map":
                names, low, high, whole = low
                setattr(rules, key, {**getattr(rules, key), **_number_map(value, key, names, low, high, whole)})
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
        if rules.target_level >= rules.seek_threshold:
            raise ValueError("target_level must be below seek_threshold")
        if rules.purchase_min > rules.purchase_max:
            raise ValueError("purchase_min can't be larger than purchase_max")
        return rules


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
}


# Other rules: key -> (low, high, kind). For "map": ((names, low, high, whole), None, "map").
LIMITS = {
    "agents": (1, 500, "int"),
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
    "price_adjust_speed": (0.01, 1, "float"),
    "price_floor": (0.01, 1, "float"),
    "price_cap": (1, 100, "float"),
    "unit_markup": (0, 1, "float"),
    "investing_enabled": (None, None, "bool"),
    "asset_labor": ((GOODS, 0, 1e6, False), None, "map"),
    "productivity": ((GOODS, 0, 1e6, False), None, "map"),
    "asset_return": ((GOODS, 0.0001, 10, False), None, "map"),
    "productivity_growth": ((GOODS, -0.99, 100, False), None, "map"),
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
    "stock_cap": (1, 1e9, "int"),
    "restock_below": (0, 1, "float"),
    "inputs": (None, None, "recipes"),
    "input_buffer_steps": (1, 10000, "int"),
    "input_reorder": (0, 1, "float"),
    "cost_floor": (None, None, "bool"),
    "max_output_stock": (0, 1e9, "int"),
    "gov_min_rate": (0, 10, "float"),
    "gov_labor_purchase": (0, 1e6, "float"),
    "purchase_min": (1, 10, "float"),
    "purchase_max": (1, 10, "float"),
    "price_mode": (PRICE_MODES, None, "choice"),
    "fixed_prices": ((PRICED, 0, 1e9, False), None, "map"),
    "death_enabled": (None, None, "bool"),
    "depression_enabled": (None, None, "bool"),
    "depression_factor": (0, 1, "float"),
    "contact_distance": (1, 200, "float"),
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


def is_primary(good, rules):
    return not rules.inputs.get(good)


def _number_map(values, name, names, low, high, whole):
    if not isinstance(values, dict) or set(values) - set(names):
        raise ValueError(f"{name} must map {', '.join(names)} to numbers")
    return {k: _number(v, f"{name}.{k}", low, high, whole) for k, v in values.items()}


DEFAULT_RULES = Rules()
