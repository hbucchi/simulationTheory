import unittest

from simulation import World, economy
from simulation.catalog import CATALOG
from simulation.rules import GOODS, Rules, is_primary
from tests.classic import CALM, CLASSIC

NO_ASSETS = {g: 0 for g in GOODS}
NO_STOCK = {g: 0 for g in GOODS}


def world_with(**rules):
    """No starting assets, no investing, no labour-saving or efficiency drag: just the industries."""
    return World(seed=1, rules=Rules.from_dict({
        "assets": NO_ASSETS, "investing_enabled": False, "selling_enabled": False,
        "labor_saving": {g: 0 for g in GOODS}, "productivity_growth": {g: 0 for g in GOODS},
        "depreciation": {g: 0 for g in GOODS},
        "efficiency_weights": {"hunger": 0, "thirst": 0, "sleep": 0, "boredom": 0},
        "asset_labor": {g: 1 for g in GOODS}, "productivity": {g: 1 for g in GOODS}, **rules}))


class RecipeTests(unittest.TestCase):
    def test_default_recipes(self):
        rules = Rules()
        self.assertEqual(rules.inputs, {e["id"]: e["inputs"] for e in CATALOG if e["inputs"]})
        self.assertEqual(rules.inputs["food"], {"grain": 1.0})
        self.assertTrue(is_primary("grain", rules) and is_primary("wood", rules) and is_primary("water", rules))
        self.assertFalse(is_primary("food", rules) or is_primary("games", rules))

    def test_recipes_are_validated(self):
        with self.assertRaises(ValueError):
            Rules.from_dict({"inputs": {"food": {"food": 1}}})      # its own input
        with self.assertRaises(ValueError):
            Rules.from_dict({"inputs": {"food": {"gold": 1}}})      # unknown good
        with self.assertRaises(ValueError):
            Rules.from_dict({"inputs": {"food": {"grain": -1}}})
        # Sending a table replaces it; zero amounts are dropped (primary).
        self.assertEqual(Rules.from_dict({"inputs": {"water": {"wood": 0.5}, "food": {"grain": 0}}}).inputs,
                         {"water": {"wood": 0.5}})


class ProductionTests(unittest.TestCase):
    def test_primary_needs_only_capital_and_labour(self):
        world = world_with()
        farmer = world.create_agent(needs=CALM, rates=CALM, labor_capacity=1, inventory=NO_STOCK,
                                    assets={**NO_ASSETS, "grain": 1})
        for _ in range(3):
            world.step()
        self.assertEqual(farmer.inventory.count("grain"), 3)

    def test_secondary_output_is_capped_by_inputs_and_uses_them(self):
        world = world_with()
        baker = world.create_agent(needs=CALM, rates=CALM, labor_capacity=1,
                                   inventory={**NO_STOCK, "grain": 2}, assets={**NO_ASSETS, "food": 1})
        for _ in range(5):   # labour for 5 food, but only 2 grain
            world.step()
        self.assertEqual(baker.inventory.count("food"), 2)
        self.assertEqual(baker.inventory.count("grain"), 0)

    def test_fractional_recipes_use_matching_fractions(self):
        world = world_with(inputs={"food": {"grain": 0.5}})
        baker = world.create_agent(needs=CALM, rates=CALM, labor_capacity=1,
                                   inventory={**NO_STOCK, "grain": 3}, assets={**NO_ASSETS, "food": 1})
        for _ in range(6):
            world.step()
        self.assertEqual(baker.inventory.count("food"), 6)   # 6 food x 0.5 grain = 3 grain
        self.assertEqual(baker.inventory.count("grain"), 0)

    def test_no_labour_is_hired_for_an_industry_without_inputs(self):
        world = world_with()
        baker = world.create_agent(needs=CALM, rates=CALM, labor_capacity=0, money=1e6,
                                   inventory=NO_STOCK, assets={**NO_ASSETS, "food": 1})
        world.create_agent(needs=CALM, rates=CALM, labor_capacity=1, money=1e6, inventory=NO_STOCK)
        world.step()
        self.assertEqual(baker.labor_need, 0)
        self.assertEqual(world.labor.stats["hired"], 0)

    def test_industry_stops_while_unsold_output_piles_up(self):
        world = world_with(max_output_stock=10)
        farmer = world.create_agent(needs=CALM, rates=CALM, labor_capacity=1,
                                    inventory={**NO_STOCK, "grain": 10}, assets={**NO_ASSETS, "grain": 1})
        world.step()
        self.assertEqual(farmer.inventory.count("grain"), 10)
        self.assertEqual(farmer.labor_need, 0)


