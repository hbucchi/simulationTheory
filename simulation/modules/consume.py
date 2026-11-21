from .. import economy
from .base import Module


class Consume(Module):
    """When a need passes the seek threshold, consume own stock until it is below the target."""

    def on_step(self, agent, world):
        economy.consume(agent, world.rules)
