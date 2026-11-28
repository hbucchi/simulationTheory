"""Indicators and fixes from the panel backlog: the labour breakdown, the chained CPI with a warm-up,
anchored expectations, ownership classes, balanced starting ownership, independent random streams,
log-scale approval, configurable epidemics and the "why?" explanations."""
import math
import unittest

from simulation import World, labor, report
from simulation.explain import METRICS, explain
from simulation.government import inflation_score
from simulation.rules import GOODS, Rules
from tests.classic import CALM

EMPTY = {g: 0 for g in GOODS}


def run(days=40, agents=40, seed=3, **rules):
    w = World(seed=seed, rules=Rules.from_dict({"agents": agents, **rules}))
    w.spawn_random_agents()
    for _ in range(days):
        w.step()
    return w


class LabourBreakdownTests(unittest.TestCase):
    def test_every_unit_of_labour_is_accounted_for(self):
        w = run(days=20)
        b = w.labor.stats["breakdown"]
        used = sum(b[k] for k in ("lost", "own_business", "hired_private", "hired_public", "autonomous",
                                  "looking", "not_offered"))
        self.assertAlmostEqual(used, b["full_capacity"], places=2)
        self.assertAlmostEqual(sum(w.labor.stats["lost_by"].values()) - b["survival_extra"], b["lost"], places=2)

    def test_losses_name_their_causes(self):
        w = World(seed=1, rules=Rules.from_dict({"assets": EMPTY, "starting_banks": 0, "gov_policies": []}))
        a = w.create_agent(needs={**CALM, "hunger": 0.85, "health": 0.85}, money=0, inventory=EMPTY)
        lost = labor.capacity_losses(a, w.rules)
        self.assertGreater(lost["hunger"], 0)
        self.assertGreater(lost["health"], lost.get("boredom", 0.0))
        cap = a.labor_capacity * labor.efficiency(a, w.rules) * 0.7 * 0.5
        self.assertAlmostEqual(sum(lost.values()), a.labor_capacity - cap, places=9)

    def test_ilo_classes_cover_everyone(self):
        w = run(days=10)
        h = w.recorder.history[-1]
        self.assertEqual(sum(h["lf"].values()), len(w.agents))
        self.assertGreaterEqual(h["lf_unemployment"], 0)
        self.assertLessEqual(h["lf_unemployment"], 1)


class PriceIndexTests(unittest.TestCase):
    def test_price_discovery_is_not_inflation(self):
        w = run(days=20, cpi_warmup_days=30)
        h = w.recorder.history[-1]
        self.assertEqual(h["cpi"], 100.0)
        self.assertEqual(h["inflation"], 0.0)
        self.assertIsNone(h["inflation_policy"])

    def test_the_index_starts_after_the_warm_up_and_policy_reads_it_after_three_months(self):
        w = run(days=60, cpi_warmup_days=30)
        self.assertEqual(w.recorder.history[-1]["cpi_days"], 29)
        self.assertIsNone(w.recorder.history[-1]["inflation_policy"])
        for _ in range(65):
            w.step()
        self.assertIsNotNone(w.recorder.history[-1]["inflation_policy"])


class ExpectationTests(unittest.TestCase):
    def test_a_fully_credible_central_bank_anchors_expectations(self):
        w = run(days=5, expectations_enabled=True, expectations_credibility=1.0)
        self.assertAlmostEqual(w.expected_inflation, w.government.inflation_target)

    def test_half_the_gap_closes_in_one_half_life(self):
        w = World(seed=1, rules=Rules.from_dict({"agents": 3, "expectations_enabled": True, "expectations_credibility": 0,
                                                "expectations_half_life_days": 10}))
        w.spawn_random_agents()
        w.step()
        w.adaptive_inflation = 0.0
        for _ in range(10):
            w.recorder.history[-1]["inflation_policy"] = 1.0
            w.update_expectations()
        self.assertAlmostEqual(w.expected_inflation, 0.5, places=6)

    def test_older_daily_speed_becomes_a_half_life(self):
        r = Rules.from_dict({"expectations_speed": 0.05})
        self.assertAlmostEqual(r.expectations_half_life_days, round(math.log(0.5) / math.log(0.95), 1))


