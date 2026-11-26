import math

from .. import economy
from .base import Module
from .invest import asset_yield, budget_needed, cash_needed, purchase_limit

# Smallest project worth starting (asset shares).
MIN_PROJECT_SHARES = 0.05
# Largest project an agent takes on at once (asset shares).
MAX_PROJECT_SHARES = 1.0
# The most adventurous agents (risk appetite 1) build up to 1 + ENTREPRENEUR_SCALE times as much,
# and agents with at least BORROW_APPETITE borrow for what their own money doesn't cover.
ENTREPRENEUR_SCALE = 4.0
BORROW_APPETITE = 0.3


def claimed_capital_goods(world):
    """{capital good: units projects still need to buy}, worked out once per step."""
    cache = world._step_cache
    if cache and "claimed" in cache:
        return cache["claimed"]
    claimed = {}
    for o in world.agents:
        if o.project:
            for k, units in o.project["need"].items():
                claimed[k] = claimed.get(k, 0) + max(0, units - o.inventory.count(k))
    if cache is not None:
        cache["claimed"] = claimed
    return claimed


def ranked_builds(world, prices, asset_prices):
    """[(good, q, cost of one share)] for goods worth building (q >= build_min_q), best q first.
    Worked out once per step (fresh outside a step)."""
    cache = world._step_cache
    if cache and "builds" in cache:
        return cache["builds"]
    out = []
    for good in world.rules.active_goods:
        cost = world.build_cost_money(good, prices)
        if not cost or cost <= 0:
            continue
        q = asset_prices[good] / cost
        if q >= world.rules.build_min_q and q > 0:
            out.append((good, q, cost))
    out.sort(key=lambda t: t[1], reverse=True)
    if cache is not None:
        cache["builds"] = out
    return out


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

    def reinvest(self, agent, world, prices):
        """Retained earnings (company cash) build new capacity in an industry the agent already
        owns, the one worth most per unit of cost first. True if it started a project."""
        rules = world.rules
        if agent.company_cash < rules.min_investment:
            return False
        for good, q, cost in ranked_builds(world, prices, world.step_asset_prices()):
            if good not in agent.assets or not self.available(good, world, agent):
                continue
            shares = min(MAX_PROJECT_SHARES, agent.company_cash / cost)
            if shares < MIN_PROJECT_SHARES:
                return False
            economy.draw_company_cash(agent, shares * cost)
            need = {k: math.ceil(round(units * shares, 9)) for k, units in rules.build_cost[good].items()}
            agent.project = {"good": good, "shares": round(shares, 4), "need": need, "started": world.tick,
                             "q": round(q, 2), "borrowed": 0.0, "reinvested": round(shares * cost, 2)}
            world.log(f"{agent.name} reinvested {shares * cost:.2f} of retained earnings: building "
                      f"{shares:.2f} more {good} asset(s), needs {economy.describe(need)}")
            return True
        return False

    def plan(self, agent, world):
        rules = world.rules
        banking = world.banking
        prices = world.current_prices()
        if self.reinvest(agent, world, prices):
            return
        deposits = sum(agent.deposits.values())
        # Deposits count as its money: it takes them out when it builds.
        # Only what is left after its budget (living costs and loan payments for budget_steps).
        spare = agent.money + deposits - budget_needed(agent, prices, world)
        if spare < rules.min_investment:
            return
        asset_prices = world.step_asset_prices()
        budget = min(spare, purchase_limit(agent, asset_prices, rules.capital_cash_ratio))
        owns_bank = any(b.owner_id == agent.id for b in banking.banks)
        # Best q first (the same for every agent this step); build the best one it can get. A new
        # bank also needs its founder's own minimum capital on top of the plant.
        best = None
        for good, best_q, best_cost in ranked_builds(world, prices, asset_prices):
            if good == "banking" and not owns_bank and spare - best_cost * MIN_PROJECT_SHARES < banking.min_capital:
                continue
            if self.available(good, world, agent):
                best = good
                break
        if best is None:
            return
        if best == "banking" and not owns_bank:
            budget = min(budget, spare - banking.min_capital)
        # Borrow what its own money doesn't cover, when the asset earns more than the loan costs.
        # Personality: risk appetite (0-1) sets how big it builds (up to 1 + 4 x appetite shares)
        # and whether it borrows for it: only agents with at least BORROW_APPETITE take a loan,
        # and only when the asset earns more than the loan costs.
        appetite = agent.personality.get("risk_appetite", 0.0)
        most = MAX_PROJECT_SHARES * (1 + ENTREPRENEUR_SCALE * appetite)
        wanted = most * best_cost
        borrowed = 0.0
        if (budget < wanted and appetite >= BORROW_APPETITE and banking.available(world)
                and asset_yield(best, world) > banking.loan_rate_now(world)):
            borrowed = banking.borrow(world, agent, wanted - budget, f"building {best}",
                                      extra_collateral=asset_prices[best] * most)
        shares = min(most, (budget + borrowed) / best_cost)
        if shares < MIN_PROJECT_SHARES:
            return
        banking.cash_up(agent, cash_needed(agent, prices, rules) + shares * best_cost)
        need = {k: math.ceil(round(units * shares, 9)) for k, units in rules.build_cost[best].items()}
        agent.project = {"good": best, "shares": round(shares, 4), "need": need, "started": world.tick,
                         "q": round(best_q, 2), "borrowed": round(borrowed, 2)}
        world.log(f"{agent.name} started building {shares:.2f} {best} asset(s) (worth {best_q:.1f}x their cost): "
                  f"needs {economy.describe(need)}" + (f", {borrowed:.2f} of it borrowed" if borrowed else ""))

    @staticmethod
    def available(good, world, agent):
        """Can the capital goods for one share of ``good`` be bought now? Other agents together
        have at least that much to spare (spare_table: worked out once per step) and no other
        project already claims it. Capital goods are slow to make, so this paces building."""
        claimed = claimed_capital_goods(world)
        for k, units in world.rules.build_cost[good].items():
            on_offer = world.spare_total(k) - world.spare_table.get(k, {}).get(agent, 0)
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
