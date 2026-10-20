"""Pluggable behaviours for agents.

A module is any object with ``on_step(agent, world)``. Attach modules to an
agent with ``agent.add_module(...)``; they run in order every step.
"""

from .base import Module
from .needs import NeedsDecay
from .wander import Wander

__all__ = ["Module", "NeedsDecay", "Wander"]
