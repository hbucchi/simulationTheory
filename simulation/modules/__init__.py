"""Pluggable behaviours for agents.

A module is any object with ``on_step(agent, world)``. Attach modules to an
agent with ``agent.add_module(...)``; they run in order every step.
"""

from .base import Module
from .build import Build
from .consume import Consume
from .invest import Invest
from .leisure import Leisure
from .mood import Mood
from .navigate import Navigate
from .needs import NeedsDecay
from .production import Production
from .rest import Rest

__all__ = ["Module", "Build", "Consume", "Invest", "Leisure", "Mood", "Navigate", "NeedsDecay", "Production", "Rest"]
