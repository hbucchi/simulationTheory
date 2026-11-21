"""Banks: an industry that needs a plant, inputs and its founder's minimum capital, takes
deposits, lends within the reserve and capital (Basel) ratios, and can be switched off."""
import unittest

import server
from simulation import World
from simulation.rules import GOODS, Rules
from tests.classic import CALM

NO_ASSETS = {g: 0 for g in GOODS}


def bank_world(**rules):
    """No starting agents or assets; tests place their own."""
    return World(seed=1, rules=Rules.from_dict({"assets": NO_ASSETS, "starting_banks": 0, "investing_enabled": False,
                                                "death_enabled": False, "reserve_ratio": 0, "bank_liquidity": 0,
                                                "tax_production": 0, "tax_wage": 0, "tax_profit": 0, "benefit_rate": 0, **rules}))


def open_bank(world, money=20000, services=50, shares=1.0):
    owner = world.create_agent(needs=CALM, money=money, assets={"banking": shares}, inventory={"banking": services})
    world.banking.step(world)
    return owner, world.banking.banks[-1]


class OpeningTests(unittest.TestCase):
    def test_starting_banks_open_with_their_founders_capital(self):
        w = World(seed=3, rules=Rules.from_dict({"agents": 20, "starting_banks": 4}))
        w.spawn_random_agents()
        money = {a.id: a.money for a in w.agents}
        w.banking.step(w)
        self.assertEqual(len(w.banking.open_banks()), 4)
        for bank in w.banking.banks:
            self.assertAlmostEqual(bank.equity, w.rules.bank_min_capital, places=6)
            owner = w.agent_by_id(bank.owner_id)
            # (Its cash may be partly in a bank by now: count deposits too.)
            self.assertAlmostEqual(owner.money + sum(owner.deposits.values()),
                                   money[bank.owner_id] - w.rules.bank_min_capital, places=6)

    def test_no_bank_without_the_minimum_capital(self):
        w = bank_world(bank_min_capital=5000)
        poor = w.create_agent(needs=CALM, money=4999, assets={"banking": 1})
        w.banking.step(w)
        self.assertEqual(w.banking.banks, [])
        self.assertTrue(any("can't open a bank" in e["message"] for e in w.events))
        poor.money = 5000
        w.banking.step(w)
        self.assertEqual(len(w.banking.banks), 1)
        self.assertEqual(poor.money, 0)

    def test_no_bank_without_a_banking_plant(self):
        w = bank_world()
        w.create_agent(needs=CALM, money=1e6)
        w.banking.step(w)
        self.assertEqual(w.banking.banks, [])

    def test_banking_is_an_industry_with_inputs_and_build_cost(self):
        r = Rules()
        self.assertEqual(r.inputs["banking"], {"electricity": 0.3})
        self.assertTrue(r.build_cost["banking"])
        # Left out (or its inputs are): no banks at all.
        for game in ({"excluded_industries": ["banking"]}, {"industry_layers": 1}, {"excluded_industries": ["coal"]}):
            w = World(seed=1, rules=Rules.from_dict({"agents": 10, **game}))
            w.spawn_random_agents()
            w.step()
            self.assertEqual(w.banking.banks, [], game)

    def test_a_new_bank_needs_the_founders_capital_on_top_of_the_plant(self):
        from simulation.modules.build import Build
        w = bank_world(investing_enabled=True, bank_min_capital=1e9)
        agent = w.create_agent(needs=CALM, money=50000)
        w._step_cache = {"seekers": {}}
        w._step_cache["builds"] = [("banking", 5.0, 400.0)]
        original = Build.__dict__["available"]
        Build.available = staticmethod(lambda good, world, a: True)
        try:
            Build().plan(agent, w)
        finally:
            Build.available = original
        self.assertIsNone(agent.project)   # can't put up a billion of capital


