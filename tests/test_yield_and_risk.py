"""Bond risk premium grows with debt; investors rank industries by measured profitability and
prefer bonds when businesses earn less."""
import unittest

from simulation import World
from simulation.modules.invest import asset_yield
from simulation.rules import GOODS, Rules
from tests.classic import CALM

EMPTY = {g: 0 for g in GOODS}


class RiskPremiumTests(unittest.TestCase):
    def test_savers_demand_more_as_debt_grows(self):
        w = World(seed=1, rules=Rules.from_dict({"assets": EMPTY, "starting_banks": 0, "gov_policies": [],
                                                 "gov_debt_limit": 0.5}))
        w.government.debt.yearly_gdp = lambda world: 1_000_000
        w.create_agent(needs=CALM, money=1e7, inventory=EMPTY)
        year = w.year_steps()
        premium = lambda: (1 + w.government.debt.risk_premium(w)) ** year - 1
        self.assertEqual(premium(), 0.0)
        w.government.debt.borrow(w, 250_000)                  # half the limit
        self.assertAlmostEqual(premium(), 0.10 * 0.25, places=6)
        w.government.debt.borrow(w, 250_000)                  # at the limit
        self.assertAlmostEqual(premium(), 0.10, places=6)
        self.assertGreater(w.government.debt.rate(w), w.government.min_rate + w.government.bond_spread)


class ProfitabilityTests(unittest.TestCase):
    def test_a_busy_profitable_industry_yields_more_than_an_idle_one(self):
        w = World(seed=3, rules=Rules.from_dict({"agents": 60}))
        w.spawn_random_agents()
        for _ in range(30):
            w.step()
        yields = {g: w.industry_yield(g) for g in w.rules.active_goods}
        self.assertTrue(any(v > 0 for v in yields.values()))
        self.assertEqual(asset_yield("water", w), w.industry_yield("water") + w.productivity_growth_per_step("water"))

    def test_unused_capacity_earns_nothing(self):
        w = World(seed=1, rules=Rules.from_dict({"assets": EMPTY, "starting_banks": 0}))
        w.create_agent(needs=CALM, money=0, inventory=EMPTY, assets={"water": 1})
        w.recorder.history.append({"produced": {g: 0 for g in GOODS}})
        self.assertEqual(w.industry_yield("water"), 0.0)


if __name__ == "__main__":
    unittest.main()
