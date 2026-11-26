"""Tests for Labour Law contracts/severance (and investment yield impact) and Firm Entity financials."""
import unittest

from simulation import World
from simulation.rules import GOODS, Rules
from tests.classic import CALM

EMPTY = {g: 0 for g in GOODS}


def make_world(**rules):
    return World(seed=1, rules=Rules.from_dict({
        "assets": EMPTY, "starting_banks": 0, "investing_enabled": False,
        "gov_policies": [], "housing_enabled": False, "death_enabled": False,
        "tax_production": 0, "tax_wage": 0, "tax_profit": 0, "benefit_rate": 0, **rules,
    }))


class ContractAndSeveranceTests(unittest.TestCase):
    def test_contracts_are_signed_honored_and_early_firing_pays_severance(self):
        w = make_world(min_contract_days=30, severance_rate=0.5, price_mode="fixed",
                       demand_pricing_enabled=False, fixed_prices={**{g: 10.0 for g in GOODS}, "labor": 10.0},
                       subsistence_enabled=False, specialization_enabled=False)
        boss = w.create_agent(needs=CALM, money=50000, assets={"water": 10.0}, labor_capacity=0.0, inventory=EMPTY)
        worker = w.create_agent(needs=CALM, money=0, labor_capacity=0.5, inventory=EMPTY)
        w.tick = 1
        w.labor.clear(w)
        self.assertEqual(len(w.labor.contracts), 1)
        self.assertEqual(w.labor.contracts[0]["end_tick"], 31)
        # Day 2: boss still has assets -> contract honored, no severance paid.
        w.tick = 2
        w.labor.clear(w)
        self.assertEqual(len(w.labor.contracts), 1)
        self.assertEqual(w.labor.severance_total, 0.0)
        # Day 3: boss loses all assets and has to terminate the contract early -> pays severance.
        boss.assets = {}
        worker_money_before = worker.money
        w.tick = 3
        w.labor.clear(w)
        self.assertEqual(len(w.labor.contracts), 0)
        self.assertGreater(w.labor.severance_total, 0.0)
        self.assertGreater(worker.money, worker_money_before)

    def test_contract_rigidity_reduces_asset_prices_and_investment_yield(self):
        w_gig = make_world(min_contract_days=0, severance_rate=0.0, price_mode="fixed",
                           demand_pricing_enabled=False, fixed_prices={**{g: 10.0 for g in GOODS}, "labor": 10.0})
        w_rigid = make_world(min_contract_days=360, severance_rate=0.8, price_mode="fixed",
                             demand_pricing_enabled=False, fixed_prices={**{g: 10.0 for g in GOODS}, "labor": 10.0})
        w_gig.labor.wage = w_rigid.labor.wage = 10.0
        self.assertGreater(w_rigid.contract_wage_multiplier(), 1.0)
        self.assertLess(w_rigid.asset_prices()["water"], w_gig.asset_prices()["water"])
        self.assertLess(w_rigid.industry_yield("water"), w_gig.industry_yield("water"))


class FirmEntityTests(unittest.TestCase):
    def test_firms_off_stays_simplified_and_firms_on_tracks_financial_statements(self):
        w_off = World(seed=2, rules=Rules.from_dict({"agents": 10, "firms_enabled": False}))
        w_off.spawn_random_agents()
        w_off.step()
        self.assertFalse(w_off.to_dict()["firms"]["enabled"])
        self.assertEqual(w_off.to_dict()["firms"]["count"], 0)

        w_on = World(seed=2, rules=Rules.from_dict({"agents": 10, "firms_enabled": True, "firm_overhead_rate": 0.02}))
        w_on.spawn_random_agents()
        for _ in range(5):
            w_on.step()
        firms = w_on.to_dict()["firms"]
        self.assertTrue(firms["enabled"])
        self.assertGreater(firms["count"], 0)
        self.assertGreater(firms["total_market_cap"], 0)
        top = firms["top_firms"][0]
        for key in ("revenue", "cogs", "wages", "depreciation", "overhead", "taxes", "net_income"):
            self.assertIn(key, top["income_statement"])
        for key in ("cash", "inventory", "plant", "total_assets", "debt", "equity"):
            self.assertIn(key, top["balance_sheet"])
        for key in ("operating", "investing", "financing", "net"):
            self.assertIn(key, top["cash_flow"])
        self.assertGreater(top["market_cap"], 0)


if __name__ == "__main__":
    unittest.main()
