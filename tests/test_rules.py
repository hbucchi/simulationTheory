import random
import statistics
import unittest

from simulation import World, economy
from simulation.distributions import normalize, sample
from simulation.rules import Rules


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
        values = draws({"dist": "normal", "min": 0, "max": 100, "mean": 50, "std": 5})
        self.assertAlmostEqual(statistics.fmean(values), 50, delta=0.3)
        self.assertAlmostEqual(statistics.pstdev(values), 5, delta=0.3)

    def test_normal_is_truncated_at_min_and_max(self):
        values = draws({"dist": "normal", "min": 9, "max": 11, "mean": 10, "std": 5})
        self.assertTrue(all(9 <= v <= 11 for v in values))

    def test_skew_direction_and_mean(self):
        right = draws({"dist": "skewed", "min": 0, "max": 100, "mean": 50, "std": 5, "skew": 5})
        left = draws({"dist": "skewed", "min": 0, "max": 100, "mean": 50, "std": 5, "skew": -5})
        self.assertGreater(skewness(right), 0.5)
        self.assertLess(skewness(left), -0.5)
        self.assertAlmostEqual(statistics.fmean(right), 50, delta=0.3)
        self.assertAlmostEqual(statistics.pstdev(right), 5, delta=0.3)

    def test_whole_numbers(self):
        values = draws({"dist": "normal", "min": 3, "max": 12, "mean": 8, "std": 3}, whole=True)
        self.assertTrue(all(isinstance(v, int) and 3 <= v <= 12 for v in values))

    def test_validation(self):
        with self.assertRaisesRegex(ValueError, "min can't be larger"):
            normalize({"dist": "uniform", "min": 5, "max": 1}, "x", 0, 10)
        with self.assertRaisesRegex(ValueError, "x.mean must be between"):
            normalize({"dist": "normal", "min": 0, "max": 1, "mean": 3, "std": 1}, "x", 0, 10)
        with self.assertRaisesRegex(ValueError, "dist must be one of"):
            normalize({"dist": "poisson", "min": 0, "max": 1}, "x", 0, 10)
        with self.assertRaisesRegex(ValueError, "unexpected skew"):
            normalize({"dist": "normal", "min": 0, "max": 1, "mean": 0.5, "std": 1, "skew": 2}, "x", 0, 10)


class RulesTests(unittest.TestCase):
    def test_partial_rules_keep_defaults(self):
        rules = Rules.from_dict({"inventory": {"water": 5}, "rates": {"thirst": 0.02}})
        self.assertEqual(rules.inventory, {"food": 100, "water": 5, "games": 100})
        self.assertEqual(rules.rates["hunger"], 0.01)

    def test_invalid_rules_are_rejected(self):
        for bad, message in [({"target_level": 0.6}, "target_level must be below"),
                             ({"gravity": 1}, "unknown rule"),
                             ({"price_mode": "auction"}, "price_mode must be one of"),
                             ({"death_enabled": "yes"}, "true or false"),
                             ({"production": {"food": 2.5}}, "whole number")]:
            with self.assertRaisesRegex(ValueError, message):
                Rules.from_dict(bad)

    def test_world_draws_each_agent_from_the_spreads(self):
        rules = Rules.from_dict({
            "agents": 200,
            "production": {"water": {"dist": "skewed", "min": 2, "max": 40, "mean": 10, "std": 6, "skew": 4}},
            "money": {"dist": "normal", "min": 0, "max": 1000, "mean": 100, "std": 20},
            "movement": 7,
        })
        world = World(seed=2, rules=rules)
        world.spawn_random_agents()
        water = [a.modules[2].intervals["water"] for a in world.agents]
        money = [a.money for a in world.agents]
        self.assertEqual(len(world.agents), 200)
        self.assertTrue(all(2 <= w <= 40 for w in water))
        self.assertGreater(len(set(water)), 10)
        self.assertGreater(skewness(water), 0)
        self.assertAlmostEqual(statistics.fmean(money), 100, delta=6)
        self.assertEqual({a.movement for a in world.agents}, {7})

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
