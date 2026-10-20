"""The Agent class: a dot in the box with needs, money, movement and an inventory."""

import math

from . import economy
from .inventory import Inventory

NEED_NAMES = ("hunger", "sleep", "thirst", "boredom")


def clamp(value, low, high):
    return max(low, min(high, value))


class Need:
    """Descriptor that keeps a need score clamped to [0.0, 1.0]."""

    def __set_name__(self, owner, name):
        self.attr = "_" + name

    def __get__(self, agent, owner=None):
        return self if agent is None else getattr(agent, self.attr)

    def __set__(self, agent, value):
        # Rounding stops float noise (0.30000000000000004) from accumulating.
        setattr(agent, self.attr, round(clamp(float(value), 0.0, 1.0), 6))


class Agent:
    """A single simulated agent.

    Needs (hunger, sleep, thirst, boredom) are scores in [0.00, 1.00] where
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
    boredom = Need()

    def __init__(self, x, y, *, name=None, hunger=0.0, sleep=0.0, thirst=0.0,
                 boredom=0.0, money=0.0, movement=10, inventory=None,
                 color=None, modules=None):
        self.id = None  # assigned by the World when the agent is added
        self.name = name
        self.x = float(x)
        self.y = float(y)
        self.hunger = hunger
        self.sleep = sleep
        self.thirst = thirst
        self.boredom = boredom
        self.money = float(money)
        self.movement = int(movement)
        self.inventory = inventory if inventory is not None else Inventory()
        self.color = color
        self.modules = list(modules or [])
        # Set by the Navigate module / the World; shown in the UI.
        self.activity = "wandering"
        self.sleeping = False  # set by the Rest module; a sleeping agent stays still
        self.target_id = None
        self.depart_heading = 0.0  # radians
        self.depart_steps = 0

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

    def depart(self, heading, steps):
        """Walk along ``heading`` (radians) for the next ``steps`` steps."""
        self.depart_heading = heading
        self.depart_steps = steps
        self.activity = "leaving"

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
            "activity": self.activity,
            "target_id": self.target_id,
            "wants": [r for r, n in economy.NEED_FOR_RESOURCE.items() if getattr(self, n) > economy.SEEK_THRESHOLD],
            "modules": {type(m).__name__: m.to_dict() for m in self.modules},
        }
