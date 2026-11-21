"""Public spending policies: income support, resources given away, public services; each with an
audience, a monthly budget and a distribution, paid from the treasury in order."""
import threading
import unittest

import server
from simulation import World, economy
from simulation.policies import Policies, clean, water_fill
from simulation.rules import GOODS, Rules
from tests.classic import CALM

EMPTY = {g: 0 for g in GOODS}


def world(**rules):
    return World(seed=1, rules=Rules.from_dict({"assets": EMPTY, "starting_banks": 0, "investing_enabled": False,
                                                "gov_policies": [], "month_steps": 30, **rules}))


class CashTests(unittest.TestCase):
    def test_equal_income_support_splits_a_days_budget(self):
        w = world()
        a, b = (w.create_agent(needs=CALM, money=0, inventory=EMPTY) for _ in range(2))
        w.government.treasury = 1000
        w.government.policies = Policies([{"kind": "cash", "audience": "everyone", "budget": 300}])
        w.government.policies.run(w)
        self.assertAlmostEqual(a.money, 5)          # 300 a month = 10 a day, shared by 2
        self.assertAlmostEqual(b.money, 5)
        self.assertAlmostEqual(w.government.treasury, 990)

    def test_neediest_first_raises_the_poorest_to_a_common_level(self):
        self.assertEqual(water_fill([0, 10, 100], 30), [20, 10, 0])
        w = world()
        poor = w.create_agent(needs=CALM, money=0, inventory=EMPTY)
        mid = w.create_agent(needs=CALM, money=10, inventory=EMPTY)
        rich = w.create_agent(needs=CALM, money=100, inventory=EMPTY)
        w.government.treasury = 1000
        w.government.policies = Policies([{"kind": "cash", "audience": "everyone", "distribution": "neediest",
                                           "budget": 900}])
        w.government.policies.run(w)
        self.assertEqual((poor.money, mid.money, rich.money), (20, 20, 100))

    def test_low_income_audience_is_the_bottom_share_by_income(self):
        w = world()
        people = [w.create_agent(needs=CALM, money=0, inventory=EMPTY) for _ in range(10)]
        for i, a in enumerate(people):
            a.income_avg = i
        w.government.treasury = 1000
        w.government.policies = Policies([{"kind": "cash", "audience": "low_income", "share": 0.2, "budget": 600}])
        w.government.policies.run(w)
        self.assertEqual([a.money for a in people[:3]], [10, 10, 0])

    def test_policies_are_paid_in_order_while_the_treasury_lasts(self):
        w = world()
        w.create_agent(needs=CALM, money=0, inventory=EMPTY)
        w.government.treasury = 15
        w.government.policies = Policies([{"kind": "cash", "budget": 300}, {"kind": "cash", "budget": 300}])
        w.government.policies.run(w)
        first, second = w.government.policies.items
        self.assertEqual((first.funded, second.funded), (1.0, 0.5))
        self.assertAlmostEqual(w.government.treasury, 0)


class GoodsTests(unittest.TestCase):
    def test_water_is_bought_from_sellers_and_given_to_the_thirstiest(self):
        w = world(tax_production=0.1)
        seller = w.create_agent(needs=CALM, money=0, inventory={**EMPTY, "water": 500})
        thirsty = w.create_agent(needs={**CALM, "thirst": 0.9}, money=0, inventory=EMPTY)
        fine = w.create_agent(needs={**CALM, "thirst": 0.1}, money=0, inventory=EMPTY)
        prices = {**w.current_prices(), "water": 10.0}
        w.current_prices = lambda: prices
        price = 10.0
        w.government.treasury = 1e6
        w.government.policies = Policies([{"kind": "goods", "good": "water", "audience": "everyone",
                                           "distribution": "neediest", "budget": 3 * price * 30}])
        w.government.policies.run(w)
        self.assertEqual(thirsty.inventory.count("water"), 3)
        self.assertEqual(fine.inventory.count("water"), 0)
        self.assertEqual(seller.inventory.count("water"), 497)
        self.assertAlmostEqual(seller.money, 3 * price * 0.9)        # minus production tax