class DepositAndLoanTests(unittest.TestCase):
    def test_lending_respects_reserves_capital_services_and_collateral(self):
        w = bank_world(bank_min_capital=1000, capital_ratio=0.1, bank_liquidity=0.1, loan_per_service=100,
                       max_loan_to_value=1.0)
        owner, bank = open_bank(w, money=1000, services=1000)
        saver = w.create_agent(needs=CALM, money=0)
        bank.reserves += 9000
        bank.deposits[saver.id] = 9000
        # Capital: equity 1000 / 0.1 = 10000 of loans; reserves: 10000 - 0.1 x 9000 = 9100.
        self.assertAlmostEqual(w.banking.lendable(w, bank), 9100)
        owner.inventory.set("banking", 20)          # services: 20 x 100
        self.assertAlmostEqual(w.banking.lendable(w, bank), 2000)
        borrower = w.create_agent(needs=CALM, money=0)
        borrower.income_avg = 1e6        # (income limit not binding here)
        self.assertEqual(w.banking.borrow(w, borrower, 500, "test"), 0)   # no collateral
        lent = w.banking.borrow(w, borrower, 5000, "test", extra_collateral=1500)
        self.assertAlmostEqual(lent, 1500)          # loan-to-value 1.0 x 1500
        self.assertEqual(owner.inventory.count("banking"), 5)   # 15 units used
        self.assertAlmostEqual(borrower.money, 1500)
        self.assertAlmostEqual(borrower.debt, 1500)

    def test_loans_are_repaid_with_interest(self):
        w = bank_world(bank_min_capital=1000, loan_steps=10, deposit_rate=0.01, loan_spread=0.01)
        owner, bank = open_bank(w, money=1000)
        borrower = w.create_agent(needs=CALM, money=0)
        borrower.income_avg = 1e6
        w.banking.borrow(w, borrower, 500, "test", extra_collateral=10000)
        borrower.money += 1000
        for _ in range(10):
            w.banking.step(w)
        self.assertEqual(bank.loans, [])
        self.assertGreater(bank.interest_received, 0)
        # It had 1500 (500 of it lent): it paid back the 500 plus interest.
        left = borrower.money + sum(borrower.deposits.values())
        self.assertLess(left, 1000)
        self.assertGreater(left, 900)

    def test_unpaid_loans_default_and_the_owner_takes_shares(self):
        w = bank_world(bank_min_capital=1000, default_steps=3, max_loan_to_value=1.0)
        owner, bank = open_bank(w, money=1000 + 5000)
        borrower = w.create_agent(needs=CALM, money=0, assets={"water": 2})
        borrower.income_avg = 1e6
        w._step_cache = None
        lent = w.banking.borrow(w, borrower, 900, "test", extra_collateral=1000)
        self.assertGreater(lent, 0)
        borrower.money = 0
        for _ in range(3):
            w.banking.step(w)
        self.assertEqual(bank.loans, [])
        self.assertIn("water", owner.assets)
        self.assertTrue(any("defaulted" in e["message"] for e in w.events))

    def test_base_money_is_conserved(self):
        w = World(seed=5, rules=Rules.from_dict({"agents": 20}))
        w.spawn_random_agents()
        start = sum(a.money for a in w.agents)
        for _ in range(200):
            w.step()
        if len(w.agents) == 20:
            base = w.base_money()
            self.assertAlmostEqual(base, start + w.money_issued(), places=5)   # (+ new money: bond interest)
            self.assertGreater(w.banking.to_dict(w)["deposits"], 0)


class FailureAndSwitchTests(unittest.TestCase):
    def test_a_bank_with_negative_equity_fails_and_pays_depositors_pro_rata(self):
        w = bank_world(bank_min_capital=100)
        owner, bank = open_bank(w, money=100)
        a, b = w.create_agent(needs=CALM, money=0), w.create_agent(needs=CALM, money=0)
        bank.deposits = {a.id: 300, b.id: 100}
        bank.reserves = 200                      # equity 200 - 400 < 0
        w.banking.step(w)
        self.assertEqual(w.banking.failed, 1)
        self.assertAlmostEqual(a.money, 150)
        self.assertAlmostEqual(b.money, 50)
        self.assertEqual(w.banking.banks, [])     # nothing left: closed, the rest is lost

    def test_switching_banking_off_winds_banks_down(self):
        w = World(seed=2, rules=Rules.from_dict({"agents": 15}))
        w.spawn_random_agents()
        for _ in range(30):
            w.step()
        self.assertTrue(w.banking.open_banks())
        sim = server.Simulation.__new__(server.Simulation)
        import threading
        sim.lock, sim.world, sim.detail = threading.Lock(), w, None
        sim.set_banking({"enabled": False})
        for _ in range(400):
            w.step()
            if not w.banking.banks:
                break
        self.assertEqual(w.banking.open_banks(), [])
        self.assertEqual(sum(sum(a.deposits.values()) for a in w.agents), 0)
        sim.set_banking({"enabled": True})
        w.step()
        self.assertTrue(w.banking.open_banks())   # owners still have plants and capital

    def test_banking_off_from_the_start(self):
        w = World(seed=2, rules=Rules.from_dict({"agents": 10, "banking_enabled": False}))
        w.spawn_random_agents()
        for _ in range(20):
            w.step()
        self.assertEqual(w.banking.banks, [])
        self.assertTrue(all(not a.deposits for a in w.agents))


