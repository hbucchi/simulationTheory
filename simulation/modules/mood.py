from .. import economy
from .base import Module


class Mood(Module):
    """Boredom reaching 1.00 makes the agent depressed.

    A depressed agent moves at half its movement and recovers sleep at half
    its sleep recovery. It recovers once boredom drops below 0.3 (after
    playing games), the same target level as every other need.
    """

    def on_step(self, agent, world):
        if not agent.depressed and agent.boredom >= economy.CRITICAL_LEVEL:
            agent.depressed = True
            world.log(f"{agent.name} became depressed (boredom 1.00): movement and sleep recovery halved")
        elif agent.depressed and agent.boredom < economy.TARGET_LEVEL:
            agent.depressed = False
            world.log(f"{agent.name} recovered from depression")
