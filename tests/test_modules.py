"""Modules: whole parts of the economy can be switched off, and what depends on them goes too."""
import unittest

from simulation import World
from simulation.rules import MODULES, Rules


class ModuleTests(unittest.TestCase):
    def test_switching_a_module_off_switches_off_what_needs_it(self):
        r = Rules.from_dict({"industries_enabled": False})
        for rule in ("investing_enabled", "building_enabled", "banking_enabled", "consumer_credit"):
            self.assertFalse(getattr(r, rule), rule)
        self.assertTrue(r.commerce_enabled)
        self.assertTrue(any("needs Industries" in n for n in r.module_notes))
        r = Rules.from_dict({"commerce_enabled": False})
        for rule in ("selling_enabled", "demand_pricing_enabled", "stockpiling_enabled", "banking_enabled"):
            self.assertFalse(getattr(r, rule), rule)
        self.assertTrue(r.investing_enabled)

    def test_every_module_is_a_boolean_rule_with_known_needs(self):
        for key, (rule, label, needs, about) in MODULES.items():
            self.assertIsInstance(getattr(Rules(), rule), bool)
            self.assertTrue(set(needs) <= set(MODULES), key)

    def test_no_commerce_means_no_trading(self):
        w = World(seed=1, rules=Rules.from_dict({"agents": 15, "commerce_enabled": False}))
        w.spawn_random_agents()
        for _ in range(30):
            w.step()
        self.assertEqual(sum(s["goods_deals"] for s in w.recorder.history), 0)

    def test_no_industries_means_nothing_is_made(self):
        w = World(seed=1, rules=Rules.from_dict({"agents": 15, "industries_enabled": False}))
        w.spawn_random_agents()
        for _ in range(30):
            w.step()
        self.assertEqual(sum(sum(s["produced"].values()) for s in w.recorder.history), 0)
        self.assertEqual(w.banking.banks, [])

    def test_government_off_means_no_policy(self):
        w = World(seed=1, rules=Rules.from_dict({"agents": 5, "government_enabled": False, "gov_min_rate": 0.05,
                                                 "gov_labor_purchase": 3}))
        self.assertEqual((w.government.min_rate, w.government.labor_purchase, w.government.capital_ratio), (0, 0, 0))


if __name__ == "__main__":
    unittest.main()
