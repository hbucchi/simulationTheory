import unittest

from simulation import World, economy
from simulation.modules import Invest
from simulation.modules.invest import purchase_limit
from simulation.rules import GOODS, Rules
from tests.classic import CALM, CLASSIC

NO_ASSETS = {g: 0 for g in GOODS}
FIXED = {"price_mode": "fixed", "demand_pricing_enabled": False, "fixed_prices": {"food": 1, "water": 1, "games": 1, "labor": 1}}


def world_with(**rules):
    # No labour-saving unless a test asks for it: these tests are about output and prices.
    return World(seed=1, rules=Rules.from_dict({**CLASSIC, "assets": NO_ASSETS, "labor_saving": {"food": 0, "water": 0, "games": 0},
                                                **rules}))


class AssetTests(unittest.TestCase):
    def test_productivity_grows_by_the_rate_over_the_period(self):  # labour per asset fixed here  # labour per asset fixed here
        world = world_with(asset_labor={"food": 1}, productivity_growth={"food": 0.05}, productivity_growth_steps=50)
        for _ in range(50):
            world.grow_assets()
        self.assertAlmostEqual(world.asset_output("food", 1), 1.05)
        for _ in range(50):
            world.grow_assets()
        self.assertAlmostEqual(world.asset_output("food", 1), 1.1025)     # compounding
        self.assertAlmostEqual(world.asset_output("food", 0.5), 0.55125)

    def test_asset_price_is_profit_over_return(self):
        world = world_with(asset_labor={"food": 1}, asset_return={"food": 0.01}, price_mode="fixed",
                           demand_pricing_enabled=False, fixed_prices={"food": 1, "water": 1, "games": 1, "labor": 0.5})
        world.labor.clear(world)                                          # sets the wage (fixed at 0.5)
        self.assertAlmostEqual(world.asset_prices()["food"], 50)          # (1 x 1 - 1 x 0.5) / 1%
        world.rules.fixed_prices["food"] = 2
        self.assertAlmostEqual(world.asset_prices()["food"], 150)         # good dearer -> asset dearer
        for _ in range(50):
            world.grow_assets()
        self.assertAlmostEqual(world.asset_prices()["food"], 160)         # productivity +5%: 1.05 x 2 - 0.5
        world.rules.fixed_prices["labor"] = 5
        world.labor.clear(world)
        self.assertEqual(world.asset_prices()["food"], 0)                  # loses money: worth nothing

    def test_assets_produce_units_each_step(self):
        world = world_with(investing_enabled=False, selling_enabled=False, asset_labor={"food": 0.5},
                           productivity_growth={"food": 0, "water": 0, "games": 0})
        agent = world.create_agent(inventory=NO_ASSETS, needs=CALM, rates=CALM, labor_capacity=1,
                                   assets={"food": 1})
        for _ in range(10):
            world.step()
        self.assertEqual(agent.inventory.count("food"), 5)            # its own labour: 0.5 unit per step
        self.assertEqual(agent.inventory.count("water"), 0)

    def test_assets_need_labour(self):
        world = world_with(investing_enabled=False, selling_enabled=False, asset_labor={"food": 1},
                           productivity_growth={"food": 0, "water": 0, "games": 0})
        idle = world.create_agent(inventory={"food": 0}, needs=CALM, rates=CALM, labor_capacity=0, money=0,
                                  assets={"food": 1})
        half = world.create_agent(inventory={"food": 0}, needs=CALM, rates=CALM, labor_capacity=0.5, money=0,
                                  assets={"food": 1})
        for _ in range(10):
            world.step()
        self.assertEqual(idle.inventory.count("food"), 0)      # no labour (and no money to hire): no output
        self.assertEqual(half.inventory.count("food"), 5)      # half the labour its asset can employ
        self.assertEqual(half.labor_need, 1)

    def test_productivity_raises_output_per_labour(self):
        world = world_with(investing_enabled=False, selling_enabled=False, asset_labor={"food": 1},
                           productivity={"food": 2}, productivity_growth={"food": 0, "water": 0, "games": 0})
        agent = world.create_agent(inventory={"food": 0}, needs=CALM, rates=CALM, labor_capacity=1,
                                   assets={"food": 1})
        for _ in range(5):
            world.step()
        self.assertEqual(agent.inventory.count("food"), 10)    # 5 labour x productivity 2

    def test_starting_assets_follow_the_rules_distribution(self):
        world = World(seed=1, rules=Rules.from_dict({"agents": 10, "investing_enabled": False, "asset_owner_share": 1, "assets": {"water": {
            "dist": "tiered", "average": 0.5, "tiers": [{"agents": 10, "share": 60}, {"agents": 90, "share": 40}]}}}))
        world.spawn_random_agents()
        water = sorted(a.assets.get("water", 0) for a in world.agents)
        self.assertAlmostEqual(water[-1], 3)          # top 10% (1 agent) holds 60% of 5 assets
        self.assertAlmostEqual(sum(water), 5)


