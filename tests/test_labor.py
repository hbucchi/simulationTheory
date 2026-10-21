import unittest

from simulation import Inventory, World, economy
from simulation.rules import Rules

CALM = {"hunger": 0, "sleep": 0, "thirst": 0, "boredom": 0}
NO_ASSETS = {"food": 0, "water": 0, "games": 0}


def world_with(**rules):
    return World(seed=1, rules=Rules.from_dict({"assets": NO_ASSETS, "investing_enabled": False, **rules}))


class PerishableInventoryTests(unittest.TestCase):
    def test_batches_expire_after_their_lifetime(self):
        inv = Inventory(perishable={"labor": 10})
        inv.add("labor", 3)            # made at step 0: expires at 10
        inv.now = 5
        inv.add("labor", 2)            # made at step 5: expires at 15
        inv.now = 10
        self.assertEqual(inv.expire(), {"labor": 3})
        self.assertEqual(inv.count("labor"), 2)
        inv.now = 15
        inv.expire()
        self.assertEqual(inv.count("labor"), 0)

    def test_oldest_labour_is_used_first(self):
        inv = Inventory(perishable={"labor": 10})
        inv.add("labor", 1)
        inv.now = 4
        inv.add("labor", 1)
        self.assertEqual(inv.take("labor", 1.5), [(10, 1), (14, 0.5)])
        self.assertAlmostEqual(inv.amount("labor"), 0.5)

    def test_lifetime_zero_never_expires(self):
        inv = Inventory(perishable={"labor": 0})
        inv.add("labor", 2)
        inv.now = 10 ** 6
        self.assertEqual(inv.expire(), {})
        self.assertEqual(inv.count("labor"), 2)

    def test_counts_whole_units_and_other_items_are_unaffected(self):
        inv = Inventory({"food": 3}, perishable={"labor": 10})
        inv.add("labor", 2.5)
        self.assertEqual((inv.count("labor"), inv.amount("labor")), (2, 2.5))
        self.assertEqual(inv.to_dict(), {"food": 3, "labor": 2})


class LabourExpiryTests(unittest.TestCase):
    def test_unsold_unused_labour_expires(self):
        world = world_with(labor_lifetime=10, labor_rate=1)
        worker = world.create_agent(needs=CALM, rates=CALM, inventory={"labor": 0})
        for _ in range(50):
            world.step()
        # Only the last 10 steps of labour are still held; the rest expired.
        self.assertEqual(worker.inventory.count("labor"), 10)
        self.assertAlmostEqual(world.labor_expired, 40)

    def test_bought_labour_keeps_its_expiry_date(self):
        world = world_with(labor_lifetime=10)
        seller = world.create_agent(needs=CALM, inventory={"labor": 0})
        buyer = world.create_agent(needs=CALM, inventory={"labor": 0})
        seller.inventory.add("labor", 4)          # made at step 0: expires at 10
        economy.transfer(seller, buyer, "labor", 4)
        buyer.inventory.now = 10
        self.assertEqual(buyer.inventory.expire(), {"labor": 4})

    def test_labour_is_only_paid_to_a_seller_that_needs_it(self):
        rules = Rules.from_dict({"selling_enabled": False})
        buyer = World(seed=1).create_agent(inventory={"water": 0, "food": 0, "games": 0, "labor": 20},
                                           needs={**CALM, "thirst": 0.8}, money=0)
        seller = World(seed=1).create_agent(inventory={"water": 50}, needs=CALM)
        bought, paid, _, _ = economy.buy(buyer, seller, {"food": 1, "water": 1, "games": 1, "labor": 1}, rules)
        self.assertEqual(bought, {})                # no money, and the seller has no use for labour
        self.assertEqual(buyer.inventory.count("labor"), 20)

    def test_owner_with_assets_uses_and_hires_labour(self):
        world = world_with(labor_lifetime=10, labor_buffer_steps=5, asset_labor={"food": 1})
        owner = world.create_agent(needs=CALM, rates=CALM, labor_rate=0, inventory={"labor": 0}, assets={"food": 2})
        world.step()
        self.assertEqual(owner.labor_need, 2)
        self.assertEqual(economy.labor_target(owner, world.rules), 10)
        self.assertEqual(economy.demand(owner, "labor", world.rules), 10)   # empty: refill the buffer


if __name__ == "__main__":
    unittest.main()
