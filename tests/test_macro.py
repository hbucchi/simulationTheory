"""Depreciation, taxes and government spending, the central bank (reserves, lender of last
resort) and national accounts (GDP, price indexes)."""
import unittest

from simulation import World
from simulation.report import NationalAccounts
from simulation.rules import GOODS, Rules
from tests.classic import CALM

NO_ASSETS = {g: 0 for g in GOODS}


def world(**rules):
    return World(seed=1, rules=Rules.from_dict({"assets": NO_ASSETS, "starting_banks": 0, "investing_enabled": False,
                                                "death_enabled": False, **rules}))


class DepreciationTests(unittest.TestCase):
    def test_plants_lose_their_yearly_rate_over_a_year(self):
        w = world(depreciation={"water": 0.05}, month_steps=30)
        a = w.create_agent(needs=CALM, money=0, assets={"water": 10})
        for _ in range(360):
            w.depreciate()
        self.assertAlmostEqual(a.assets["water"], 9.5, places=6)
        self.assertAlmostEqual(w.assets_depreciated["water"], 0.5, places=6)

    def test_defaults_are_between_1_and_5_percent_a_year(self):
        rates = Rules().depreciation
        self.assertTrue(all(0.01 <= rates[g] <= 0.05 for g in GOODS))
        self.assertLess(rates["housing"], rates["machinery"])


class TaxTests(unittest.TestCase):
    def test_salary_tax_is_withheld_from_wages(self):
        from simulation.labor import LaborMarket
        w = world(tax_wage=0.1)
        boss = w.create_agent(needs=CALM, money=1000)
        worker = w.create_agent(needs=CALM, money=0)
        LaborMarket._hire(boss, worker, 1, 100.0, LaborMarket._empty_stats(), w.government)
        self.assertAlmostEqual(worker.money, 90)
        self.assertAlmostEqual(boss.money, 900)
        self.assertAlmostEqual(w.government.revenue["wage"], 10)

    def test_profit_tax_comes_before_the_dividend_split(self):
        w = world(tax_profit=0.2)
        a = w.create_agent(needs=CALM, money=1e6, assets={"water": 1}, payout_ratio=0.5)
        a.flow["sources"]["goods"] = 1000
        a.wage_avg = 1e6
        w.retain_earnings()
        self.assertAlmostEqual(w.government.revenue["profit"], 200)
        self.assertAlmostEqual(a.company_cash, 400)    # half of what's left after tax

    def test_production_tax_is_paid_on_sales(self):
        w = World(seed=3, rules=Rules.from_dict({"agents": 20, "tax_production": 0.05}))
        w.spawn_random_agents()
        for _ in range(60):
            w.step()
        self.assertGreater(w.government.revenue["production"], 0)

    def test_no_taxes_without_a_government(self):
        w = World(seed=3, rules=Rules.from_dict({"agents": 20, "government_enabled": False}))
        w.spawn_random_agents()
        for _ in range(30):
            w.step()
        self.assertEqual(sum(w.government.revenue.values()), 0)

    def test_by_default_money_left_in_the_treasury_stays_there(self):
        w = World(seed=4, rules=Rules.from_dict({"agents": 25}))
        w.spawn_random_agents()
        for _ in range(60):
            w.step()
        g = w.government
        self.assertEqual(g.spent["transfers"], 0)            # nothing paid out unless the player chooses it
        self.assertGreater(g.treasury, 0)

    def test_the_player_can_pay_out_a_share_of_the_treasury(self):
        w = World(seed=4, rules=Rules.from_dict({"agents": 25, "surplus_transfers": 0.5}))
        w.spawn_random_agents()
        w.government.treasury = 1000.0
        before = [a.money for a in w.agents]
        w.labor._spend_surplus(w, [], {}, w.labor._empty_stats())
        self.assertAlmostEqual(w.government.treasury, 500.0)
        self.assertAlmostEqual(sum(a.money for a in w.agents) - sum(before), 500.0)

    def test_older_balanced_budget_scenarios_still_load(self):
        r = Rules.from_dict({"balanced_budget": True})
        self.assertEqual((r.surplus_public_works, r.surplus_transfers, r.surplus_repay_debt), (1.0, 1.0, 0.0))

    def test_taxes_are_spent_and_money_is_conserved(self):
        w = World(seed=4, rules=Rules.from_dict({"agents": 25, "surplus_public_works": 1, "surplus_transfers": 1}))
        w.spawn_random_agents()
        start = w.base_money()
        for _ in range(120):
            w.step()
        g = w.government
        self.assertGreater(sum(g.revenue.values()), 0)
        self.assertGreater(g.spent["benefits"] + g.spent["public_works"], 0)
        # Balanced budget: nothing kept beyond the taxes collected after the day's spending.
        self.assertLessEqual(g.treasury, sum(g.step_revenue.values()) + g.debt.step_borrowed + 1)   # (+ savers' bonds, spent tomorrow)
        if len(w.agents) == 25:
            self.assertAlmostEqual(w.base_money(), start + w.money_issued(), places=4)


