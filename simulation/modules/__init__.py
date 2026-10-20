"""Pluggable behaviours for agents.

A module is any object with ``on_step(agent, world)``. Attach modules to an
agent with ``agent.add_module(...)``; they run in order every step.
"""

from .base import Module
from .consume import Consume
from .navigate import Navigate
from .needs import NeedsDecay
from .production import Production

__all__ = ["Module", "Consume", "Navigate", "NeedsDecay", "Production"]
