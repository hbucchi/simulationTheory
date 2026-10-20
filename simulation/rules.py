"""Game rules: every world-wide setting, chosen on the setup screen before a game starts.

A World owns one Rules object and keeps it for the whole game. Rules give the
defaults for new agents (each agent can still be edited individually) and the
world-wide mechanics (thresholds, prices, death, depression, meetings).

Per-agent values (marked "spread") are either a number or a distribution that
each new agent is drawn from; see distributions.py.
"""

from dataclasses import asdict, dataclass, field, fields

from . import distributions

RESOURCES = ("food", "water", "games")
NEEDS = ("hunger", "sleep", "thirst", "boredom")
PRICE_MODES = ("scarcity", "fixed")


@dataclass
class Rules:
    # Starting agents (spreads)
    agents: int = 3
    inventory: dict = field(default_factory=lambda: {"food": 100, "water": 100, "games": 100})
    money: object = 100.0
    movement: object = field(default_factory=lambda: {"dist": "uniform", "min": 5, "max": 25})
    start_needs: object = field(default_factory=lambda: {"dist": "uniform", "min": 0.0, "max": 0.5})

    # Production: 1 unit every N steps (0 = never) (spreads)
    production: dict = field(default_factory=lambda: {"food": 10, "water": 10, "games": 10})

    # Consumption: how fast needs grow (spreads), and what consuming does
    rates: dict = field(default_factory=lambda: {"hunger": 0.010, "sleep": 0.005, "thirst": 0.015,
                                                 "boredom": 0.008})
    relief_per_unit: float = 0.1       # consuming 1 unit lowers its need by this
    seek_threshold: float = 0.5        # above this: consume / seek a trade / rest
    target_level: float = 0.3          # ... until the need is below this
    sleep_recovery: object = 0.05      # sleep recovered per step while resting (spread)

    # Prices
    price_mode: str = "scarcity"       # "scarcity": money/units*(1-share); "fixed": fixed_prices
    fixed_prices: dict = field(default_factory=lambda: {"food": 1.0, "water": 1.0, "games": 1.0})

    # Life
    death_enabled: bool = True         # hunger or thirst at 1.00 kills
    depression_enabled: bool = True    # boredom at 1.00 depresses
    depression_factor: float = 0.5     # depressed speed and sleep recovery are multiplied by this

    # Meetings
    contact_distance: float = 12       # px between centres to count as touching
    depart_steps: int = 15             # steps two traders walk apart
    cooldown_steps: int = 60           # steps a pair ignores each other after meeting

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
            low, high, kind = LIMITS[key]
            if kind == "map":
                names, low, high, whole = low
                setattr(rules, key, {**getattr(rules, key), **_number_map(value, key, names, low, high, whole)})
            elif kind == "spreadmap":
                names, low, high, whole = low
                if not isinstance(value, dict) or set(value) - set(names):
                    raise ValueError(f"{key} must map {', '.join(names)} to values")
                setattr(rules, key, {**getattr(rules, key), **{
                    n: distributions.normalize(v, f"{key}.{n}", low, high, whole) for n, v in value.items()}})
            elif kind == "spread":
                low, whole = low
                setattr(rules, key, distributions.normalize(value, key, low, high, whole))
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
        return rules


# key -> (low, high, kind). For "map"/"spreadmap": ((names, low, high, whole), None, kind);
# for "spread": ((low, whole), high, "spread").
LIMITS = {
    "agents": (1, 500, "int"),
    "inventory": ((RESOURCES, 0, 1e9, True), None, "spreadmap"),
    "money": ((0, False), 1e12, "spread"),
    "movement": ((1, True), 200, "spread"),
    "start_needs": ((0, False), 1, "spread"),
    "production": ((RESOURCES, 0, 1e6, True), None, "spreadmap"),
    "rates": ((NEEDS, 0, 1, False), None, "spreadmap"),
    "relief_per_unit": (0.001, 1, "float"),
    "seek_threshold": (0, 1, "float"),
    "target_level": (0, 1, "float"),
    "sleep_recovery": ((0, False), 1, "spread"),
    "price_mode": (PRICE_MODES, None, "choice"),
    "fixed_prices": ((RESOURCES, 0, 1e9, False), None, "map"),
    "death_enabled": (None, None, "bool"),
    "depression_enabled": (None, None, "bool"),
    "depression_factor": (0, 1, "float"),
    "contact_distance": (1, 200, "float"),
    "depart_steps": (0, 1000, "int"),
    "cooldown_steps": (0, 10000, "int"),
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


def _number_map(values, name, names, low, high, whole):
    if not isinstance(values, dict) or set(values) - set(names):
        raise ValueError(f"{name} must map {', '.join(names)} to numbers")
    return {k: _number(v, f"{name}.{k}", low, high, whole) for k, v in values.items()}


DEFAULT_RULES = Rules()
