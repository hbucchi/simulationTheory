"""Lucky businesses: now and then a business strikes lucky and makes many times more for a while."""
import unittest

from simulation import World
from simulation.rules import GOODS, Rules
from tests.classic import CALM

EMPTY = {g: 0 for g in GOODS}


class LuckTests(unittest.TestCase):
    def test_a_lucky_business_makes_ten_times_more_until_its_luck_runs_out(self):
        w = World(seed=1, rules=Rules.from_dict({"assets": EMPTY, "starting_banks": 0, "investing_enabled": False,
                                                 "gov_policies": [], "selling_enabled": False,
                                                 "subsistence_enabled": False}))   # count the business's output only
        a = w.create_agent(needs=CALM, rates=CALM, money=1e6, inventory=EMPTY, assets={"water": 1}, labor_capacity=10)
        production = a.modules[2]

        def made_today():
            before = a.inventory.count("water") + production.asset_progress.get("water", 0.0)
            w.step()
            return a.inventory.count("water") + production.asset_progress.get("water", 0.0) - before

        for _ in range(3):
            w.step()                       # (settle into a normal day's work)
        plain = made_today()
        a.luck["water"] = [10.0, w.tick + 1]
        self.assertAlmostEqual(made_today(), 10 * plain, delta=plain * 0.05)

    def test_luck_strikes_about_as_often_as_set(self):
        w = World(seed=4, rules=Rules.from_dict({"agents": 200, "luck_chance_year": 0.5, "asset_owner_share": 1}))
        w.spawn_random_agents()
        businesses = sum(len([g for g in a.assets if g in w.rules.active_goods]) for a in w.agents)
        w.draw_luck()
        lucky = sum(len(a.luck) for a in w.agents)
        self.assertAlmostEqual(lucky / businesses, 0.5 / 12, delta=0.02)
        big = sum(1 for a in w.agents for m, _ in a.luck.values() if m == 100)
        self.assertLess(big, lucky)

    def test_no_luck_when_switched_off(self):
        w = World(seed=4, rules=Rules.from_dict({"agents": 50, "luck_enabled": False, "luck_chance_year": 1}))
        w.spawn_random_agents()
        w.draw_luck()
        self.assertEqual(sum(len(a.luck) for a in w.agents), 0)


if __name__ == "__main__":
    unittest.main()
