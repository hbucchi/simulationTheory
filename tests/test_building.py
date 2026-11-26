import unittest

from simulation import World, economy
from simulation.catalog import CAPITAL_GOODS
from simulation.modules import Build
from simulation.rules import GOODS, Rules
from tests.classic import CALM

NO_STOCK = {g: 0 for g in GOODS}
NO_ASSETS = {g: 0 for g in GOODS}
FIXED = {"price_mode": "fixed", "demand_pricing_enabled": False}


def world_with(**rules):
    return World(seed=1, rules=Rules.from_dict({"assets": NO_ASSETS, "selling_enabled": False, **FIXED, **rules}))


class CapitalIndustryTests(unittest.TestCase):
    def test_capital_goods_and_build_costs(self):
        rules = Rules()
        self.assertEqual(set(CAPITAL_GOODS), {"machinery", "construction"})
        self.assertEqual(rules.build_cost["grain"], {"machinery": 2.0, "construction": 1.0})
        self.assertEqual(rules.build_cost["software"], {"construction": 2.0, "electronics": 3.0})
        self.assertEqual(Rules.from_dict({"build_cost": {"food": {"machinery": 5}}}).build_cost["food"], {"machinery": 5})
        with self.assertRaises(ValueError):
            Rules.from_dict({"build_cost": {"food": {"gold": 1}}})

    def test_capital_and_housing_plants_make_little_per_step(self):
        rules = Rules()
        per_share = {g: rules.asset_labor[g] * rules.productivity[g] for g in rules.active_goods}
        normal = sorted(per_share[g] for g in per_share if g not in ("machinery", "construction", "housing"))
        median = normal[len(normal) // 2]
        for g in ("machinery", "construction", "housing"):
            self.assertLess(per_share[g], median / 4, g)


class BuildTests(unittest.TestCase):
    def investor(self, world, **kw):
        return world.create_agent(**{"needs": CALM, "rates": CALM, "money": 1e6, "inventory": NO_STOCK, **kw})

    def test_starts_a_project_when_an_asset_is_worth_more_than_building_it(self):
        world = world_with(fixed_prices={"machinery": 10, "construction": 10, "labor": 1}, min_investment=1)
        investor = self.investor(world)
        world.create_agent(needs=CALM, rates=CALM, inventory={**NO_STOCK, "machinery": 50, "construction": 50})
        world.update_demand()
        Build().on_step(investor, world)
        self.assertIsNotNone(investor.project)
        good = investor.project["good"]
        self.assertGreaterEqual(investor.project["q"], 1)
        self.assertEqual(set(investor.project["need"]), set(world.rules.build_cost[good]))
        self.assertGreater(economy.project_shortfall(investor, "machinery") + economy.project_shortfall(investor, "construction"), 0)

    def test_no_project_without_capital_goods_for_sale(self):
        world = world_with(fixed_prices={"machinery": 10, "construction": 10, "labor": 1}, min_investment=1)
        investor = self.investor(world)
        world.update_demand()
        Build().on_step(investor, world)
        self.assertIsNone(investor.project)

    def test_no_project_when_building_costs_more_than_the_asset_is_worth(self):
        world = world_with(fixed_prices={"machinery": 1e9, "construction": 1e9, "electronics": 1e9, "labor": 1},
                           min_investment=1)
        investor = self.investor(world)
        world.create_agent(needs=CALM, rates=CALM, inventory={**NO_STOCK, "machinery": 50, "construction": 50})
        world.update_demand()
        Build().on_step(investor, world)
        self.assertIsNone(investor.project)

    def test_holding_all_the_capital_goods_completes_the_project(self):
        world = world_with()
        builder = self.investor(world, inventory={**NO_STOCK, "machinery": 5, "construction": 3})
        builder.project = {"good": "grain", "shares": 1.0, "need": {"machinery": 2, "construction": 1}, "started": 0}
        self.assertEqual(economy.spare(builder, "machinery", world.rules), 3)   # keeps what the project needs
        Build().on_step(builder, world)
        self.assertIsNone(builder.project)
        self.assertEqual(builder.assets["grain"], 1.0)
        self.assertEqual((builder.inventory.count("machinery"), builder.inventory.count("construction")), (3, 2))
        self.assertEqual(world.assets_built, {"grain": 1.0})

    def test_project_is_dropped_after_too_long(self):
        world = world_with(project_steps=5)
        builder = self.investor(world)
        builder.project = {"good": "grain", "shares": 1.0, "need": {"machinery": 2}, "started": 0}
        world.tick = 6
        Build().on_step(builder, world)
        self.assertIsNone(builder.project)
        self.assertNotIn("grain", builder.assets)

    def test_builder_goes_out_to_buy_capital_goods(self):
        world = world_with()
        builder = self.investor(world, x=100, y=100)
        seller = world.create_agent(needs=CALM, rates=CALM, inventory={**NO_STOCK, "machinery": 10}, x=800, y=100)
        builder.project = {"good": "grain", "shares": 1.0, "need": {"machinery": 2}, "started": 0}
        world.update_demand()
        self.assertEqual(world.nearest_seller(builder, stockpile=True), (seller, "machinery"))
        deals = economy.trade(builder, seller, world.current_prices(), world.rules)
        self.assertEqual(deals[0][2], {"machinery": 2})


if __name__ == "__main__":
    unittest.main()
