"""Rules of the economy: what resources exist, what they satisfy, and how trading works.

Need scale reminder: 0.00 = satisfied, 1.00 = desperate.
"""

import math

from .rules import DEFAULT_RULES, RESOURCES

# Which need each resource relieves. Sleep is recovered by resting (modules/rest.py).
NEED_FOR_RESOURCE = {"food": "hunger", "water": "thirst", "games": "boredom"}

# A need reaching this level has consequences: hunger/thirst -> death, boredom -> depression.
CRITICAL_LEVEL = 1.0

# A reserve is at most this many times the base stockpile (when a resource falls 3x the trigger).
MAX_STOCKPILE_LEVEL = 3

# Every function below takes the game's Rules (thresholds, relief per unit,
# price mode); they default to the standard rules. Functions that take
# ``scarcity`` get {resource: decline} from the World (how much the average
# units per agent fell over the scarcity window); None means no stockpiling.


def market_prices(agents, rules=DEFAULT_RULES, extra_money=0.0):
    """Money price of one unit of each resource.

    "fixed" mode: the prices set in the rules. "scarcity" mode, from what
    everyone holds right now:

        price(r) = total money / total units of all resources * (1 - share of r)

    where share of r = units of r / total units. The scarcer a resource
    (smaller share), the higher its price. No goods at all -> every price is 0.
    ``extra_money`` is money held outside the agents that still belongs to the
    economy (the asset builder's funds, on their way back to the agents).
    """
    if rules.price_mode == "fixed":
        return dict(rules.fixed_prices)
    money = sum(a.money for a in agents) + extra_money
    units = {r: sum(a.inventory.count(r) for a in agents) for r in RESOURCES}
    total = sum(units.values())
    if total == 0:
        return {r: 0.0 for r in RESOURCES}
    return {r: money / total * (1 - units[r] / total) for r in RESOURCES}


def units_to_satisfy(level, rules=DEFAULT_RULES):
    """Units needed to bring a need strictly below the target level (0 if already below)."""
    if level < rules.target_level:
        return 0
    # round() guards against float noise such as 0.6 - 0.3 = 0.29999999999999993
    return math.floor(round((level - rules.target_level) / rules.relief_per_unit, 9)) + 1


def transfer(giver, receiver, resource, qty=1):
    giver.inventory.remove(resource, qty)
    receiver.inventory.add(resource, qty)


def pay(payer, payee, amount):
    payer.money -= amount
    payee.money += amount


def consume(agent, rules=DEFAULT_RULES):
    """Eat/drink/play from own stock for every need above the seek threshold.

    Returns {resource: units consumed}.
    """
    eaten = {}
    for resource, need in NEED_FOR_RESOURCE.items():
        level = getattr(agent, need)
        if level <= rules.seek_threshold:
            continue
        units = min(units_to_satisfy(level, rules), agent.inventory.count(resource))
        if units:
            agent.inventory.remove(resource, units)
            setattr(agent, need, level - units * rules.relief_per_unit)
            eaten[resource] = units
    return eaten


def is_needy(agent, rules=DEFAULT_RULES):
    """True when some resource-backed need is above the threshold (stock already used up)."""
    return any(getattr(agent, need) > rules.seek_threshold for need in NEED_FOR_RESOURCE.values())


def demand(agent, resource, rules=DEFAULT_RULES):
    """Units the agent wants to buy: enough to drop the need below the target, minus stock."""
    level = getattr(agent, NEED_FOR_RESOURCE[resource])
    if level <= rules.seek_threshold:
        return 0
    return max(0, units_to_satisfy(level, rules) - agent.inventory.count(resource))


def net_use(agent, resource, rules=DEFAULT_RULES):
    """Units per step the agent uses beyond what it produces itself (0 if self-sufficient)."""
    rates = next((m.rates for m in agent.modules if hasattr(m, "rates")), {})
    every = next((m.intervals.get(resource) for m in agent.modules if hasattr(m, "intervals")), 0)
    used = rates.get(NEED_FOR_RESOURCE[resource], 0) / rules.relief_per_unit
    return max(0.0, used - (1 / every if every else 0))


