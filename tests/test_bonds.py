"""Government bonds: the government borrows what taxes can't pay for, from banks and savers, at
the central bank's rate + a spread, within a debt limit; it pays interest and repays or rolls
bonds over when they fall due."""
import unittest

from simulation import World
from simulation.rules import GOODS, Rules
from tests.classic import CALM

EMPTY = {g: 0 for g in GOODS}


def world(gdp=1e6, **rules):
    w = World(seed=1, rules=Rules.from_dict({"assets": EMPTY, "starting_banks": 0, "investing_enabled": False,
                                            "gov_policies": [], "gov_debt_limit": 0.5, "min_investment": 10,
                                            "month_steps": 30, **rules}))
    w.government.debt.yearly_gdp = lambda world: gdp      # a GDP to size the debt limit
    return w


class BorrowingTests(unittest.TestCase):
    def test_savers_lend_what_taxes_cant_pay_and_money_only_moves(self):
        w = world()
        saver = w.create_agent(needs=CALM, money=10_000, inventory=EMPTY)
        start = w.base_money()
        raised = w.government.debt.borrow(w, 1000)
        self.assertAlmostEqual(raised, 1000)
        self.assertAlmostEqual(w.government.treasury, 1000)
        self.assertAlmostEqual(w.government.debt.held_by(saver), 1000)
        self.assertAlmostEqual(w.base_money(), start)                # no money created

    def test_banks_lend_first_and_bonds_count_in_their_equity(self):
        w = world(bank_min_capital=1000, reserve_ratio=0, bank_liquidity=0)
        owner = w.create_agent(needs=CALM, money=5000, assets={"banking": 1}, inventory=EMPTY)
        w.banking.step(w)
        bank = w.banking.banks[0]
        saver = w.create_agent(needs=CALM, money=10_000, inventory=EMPTY)
        equity = bank.equity
        w.government.debt.borrow(w, 500)
        self.assertAlmostEqual(bank.bonds, 500)
        self.assertAlmostEqual(bank.equity, equity)
        self.assertEqual(w.government.debt.held_by(saver), 0)

    def test_the_debt_limit_caps_borrowing(self):
        w = world(gdp=1000)                      # limit 50% of 1000
        w.create_agent(needs=CALM, money=10_000, inventory=EMPTY)
        self.assertAlmostEqual(w.government.debt.borrow(w, 2000), 500)
        self.assertEqual(w.government.debt.borrow(w, 100), 0)

    def test_no_borrowing_when_bonds_are_off(self):
        w = world(gov_bonds_enabled=False)
        w.create_agent(needs=CALM, money=10_000, inventory=EMPTY)
        self.assertEqual(w.government.debt.borrow(w, 100), 0)

    def test_an_underfunded_policy_is_paid_with_borrowed_money(self):
        from simulation.policies import Policies
        w = world()
        w.create_agent(needs=CALM, money=10_000, inventory=EMPTY)
        poor = w.create_agent(needs=CALM, money=0, inventory=EMPTY)
        w.government.policies = Policies([{"kind": "cash", "audience": "everyone", "budget": 600}])
        w.government.policies.run(w)
        self.assertEqual(w.government.policies.items[0].funded, 1.0)
        self.assertAlmostEqual(poor.money, 10)
        self.assertAlmostEqual(w.government.debt.total, 20)


class InterestAndRepaymentTests(unittest.TestCase):
    def test_interest_is_the_policy_rate_plus_the_spread(self):
        w = world(gov_min_rate=0.0001, gov_bond_spread=0.00005)
        saver = w.create_agent(needs=CALM, money=10_000, inventory=EMPTY)
        w.government.debt.borrow(w, 1000)
        w.government.treasury = 1e6
        before = saver.money
        w.government.debt.step(w)
        self.assertAlmostEqual(saver.money - before, 1000 * 0.00015)

    def test_due_bonds_are_repaid_or_rolled_over(self):
        w = world(gov_bond_days=10)
        saver = w.create_agent(needs=CALM, money=10_000, inventory=EMPTY)
        w.government.debt.borrow(w, 1000)
        w.government.treasury = 0
        w.tick += 10
        w.government.debt.step(w)                              # nothing to repay with: rolled over
        self.assertAlmostEqual(w.government.debt.total, 1000, delta=1)   # (+ the day's interest, borrowed)
        self.assertEqual(w.government.debt.bonds[0].due, w.tick + 10)
        w.government.treasury = 5000
        w.tick += 10
        money = saver.money
        w.government.debt.step(w)
        self.assertEqual(w.government.debt.total, 0)
        self.assertGreater(saver.money - money, 1000 - 1e-6)

    def test_a_dead_holders_bonds_are_cancelled(self):
        w = world()
        saver = w.create_agent(needs=CALM, money=10_000, inventory=EMPTY)
        w.government.debt.borrow(w, 1000)
        w.remove_agent(saver)
        w.government.debt.step(w)
        self.assertEqual(w.government.debt.total, 0)


class GameTests(unittest.TestCase):
    def test_a_game_borrows_when_spending_outruns_taxes(self):
        w = World(seed=3, rules=Rules.from_dict({"agents": 30, "tax_production": 0, "tax_wage": 0, "tax_profit": 0,
                                                 "gov_policies": [{"kind": "cash", "audience": "everyone",
                                                                   "budget": 3000}]}))
        w.spawn_random_agents()
        start = w.base_money()
        for _ in range(90):
            w.step()
        debt = w.to_dict()["government"]["debt"]
        self.assertGreater(debt["debt"], 0)
        self.assertGreater(debt["interest_paid"], 0)
        if len(w.agents) == 30:
            self.assertAlmostEqual(w.base_money(), start + w.money_issued(), places=4)


if __name__ == "__main__":
    unittest.main()
