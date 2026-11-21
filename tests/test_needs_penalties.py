"""Needs are ranked (need_priority) and going without has consequences (penalties.py); agents
with no assets make a little of a basic good on their own (subsistence)."""
import unittest

from simulation import World, distributions, economy, penalties
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
    """Autonomous production: every agent can make a little water or food with labour it has left."""

    def test_a_thirsty_agent_fetches_a_little_water(self):
        w = world()
        a = w.create_agent(needs={**CALM, "thirst": 0.7}, money=0, inventory=EMPTY)
        a.capacity_now, a.labor_sold, a.own_labor = 0.5, 0.0, 0.0
        for _ in range(4):
            LaborMarket._subsistence(w)
        self.assertEqual(a.subsistence_made, {"water": 0.25})
        self.assertEqual(a.inventory.count("water"), 1)               # 4 days x 0.25

    def test_a_hungry_agent_makes_food_instead(self):
        w = world()
        a = w.create_agent(needs={**CALM, "hunger": 0.7, "thirst": 0.2}, money=0, inventory=EMPTY)
        a.capacity_now, a.labor_sold, a.own_labor = 0.5, 0.0, 0.0
        LaborMarket._subsistence(w)
        self.assertEqual(list(a.subsistence_made), ["food"])

    def test_owners_with_spare_time_do_it_too_but_not_with_their_labour_used_up(self):
        w = world()
        owner = w.create_agent(needs={**CALM, "thirst": 0.7}, money=0, inventory=EMPTY, assets={"water": 1})
        busy = w.create_agent(needs={**CALM, "thirst": 0.7}, money=0, inventory=EMPTY)
        owner.capacity_now, owner.own_labor, owner.labor_sold = 0.5, 0.3, 0.0
        busy.capacity_now, busy.own_labor, busy.labor_sold = 0.5, 0.0, 0.5
        stats = {}
        LaborMarket._subsistence(w, stats)
        self.assertAlmostEqual(owner.subsistence_made["water"], 0.2 * 0.5)
        self.assertEqual(busy.subsistence_made, {})
        self.assertEqual(stats["subsistence_agents"], 1)

    def test_working_only_for_itself_just_about_keeps_an_agent_alive(self):
        r = Rules()
        rates = dict(LaborMarket.subsistence_options(r))
        labour = (distributions.mean(r.rates["thirst"]) / (rates["water"] * r.relief("water", "thirst"))
                  + distributions.mean(r.rates["hunger"]) / (rates["food"] * r.relief("food", "hunger")))
        self.assertLessEqual(labour, 0.5)            # a day's labour (0.5) covers thirst and hunger
        self.assertGreater(labour, 0.4)              # ... with little to spare

    def test_without_a_food_industry_the_main_hunger_good_takes_its_place(self):
        r = Rules.from_dict({"industry_layers": 1})
        rates = dict(LaborMarket.subsistence_options(r))
        self.assertAlmostEqual(rates["grain"] * r.relief("grain", "hunger"), 0.35 * Rules().relief("food", "hunger"))

    def test_a_weak_agent_short_of_water_can_still_fetch_some(self):
        w = world()
        a = w.create_agent(needs={**CALM, "thirst": 0.9}, money=0, inventory=EMPTY, labor_capacity=0.5)
        a.capacity_now, a.labor_sold, a.own_labor = 0.02, 0.0, 0.0      # crushed by penalties
        LaborMarket._subsistence(w)
        self.assertAlmostEqual(a.subsistence_made["water"], 0.5 * 1.0 * 0.5)


if __name__ == "__main__":
    unittest.main()
