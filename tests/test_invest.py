import unittest

from simulation import World
from simulation.modules import Invest
from simulation.modules.invest import best_asset
from simulation.rules import Rules

CALM = {"hunger": 0, "sleep": 0, "thirst": 0, "boredom": 0}
NO_NEEDS = {"hunger": 0, "sleep": 0, "thirst": 0, "boredom": 0}
FIXED = {"price_mode": "fixed", "demand_pricing_enabled": False, "fixed_prices": {"food": 1, "water": 1, "games": 1}}


def world_with(**rules):
    return World(seed=1, rules=Rules.from_dict(rules))


class AssetValueTests(unittest.TestCase):
    def test_value_grows_by_the_rate_over_the_period(self):
        world = world_with(asset_growth={"food": 0.05}, asset_growth_steps=50)
        for _ in range(50):
            world.grow_assets()
        self.assertAlmostEqual(world.asset_value["food"], 105)
        for _ in range(50):
            world.grow_assets()
        self.assertAlmostEqual(world.asset_value["food"], 110.25)  # compounding

    def test_output_is_value_times_return(self):
        world = world_with()
        self.assertAlmostEqual(world.asset_output("food", 1), 1)       # worth 100 at 1%
        self.assertAlmostEqual(world.asset_output("food", 0.5), 0.5)
        world.asset_value["food"] = 105
        self.assertAlmostEqual(world.asset_output("food", 1), 1.05)

    def test_assets_produce_units_each_step(self):
        world = world_with(investing_enabled=False, asset_growth={"food": 0, "water": 0, "games": 0})
        agent = world.create_agent(inventory={"food": 0, "water": 0, "games": 0}, needs=CALM, rates=NO_NEEDS,
                                   production={"food": 0, "water": 0, "games": 0}, assets={"food": 0.5})
        for _ in range(10):
            world.step()
        self.assertEqual(agent.inventory.count("food"), 5)            # 0.5 unit per step
        self.assertEqual(agent.inventory.count("water"), 0)

    def test_growing_value_raises_output(self):
        world = world_with(investing_enabled=False, asset_growth={"food": 0.05}, asset_growth_steps=50)
        agent = world.create_agent(inventory={"food": 0, "water": 0, "games": 0}, needs=CALM, rates=NO_NEEDS,
                                   production={"food": 0, "water": 0, "games": 0}, assets={"food": 1})
        for _ in range(100):
            world.step()
        # Output climbs from ~1.0 to ~1.1 per step: about 105 units over 100 steps (not 100).
        self.assertIn(agent.inventory.count("food"), range(104, 107))


class InvestTests(unittest.TestCase):
    def test_keeps_cash_and_invests_the_rest_as_shares(self):
        world = world_with(liquidity_units=3, builder_payout_rate=0, **FIXED)
        agent = world.create_agent(money=100, needs=CALM, x=0, y=0)
        Invest().on_step(agent, world)
        # Keeps 3 x (1+1+1) = 9; 91 buys 0.91 of a 100-value asset.
        self.assertAlmostEqual(sum(agent.assets.values()), 0.91)
        self.assertAlmostEqual(agent.money, 9)
        self.assertAlmostEqual(world.builder_funds, 91)
        self.assertIn("0.91 new from the builder", world.events[-1]["message"])

    def test_waits_until_the_minimum_investment_is_spare(self):
        world = world_with(liquidity_units=3, min_investment=10, **FIXED)
        agent = world.create_agent(money=18, needs=CALM)
        Invest().on_step(agent, world)
        self.assertEqual(agent.assets, {})

    def test_best_asset_counts_output_value_and_growth(self):
        world = world_with(price_mode="fixed", demand_pricing_enabled=False,
                           fixed_prices={"food": 1, "water": 3, "games": 1},
                           asset_growth={"food": 0, "water": 0, "games": 0.5})
        prices = world.current_prices()
        # food 0.01 x 1 = 0.010/step; water 0.01 x 3 = 0.030/step; games 0.01 + growth 1.5^(1/50)-1 = 0.018.
        self.assertEqual(best_asset(prices, world), "water")
        world.rules.asset_growth["games"] = 3   # x4 in 50 steps: ~0.028 + 0.01 growth/output
        self.assertEqual(best_asset(prices, world), "games")

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
        # Fixed prices 1 each -> liquidity 3 x 3 = 9 money; one asset is worth 100.
        return world_with(liquidity_units=3, builder_payout_rate=0, **FIXED)

    def test_starting_assets_follow_the_rules_distribution(self):
        world = world_with(agents=10, investing_enabled=False, assets={"water": {
            "dist": "tiered", "average": 0.5, "tiers": [{"agents": 10, "share": 60}, {"agents": 90, "share": 40}]}})
        world.spawn_random_agents()
        water = sorted(a.assets.get("water", 0) for a in world.agents)
        self.assertAlmostEqual(water[-1], 3)          # top 10% (1 agent) holds 60% of 5 assets
        self.assertAlmostEqual(sum(water), 5)

    def test_investor_buys_from_cash_short_owners_and_pays_them(self):
        world = self.market()
        investor = world.create_agent(money=49, needs=CALM, x=0, y=0)
        poor = world.create_agent(money=0, needs=CALM, assets={"food": 1}, x=900, y=900)
        rich = world.create_agent(money=500, needs=CALM, assets={"food": 1}, x=500, y=900)
        Invest().on_step(investor, world)
        # 40 spare. The poor owner is 9 short: sells 0.09 for 9; the other 31 buy 0.31 new.
        self.assertAlmostEqual(investor.assets["food"], 0.40)
        self.assertAlmostEqual(poor.assets["food"], 0.91)
        self.assertAlmostEqual(poor.money, 9)
        self.assertEqual(rich.assets["food"], 1)      # has plenty of cash: doesn't sell
        self.assertAlmostEqual(world.builder_funds, 31)
        self.assertIn("0.09 from", world.events[-1]["message"])

    def test_shares_are_conserved_in_resales(self):
        world = self.market()
        investor = world.create_agent(money=39, needs=CALM)
        sellers = [world.create_agent(money=0, needs=CALM, assets={"food": 0.5}) for _ in range(3)]
        Invest().on_step(investor, world)
        # 30 spare buys 0.09 from each seller (27) and 0.03 new.
        self.assertAlmostEqual(investor.assets["food"], 0.30)
        self.assertAlmostEqual(sum(s.assets["food"] for s in sellers), 1.5 - 0.27)
        self.assertAlmostEqual(world.builder_funds, 3)


if __name__ == "__main__":
    unittest.main()
