"""Sticky prices (a toggle; perfectly flexible by default): posted prices close only part of the
gap to the market price each day."""
import threading
import unittest

import server
from simulation import World
from simulation.rules import Rules


class StickyPriceTests(unittest.TestCase):
    def test_flexible_by_default(self):
        self.assertEqual(Rules().price_stickiness, 0)

    def test_sticky_prices_move_part_of_the_way(self):
        w = World(seed=1, rules=Rules.from_dict({"agents": 5, "price_stickiness": 0.8}))
        w.post_prices({"water": 100.0})
        self.assertAlmostEqual(w.post_prices({"water": 200.0})["water"], 120.0)    # 20% of the gap
        w.price_stickiness = 0
        self.assertEqual(w.post_prices({"water": 200.0})["water"], 200.0)

    def test_players_change_it_in_game(self):
        w = World(seed=2, rules=Rules.from_dict({"agents": 5}))
        w.spawn_random_agents()
        sim = server.Simulation.__new__(server.Simulation)
        sim.lock, sim.world, sim.detail = threading.Lock(), w, None
        self.assertEqual(sim.set_market({"price_stickiness": 0.95})["market"]["price_stickiness"], 0.95)


if __name__ == "__main__":
    unittest.main()
