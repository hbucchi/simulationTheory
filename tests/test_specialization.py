"""Specialization (experience makes a worker up to 10x more productive in an industry, and worse
at autonomous production) and clearance sales (goods about to expire sell at a discount)."""
import math
import threading
import unittest

import server
from simulation import World, economy
from simulation.labor import LaborMarket, autonomous_factor, skill
from simulation.rules import GOODS, Rules
from tests.classic import CALM

EMPTY = {g: 0 for g in GOODS}


def world(**rules):
    return World(seed=1, rules=Rules.from_dict({"assets": EMPTY, "starting_banks": 0, "investing_enabled": False,
                                                "gov_policies": [], **rules}))


class SkillTests(unittest.TestCase):
    def test_skill_grows_with_diminishing_returns_up_to_ten_times(self):
        w = world()
        a = w.create_agent(needs=CALM, money=0, inventory=EMPTY)
        self.assertEqual(skill(a, "water", w.rules), 1.0)
        a.experience["water"] = 60                       # one learning scale
        self.assertAlmostEqual(skill(a, "water", w.rules), 1 + 9 * (1 - math.exp(-1)))
        a.experience["water"] = 1e6
        self.assertAlmostEqual(skill(a, "water", w.rules), 10.0)
        self.assertEqual(skill(a, "food", w.rules), 1.0)  # only where it worked

    def test_specialists_lose_the_knack_of_fending_for_themselves(self):
        w = world()
        a = w.create_agent(needs=CALM, money=0, inventory=EMPTY)
        self.assertEqual(autonomous_factor(a, w.rules), 1.0)
        a.experience["water"] = 1e6
        self.assertAlmostEqual(autonomous_factor(a, w.rules), 0.05)

    def test_working_builds_experience_and_employers_pick_the_skilled(self):
        w = world()
        boss = w.create_agent(needs=CALM, money=1e6, inventory=EMPTY)
        novice = w.create_agent(needs=CALM, money=0, inventory=EMPTY)
        expert = w.create_agent(needs=CALM, money=0, inventory=EMPTY)
        expert.experience["water"] = 1e6
        stats = LaborMarket._empty_stats()
        LaborMarket._hire(boss, expert, 0.5, 10.0, stats, w.government, effective=0.5 * 10, good="water")
        self.assertAlmostEqual(boss.labor_available, 5.0)                 # half a day of an expert = 5 units
        self.assertAlmostEqual(expert.experience["water"], 1e6 + 0.5)
        order = sorted([novice, expert], key=lambda x: x.asking_wage / skill(x, "water", w.rules))
        novice.asking_wage = expert.asking_wage = 10
        order = sorted([novice, expert], key=lambda x: x.asking_wage / skill(x, "water", w.rules))
        self.assertIs(order[0], expert)

    def test_off_means_no_skills(self):
        w = world(specialization_enabled=False)
        a = w.create_agent(needs=CALM, money=0, inventory=EMPTY)
        a.experience["water"] = 1e6
        self.assertEqual((skill(a, "water", w.rules), autonomous_factor(a, w.rules)), (1.0, 1.0))


class ClearanceTests(unittest.TestCase):
    def seller_with(self, w, days_left):
        s = w.create_agent(needs=CALM, money=0, inventory=EMPTY)
        s.inventory.add("food", 10, expires=w.tick + days_left)
        return s

    def test_goods_in_their_last_five_days_sell_at_80_percent_off(self):
        w = world()
        self.assertAlmostEqual(economy.clearance_discount(self.seller_with(w, 5), "food", w.rules), 0.8)
        self.assertEqual(economy.clearance_discount(self.seller_with(w, 6), "food", w.rules), 0.0)

    def test_a_gradual_schedule(self):
        w = world(clearance_schedule=[[30, 0.05], [20, 0.1], [15, 0.2], [1, 0.8]])
        for days, off in ((40, 0), (25, 0.05), (18, 0.1), (10, 0.2), (1, 0.8)):
            self.assertAlmostEqual(economy.clearance_discount(self.seller_with(w, days), "food", w.rules), off)

    def test_the_buyer_pays_the_discounted_price(self):
        w = world()
        seller = self.seller_with(w, 3)
        buyer = w.create_agent(needs={**CALM, "hunger": 0.9}, money=1e6, inventory=EMPTY)
        prices = {**w.current_prices(), "food": 100.0}
        bought, paid, *_ = economy.buy(buyer, seller, prices, w.rules)
        self.assertGreater(bought.get("food", 0), 0)
        self.assertAlmostEqual(paid["money"], bought["food"] * 20.0)

    def test_bad_schedules_are_refused_and_players_change_it_in_game(self):
        for bad in ([[5, 2]], [[-1, 0.5]], [5, 0.8], "x"):
            with self.assertRaises(ValueError):
                Rules.from_dict({"clearance_schedule": bad})
        w = World(seed=2, rules=Rules.from_dict({"agents": 5}))
        w.spawn_random_agents()
        sim = server.Simulation.__new__(server.Simulation)
        sim.lock, sim.world, sim.detail = threading.Lock(), w, None
        state = sim.set_market({"clearance_schedule": [[30, 0.05], [1, 0.8]], "clearance_enabled": True})
        self.assertEqual(state["market"]["clearance_schedule"], [[30, 0.05], [1, 0.8]])


if __name__ == "__main__":
    unittest.main()
