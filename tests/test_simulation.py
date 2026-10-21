import math
import unittest

from simulation import Agent, Inventory, World, economy
from simulation.rules import Rules
from simulation.modules import NeedsDecay, Production


def no_invest():
    """These tests check other mechanics: no assets (their output would change needs), no
    asset purchases (log lines, spent money) and no surplus selling (changes where agents walk)."""
    return Rules.from_dict({"investing_enabled": False, "selling_enabled": False,
                            "assets": {"food": 0, "water": 0, "games": 0}})


def bare_world():
    """World with no random agents; tests place their own."""
    return World(rules=no_invest(), seed=1)


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

    def test_prices_follow_the_formula_and_scarcity(self):
        a = Agent(0, 0, money=300, inventory=Inventory({"food": 60, "water": 10, "games": 30}))
        prices = economy.market_prices([a])
        # 300 money / 100 units = 3 per unit, times (1 - share)
        self.assertAlmostEqual(prices["food"], 3 * 0.4)
        self.assertAlmostEqual(prices["water"], 3 * 0.9)
        self.assertAlmostEqual(prices["games"], 3 * 0.7)
        self.assertGreater(prices["water"], prices["games"])  # scarcest is dearest

    def test_no_goods_means_zero_prices(self):
        self.assertEqual(economy.market_prices([Agent(0, 0, money=50)]),
                         {"food": 0.0, "water": 0.0, "games": 0.0})

    def test_barter_settles_the_price_difference_in_money(self):
        a = Agent(0, 0, thirst=0.8, money=10, inventory=Inventory({"food": 20}))
        b = Agent(0, 0, hunger=0.8, money=10, inventory=Inventory({"water": 20}))
        prices = {"food": 1.0, "water": 1.5, "games": 1.0}
        economy.trade(a, b, prices, no_invest())
        # a buys 6 water paying with food (what b needs), topping up 0.5 per unit since
        # water is dearer. That covers b's hunger too, so b buys nothing back.
        self.assertEqual(a.inventory.to_dict(), {"food": 14})
        self.assertEqual(b.inventory.to_dict(), {"water": 14})
        self.assertAlmostEqual(a.thirst, 0.2)
        self.assertAlmostEqual(b.hunger, 0.2)
        self.assertAlmostEqual(a.money, 7)
        self.assertAlmostEqual(b.money, 13)

    def test_trade_falls_back_to_money_at_market_price(self):
        buyer = Agent(0, 0, hunger=0.7, money=10)
        seller = Agent(0, 0, inventory=Inventory({"food": 3}))
        economy.trade(buyer, seller, {"food": 2.5, "water": 1, "games": 1}, no_invest())
        self.assertEqual(seller.inventory.count("food"), 0)  # only had 3 of the 5 wanted
        self.assertAlmostEqual(buyer.money, 2.5)
        self.assertAlmostEqual(seller.money, 7.5)
        self.assertAlmostEqual(buyer.hunger, 0.4)

    def test_buyer_stops_when_it_cannot_afford_more(self):
        buyer = Agent(0, 0, hunger=0.7, money=5)
        seller = Agent(0, 0, inventory=Inventory({"food": 10}))
        economy.trade(buyer, seller, {"food": 2, "water": 1, "games": 1}, no_invest())
        self.assertEqual(buyer.inventory.count("food"), 0)  # bought 2, ate them
        self.assertAlmostEqual(buyer.money, 1)
        self.assertAlmostEqual(buyer.hunger, 0.5)

    def test_seller_keeps_what_it_needs_itself(self):
        buyer = Agent(0, 0, hunger=0.9, money=100)
        seller = Agent(0, 0, hunger=0.45, inventory=Inventory({"food": 5}))
        economy.trade(buyer, seller, {"food": 1, "water": 1, "games": 1}, no_invest())
        self.assertEqual(seller.inventory.count("food"), 2)  # reserve for 0.45 -> below 0.3


