"""The housing market: whole houses, each housing one agent; homebuilders add houses; rent,
evictions, buying a home, buying to let (only with a home of one's own), and estates."""
import unittest

from simulation import World
from simulation.rules import GOODS, Rules
from tests.classic import CALM

EMPTY = {g: 0 for g in GOODS}


def world(**rules):
    return World(seed=1, rules=Rules.from_dict({"assets": EMPTY, "starting_banks": 0, "investing_enabled": False,
                                                "gov_policies": [], "month_steps": 30, **rules}))


def price_at(w, price):
    w.housing._price = (w.tick, price)          # today's house price, for the test
    return price


class StartTests(unittest.TestCase):
    def test_owners_live_in_their_own_houses_others_rent_and_some_are_homeless(self):
        w = World(seed=3, rules=Rules.from_dict({"agents": 100}))
        w.spawn_random_agents()
        h = w.housing.to_dict(w)
        self.assertEqual(h["houses"], 95)
        owners = [a for a in w.agents if a.assets]
        self.assertTrue(all(a.home is not None and a.home.owner is a for a in owners))
        self.assertEqual(h["homeless"], 5)
        self.assertEqual(h["rented"], 95 - len(owners))


class ShelterTests(unittest.TestCase):
    def test_a_house_meets_shelter_and_the_homeless_shelter_grows_fast(self):
        w = world()
        housed = w.create_agent(needs={**CALM, "shelter": 0.5}, money=0, inventory=EMPTY)
        homeless = w.create_agent(needs={**CALM, "shelter": 0.5}, money=0, inventory=EMPTY)
        w.housing.move_in(housed, w.housing.new_house(None, 0))
        for a in (housed, homeless):
            a.modules[1].on_step(a, w)       # NeedsDecay
        self.assertAlmostEqual(housed.shelter, 0.5 - w.rules.house_relief)
        self.assertAlmostEqual(homeless.shelter, 0.5 + w.rules.homeless_shelter_rate)


class RentTests(unittest.TestCase):
    def test_tenants_pay_rent_daily_and_are_evicted_when_they_cant(self):
        w = world(eviction_days=3)
        landlord = w.create_agent(needs=CALM, money=0, inventory=EMPTY)
        tenant = w.create_agent(needs=CALM, money=100, inventory=EMPTY)
        house = w.housing.new_house(landlord, 0)
        w.housing.move_in(tenant, house)
        rent = price_at(w, 10_000) * w.housing.rent_yield
        w.housing.step(w)
        self.assertAlmostEqual(landlord.money, rent)
        tenant.money = 0
        for _ in range(3):
            w.tick += 1
            price_at(w, 10_000)
            w.housing.step(w)
        self.assertIsNone(tenant.home)
        self.assertEqual(w.housing.evictions, 1)


class BuyingTests(unittest.TestCase):
    def test_an_agent_buys_a_vacant_house_for_sale_once_it_can_pay_on_top_of_its_budget(self):
        w = world()
        builder = w.create_agent(needs=CALM, money=0, inventory=EMPTY)
        buyer = w.create_agent(needs=CALM, money=50_000, inventory=EMPTY)
        house = w.housing.new_house(builder, 0)
        house.for_sale = True
        price_at(w, 20_000)
        w.housing.step(w)
        self.assertIs(house.owner, buyer)
        self.assertIs(buyer.home, house)
        self.assertAlmostEqual(builder.money, 20_000)
        self.assertAlmostEqual(buyer.money, 30_000)

    def test_only_an_agent_with_a_home_of_its_own_buys_more_to_let(self):
        w = world(deposit_rate=0)
        seller = w.create_agent(needs=CALM, money=0, inventory=EMPTY)
        tenant = w.create_agent(needs=CALM, money=0, inventory=EMPTY)
        renter = w.create_agent(needs=CALM, money=1e6, inventory=EMPTY)     # rich, but rents
        let = w.housing.new_house(seller, 0)
        w.housing.move_in(tenant, let)
        let.for_sale = True
        w.housing.move_in(renter, w.housing.new_house(seller, 0))
        price_at(w, 20_000)
        w.housing.step(w)
        self.assertIs(let.owner, seller)                    # it can't: no home of its own
        own = w.housing.new_house(None, 0)
        own.for_sale = True
        w.tick += 1
        price_at(w, 20_000)
        w.housing.step(w)                                    # buys a home first...
        self.assertIs(renter.home.owner, renter)
        w.tick += 1
        price_at(w, 20_000)
        w.housing.step(w)                                    # ... then one to let
        self.assertEqual(len(renter.houses), 2)
        self.assertIs(let.occupant, tenant)                  # (a tenant stays when its house is sold)

    def test_the_price_never_goes_below_the_minimum(self):
        w = World(seed=3, rules=Rules.from_dict({"agents": 20}))
        w.spawn_random_agents()
        self.assertGreaterEqual(w.housing.price(w), w.housing.min_price(w))
        self.assertGreater(w.housing.min_price(w), max(w.current_prices()[g] for g in w.rules.active_goods))


class BuildingTests(unittest.TestCase):
    def test_homebuilders_turn_housing_units_into_houses_for_sale(self):
        w = world(house_units=10)
        builder = w.create_agent(needs=CALM, money=0, inventory={**EMPTY, "housing": 25})
        price_at(w, 10_000)
        w.housing.step(w)
        self.assertEqual(len(builder.houses), 2)
        self.assertTrue(all(h.for_sale for h in builder.houses))
        self.assertEqual(builder.inventory.count("housing"), 5)


class EstateTests(unittest.TestCase):
    def test_a_dead_owners_houses_go_to_a_buyer_nearby_or_to_public_housing(self):
        w = world()
        dead = w.create_agent(needs=CALM, money=0, inventory=EMPTY, x=10, y=10)
        rich = w.create_agent(needs=CALM, money=1e6, inventory=EMPTY, x=20, y=10)
        a, b = w.housing.new_house(dead, 0), w.housing.new_house(dead, 0)
        price_at(w, 600_000)
        w.remove_agent(dead)
        w.housing.on_death(w, dead, [rich])
        self.assertIs(a.owner, rich)
        self.assertIsNone(b.owner)                         # nobody else could pay: public housing


if __name__ == "__main__":
    unittest.main()
