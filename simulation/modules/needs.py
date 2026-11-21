from ..rules import DEFAULT_RULES
from .base import Module


class NeedsDecay(Module):
    """Needs grow a little every step (agents get hungrier, more tired, ...).

    ``rates`` maps need name -> amount added per step. Sleep doesn't grow
    while the agent is resting (see Rest).
    """

    def __init__(self, rates=None):
        self.rates = {**DEFAULT_RULES.rates, **(rates or {})}

    def on_step(self, agent, world):
        for need, rate in self.rates.items():
            if need == "sleep" and agent.sleeping:
                continue
            setattr(agent, need, getattr(agent, need) + rate)

    def to_dict(self):
        return {"rates": self.rates}
