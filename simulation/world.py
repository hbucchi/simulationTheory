"""The World: a WIDTH x HEIGHT box holding agents and advancing time in steps."""

import math
import random

from . import economy
from .agent import Agent
from .inventory import Inventory
from .modules import Consume, Navigate, NeedsDecay, Production

AGENT_COLORS = ["#e4572e", "#29335c", "#f3a712", "#669bbc", "#a8c686", "#8e44ad", "#16a085", "#c0392b"]


class World:
    # After two agents meet they walk apart for DEPART_STEPS and ignore each
    # other for COOLDOWN_STEPS, so they don't instantly re-meet.
    DEPART_STEPS = 15
    COOLDOWN_STEPS = 60
    # Departure = straight away from the partner, turned by a random angle in
    # [-MAX_TURN, +MAX_TURN]: a 180-degree window that never points back at them.
    MAX_TURN = math.radians(90)

    def __init__(self, width=1024, height=1024, contact_distance=12, seed=None):
        self.width = width
        self.height = height
        # Two agents are "in touch" (able to interact) when their centres are
        # at most this many pixels apart. 12 = two dots of radius 6 touching.
        self.contact_distance = contact_distance
        self.seed = seed
        self.rng = random.Random(seed)
        self.agents = []
        self.tick = 0
        self.events = []  # newest last; trimmed to keep the payload small
        self.cooldowns = {}  # frozenset({id_a, id_b}) -> tick until which they ignore each other

    def clamp_position(self, x, y):
        return (min(max(x, 0.0), self.width), min(max(y, 0.0), self.height))

    def random_position(self):
        return (self.rng.uniform(0, self.width), self.rng.uniform(0, self.height))

    def add_agent(self, agent):
        agent.id = len(self.agents) + 1
        agent.name = agent.name or f"Agent {agent.id}"
        if agent.color is None:
            agent.color = AGENT_COLORS[len(self.agents) % len(AGENT_COLORS)]
        self.agents.append(agent)
        return agent

    def create_agent(self, *, inventory=None, money=economy.DEFAULT_MONEY, production=None,
                     rates=None, movement=None, needs=None, name=None):
        """Create an agent at a random position with the standard modules.

        ``inventory`` / ``production`` override the defaults per resource;
        ``rates`` overrides how fast each need grows per step;
        ``needs`` overrides starting need levels (otherwise random in [0, 0.5]).
        """
        x, y = self.random_position()
        start_needs = {n: round(self.rng.uniform(0, 0.5), 2) for n in ("hunger", "sleep", "thirst", "boredom")}
        start_needs.update(needs or {})
        agent = Agent(
            x, y, name=name, **start_needs,
            money=money,
            movement=movement if movement is not None else self.rng.randint(5, 25),
            inventory=Inventory({**economy.DEFAULT_INVENTORY, **(inventory or {})}),
            modules=[NeedsDecay(rates), Production(production), Consume(), Navigate()],
        )
        return self.add_agent(agent)

    def configure_agent(self, agent, *, production=None, rates=None):
        """Change an existing agent's production intervals and/or need growth rates."""
        for module in agent.modules:
            if isinstance(module, Production) and production:
                module.set_intervals(production)
            if isinstance(module, NeedsDecay) and rates:
                module.rates.update(rates)
        return agent

    def spawn_random_agents(self, count):
        for _ in range(count):
            self.create_agent()

    def in_cooldown(self, a, b):
        return self.cooldowns.get(frozenset((a.id, b.id)), -1) >= self.tick

    def agent_by_id(self, agent_id):
        return next((a for a in self.agents if a.id == agent_id), None)

    def seekers_of(self, agent):
        """Agents currently seeking ``agent`` (and allowed to meet it)."""
        return [o for o in self.agents
                if o.activity == "seeking" and o.target_id == agent.id and not self.in_cooldown(agent, o)]

    def nearest_partner(self, agent):
        """Closest other agent that ``agent`` hasn't just met, or None."""
        others = [o for o in self.agents if o is not agent and not self.in_cooldown(agent, o)]
        return min(others, key=agent.distance_to, default=None)

    def contacts(self):
        """All pairs of agents currently close enough to interact."""
        pairs = []
        for i, a in enumerate(self.agents):
            for b in self.agents[i + 1:]:
                if a.distance_to(b) <= self.contact_distance:
                    pairs.append((a, b))
        return pairs

    def step(self):
        """Advance the simulation by one tick.

        Agents act one after another, and contacts are checked right after
        each agent moves. Checking only at the end of the tick would let a
        seeker reach its target's spot and then see the target step away
        before the check ran.
        """
        self.tick += 1
        for agent in self.agents:
            agent.step(self)
            for other in self.agents:
                if (other is not agent and agent.distance_to(other) <= self.contact_distance
                        and not self.in_cooldown(agent, other)):
                    self.interact(agent, other)

    def interact(self, a, b):
        """Two agents touched: trade what they need, then walk apart."""
        deals = economy.trade(a, b)
        for buyer, seller, bought, paid in deals:
            self.log(f"{buyer.name} got {economy.describe(bought)} from {seller.name} "
                     f"for {economy.describe(paid)}")
        if not deals:
            self.log(f"{a.name} and {b.name} met (nothing to trade)")

        self.cooldowns[frozenset((a.id, b.id))] = self.tick + self.COOLDOWN_STEPS
        away = math.atan2(a.y - b.y, a.x - b.x)
        if a.x == b.x and a.y == b.y:
            away = self.rng.uniform(-math.pi, math.pi)
        a.depart(away + self.rng.uniform(-self.MAX_TURN, self.MAX_TURN), self.DEPART_STEPS)
        b.depart(away + math.pi + self.rng.uniform(-self.MAX_TURN, self.MAX_TURN), self.DEPART_STEPS)

    def log(self, message):
        self.events.append({"tick": self.tick, "message": message})
        del self.events[:-200]

    def to_dict(self):
        return {
            "tick": self.tick,
            "width": self.width,
            "height": self.height,
            "contact_distance": self.contact_distance,
            "seed": self.seed,
            "defaults": {
                "inventory": economy.DEFAULT_INVENTORY,
                "money": economy.DEFAULT_MONEY,
                "production": economy.DEFAULT_PRODUCTION,
                "rates": NeedsDecay.DEFAULT_RATES,
            },
            "agents": [a.to_dict() for a in self.agents],
            "contacts": [[a.id, b.id] for a, b in self.contacts()],
            "events": self.events[-50:],
        }
