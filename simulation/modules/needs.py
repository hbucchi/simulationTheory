from .base import Module


class NeedsDecay(Module):
    """Needs grow a little every step (agents get hungrier, more tired, ...).

    ``rates`` maps need name -> amount added per step. Sleep doesn't grow
    while the agent is resting (see Rest).
    """

    DEFAULT_RATES = {"hunger": 0.010, "sleep": 0.005, "thirst": 0.015, "boredom": 0.008}

    def __init__(self, rates=None):
        self.rates = {**self.DEFAULT_RATES, **(rates or {})}

    def on_step(self, agent, world):
        for need, rate in self.rates.items():
            if need == "sleep" and agent.sleeping:
                continue
            setattr(agent, need, getattr(agent, need) + rate)

    def to_dict(self):
        return {"rates": self.rates}
