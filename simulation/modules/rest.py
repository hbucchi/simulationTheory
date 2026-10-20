from .. import economy
from .base import Module


class Rest(Module):
    """Sleep is recovered by staying still.

    When sleep rises above 0.5 the agent stops and recovers ``recovery`` per
    step until sleep is below 0.3, then gets moving again (same thresholds as
    the other needs). While resting, sleep doesn't grow and Navigate keeps
    the agent in place. A depressed agent recovers at half the rate.
    """

    DEFAULT_RECOVERY = 0.05

    def __init__(self, recovery=None):
        self.recovery = self.DEFAULT_RECOVERY if recovery is None else recovery

    def on_step(self, agent, world):
        if agent.sleeping and agent.sleep < economy.TARGET_LEVEL:
            agent.sleeping = False
        elif not agent.sleeping and agent.sleep > economy.SEEK_THRESHOLD:
            agent.sleeping = True
        if agent.sleeping:
            agent.sleep -= self.recovery / 2 if agent.depressed else self.recovery

    def to_dict(self):
        return {"recovery": self.recovery}
