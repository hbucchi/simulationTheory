from .. import economy
from .base import Module


class Consume(Module):
    """When a need passes 0.5, consume own stock until it is below 0.3."""

    def on_step(self, agent, world):
        economy.consume(agent)