def stockpile_target(agent, resource, rules=DEFAULT_RULES, scarcity=None):
    """Units the agent wants in reserve because ``resource`` is becoming scarce (0 if it isn't).

    Reserve = net use per step x stockpile_steps x (decline / trigger), capped at
    MAX_STOCKPILE_LEVEL: the faster the resource disappears, the more it hoards.
    """
    if not scarcity or not rules.stockpiling_enabled:
        return 0
    decline = scarcity.get(resource, 0)
    if decline < rules.scarcity_trigger:
        return 0
    level = min(MAX_STOCKPILE_LEVEL, decline / rules.scarcity_trigger)
    return math.ceil(round(net_use(agent, resource, rules) * rules.stockpile_steps * level, 9))


def stockpile_shortfall(agent, resource, rules=DEFAULT_RULES, scarcity=None):
    return max(0, stockpile_target(agent, resource, rules, scarcity) - agent.inventory.count(resource))


def wants_anything(agent, rules=DEFAULT_RULES, scarcity=None):
    """Needs something now, or is below a stockpile reserve."""
    return is_needy(agent, rules) or any(stockpile_shortfall(agent, r, rules, scarcity) for r in RESOURCES)


def spare(agent, resource, rules=DEFAULT_RULES, scarcity=None):
    """Units the agent can give away without hurting its current needs or its reserve."""
    reserve = max(units_to_satisfy(getattr(agent, NEED_FOR_RESOURCE[resource]), rules),
                  stockpile_target(agent, resource, rules, scarcity))
    return max(0, agent.inventory.count(resource) - reserve)


def _settle_one(buyer, seller, buying, prices, rules, scarcity=None, money_only=False):
    """Buyer gets one unit of ``buying``. Returns (resource given in exchange or None, money buyer paid).

    Payment preference: a resource the seller needs (barter), then money, then
    any other spare resource. In a barter the price difference is settled in
    money by whichever side got the cheaper deal. Returns None if the buyer
    can't pay at all. ``money_only`` (stockpiling) never gives goods away.
    """
    price = prices[buying]
    if money_only:
        return (None, price) if buyer.money >= price else None
    needed_by_seller = [r for r in RESOURCES if r != buying and demand(seller, r, rules) > 0]
    others = [r for r in RESOURCES if r != buying and r not in needed_by_seller]
    for option in needed_by_seller + ["money"] + others:
        if option == "money":
            if buyer.money >= price:
                return None, price
            continue
        if spare(buyer, option, rules, scarcity) == 0:
            continue
        diff = price - prices[option]   # > 0: buyer tops up; < 0: seller gives change
        payer = buyer if diff > 0 else seller
        if payer.money >= abs(diff):
            return option, diff
    return None


def purchase_goal(buyer, resource, rules, rng=None):
    """How many units the buyer wants to hold after buying ``resource``.

    It needs units_to_satisfy(level); it buys that times a random multiplier in
    [purchase_min, purchase_max] (rounded up), so it stocks up for later. With no
    rng the multiplier is purchase_min. Returns 0 if it doesn't need the resource.
    """
    if not demand(buyer, resource, rules):
        return 0
    needed = units_to_satisfy(getattr(buyer, NEED_FOR_RESOURCE[resource]), rules)
    multiplier = rng.uniform(rules.purchase_min, rules.purchase_max) if rng else rules.purchase_min
    return math.ceil(round(needed * multiplier, 9))


