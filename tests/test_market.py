import unittest

from simulation import World, economy
from simulation.rules import GOODS, Rules
from tests.classic import CALM, CLASSIC



def world_with(**rules):
    # Investing is off unless a test turns it on: asset purchases would spend the money under test.
    return World(seed=1, rules=Rules.from_dict({**CLASSIC, "investing_enabled": False, "selling_enabled": False,
                                                "assets": {g: 0 for g in GOODS}, **rules}))


class ScarcityTests(unittest.TestCase):
    def test_decline_in_average_per_agent_over_the_window(self):
        world = world_with(scarcity_window=10)
        agent = world.create_agent(inventory={"water": 100}, x=0, y=0)
        for step in range(10):
            world.update_scarcity()
            agent.inventory.set("water", 100 - 2 * (step + 1))
        self.assertEqual(world.scarcity["water"], 0)           # window not full yet
        world.update_scarcity()                                  # 100 ... 80 over 10 steps
        self.assertAlmostEqual(world.scarcity["water"], 0.2)
        self.assertEqual(world.scarcity["food"], 0)

    def test_reserve_grows_with_decline_and_is_capped(self):
        rules = Rules.from_dict({"stockpile_steps": 100, "scarcity_trigger": 0.1})
        world = World(seed=1, rules=rules)
        agent = world.create_agent(rates={"thirst": 0.015})  # uses 0.15/step
        target = lambda d: economy.stockpile_target(agent, "water", rules, {"water": d})
        self.assertEqual(target(0.05), 0)      # below the trigger
        self.assertEqual(target(0.1), 15)      # 0.15 x 100 x 1
        self.assertEqual(target(0.2), 30)      # twice the trigger -> twice the reserve
        self.assertEqual(target(0.9), 45)      # capped at 3x

    def test_self_sufficient_producer_does_not_stockpile(self):
        rules = Rules()
        agent = World(seed=1).create_agent(rates={"thirst": 0.01})  # uses 0.1 water per step
        agent.output_capacity = {"water": 0.2}                       # its water assets make 0.2
        self.assertEqual(economy.stockpile_target(agent, "water", rules, {"water": 0.5}), 0)

    def test_disabled_means_no_reserve(self):
        rules = Rules.from_dict({"stockpiling_enabled": False})
        agent = World(seed=1).create_agent()
        self.assertEqual(economy.stockpile_target(agent, "water", rules, {"water": 0.5}), 0)


class StockpilingTests(unittest.TestCase):
    def setUp(self):
        self.world = world_with(stockpile_steps=100, scarcity_trigger=0.1, stockpile_budget=0.5)
        self.world.scarcity = {"food": 0, "water": 0.2, "games": 0}
        self.world.update_scarcity = lambda: None   # keep the scarcity fixed for the test

    def test_calm_agent_goes_to_stockpile_a_scarce_resource(self):
        hoarder = self.world.create_agent(inventory={"water": 0}, needs=CALM,
                                          rates={"thirst": 0.015}, money=100, x=100, y=100, movement=5)
        seller = self.world.create_agent(inventory={"water": 500}, needs=CALM,
                                         x=200, y=100, movement=1)
        self.world.step()
        self.assertEqual((hoarder.activity, hoarder.target_id, hoarder.seeking_for),
                         ("stockpiling", seller.id, "water"))

    def test_stockpile_is_bought_with_money_within_budget(self):
        buyer = self.world.create_agent(inventory={"water": 0, "food": 50}, needs=CALM,
                                        rates={"thirst": 0.015}, money=10)
        seller = self.world.create_agent(inventory={"water": 500}, needs=CALM)
        bought, paid, stocked, _ = economy.buy(buyer, seller, {"food": 1, "water": 1, "games": 1},
                                            self.world.rules, None, self.world.scarcity)
        # Wants 30 in reserve, but may spend only half of its 10 money: 5 units, no food given away.
        self.assertEqual((bought, stocked), ({"water": 5}, {"water": 5}))
        self.assertEqual((buyer.money, buyer.inventory.count("food")), (5, 50))

    def test_seller_keeps_its_own_reserve(self):
        seller = self.world.create_agent(inventory={"water": 20}, needs=CALM,
                                         rates={"thirst": 0.015})
        self.assertEqual(economy.spare(seller, "water", self.world.rules, self.world.scarcity), 0)  # reserve 30
        self.assertEqual(economy.spare(seller, "water", self.world.rules), 20)  # no scarcity, no reserve

    def test_trade_log_marks_stockpiled_units(self):
        self.world.create_agent(inventory={"water": 0}, needs=CALM,
                                rates={"thirst": 0.015}, money=100, x=100, y=100, movement=1)
        self.world.create_agent(inventory={"water": 500}, needs=CALM,
                                x=105, y=100, movement=1)
        self.world.step()
        self.assertIn("water to stockpile", self.world.events[0]["message"])



