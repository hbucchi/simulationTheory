"""Labour law: wages are paid daily, weekly or monthly; the salary tax is withheld on payday."""
import unittest

from simulation import World
from simulation.labor import LaborMarket
from simulation.rules import GOODS, Rules
from tests.classic import CALM

EMPTY = {g: 0 for g in GOODS}


def world(period, **rules):
    return World(seed=1, rules=Rules.from_dict({"assets": EMPTY, "starting_banks": 0, "gov_policies": [],
                                                "pay_period": period, "tax_wage": 0.1, "month_steps": 30, **rules}))


class PaydayTests(unittest.TestCase):
    def test_weekly_pay_is_owed_until_payday_then_paid_net_of_tax(self):
        w = world("weekly")
        boss = w.create_agent(needs=CALM, money=1000, inventory=EMPTY)
        worker = w.create_agent(needs=CALM, money=0, inventory=EMPTY)
        stats = LaborMarket._empty_stats()
        for _ in range(3):
            LaborMarket._hire(boss, worker, 1, 100.0, stats, w.government, w.labor.payroll)
        self.assertEqual((worker.money, boss.money), (0, 1000))            # nothing paid yet
        self.assertAlmostEqual(w.labor.owed_to(worker.id), 300)
        self.assertAlmostEqual(w.labor.owed_by(boss.id), 300)
        w.labor.payday(w)
        self.assertAlmostEqual(worker.money, 270)                          # 300 minus 10% salary tax
        self.assertAlmostEqual(boss.money, 700)
        self.assertAlmostEqual(w.government.revenue["wage"], 30)

    def test_an_employer_short_of_cash_owes_the_rest(self):
        w = world("monthly")
        boss = w.create_agent(needs=CALM, money=50, inventory=EMPTY)
        worker = w.create_agent(needs=CALM, money=0, inventory=EMPTY)
        LaborMarket._hire(boss, worker, 1, 100.0, LaborMarket._empty_stats(), w.government, w.labor.payroll)
        w.labor.payday(w)
        self.assertAlmostEqual(worker.money, 45)
        self.assertAlmostEqual(w.labor.owed_to(worker.id), 50)

    def test_paydays_follow_the_law_and_it_can_change_in_game(self):
        w = world("daily")
        self.assertEqual(LaborMarket.pay_days(w), 1)
        w.government.set("pay_period", "monthly")
        self.assertEqual(LaborMarket.pay_days(w), 30)
        w.government.set("pay_period", "weekly")
        self.assertEqual(LaborMarket.pay_days(w), 7)

    def test_a_monthly_paid_game_runs_and_conserves_money(self):
        w = World(seed=2, rules=Rules.from_dict({"agents": 30, "pay_period": "monthly"}))
        w.spawn_random_agents()
        start = w.base_money()
        for _ in range(75):
            w.step()
        self.assertGreater(w.government.revenue["wage"], 0)
        if len(w.agents) == 30:
            self.assertAlmostEqual(w.base_money(), start + w.money_issued(), places=4)


if __name__ == "__main__":
    unittest.main()
