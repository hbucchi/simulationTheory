import math

from .. import economy
from .base import Module


class Invest(Module):
    """Spends money above a liquidity reserve on productive assets.

    It keeps cash_needed (liquidity: enough money to buy rules.liquidity_units of
    every resource at current prices, plus the cost of what it needs right now).
    Above that, the agent buys as many assets as it can
    afford of the single best one: the asset adding the most income per money
    spent (extra units per step x current price / asset price). Assets of a
    resource the agent doesn't produce add nothing, so they are never bought.

    It buys first from agents that own that asset and are short of cash (see
    cash_needed), most cash-short first, paying them the asset price; a seller
    stops once it has the cash it needs. The rest are new assets from the
    builder.
    """

    def on_step(self, agent, world):
        rules = world.rules
        if not rules.investing_enabled:
            return
        prices = world.current_prices()
        # Same cash rule as sellers use, so an agent never invests money it then has to sell back for.
        spare = agent.money - cash_needed(agent, prices, rules)
        best = best_asset(agent, prices, rules)
        if best is None or spare < rules.asset_price[best]:
            return
        price = rules.asset_price[best]
        count = math.floor(spare / price)
        bought_from = {}
        sellers = sorted((o for o in world.agents if o is not agent and o.assets.get(best, 0) > 0
                          and o.money < cash_needed(o, prices, rules)), key=lambda o: o.money)
        for seller in sellers:
            need = cash_needed(seller, prices, rules)
            while count and seller.assets.get(best, 0) > 0 and seller.money < need:
                seller.assets[best] -= 1
                seller.money += price
                agent.money -= price
                agent.assets[best] = agent.assets.get(best, 0) + 1
                bought_from[seller.name] = bought_from.get(seller.name, 0) + 1
                world.asset_resales += 1
                world.asset_resale_money += price
                count -= 1
            if not seller.assets.get(best):
                seller.assets.pop(best, None)
        if count:
            agent.money -= count * price
            agent.assets[best] = agent.assets.get(best, 0) + count
            world.pay_builder(count * price)
        parts = [f"{n} from {name}" for name, n in bought_from.items()] + ([f"{count} new from the builder"] if count else [])
        total = sum(bought_from.values()) + count
        world.log(f"{agent.name} bought {total} {best} asset{'s' if total > 1 else ''} for {total * price:.2f} "
                  f"({', '.join(parts)}; {best} output now +{agent.assets[best] * rules.asset_return[best] * 100:.0f}%)")


def cash_needed(agent, prices, rules):
    """Money an agent wants on hand: its liquidity plus the cost of what it needs to buy now."""
    liquidity = rules.liquidity_units * sum(prices.values())
    shopping = sum(economy.demand(agent, r, rules) * prices[r] for r in economy.RESOURCES)
    return liquidity + shopping


def asset_income(agent, resource, prices, rules):
    """Money per step one more asset of ``resource`` would add, at current prices."""
    every = next((m.intervals.get(resource) for m in agent.modules if hasattr(m, "intervals")), 0)
    if not every:
        return 0.0
    return rules.asset_return[resource] / every * prices[resource]


def best_asset(agent, prices, rules):
    """Resource whose asset adds the most income per money spent, or None."""
    value = {r: asset_income(agent, r, prices, rules) / rules.asset_price[r]
             for r in economy.RESOURCES if rules.asset_price[r] > 0}
    best = max(value, key=value.get, default=None)
    return best if best and value[best] > 0 else None
