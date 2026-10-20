from .base import Module


class Wander(Module):
    """Random walk: pick a target point in the box, walk to it, pick another.

    Each step the agent covers at most ``agent.movement`` pixels.
    """

    def __init__(self):
        self.target = None

    def on_step(self, agent, world):
        if self.target is None or (agent.x, agent.y) == self.target:
            self.target = world.random_position()
        agent.move_towards(*self.target, world)
