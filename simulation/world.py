"""The World: a WIDTH x HEIGHT box holding agents and advancing time in steps."""

import random

from .agent import Agent
from .modules import NeedsDecay, Wander

AGENT_COLORS = ["#e4572e", "#29335c", "#f3a712", "#669bbc", "#a8c686", "#8e44ad", "#16a085", "#c0392b"]


class World:
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

    def spawn_random_agents(self, count):
        """Create ``count`` agents at random positions with random starting stats."""
        for _ in range(count):
            x, y = self.random_position()
            agent = Agent(
                x, y,
                hunger=round(self.rng.uniform(0, 0.5), 2),
                sleep=round(self.rng.uniform(0, 0.5), 2),
                thirst=round(self.rng.uniform(0, 0.5), 2),
                leisure=round(self.rng.uniform(0, 0.5), 2),
                money=round(self.rng.uniform(50, 200), 2),
                movement=self.rng.randint(5, 25),
            )
            agent.add_module(NeedsDecay()).add_module(Wander())
            self.add_agent(agent)

    def contacts(self):
        """All pairs of agents currently close enough to interact."""
        pairs = []
        for i, a in enumerate(self.agents):
            for b in self.agents[i + 1:]:
                if a.distance_to(b) <= self.contact_distance:
                    pairs.append((a, b))
        return pairs

    def step(self):
        """Advance the simulation by one tick: every agent acts, then contacts resolve."""
        self.tick += 1
        for agent in self.agents:
            agent.step(self)
        for a, b in self.contacts():
            self.interact(a, b)

    def interact(self, a, b):
        """Hook for agent-to-agent interaction (trading comes later). Logs for now."""
        self.log(f"{a.name} and {b.name} met at ({a.x:.0f}, {a.y:.0f})")

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
            "agents": [a.to_dict() for a in self.agents],
            "contacts": [[a.id, b.id] for a, b in self.contacts()],
            "events": self.events[-50:],
        }
