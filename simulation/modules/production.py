import math

from ..rules import GOODS
from .base import Module


class Production(Module):
    """Goods from the agent's industries (its assets), worked by the labour it has this step.

    Every good has an industry. Primary industries (extraction) need capital (asset
    shares) and labour; secondary industries also use inputs (rules.inputs: units of
    each input per unit of output). Output is limited by whatever is scarcest, in
    fixed proportions:

        output = productivity x min(labour, shares x labour per asset, labour the inputs allow)

    The labour market (labor.py) sets ``agent.labor_available`` each step: its own
    labour used on its assets plus labour it hired. It only hires labour the inputs
    in stock can keep busy (world.usable_jobs). With less labour than its industries
    can use, all of them run at the same reduced share. Fractions of goods carry over
    until they make a whole unit; inputs are used in matching fractions, drawn from the
    inventory a whole unit at a time into ``agent.input_credit``.
    ``agent.output_capacity`` is what its industries make per step at full capacity
    (used for input buffers and stockpiling).
    """

    def __init__(self):
        self.asset_progress = {}   # good -> fraction of a unit made so far

    def on_step(self, agent, world):
        jobs = {g: world.usable_jobs(agent, g) for g in agent.assets if g in GOODS}
        agent.labor_need = sum(jobs.values())
        agent.output_capacity = {g: world.asset_output(g, shares) for g, shares in agent.assets.items() if g in GOODS}
        ratio = min(1.0, agent.labor_available / agent.labor_need) if agent.labor_need else 0.0
        recipes = world.rules.inputs
        for good, employed in jobs.items():
            fresh = employed * ratio * world.productivity_now[good]
            for item, per_unit in recipes.get(good, {}).items():
                self._use(agent, item, fresh * per_unit)
            made = self.asset_progress.get(good, 0) + fresh
            whole = int(made + 1e-9)
            if whole:
                agent.inventory.add(good, whole)
                agent.flow["produced"][good] = agent.flow["produced"].get(good, 0) + whole
            self.asset_progress[good] = made - whole

    @staticmethod
    def _use(agent, item, amount):
        """Use ``amount`` (fractional) of an input: from the credit first, then whole units from stock."""
        if amount <= 0:
            return
        credit = agent.input_credit.get(item, 0.0)
        if credit + 1e-9 < amount:
            draw = min(agent.inventory.count(item), math.ceil(amount - credit - 1e-9))
            if draw:
                agent.inventory.remove(item, draw)
                credit += draw
        agent.input_credit[item] = max(0.0, credit - amount)
        agent.flow["used"][item] = agent.flow["used"].get(item, 0) + amount