class CentralBankTests(unittest.TestCase):
    def setUp(self):
        self.w = world(bank_min_capital=1000, reserve_ratio=0.1, bank_liquidity=0.0, tax_profit=0)
        self.owner = self.w.create_agent(needs=CALM, money=1000, assets={"banking": 1})
        self.w.banking.step(self.w)
        self.bank = self.w.banking.banks[0]
        self.saver = self.w.create_agent(needs=CALM, money=0)

    def test_banks_keep_the_required_reserves_at_the_central_bank(self):
        self.bank.reserves += 5000
        self.bank.deposits[self.saver.id] = 5000
        self.w.banking._central_bank(self.w, self.bank)
        self.assertAlmostEqual(self.bank.cb_reserves, 500)
        self.assertAlmostEqual(self.bank.reserves, 5500)

    def test_lender_of_last_resort_lends_to_a_solvent_bank_short_of_cash(self):
        self.bank.deposits[self.saver.id] = 5000
        self.bank.loans_value = 0
        # It lent its cash out: 1000 in the vault, 5000 of loans, 5000 of deposits.
        from simulation.banking import Loan
        borrower = self.w.create_agent(needs=CALM, money=0)
        self.bank.loans.append(Loan(1, self.bank, borrower, 5000, 0.0, 1000, 0, "test"))
        got = self.w.banking.withdraw(self.saver, 3000)
        self.assertAlmostEqual(got, 3000)
        self.assertAlmostEqual(self.bank.cb_loans, 2000)
        self.assertAlmostEqual(self.w.government.llr_outstanding, 2000)

    def test_without_a_lender_of_last_resort_depositors_wait(self):
        self.w.government.set("lender_of_last_resort", False)
        self.bank.deposits[self.saver.id] = 5000
        from simulation.banking import Loan
        borrower = self.w.create_agent(needs=CALM, money=0)
        self.bank.loans.append(Loan(1, self.bank, borrower, 5000, 0.0, 1000, 0, "test"))
        self.assertAlmostEqual(self.w.banking.withdraw(self.saver, 3000), 1000)   # only the vault


class NationalAccountsTests(unittest.TestCase):
    def test_real_gdp_uses_year_ago_prices(self):
        acc = NationalAccounts()
        made = {g: 0 for g in GOODS}
        prices = {g: 10.0 for g in GOODS}
        for _ in range(4):                              # a "year" of 4 steps at $10
            out = acc.update({**made, "food": 1}, {**made, "food": 1}, prices, year=4)
        doubled = {g: 20.0 for g in GOODS}
        for _ in range(4):                              # a year later prices doubled
            out = acc.update({**made, "food": 1}, {**made, "food": 1}, doubled, year=4)
        self.assertAlmostEqual(out["gdp_nominal"], 4 * 20)
        self.assertAlmostEqual(out["gdp_real"], 4 * 10)
        self.assertAlmostEqual(out["deflator"], 200)
        self.assertAlmostEqual(out["cpi"], 200)
        self.assertAlmostEqual(out["inflation"], 1.0)

    def test_the_game_reports_gdp_and_inflation(self):
        w = World(seed=2, rules=Rules.from_dict({"agents": 10}))
        w.spawn_random_agents()
        for _ in range(20):
            w.step()
        macro = w.to_dict()["macro"]
        self.assertGreater(macro["gdp_nominal"], 0)
        self.assertIn("inflation", macro)


class PriceLevelTests(unittest.TestCase):
    """M x V = P x Y: the price level makes a year of consumption cost money x velocity."""

    def months_of_cash(self, w):
        from simulation import economy
        prices = w.current_prices()
        costs = [(a, economy.living_cost(a, prices, w.rules) * 30) for a in w.agents]
        months = sorted(economy.money_of(a) / c for a, c in costs if c > 0)   # (some live off their own industries)
        return months[len(months) // 2]

    def test_velocity_sets_how_long_cash_lasts(self):
        w = World(seed=1, rules=Rules.from_dict({"agents": 30, "money_velocity": 4}))
        w.spawn_random_agents()
        for _ in range(40):
            w.step()
        self.assertLess(self.months_of_cash(w), 24)       # months, not years (plain formula: ~16 years)

    def test_the_amount_of_money_only_sets_the_scale(self):
        levels = []
        for money in (1000, 4000):
            w = World(seed=1, rules=Rules.from_dict({"agents": 30, "money": money, "start_months_cap": 0}))
            w.spawn_random_agents()
            levels.append(w.current_prices()["water"])
        self.assertAlmostEqual(levels[1] / levels[0], 4, places=6)

    def test_velocity_zero_is_the_plain_scarcity_formula(self):
        from simulation import economy
        w = World(seed=1, rules=Rules.from_dict({"agents": 10, "money_velocity": 0, "demand_pricing_enabled": False,
                                                 "cost_floor": False, "price_mode": "scarcity"}))
        w.spawn_random_agents()
        self.assertAlmostEqual(w.current_prices()["water"], economy.market_prices(w.agents, w.rules)["water"])


if __name__ == "__main__":
    unittest.main()
