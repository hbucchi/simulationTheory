"""Cost prices: base = (inputs + labour + depreciation) x (1 + margin after profit tax) / (1 - production
tax), x demand (buyers who can pay vs sellers) x inventory (stock vs days of sales); sellers short of
cash discount; wages are sticky downward."""
import unittest

from simulation import World, economy
from simulation.labor import LaborMarket
from simulation.rules import GOODS, Rules
from tests.classic import CALM

EMPTY = {g: 0 for g in GOODS}


def world(**rules):
    return World(seed=1, rules=Rules.from_dict({"assets": EMPTY, "starting_banks": 0, "investing_enabled": False,
                                                "gov_policies": [], "demand_pricing_enabled": False, **rules}))


class BasePriceTests(unittest.TestCase):
    def test_base_price_is_cost_plus_margin_grossed_up_for_taxes(self):
        w = world(tax_production=0.05, tax_profit=0.15, depreciation={g: 0 for g in GOODS})
        w.labor.wage = 100.0
        prices = w.current_prices()
        labour = 100.0 / w.productivity_now["water"]
        self.assertAlmostEqual(prices["water"], labour * (1 + 0.1 / 0.85) / 0.95)
        grain = prices["grain"]
        food_cost = w.rules.inputs["food"]["grain"] * grain + 100.0 / w.productivity_now["food"]
        self.assertAlmostEqual(prices["food"], food_cost * (1 + 0.1 / 0.85) / 0.95)

    def test_depreciation_adds_the_wear_of_the_asset(self):
        w = world(tax_production=0, tax_profit=0)
        w.labor.wage = 100.0
        no_wear = World(seed=1, rules=Rules.from_dict({"assets": EMPTY, "starting_banks": 0, "tax_production": 0,
                                                       "tax_profit": 0, "demand_pricing_enabled": False,
                                                       "depreciation": {g: 0 for g in GOODS}}))
        no_wear.labor.wage = 100.0
        w._dep_prices = w.cost_prices()
        self.assertGreater(w.current_prices()["water"], no_wear.current_prices()["water"])

    def test_starts_from_a_wage_of_six_percent_of_starting_money(self):
        w = world(money=3000)
        self.assertAlmostEqual(w.labor.wage, 180.0)


class InventoryTests(unittest.TestCase):
    def test_overstock_lowers_the_price_and_shortage_raises_it_a_little_each_day(self):
        w = world()
        owner = w.create_agent(needs=CALM, money=0, assets={"water": 1}, inventory=EMPTY)
        w.update_stock_factors({"water": {owner: 10_000}})
        self.assertAlmostEqual(w.stock_factor["water"], 1 - w.rules.stock_adjust_speed)
        w.stock_factor["water"] = 1.0
        w.update_stock_factors({"water": {owner: 0.01}})      # almost nothing left to sell
        self.assertAlmostEqual(w.stock_factor["water"], 1 + w.rules.stock_adjust_speed)
        w.stock_factor["water"] = 1.0
        w.update_stock_factors({"water": {}})                 # nothing made, nothing sold: no signal
        self.assertEqual(w.stock_factor["water"], 1.0)


class CashFlowTests(unittest.TestCase):
    def test_an_owner_short_of_cash_for_wages_sells_at_a_discount(self):
        w = world()
        owner = w.create_agent(needs=CALM, money=0, assets={"water": 1}, inventory=EMPTY)
        owner.labor_need = 1.0
        w.update_distress()
        self.assertAlmostEqual(owner.distress, w.rules.distress_max)
        owner.money = 1e9
        w.update_distress()
        self.assertEqual(owner.distress, 0.0)


class StickyWageTests(unittest.TestCase):
    def test_wages_move_symmetrically_and_accelerate_when_pressure_persists(self):
        w = World(seed=3, rules=Rules.from_dict({"agents": 30}))
        self.assertEqual(w.rules.wage_adjust_speed, w.rules.wage_down_speed)
        w.spawn_random_agents()
        w.step()
        before = w.labor.wage
        w.step()
        change = w.labor.wage / before - 1
        daily_base = (1 + w.rules.wage_adjust_speed) ** (1 / w.rules.month_steps) - 1
        self.assertGreaterEqual(change, -daily_base - 1e-9)
        self.assertLessEqual(change, daily_base + 1e-9)

        # Persistent pressure in the same direction for >1 month doubles the monthly max rate (2% -> 4%).
        w2 = World(seed=3, rules=Rules.from_dict({"agents": 10, "month_steps": 30, "wage_adjust_speed": 0.02,
                                                  "wage_down_speed": 0.02, "gov_min_wage": 0}))
        w2.spawn_random_agents()
        w2.labor.wage = 100.0
        # Month 1 (day 1 of streak): max daily move <= (1.02)^(1/30) - 1
        w2.labor.wage_streak_dir, w2.labor.wage_streak_days = 1, 0
        # Force excess demand by giving an owner lots of jobs and cash
        w2.agents[0].assets = {"water": 500.0}
        w2.agents[0].money = 1e7
        w2.labor.clear(w2)
        m1_change = w2.labor.wage / 100.0 - 1
        # Simulate being in month 2 (day 31 of upward streak): rate should double (~4%/month).
        w2.labor.wage = 100.0
        w2.labor.wage_streak_dir, w2.labor.wage_streak_days = 1, 30
        w2.labor.clear(w2)
        m2_change = w2.labor.wage / 100.0 - 1
        self.assertGreater(m2_change, m1_change * 1.8)


if __name__ == "__main__":
    unittest.main()
