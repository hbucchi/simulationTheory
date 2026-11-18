import random
import statistics
import unittest

from simulation import World, economy
from simulation.distributions import allocate, normalize, sample
from simulation.rules import Rules
from tests.classic import CALM, CLASSIC


def draws(spec, n=5000, whole=False):
    rng = random.Random(1)
    return [sample(spec, rng, whole) for _ in range(n)]


def skewness(values):
    m, s = statistics.fmean(values), statistics.pstdev(values)
    return statistics.fmean(((v - m) / s) ** 3 for v in values)


class DistributionTests(unittest.TestCase):
    def test_plain_number_is_fixed(self):
        self.assertEqual(draws(7, n=3), [7, 7, 7])

    def test_uniform_stays_in_range(self):
        values = draws({"dist": "uniform", "min": 2, "max": 4})
        self.assertTrue(all(2 <= v <= 4 for v in values))
        self.assertAlmostEqual(statistics.fmean(values), 3, delta=0.05)

    def test_normal_has_requested_mean_and_std(self):
        values = draws({"dist": "normal", "mean": 50, "std": 5, "limit": 10, "skew": 0})
        self.assertAlmostEqual(statistics.fmean(values), 50, delta=0.3)
        self.assertAlmostEqual(statistics.pstdev(values), 5, delta=0.3)

    def test_normal_is_cut_at_limit_stds_and_field_bounds(self):
        values = draws({"dist": "normal", "mean": 10, "std": 5, "limit": 1, "skew": 0})
        self.assertTrue(all(5 <= v <= 15 for v in values))
        rng = random.Random(1)
        floored = [sample({"dist": "normal", "mean": 1, "std": 5, "limit": 3, "skew": 0}, rng, low=0)
                   for _ in range(2000)]
        self.assertGreaterEqual(min(floored), 0)

    def test_skew_direction_and_mean(self):
        right = draws({"dist": "normal", "mean": 50, "std": 5, "limit": 10, "skew": 5})
        left = draws({"dist": "normal", "mean": 50, "std": 5, "limit": 10, "skew": -5})
        self.assertGreater(skewness(right), 0.5)
        self.assertLess(skewness(left), -0.5)
        self.assertAlmostEqual(statistics.fmean(right), 50, delta=0.3)
        self.assertAlmostEqual(statistics.pstdev(right), 5, delta=0.3)

    def test_whole_numbers(self):
        values = draws({"dist": "normal", "mean": 8, "std": 3, "limit": 2, "skew": 0}, whole=True)
        self.assertTrue(all(isinstance(v, int) and 2 <= v <= 14 for v in values))

    def test_tiered_allocation_matches_the_tiers(self):
        spec = normalize({"dist": "tiered", "average": 100, "tiers": [
            {"agents": 1, "share": 50}, {"agents": 10, "share": 20}, {"agents": 89, "share": 30}]},
            "money", 0, 1e9, tiered=True)
        values = sorted(allocate(spec, 100, random.Random(3), whole=True), reverse=True)
        self.assertEqual(sum(values), 10000)
        self.assertEqual(values[0], 5000)              # top 1 agent holds 50%
        self.assertEqual(sum(values[1:11]), 2000)      # next 10 hold 20%
        self.assertEqual(sum(values[11:]), 3000)       # the other 89 share 30%

    def test_tiered_with_fewer_agents_than_tiers_keeps_the_total(self):
        spec = {"dist": "tiered", "average": 10, "tiers": [
            {"agents": 1, "share": 50}, {"agents": 10, "share": 20}, {"agents": 89, "share": 30}]}
        values = allocate(spec, 2, random.Random(1), whole=True)
        self.assertEqual(sum(values), 20)

    def test_tiered_single_draw_uses_tier_probabilities(self):
        spec = {"dist": "tiered", "average": 10, "tiers": [{"agents": 20, "share": 80}, {"agents": 80, "share": 20}]}
        values = draws(spec, n=4000)
        self.assertEqual(set(values), {40.0, 2.5})      # 10*80/20 and 10*20/80
        self.assertAlmostEqual(values.count(40.0) / len(values), 0.2, delta=0.03)

    def test_validation(self):
        with self.assertRaisesRegex(ValueError, "min can't be larger"):
            normalize({"dist": "uniform", "min": 5, "max": 1}, "x", 0, 10)
        with self.assertRaisesRegex(ValueError, "x.mean must be between"):
            normalize({"dist": "normal", "mean": 30, "std": 1, "limit": 3, "skew": 0}, "x", 0, 10)
        with self.assertRaisesRegex(ValueError, "dist must be one of uniform, normal$"):
            normalize({"dist": "tiered", "average": 1, "tiers": []}, "x", 0, 10)
        with self.assertRaisesRegex(ValueError, "add up to 90"):
            normalize({"dist": "tiered", "average": 1, "tiers": [{"agents": 80, "share": 50},
                                                                 {"agents": 10, "share": 50}]}, "x", 0, 10, tiered=True)
        with self.assertRaisesRegex(ValueError, "unexpected min"):
            normalize({"dist": "normal", "mean": 1, "std": 1, "min": 0}, "x", 0, 10)


