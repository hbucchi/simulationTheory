"""Mortgages: banks lend up to a share of a house's price over many years, if the installments fit
the borrower's income; missed payments end in foreclosure; selling repays the bank first."""
import unittest

from simulation import World
from simulation.banking import annuity
from simulation.rules import GOODS, Rules
from tests.classic import CALM

EMPTY = {g: 0 for g in GOODS}


def world(**rules):
    w = World(seed=1, rules=Rules.from_dict({"assets": EMPTY, "starting_banks": 0, "investing_enabled": False,
                                            "gov_policies": [], "month_steps": 30, "reserve_ratio": 0,
                                            "bank_liquidity": 0, "bank_min_capital": 1000, **rules}))
    banker = w.create_agent(needs=CALM, money=1e6, assets={"banking": 1}, inventory=EMPTY)
    w.banking.step(w)
    w.banking.banks[0].reserves += 1e6          # (deposits to lend)
    w.banking.banks[0].deposits[banker.id] = 1e6
    return w, banker


def price_at(w, price):
    w.housing._price = (w.tick, price)
    return price


class OfferTests(unittest.TestCase):
    def test_the_bank_lends_90_percent_if_the_installment_fits_35_percent_of_income(self):
        w, _ = world()
        buyer = w.create_agent(needs=CALM, money=0, inventory=EMPTY)
        rate = w.banking.mortgage_rate(w)
        installment = annuity(90_000, rate, 30 * 360)
        buyer.income_avg = installment / 0.35 * 1.01
        bank, amount = w.banking.mortgage_offer(w, buyer, 100_000)
        self.assertAlmostEqual(amount, 90_000)
        buyer.income_avg = installment / 0.35 * 0.99          # a little too little income
        self.assertIsNone(w.banking.mortgage_offer(w, buyer, 100_000))

    def test_other_loans_count_against_the_income(self):
        w, _ = world()
        buyer = w.create_agent(needs=CALM, money=0, inventory=EMPTY)
        buyer.income_avg = annuity(90_000, w.banking.mortgage_rate(w), 30 * 360) / 0.35 * 1.01
        w.banking.payments_of = lambda agent: 1.0              # already paying a loan
        self.assertIsNone(w.banking.mortgage_offer(w, buyer, 100_000))


class BuyingWithAMortgageTests(unittest.TestCase):
    def test_a_first_home_bought_with_a_deposit_and_a_mortgage(self):
        w, _ = world()
        seller = w.create_agent(needs=CALM, money=0, inventory=EMPTY)
        buyer = w.create_agent(needs=CALM, money=30_000, inventory=EMPTY)
        buyer.income_avg = 1_000
        house = w.housing.new_house(seller, 0)
        house.for_sale = True
        price_at(w, 100_000)
        w.housing.step(w)
        self.assertIs(buyer.home, house)
        self.assertAlmostEqual(seller.money, 100_000)
        self.assertAlmostEqual(buyer.debt, 90_000)
        self.assertIs(w.banking.mortgage_on(house).house, house)

    def test_selling_a_mortgaged_house_repays_the_bank_first(self):
        w, _ = world()
        owner = w.create_agent(needs=CALM, money=0, inventory=EMPTY)
        owner.income_avg = 1_000
        house = w.housing.new_house(owner, 0)
        w.banking.take_mortgage(w, owner, w.banking.banks[0], 80_000, house)
        owner.money = 0
        buyer = w.create_agent(needs=CALM, money=200_000, inventory=EMPTY)
        w.housing._buy(w, buyer, house, 100_000)
        self.assertAlmostEqual(owner.money, 20_000)
        self.assertIsNone(w.banking.mortgage_on(house))


class ForeclosureTests(unittest.TestCase):
    def test_unpaid_installments_end_in_foreclosure(self):
        w, banker = world(mortgage_default_days=3)
        owner = w.create_agent(needs=CALM, money=0, inventory=EMPTY)
        house = w.housing.new_house(owner, 0)
        w.housing.move_in(owner, house)
        w.banking.take_mortgage(w, owner, w.banking.banks[0], 80_000, house)
        owner.money = 0
        price_at(w, 100_000)
        for _ in range(3):
            w.banking._collect(w, w.banking.banks[0])
        self.assertIs(house.owner, banker)
        self.assertIsNone(owner.home)
        self.assertEqual(w.banking.foreclosures, 1)


if __name__ == "__main__":
    unittest.main()
