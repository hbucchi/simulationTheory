import unittest

from simulation import World, economy
from simulation.catalog import CATALOG, SECTORS
from simulation import distributions
from simulation.rules import GOODS, MAX_LAYERS, SIZING_HEADROOM, Rules
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
        # Without food, meat or meals, hunger falls on raw grain and livestock: their farms alone
        # can relieve SIZING_HEADROOM x the hunger an average agent builds up.
        capacity = sum(one.assets[g]["average"] * one.asset_labor[g] * one.productivity[g] * one.relief(g, "hunger")
                       for g in one.goods_for("hunger"))
        self.assertGreaterEqual(capacity, SIZING_HEADROOM * distributions.mean(one.rates["hunger"]) * 0.99)
        self.assertNotEqual(one.assets["grain"]["average"], catalog["grain"])
        self.assertEqual(one.assets["food"]["average"], 0)
        # An input people also consume gets extra capacity for that: grain feeds food and is eaten.
        food_use = full.assets["food"]["average"] * full.asset_labor["food"] * full.productivity["food"]
        grain_made = full.assets["grain"]["average"] * full.asset_labor["grain"] * full.productivity["grain"]
        self.assertGreater(grain_made, food_use * full.inputs["food"]["grain"] * SIZING_HEADROOM * 0.99)
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
        self.assertAlmostEqual(rules.relief(rules.goods_for("hunger")[0], "hunger"), 0.2)   # most effective first
        self.assertEqual(rules.relief("ore"), 0)                              # relieves no need
        self.assertNotIn("sleep", rules.consumer_needs)                       # sleep comes from rest

    def test_effects_are_validated_and_replace_the_table(self):
        rules = Rules.from_dict({"effects": {"steel": {"shelter": 0.5}}})
        self.assertEqual(rules.need_of("steel"), "shelter")
        self.assertIsNone(rules.need_of("food"))
        bad = ({"food": {"sleep": 0.5}},     # sleep can only be harmed
               {"food": {"joy": 1}}, {"food": {"hunger": 2}}, {"food": {"hunger": -1.5}})
        for effects in bad:
            with self.assertRaises(ValueError):
                Rules.from_dict({"effects": effects})


class MultiNeedTests(unittest.TestCase):
    def test_a_good_can_relieve_several_needs_and_harm_others(self):
        rules = Rules()
        e = rules.effects_of("fast_food")                     # layer 3: benefits x2, harm unscaled
        self.assertAlmostEqual(e["hunger"], 0.2)
        self.assertAlmostEqual(e["boredom"], 0.08)
        self.assertAlmostEqual(e["health"], -0.04)
        self.assertEqual(rules.need_of("fast_food"), "hunger")   # its biggest benefit
        self.assertIn("fast_food", rules.goods_for("boredom"))   # a side benefit counts too
        self.assertNotIn("fast_food", rules.goods_for("health"))

    def test_eating_applies_every_effect(self):
        world = quiet_world()
        agent = world.create_agent(needs={**CALM, "hunger": 0.6, "boredom": 0.4}, rates=CALM,
                                   inventory={**NO_STOCK, "fast_food": 5})
        economy.consume(agent, world.rules)
        # 2 units: hunger 0.6 -> 0.2, boredom 0.4 -> 0.24, health 0 -> 0.08
        self.assertAlmostEqual(agent.hunger, 0.2)
        self.assertAlmostEqual(agent.boredom, 0.24)
        self.assertAlmostEqual(agent.health, 0.08)

    def test_side_effects_matter_more_when_that_need_is_pressing(self):
        world = quiet_world()
        stock = {**NO_STOCK, "fast_food": 5, "meals": 5}
        healthy = world.create_agent(needs={**CALM, "hunger": 0.6, "boredom": 0.5}, rates=CALM, inventory=stock)
        ill = world.create_agent(needs={**CALM, "hunger": 0.6, "boredom": 0.5, "health": 0.9}, rates=CALM, inventory=stock)
        # Both relieve hunger 0.2; fast food adds fun (+0.08 x 0.5) but costs health (-0.04 x level).
        self.assertGreater(economy.benefit(healthy, "fast_food", world.rules, "hunger"),
                           economy.benefit(healthy, "meals", world.rules, "hunger"))
        self.assertLess(economy.benefit(ill, "fast_food", world.rules, "hunger"),
                        economy.benefit(ill, "meals", world.rules, "hunger"))
        economy.consume(ill, world.rules)
        self.assertEqual(ill.inventory.count("fast_food"), 5)   # ate the meals instead

    def test_harmful_goods_are_not_consumed(self):
        world = quiet_world(effects={"spirits": {"boredom": 0.1, "health": -1}})
        agent = world.create_agent(needs={**CALM, "boredom": 0.6, "health": 0.8}, rates=CALM,
                                   inventory={**NO_STOCK, "spirits": 5})
        economy.consume(agent, world.rules)
        self.assertEqual(agent.inventory.count("spirits"), 5)


class LabourByLayerTests(unittest.TestCase):
    def test_deeper_layers_need_less_labour_per_unit_with_exceptions(self):
        rules = Rules()
        per_unit = {}
        for g in rules.active_goods:
            per_unit.setdefault(rules.layer(g), []).append(1 / rules.productivity[g])
        averages = [sum(v) / len(v) for _, v in sorted(per_unit.items())]
        self.assertEqual(averages, sorted(averages, reverse=True))           # falls layer by layer
        self.assertGreater(1 / rules.productivity["healthcare"], 1 / rules.productivity["software"])
        self.assertEqual(rules.productivity["water"], 4.0)
        self.assertEqual(rules.productivity["software"], 9.0)


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