class ProductionTests(unittest.TestCase):
    def test_one_unit_every_n_steps(self):
        world = bare_world()
        agent = world.add_agent(Agent(0, 0, modules=[Production({"food": 3, "water": 0, "games": 10})]))
        for _ in range(9):
            world.step()
        self.assertEqual(agent.inventory.to_dict(), {"food": 3})


class ConfigurationTests(unittest.TestCase):
    def test_create_agent_with_custom_rates_and_production(self):
        world = bare_world()
        agent = world.create_agent(rates={"thirst": 0.05}, production={"water": 2},
                                   needs={"hunger": 0, "sleep": 0, "thirst": 0, "boredom": 0},
                                   inventory={"food": 0, "water": 0, "games": 0})
        for _ in range(4):
            world.step()
        self.assertAlmostEqual(agent.thirst, 0.2)
        self.assertAlmostEqual(agent.hunger, 0.04)  # default rate untouched
        self.assertEqual(agent.inventory.count("water"), 2)

    def test_configure_existing_agent(self):
        world = bare_world()
        agent = world.create_agent(needs={"hunger": 0, "sleep": 0, "thirst": 0, "boredom": 0},
                                   inventory={"food": 0, "water": 0, "games": 0})
        world.update_agent(agent, production={"food": 1, "games": 0}, rates={"hunger": 0})
        for _ in range(5):
            world.step()
        self.assertEqual([agent.inventory.count(r) for r in ("food", "water", "games")], [5, 0, 0])
        self.assertEqual(agent.hunger, 0)
        modules = agent.to_dict()["modules"]
        self.assertEqual(modules["Production"]["intervals"], {"food": 1, "water": 10, "games": 0})
        self.assertEqual(modules["NeedsDecay"]["rates"]["hunger"], 0)


class RestTests(unittest.TestCase):
    def test_tired_agent_stops_and_recovers_until_below_target(self):
        world = bare_world()
        agent = world.create_agent(needs={"sleep": 0.6, "hunger": 0, "thirst": 0, "boredom": 0}, x=500, y=500)
        positions = set()
        for _ in range(7):  # 0.6 -> 0.25 at 0.05/step
            world.step()
            positions.add((agent.x, agent.y))
            self.assertEqual(agent.activity, "sleeping")
        self.assertEqual(positions, {(500, 500)})
        self.assertAlmostEqual(agent.sleep, 0.25)
        world.step()
        self.assertNotEqual(agent.activity, "sleeping")
        self.assertNotEqual((agent.x, agent.y), (500, 500))

    def test_sleep_does_not_start_until_above_threshold(self):
        world = bare_world()
        agent = world.create_agent(needs={"sleep": 0.45}, rates={"sleep": 0.02})
        world.step()
        self.assertFalse(agent.sleeping)  # 0.47
        for _ in range(2):
            world.step()                  # 0.49, 0.51
        self.assertFalse(agent.sleeping)
        world.step()                      # was 0.51 at the start of the step -> rests
        self.assertTrue(agent.sleeping)
        self.assertAlmostEqual(agent.sleep, 0.46)

    def test_sleep_recovery_is_editable(self):
        world = bare_world()
        agent = world.create_agent(needs={"sleep": 0.9}, sleep_recovery=0.2)
        world.step()
        self.assertAlmostEqual(agent.sleep, 0.7)
        world.update_agent(agent, sleep_recovery=0.1)
        world.step()
        self.assertAlmostEqual(agent.sleep, 0.6)
        self.assertEqual(agent.to_dict()["modules"]["Rest"]["recovery"], 0.1)

    def test_sleeping_agent_can_still_be_reached_and_trade(self):
        world = bare_world()
        sleeper = world.create_agent(needs={"sleep": 0.9}, x=500, y=500)
        thirsty = world.create_agent(inventory={"water": 0}, needs={"thirst": 0.9, "sleep": 0}, x=400, y=500,
                                     movement=20)
        for _ in range(10):
            world.step()
        self.assertTrue(any(f"{thirsty.name} got" in e["message"] for e in world.events))
        self.assertEqual((sleeper.x, sleeper.y), (500, 500))


