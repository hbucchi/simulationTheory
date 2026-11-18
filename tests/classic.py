"""Shared test settings.

CALM: every need at 0 (pass as needs= or rates= to keep an agent from needing anything).
CLASSIC: the original 3-good economy, for tests of mechanics that don't depend on the industry
catalog: only food, water and games relieve needs (one unit relieves relief_per_unit, as at
layer 1), every industry is primary, nothing expires, the stock band covers 1000 steps (about
the old "100 units of each good"), and those three industries have the old productivity.
"""

from simulation.rules import NEEDS

CALM = {n: 0 for n in NEEDS}

CLASSIC = {
    "inputs": {},
    "effects": {"food": {"hunger": 1}, "water": {"thirst": 1}, "games": {"boredom": 1}},
    "expiry_enabled": False,
    "stock_steps": 1000,
    # the old per-asset numbers for these three goods
    "asset_labor": {"food": 0.2, "water": 0.2, "games": 0.2},
    "productivity": {"food": 1.0, "water": 1.0, "games": 1.0},
}
