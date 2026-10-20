"""The Agent class: a dot in the box with needs, money, movement and an inventory."""

import math

from .inventory import Inventory

NEED_NAMES = ("hunger", "sleep", "thirst", "leisure")


def clamp(value, low, high):
    return max(low, min(high, value))


class Need:
    """Descriptor that keeps a need score clamped to [0.0, 1.0]."""

    def __set_name__(self, owner, name):
        self.attr = "_" + name

    def __get__(self, agent, owner=None):
        return self if agent is None else getattr(agent, self.attr)

    def __set__(self, agent, value):
        setattr(agent, self.attr, clamp(float(value), 0.0, 1.0))


class Agent:
    """A single simulated agent.

    Needs (hunger, sleep, thirst, leisure) are scores in [0.00, 1.00] where
    0.00 means fully satisfied and 1.00 means desperate.
    ``money`` is an unbounded float. ``movement`` is an integer: the maximum
    number of pixels the agent can travel in one step.

    Behaviour is not hard-coded here: it is added by attaching modules (see
    ``simulation/modules``). Each step the world calls every module's
    ``on_step`` with this agent.
    """

    hunger = Need()
    sleep = Need()
    thirst = Need()
    leisure = Need()

    def __init__(self, x, y, *, name=None, hunger=0.0, sleep=0.0, thirst=0.0,
                 leisure=0.0, money=0.0, movement=10, inventory=None,
                 color=None, modules=None):
        self.id = None  # assigned by the World when the agent is added
        self.name = name
        self.x = float(x)
        self.y = float(y)
        self.hunger = hunger
        self.sleep = sleep
        self.thirst = thirst
        self.leisure = leisure
        self.money = float(money)
        self.movement = int(movement)
        self.inventory = inventory if inventory is not None else Inventory()
        self.color = color
        self.modules = list(modules or [])

    @property
    def needs(self):
        return {name: getattr(self, name) for name in NEED_NAMES}

    def add_module(self, module):
        self.modules.append(module)
        return self

    def distance_to(self, other):
        return math.hypot(self.x - other.x, self.y - other.y)

    def move_towards(self, tx, ty, world):
        """Move straight toward (tx, ty), at most ``movement`` pixels, staying in the box."""
        dx, dy = tx - self.x, ty - self.y
        dist = math.hypot(dx, dy)
        if dist > self.movement:
            dx, dy = dx / dist * self.movement, dy / dist * self.movement
        self.x, self.y = world.clamp_position(self.x + dx, self.y + dy)

    def step(self, world):
        for module in self.modules:
            module.on_step(self, world)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "x": round(self.x, 2),
            "y": round(self.y, 2),
            "needs": {k: round(v, 2) for k, v in self.needs.items()},
            "money": round(self.money, 2),
            "movement": self.movement,
            "inventory": self.inventory.to_dict(),
            "color": self.color,
            "modules": [type(m).__name__ for m in self.modules],
        }
