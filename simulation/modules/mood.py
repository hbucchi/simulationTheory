from .. import economy
from .base import Module


class Mood(Module):
    """Boredom reaching 1.00 makes the agent depressed.

    A depressed agent's movement and sleep recovery are multiplied by the
    rules' depression_factor (0.5 by default). It recovers once boredom drops
    below the target level (after playing games). Only attached when the
    rules enable depression.
    """

    def on_step(self, agent, world):
        if not agent.depressed and agent.boredom >= economy.CRITICAL_LEVEL:
            agent.depressed = True
            world.log(f"{agent.name} became depressed (boredom 1.00): movement and sleep recovery "
                      f"x{world.rules.depression_factor:g}")
        elif agent.depressed and agent.boredom < world.rules.target_level:
            agent.depressed = False
            world.log(f"{agent.name} recovered from depression")
