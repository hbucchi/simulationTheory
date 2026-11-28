"""The central bank's Taylor rule: rate = neutral + inflation + 0.5 (inflation - target) + 0.5 gap,
the gap from unemployment (Okun's law), set monthly, within 0-20% a year."""
import unittest

from simulation import World
from simulation.rules import Rules


class TaylorTests(unittest.TestCase):
    def world(self, inflation, unemployment, **rules):
        w = World(seed=1, rules=Rules.from_dict({"agents": 5, "taylor_smoothing": 0, **rules}))
        w.spawn_random_agents()
        w.step()
        last = w.recorder.history[-1]
        last.update(inflation=inflation, inflation_policy=inflation, accounts_steps=200)
        for s in w.recorder.history:
            s["unemployment"] = unemployment
        return w

    def rate_year(self, w):
        return (1 + w.government.min_rate) ** w.year_steps() - 1

    def test_high_inflation_raises_the_rate(self):
        w = self.world(inflation=0.10, unemployment=0.05)
        w.government.monthly(w)
        # 2% + 10% + 0.5 x 8% + 0 = 16%
        self.assertAlmostEqual(self.rate_year(w), 0.16, places=6)

    def test_the_rate_moves_gradually_with_smoothing(self):
        w = self.world(inflation=0.10, unemployment=0.05, taylor_smoothing=0.75)
        w.government.monthly(w)
        # From 0%: a quarter of the way to 16%.
        self.assertAlmostEqual(self.rate_year(w), 0.04, places=6)
        self.assertAlmostEqual(w.government.taylor_last["target_rate"], 0.16, places=6)

    def test_no_reading_during_price_discovery(self):
        w = self.world(inflation=3.0, unemployment=0.05)
        w.recorder.history[-1]["inflation_policy"] = None      # (index too young to read)
        w.government.monthly(w)
        self.assertEqual(w.government.min_rate, 0)

    def test_a_slump_cuts_the_rate_to_zero(self):
        w = self.world(inflation=-0.05, unemployment=0.30)
        w.government.monthly(w)
        self.assertEqual(w.government.min_rate, 0)

    def test_manual_rate_when_the_rule_is_off(self):
        w = self.world(inflation=0.10, unemployment=0.05, taylor_enabled=False, gov_min_rate=0.0001)
        w.government.monthly(w)
        self.assertEqual(w.government.min_rate, 0.0001)

    def test_nothing_before_a_quarter_of_data(self):
        w = World(seed=1, rules=Rules.from_dict({"agents": 5, "gov_min_rate": 0.0001}))
        w.spawn_random_agents()
        w.step()
        self.assertIsNone(w.government.taylor_rate(w))


if __name__ == "__main__":
    unittest.main()
