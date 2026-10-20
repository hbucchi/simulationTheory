import math
import unittest

from simulation import Agent, Inventory, World, economy
from simulation.modules import NeedsDecay, Production


def bare_world():
    """World with no random agents; tests place their own."""
    return World(seed=1)


class AgentTests(unittest.TestCase):
    def test_needs_are_clamped_to_unit_range(self):
        agent = Agent(0, 0, hunger=1.7, thirst=-0.3)
        self.assertEqual(agent.hunger, 1.0)
        self.assertEqual(agent.thirst, 0.0)

    def test_move_respects_movement_and_box(self):
        world = bare_world()
        agent = world.add_agent(Agent(1020, 500, movement=10))
        agent.move_towards(2000, 500, world)
        self.assertEqual((agent.x, agent.y), (1024, 500))
        agent.move_towards(0, 500, world)
        self.assertAlmostEqual(agent.x, 1014)

    def test_needs_decay_each_step(self):
        world = bare_world()
        agent = world.add_agent(Agent(10, 10, modules=[NeedsDecay({"hunger": 0.1})]))
        world.step()
        self.assertAlmostEqual(agent.hunger, 0.1)


class InventoryTests(unittest.TestCase):
    def test_add_and_remove(self):
        inv = Inventory()
        inv.add("water", 2)
        self.assertTrue(inv.remove("water"))
        self.assertFalse(inv.remove("water", 5))
        self.assertEqual(inv.to_dict(), {"water": 1})


class EconomyTests(unittest.TestCase):
    def test_units_to_satisfy_goes_strictly_below_target(self):
        self.assertEqual(economy.units_to_satisfy(0.2), 0)
        self.assertEqual(economy.units_to_satisfy(0.3), 1)
        self.assertEqual(economy.units_to_satisfy(0.55), 3)   # 0.55 -> 0.25
        self.assertEqual(economy.units_to_satisfy(0.6), 4)    # 0.6 -> 0.2 (0.3 is not below)
        self.assertEqual(economy.units_to_satisfy(1.0), 8)

    def test_consume_only_above_threshold(self):
        agent = Agent(0, 0, hunger=0.5, thirst=0.75, inventory=Inventory({"food": 10, "water": 10}))
        economy.consume(agent)
        self.assertEqual(agent.hunger, 0.5)
        self.assertAlmostEqual(agent.thirst, 0.25)
        self.assertEqual(agent.inventory.count("water"), 5)

    def test_trade_barters_what_the_other_needs(self):
        a = Agent(0, 0, thirst=0.8, inventory=Inventory({"food": 20}))
        b = Agent(0, 0, hunger=0.8, inventory=Inventory({"water": 20}))
        economy.trade(a, b)
        # Each needed 6 units and paid with the thing the other needed, 1:1.
        self.assertEqual(a.inventory.to_dict(), {"food": 14})
        self.assertEqual(b.inventory.to_dict(), {"water": 14})
        self.assertAlmostEqual(a.thirst, 0.2)
        self.assertAlmostEqual(b.hunger, 0.2)
        self.assertEqual((a.money, b.money), (0, 0))

    def test_trade_falls_back_to_money(self):
        buyer = Agent(0, 0, hunger=0.7, money=10)
        seller = Agent(0, 0, inventory=Inventory({"food": 3}))
        economy.trade(buyer, seller)
        self.assertEqual(seller.inventory.count("food"), 0)  # only had 3 of the 5 wanted
        self.assertEqual((buyer.money, seller.money), (7, 3))
        self.assertAlmostEqual(buyer.hunger, 0.4)

    def test_seller_keeps_what_it_needs_itself(self):
        buyer = Agent(0, 0, hunger=0.9, money=100)
        seller = Agent(0, 0, hunger=0.45, inventory=Inventory({"food": 5}))
        economy.trade(buyer, seller)
        self.assertEqual(seller.inventory.count("food"), 2)  # reserve for 0.45 -> below 0.3


class ProductionTests(unittest.TestCase):
    def test_one_unit_every_n_steps(self):
        world = bare_world()
        agent = world.add_agent(Agent(0, 0, modules=[Production({"food": 3, "water": 0, "games": 10})]))
        for _ in range(9):
            world.step()
        self.assertEqual(agent.inventory.to_dict(), {"food": 3})


