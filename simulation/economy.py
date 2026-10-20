"""Rules of the economy: what resources exist, what they satisfy, and how trading works.

Need scale reminder: 0.00 = satisfied, 1.00 = desperate.
"""

import math

RESOURCES = ("food", "water", "games")
# Which need each resource relieves. Sleep is recovered by resting (modules/rest.py).
NEED_FOR_RESOURCE = {"food": "hunger", "water": "thirst", "games": "boredom"}

RELIEF_PER_UNIT = 0.1   # consuming 1 unit lowers its need by 0.1
SEEK_THRESHOLD = 0.5    # above this an agent acts: consume, or go find someone to trade with
TARGET_LEVEL = 0.3      # consume/trade until the need is below this

DEFAULT_INVENTORY = {"food": 100, "water": 100, "games": 100}
DEFAULT_MONEY = 100.0
DEFAULT_PRODUCTION = {r: 10 for r in RESOURCES}  # 1 unit every N steps (0 = never)

# A need reaching this level has consequences: hunger/thirst -> death, boredom -> depression.
CRITICAL_LEVEL = 1.0


def market_prices(agents):
    """Money price of one unit of each resource, from what everyone holds right now.

        price(r) = total money / total units of all resources * (1 - share of r)

    where share of r = units of r / total units. The scarcer a resource
    (smaller share), the higher its price. No goods at all -> every price is 0.
    """
    money = sum(a.money for a in agents)
    units = {r: sum(a.inventory.count(r) for a in agents) for r in RESOURCES}
    total = sum(units.values())
    if total == 0:
        return {r: 0.0 for r in RESOURCES}
    return {r: money / total * (1 - units[r] / total) for r in RESOURCES}


def units_to_satisfy(level):
    """Units needed to bring a need strictly below TARGET_LEVEL (0 if already below)."""
    if level < TARGET_LEVEL:
        return 0
    # round() guards against float noise such as 0.6 - 0.3 = 0.29999999999999993
    return math.floor(round((level - TARGET_LEVEL) / RELIEF_PER_UNIT, 9)) + 1


def transfer(giver, receiver, resource, qty=1):
    giver.inventory.remove(resource, qty)
    receiver.inventory.add(resource, qty)


def pay(payer, payee, amount):
    payer.money -= amount
    payee.money += amount


def consume(agent):
    """Eat/drink/play from own stock for every need above SEEK_THRESHOLD.

    Returns {resource: units consumed}.
    """
    eaten = {}
    for resource, need in NEED_FOR_RESOURCE.items():
        level = getattr(agent, need)
        if level <= SEEK_THRESHOLD:
            continue
        units = min(units_to_satisfy(level), agent.inventory.count(resource))
        if units:
            agent.inventory.remove(resource, units)
            setattr(agent, need, level - units * RELIEF_PER_UNIT)
            eaten[resource] = units
    return eaten


def is_needy(agent):
    """True when some resource-backed need is above the threshold (stock already used up)."""
    return any(getattr(agent, need) > SEEK_THRESHOLD for need in NEED_FOR_RESOURCE.values())


def demand(agent, resource):
    """Units the agent wants to buy: enough to drop the need below TARGET_LEVEL, minus stock."""
    level = getattr(agent, NEED_FOR_RESOURCE[resource])
    if level <= SEEK_THRESHOLD:
        return 0
    return max(0, units_to_satisfy(level) - agent.inventory.count(resource))


def spare(agent, resource):
    """Units the agent can give away without hurting its own current needs."""
    reserve = units_to_satisfy(getattr(agent, NEED_FOR_RESOURCE[resource]))
    return max(0, agent.inventory.count(resource) - reserve)


def _settle_one(buyer, seller, buying, prices):
    """Buyer gets one unit of ``buying``. Returns (resource given in exchange or None, money buyer paid).

    Payment preference: a resource the seller needs (barter), then money, then
    any other spare resource. In a barter the price difference is settled in
    money by whichever side got the cheaper deal. Returns None if the buyer
    can't pay at all.
    """
    price = prices[buying]
    needed_by_seller = [r for r in RESOURCES if r != buying and demand(seller, r) > 0]
    others = [r for r in RESOURCES if r != buying and r not in needed_by_seller]
    for option in needed_by_seller + ["money"] + others:
        if option == "money":
            if buyer.money >= price:
                return None, price
            continue
        if spare(buyer, option) == 0:
            continue
        diff = price - prices[option]   # > 0: buyer tops up; < 0: seller gives change
        payer = buyer if diff > 0 else seller
        if payer.money >= abs(diff):
            return option, diff
    return None


def buy(buyer, seller, prices):
    """Buyer acquires what it needs from seller at market prices.

    Returns (bought, paid): bought = {resource: units}; paid = {resource: units,
    "money": net money buyer -> seller (negative = buyer received change)}.
    """
    bought, paid = {}, {}
    wants = sorted(RESOURCES, key=lambda r: getattr(buyer, NEED_FOR_RESOURCE[r]), reverse=True)
    for resource in wants:
        while demand(buyer, resource) > 0 and spare(seller, resource) > 0:
            settled = _settle_one(buyer, seller, resource, prices)
            if settled is None:
                return bought, paid
            given, money = settled
            transfer(seller, buyer, resource)
            if given:
                transfer(buyer, seller, given)
                paid[given] = paid.get(given, 0) + 1
            pay(buyer, seller, money)
            paid["money"] = paid.get("money", 0.0) + money
            bought[resource] = bought.get(resource, 0) + 1
    return bought, paid


def trade(a, b, prices):
    """Both agents buy what they need from each other, then consume. Returns a list of deals."""
    deals = []
    for buyer, seller in ((a, b), (b, a)):
        bought, paid = buy(buyer, seller, prices)
        if bought:
            deals.append((buyer, seller, bought, paid))
    consume(a)
    consume(b)
    return deals


def unmet(buyer, seller):
    """Why ``buyer`` still lacks something after dealing with ``seller`` (list of strings)."""
    reasons = []
    for resource in RESOURCES:
        missing = demand(buyer, resource)
        if not missing:
            continue
        stock = seller.inventory.count(resource)
        if stock == 0:
            why = f"{seller.name} has none"
        elif spare(seller, resource) == 0:
            why = f"{seller.name} keeps its {stock} for itself"
        else:
            why = "nothing left to pay with"
        reasons.append(f"{buyer.name} still needs {missing} {resource}: {why}")
    return reasons


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
