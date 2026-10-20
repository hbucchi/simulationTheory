"""Rules of the economy: what resources exist, what they satisfy, and how trading works.

Need scale reminder: 0.00 = satisfied, 1.00 = desperate.
"""

import math

RESOURCES = ("food", "water", "games")
# Which need each resource relieves. Sleep has no resource (yet).
NEED_FOR_RESOURCE = {"food": "hunger", "water": "thirst", "games": "boredom"}

RELIEF_PER_UNIT = 0.1   # consuming 1 unit lowers its need by 0.1
SEEK_THRESHOLD = 0.5    # above this an agent acts: consume, or go find someone to trade with
TARGET_LEVEL = 0.3      # consume/trade until the need is below this

DEFAULT_INVENTORY = {"food": 100, "water": 100, "games": 100}
DEFAULT_MONEY = 100.0
DEFAULT_PRODUCTION = {r: 10 for r in RESOURCES}  # 1 unit every N steps (0 = never)

ASSETS = RESOURCES + ("money",)  # everything that can change hands, all at 1:1


def units_to_satisfy(level):
    """Units needed to bring a need strictly below TARGET_LEVEL (0 if already below)."""
    if level < TARGET_LEVEL:
        return 0
    # round() guards against float noise such as 0.6 - 0.3 = 0.29999999999999993
    return math.floor(round((level - TARGET_LEVEL) / RELIEF_PER_UNIT, 9)) + 1


def holding(agent, asset):
    return int(agent.money) if asset == "money" else agent.inventory.count(asset)


def transfer(giver, receiver, asset, qty=1):
    if asset == "money":
        giver.money -= qty
        receiver.money += qty
    else:
        giver.inventory.remove(asset, qty)
        receiver.inventory.add(asset, qty)


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


def spare(agent, asset):
    """Units the agent can give away without hurting its own current needs."""
    if asset == "money":
        return int(agent.money)
    reserve = units_to_satisfy(getattr(agent, NEED_FOR_RESOURCE[asset]))
    return max(0, agent.inventory.count(asset) - reserve)


def _pick_payment(buyer, seller, buying):
    """What the buyer hands over for one unit: something the seller needs, else money, else any surplus."""
    candidates = [a for a in RESOURCES if a != buying and demand(seller, a) > 0]
    candidates += ["money"]
    candidates += [a for a in RESOURCES if a != buying and a not in candidates]
    for asset in candidates:
        if spare(buyer, asset) > 0:
            return asset
    return None


def buy(buyer, seller):
    """Buyer acquires what it needs from seller at 1:1. Returns (bought, paid) dicts."""
    bought, paid = {}, {}
    wants = sorted(RESOURCES, key=lambda r: getattr(buyer, NEED_FOR_RESOURCE[r]), reverse=True)
    for resource in wants:
        while demand(buyer, resource) > 0 and spare(seller, resource) > 0:
            payment = _pick_payment(buyer, seller, resource)
            if payment is None:
                return bought, paid
            transfer(seller, buyer, resource)
            transfer(buyer, seller, payment)
            bought[resource] = bought.get(resource, 0) + 1
            paid[payment] = paid.get(payment, 0) + 1
    return bought, paid


def trade(a, b):
    """Both agents buy what they need from each other, then consume. Returns a list of deals."""
    deals = []
    for buyer, seller in ((a, b), (b, a)):
        bought, paid = buy(buyer, seller)
        if bought:
            deals.append((buyer, seller, bought, paid))
    consume(a)
    consume(b)
    return deals


def describe(items):
    return " + ".join(f"{n} {k}" for k, n in items.items())
