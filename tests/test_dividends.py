"""Companies (and banks) pay out part of their profits as dividends and keep the rest to grow:
the split is the owner's payout_ratio, a personality trait."""
import unittest

import server
from simulation import World
from simulation.modules.build import Build
from simulation.rules import GOODS, Rules
from tests.classic import CALM

NO_ASSETS = {g: 0 for g in GOODS}


def world(**rules):
    return World(seed=1, rules=Rules.from_dict({"assets": NO_ASSETS, "starting_banks": 0, "investing_enabled": False,
                                                "death_enabled": False, "reserve_ratio": 0, "bank_liquidity": 0,
                                                "tax_production": 0, "tax_wage": 0, "tax_profit": 0, "benefit_rate": 0, **rules}))


def owner_with_profit(w, payout, sales, wages=0.0, money=1e6):
    a = w.create_agent(needs=CALM, money=money, assets={"water": 1}, payout_ratio=payout)
    a.flow["sources"]["goods"] = sales
    a.flow["wages_paid"] = wages
    a.wage_avg = 1e6          # (company cash cap not binding)
    return a


class RetainedEarningsTests(unittest.TestCase):
    def test_profit_is_split_by_the_owners_payout_ratio(self):
        w = world()
        a = owner_with_profit(w, payout=0.3, sales=1000, wages=200)    # profit 800
        w.retain_earnings()
        self.assertAlmostEqual(a.company_cash, 0.7 * 800)
        self.assertAlmostEqual(a.money, 1e6 - 0.7 * 800)
        self.assertAlmostEqual(w.base_money(), 1e6)                    # only moved

    def test_paying_everything_out_keeps_nothing(self):
        w = world()
        a = owner_with_profit(w, payout=1.0, sales=1000)
        w.retain_earnings()
        self.assertEqual(a.company_cash, 0)

    def test_payout_ratio_is_drawn_per_agent_and_editable(self):
        w = World(seed=2, rules=Rules.from_dict({"agents": 20}))
        w.spawn_random_agents()
        ratios = {a.personality["payout_ratio"] for a in w.agents}
        self.assertGreater(len(ratios), 1)
        self.assertTrue(all(0.2 <= r <= 0.8 for r in ratios))          # default uniform 0.2-0.8
        w.update_agent(w.agents[0], **server.parse_agent_config({"payout_ratio": 0.9}))
        self.assertEqual(w.agents[0].personality["payout_ratio"], 0.9)

    def test_owners_take_enough_to_live_on(self):
        w = world()
        a = owner_with_profit(w, payout=0.0, sales=1000, money=1000)
        w.retain_earnings()          # keeps the profit... but the owner needs its budget first
        self.assertGreater(a.money, 0)
        self.assertLess(a.company_cash, 1000)

    def test_companies_keep_only_what_they_can_use(self):
        w = world()
        a = owner_with_profit(w, payout=0.0, sales=0)
        a.wage_avg = 0.0
        a.company_cash = 50000
        w.retain_earnings()
        self.assertAlmostEqual(a.company_cash, w.company_cash_cap(a, w.current_prices()), places=6)

    def test_selling_every_company_returns_the_cash(self):
        w = world()
        a = w.create_agent(needs=CALM, money=0)
        a.company_cash = 300
        w.retain_earnings()
        self.assertEqual((a.company_cash, a.money), (0, 300))

    def test_retained_earnings_build_more_of_its_own_industry(self):
        w = world(investing_enabled=True, min_investment=100)
        a = w.create_agent(needs=CALM, money=0, assets={"water": 1})
        a.company_cash = 5000
        w._step_cache = {"seekers": {}, "builds": [("grain", 9.0, 400.0), ("water", 2.0, 400.0)]}
        original = Build.__dict__["available"]
        Build.available = staticmethod(lambda good, world, agent: True)
        try:
            Build().plan(a, w)
        finally:
            Build.available = original
        self.assertEqual(a.project["good"], "water")       # its own industry, not the better grain
        self.assertAlmostEqual(a.project["reinvested"], 400.0)
        self.assertAlmostEqual(a.company_cash, 4600.0)


class BankDividendTests(unittest.TestCase):
    def make_bank(self, payout):
        w = world(bank_min_capital=1000)
        owner = w.create_agent(needs=CALM, money=1000, assets={"banking": 1}, payout_ratio=payout)
        w.banking.step(w)
        return w, owner, w.banking.banks[0]

    def test_banks_pay_out_their_share_and_keep_the_rest_as_equity(self):
        w, owner, bank = self.make_bank(payout=0.25)
        bank.reserves += 400          # 400 of profit this step
        w.banking.step(w)
        self.assertAlmostEqual(bank.dividends, 100)
        self.assertAlmostEqual(bank.equity, 1300)
        self.assertAlmostEqual(bank.retained, 300)

    def test_retained_equity_lets_a_bank_lend_more(self):
        w, owner, bank = self.make_bank(payout=0.0)
        owner.inventory.set("banking", 1000)
        before = bank.equity / w.government.capital_ratio
        bank.reserves += 1000
        w.banking.step(w)
        self.assertAlmostEqual(bank.equity / w.government.capital_ratio, before * 2)


class LoanIncomeShareTests(unittest.TestCase):
    def test_the_share_of_monthly_income_can_be_changed_in_the_game(self):
        import threading
        w = World(seed=2, rules=Rules.from_dict({"agents": 5}))
        w.spawn_random_agents()
        sim = server.Simulation.__new__(server.Simulation)
        sim.lock, sim.world, sim.detail = threading.Lock(), w, None
        state = sim.set_banking({"loan_income_share": 0.25})
        self.assertEqual(state["banking"]["loan_income_share"], 0.25)
        self.assertEqual(w.banking.loan_income_share, 0.25)


if __name__ == "__main__":
    unittest.main()
