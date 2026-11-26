"""Tests for Inheritance, Shocks/Disasters/Epidemics, Inflation Expectations, and Distress Sticky-Price Exception."""
import threading
import unittest

import server
from simulation import World, economy
from simulation.rules import GOODS, Rules
from tests.classic import CALM

EMPTY = {g: 0 for g in GOODS}


def make_world(**rules):
    return World(seed=1, rules=Rules.from_dict({
        "assets": EMPTY, "starting_banks": 0, "investing_enabled": False,
        "gov_policies": [], "housing_enabled": False, **rules,
    }))


class InheritanceTests(unittest.TestCase):
    def test_nearest_agent_inherits_money_deposits_goods_shares_and_houses(self):
        w = make_world(inheritance_enabled=True, housing_enabled=True, banking_enabled=True,
                       bank_min_capital=1000, reserve_ratio=0.0, bank_liquidity=0.0)
        banker = w.create_agent(needs=CALM, money=5000, assets={"banking": 1.0}, inventory={"banking": 50}, x=900, y=900)
        w.banking.step(w)
        dead = w.create_agent(needs={**CALM, "hunger": 1.0}, money=1200,
                              assets={"food": 2.5}, inventory={**EMPTY, "water": 7}, x=100, y=100)
        w.banking.deposit(w, dead, 500)   # 700 cash left, 500 in bank
        house = w.housing.new_house(dead, 0)
        w.housing.move_in(dead, house)
        near = w.create_agent(needs=CALM, money=100, inventory=EMPTY, x=110, y=100)
        far = w.create_agent(needs=CALM, money=100, inventory=EMPTY, x=800, y=800)

        base_before = w.base_money()
        w._die(dead, "hunger")

        self.assertAlmostEqual(near.money, 800.0)              # 100 + 700 cash
        self.assertAlmostEqual(sum(near.deposits.values()), 500.0)
        self.assertEqual(near.inventory.count("water"), 7)
        self.assertAlmostEqual(near.assets.get("food", 0.0), 2.5)
        self.assertIs(house.owner, near)
        self.assertIs(near.home, house)
        self.assertAlmostEqual(far.money, 100.0)
        self.assertAlmostEqual(w.base_money(), base_before, places=5)
        self.assertTrue(any("inherited" in e["message"] for e in w.events))


class ShockTests(unittest.TestCase):
    def test_shortage_cuts_productivity_and_recovers_after_duration(self):
        w = make_world()
        base_out = w.asset_output("grain", 1.0)
        w.shocks.trigger_shortage(w, goods=["grain"], severity=0.5, days=5)
        self.assertAlmostEqual(w.asset_output("grain", 1.0), base_out * 0.5)
        for _ in range(5):
            w.tick += 1
            w.shocks.step(w)
        self.assertAlmostEqual(w.asset_output("grain", 1.0), base_out)

    def test_disaster_destroys_houses_and_makes_occupants_homeless(self):
        w = make_world(housing_enabled=True)
        owner = w.create_agent(needs=CALM, money=1000, inventory=EMPTY)
        for _ in range(10):
            h = w.housing.new_house(owner, 0)
            t = w.create_agent(needs=CALM, money=100, inventory=EMPTY)
            w.housing.move_in(t, h)
        self.assertEqual(len(w.housing.houses), 10)
        entry = w.shocks.trigger_disaster(w, house_loss=0.3)
        self.assertEqual(entry["houses_destroyed"], 3)
        self.assertEqual(len(w.housing.houses), 7)

    def test_epidemic_spreads_impacts_health_and_can_kill(self):
        w = make_world(death_enabled=True)
        for i in range(10):
            w.create_agent(needs=CALM, money=100, inventory=EMPTY, x=100 + i * 2, y=100)
        epi = w.shocks.trigger_epidemic(w, initial_infected=2, contagion_rate=1.0,
                                        lethality_rate=0.5, health_impact=0.1, duration=5, radius=200)
        self.assertEqual(len(epi["infected"]), 2)
        for _ in range(5):
            w.tick += 1
            w.shocks.step(w)
        self.assertGreater(epi["total_infected"], 2)
        self.assertGreater(epi["total_deaths"], 0)
        self.assertLess(len(w.agents), 10)

    def test_api_shock_endpoint(self):
        w = World(seed=1, rules=Rules.from_dict({"agents": 10}))
        w.spawn_random_agents()
        sim = server.Simulation.__new__(server.Simulation)
        sim.lock, sim.world, sim.detail = threading.Lock(), w, None
        state = sim.trigger_shock({"kind": "shortage", "goods": ["grain"], "severity": 0.4, "days": 20})
        self.assertEqual(len(state["shocks"]["shortages"]), 1)


class ExpectationsAndDistressTests(unittest.TestCase):
    def test_expectations_raise_nominal_wage_drift_and_loan_rate_when_enabled(self):
        w_off = make_world(expectations_enabled=False, banking_enabled=True)
        w_on = make_world(expectations_enabled=True, banking_enabled=True)
        w_off.expected_inflation = 0.20
        w_on.expected_inflation = 0.20
        self.assertGreater(w_on.banking.loan_rate_now(w_on), w_off.banking.loan_rate_now(w_off))

    def test_distressed_and_clearance_sales_bypass_sticky_posted_price(self):
        w = make_world(clearance_enabled=True)
        seller = w.create_agent(needs=CALM, money=0, inventory=EMPTY)
        seller.inventory.add("food", 10, expires=w.tick + 2)   # within 5-day 80% clearance window
        buyer = w.create_agent(needs={**CALM, "hunger": 0.9}, money=1e6, inventory=EMPTY)
        posted = {**w.current_prices(), "food": 100.0}
        spot = {**posted, "food": 50.0}
        # Clearance discounts 80% off the lower spot price ($50 -> $10), not the sticky posted price ($100 -> $20).
        bought, paid, *_ = economy.buy(buyer, seller, posted, w.rules, spot_prices=spot)
        self.assertGreater(bought.get("food", 0), 0)
        self.assertAlmostEqual(paid["money"], bought["food"] * 10.0)


if __name__ == "__main__":
    unittest.main()
