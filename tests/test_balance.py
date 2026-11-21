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



class SurvivalFirstTests(unittest.TestCase):
    """Steps are days: agents don't spend weeks walking away from deals, and they drink before
    they go after games, so nobody dies of thirst next to plenty of water."""

    def world(self, **rules):
        return World(seed=1, rules=Rules.from_dict({"assets": NO_ASSETS, "starting_banks": 0, **rules}))

    def test_meeting_timings_are_in_days(self):
        r = Rules()
        self.assertLessEqual(r.depart_steps, 3)
        self.assertLessEqual(r.cooldown_steps, 7)

    def test_thirst_beats_boredom(self):
        from simulation import economy
        w = self.world()
        a = w.create_agent(needs={**CALM, "thirst": 0.6, "boredom": 1.0}, money=0)
        self.assertGreater(economy.urgency(a, "thirst", w.rules), economy.urgency(a, "boredom", w.rules))
        w2 = self.world(need_priority={"thirst": 1.0, "boredom": 1.0})        # priorities are game rules
        b = w2.create_agent(needs={**CALM, "thirst": 0.6, "boredom": 1.0}, money=0)
        self.assertLess(economy.urgency(b, "thirst", w2.rules), economy.urgency(b, "boredom", w2.rules))

    def test_a_thirsty_agent_stops_walking_away_from_its_last_deal(self):
        w = self.world()
        a = w.create_agent(needs={**CALM, "thirst": 0.7}, money=0, x=100, y=100, inventory=NO_ASSETS)
        a.depart(0.0, 10)
        w.step()
        self.assertNotEqual(a.activity, "leaving")
        self.assertEqual(a.depart_steps, 0)

    def test_a_seller_stops_for_a_buyer_about_to_reach_it(self):
        w = self.world()
        seller = w.create_agent(needs={**CALM, "hunger": 0.6}, money=0, x=100, y=100, inventory={"water": 50})
        buyer = w.create_agent(needs={**CALM, "thirst": 0.7}, money=1000, x=140, y=100)
        buyer.activity, buyer.target_id = "seeking", seller.id
        from simulation.modules.navigate import Navigate
        Navigate().on_step(seller, w)
        self.assertEqual((seller.activity, seller.target_id), ("meeting", buyer.id))

    def test_no_investing_while_in_need(self):
        from simulation.modules.invest import Invest
        w = self.world(investing_enabled=True, min_investment=10)
        owner = w.create_agent(needs=CALM, money=0, assets={"water": 1})
        a = w.create_agent(needs={**CALM, "thirst": 0.8}, money=1e6)
        owner.money = -1e6           # desperate to sell
        Invest().on_step(a, w)
        self.assertNotIn("water", a.assets)

    def test_no_stockpiling_while_thirsty(self):
        from simulation import economy
        w = self.world()
        seller = w.create_agent(needs=CALM, money=0, inventory={**NO_ASSETS, "stone": 50})
        buyer = w.create_agent(needs={**CALM, "thirst": 0.7}, money=1000, inventory=NO_ASSETS)
        w.scarcity["stone"] = 1.0                  # stone is running out: worth a reserve
        prices = w.current_prices()
        bought, *_ = economy.buy(buyer, seller, prices, w.rules, w.rng, w.scarcity)
        self.assertNotIn("stone", bought)

    def test_the_safety_net_pays_for_the_water_of_people_who_cant(self):
        from simulation import economy
        w = self.world()
        poor = w.create_agent(needs={**CALM, "thirst": 0.9}, money=0, inventory=NO_ASSETS)
        fine = w.create_agent(needs=CALM, money=0, inventory=NO_ASSETS)
        w.government.treasury = 1e6
        w.government.policies.run(w)      # the default policy: food and water safety net
        need = economy.shopping_cost(poor, w.current_prices(), w.rules, economy.FATAL_NEEDS)
        self.assertAlmostEqual(poor.money, need)
        self.assertEqual(fine.money, 0)
        self.assertAlmostEqual(w.government.treasury, 1e6 - need)


if __name__ == "__main__":
    unittest.main()
