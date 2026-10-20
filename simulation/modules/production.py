from ..economy import DEFAULT_PRODUCTION
from .base import Module


class Production(Module):
    """Adds 1 unit of a resource every N steps.

    ``intervals`` maps resource -> N (steps per unit). 0 or None disables it.
    """

    def __init__(self, intervals=None):
        self.intervals = {**DEFAULT_PRODUCTION, **(intervals or {})}
        self.counters = {r: 0 for r in self.intervals}

    def set_intervals(self, intervals):
        self.intervals.update(intervals)
        for resource in intervals:
            self.counters.setdefault(resource, 0)

    def on_step(self, agent, world):
        for resource, every in self.intervals.items():
            if not every:
                continue
            self.counters[resource] += 1
            if self.counters[resource] >= every:
                self.counters[resource] = 0
                agent.inventory.add(resource)

    def to_dict(self):
        return {"intervals": self.intervals}