class LifeTests(unittest.TestCase):
    def test_agent_dies_when_hunger_or_thirst_reaches_one(self):
        for need in ("hunger", "thirst"):
            world = bare_world()
            doomed = world.create_agent(inventory={"food": 0, "water": 0}, needs={need: 0.99}, rates={need: 0.02})
            survivor = world.create_agent(x=900, y=900)
            survivor.x = 900  # far from doomed: no chance to trade first
            doomed.x, doomed.y = 10, 10
            world.step()
            self.assertEqual(world.agents, [survivor])
            self.assertIn(f"{doomed.name} died of {need}", world.events[-1]["message"])

    def test_eating_in_time_prevents_death(self):
        world = bare_world()
        agent = world.create_agent(needs={"hunger": 0.99}, rates={"hunger": 0.02})
        world.step()
        self.assertIn(agent, world.agents)
        self.assertLess(agent.hunger, 0.3)

    def test_boredom_at_one_depresses_until_below_target(self):
        world = bare_world()
        agent = world.create_agent(inventory={"games": 0}, needs={"boredom": 0.99, "sleep": 0.9},
                                   movement=21, sleep_recovery=0.1, rates={"boredom": 0.02, "sleep": 0})
        world.step()
        self.assertTrue(agent.depressed)
        self.assertEqual(agent.speed, 10)
        self.assertIn("became depressed", world.events[-1]["message"])
        before = agent.sleep
        world.step()                      # still resting: half of 0.1
        self.assertAlmostEqual(before - agent.sleep, 0.05)
        agent.inventory.add("games", 10)
        world.step()                      # plays 8 games: boredom 1.0 -> 0.2
        self.assertFalse(agent.depressed)
        self.assertEqual(agent.speed, 21)

    def test_depressed_agent_moves_at_half_speed(self):
        world = bare_world()
        agent = world.create_agent(movement=20, x=100, y=100)
        agent.depressed = True
        agent.move_towards(500, 100, world)
        self.assertEqual(agent.x, 110)


class EditingTests(unittest.TestCase):
    def test_update_every_field(self):
        world = bare_world()
        agent = world.create_agent()
        world.update_agent(agent, name="Bob", x=10, y=2000, needs={"sleep": 0.7}, inventory={"games": 3},
                           money=12.5, movement=40, production={"water": 2}, rates={"boredom": 0.1})
        d = agent.to_dict()
        self.assertEqual((d["name"], d["x"], d["y"], d["needs"]["sleep"]), ("Bob", 10, 1024, 0.7))
        self.assertEqual((d["inventory"]["games"], d["money"], d["movement"]), (3, 12.5, 40))
        self.assertEqual(d["modules"]["Production"]["intervals"]["water"], 2)
        self.assertEqual(d["modules"]["NeedsDecay"]["rates"]["boredom"], 0.1)

    def test_remove_agent_keeps_ids_unique(self):
        world = bare_world()
        world.spawn_random_agents(3)
        world.remove_agent(world.agents[0])
        new = world.create_agent()
        self.assertEqual([a.id for a in world.agents], [2, 3, 4])
        self.assertEqual(new.name, "Agent 4")


