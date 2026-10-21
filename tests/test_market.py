import unittest

from simulation import World, economy
from simulation.rules import Rules

CALM = {"hunger": 0, "sleep": 0, "thirst": 0, "boredom": 0}


def world_with(**rules):
    return World(seed=1, rules=Rules.from_dict(rules))


class ScarcityTests(unittest.TestCase):
    def test_decline_in_average_per_agent_over_the_window(self):
        world = world_with(scarcity_window=10)
        agent = world.create_agent(inventory={"water": 100}, production={"water": 0}, x=0, y=0)
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
        agent = world.create_agent(rates={"thirst": 0.015}, production={"water": 0})  # uses 0.15/step
        target = lambda d: economy.stockpile_target(agent, "water", rules, {"water": d})
        self.assertEqual(target(0.05), 0)      # below the trigger
        self.assertEqual(target(0.1), 15)      # 0.15 x 100 x 1
        self.assertEqual(target(0.2), 30)      # twice the trigger -> twice the reserve
        self.assertEqual(target(0.9), 45)      # capped at 3x

    def test_self_sufficient_producer_does_not_stockpile(self):
        rules = Rules()
        agent = World(seed=1).create_agent(rates={"thirst": 0.01}, production={"water": 5})  # uses 0.1, makes 0.2
        self.assertEqual(economy.stockpile_target(agent, "water", rules, {"water": 0.5}), 0)

    def test_disabled_means_no_reserve(self):
        rules = Rules.from_dict({"stockpiling_enabled": False})
        agent = World(seed=1).create_agent(production={"water": 0})
        self.assertEqual(economy.stockpile_target(agent, "water", rules, {"water": 0.5}), 0)


class StockpilingTests(unittest.TestCase):
    def setUp(self):
        self.world = world_with(stockpile_steps=100, scarcity_trigger=0.1, stockpile_budget=0.5)
        self.world.scarcity = {"food": 0, "water": 0.2, "games": 0}
        self.world.update_scarcity = lambda: None   # keep the scarcity fixed for the test

    def test_calm_agent_goes_to_stockpile_a_scarce_resource(self):
        hoarder = self.world.create_agent(inventory={"water": 0}, needs=CALM, production={"water": 0},
                                          rates={"thirst": 0.015}, money=100, x=100, y=100, movement=5)
        seller = self.world.create_agent(inventory={"water": 500}, needs=CALM, production={"water": 1},
                                         x=200, y=100, movement=1)
        self.world.step()
        self.assertEqual((hoarder.activity, hoarder.target_id, hoarder.seeking_for),
                         ("stockpiling", seller.id, "water"))

    def test_stockpile_is_bought_with_money_within_budget(self):
        buyer = self.world.create_agent(inventory={"water": 0, "food": 50}, needs=CALM, production={"water": 0},
                                        rates={"thirst": 0.015}, money=10)
        seller = self.world.create_agent(inventory={"water": 500}, needs=CALM, production={"water": 1})
        bought, paid, stocked = economy.buy(buyer, seller, {"food": 1, "water": 1, "games": 1},
                                            self.world.rules, None, self.world.scarcity)
        # Wants 30 in reserve, but may spend only half of its 10 money: 5 units, no food given away.
        self.assertEqual((bought, stocked), ({"water": 5}, {"water": 5}))
        self.assertEqual((buyer.money, buyer.inventory.count("food")), (5, 50))

    def test_seller_keeps_its_own_reserve(self):
        seller = self.world.create_agent(inventory={"water": 20}, needs=CALM, production={"water": 0},
                                         rates={"thirst": 0.015})
        self.assertEqual(economy.spare(seller, "water", self.world.rules, self.world.scarcity), 0)  # reserve 30
        self.assertEqual(economy.spare(seller, "water", self.world.rules), 20)  # no scarcity, no reserve

    def test_trade_log_marks_stockpiled_units(self):
        self.world.create_agent(inventory={"water": 0}, needs=CALM, production={"water": 0},
                                rates={"thirst": 0.015}, money=100, x=100, y=100, movement=1)
        self.world.create_agent(inventory={"water": 500}, needs=CALM, production={"water": 1},
                                x=105, y=100, movement=1)
        self.world.step()
        self.assertIn("water to stockpile", self.world.events[0]["message"])


if __name__ == "__main__":
    unittest.main()
