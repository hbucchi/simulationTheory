"""The World: a WIDTH x HEIGHT box holding agents and advancing time in steps."""

import math
import random
from collections import deque

from . import distributions, economy
from .agent import Agent
from .inventory import Inventory
from .modules import Consume, Mood, Navigate, NeedsDecay, Production, Rest
from .rules import SPREADS, Rules

AGENT_COLORS = ["#e4572e", "#29335c", "#f3a712", "#669bbc", "#a8c686", "#8e44ad", "#16a085", "#c0392b"]


class World:
    # After two agents meet they walk apart for rules.depart_steps and ignore
    # each other for rules.cooldown_steps, so they don't instantly re-meet.
    # Departure = straight away from the partner, turned by a random angle in
    # [-MAX_TURN, +MAX_TURN]: a 180-degree window that never points back at them.
    MAX_TURN = math.radians(90)

    def __init__(self, width=1024, height=1024, seed=None, rules=None):
        self.width = width
        self.height = height
        self.rules = rules or Rules()
        # Two agents are "in touch" (able to interact) when their centres are
        # at most this many pixels apart. 12 = two dots of radius 6 touching.
        self.contact_distance = self.rules.contact_distance
        self.seed = seed
        self.rng = random.Random(seed)
        self.agents = []
        self.tick = 0
        self.events = []  # newest last; trimmed to keep the payload small
        self.cooldowns = {}  # frozenset({id_a, id_b}) -> tick until which they ignore each other
        # Average units per living agent of each resource, one entry per step, for the
        # last scarcity_window steps; scarcity = how much that average fell over the window.
        self.per_agent_history = {r: deque(maxlen=self.rules.scarcity_window + 1) for r in economy.RESOURCES}
        self.scarcity = {r: 0.0 for r in economy.RESOURCES}
        self.next_id = 1

    def clamp_position(self, x, y):
        return (min(max(x, 0.0), self.width), min(max(y, 0.0), self.height))

    def random_position(self):
        return (self.rng.uniform(0, self.width), self.rng.uniform(0, self.height))

    def add_agent(self, agent):
        agent.id = self.next_id
        self.next_id += 1
        agent.name = agent.name or f"Agent {agent.id}"
        if agent.color is None:
            agent.color = AGENT_COLORS[(agent.id - 1) % len(AGENT_COLORS)]
        self.agents.append(agent)
        return agent

    def create_agent(self, *, inventory=None, money=None, production=None,
                     rates=None, sleep_recovery=None, movement=None, needs=None, name=None,
                     x=None, y=None):
        """Create an agent with the standard modules. Anything omitted comes from the rules.

        ``inventory`` / ``production`` override per resource;
        ``rates`` overrides how fast each need grows per step;
        ``sleep_recovery`` is how much sleep drops per step while resting;
        ``needs`` overrides starting need levels;
        ``x`` / ``y`` default to a random position.
        Values not given are drawn from the rules' spreads (see distributions.py).
        """
        r = self.rules

        def draw(spec, whole=False, field=None):
            low, high = SPREADS[field][1:3] if field else (-math.inf, math.inf)
            return distributions.sample(spec, self.rng, whole, low, high)

        rx, ry = self.random_position()
        x, y = self.clamp_position(rx if x is None else x, ry if y is None else y)
        start_needs = {n: round(draw(r.start_needs, field="start_needs"), 2)
                       for n in ("hunger", "sleep", "thirst", "boredom")}
        start_needs.update(needs or {})
        # Rest runs first so a resting agent's sleep never grows that step.
        modules = [Rest(draw(r.sleep_recovery, field="sleep_recovery") if sleep_recovery is None else sleep_recovery),
                   NeedsDecay({**{n: draw(v, field="rates") for n, v in r.rates.items()}, **(rates or {})}),
                   Production({**{k: draw(v, True, "production") for k, v in r.production.items()},
                               **(production or {})}),
                   Consume()]
        if r.depression_enabled:
            modules.append(Mood())
        modules.append(Navigate())
        agent = Agent(
            x, y, name=name, **start_needs,
            money=round(draw(r.money, field="money"), 2) if money is None else money,
            movement=draw(r.movement, True, "movement") if movement is None else movement,
            inventory=Inventory({**{k: draw(v, True, "inventory") for k, v in r.inventory.items()},
                                 **(inventory or {})}),
            modules=modules,
        )
        agent.depression_factor = r.depression_factor
        return self.add_agent(agent)

    def update_agent(self, agent, *, name=None, x=None, y=None, needs=None, inventory=None,
                     money=None, movement=None, production=None, rates=None, sleep_recovery=None):
        """Change any of an existing agent's settings; omitted fields stay as they are."""
        if name:
            agent.name = name
        agent.x, agent.y = self.clamp_position(agent.x if x is None else x, agent.y if y is None else y)
        for need, level in (needs or {}).items():
            setattr(agent, need, level)
        for resource, qty in (inventory or {}).items():
            agent.inventory.set(resource, qty)
        if money is not None:
            agent.money = float(money)
        if movement is not None:
            agent.movement = int(movement)
        for module in agent.modules:
            if isinstance(module, Production) and production:
                module.set_intervals(production)
            if isinstance(module, NeedsDecay) and rates:
                module.rates.update(rates)
            if isinstance(module, Rest) and sleep_recovery is not None:
                module.recovery = sleep_recovery
        return agent

    def remove_agent(self, agent):
        self.agents.remove(agent)
        for other in self.agents:
            if other.target_id == agent.id:
                other.target_id = None

    def spawn_random_agents(self, count=None):
        """Create the starting agents. Tiered inventory/money is shared out between them
        exactly (e.g. the top 1% really hold 50%); other values are drawn per agent."""
        n = self.rules.agents if count is None else count
        r = self.rules
        money = distributions.allocate(r.money, n, self.rng, False, *SPREADS["money"][1:3])
        stock = {k: distributions.allocate(v, n, self.rng, True, *SPREADS["inventory"][1:3])
                 for k, v in r.inventory.items()}
        for i in range(n):
            self.create_agent(money=round(money[i], 2), inventory={k: v[i] for k, v in stock.items()})

    def in_cooldown(self, a, b):
        return self.cooldowns.get(frozenset((a.id, b.id)), -1) >= self.tick

    def agent_by_id(self, agent_id):
        return next((a for a in self.agents if a.id == agent_id), None)

    def seekers_of(self, agent):
        """Agents currently seeking ``agent`` (and allowed to meet it)."""
        return [o for o in self.agents
                if o.activity == "seeking" and o.target_id == agent.id and not self.in_cooldown(agent, o)]

    def nearest_seller(self, agent, stockpile=False):
        """Closest agent with spare of what ``agent`` needs: (seller, resource) or (None, None).

        Needs are tried most urgent first, so a thirsty and slightly hungry agent
        looks for water before food. With ``stockpile`` it looks instead for
        resources it is short of in its reserve. Agents it has just met are skipped.
        """
        if stockpile:
            wanted = [r for r in economy.RESOURCES
                      if economy.stockpile_shortfall(agent, r, self.rules, self.scarcity) > 0]
            wanted.sort(key=lambda r: self.scarcity[r], reverse=True)
        else:
            wanted = [r for r in economy.RESOURCES if economy.demand(agent, r, self.rules) > 0]
            wanted.sort(key=lambda r: getattr(agent, economy.NEED_FOR_RESOURCE[r]), reverse=True)
        for resource in wanted:
            sellers = [o for o in self.agents if o is not agent and not self.in_cooldown(agent, o)
                       and economy.spare(o, resource, self.rules, self.scarcity) > 0]
            if sellers:
                return min(sellers, key=agent.distance_to), resource
        return None, None

    def update_scarcity(self):
        """Record average units per agent and how much it fell over the scarcity window."""
        n = len(self.agents)
        for r, history in self.per_agent_history.items():
            history.append(sum(a.inventory.count(r) for a in self.agents) / n if n else 0.0)
            past, now = history[0], history[-1]
            full = len(history) == history.maxlen
            self.scarcity[r] = max(0.0, 1 - now / past) if full and past > 0 else 0.0

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
        self.update_scarcity()
        for agent in list(self.agents):
            if agent not in self.agents:
                continue
            agent.step(self)
            if self.check_death(agent):
                continue
            for other in self.agents:
                if (other is not agent and agent.distance_to(other) <= self.contact_distance
                        and not self.in_cooldown(agent, other)):
                    self.interact(agent, other)

    def check_death(self, agent):
        """Hunger or thirst at 1.00 (after eating/drinking what it had) kills the agent.

        It disappears along with its inventory and money. Off when the rules disable death.
        """
        if not self.rules.death_enabled:
            return False
        for need in ("hunger", "thirst"):
            if getattr(agent, need) >= economy.CRITICAL_LEVEL:
                self.remove_agent(agent)
                cause = "hunger" if need == "hunger" else "thirst"
                self.log(f"{agent.name} died of {cause}")
                return True
        return False

    def interact(self, a, b):
        """Two agents touched. If either needs something they trade, then walk apart.

        Afterwards the pair ignores each other for rules.cooldown_steps, so a needy
        agent moves on to the next-closest agent instead of retrying the same one.
        """
        rules = self.rules
        scarcity = self.scarcity
        if not (economy.wants_anything(a, rules, scarcity) or economy.wants_anything(b, rules, scarcity)):
            return  # a casual bump: nobody needs anything
        prices = economy.market_prices(self.agents, rules)
        deals = economy.trade(a, b, prices, rules, self.rng, scarcity)
        for buyer, seller, bought, paid, stocked in deals:
            note = f" ({economy.describe(stocked)} to stockpile)" if stocked else ""
            self.log(f"{buyer.name} got {economy.describe(bought)} from {seller.name} "
                     f"for {economy.describe_payment(paid)}{note}")
        for reason in economy.unmet(a, b, rules, scarcity) + economy.unmet(b, a, rules, scarcity):
            self.log(f"No trade: {reason}")

        self.cooldowns[frozenset((a.id, b.id))] = self.tick + rules.cooldown_steps
        if deals:
            self.depart(a, b)

    def depart(self, a, b):
        """Send a and b off in roughly opposite directions."""
        away = math.atan2(a.y - b.y, a.x - b.x)
        if a.x == b.x and a.y == b.y:
            away = self.rng.uniform(-math.pi, math.pi)
        steps = self.rules.depart_steps
        a.depart(away + self.rng.uniform(-self.MAX_TURN, self.MAX_TURN), steps)
        b.depart(away + math.pi + self.rng.uniform(-self.MAX_TURN, self.MAX_TURN), steps)

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
            "rules": self.rules.to_dict(),
            "market": {
                "prices": economy.market_prices(self.agents, self.rules),
                # Average units per agent over the scarcity window (oldest first) and how much it fell.
                "per_agent_history": {r: list(h) for r, h in self.per_agent_history.items()},
                "scarcity": self.scarcity,
                "stockpiling": {r: self.rules.stockpiling_enabled and d >= self.rules.scarcity_trigger
                                for r, d in self.scarcity.items()},
                "money": sum(a.money for a in self.agents),
                "units": {r: sum(a.inventory.count(r) for a in self.agents) for r in economy.RESOURCES},
            },
            "agents": [dict(a.to_dict(self.rules), reserve={
                r: economy.stockpile_target(a, r, self.rules, self.scarcity) for r in economy.RESOURCES})
                for a in self.agents],
            # Only pairs that can interact; pairs in cooldown just overlap.
            "contacts": [[a.id, b.id] for a, b in self.contacts() if not self.in_cooldown(a, b)],
            "events": self.events[-50:],
        }