class WorldTests(unittest.TestCase):
    def test_default_agent_resources(self):
        world = bare_world()
        agent = world.create_agent()
        self.assertEqual(agent.inventory.to_dict(), {"food": 100, "water": 100, "games": 100})
        self.assertEqual(agent.money, 100.0)

    def test_agents_stay_in_box_and_within_movement(self):
        world = World(rules=no_invest(), seed=7)
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
            world = World(rules=no_invest(), seed=seed)
            seeker = world.create_agent(inventory={"water": 0}, needs={"thirst": 0.6},
                                        rates={"thirst": 0.005}, production={"water": 0},
                                        movement=5)  # survives the 45-step chase
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

    def test_seeker_retargets_to_the_closest_agent_every_step(self):
        world = bare_world()
        seeker = world.create_agent(inventory={"water": 0}, needs={"thirst": 0.9}, movement=5, x=500, y=500)
        first = world.create_agent(movement=1, x=600, y=500)    # closest at the start
        second = world.create_agent(movement=1, x=600, y=500)
        world.step()
        self.assertEqual(seeker.target_id, first.id)
        second.x, second.y = 480, 500                           # now another agent is closer
        world.step()
        self.assertEqual(seeker.target_id, second.id)
        self.assertEqual(seeker.x, 500)                         # it turned around toward it

    def test_seeker_skips_agents_without_spare_and_goes_to_a_seller(self):
        world = bare_world()
        thirsty = world.create_agent(inventory={"water": 0}, needs={"thirst": 0.9}, movement=5, x=500, y=500)
        dry = world.create_agent(inventory={"water": 0}, movement=1, x=550, y=500)       # closer, no water
        seller = world.create_agent(inventory={"water": 50}, needs={"thirst": 0}, movement=1, x=300, y=500)
        world.step()
        self.assertEqual((thirsty.activity, thirsty.target_id, thirsty.seeking_for), ("seeking", seller.id, "water"))
        self.assertEqual(thirsty.x, 495)  # walked away from the dry agent, toward the seller

    def test_most_urgent_need_is_sought_first(self):
        world = bare_world()
        agent = world.create_agent(inventory={"water": 0, "food": 0}, needs={"thirst": 0.9, "hunger": 0.6},
                                   x=500, y=500)
        world.create_agent(inventory={"food": 50, "water": 0}, needs={"hunger": 0}, x=520, y=500)
        water_seller = world.create_agent(inventory={"water": 50, "food": 0}, needs={"thirst": 0}, x=900, y=500)
        world.step()
        self.assertEqual((agent.target_id, agent.seeking_for), (water_seller.id, "water"))

    def test_nobody_to_buy_from_means_searching(self):
        world = bare_world()
        agent = world.create_agent(inventory={"water": 0}, needs={"thirst": 0.9}, x=500, y=500)
        world.create_agent(inventory={"water": 0}, x=900, y=900)
        world.step()
        self.assertEqual((agent.activity, agent.target_id), ("searching", None))

    def test_bump_without_needs_is_ignored(self):
        world = bare_world()
        calm = {"hunger": 0, "sleep": 0, "thirst": 0, "boredom": 0}
        world.create_agent(needs=calm, x=100, y=100, movement=1)
        world.create_agent(needs=calm, x=105, y=100, movement=1)
        world.step()
        self.assertEqual(world.events, [])
        self.assertEqual(world.cooldowns, {})

    def test_failed_trade_explains_why_and_agents_do_not_leave(self):
        world = bare_world()
        a = world.create_agent(inventory={"water": 0}, needs={"thirst": 0.9}, x=100, y=100, movement=1)
        b = world.create_agent(inventory={"water": 0}, x=105, y=100, movement=1)
        world.step()
        self.assertIn(f"No trade: {a.name} still needs 7 water: {b.name} has none", world.events[-1]["message"])
        self.assertNotEqual(a.activity, "leaving")
        self.assertTrue(world.in_cooldown(a, b))

    def test_contact_counts_as_soon_as_an_agent_moves_onto_another(self):
        world = bare_world()
        seeker = world.create_agent(inventory={"water": 0}, needs={"thirst": 0.9}, movement=20)
        target = world.create_agent(movement=20)
        seeker.x, seeker.y, target.x, target.y = 100, 100, 115, 100
        world.step()  # seeker moves first and lands on target; target hasn't moved away yet
        self.assertIn(f"{seeker.name} got", world.events[0]["message"])

    def test_same_seed_is_reproducible(self):
        a, b = World(rules=no_invest(), seed=3), World(rules=no_invest(), seed=3)
        a.spawn_random_agents(3)
        b.spawn_random_agents(3)
        for _ in range(300):
            a.step(); b.step()
        self.assertEqual(a.to_dict(), b.to_dict())


if __name__ == "__main__":
    unittest.main()
