"""Fixes from the 1000-agent review: minimum wage, waste-aware production and valuation,
6-month starting stocks, full-cost price floor and risk appetite."""
import unittest

from simulation import World
from simulation.rules import GOODS, Rules, daily_use
from tests.classic import CALM

NO_ASSETS = {g: 0 for g in GOODS}


class MinimumWageTests(unittest.TestCase):
    def test_nobody_works_below_the_minimum_wage(self):
        w = World(seed=1, rules=Rules.from_dict({"agents": 30, "gov_min_wage": 500}))
        w.spawn_random_agents()
        for _ in range(5):
            w.step()
        self.assertGreaterEqual(w.labor.wage, 500)
        self.assertTrue(all(a.asking_wage >= 500 for a in w.agents if a.offered > 0))

    def test_no_minimum_without_a_government(self):
        w = World(seed=1, rules=Rules.from_dict({"agents": 5, "gov_min_wage": 500, "government_enabled": False}))
        self.assertEqual(w.government.min_wage, 0)


class WasteTests(unittest.TestCase):
    def test_waste_lowers_production_and_asset_value(self):
        w = World(seed=1, rules=Rules.from_dict({"assets": NO_ASSETS, "starting_banks": 0}))
        owner = w.create_agent(needs=CALM, money=1e6, assets={"electricity": 5},
                               inventory={"coal": 500, "natural_gas": 500})
        before_jobs = w.usable_jobs(owner, "electricity")
        before_value = w.asset_prices()["electricity"]
        w.sell_through["electricity"] = 0.25            # three quarters of recent output rotted
        self.assertAlmostEqual(w.usable_jobs(owner, "electricity"), before_jobs * 0.25)
        self.assertLess(w.asset_prices()["electricity"], before_value)

    def test_perishable_output_is_held_for_at_most_half_its_shelf_life(self):
        w = World(seed=1, rules=Rules.from_dict({"assets": NO_ASSETS, "starting_banks": 0, "output_buffer_steps": 30}))
        owner = w.create_agent(needs=CALM, money=1e6, assets={"electricity": 1}, inventory={"coal": 500, "natural_gas": 500})
        made = w.asset_output("electricity", 1)
        life = w.rules.shelf_life["electricity"]                  # 20 days: at most 10 days held
        owner.inventory.add("electricity", int(made * life * 0.5) + 1)
        self.assertEqual(w.usable_jobs(owner, "electricity"), 0)


class StartingStockTests(unittest.TestCase):
    def test_starting_stock_is_at_most_six_months_of_use(self):
        r = Rules.from_dict({})
        use = daily_use(r)
        for g, units in r.inventory.items():
            if isinstance(units, (int, float)) and units:
                self.assertLessEqual(units, use[g] * 6 * 30 + 1, g)
        self.assertLess(r.inventory["games"], Rules().inventory["games"])
        self.assertEqual(Rules.from_dict({"max_stock_months": 0}).inventory["games"], Rules().inventory["games"])


class PriceFloorTests(unittest.TestCase):
    def test_every_good_covers_its_full_unit_cost(self):
        w = World(seed=2, rules=Rules.from_dict({"agents": 40}))
        w.spawn_random_agents()
        for _ in range(30):
            w.step()
        prices = w.current_prices()
        for g in w.rules.active_goods:
            self.assertGreaterEqual(prices[g] + 1e-6, w.unit_cost(g, prices) * 1.1 * 0.999, g)
        values = w.asset_prices(prices)
        self.assertGreater(values["machinery"], 0)       # capital goods are worth something now
        self.assertGreater(values["housing"], 0)


class RiskAppetiteTests(unittest.TestCase):
    def test_traits_are_drawn_and_editable(self):
        w = World(seed=3, rules=Rules.from_dict({"agents": 20}))
        w.spawn_random_agents()
        appetites = [a.personality["risk_appetite"] for a in w.agents]
        self.assertTrue(all(0 <= x <= 1 for x in appetites))
        self.assertGreater(len(set(appetites)), 5)

    def test_entrepreneurs_build_bigger_and_borrow(self):
        from simulation.modules.build import Build
        results = {}
        for appetite in (0.0, 1.0):
            w = World(seed=1, rules=Rules.from_dict({"assets": NO_ASSETS, "starting_banks": 0, "min_investment": 10,
                                                     "bank_min_capital": 100, "max_loan_to_value": 10}))
            banker = w.create_agent(needs=CALM, money=1000, assets={"banking": 1}, inventory={"banking": 10000})
            w.banking.step(w)
            w.banking.banks[0].reserves += 1e6
            w.banking._central_bank(w, w.banking.banks[0])   # meet the reserve requirement first
            agent = w.create_agent(needs=CALM, money=5000, risk_appetite=appetite, assets={"water": 1})
            w._step_cache = {"seekers": {}, "builds": [("grain", 5.0, 1000.0)]}
            original = Build.__dict__["available"]
            Build.available = staticmethod(lambda good, world, a: True)
            try:
                Build().plan(agent, w)
            finally:
                Build.available = original
            results[appetite] = agent.project
        self.assertIsNotNone(results[1.0])
        self.assertEqual(results[0.0]["borrowed"], 0)
        self.assertGreater(results[1.0]["borrowed"], 0)
        self.assertGreater(results[1.0]["shares"], results[0.0]["shares"])


if __name__ == "__main__":
    unittest.main()
