import unittest

from simulation import World, labor
from simulation.rules import Rules

CALM = {"hunger": 0, "sleep": 0, "thirst": 0, "boredom": 0}
NO_ASSETS = {"food": 0, "water": 0, "games": 0}
STATIC = {"labor_saving": {"food": 0, "water": 0, "games": 0},
          "productivity_growth": {"food": 0, "water": 0, "games": 0}}
FIXED = {"price_mode": "fixed", "demand_pricing_enabled": False,
         "fixed_prices": {"food": 10, "water": 10, "games": 10, "labor": 5}}


def world_with(**rules):
    return World(seed=1, rules=Rules.from_dict({"assets": NO_ASSETS, "investing_enabled": False,
                                                "selling_enabled": False, **STATIC, **rules}))


class CapacityModuleTests(unittest.TestCase):
    def test_efficiency_falls_with_needs_and_depression(self):
        rules = Rules()
        agent = World(seed=1).create_agent(needs=CALM)
        self.assertEqual(labor.efficiency(agent, rules), 1)
        agent.hunger, agent.thirst = 0.5, 0.5                      # 1 - 0.3*0.5 - 0.3*0.5
        self.assertAlmostEqual(labor.efficiency(agent, rules), 0.7)
        agent.depressed = True                                      # - 0.3
        self.assertAlmostEqual(labor.efficiency(agent, rules), 0.4)
        agent.hunger = agent.thirst = agent.sleep = agent.boredom = 1
        self.assertEqual(labor.efficiency(agent, rules), rules.min_efficiency)

    def test_wellbeing(self):
        rules = Rules()
        agent = World(seed=1).create_agent(needs=CALM)
        self.assertEqual(labor.wellbeing(agent, rules), 1)
        agent.hunger = agent.thirst = agent.sleep = agent.boredom = 0.5
        self.assertAlmostEqual(labor.wellbeing(agent, rules), 0.5)

    def test_general_need_grows_when_short_of_money_or_in_need(self):
        rules = Rules.from_dict({"money_weight": 0.5, "comfort_steps": 10})
        prices = {"food": 10, "water": 10, "games": 10}
        world = World(seed=1)
        agent = world.create_agent(needs=CALM, money=1e6, rates={"hunger": 0.01, "thirst": 0, "boredom": 0, "sleep": 0})
        self.assertAlmostEqual(labor.general_need(agent, prices, rules), 0)
        agent.money = 0                                               # broke: money part is 1
        self.assertAlmostEqual(labor.general_need(agent, prices, rules), 0.5)
        agent.thirst = 0.8                                            # and thirsty
        self.assertAlmostEqual(labor.general_need(agent, prices, rules), 0.9)


class LabourMarketTests(unittest.TestCase):
    def owner_and_workers(self, workers, **rules):
        # Everyone offers all their free capacity unless a test says otherwise, so only the
        # asking wage decides who is hired. Workers have normal needs (a cost of living).
        world = world_with(asset_labor={"food": 1}, **{"participation_floor": 1, **rules})
        owner = world.create_agent(needs=CALM, rates=CALM, money=1e6, labor_capacity=0, assets={"food": 3},
                                   inventory={"food": 0})
        crew = [world.create_agent(needs=CALM, money=0, labor_capacity=1) for _ in range(workers)]
        return world, owner, crew

    def test_owner_uses_its_own_labour_first(self):
        world = world_with(asset_labor={"food": 1})
        owner = world.create_agent(needs=CALM, rates=CALM, labor_capacity=1, assets={"food": 1}, inventory={"food": 0})
        world.labor.clear(world)
        self.assertEqual((owner.labor_available, owner.labor_bought), (1, 0))

    def test_employer_hires_the_cheapest_workers_and_pays_cash(self):
        world, owner, crew = self.owner_and_workers(4, **FIXED)
        crew[0].money = 1e6                              # comfortable: offers little, asks more
        world.labor.clear(world)
        self.assertAlmostEqual(owner.labor_available, 3)
        self.assertEqual(crew[0].labor_sold, 0)         # the dearest worker is the one left out
        paid = sum(w.money for w in crew[1:])
        self.assertAlmostEqual(owner.money, 1e6 - paid)
        self.assertGreater(paid, 0)
        world.step()
        self.assertEqual(owner.inventory.count("food"), 3)   # 3 labour x productivity 1

    def test_unsold_capacity_is_lost(self):
        world, owner, crew = self.owner_and_workers(6, **FIXED)
        world.labor.clear(world)
        stats = world.labor.stats
        self.assertAlmostEqual(stats["hired"], 3)
        self.assertAlmostEqual(stats["unused"], stats["capacity"] - 3)
        world.labor.clear(world)                         # nothing carries over to the next step
        self.assertAlmostEqual(stats["capacity"], world.labor.stats["capacity"])

    def test_more_capacity_for_the_same_jobs_lowers_the_wage(self):
        wages = {}
        for workers in (15, 25):
            world, owner, crew = self.owner_and_workers(workers, price_adjust_speed=1)
            owner.assets["food"] = 15
            world.labor.clear(world)
            wages[workers] = world.labor.multiplier
        self.assertLess(wages[25], wages[15])

    def test_needy_workers_offer_more_and_ask_less(self):
        world, owner, crew = self.owner_and_workers(2, participation_floor=0.2, **FIXED)
        rich, poor = crew
        rich.money = 1e6
        world.labor.clear(world)
        self.assertGreater(poor.offered, rich.offered)
        self.assertLess(poor.asking_wage, rich.asking_wage)

    def test_government_hires_leftover_capacity_with_new_money(self):
        world, owner, crew = self.owner_and_workers(5, gov_labor_purchase=1, **FIXED)
        money_before = sum(a.money for a in world.agents)
        world.labor.clear(world)
        self.assertAlmostEqual(world.labor.stats["gov_hired"], 1)
        self.assertAlmostEqual(sum(a.money for a in world.agents) - money_before, world.government.last_spent)
        self.assertGreater(world.government.money_created, 0)


class LabourSavingTests(unittest.TestCase):
    def test_industries_need_less_labour_per_asset_over_time(self):
        world = World(seed=1, rules=Rules.from_dict({"asset_labor": {"food": 1}, "labor_saving": {"food": 0.03},
                                                     "productivity_growth": {"food": 0.05}, "productivity_growth_steps": 50}))
        for _ in range(50):
            world.grow_assets()
        self.assertAlmostEqual(world.asset_jobs("food", 1), 0.97)
        self.assertAlmostEqual(world.asset_output("food", 1), 0.97 * 1.05)   # more output, less labour


if __name__ == "__main__":
    unittest.main()