def buy(buyer, seller, prices, rules=DEFAULT_RULES, rng=None, scarcity=None, markups=None):
    """Buyer acquires what it needs (times a random multiplier) from seller at market prices,
    plus any stockpile reserve it is missing.

    It stops when it reaches its goal, the seller has no spare left, or it
    can't pay. Units bought only for the reserve are paid in money, up to
    stockpile_budget of the money the buyer had at the start. ``markups``
    ({resource: rate}) makes each extra unit of a resource in this deal cost
    that much more than the previous one (price x (1 + rate) ** k).
    Returns (bought, paid, stocked, unit_prices): bought = {resource: units};
    paid = {resource: units, "money": net money buyer -> seller (negative =
    change)}; stocked = {resource: units of bought that went to the reserve};
    unit_prices = {resource: [first unit price, last unit price]}.
    """
    bought, paid, stocked, unit_prices = {}, {}, {}, {}
    budget = buyer.money * rules.stockpile_budget
    spent_on_reserve = 0.0
    wants = sorted(RESOURCES, key=lambda r: getattr(buyer, NEED_FOR_RESOURCE[r]), reverse=True)
    for resource in wants:
        need_goal = purchase_goal(buyer, resource, rules, rng)
        goal = max(need_goal, stockpile_target(buyer, resource, rules, scarcity))
        markup = (markups or {}).get(resource, 0)
        while buyer.inventory.count(resource) < goal and spare(seller, resource, rules, scarcity) > 0:
            unit_price = prices[resource] * (1 + markup) ** bought.get(resource, 0)
            for_reserve = buyer.inventory.count(resource) >= need_goal
            if for_reserve and spent_on_reserve + unit_price > budget:
                break
            settled = _settle_one(buyer, seller, resource, {**prices, resource: unit_price}, rules, scarcity,
                                  money_only=for_reserve)
            if settled is None:
                return bought, paid, stocked, unit_prices
            unit_prices.setdefault(resource, [unit_price, unit_price])[1] = unit_price
            if for_reserve:
                spent_on_reserve += unit_price
                stocked[resource] = stocked.get(resource, 0) + 1
            given, money = settled
            transfer(seller, buyer, resource)
            if given:
                transfer(buyer, seller, given)
                paid[given] = paid.get(given, 0) + 1
            pay(buyer, seller, money)
            paid["money"] = paid.get("money", 0.0) + money
            bought[resource] = bought.get(resource, 0) + 1
    return bought, paid, stocked, unit_prices


def trade(a, b, prices, rules=DEFAULT_RULES, rng=None, scarcity=None, markups=None):
    """Both agents buy what they need (and any stockpile) from each other, then consume.

    Returns a list of deals: (buyer, seller, bought, paid, stocked, unit_prices).
    """
    deals = []
    for buyer, seller in ((a, b), (b, a)):
        bought, paid, stocked, unit_prices = buy(buyer, seller, prices, rules, rng, scarcity, markups)
        if bought:
            deals.append((buyer, seller, bought, paid, stocked, unit_prices))
    consume(a, rules)
    consume(b, rules)
    return deals


def unmet(buyer, seller, rules=DEFAULT_RULES, scarcity=None):
    """Why ``buyer`` still lacks something after dealing with ``seller`` (list of strings)."""
    reasons = []
    for resource in RESOURCES:
        missing = demand(buyer, resource, rules)
        if not missing:
            continue
        stock = seller.inventory.count(resource)
        if stock == 0:
            why = f"{seller.name} has none"
        elif spare(seller, resource, rules, scarcity) == 0:
            why = f"{seller.name} keeps its {stock} for itself"
        else:
            why = "nothing left to pay with"
        reasons.append(f"{buyer.name} still needs {missing} {resource}: {why}")
    return reasons


def demand_multiplier_target(buyers, sellers, rules=DEFAULT_RULES):
    """Where demand pressure pushes a resource's price multiplier.

    ((buyers + 1) / (sellers + 1)) ** price_elasticity, kept within
    [price_floor, price_cap]. The +1s keep it finite when nobody sells, and
    make 0 buyers vs 0 sellers neutral (x1).
    """
    ratio = ((buyers + 1) / (sellers + 1)) ** rules.price_elasticity
    return min(max(ratio, rules.price_floor), rules.price_cap)


def describe(items):
    return " + ".join(f"{n} {k}" for k, n in items.items())


def describe_payment(paid):
    """e.g. '3.20 money', '2 food + 0.15 money', '2 food (got 0.40 money change)'."""
    goods = {k: n for k, n in paid.items() if k != "money"}
    money = round(paid.get("money", 0.0), 2)
    parts = [describe(goods)] if goods else []
    if money > 0:
        parts.append(f"{money:.2f} money")
    text = " + ".join(parts) or "nothing (free)"
    if money < 0:
        text += f" (got {-money:.2f} money change)"
    return text
