from .. import economy
from .base import Module


class Leisure(Module):
    """Spending grows with wealth (personality module): every day an agent with money beyond its
    budget spends lavishness x rules.leisure_rate of that spare money on comfort goods (the
    rules.leisure_needs: entertainment and health by default), buying the good that gives the most
    relief per dollar from sellers within its trading radius, and enjoys it at once. Frugal agents
    (lavishness near 0) barely spend; lavish ones become big customers of the upper industries.
    """

    def on_step(self, agent, world):
        rules = world.rules
        lavish = agent.personality.get("lavishness", 0.0)
        if not rules.personality_enabled or lavish <= 0 or rules.leisure_rate <= 0 or not rules.commerce_enabled:
            return
        if economy.in_danger(agent, rules):
            return
        from .invest import budget_needed
        prices = world.current_prices()
        spare = economy.money_of(agent) - budget_needed(agent, prices, world)
        if spare <= rules.min_investment:
            return
        budget = spare * rules.leisure_rate * lavish
        radius = rules.trade_radius if rules.trade_radius > 0 else float("inf")
        for need in rules.leisure_needs:
            if need not in rules.consumer_needs or budget <= 0:
                continue
            # The best relief per dollar among goods someone within reach sells.
            options = []
            for g in rules.goods_for(need):
                price = prices.get(g, 0.0)
                if price <= 0:
                    continue
                sellers = [s for s in world.spare_table.get(g, {}) if s is not agent and s in world.alive
                           and agent.distance_to(s) <= radius]
                if sellers:
                    options.append((rules.relief(g, need) / price, g, price, sellers))
            if not options:
                continue
            _, good, price, sellers = max(options, key=lambda o: o[0])
            share = budget / len(rules.leisure_needs)
            for seller in sorted(sellers, key=agent.distance_to):
                units = min(int(share // price), economy.spare(seller, good, rules, world.scarcity))
                if units <= 0:
                    break
                world.leisure_sale(agent, seller, good, units, price)
                share -= units * price
                budget -= units * price
