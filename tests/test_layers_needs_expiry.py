import unittest

from simulation import World, economy
from simulation.catalog import CATALOG, SECTORS
from simulation.rules import GOODS, MAX_LAYERS, Rules
from tests.classic import CALM

NO_STOCK = {g: 0 for g in GOODS}
NO_ASSETS = {g: 0 for g in GOODS}


def quiet_world(**rules):
    """No starting assets, no investing, no selling: tests place their own agents."""
    return World(seed=1, rules=Rules.from_dict({"assets": NO_ASSETS, "investing_enabled": False,
                                                "selling_enabled": False, **rules}))


class CatalogTests(unittest.TestCase):
    def test_every_industry_has_a_known_sector_and_valid_recipe(self):
        for e in CATALOG:
            self.assertIn(e["sector"], SECTORS, e["id"])
            self.assertTrue(set(e["inputs"]) <= set(GOODS), e["id"])
        self.assertEqual(len({e["id"] for e in CATALOG}), len(CATALOG))

    def test_layers_follow_the_recipes(self):
        rules = Rules()
        self.assertEqual(rules.layer("grain"), 1)
        self.assertEqual(rules.layer("food"), 2)            # grain -> food
        self.assertEqual(rules.layer("meals"), 3)           # food, meat, electricity -> meals
        self.assertEqual(rules.layer("software"), 6)        # ... electronics -> telecom -> software
        for e in CATALOG:
            deepest_input = max((rules.layer(i) for i in e["inputs"]), default=0)
            self.assertEqual(rules.layer(e["id"]), deepest_input + 1, e["id"])


class LayerLimitTests(unittest.TestCase):
    def test_industries_deeper_than_the_limit_do_not_exist(self):
        rules = Rules.from_dict({"industry_layers": 2})
        self.assertTrue(rules.is_active("food"))
        self.assertFalse(rules.is_active("meals"))
        self.assertTrue(all(rules.layer(g) <= 2 for g in rules.active_goods))
        world = World(seed=1, rules=rules)
        agent = world.create_agent(inventory={"meals": 5}, assets={"software": 3})
        self.assertEqual(agent.inventory.count("meals"), 0)
        self.assertNotIn("software", agent.assets)
        self.assertNotIn("meals", rules.goods_for("hunger"))

    def test_limit_and_depth_are_validated(self):
        for bad in (0, 11):
            with self.assertRaises(ValueError):
                Rules.from_dict({"industry_layers": bad})
        chain = {GOODS[i + 1]: {GOODS[i]: 1} for i in range(MAX_LAYERS)}   # 11 layers deep
        with self.assertRaises(ValueError):
            Rules.from_dict({"inputs": chain})
        with self.assertRaises(ValueError):                                # a loop
            Rules.from_dict({"inputs": {"food": {"meals": 1}, "meals": {"food": 1}}})


class GameSizingTests(unittest.TestCase):
    def test_default_industries_are_sized_for_the_game(self):
        full, one = Rules.from_dict({}), Rules.from_dict({"industry_layers": 1})
        catalog = {e["id"]: e["shares"] for e in CATALOG}
        self.assertEqual({g: full.assets[g]["average"] for g in GOODS}, catalog)    # full game = the catalog
        # Without food, meat or meals, hunger falls on raw grain and livestock: bigger farms.
        self.assertGreater(one.assets["grain"]["average"], catalog["grain"])
        self.assertGreater(one.assets["livestock"]["average"], catalog["livestock"])
        self.assertEqual(one.assets["food"]["average"], 0)
        # Explicit assets are kept as given.
        self.assertEqual(Rules.from_dict({"industry_layers": 1, "assets": {"grain": 5}}).assets["grain"], 5)

    def test_starting_stock_of_missing_goods_becomes_the_same_relief(self):
        one = Rules.from_dict({"industry_layers": 1})
        # 30 food (0.15 each = 4.5 of hunger relief) -> 75 grain (0.06 each), on top of 30 grain.
        self.assertEqual(one.inventory["food"], 0)
        self.assertEqual(one.inventory["grain"], 105)


class EffectivenessTests(unittest.TestCase):
    def test_deeper_layers_relieve_more_per_unit(self):
        rules = Rules()   # relief_per_unit 0.1, layer bonus 0.5
        self.assertAlmostEqual(rules.relief("water"), 0.1)                     # layer 1, fit 1
        self.assertAlmostEqual(rules.relief("grain"), 0.1 * 0.6)              # layer 1, fit 0.6
        self.assertAlmostEqual(rules.relief("food"), 0.1 * 1.5)               # layer 2
        self.assertAlmostEqual(rules.relief("meals"), 0.1 * 2.0)              # layer 3
        self.assertEqual(rules.goods_for("hunger")[0], "meals")               # most effective first
        self.assertEqual(rules.relief("ore"), 0)                              # relieves no need
        self.assertNotIn("sleep", rules.consumer_needs)                       # sleep comes from rest

    def test_satisfies_is_validated_and_replaces_the_table(self):
        rules = Rules.from_dict({"satisfies": {"steel": {"need": "shelter", "fit": 0.5}}})
        self.assertEqual(rules.need_of("steel"), "shelter")
        self.assertIsNone(rules.need_of("food"))
        for bad in ({"food": {"need": "sleep", "fit": 1}}, {"food": {"need": "joy"}}, {"food": {"need": "hunger", "fit": 2}}):
            with self.assertRaises(ValueError):
                Rules.from_dict({"satisfies": bad})


