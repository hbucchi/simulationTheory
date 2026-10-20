from .base import Module


class NeedsDecay(Module):
    """Needs grow a little every step (agents get hungrier, more tired, ...).

    ``rates`` maps need name -> amount added per step. Nothing satisfies
    the needs yet; that comes with eating/sleeping/trading modules.
    """

    DEFAULT_RATES = {"hunger": 0.010, "sleep": 0.005, "thirst": 0.015, "leisure": 0.008}

    def __init__(self, rates=None):
        self.rates = {**self.DEFAULT_RATES, **(rates or {})}

    def on_step(self, agent, world):
        for need, rate in self.rates.items():
            setattr(agent, need, getattr(agent, need) + rate)
