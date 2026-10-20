import unittest

from simulation import Agent, Inventory, World
from simulation.modules import NeedsDecay, Wander


class AgentTests(unittest.TestCase):
    def test_needs_are_clamped_to_unit_range(self):
        agent = Agent(0, 0, hunger=1.7, thirst=-0.3)
        self.assertEqual(agent.hunger, 1.0)
        self.assertEqual(agent.thirst, 0.0)

    def test_move_respects_movement_and_box(self):
        world = World(seed=1)
        agent = world.add_agent(Agent(1020, 500, movement=10))
        agent.move_towards(2000, 500, world)
        self.assertEqual((agent.x, agent.y), (1024, 500))
        agent.move_towards(0, 500, world)
        self.assertAlmostEqual(agent.x, 1014)

    def test_needs_decay_each_step(self):
        world = World(seed=1)
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


class WorldTests(unittest.TestCase):
    def test_agents_stay_in_box_and_within_movement(self):
        world = World(seed=7)
        world.spawn_random_agents(3)
        for _ in range(500):
            before = [(a.x, a.y) for a in world.agents]
            world.step()
            for (bx, by), a in zip(before, world.agents):
                self.assertTrue(0 <= a.x <= world.width and 0 <= a.y <= world.height)
                self.assertLessEqual(((a.x - bx) ** 2 + (a.y - by) ** 2) ** 0.5, a.movement + 1e-9)

    def test_contact_triggers_interaction_event(self):
        world = World(seed=1)
        world.add_agent(Agent(100, 100))
        world.add_agent(Agent(105, 100))
        world.add_agent(Agent(900, 900))
        world.step()
        self.assertEqual(len(world.contacts()), 1)
        self.assertIn("Agent 1 and Agent 2 met", world.events[-1]["message"])

    def test_same_seed_is_reproducible(self):
        a, b = World(seed=3), World(seed=3)
        a.spawn_random_agents(3)
        b.spawn_random_agents(3)
        for _ in range(50):
            a.step(); b.step()
        self.assertEqual(a.to_dict(), b.to_dict())


if __name__ == "__main__":
    unittest.main()
