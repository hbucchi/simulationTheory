from ..rules import DEFAULT_RULES
from .base import Module


class Rest(Module):
    """Sleep is recovered by staying still.

    When sleep rises above the seek threshold the agent stops and recovers
    ``recovery`` per step until sleep is below the target level, then gets
    moving again (same thresholds as the other needs). While resting, sleep
    doesn't grow and Navigate keeps the agent in place. A depressed agent
    recovers at ``recovery * depression_factor``.
    """

    def __init__(self, recovery=None):
        self.recovery = DEFAULT_RULES.sleep_recovery if recovery is None else recovery

    def on_step(self, agent, world):
        rules = world.rules
        if agent.sleeping and agent.sleep < rules.target_level:
            agent.sleeping = False
        elif not agent.sleeping and agent.sleep > rules.seek_threshold:
            agent.sleeping = True
        if agent.sleeping:
            agent.sleep -= self.recovery * (rules.depression_factor if agent.depressed else 1)

    def to_dict(self):
        return {"recovery": self.recovery}
