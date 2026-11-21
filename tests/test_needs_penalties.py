"""Needs are ranked (need_priority) and going without has consequences (penalties.py); agents
with no assets make a little of a basic good on their own (subsistence)."""
import unittest

from simulation import World, economy, penalties
from simulation.labor import LaborMarket
from simulation.rules import GOODS, Rules
from tests.classic import CALM

EMPTY = {g: 0 for g in GOODS}


def world(**rules):
    return World(seed=1, rules=Rules.from_dict({"assets": EMPTY, "starting_banks": 0, "investing_enabled": False,
                                                "gov_policies": [], **rules}))


class PriorityTests(unittest.TestCase):
    def test_needs_are_ranked_water_food_sleep_shelter_health_energy_boredom(self):
        w = world()
        a = w.create_agent(needs={n: 0.6 for n in CALM}, money=0, inventory=EMPTY)
        order = sorted(w.rules.need_priority, key=lambda n: economy.urgency(a, n, w.rules), reverse=True)
        self.assertEqual(order, ["thirst", "hunger", "sleep", "shelter", "health", "energy", "boredom"])


class PenaltyTests(unittest.TestCase):
    def test_a_very_thirsty_agent_walks_slower(self):
        w = world()
        a = w.create_agent(needs={**CALM, "thirst": 0.85}, money=0, inventory=EMPTY, movement=20)
        a.modules[1].on_step(a, w)            # NeedsDecay
        self.assertEqual(a.speed, 14)

    def test_hunger_tiredness_sickness_and_cold_cut_labour(self):
        w = world()
        a = w.create_agent(needs={**CALM, "hunger": 0.85, "health": 0.85}, money=0, inventory=EMPTY)
        self.assertAlmostEqual(penalties.labor_factor(a, w.rules), 0.7 * 0.5)
        a.health = 1.0
        self.assertEqual(penalties.labor_factor(a, w.rules), 0.0)       # too sick to work

    def test_without_shelter_health_worsens_twice_as_fast(self):
        w = world()
        a = w.create_agent(needs={**CALM, "shelter": 0.9}, money=0, inventory=EMPTY)
        rate = a.modules[1].rates["health"]
        a.modules[1].on_step(a, w)
        self.assertAlmostEqual(a.health, 2 * rate)

    def test_thirty_days_too_ill_to_work_kills(self):
        w = world()
        a = w.create_agent(needs={**CALM, "health": 1.0}, money=0, inventory=EMPTY)
        a.critical_health_days = penalties.HEALTH_DEATH_DAYS
        self.assertTrue(w.check_death(a))
        self.assertNotIn(a, w.agents)

    def test_penalties_can_be_switched_off(self):
        w = world(need_penalties_enabled=False)
        a = w.create_agent(needs={**CALM, "hunger": 0.9, "thirst": 0.9}, money=0, inventory=EMPTY)
        self.assertEqual(penalties.labor_factor(a, w.rules), 1.0)
        self.assertEqual(penalties.speed_factor(a, w.rules), 1.0)


class SubsistenceTests(unittest.TestCase):
    def test_an_agent_without_assets_fetches_a_little_water_when_thirsty(self):
        w = world()
        a = w.create_agent(needs={**CALM, "thirst": 0.7}, money=0, inventory=EMPTY)
        a.capacity_now, a.labor_sold = 0.5, 0.0
        for _ in range(5):
            LaborMarket._subsistence(w)
        self.assertEqual(a.subsistence_made, {"water": 0.2})
        self.assertEqual(a.inventory.count("water"), 1)               # 5 days x 0.2

    def test_owners_and_fully_employed_agents_make_nothing_on_their_own(self):
        w = world()
        owner = w.create_agent(needs={**CALM, "thirst": 0.7}, money=0, inventory=EMPTY, assets={"water": 1})
        worker = w.create_agent(needs={**CALM, "thirst": 0.7}, money=0, inventory=EMPTY)
        owner.capacity_now = worker.capacity_now = worker.labor_sold = 0.5
        LaborMarket._subsistence(w)
        self.assertEqual((owner.subsistence_made, worker.subsistence_made), ({}, {}))

    def test_it_is_far_below_what_a_job_pays_in_goods(self):
        r = Rules()
        self.assertTrue(all(rate <= 0.1 * 4 for rate in r.subsistence_rates.values()))


if __name__ == "__main__":
    unittest.main()
