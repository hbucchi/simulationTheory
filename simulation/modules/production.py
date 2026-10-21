from ..rules import DEFAULT_RULES
from .base import Module


class Production(Module):
    """The agent's own production (1 unit every N steps) plus its assets' output.

    ``intervals`` maps resource -> N (steps per unit). 0 or None disables it.
    Assets add shares x current asset value x asset_return units per step;
    fractions accumulate until a whole unit is made.
    """

    def __init__(self, intervals=None):
        self.intervals = {**DEFAULT_RULES.production, **(intervals or {})}
        self.counters = {r: 0 for r in self.intervals}
        self.asset_progress = {}  # resource -> fraction of a unit made by assets so far

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
        for resource, shares in agent.assets.items():
            made = self.asset_progress.get(resource, 0) + world.asset_output(resource, shares)
            whole = int(made + 1e-9)
            if whole:
                agent.inventory.add(resource, whole)
            self.asset_progress[resource] = made - whole

    def to_dict(self):
        return {"intervals": self.intervals}