class ServiceTests(unittest.TestCase):
    def test_a_public_health_service_hires_idle_workers_and_relieves_the_sick(self):
        from simulation.policies import service_relief_per_labor
        w = world(tax_wage=0)
        worker = w.create_agent(needs=CALM, money=0, inventory=EMPTY)
        sick = w.create_agent(needs={**CALM, "health": 0.9}, money=0, inventory=EMPTY)
        worker.asking_wage = 10
        w.government.treasury = 1e6
        w.government.policies = Policies([{"kind": "service", "need": "health", "audience": "in_need",
                                           "distribution": "neediest", "budget": 30 * 5}])
        remaining = {worker: 1.0}
        w.government.policies.run(w, offers=[worker], remaining=remaining, stats={"gov_hired": 0})
        p = w.government.policies.items[0]
        self.assertAlmostEqual(p.hired, 0.5)                     # $5 a day at $10 a unit
        self.assertAlmostEqual(worker.money, 5)
        self.assertAlmostEqual(sick.health, 0.9 - 0.5 * service_relief_per_labor(w, "health"))


class ValidationAndServerTests(unittest.TestCase):
    def test_bad_policies_are_refused(self):
        for bad in ({"kind": "loot"}, {"kind": "goods"}, {"kind": "service", "need": "sleep"},
                    {"audience": "martians"}, {"budget": -1}, {"oops": 1}):
            with self.assertRaises(ValueError):
                clean(bad)

    def test_the_default_game_has_a_food_and_water_safety_net(self):
        w = World(seed=1, rules=Rules())
        [p] = w.government.policies.items
        self.assertEqual((p.kind, p.audience), ("cash", "cant_afford"))

    def test_players_add_change_and_close_policies_while_playing(self):
        w = World(seed=2, rules=Rules.from_dict({"agents": 5}))
        w.spawn_random_agents()
        sim = server.Simulation.__new__(server.Simulation)
        sim.lock, sim.world, sim.detail = threading.Lock(), w, None
        state = sim.change_policies({"action": "add", "policy": {"kind": "goods", "good": "water", "budget": 500}})
        new = state["government"]["policies"][-1]
        self.assertEqual((new["good"], new["budget"]), ("water", 500))
        state = sim.change_policies({"action": "update", "id": new["id"], "policy": {"kind": "service", "need": "health"}})
        changed = state["government"]["policies"][-1]
        self.assertEqual((changed["kind"], changed["need"], changed["good"]), ("service", "health", None))
        state = sim.change_policies({"action": "update", "id": new["id"], "policy": {"kind": "goods"}})
        self.assertEqual(state["government"]["policies"][-1]["good"], "food")    # a resource to start from
        state = sim.change_policies({"action": "remove", "id": new["id"]})
        self.assertEqual(len(state["government"]["policies"]), 1)
        with self.assertRaises(LookupError):
            sim.change_policies({"action": "remove", "id": 999})


class GameTests(unittest.TestCase):
    def test_a_game_with_several_policies_runs_and_spends(self):
        w = World(seed=3, rules=Rules.from_dict({"agents": 30, "gov_policies": [
            {"kind": "cash", "audience": "low_income", "budget": 2000},
            {"kind": "goods", "good": "food", "audience": "in_need", "distribution": "neediest", "budget": 2000},
            {"kind": "service", "need": "health", "audience": "everyone", "budget": 2000}]}))
        w.spawn_random_agents()
        start = w.base_money()
        for _ in range(60):
            w.step()
        self.assertGreater(sum(p.spent for p in w.government.policies.items), 0)
        if len(w.agents) == 30:
            self.assertAlmostEqual(w.base_money(), start + w.money_issued(), places=4)


if __name__ == "__main__":
    unittest.main()
