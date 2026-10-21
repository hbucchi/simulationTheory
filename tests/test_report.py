import unittest

from simulation import World, economy
from simulation.report import build_report, gini, lorenz, top_share
from simulation.rules import Rules

CALM = {"hunger": 0, "sleep": 0, "thirst": 0, "boredom": 0}


class MeasureTests(unittest.TestCase):
    def test_gini(self):
        self.assertEqual(gini([5, 5, 5, 5]), 0)
        self.assertAlmostEqual(gini([0, 0, 0, 10]), 0.75)    # one of four holds all: (n-1)/n
        self.assertEqual(gini([]), 0)

    def test_top_share_and_lorenz(self):
        self.assertAlmostEqual(top_share([90] + [10 / 9] * 9, 0.1), 0.9)
        points = lorenz([1, 1, 2])
        self.assertEqual(points[0], [0.0, 0.0])
        self.assertEqual(points[-1], [1.0, 1.0])
        self.assertAlmostEqual(points[1][1], 0.25)               # poorest third holds a quarter


class RecorderTests(unittest.TestCase):
    def test_snapshot_counts_production_consumption_and_income(self):
        world = World(seed=1, rules=Rules.from_dict({"investing_enabled": False, "selling_enabled": False,
                                                     "assets": {"food": 0, "water": 0, "games": 0},
                                                     "asset_labor": {"food": 1}}))
        owner = world.create_agent(needs={**CALM, "hunger": 0.6}, rates=CALM, labor_rate=1, assets={"food": 1},
                                   inventory={"food": 0, "water": 50, "games": 50, "labor": 0})
        world.step()
        snap = world.recorder.history[-1]
        self.assertEqual(snap["produced"]["food"], 1)          # 1 labour x productivity 1
        self.assertEqual(snap["consumed"]["food"], 1)          # hungry: ate it straight away
        self.assertAlmostEqual(snap["labor_made"], 1)
        self.assertAlmostEqual(snap["labor_used"], 1)
        self.assertEqual(snap["population"], 1)

        buyer = world.create_agent(needs=CALM, money=50)
        economy.pay(buyer, owner, 7)
        self.assertEqual(owner.flow["income"], 7)

    def test_report_window_and_totals(self):
        world = World(seed=3, rules=Rules.from_dict({"agents": 8}))
        world.spawn_random_agents()
        for _ in range(150):
            world.step()
        report = build_report(world, 100)
        self.assertEqual(report["totals"]["steps"], 100)
        self.assertEqual(report["totals"]["from_tick"], 51)
        self.assertEqual(len(report["series"]), 100)
        self.assertEqual(set(report["prices"]), set(economy.RESOURCES))
        self.assertLessEqual(len(report["top_agents"]), 5)
        self.assertEqual(len(build_report(world)["series"]), 150)
        for key in ("gini_money", "gini_assets", "gini_wealth"):
            self.assertTrue(0 <= report["current"][key] <= 1)

    def test_long_histories_are_averaged_down(self):
        world = World(seed=3, rules=Rules.from_dict({"agents": 3}))
        world.spawn_random_agents()
        for _ in range(700):
            world.step()
        self.assertLessEqual(len(build_report(world)["series"]), 300)


if __name__ == "__main__":
    unittest.main()
