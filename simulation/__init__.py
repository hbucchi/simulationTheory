"""Agent-based simulation core: agents, the world (box) and pluggable modules."""

from .agent import Agent
from .inventory import Inventory
from .world import World

__all__ = ["Agent", "Inventory", "World"]
