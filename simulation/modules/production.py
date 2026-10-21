from ..rules import GOODS
from .base import Module


class Production(Module):
    """Goods from the agent's assets, worked by the labour it has this step.

    The labour market (labor.py) sets ``agent.labor_available`` each step: its own
    labour used on its assets plus labour it hired. Each asset share employs up to
    world.asset_jobs() labour per step, and each unit of labour makes the good's
    current productivity in units. With less labour than its assets can employ, all
    its assets run at the same reduced share. Fractions of goods carry over until
    they make a whole unit. ``agent.output_capacity`` is what they make per step when
    fully staffed (used to decide what to stockpile).
    """

    def __init__(self):
        self.asset_progress = {}   # good -> fraction of a unit made so far

    def on_step(self, agent, world):
        jobs = {g: world.asset_jobs(g, shares) for g, shares in agent.assets.items() if g in GOODS}
        agent.labor_need = sum(jobs.values())
        agent.output_capacity = {g: employed * world.productivity_now[g] for g, employed in jobs.items()}
        ratio = min(1.0, agent.labor_available / agent.labor_need) if agent.labor_need else 0.0
        for good, employed in jobs.items():
            made = self.asset_progress.get(good, 0) + employed * ratio * world.productivity_now[good]
            whole = int(made + 1e-9)
            if whole:
                agent.inventory.add(good, whole)
                agent.flow["produced"][good] = agent.flow["produced"].get(good, 0) + whole
            self.asset_progress[good] = made - whole
