import math

from .. import economy
from .base import Module


class Navigate(Module):
    """Decides where the agent walks each step. Priority:

    1. leaving   - just traded: walk along the departure heading.
    2. seeking   - a need is above 0.5 and stock is gone: every step, find the
                   closest available agent (it can't know who has what) and
                   walk straight at its current position.
    3. meeting   - another agent is seeking this one: walk toward that seeker,
                   so both close the gap and are guaranteed to touch.
    4. wandering - otherwise: random walk between random points.
    """

    def __init__(self):
        self.wander_target = None

    def on_step(self, agent, world):
        if agent.depart_steps > 0:
            agent.activity = "leaving"
            agent.target_id = None
            agent.depart_steps -= 1
            agent.move_towards(agent.x + math.cos(agent.depart_heading) * agent.movement,
                               agent.y + math.sin(agent.depart_heading) * agent.movement, world)
            return

        if economy.is_needy(agent):
            partner = world.nearest_partner(agent)
            if partner is not None:
                self._go_to(agent, "seeking", partner, world)
                return

        seekers = world.seekers_of(agent)
        if seekers:
            self._go_to(agent, "meeting", min(seekers, key=agent.distance_to), world)
            return

        agent.activity = "wandering"
        agent.target_id = None
        if self.wander_target is None or (agent.x, agent.y) == self.wander_target:
            self.wander_target = world.random_position()
        agent.move_towards(*self.wander_target, world)

    @staticmethod
    def _go_to(agent, activity, partner, world):
        agent.activity = activity
        agent.target_id = partner.id
        agent.move_towards(partner.x, partner.y, world)  # partner's position right now
