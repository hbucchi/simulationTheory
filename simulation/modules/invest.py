from .. import economy
from .base import Module

# Owners only sell to cover a cash shortfall of at least this much money, so agents a
# fraction of a cent short don't sell dust-sized slivers of assets every step.
MIN_SALE = 1.0


class Invest(Module):
    """Spends money above what the agent wants on hand on productive assets.

    Each resource has its own asset type. Holdings are shares: 0.5 of a food
    asset gets half its output. The current value of one whole asset is
    world.asset_value[r] (it grows over time); one asset produces
    value x asset_return[r] units of r per step (see Production).

    The agent keeps cash_needed (liquidity for rules.liquidity_units of every
    resource at current prices, plus the cost of what it needs to buy now) and,
    once at least rules.min_investment is spare, spends all of the spare on the
    single best asset: the highest return per money per step, counting both its
    output (asset_return x current price of the resource) and its value growth.

    It buys first from owners that are short of cash (most short first), paying
    them the current value for just enough shares to cover their shortfall. The
    rest are new shares from the builder.
    """

    def on_step(self, agent, world):
        rules = world.rules
        if not rules.investing_enabled:
            return
        prices = world.current_prices()
        # Same cash rule as sellers use, so an agent never invests money it then has to sell back for.
        spare = agent.money - cash_needed(agent, prices, rules)
        if spare < rules.min_investment:
            return
        best = best_asset(prices, world)
        if best is None:
            return
        value = world.asset_value[best]
        bought_from = {}
        sellers = sorted((o for o in world.agents if o is not agent and o.assets.get(best, 0) > 0
                          and cash_needed(o, prices, rules) - o.money >= MIN_SALE), key=lambda o: o.money)
        for seller in sellers:
            if spare <= 1e-9:
                break
            shortfall = cash_needed(seller, prices, rules) - seller.money
            money = min(spare, shortfall, seller.assets[best] * value)
            shares = money / value
            transfer_shares(seller, agent, best, shares)
            seller.money += money
            agent.money -= money
            spare -= money
            bought_from[seller.name] = bought_from.get(seller.name, 0) + shares
            world.asset_resales += 1
            world.asset_resale_money += money
        new_shares = spare / value if spare > 1e-9 else 0
        if new_shares:
            agent.money -= spare
            agent.assets[best] = agent.assets.get(best, 0) + new_shares
            world.pay_builder(spare)
        parts = [f"{n:.2f} from {name}" for name, n in bought_from.items()]
        if new_shares:
            parts.append(f"{new_shares:.2f} new from the builder")
        total = sum(bought_from.values()) + new_shares
        held = agent.assets[best]
        world.log(f"{agent.name} invested {total * value:.2f} in {total:.2f} {best} asset(s) at {value:.2f} each "
                  f"({', '.join(parts)}); now owns {held:.2f}, making {world.asset_output(best, held):.2f} "
                  f"{best}/step")


def transfer_shares(seller, buyer, resource, shares):
    seller.assets[resource] -= shares
    if seller.assets[resource] <= 1e-9:
        del seller.assets[resource]
    buyer.assets[resource] = buyer.assets.get(resource, 0) + shares


def cash_needed(agent, prices, rules):
    """Money an agent wants on hand: its liquidity plus the cost of what it needs to buy now."""
    liquidity = rules.liquidity_units * sum(prices.values())
    shopping = sum(economy.demand(agent, r, rules) * prices[r] for r in economy.RESOURCES)
    return liquidity + shopping


def asset_yield(resource, prices, world):
    """Money earned per step per money invested in ``resource`` assets: output + value growth."""
    output = world.rules.asset_return[resource] * prices[resource]
    return output + world.asset_growth_per_step(resource)


def best_asset(prices, world):
    """Resource whose asset earns the most per money invested, or None."""
    yields = {r: asset_yield(r, prices, world) for r in economy.RESOURCES}
    best = max(yields, key=yields.get)
    return best if yields[best] > 0 else None