class InputTradingTests(unittest.TestCase):
    def make_baker(self, world, grain):
        baker = world.create_agent(needs=CALM, rates=CALM, labor_capacity=0, money=1e6,
                                   inventory={**NO_STOCK, "grain": grain}, assets={**NO_ASSETS, "food": 1})
        world.step()   # sets its output capacity
        return baker

    def test_input_buffer_and_reorder_point(self):
        world = world_with()                      # capacity 1 food/step, 20 steps, reorder at half
        self.assertEqual(economy.input_target(self.make_baker(world, 10), "grain", world.rules), 20)
        self.assertEqual(economy.input_shortfall(self.make_baker(world, 9), "grain", world.rules), 11)
        self.assertEqual(economy.input_shortfall(self.make_baker(world, 10), "grain", world.rules), 0)

    def test_baker_keeps_its_inputs_and_farmer_sells_all_raw(self):
        world = world_with(selling_enabled=True)
        baker = self.make_baker(world, 30)
        farmer = world.create_agent(needs=CALM, rates=CALM, inventory={**NO_STOCK, "grain": 30})
        self.assertEqual(economy.spare(baker, "grain", world.rules), 10)    # keeps its 20-unit buffer
        self.assertEqual(economy.spare(farmer, "grain", world.rules), 30)   # no need for it: sells it all
        self.assertEqual(economy.surplus(farmer, "grain", world.rules), 30)
        # Grain also feeds people (0.06 per unit): with hunger growing 0.01/step an agent keeps the
        # floor of its 100-step band, 0.5 of relief = 9 grain.
        eater = world.create_agent(needs=CALM, rates={**CALM, "hunger": 0.01}, inventory={**NO_STOCK, "grain": 30})
        self.assertEqual(economy.spare(eater, "grain", world.rules), 21)

    def test_pure_inputs_are_never_kept_for_needs(self):
        world = world_with(selling_enabled=True)
        miner = world.create_agent(needs=CALM, inventory={**NO_STOCK, "ore": 30})
        self.assertIsNone(world.rules.need_of("ore"))
        self.assertEqual(economy.spare(miner, "ore", world.rules), 30)

    def test_short_baker_buys_inputs_from_farmer(self):
        world = world_with(price_mode="fixed", demand_pricing_enabled=False)
        baker = self.make_baker(world, 0)
        farmer = world.create_agent(needs=CALM, inventory={**NO_STOCK, "grain": 50})
        deals = economy.trade(baker, farmer, world.current_prices(), world.rules)
        self.assertEqual(deals[0][2], {"grain": 20})
        self.assertEqual(baker.inventory.count("grain"), 20)
        self.assertTrue(economy.wants_to_buy(self.make_baker(world, 0), "grain", world.rules))


class PricingTests(unittest.TestCase):
    def test_secondary_good_never_sells_below_its_inputs(self):
        world = world_with()
        world.create_agent(needs=CALM, inventory={**NO_STOCK, "food": 1000, "water": 10, "games": 10, "grain": 1, "wood": 10})
        world.labor.wage = 5.0
        prices = world.current_prices()
        # food is plentiful, grain scarce: the scarcity price alone would put food below grain. The
        # floor is the unit cost (1 grain + labour: wage 5 / productivity 1) plus the 10% margin.
        self.assertAlmostEqual(prices["food"], (prices["grain"] * 1 + 5.0 / world.productivity_now["food"]) * 1.1)
        world.rules.cost_floor = False
        self.assertLess(world.current_prices()["food"], prices["grain"])

    def test_asset_price_counts_input_costs(self):
        world = world_with(price_mode="fixed", demand_pricing_enabled=False, gov_min_rate=0,
                           fixed_prices={"food": 10, "grain": 4, "labor": 1},
                           asset_return={"food": 0.1})
        world.labor.wage = 1.0
        # one food asset: 1 labour -> 1 food: profit = 1 x (10 - 4) - 1 x 1 = 5, / 0.1 return
        self.assertAlmostEqual(world.asset_prices()["food"], 50)


if __name__ == "__main__":
    unittest.main()