class InvestTests(unittest.TestCase):
    def market(self):
        # Prices 1 -> liquidity 3 x 3 = 9 money; a whole food asset (1 unit/step at 1%) costs 100.
        return world_with(liquidity_units=3, min_investment=10, asset_labor={"food": 1, "water": 1, "games": 1}, **FIXED)

    def test_buys_only_from_cash_short_owners_and_pays_them(self):
        world = self.market()
        investor = world.create_agent(money=49, needs=CALM, inventory={"food": 10}, x=0, y=0)
        poor = world.create_agent(money=0, needs=CALM, assets={"food": 1}, x=900, y=900)
        rich = world.create_agent(money=500, needs=CALM, assets={"food": 1}, x=500, y=900)
        Invest().on_step(investor, world)
        # Cash kept: 3 units of food, water and games at 1 = 9. 40 spare, but the only
        # seller is 9 short: it sells 0.09 for 9. Nothing is created.
        self.assertAlmostEqual(investor.assets["food"], 0.09)
        self.assertAlmostEqual((poor.assets["food"], poor.money), (0.91, 9))
        self.assertAlmostEqual(investor.money, 40)
        self.assertEqual(rich.assets["food"], 1)
        self.assertAlmostEqual(sum(a.assets.get("food", 0) for a in world.agents), 2)   # still 2 assets
        self.assertIn("0.09 from", world.events[-1]["message"])

    def test_no_seller_means_no_purchase(self):
        world = self.market()
        investor = world.create_agent(money=100, needs=CALM, inventory={"food": 10})
        world.create_agent(money=500, needs=CALM, assets={"food": 1})
        Invest().on_step(investor, world)
        self.assertEqual(investor.assets, {})
        self.assertEqual(investor.money, 100)

    def test_owner_over_the_cap_sells_part_of_those_assets(self):
        world = self.market()
        investor = world.create_agent(money=200, needs=CALM, inventory={"food": 20, "water": 60, "games": 60})
        full = world.create_agent(money=500, needs=CALM, assets={"food": 1}, inventory={"food": 300})
        Invest().on_step(investor, world)
        # Food is 1/unit and the asset makes 1 food/step at 1% -> 100 per asset; sells 25%.
        self.assertAlmostEqual(investor.assets["food"], 0.25)
        self.assertAlmostEqual(full.assets["food"], 0.75)
        self.assertAlmostEqual(full.money, 525)

    def test_considers_every_industry_not_only_what_it_uses(self):
        world = self.market()
        world.create_agent(money=500, needs=CALM, assets={"food": 1}, inventory={"food": 300})
        # Plenty of food of its own: it still buys food assets when they are the best on offer.
        investor = world.create_agent(money=200, needs=CALM, inventory={"food": 300, "water": 60, "games": 60})
        Invest().on_step(investor, world)
        self.assertGreater(investor.assets.get("food", 0), 0)

    def test_prefers_the_asset_with_the_best_return(self):
        world = world_with(liquidity_units=3, min_investment=10, asset_return={"food": 0.01, "water": 0.02, "games": 0.01},
                           **FIXED)
        investor = world.create_agent(money=100, needs=CALM, inventory={"food": 10, "water": 10})
        world.create_agent(money=0, needs=CALM, assets={"food": 1, "water": 1})
        Invest().on_step(investor, world)
        self.assertIn("water", investor.assets)
        self.assertNotIn("food", investor.assets)

    def test_money_and_assets_are_conserved(self):
        # Building turns capital goods into new shares, so it is off here (and plants don't wear out).
        world = World(seed=2, rules=Rules.from_dict({"agents": 15, "building_enabled": False,
                                                     "depreciation": {g: 0 for g in GOODS}}))
        world.spawn_random_agents()
        money = sum(a.money for a in world.agents)
        assets = {r: sum(a.assets.get(r, 0) for a in world.agents) for r in economy.RESOURCES}
        for _ in range(300):
            world.step()
        if len(world.agents) == 15:   # nobody died (deaths remove money and assets)
            # Base money: agents' cash plus banks' cash (deposits and loans only move it).
            base = world.base_money()
            self.assertAlmostEqual(base, money, places=6)
            for r in economy.RESOURCES:
                self.assertAlmostEqual(sum(a.assets.get(r, 0) for a in world.agents), assets[r], places=6)


