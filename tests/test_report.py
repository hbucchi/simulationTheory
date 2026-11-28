import unittest

from simulation import World, economy
from simulation.report import bottom_share, build_report, gini, lorenz, top_share
from simulation.rules import GOODS, Rules
from tests.classic import CALM, CLASSIC



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
        self.assertAlmostEqual(bottom_share([1, 1, 4, 4]), 0.2)  # poorest half holds 2 of 10


class RecorderTests(unittest.TestCase):
    def test_snapshot_counts_production_consumption_and_income(self):
        world = World(seed=1, rules=Rules.from_dict({**CLASSIC, "investing_enabled": False, "selling_enabled": False,
                                                     "assets": {g: 0 for g in GOODS},
                                                     "asset_labor": {"food": 1},
                                                     "labor_saving": {"food": 0, "water": 0, "games": 0},
                                                     "efficiency_weights": {"hunger": 0, "thirst": 0, "sleep": 0,
                                                                            "boredom": 0}}))
        owner = world.create_agent(needs={**CALM, "hunger": 0.6}, rates=CALM, labor_capacity=1, assets={"food": 1},
                                   inventory={"food": 0, "water": 50, "games": 50})
        world.step()
        snap = world.recorder.history[-1]
        self.assertEqual(snap["produced"]["food"], 1)          # its own 1 labour x productivity 1
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
        self.assertEqual(set(report["prices"]), set(economy.PRICED))
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


class DistributionReportTests(unittest.TestCase):
    def test_income_is_split_by_source_and_wages_counted(self):
        world = World(seed=3, rules=Rules.from_dict({"agents": 12}))
        world.spawn_random_agents()
        for _ in range(60):
            world.step()
        report = build_report(world)
        sources = report["totals"]["income_sources"]
        self.assertAlmostEqual(sum(sources.values()), report["totals"]["income"], places=4)
        self.assertGreater(sources["wages"], 0)

    def test_asset_concentration_uses_shares_not_value(self):
        world = World(seed=1, rules=Rules.from_dict({"investing_enabled": False, "selling_enabled": False}))
        world.create_agent(assets={**{g: 0 for g in GOODS}, "food": 4})
        world.create_agent(assets={g: 0 for g in GOODS})
        world.asset_prices = lambda prices=None: {g: 0.0 for g in economy.GOODS}   # assets worth nothing...
        world.step()
        self.assertAlmostEqual(world.recorder.history[-1]["gini_assets"], 0.5)   # ...but one agent owns them all

    def test_report_has_start_end_groups_and_quintiles(self):
        world = World(seed=2, rules=Rules.from_dict({"agents": 10}))
        world.spawn_random_agents()
        for _ in range(20):
            world.step()
        report = build_report(world, 10)
        self.assertEqual(report["end"]["tick"], world.tick)
        self.assertEqual(report["start"]["tick"], world.tick - 9)
        groups = report["groups"]
        self.assertEqual(groups["owners"]["count"] + groups["smes"]["count"] + groups["workers"]["count"], len(world.agents))
        self.assertEqual(len(report["quintiles"]), 5)
        self.assertAlmostEqual(sum(q["share"] for q in report["quintiles"]), 1)
        shares = [q["wealth"] for q in report["quintiles"]]
        self.assertEqual(shares, sorted(shares))                       # poorest fifth first
        for key in ("employment", "participation", "unemployment", "utilisation", "unfilled_jobs"):
            self.assertTrue(0 <= report["end"][key] <= 1, key)

    def test_deaths_are_counted_by_cause(self):
        world = World(seed=1)
        world.create_agent(needs={**CALM, "thirst": 1.0}, inventory={"food": 0, "water": 0, "games": 0})
        world.step()
        self.assertEqual(build_report(world)["totals"]["deaths_thirst"], 1)


if __name__ == "__main__":
    unittest.main()
