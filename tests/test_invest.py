import unittest

from simulation import World
from simulation.modules import Invest
from simulation.modules.invest import best_asset
from simulation.rules import Rules

CALM = {"hunger": 0, "sleep": 0, "thirst": 0, "boredom": 0}
NO_NEEDS = {"hunger": 0, "sleep": 0, "thirst": 0, "boredom": 0}


def world_with(**rules):
    return World(seed=1, rules=Rules.from_dict(rules))


class ProductionBoostTests(unittest.TestCase):
    def test_assets_raise_output_by_their_return(self):
        world = world_with(investing_enabled=False)
        agent = world.create_agent(inventory={"food": 0, "water": 0, "games": 0}, needs=CALM, rates=NO_NEEDS,
                                   production={"food": 10, "water": 10, "games": 0}, assets={"food": 10})
        for _ in range(1000):
            world.step()
        self.assertEqual(agent.inventory.count("water"), 100)   # no assets: 1 per 10 steps
        self.assertEqual(agent.inventory.count("food"), 110)    # 10 assets x 1% = 10% faster


class InvestTests(unittest.TestCase):
    def test_keeps_liquidity_and_invests_the_rest(self):
        world = world_with(price_mode="fixed", fixed_prices={"food": 2, "water": 2, "games": 2},
                           demand_pricing_enabled=False, liquidity_units=3)
        agent = world.create_agent(money=100, needs=CALM, x=0, y=0)
        world.step()
        # Liquidity 3 x (2+2+2) = 18; 82 spare buys 8 assets at 10, leaving 20 (plus the builder's payout).
        self.assertEqual(sum(agent.assets.values()), 8)
        self.assertAlmostEqual(agent.money, 20)
        self.assertIn("bought 8", world.events[0]["message"])

    def test_buys_the_asset_with_the_best_income_per_money(self):
        world = world_with(price_mode="fixed", fixed_prices={"food": 1, "water": 3, "games": 1},
                           demand_pricing_enabled=False)
        agent = world.create_agent(production={"food": 5, "water": 10, "games": 0})
        prices = world.current_prices()
        # food: 0.01/5*1 = 0.002 per step; water: 0.01/10*3 = 0.003 per step; games: not produced.
        self.assertEqual(best_asset(agent, prices, world.rules), "water")
        agent.modules[2].intervals.update({"food": 0, "water": 0})
        self.assertIsNone(best_asset(agent, prices, world.rules))

    def test_builder_pays_back_evenly_and_money_is_conserved(self):
        world = world_with(agents=10, builder_payout_rate=0.1)
        world.spawn_random_agents()
        total = sum(a.money for a in world.agents)
        world.step()
        self.assertGreater(world.builder_funds, 0)
        for _ in range(200):
            world.step()
            self.assertAlmostEqual(sum(a.money for a in world.agents) + world.builder_funds, total, places=6)
        self.assertGreater(world.builder_paid_out, 0)

    def test_disabled_means_no_assets(self):
        world = world_with(agents=5, investing_enabled=False)
        world.spawn_random_agents()
        for _ in range(20):
            world.step()
        self.assertEqual(sum(sum(a.assets.values()) for a in world.agents), 0)
        self.assertEqual(world.builder_funds, 0)



class AssetMarketTests(unittest.TestCase):
    def market(self):
        # Fixed prices 1 each -> liquidity 3 x 3 = 9 money; assets cost 10.
        return world_with(price_mode="fixed", demand_pricing_enabled=False, liquidity_units=3,
                          fixed_prices={"food": 1, "water": 1, "games": 1}, builder_payout_rate=0)

    def test_starting_assets_follow_the_rules_distribution(self):
        world = world_with(agents=10, investing_enabled=False, assets={"water": {
            "dist": "tiered", "average": 5, "tiers": [{"agents": 10, "share": 60}, {"agents": 90, "share": 40}]}})
        world.spawn_random_agents()
        water = sorted(a.assets.get("water", 0) for a in world.agents)
        self.assertEqual((water[-1], sum(water)), (30, 50))   # top 10% (1 agent) holds 60% of 50

    def test_investor_buys_from_cash_short_owners_and_pays_them(self):
        world = self.market()
        investor = world.create_agent(money=49, needs=CALM, production={"water": 10, "food": 0, "games": 0}, x=0, y=0)
        poor = world.create_agent(money=0, needs=CALM, assets={"water": 5}, x=900, y=900)
        rich = world.create_agent(money=500, needs=CALM, assets={"water": 5}, production={"water": 0, "food": 0, "games": 0},
                                  x=500, y=900)
        Invest().on_step(investor, world)
        # 40 spare -> 4 assets. The poor owner sells only until it has 9 (its liquidity): 1 sale.
        self.assertEqual(investor.assets["water"], 4)
        self.assertEqual((poor.assets["water"], poor.money), (4, 10))
        self.assertEqual(rich.assets["water"], 5)                 # has plenty of cash: doesn't sell
        self.assertEqual((world.asset_resales, world.builder_funds), (1, 30))
        self.assertIn("1 from", world.events[-1]["message"])
        self.assertIn("3 new from the builder", world.events[-1]["message"])

    def test_assets_are_conserved_in_resales(self):
        world = self.market()
        investor = world.create_agent(money=29, needs=CALM, production={"water": 10, "food": 0, "games": 0})
        sellers = [world.create_agent(money=0, needs=CALM, assets={"water": 1}) for _ in range(3)]
        Invest().on_step(investor, world)
        self.assertEqual(investor.assets["water"], 2)             # 20 spare -> 2, both resales
        self.assertEqual(sum(s.assets.get("water", 0) for s in sellers), 1)
        self.assertEqual(world.builder_funds, 0)


if __name__ == "__main__":
    unittest.main()
