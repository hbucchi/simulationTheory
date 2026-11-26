from .. import penalties
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
        rules = world.rules
        housing = rules.housing_enabled
        for need, rate in self.rates.items():
            if need == "sleep" and agent.sleeping:
                continue
            if need == "shelter" and housing:
                # A house meets shelter every day; the homeless' shelter grows fast (housing.py).
                if agent.home is not None:
                    agent.shelter = max(0.0, agent.shelter - rules.house_relief)
                    continue
                if rate > 0:
                    rate = max(rate, rules.homeless_shelter_rate)
            setattr(agent, need, getattr(agent, need) + rate * penalties.growth_factor(agent, need, rules))
        agent.recent_fun *= 1 - 1 / rules.month_steps      # what it had lately fades over about a month
        # Unmet needs (penalties.py): slower walking, and days spent too sick to work.
        agent.speed_factor = penalties.speed_factor(agent, rules)
        if rules.need_penalties_enabled and "health" in rules.consumer_needs and agent.health >= penalties.CRITICAL:
            agent.critical_health_days += 1
        else:
            agent.critical_health_days = 0

    def to_dict(self):
        return {"rates": self.rates}
