"""Shared test settings.

CALM: every need at 0 (pass as needs= or rates= to keep an agent from needing anything).
CLASSIC: the original 3-good economy, for tests of mechanics that don't depend on the industry
catalog: only food, water and games relieve needs (one unit relieves relief_per_unit, as at
layer 1), every industry is primary, nothing expires, the stock band covers 1000 steps (about
the old "100 units of each good"), and those three industries have the old productivity.
"""

from simulation.rules import GOODS, NEEDS

CALM = {n: 0 for n in NEEDS}

CLASSIC = {
    "inputs": {},
    "effects": {"food": {"hunger": 1}, "water": {"thirst": 1}, "games": {"boredom": 1}},
    "expiry_enabled": False,
    "stock_steps": 1000,
    # the old per-asset numbers for these three goods
    "asset_labor": {"food": 0.2, "water": 0.2, "games": 0.2},
    "productivity": {"food": 1.0, "water": 1.0, "games": 1.0},
    # plants don't wear out (exact output in tests)
    "depreciation": {g: 0 for g in GOODS},
    # no taxes or government spending (mechanics are tested on their own)
    "tax_production": 0, "tax_wage": 0, "tax_profit": 0, "benefit_rate": 0,
    # the plain scarcity formula (no price level from velocity)
    "money_velocity": 0,
    "need_penalties_enabled": False,
    "subsistence_enabled": False,
    "housing_enabled": False,
    "trade_radius": 0,
    "luck_enabled": False,
    "wage_adjust_speed": 0,
    "specialization_enabled": False,
    "clearance_enabled": False,
    "price_mode": "scarcity",
    "distress_enabled": False,
}