class DemandPricingTests(unittest.TestCase):
    def test_target_multiplier_follows_buyers_over_sellers(self):
        rules = Rules()  # elasticity 0.5, floor 0.25, cap 4
        target = lambda b, s, level=0.0: economy.demand_multiplier_target(b, s, "water", rules, level)
        self.assertEqual(target(0, 0), 1)
        self.assertAlmostEqual(target(8, 0), 3)            # (9/1) ** 0.5
        self.assertAlmostEqual(target(0, 8), 1 / 3)        # (1/9) ** 0.5
        self.assertEqual(target(1000, 0), 4)               # capped
        self.assertEqual(target(0, 1000), 0.25)            # floored
        self.assertAlmostEqual(target(0, 0, 1.0), 2)       # one holder of all supply, weight 1

    def test_elasticity_is_set_per_resource(self):
        rules = Rules.from_dict({"price_elasticity": {"food": 0, "water": 1}})
        self.assertEqual(economy.demand_pressure(8, 0, "food", rules), 1)    # food ignores demand
        self.assertEqual(economy.demand_pressure(8, 0, "water", rules), 9)   # water fully reacts
        self.assertEqual(economy.demand_pressure(8, 0, "games", rules), 3)   # default 0.5

    def test_concentration_measure(self):
        self.assertEqual(economy.concentration([5, 5, 5, 5]), 0)             # spread evenly
        self.assertEqual(economy.concentration([20, 0, 0, 0]), 1)            # one holder
        self.assertAlmostEqual(economy.concentration([10, 10, 0, 0]), 1 / 3)  # HHI 0.5 -> (0.5-0.25)/0.75
        self.assertEqual(economy.concentration([0, 0, 0]), 0)                # no supply

    def test_concentrated_supply_raises_the_price(self):
        rules = {"demand_pricing_enabled": True, "price_elasticity": {"water": 0}, "price_adjust_speed": 1,
                 "concentration_weight": {"water": 1}}
        spread = world_with(**rules)
        alone = world_with(**rules)
        for i in range(4):
            spread.create_agent(inventory={"water": 50}, needs=CALM, x=10 * i, y=0)
            alone.create_agent(inventory={"water": 200 if i == 0 else 0}, needs=CALM, x=10 * i, y=0)
        spread.update_demand()
        alone.update_demand()
        self.assertEqual(spread.price_multiplier["water"], 1)
        self.assertEqual(alone.price_multiplier["water"], 2)

    def make_world(self, thirsty, sellers, **rules):
        # Demand pressure on its own: no concentration factor.
        world = world_with(stockpiling_enabled=False,
                           concentration_weight={"food": 0, "water": 0, "games": 0},
                           buyer_power_weight={"food": 0, "water": 0, "games": 0}, **rules)
        for i in range(thirsty):
            world.create_agent(inventory={"water": 0}, needs={**CALM, "thirst": 0.9}, rates={"thirst": 0}, x=10 * i, y=0)
        for i in range(sellers):
            world.create_agent(inventory={"water": 100}, needs=CALM, rates={"thirst": 0}, x=10 * i, y=900)
        return world

    def test_many_buyers_few_sellers_push_the_price_up_gradually(self):
        world = self.make_world(thirsty=8, sellers=1)
        base = economy.market_prices(world.agents, world.rules)["water"]
        world.update_demand()
        self.assertEqual((world.buyers["water"], world.sellers["water"]), (8, 1))
        first = world.current_prices()["water"] / base
        self.assertAlmostEqual(first, 1 + 0.2 * ((9 / 2) ** 0.5 - 1))  # 20% of the way to the target
        for _ in range(50):
            world.update_demand()
        self.assertAlmostEqual(world.current_prices()["water"] / base, (9 / 2) ** 0.5, places=3)

    def test_many_sellers_few_buyers_push_the_price_down(self):
        world = self.make_world(thirsty=1, sellers=8)
        for _ in range(50):
            world.update_demand()
        self.assertAlmostEqual(world.price_multiplier["water"], (2 / 9) ** 0.5, places=3)

    def test_disabled_keeps_the_base_price(self):
        world = self.make_world(thirsty=8, sellers=1, demand_pricing_enabled=False)
        for _ in range(10):
            world.update_demand()
        self.assertEqual(world.price_multiplier["water"], 1)

    def test_each_extra_unit_costs_more_under_pressure(self):
        rules = Rules.from_dict({"selling_enabled": False})
        buyer = World(seed=1).create_agent(inventory={"water": 0, "food": 0, "games": 0},
                                           needs={**CALM, "thirst": 0.6}, money=100)
        seller = World(seed=1).create_agent(inventory={"water": 100}, needs=CALM)
        bought, paid, _, unit_prices = economy.buy(buyer, seller, {"food": 1, "water": 1, "games": 1},
                                                   rules, None, None, {"water": 0.1})
        self.assertEqual(bought, {"water": 4})                            # 0.6 -> below 0.3
        self.assertAlmostEqual(paid["money"], 1 + 1.1 + 1.21 + 1.331)
        self.assertAlmostEqual(unit_prices["water"][1], 1.331)

    def test_markup_only_applies_where_buyers_outnumber_sellers(self):
        world = self.make_world(thirsty=3, sellers=1)
        world.update_demand()
        markups = world.unit_markups()
        self.assertEqual(markups["water"], 0.05)
        self.assertEqual({g for g, m in markups.items() if m}, {"water"})


class BuyerPowerTests(unittest.TestCase):
    def test_concentrated_buying_power_pushes_prices_down(self):
        rules = Rules.from_dict({"buyer_power_weight": {"water": 1}, "concentration_weight": {"water": 0}})
        even = economy.demand_multiplier_target(5, 5, "water", rules, 0.0, buyer_level=0.0)
        one_buyer = economy.demand_multiplier_target(5, 5, "water", rules, 0.0, buyer_level=1.0)
        self.assertAlmostEqual(even, 1.0)
        self.assertAlmostEqual(one_buyer, 0.5)        # a monopsony halves the price at weight 1


if __name__ == "__main__":
    unittest.main()
