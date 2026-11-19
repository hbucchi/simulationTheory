"""Choosing the industries in a game, and the shortcuts that keep big games fast (each checked
against the slow, obvious version it replaces)."""
import unittest

import server
from simulation import World, economy
from simulation.rules import GOODS, Rules
from simulation.world import FULL_DETAIL_AGENTS


def busy_world(agents=40, steps=150, seed=3, **rules):
    w = World(seed=seed, rules=Rules.from_dict({"agents": agents, **rules}))
    w.spawn_random_agents()
    for _ in range(steps):
        w.step()
    return w


class ExcludedIndustryTests(unittest.TestCase):
    def test_excluded_industries_and_everything_made_from_them_are_left_out(self):
        r = Rules.from_dict({"excluded_industries": ["grain"]})
        self.assertFalse(r.is_active("grain"))
        # Made from grain (directly or further down): gone too, and reported as such.
        for g in ("food", "beverages", "meals", "fast_food"):
            self.assertFalse(r.is_active(g), g)
            self.assertIn(g, r.auto_excluded)
        self.assertNotIn("grain", r.auto_excluded)        # left out by choice, not automatically
        self.assertTrue(r.is_active("meat"))               # other hunger goods are untouched
        self.assertIn("meat", r.goods_for("hunger"))
        self.assertNotIn("food", r.goods_for("hunger"))

    def test_too_deep_industries_are_not_reported_as_auto_excluded(self):
        r = Rules.from_dict({"industry_layers": 2, "excluded_industries": ["electricity"]})
        self.assertFalse(r.is_active("apparel"))           # layer 3: cut by the layer limit
        self.assertNotIn("apparel", r.auto_excluded)

    def test_excluded_industries_are_validated(self):
        for bad in ("grain", ["unobtainium"], [1]):
            with self.assertRaises(ValueError):
                Rules.from_dict({"excluded_industries": bad})
        self.assertEqual(Rules.from_dict({"excluded_industries": ["food", "grain", "food"]}).excluded_industries,
                         ["grain", "food"])            # catalog order, no repeats

    def test_left_out_industries_get_no_assets_and_their_stock_moves_to_others(self):
        r = Rules.from_dict({"excluded_industries": ["food"]})
        self.assertEqual(r.assets["food"]["average"], 0)
        self.assertEqual(r.inventory["food"], 0)
        full = Rules.from_dict({})
        # Starting food became the same relief in the best hunger good still in the game.
        best = r.goods_for("hunger")[0]
        self.assertGreater(r.inventory[best], full.inventory[best])

    def test_stock_given_for_a_missing_good_is_converted_too(self):
        r = Rules.from_dict({"excluded_industries": ["food"], "inventory": {"food": 40}})
        self.assertEqual(r.inventory["food"], 0)

    def test_a_game_without_them_runs_and_nobody_holds_them(self):
        w = busy_world(agents=12, steps=60, excluded_industries=["electricity", "grain"])
        for a in w.agents:
            for g in ("electricity", "grain", "food", "meals"):
                self.assertEqual(a.inventory.count(g), 0)
                self.assertNotIn(g, a.assets)
        self.assertIn("food", w.to_dict()["auto_excluded"])


class FastPathTests(unittest.TestCase):
    """The per-step shortcuts give exactly what the plain per-good checks give."""

    @classmethod
    def setUpClass(cls):
        cls.worlds = [busy_world(), busy_world(seed=4, industry_layers=2), busy_world(seed=5, steps=300)]

    def test_wanted_goods_matches_wants_to_buy(self):
        for w in self.worlds:
            for a in w.agents:
                slow = {r for r in w.rules.active_goods if economy.wants_to_buy(a, r, w.rules, w.scarcity)}
                self.assertEqual(economy.wanted_goods(a, w.rules, w.scarcity), slow)

    def test_spare_and_surplus_match_the_separate_checks(self):
        for w in self.worlds:
            for a in w.agents:
                for r in w.rules.active_goods:
                    spare = economy.spare(a, r, w.rules, w.scarcity)
                    surplus = economy.surplus(a, r, w.rules, w.scarcity) if spare else 0
                    self.assertEqual(economy.spare_and_surplus(a, r, w.rules, w.scarcity), (spare, surplus))

    def test_contacts_match_checking_every_pair(self):
        w = self.worlds[0]
        # Pile some agents together so there are contacts to find.
        for a in w.agents[:10]:
            a.x, a.y = 500 + a.id % 3 * 5, 500 + a.id % 2 * 7
        pairs = [(a, b) for i, a in enumerate(w.agents) for b in w.agents[i + 1:]
                 if a.distance_to(b) <= w.contact_distance]
        self.assertTrue(pairs)
        self.assertEqual(w.contacts(), pairs)


class StateDetailTests(unittest.TestCase):
    def test_small_games_describe_everyone_in_full(self):
        w = busy_world(agents=5, steps=2)
        self.assertTrue(all(a["full"] and "modules" in a for a in w.to_dict()["agents"]))

    def test_big_games_describe_only_the_agents_asked_for(self):
        w = busy_world(agents=FULL_DETAIL_AGENTS + 5, steps=1)
        agents = w.to_dict(detail=[1, 2])["agents"]
        full = [a["id"] for a in agents if a["full"]]
        self.assertEqual(full, [1, 2])
        compact = next(a for a in agents if not a["full"])
        for key in ("x", "y", "needs", "inventory", "activity", "money", "wants", "reserve", "labor"):
            self.assertIn(key, compact)
        self.assertNotIn("modules", compact)
        self.assertTrue(all(n for n in compact["inventory"].values()))   # only goods it holds
        self.assertTrue(all(a["full"] for a in w.to_dict(detail="all")["agents"]))

    def test_server_reads_the_detail_it_is_asked_for(self):
        self.assertEqual(server.parse_detail("all"), "all")
        self.assertEqual(server.parse_detail([3, "4", "x"]), {3, 4})
        with self.assertRaises(ValueError):
            server.parse_detail("3")


if __name__ == "__main__":
    unittest.main()