class RulesTests(unittest.TestCase):
    def test_partial_rules_keep_defaults(self):
        rules = Rules.from_dict({"inventory": {"water": 5}, "rates": {"thirst": 0.02}})
        self.assertEqual(rules.inventory, {**Rules().inventory, "water": 5})
        self.assertEqual(rules.rates["hunger"], 0.01)

    def test_invalid_rules_are_rejected(self):
        for bad, message in [({"target_level": 0.6}, "target_level must be below"),
                             ({"gravity": 1}, "unknown rule"),
                             ({"price_mode": "auction"}, "price_mode must be one of"),
                             ({"death_enabled": "yes"}, "true or false"),
                             ({"labor_capacity": -1}, "between"),
                             ({"purchase_min": 3, "purchase_max": 2}, "purchase_min can't be larger"),
                             ({"labor_capacity": {"dist": "tiered", "average": 1,
                                              "tiers": [{"agents": 100, "share": 100}]}},
                              "dist must be one of uniform, normal")]:
            with self.assertRaisesRegex(ValueError, message):
                Rules.from_dict(bad)

    def test_world_draws_each_agent_from_the_spreads(self):
        rules = Rules.from_dict({
            "agents": 200,
            "labor_capacity": {"dist": "normal", "mean": 10, "std": 6, "limit": 3, "skew": 4},
            "money": {"dist": "normal", "mean": 100, "std": 20, "limit": 3, "skew": 0},
            "movement": 7,
        })
        world = World(seed=2, rules=rules)
        world.spawn_random_agents()
        labor = [a.labor_capacity for a in world.agents]
        money = [a.money for a in world.agents]
        self.assertEqual(len(world.agents), 200)
        self.assertTrue(all(0 <= x <= 28 for x in labor))   # mean 10 +- 3 std, never below 0
        self.assertGreater(len(set(labor)), 10)
        self.assertGreater(skewness(labor), 0)
        self.assertAlmostEqual(statistics.fmean(money), 100, delta=6)
        self.assertEqual({a.movement for a in world.agents}, {7})

    def test_spawn_shares_tiered_money_exactly(self):
        rules = Rules.from_dict({"agents": 10, "money": {"dist": "tiered", "average": 100, "tiers": [
            {"agents": 10, "share": 60}, {"agents": 90, "share": 40}]}})
        world = World(seed=5, rules=rules)
        world.spawn_random_agents()
        money = sorted(a.money for a in world.agents)
        self.assertEqual(money[-1], 600)
        self.assertAlmostEqual(sum(money[:-1]), 400, delta=0.1)  # 400 / 9 rounded to cents

    def test_buyer_stocks_up_between_one_and_three_times_its_need(self):
        bought = []
        for seed in range(200):
            buyer = World(seed=seed).create_agent(inventory={"water": 0}, needs={"thirst": 0.8}, money=1000)
            seller = World(seed=seed).create_agent(inventory={"water": 1000}, needs={"thirst": 0})
            economy.buy(buyer, seller, {"food": 1, "water": 1, "games": 1}, Rules.from_dict({"selling_enabled": False}), random.Random(seed))
            bought.append(buyer.inventory.count("water"))
        need = economy.units_to_satisfy(0.8)          # 6
        self.assertTrue(all(need <= b <= 3 * need for b in bought))
        self.assertGreater(len(set(bought)), 5)

    def test_purchase_is_capped_by_money_and_seller_spare(self):
        buyer = World(seed=1).create_agent(inventory={"water": 0, "food": 0, "games": 0}, needs={"thirst": 0.8},
                                           money=4)  # nothing else to barter with
        seller = World(seed=1).create_agent(inventory={"water": 1000}, needs={"thirst": 0})
        economy.buy(buyer, seller, {"food": 1, "water": 1, "games": 1}, Rules.from_dict({"selling_enabled": False}), random.Random(1))
        self.assertEqual(buyer.inventory.count("water"), 4)

    def test_world_rules_change_mechanics(self):
        rules = Rules.from_dict({"price_mode": "fixed", "fixed_prices": {"water": 4},
                                 "death_enabled": False, "depression_enabled": False,
                                 "relief_per_unit": 0.2})
        world = World(seed=1, rules=rules)
        agent = world.create_agent(inventory={"food": 0, "water": 0}, needs={"thirst": 0.99}, x=0, y=0)
        world.create_agent(x=900, y=900)
        for _ in range(5):
            world.step()
        self.assertIn(agent, world.agents)                    # no death
        self.assertEqual(economy.market_prices(world.agents, rules)["water"], 4)
        self.assertNotIn("Mood", agent.to_dict()["modules"])  # no depression
        self.assertEqual(economy.units_to_satisfy(0.7, rules), 3)  # 0.2 per unit: 0.7 -> 0.1


if __name__ == "__main__":
    unittest.main()
