"""The Agent class: a dot in the box with needs, money, movement and an inventory."""

import math

from . import economy, penalties
from .inventory import Inventory
from .rules import DEFAULT_RULES

from .rules import NEEDS as NEED_NAMES


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

    Needs (hunger, sleep, thirst, boredom, health, energy, shelter) are scores in [0.00, 1.00] where
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
    health = Need()
    energy = Need()
    shelter = Need()

    def __init__(self, x, y, *, name=None, hunger=0.0, sleep=0.0, thirst=0.0,
                 boredom=0.0, health=0.0, energy=0.0, shelter=0.0, money=0.0, movement=10, inventory=None,
                 color=None, modules=None):
        self.id = None  # assigned by the World when the agent is added
        self.name = name
        self.x = float(x)
        self.y = float(y)
        self.hunger = hunger
        self.sleep = sleep
        self.thirst = thirst
        self.boredom = boredom
        self.health = health
        self.energy = energy
        self.shelter = shelter
        self.money = float(money)
        self.movement = int(movement)
        self.inventory = inventory if inventory is not None else Inventory()
        self.color = color
        self.modules = list(modules or [])
        # Set by the Navigate module / the World; shown in the UI.
        self.activity = "wandering"
        self.sleeping = False  # set by the Rest module; a sleeping agent stays still
        self.depressed = False  # set by the Mood module; slows movement and sleep recovery
        self.speed_factor = 1.0      # < 1 while very thirsty (penalties.py; set by NeedsDecay)
        self.critical_health_days = 0   # days in a row at health 1.00 (dies at penalties.HEALTH_DEATH_DAYS)
        self.subsistence = {}        # {good: fraction of a unit made on its own so far}
        self.months_left = None      # months of living costs its money and goods cover (labor.py)
        self.experience = {}         # {good: units of labour worked in its industry} (specialization)
        self.main_good = None        # the industry it hires for (labor.py)
        self.distress = 0.0          # cash-flow discount on its sales (World.update_distress)
        self.luck = {}               # {good: [output multiplier, last day]}: a lucky business (world.draw_luck)
        self.home = None             # the House it lives in (housing.py), or None: homeless
        self.houses = []             # Houses it owns
        self.subsistence_made = {}   # {good: units per day made on its own (latest day)}
        self.depression_factor = 0.5  # set from the game rules by the World
        self.assets = {}  # good -> shares of productive assets owned
        self.labor_need = 0.0  # labour its assets use per step at full capacity (Production)
        self.output_capacity = {}  # good -> units its assets make per step when fully staffed
        # Labour (set each step by the labour market, labor.py).
        self.labor_capacity = 0.5   # most labour it can give per step when fully efficient
        self.efficiency = 1.0
        self.wellbeing = 1.0
        self.job_need = 0.0
        self.capacity_now = 0.0     # labor_capacity x efficiency
        self.offered = 0.0          # capacity offered to the market this step
        self.asking_wage = 0.0
        self.labor_available = 0.0  # labour working its assets this step (own + hired)
        self.labor_sold = 0.0       # labour it sold this step
        self.labor_bought = 0.0     # labour it hired this step
        self.employers = {}         # who it worked for this step -> units
        # This step's flows (income, produced, consumed, labour), reset by the World each step.
        self.flow = {"income": 0.0, "sources": {}, "produced": {}, "consumed": {}, "used": {}, "expired": {},
                     "labor_made": 0.0, "labor_used": 0.0}
        self.input_credit = {}  # input good -> fraction of a unit already taken from stock (Production)
        # Smoothed per-step income and consumption (for income / consumption inequality).
        self.income_avg = 0.0
        self.consumption_avg = 0.0
        self.project = None      # building project (Build): {"good", "shares", "need", "started"}
        self.deposits = {}       # bank id -> balance (kept in step by banking.py)
        # Personality traits (more to come): payout_ratio = share of company profits paid out
        # as dividends; the rest stays in the company (company_cash) to pay wages and reinvest.
        self.personality = {"payout_ratio": 0.5, "risk_appetite": 0.0}
        self.company_cash = 0.0  # retained earnings of the companies it owns
        self.debt = 0.0          # what it owes the banks
        self.target_id = None
        self.seeking_for = None  # resource it is going to buy from target_id (Navigate)
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
        """Move straight toward (tx, ty), at most ``speed`` pixels, staying in the box."""
        dx, dy = tx - self.x, ty - self.y
        dist = math.hypot(dx, dy)
        if dist > self.speed:
            dx, dy = dx / dist * self.speed, dy / dist * self.speed
        self.x, self.y = world.clamp_position(self.x + dx, self.y + dy)

    def depart(self, heading, steps):
        """Walk along ``heading`` (radians) for the next ``steps`` steps."""
        self.depart_heading = heading
        self.depart_steps = steps
        self.activity = "leaving"

    def step(self, world):
        for module in self.modules:
            module.on_step(self, world)

    @property
    def speed(self):
        """Pixels this agent can actually move per step: movement, reduced while depressed."""
        speed = max(1, int(self.movement * self.depression_factor)) if self.depressed else self.movement
        return max(1, int(speed * self.speed_factor)) if self.speed_factor < 1 else speed

    def _held(self):
        """{good: whole units} of the goods it holds (none of the zeros)."""
        return {g: n for g, n in self.inventory.to_dict().items() if n}

    def to_dict(self, rules=DEFAULT_RULES, full=True):
        """Everything about the agent; full=False leaves out the costly details (labour, modules,
        industry buffers) that only its card and editor show, for big games."""
        if not full:
            return {
                "id": self.id, "name": self.name, "x": round(self.x, 2), "y": round(self.y, 2),
                "needs": {k: round(v, 2) for k, v in self.needs.items()},
                "money": round(self.money, 2), "movement": self.movement, "speed": self.speed,
                "deposits": round(sum(self.deposits.values()), 2), "debt": round(self.debt, 2),
                "company_cash": round(self.company_cash, 2), "personality": dict(self.personality),
                "assets": dict(self.assets), "depressed": self.depressed,
                "inventory": self._held(), "color": self.color, "activity": self.activity,
                "target_id": self.target_id, "project": self.project, "seeking_for": self.seeking_for,
                "wants": [n for n in rules.consumer_needs if getattr(self, n) > rules.seek_threshold],
                # The labour figures the overview averages / sorts by.
                "labor": {"efficiency": round(self.efficiency, 3), "wellbeing": round(self.wellbeing, 3),
                          "job_need": round(self.job_need, 3), "sold": round(self.labor_sold, 4)},
                "full": False,
            }
        return {
            "id": self.id,
            "name": self.name,
            "x": round(self.x, 2),
            "y": round(self.y, 2),
            "needs": {k: round(v, 2) for k, v in self.needs.items()},
            "money": round(self.money, 2),
            "deposits": round(sum(self.deposits.values()), 2), "debt": round(self.debt, 2),
            "company_cash": round(self.company_cash, 2), "personality": dict(self.personality),
            "movement": self.movement,
            "speed": self.speed,
            "assets": dict(self.assets),
            "labor_need": round(self.labor_need, 4),
            "labor": {"capacity": self.labor_capacity, "efficiency": round(self.efficiency, 3),
                      "wellbeing": round(self.wellbeing, 3), "job_need": round(self.job_need, 3),
                      "capacity_now": round(self.capacity_now, 4), "offered": round(self.offered, 4),
                      "asking_wage": round(self.asking_wage, 2), "sold": round(self.labor_sold, 4),
                      "bought": round(self.labor_bought, 4), "employers": {k: round(v, 3) for k, v in self.employers.items()}},
            "depressed": self.depressed,
            # What unmet needs are costing it now, and what it made on its own (no assets).
            "penalties": penalties.describe(self, rules),
            "home": None if self.home is None else {
                "house": self.home.id, "owns": self.home.owner is self,
                "landlord": "the government" if self.home.owner is None else self.home.owner.name},
            "houses": len(self.houses),
            "luck": {g: {"times": m, "until": u} for g, (m, u) in self.luck.items()},
            "experience": {g: round(x, 2) for g, x in sorted(self.experience.items(), key=lambda kv: -kv[1])[:3]},
            "houses_let": sum(1 for h in self.houses if h.occupant is not None and h.occupant is not self),
            "subsistence": {g: round(v, 3) for g, v in self.subsistence_made.items()},
            "inventory": self._held(),
            "output_capacity": {g: round(v, 4) for g, v in self.output_capacity.items()},
            "input_target": {r: economy.input_target(self, r, rules) for r in rules.active_goods
                             if economy.input_target(self, r, rules)},
            "color": self.color,
            "activity": self.activity,
            "target_id": self.target_id,
            "project": self.project,
            "seeking_for": self.seeking_for,
            # Needs above the seek threshold that goods can relieve.
            "wants": [n for n in rules.consumer_needs if getattr(self, n) > rules.seek_threshold],
            "modules": {type(m).__name__: m.to_dict() for m in self.modules},
            "full": True,
        }
