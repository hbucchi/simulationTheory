from ..rules import DEFAULT_RULES
from .base import Module


class Production(Module):
    """Adds 1 unit of a resource every N steps, faster with assets.

    ``intervals`` maps resource -> N (steps per unit). 0 or None disables it.
    Each step adds (1 + assets x asset_return) of progress; a unit is made each
    time progress reaches N. With no assets that is exactly one unit per N steps.
    """

    def __init__(self, intervals=None):
        self.intervals = {**DEFAULT_RULES.production, **(intervals or {})}
        self.counters = {r: 0 for r in self.intervals}

    def set_intervals(self, intervals):
        self.intervals.update(intervals)
        for resource in intervals:
            self.counters.setdefault(resource, 0)

    def on_step(self, agent, world):
        for resource, every in self.intervals.items():
            if not every:
                continue
            boost = agent.assets.get(resource, 0) * world.rules.asset_return[resource]
            self.counters[resource] += 1 + boost
            while self.counters[resource] >= every - 1e-9:
                self.counters[resource] -= every
                agent.inventory.add(resource)

    def to_dict(self):
        return {"intervals": self.intervals}
