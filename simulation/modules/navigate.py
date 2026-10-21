import math

from .. import economy
from .base import Module


class Navigate(Module):
    """Decides where the agent walks each step. Priority:

    0. sleeping  - resting to recover sleep (Rest module): stay still. Others
                   can still walk up to it and trade.
    1. leaving   - just traded: walk along the departure heading (unless someone is
                   coming to buy from it: then it meets them, see 3).
    2. seeking   - a need is above the seek threshold and stock is gone: every
                   step, find the closest agent that has spare of what it
                   needs (most urgent need first) and walk straight at it.
       searching - same, but nobody has any to sell: keep wandering.
    2b. stockpiling - not in need, but below its reserve of a resource that is
                   becoming scarce: go to the nearest agent with spare of it.
        restocking  - same, because its stock fell below the floor of its stock band.
        hiring      - same, for labour its assets need.
    3. meeting   - another agent is seeking this one: walk toward that seeker,
                   so both close the gap and are guaranteed to touch.
    3b. selling  - holds more than the stock cap of a good, or labour beyond what its own
                   assets need: go to the nearest agent that wants it and has money.
    4. wandering - otherwise: random walk between random points.
    """

    def __init__(self):
        self.wander_target = None

    def on_step(self, agent, world):
        if agent.sleeping:
            agent.activity = "sleeping"
            agent.target_id = None
            return

        # Someone coming to buy from it beats walking away from the last deal: a busy
        # seller that keeps leaving can't be caught by slower buyers, who then starve.
        seekers = world.seekers_of(agent)
        if seekers and agent.depart_steps > 0:
            agent.depart_steps = 0
            self._go_to(agent, "meeting", min(seekers, key=agent.distance_to), world)
            return

        if agent.depart_steps > 0:
            agent.activity = "leaving"
            agent.target_id = None
            agent.depart_steps -= 1
            agent.move_towards(agent.x + math.cos(agent.depart_heading) * agent.movement,
                               agent.y + math.sin(agent.depart_heading) * agent.movement, world)
            return

        agent.seeking_for = None
        needy = economy.is_needy(agent, world.rules)
        if needy:
            seller, resource = world.nearest_seller(agent)
            if seller is not None:
                agent.seeking_for = resource
                self._go_to(agent, "seeking", seller, world)
                return
        else:
            seller, resource = world.nearest_seller(agent, stockpile=True)
            if seller is not None:
                agent.seeking_for = resource
                # Stockpiling: building a reserve because it is getting scarce. Restocking:
                # back up to the cap after falling below the floor.
                hoarding = economy.stockpile_shortfall(agent, resource, world.rules, world.scarcity) > 0
                activity = "hiring" if resource == economy.LABOR else "stockpiling" if hoarding else "restocking"
                self._go_to(agent, activity, seller, world)
                return
        seekers = world.seekers_of(agent)
        if seekers:
            self._go_to(agent, "meeting", min(seekers, key=agent.distance_to), world)
            return

        if not needy:
            for resource in sorted(economy.RESOURCES, reverse=True,
                                   key=lambda r: economy.surplus(agent, r, world.rules, world.scarcity)):
                if not economy.surplus(agent, resource, world.rules, world.scarcity):
                    break
                buyer = world.nearest_buyer(agent, resource)
                if buyer is not None:
                    agent.seeking_for = resource
                    self._go_to(agent, "selling", buyer, world)
                    return

        agent.activity = "searching" if needy else "wandering"
        agent.target_id = None
        if self.wander_target is None or (agent.x, agent.y) == self.wander_target:
            self.wander_target = world.random_position()
        agent.move_towards(*self.wander_target, world)

    @staticmethod
    def _go_to(agent, activity, partner, world):
        agent.activity = activity
        agent.target_id = partner.id
        agent.move_towards(partner.x, partner.y, world)  # partner's position right now
