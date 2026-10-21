from ..rules import GOODS, LABOR
from .base import Module


class Production(Module):
    """Labour from the agent itself; goods only from its assets, worked by labour.

    Each step the agent adds ``labor_rate`` units of labour (a batch that expires
    rules.labor_lifetime steps later). Each asset share can employ up to
    rules.asset_labor[good] labour per step, using the oldest labour first, and
    each unit of labour makes the good's current productivity in units. With less
    labour than its assets can employ, all its assets run at the same reduced
    share. Fractions of goods carry over until they make a whole unit.

    ``agent.labor_need`` is set to the labour its assets can employ per step and
    ``agent.output_capacity`` to what they make per step when fully staffed; the
    economy uses them to decide how much labour to hire and what to stockpile.
    """

    def __init__(self, labor_rate=0.0):
        self.labor_rate = labor_rate
        self.asset_progress = {}   # good -> fraction of a unit made so far

    def on_step(self, agent, world):
        jobs = {g: world.asset_jobs(g, shares) for g, shares in agent.assets.items() if g in GOODS}
        agent.labor_need = sum(jobs.values())
        agent.output_capacity = {g: employed * world.productivity_now[g] for g, employed in jobs.items()}

        if self.labor_rate > 0:
            agent.inventory.add(LABOR, self.labor_rate)
        labor = agent.inventory.amount(LABOR)
        ratio = min(1.0, labor / agent.labor_need) if agent.labor_need else 1.0
        if agent.labor_need:
            agent.inventory.take(LABOR, agent.labor_need * ratio)

        for good, employed in jobs.items():
            made = self.asset_progress.get(good, 0) + employed * ratio * world.productivity_now[good]
            whole = int(made + 1e-9)
            if whole:
                agent.inventory.add(good, whole)
            self.asset_progress[good] = made - whole

    def to_dict(self):
        return {"labor_rate": self.labor_rate}
