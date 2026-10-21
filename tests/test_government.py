import unittest

from simulation import World
from simulation.rules import Rules

CALM = {"hunger": 0, "sleep": 0, "thirst": 0, "boredom": 0}
NO_ASSETS = {"food": 0, "water": 0, "games": 0}
FIXED = {"price_mode": "fixed", "demand_pricing_enabled": False,
         "fixed_prices": {"food": 1, "water": 1, "games": 1, "labor": 2}}


def world_with(**rules):
    return World(seed=1, rules=Rules.from_dict({"assets": NO_ASSETS, "investing_enabled": False, **rules}))


class MinimumRateTests(unittest.TestCase):
    def test_rate_is_a_floor_under_asset_returns(self):
        world = world_with(asset_labor={"food": 1}, asset_return={"food": 0.01, "water": 0.05, "games": 0.01}, **FIXED)
        self.assertAlmostEqual(world.asset_prices()["food"], 100)     # 1 unit/step x 1 / 1%
        world.government.min_rate = 0.02
        self.assertAlmostEqual(world.asset_prices()["food"], 50)      # valued at 2% now
        self.assertAlmostEqual(world.government.effective_return(world.rules, "water"), 0.05)  # already above

    def test_rate_comes_from_the_rules(self):
        world = world_with(gov_min_rate=0.03)
        self.assertEqual(world.government.min_rate, 0.03)


class LabourPurchaseTests(unittest.TestCase):
    def test_buys_spare_labour_with_new_money(self):
        world = world_with(gov_labor_purchase=3, labor_rate=0, **FIXED)
        workers = [world.create_agent(needs=CALM, money=0, inventory={"labor": 2}) for _ in range(3)]
        world.government.buy_labor(world)
        self.assertAlmostEqual(sum(w.inventory.amount("labor") for w in workers), 3)   # 6 held, 3 bought
        self.assertAlmostEqual(sum(w.money for w in workers), 6)                       # 3 units x price 2
        self.assertAlmostEqual(world.government.money_created, 6)
        self.assertAlmostEqual(world.government.labor_bought, 3)

    def test_buys_only_what_is_on_offer(self):
        world = world_with(gov_labor_purchase=10, labor_rate=0, **FIXED)
        world.create_agent(needs=CALM, money=0, inventory={"labor": 2})
        world.government.buy_labor(world)
        self.assertAlmostEqual(world.government.labor_bought, 2)

    def test_injection_grows_the_money_supply(self):
        world = World(seed=2, rules=Rules.from_dict({"agents": 10, "gov_labor_purchase": 1}))
        world.spawn_random_agents()
        start = sum(a.money for a in world.agents)
        for _ in range(100):
            world.step()
        alive_money = sum(a.money for a in world.agents)
        self.assertGreater(world.government.money_created, 0)
        if len(world.agents) == 10:
            self.assertAlmostEqual(alive_money, start + world.government.money_created, places=6)

    def test_off_by_default(self):
        world = World(seed=2, rules=Rules.from_dict({"agents": 5}))
        world.spawn_random_agents()
        for _ in range(20):
            world.step()
        self.assertEqual((world.government.money_created, world.government.labor_bought), (0, 0))


if __name__ == "__main__":
    unittest.main()