class StockBandTests(unittest.TestCase):
    # Thirst grows 0.01/step and the band covers 1000 steps: a cap of 10 relief = 100 water.
    rules = Rules.from_dict({**CLASSIC, "stock_steps": 1000, "restock_below": 0.5})

    def agent(self, water):
        return World(seed=1, rules=self.rules).create_agent(inventory={"water": water}, needs=CALM,
                                                            rates={"thirst": 0.01})

    def test_above_the_cap_is_surplus_to_sell(self):
        self.assertEqual(economy.surplus(self.agent(140), "water", self.rules), 40)
        self.assertEqual(economy.surplus(self.agent(90), "water", self.rules), 0)
        self.assertEqual(economy.surplus(self.agent(140), "water", Rules.from_dict({**CLASSIC, "selling_enabled": False})), 0)

    def test_below_the_floor_restocks_up_to_the_cap(self):
        self.assertEqual(economy.restock_shortfall(self.agent(40), "water", self.rules), 60)
        self.assertEqual(economy.restock_shortfall(self.agent(60), "water", self.rules), 0)   # inside the band

    def test_never_sells_below_the_floor(self):
        self.assertEqual(economy.spare(self.agent(70), "water", self.rules), 20)

    def test_restocking_buys_up_to_the_cap_with_money(self):
        rules = Rules.from_dict({**CLASSIC, "stock_steps": 1000, "restock_below": 0.5, "stockpile_budget": 1})
        rates = {"hunger": 0.01, "thirst": 0.01, "boredom": 0.01}
        buyer = World(seed=1, rules=rules).create_agent(inventory={"water": 40, "food": 100, "games": 100},
                                                        needs=CALM, rates=rates, money=100)
        seller = World(seed=1, rules=rules).create_agent(inventory={"water": 200}, needs=CALM, rates=rates)
        bought, paid, stocked, _ = economy.buy(buyer, seller, {"food": 1, "water": 1, "games": 1}, rules)
        self.assertEqual(bought, {"water": 60})
        self.assertEqual(paid, {"money": 60})          # money only, no food bartered away
        self.assertEqual(seller.inventory.count("water"), 140)

    def test_agent_with_surplus_goes_to_a_buyer(self):
        world = world_with(investing_enabled=False)
        seller = world.create_agent(inventory={"water": 500, "food": 60, "games": 60}, needs=CALM, x=100, y=100,
                                    movement=5)
        buyer = world.create_agent(inventory={"water": 10, "food": 60, "games": 60}, needs=CALM, money=100, x=900, y=100, movement=1)
        world.step()
        self.assertEqual((seller.activity, seller.target_id, seller.seeking_for), ("selling", buyer.id, "water"))
        self.assertEqual((buyer.activity, buyer.seeking_for), ("restocking", "water"))


class CapitalistCashTests(unittest.TestCase):
    def test_purchase_limit_keeps_cash_to_assets_ratio(self):
        agent = World(seed=1).create_agent(money=1000, assets={"food": 2, "water": 0, "games": 0})
        prices = {"food": 100.0, "water": 100.0, "games": 100.0}      # holds assets worth 200
        # ratio 0.5: spends x so that 1000 - x >= 0.5 * (200 + x)  ->  x = 600
        self.assertAlmostEqual(purchase_limit(agent, prices, 0.5), 600)
        self.assertAlmostEqual(purchase_limit(agent, prices, 0), 1000)      # no rule: all the cash
        agent.money = 50
        self.assertEqual(purchase_limit(agent, prices, 1), 0)               # too little cash to buy any

    def test_higher_ratio_means_fewer_asset_purchases(self):
        def trades(ratio):
            world = World(seed=3, rules=Rules.from_dict({"agents": 20, "capital_cash_ratio": ratio}))
            world.spawn_random_agents()
            for _ in range(150):
                world.step()
            return world.asset_trades
        self.assertGreaterEqual(trades(0), trades(5))


if __name__ == "__main__":
    unittest.main()
