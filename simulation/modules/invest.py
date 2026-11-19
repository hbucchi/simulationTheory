from .. import economy
from .base import Module

# Owners only sell to cover a cash shortfall of at least this share of min_investment, so
# agents a fraction of a cent short don't sell dust-sized slivers of assets every step.
MIN_SALE_SHARE = 0.1
# An owner holding more than the stock cap of a resource sells at most this share of its
# assets of that resource per deal.
SURPLUS_SELL_SHARE = 0.25


class Invest(Module):
    """Buys asset shares from other agents with money above what the agent wants on hand.

    No assets are created: the only ones are the starting assets, and shares only
    move between agents. One whole asset of resource r costs
    world.asset_prices()[r] = output per step x current price of r / asset_return[r].

    The agent keeps cash_needed (liquidity for rules.liquidity_units of every
    resource at current prices, plus the cost of what it needs to buy now). Once
    at least rules.min_investment is spare, it buys shares of the best asset that
    someone is selling (highest asset_return plus value growth per step), but
    only of resources it lacks: needs now, or below the floor of its stock band.
    (Owners sell above the cap, so the band between floor and cap keeps the same
    shares from going back and forth.) With the stock band off, any resource.

    Capitalist cash rule: the purchase must also leave the agent holding at least
    rules.capital_cash_ratio x the value of all its assets (the new one included) in cash,
    so it can still pay the labour those assets need. With ratio r, cash M and assets worth A,
    it spends at most (M - r x A) / (1 + r).

    Owners sell for two reasons:
    - short of cash (by at least MIN_SALE_SHARE of min_investment): just enough shares to cover the gap,
      most cash-short first;
    - holding more than the stock cap of the resource: they don't need more of it,
      so they sell up to SURPLUS_SELL_SHARE of those assets per deal.
    """

    def on_step(self, agent, world):
        rules = world.rules
        if not rules.investing_enabled or agent.project:   # its money is going into a building project
            return
        prices = world.current_prices()
        # Same cash rule as sellers use, so an agent never invests money it then has to sell back for.
        spare = agent.money - cash_needed(agent, prices, rules)
        if spare < rules.min_investment:
            return
        asset_prices = world.step_asset_prices()
        spare = min(spare, purchase_limit(agent, asset_prices, rules.capital_cash_ratio))
        if spare < rules.min_investment:
            return
        # Owners short of cash: {agent: shortfall}, most short first (worked out once per step).
        short = {o: gap for o, gap in cash_short_owners(world, prices).items() if o is not agent}
        for resource in ranked_assets(world):
            price = asset_prices[resource]
            # Who wants each good is worked out once per step (World.update_demand); ask directly
            # if that hasn't run yet.
            buyers = world.buyer_sets.get(resource)
            wants = agent in buyers if buyers is not None else economy.wants_to_buy(agent, resource, rules, world.scarcity)
            lacks = wants or not rules.selling_enabled
            if price <= 0 or not lacks:
                continue   # worthless, or it isn't short of this resource
            # Cash-short owners first (they need the money most), then owners over the cap.
            owners = world.owners_of(resource)
            limits = {o: short[o] for o in owners if o in short}
            for o in owners:
                if (o is not agent and o not in limits and world.surpluses_of(o).get(resource)):
                    limits[o] = o.assets[resource] * SURPLUS_SELL_SHARE * price
            if not limits:
                continue
            bought = {}
            for seller, limit in limits.items():
                if spare <= 1e-9:
                    break
                money = min(spare, limit, seller.assets[resource] * price)
                shares = money / price
                transfer_shares(seller, agent, resource, shares)
                seller.money += money
                economy.earn(seller, money, "assets")
                agent.money -= money
                spare -= money
                bought[seller.name] = shares
                world.asset_trades += 1
                world.asset_trade_money += money
            held = agent.assets[resource]
            total = sum(bought.values())
            # Name the three biggest sellers; the rest are counted.
            top = sorted(bought.items(), key=lambda kv: kv[1], reverse=True)
            sources = ", ".join(f"{n:.2f} from {name}" for name, n in top[:3])
            if len(top) > 3:
                sources += f" and {sum(n for _, n in top[3:]):.2f} from {len(top) - 3} others"
            world.log(f"{agent.name} bought {total:.2f} {resource} asset(s) at {price:.2f} each for "
                      f"{total * price:.2f} ({sources}); "
                      f"now owns {held:.2f}, making {world.asset_output(resource, held):.2f} {resource}/step")
            return


def cash_short_owners(world, prices):
    """{owner: how much cash it is short}, most short first, for owners short by at least
    MIN_SALE_SHARE of min_investment. Worked out once per step (fresh outside a step)."""
    cache = world._step_cache
    if cache and "cash_short" in cache:
        return cache["cash_short"]
    rules = world.rules
    min_sale = rules.min_investment * MIN_SALE_SHARE
    short = {o: cash_needed(o, prices, rules) - o.money for o in world.agents if o.assets}
    short = {o: gap for o, gap in sorted(short.items(), key=lambda kv: kv[0].money) if gap >= min_sale}
    if cache is not None:
        cache["cash_short"] = short
    return short


def transfer_shares(seller, buyer, resource, shares):
    seller.assets[resource] -= shares
    if seller.assets[resource] <= 1e-9:
        del seller.assets[resource]
    buyer.assets[resource] = buyer.assets.get(resource, 0) + shares


def purchase_limit(agent, asset_prices, ratio):
    """Most the agent can spend on a new asset and still hold ``ratio`` x its assets in cash."""
    held = sum(shares * asset_prices.get(g, 0.0) for g, shares in agent.assets.items())
    return max(0.0, (agent.money - ratio * held) / (1 + ratio))


def cash_needed(agent, prices, rules):
    """Money an agent wants on hand: its liquidity plus the cost of what it needs to buy now."""
    return economy.liquidity_cost(prices, rules) + economy.shopping_cost(agent, prices, rules)


def asset_yield(resource, world):
    """Money earned per step per money invested: asset_return (output at the asset's price)
    plus productivity growth (which raises its output and so its price)."""
    return world.government.effective_return(world.rules, resource) + world.productivity_growth_per_step(resource)


def ranked_assets(world):
    """Resources ordered from the best asset to buy to the worst (once per step)."""
    cache = world._step_cache
    if cache and "ranked_assets" in cache:
        return cache["ranked_assets"]
    ranked = sorted(world.rules.active_goods, key=lambda r: asset_yield(r, world), reverse=True)
    if cache is not None:
        cache["ranked_assets"] = ranked
    return ranked