class NeedLevelTests(unittest.TestCase):
    def test_consumes_the_most_effective_good_first(self):
        world = quiet_world()
        agent = world.create_agent(needs={**CALM, "hunger": 0.7}, rates=CALM,
                                   inventory={**NO_STOCK, "grain": 10, "food": 10, "meals": 1})
        economy.consume(agent, world.rules)
        # 1 meal (0.2) then 2 food (0.15 each): 0.7 -> 0.2; grain untouched.
        self.assertEqual(agent.inventory.count("meals"), 0)
        self.assertEqual(agent.inventory.count("food"), 8)
        self.assertEqual(agent.inventory.count("grain"), 10)
        self.assertAlmostEqual(agent.hunger, 0.2)

    def test_demand_counts_relief_from_every_good_for_the_need(self):
        world = quiet_world()
        agent = world.create_agent(needs={**CALM, "hunger": 0.7}, rates=CALM, inventory={**NO_STOCK, "grain": 5})
        # 0.7 - 5 x 0.06 = 0.4 still to bring below 0.3: 1 food (0.15) or 2 grain (0.06 each).
        self.assertEqual(economy.demand(agent, "food", world.rules), 1)
        self.assertEqual(economy.demand(agent, "grain", world.rules), 2)

    def test_buyer_picks_the_best_relief_per_dollar_and_does_not_overbuy(self):
        world = quiet_world(price_mode="fixed", demand_pricing_enabled=False,
                            fixed_prices={"grain": 1, "food": 10, "meals": 3})
        buyer = world.create_agent(needs={**CALM, "hunger": 0.7}, rates=CALM, money=100, inventory=NO_STOCK)
        seller = world.create_agent(needs=CALM, rates=CALM, inventory={**NO_STOCK, "grain": 50, "food": 50, "meals": 50})
        bought, *_ = economy.buy(buyer, seller, world.current_prices(), world.rules)
        # Per unit of relief: meals $15, grain $16.7, food $66.7 -> meals only, 0.7 -> below 0.3: 3 meals.
        self.assertEqual(bought, {"meals": 3})

    def test_seeks_the_nearest_agent_with_any_good_for_its_need(self):
        world = quiet_world()
        hungry = world.create_agent(needs={**CALM, "hunger": 0.9}, rates=CALM, inventory=NO_STOCK, x=100, y=100)
        near = world.create_agent(needs=CALM, rates=CALM, inventory={**NO_STOCK, "grain": 50}, x=200, y=100)
        world.create_agent(needs=CALM, rates=CALM, inventory={**NO_STOCK, "meals": 50}, x=900, y=900)
        world.update_demand()
        self.assertEqual(world.nearest_seller(hungry), (near, "grain"))


class ExpiryTests(unittest.TestCase):
    def test_units_expire_after_their_shelf_life_and_are_counted(self):
        world = quiet_world(shelf_life={"food": 3})
        agent = world.create_agent(needs=CALM, rates=CALM, inventory=NO_STOCK)
        agent.inventory.add("food", 4)          # made now (step 0): expire at step 3
        for _ in range(3):
            world.step()
        self.assertEqual(agent.inventory.count("food"), 0)
        self.assertEqual(sum(s["expired"]["food"] for s in world.recorder.history), 4)

    def test_starting_stock_expires_bit_by_bit(self):
        world = quiet_world(shelf_life={"food": 100})
        agent = world.create_agent(needs=CALM, rates=CALM, inventory={**NO_STOCK, "food": 50})
        expiries = sorted({expires for expires, _ in agent.inventory.batches["food"]})
        self.assertEqual(len(expiries), World.START_BATCHES)
        self.assertEqual((expiries[0], expiries[-1]), (10, 100))

    def test_traded_units_keep_their_expiry_and_expiry_can_be_off(self):
        world = quiet_world(shelf_life={"food": 50})
        a = world.create_agent(needs=CALM, rates=CALM, inventory=NO_STOCK)
        b = world.create_agent(needs=CALM, rates=CALM, inventory=NO_STOCK)
        a.inventory.add("food", 2, expires=7)
        economy.transfer(a, b, "food", 2)
        self.assertEqual(list(b.inventory.batches["food"]), [[7, 2]])
        off = quiet_world(expiry_enabled=False).create_agent(inventory={**NO_STOCK, "food": 5})
        self.assertNotIn("food", off.inventory.perishable)

    def test_perishables_are_only_stocked_up_to_what_will_be_used(self):
        world = World(seed=1, rules=Rules.from_dict({"stock_steps": 1000, "shelf_life": {"food": 100}}))
        agent = world.create_agent(needs=CALM, rates={**CALM, "hunger": 0.01}, inventory=NO_STOCK)
        # Hunger would want 10 of relief (67 food), but in 80 of food's 100 steps it eats 0.01/0.15 x 80.
        self.assertEqual(economy.useful_stock(agent, "food", world.rules), 6)
        self.assertEqual(economy.restock_shortfall(agent, "food", world.rules), 6)


class StockBandTests(unittest.TestCase):
    def test_band_is_steps_of_each_need(self):
        world = World(seed=1, rules=Rules.from_dict({"stock_steps": 100, "restock_below": 0.5, "expiry_enabled": False}))
        agent = world.create_agent(needs=CALM, rates={**CALM, "thirst": 0.02}, inventory=NO_STOCK)
        self.assertAlmostEqual(economy.band_relief(agent, "thirst", world.rules), 2.0)   # 100 steps x 0.02
        self.assertEqual(economy.restock_shortfall(agent, "water", world.rules), 20)    # 2.0 / 0.1


if __name__ == "__main__":
    unittest.main()