class WorldTests(unittest.TestCase):
    def test_default_agent_resources(self):
        world = bare_world()
        agent = world.create_agent()
        self.assertEqual(agent.inventory.to_dict(), {"food": 100, "water": 100, "games": 100})
        self.assertEqual(agent.money, 100.0)

    def test_agents_stay_in_box_and_within_movement(self):
        world = World(seed=7)
        world.spawn_random_agents(3)
        for _ in range(500):
            before = [(a.x, a.y) for a in world.agents]
            world.step()
            for (bx, by), a in zip(before, world.agents):
                self.assertTrue(0 <= a.x <= world.width and 0 <= a.y <= world.height)
                self.assertLessEqual(math.hypot(a.x - bx, a.y - by), a.movement + 1e-9)

    def test_needy_agent_seeks_nearest_and_trades_then_both_leave(self):
        world = bare_world()
        thirsty = world.create_agent(inventory={"water": 0}, needs={"thirst": 0.9}, movement=20)
        near = world.create_agent(movement=5)
        far = world.create_agent(movement=5)
        thirsty.x, thirsty.y = 100, 100
        near.x, near.y = 200, 100
        far.x, far.y = 900, 900
        for _ in range(20):
            world.step()
            if any("got" in e["message"] for e in world.events):
                break
        self.assertIn(f"{thirsty.name} got", world.events[-1]["message"])
        self.assertIn(f"from {near.name}", world.events[-1]["message"])
        self.assertLess(thirsty.thirst, 0.3)
        self.assertEqual((thirsty.activity, near.activity), ("leaving", "leaving"))
        # Departure headings point away from each other (within the 180-degree window).
        away = math.atan2(thirsty.y - near.y, thirsty.x - near.x) if (thirsty.x, thirsty.y) != (near.x, near.y) else None
        if away is not None:
            diff = (thirsty.depart_heading - away + math.pi) % (2 * math.pi) - math.pi
            self.assertLessEqual(abs(diff), math.pi / 2 + 1e-9)
        # They ignore each other for a while.
        self.assertTrue(world.in_cooldown(thirsty, near))

    def test_slow_seeker_always_reaches_faster_agent(self):
        for seed in range(20):
            world = World(seed=seed)
            seeker = world.create_agent(inventory={"water": 0}, needs={"thirst": 0.9}, movement=5)
            runner = world.create_agent(movement=25)
            seeker.x, seeker.y, runner.x, runner.y = 50, 50, 1000, 1000
            for _ in range(60):  # 1344 px apart, closing at 30 px/step -> 45 steps
                world.step()
                if world.events:
                    break
            self.assertIn("got", world.events[-1]["message"], f"seed {seed}")

    def test_sought_agent_walks_toward_its_seeker(self):
        world = bare_world()
        seeker = world.create_agent(inventory={"water": 0}, needs={"thirst": 0.9}, movement=5)
        other = world.create_agent(movement=10, needs={"thirst": 0, "hunger": 0, "boredom": 0})
        seeker.x, seeker.y, other.x, other.y = 100, 500, 900, 500
        world.step()
        self.assertEqual((seeker.activity, seeker.target_id), ("seeking", other.id))
        self.assertEqual((other.activity, other.target_id), ("meeting", seeker.id))
        self.assertEqual((seeker.x, other.x), (105, 890))

    def test_seeker_keeps_its_target(self):
        world = bare_world()
        seeker = world.create_agent(inventory={"water": 0}, needs={"thirst": 0.9}, movement=5)
        first = world.create_agent(movement=1)
        second = world.create_agent(movement=1)
        seeker.x, seeker.y = 500, 500
        first.x, first.y = 600, 500     # nearest at the start
        second.x, second.y = 390, 500   # becomes nearer after one step toward `first`
        world.step()
        world.step()
        self.assertEqual(seeker.target_id, first.id)

    def test_contact_counts_as_soon_as_an_agent_moves_onto_another(self):
        world = bare_world()
        seeker = world.create_agent(inventory={"water": 0}, needs={"thirst": 0.9}, movement=20)
        target = world.create_agent(movement=20)
        seeker.x, seeker.y, target.x, target.y = 100, 100, 115, 100
        world.step()  # seeker moves first and lands on target; target hasn't moved away yet
        self.assertIn(f"{seeker.name} got", world.events[0]["message"])

    def test_same_seed_is_reproducible(self):
        a, b = World(seed=3), World(seed=3)
        a.spawn_random_agents(3)
        b.spawn_random_agents(3)
        for _ in range(300):
            a.step(); b.step()
        self.assertEqual(a.to_dict(), b.to_dict())


if __name__ == "__main__":
    unittest.main()
