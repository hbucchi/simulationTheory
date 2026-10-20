import math

from .. import economy
from .base import Module


class Navigate(Module):
    """Decides where the agent walks each step. Priority:

    1. leaving   - just met someone: walk along the departure heading.
    2. seeking   - a need is above 0.5 and stock is gone: walk to the nearest
                   agent it hasn't just met (it can't know who has what).
    3. wandering - otherwise: random walk between random points.
    """

    def __init__(self):
        self.wander_target = None

    def on_step(self, agent, world):
        agent.target_id = None
        if agent.depart_steps > 0:
            agent.activity = "leaving"
            agent.depart_steps -= 1
            agent.move_towards(agent.x + math.cos(agent.depart_heading) * agent.movement,
                               agent.y + math.sin(agent.depart_heading) * agent.movement, world)
            return

        if economy.is_needy(agent):
            partner = world.nearest_partner(agent)
            if partner is not None:
                agent.activity = "seeking"
                agent.target_id = partner.id
                agent.move_towards(partner.x, partner.y, world)
                return

        agent.activity = "wandering"
        if self.wander_target is None or (agent.x, agent.y) == self.wander_target:
            self.wander_target = world.random_position()
        agent.move_towards(*self.wander_target, world)