class BudgetAndConsumerCreditTests(unittest.TestCase):
    def test_budget_is_living_costs_and_loan_payments_over_the_budget_steps(self):
        from simulation.modules.invest import budget, cash_needed
        w = World(seed=4, rules=Rules.from_dict({"agents": 10, "budget_steps": 30}))
        w.spawn_random_agents()
        for _ in range(5):
            w.step()
        from simulation import economy
        prices = w.current_prices()
        a = max(w.agents, key=lambda x: economy.living_cost(x, prices, w.rules))   # lives off what it buys
        b = budget(a, prices, w)
        self.assertGreater(b["living"], 0)
        self.assertAlmostEqual(b["total"], cash_needed(a, prices, w.rules) + 30 * (b["living"] + b["loans"]))
        entry = next(x for x in w.to_dict()["agents"] if x["id"] == a.id)
        self.assertIn("budget", entry)

    def test_agents_only_invest_what_is_left_after_their_budget(self):
        from simulation.modules.invest import Invest, budget
        w = bank_world(investing_enabled=True, budget_steps=100000)   # a budget nobody can cover
        investor = w.create_agent(needs=CALM, money=50000)
        w.create_agent(needs=CALM, money=0, assets={"water": 2})
        self.assertGreater(budget(investor, w.current_prices(), w)["total"], 50000)
        Invest().on_step(investor, w)
        self.assertEqual(investor.assets, {})

    def test_loans_are_limited_to_a_share_of_monthly_income(self):
        w = bank_world(bank_min_capital=1000, loan_income_share=0.4, month_steps=30)
        open_bank(w, money=1000, services=100)
        w.banking.banks[0].reserves += 100000
        broke = w.create_agent(needs=CALM, money=0)
        self.assertEqual(w.banking.borrow(w, broke, 500, "consumption", unsecured=True), 0)   # no income
        worker = w.create_agent(needs=CALM, money=0)
        worker.income_avg = 10.0         # $300 a month: it may owe at most 40% of it, $120
        self.assertAlmostEqual(w.banking.borrow(w, worker, 500, "consumption", unsecured=True), 120)
        self.assertEqual(w.banking.borrow(w, worker, 500, "consumption", unsecured=True), 0)
        # The share can be changed during the game.
        w.banking.loan_income_share = 1.0
        self.assertAlmostEqual(w.banking.borrow(w, worker, 500, "consumption", unsecured=True), 180)

    def test_needs_come_before_loan_payments(self):
        w = bank_world(bank_min_capital=1000)
        owner, bank = open_bank(w, money=1000)
        w.create_agent(needs=CALM, money=50000, inventory={"water": 20, "food": 20})   # gives goods a price
        borrower = w.create_agent(needs={**CALM, "thirst": 0.9}, money=0, inventory={g: 0 for g in GOODS})
        borrower.income_avg = 1e6
        w.banking.borrow(w, borrower, 200, "test", extra_collateral=1000)
        from simulation import economy
        self.assertGreater(economy.shopping_cost(borrower, w.current_prices(), w.rules), 200)
        balance = bank.loans[0].balance
        w.banking.step(w)            # it needs its 200 for water: the payment is missed
        self.assertEqual(bank.loans[0].missed, 1)
        self.assertEqual(bank.loans[0].balance, balance)


class RoundingTests(unittest.TestCase):
    def test_a_bank_at_exactly_its_minimum_capital_can_still_lend(self):
        w = bank_world(bank_min_capital=5000)
        owner, bank = open_bank(w, money=5000, services=10)
        bank.reserves -= 1e-9           # equity 4999.999999999: float noise, not a shortfall
        self.assertGreater(w.banking.lendable(w, bank), 0)


class CentralBankTests(unittest.TestCase):
    def test_the_central_bank_sets_the_basel_ratio(self):
        import threading
        w = bank_world(bank_min_capital=1200, capital_ratio=0.12, reserve_ratio=0.0)
        owner, bank = open_bank(w, money=1200, services=10**6)
        bank.reserves += 10**6
        bank.deposits[owner.id] = 10**6
        self.assertAlmostEqual(w.banking.lendable(w, bank), 1200 / 0.12)       # 12%: $10,000 of loans
        sim = server.Simulation.__new__(server.Simulation)
        sim.lock, sim.world, sim.detail = threading.Lock(), w, None
        sim.set_policy({"capital_ratio": 0.24})
        self.assertAlmostEqual(w.banking.lendable(w, bank), 1200 / 0.24)
        sim.set_policy({"enabled": False})                                          # no regulator
        self.assertEqual(w.government.capital_ratio, 0)
        self.assertGreater(w.banking.lendable(w, bank), 1200 / 0.12)
        sim.set_policy({"enabled": True})
        self.assertAlmostEqual(w.government.capital_ratio, 0.24)                 # remembered


if __name__ == "__main__":
    unittest.main()
