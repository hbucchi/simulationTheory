"""Personality: frugal-lavish (leisure spending, diminishing returns on entertainment), set per
agent or for a group; idle savings go into bonds."""
import threading
import unittest

import server
from simulation import World, economy
from simulation.modules.leisure import Leisure
from simulation.rules import GOODS, Rules
from tests.classic import CALM

EMPTY = {g: 0 for g in GOODS}


def world(**rules):
    return World(seed=1, rules=Rules.from_dict({"assets": EMPTY, "starting_banks": 0, "investing_enabled": False,
                                                "gov_policies": [], **rules}))


class AdaptationTests(unittest.TestCase):
    def test_lavish_agents_tire_of_entertainment_frugal_ones_do_not(self):
        w = world()
        lavish = w.create_agent(needs=CALM, money=0, inventory=EMPTY, lavishness=1.0)
        frugal = w.create_agent(needs=CALM, money=0, inventory=EMPTY, lavishness=0.0)
        for a in (lavish, frugal):
            a.recent_fun = 10
        self.assertAlmostEqual(economy.adaptation(lavish, "boredom", w.rules), 1 / (1 + 0.5 * 10))
        self.assertEqual(economy.adaptation(frugal, "boredom", w.rules), 1.0)
        self.assertEqual(economy.adaptation(lavish, "hunger", w.rules), 1.0)    # only entertainment


class LeisureTests(unittest.TestCase):
    def test_a_rich_lavish_agent_spends_on_entertainment_a_frugal_one_does_not(self):
        w = world(trade_radius=5000)
        seller = w.create_agent(needs=CALM, money=0, inventory={**EMPTY, "games": 500})
        lavish = w.create_agent(needs=CALM, money=1e6, inventory=EMPTY, lavishness=1.0)
        frugal = w.create_agent(needs=CALM, money=1e6, inventory=EMPTY, lavishness=0.0)
        w.update_demand()
        prices = {**w.current_prices(), **{g: 10.0 for g in GOODS}}
        w.current_prices = lambda include_labor=True: prices
        Leisure().on_step(lavish, w)
        Leisure().on_step(frugal, w)
        self.assertLess(lavish.money, 1e6)
        self.assertGreater(seller.money, 0)
        self.assertEqual(frugal.money, 1e6)


class GroupTests(unittest.TestCase):
    def test_players_set_a_trait_for_a_group(self):
        w = World(seed=2, rules=Rules.from_dict({"agents": 20}))
        w.spawn_random_agents()
        sim = server.Simulation.__new__(server.Simulation)
        sim.lock, sim.world, sim.detail = threading.Lock(), w, None
        sim.set_personality({"group": "owners", "trait": "lavishness", "value": 0.9})
        owners = [a for a in w.agents if a.assets]
        self.assertTrue(owners and all(a.personality["lavishness"] == 0.9 for a in owners))
        with self.assertRaises(ValueError):
            sim.set_personality({"group": "martians", "trait": "lavishness", "value": 1})


class SavingsTests(unittest.TestCase):
    def test_idle_money_buys_bonds_and_the_treasury_gets_it(self):
        w = world()
        w.government.debt.yearly_gdp = lambda world: 1e9
        saver = w.create_agent(needs=CALM, money=1e6, inventory=EMPTY)
        lent = w.government.debt.sell_to(w, saver, 50_000)
        self.assertAlmostEqual(lent, 50_000)
        self.assertAlmostEqual(w.government.treasury, 50_000)
        self.assertAlmostEqual(w.government.debt.held_by(saver), 50_000)


if __name__ == "__main__":
    unittest.main()
