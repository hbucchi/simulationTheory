import math

from .. import economy
from .base import Module
from .invest import cash_needed, purchase_limit

# Smallest project worth starting (asset shares).
MIN_PROJECT_SHARES = 0.05
# Largest project an agent takes on at once (asset shares).
MAX_PROJECT_SHARES = 1.0


class Build(Module):
    """Builds new asset shares (industry capacity) out of capital goods.

    No project yet: with money to spare (the same cash rules as Invest), the agent compares,
    for every industry in the game, what one asset share is worth (world.asset_prices) with
    what its capital goods cost (rules.build_cost x current prices): Tobin's q = value / cost.
    Only industries whose capital goods are for sale right now (and not claimed by other projects)
    count, so slow capital industries pace how much gets built. If the best q is at least
    rules.build_min_q, building beats buying, so it starts a project
    for as many shares as it can afford (at most MAX_PROJECT_SHARES) and works out the whole
    units of each capital good it needs.

    With a project: it goes out to buy the capital goods (economy.project_shortfall drives
    Navigate's "building" activity; it keeps them and won't sell them). As soon as it holds
    them all it uses them up and gets the new shares. Capital industries are slow (very low
    productivity), so this takes time. A project not done within rules.project_steps is dropped;
    whatever it bought stays in its inventory.
    """

    def on_step(self, agent, world):
        rules = world.rules
        if not rules.building_enabled:
            return
        if agent.project:
            self.progress(agent, world)
        elif rules.investing_enabled:
            self.plan(agent, world)

    def plan(self, agent, world):
        rules = world.rules
        prices = world.current_prices()
        spare = agent.money - cash_needed(agent, prices, rules)
        if spare < rules.min_investment:
            return
        asset_prices = world.asset_prices(prices)
        budget = min(spare, purchase_limit(agent, asset_prices, rules.capital_cash_ratio))
        best, best_q, best_cost = None, 0.0, 0.0
        for good in rules.active_goods:
            cost = world.build_cost_money(good, prices)
            if not cost or cost <= 0 or not self.available(good, world, agent):
                continue
            q = asset_prices[good] / cost
            if q > best_q:
                best, best_q, best_cost = good, q, cost
        if best is None or best_q < rules.build_min_q:
            return
        shares = min(MAX_PROJECT_SHARES, budget / best_cost)
        if shares < MIN_PROJECT_SHARES:
            return
        need = {k: math.ceil(round(units * shares, 9)) for k, units in rules.build_cost[best].items()}
        agent.project = {"good": best, "shares": round(shares, 4), "need": need, "started": world.tick,
                         "q": round(best_q, 2)}
        world.log(f"{agent.name} started building {shares:.2f} {best} asset(s) (worth {best_q:.1f}x their cost): "
                  f"needs {economy.describe(need)}")

    @staticmethod
    def available(good, world, agent):
        """Can the capital goods for one share of ``good`` be bought now? Other agents together
        have at least that much to spare (spare_table: worked out once per step) and no other
        project already claims it. Capital goods are slow to make, so this paces building."""
        claimed = {}
        for o in world.agents:
            if o.project:
                for k, units in o.project["need"].items():
                    claimed[k] = claimed.get(k, 0) + max(0, units - o.inventory.count(k))
        for k, units in world.rules.build_cost[good].items():
            on_offer = sum(n for o, n in world.spare_table.get(k, {}).items() if o is not agent)
            if on_offer + agent.inventory.count(k) - claimed.get(k, 0) < units:
                return False
        return True

    def progress(self, agent, world):
        project = agent.project
        if world.tick - project["started"] > world.rules.project_steps:
            agent.project = None
            world.log(f"{agent.name} gave up building {project['good']} assets (capital goods too slow to get)")
            return
        if any(agent.inventory.count(k) < units for k, units in project["need"].items()):
            return
        for k, units in project["need"].items():
            if units:
                agent.inventory.remove(k, units)
        good, shares = project["good"], project["shares"]
        agent.assets[good] = agent.assets.get(good, 0) + shares
        world.assets_built[good] = world.assets_built.get(good, 0) + shares
        agent.project = None
        world.log(f"{agent.name} built {shares:.2f} new {good} asset(s) from {economy.describe(project['need'])}"
                  f" in {world.tick - project['started']} steps; now owns {agent.assets[good]:.2f}")