class OwnershipTests(unittest.TestCase):
    def test_big_owners_hold_80_percent_the_rest_are_smes(self):
        w = World(seed=1, rules=Rules.from_dict({"assets": EMPTY, "starting_banks": 0, "gov_policies": []}))
        for shares in (50, 30, 10, 5, 5):
            w.create_agent(needs=CALM, money=0, inventory=EMPTY, assets={"water": shares})
        w.create_agent(needs=CALM, money=0, inventory=EMPTY)
        rows = [{"agent": a, "assets": 0.0, "shares": sum(a.assets.values())} for a in w.agents]
        big, smes = report.ownership_classes(rows, 0.8)
        self.assertEqual(len(big), 2)          # 50 + 30 = 80%
        self.assertEqual(len(smes), 3)

    def test_each_industry_starts_with_the_same_number_of_owners(self):
        w = World(seed=12, rules=Rules.from_dict({"agents": 200, "industry_owners": 3}))
        w.spawn_random_agents()
        for g in w.rules.active_goods:
            if g == "banking":
                continue
            holders = [a for a in w.agents if a.assets.get(g, 0) > 0]
            if holders:
                self.assertEqual(len(holders), 3, g)
                self.assertAlmostEqual(min(a.assets[g] for a in holders), max(a.assets[g] for a in holders))


class RandomStreamTests(unittest.TestCase):
    def test_moving_agents_on_the_map_does_not_change_who_owns_what(self):
        a = World(seed=11, rules=Rules.from_dict({"agents": 50}))
        b = World(seed=11, rules=Rules.from_dict({"agents": 50}), stream_seeds={"positions": 99})
        a.spawn_random_agents()
        b.spawn_random_agents()
        self.assertEqual([x.assets for x in a.agents], [y.assets for y in b.agents])
        self.assertEqual([x.money for x in a.agents], [y.money for y in b.agents])
        self.assertNotEqual([(x.x, x.y) for x in a.agents], [(y.x, y.y) for y in b.agents])


class ApprovalTests(unittest.TestCase):
    def test_inflation_hurts_on_a_log_scale(self):
        self.assertAlmostEqual(inflation_score(0.02, 0.02), 1.0)
        self.assertAlmostEqual(inflation_score(1.02 * 1.10 - 1, 0.02), 0.5, places=6)
        # Still telling 39% from 1,000% apart, but less than linearly.
        self.assertGreater(inflation_score(0.39, 0.02), inflation_score(3.16, 0.02))
        self.assertGreater(inflation_score(3.16, 0.02), inflation_score(10.0, 0.02))


class EpidemicTests(unittest.TestCase):
    def test_fatality_is_per_infection(self):
        w = World(seed=1, rules=Rules.from_dict({"assets": EMPTY, "starting_banks": 0, "gov_policies": []}))
        w.create_agent(needs=CALM, money=0, inventory=EMPTY)
        epi = w.shocks.trigger_epidemic(w, fatality=0.26, duration=30)
        self.assertAlmostEqual(1 - (1 - epi["lethality_rate"]) ** 30, 0.26)

    def test_frail_agents_are_more_at_risk(self):
        w = World(seed=1, rules=Rules.from_dict({"assets": EMPTY, "starting_banks": 0, "gov_policies": []}))
        well = w.create_agent(needs={**CALM, "health": 0.1}, money=0, inventory=EMPTY)
        ill = w.create_agent(needs={**CALM, "health": 0.9}, money=0, inventory=EMPTY)
        epi = w.shocks.trigger_epidemic(w, fatality=0.05, duration=10, frailty=1.0)
        self.assertGreater(w.shocks.death_risk(epi, ill), w.shocks.death_risk(epi, well))


class ExplainTests(unittest.TestCase):
    def test_every_headline_has_an_explanation(self):
        w = run(days=45)
        for m in METRICS:
            e = explain(w, m)
            self.assertEqual(e["metric"], m)
            self.assertTrue(e["summary"])

    def test_unknown_metric_is_refused(self):
        with self.assertRaises(ValueError):
            explain(run(days=1), "astrology")


if __name__ == "__main__":
    unittest.main()
