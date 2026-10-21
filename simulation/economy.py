"""Rules of the economy: what resources exist, what they satisfy, and how trading works.

Need scale reminder: 0.00 = satisfied, 1.00 = desperate.
"""

import math

from .rules import DEFAULT_RULES, GOODS, LABOR, RESOURCES

# Which need each good relieves. Sleep is recovered by resting (modules/rest.py). Labour
# relieves no need: it is bought by asset owners to make goods.
NEED_FOR_RESOURCE = {"food": "hunger", "water": "thirst", "games": "boredom"}

# A need reaching this level has consequences: hunger/thirst -> death, boredom -> depression.
CRITICAL_LEVEL = 1.0

# A reserve is at most this many times the base stockpile (when a resource falls 3x the trigger).
MAX_STOCKPILE_LEVEL = 3

# Every function below takes the game's Rules (thresholds, relief per unit,
# price mode); they default to the standard rules. Functions that take
# ``scarcity`` get {resource: decline} from the World (how much the average
# units per agent fell over the scarcity window); None means no stockpiling.


def market_prices(agents, rules=DEFAULT_RULES):
    """Money price of one unit of each resource.

    "fixed" mode: the prices set in the rules. "scarcity" mode, from what
    everyone holds right now:

        price(r) = total money / total units of all resources * (1 - share of r)

    where share of r = units of r / total units. The scarcer a resource
    (smaller share), the higher its price. No goods at all -> every price is 0.
    """
    if rules.price_mode == "fixed":
        return dict(rules.fixed_prices)
    money = sum(a.money for a in agents)
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
    """Move ``qty`` units. Perishable units (labour) keep their expiry date, oldest given first."""
    if resource in giver.inventory.perishable:
        for expires, units in giver.inventory.take(resource, qty):
            receiver.inventory.add(resource, units, expires=expires)
        return
    giver.inventory.remove(resource, qty)
    receiver.inventory.add(resource, qty)


def pay(payer, payee, amount):
    """Move money; whoever receives it (the payee, or the payer when it gets change) earns income."""
    payer.money -= amount
    payee.money += amount
    receiver = payee if amount > 0 else payer
    receiver.flow["income"] += abs(amount)


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
            agent.flow["consumed"][resource] = agent.flow["consumed"].get(resource, 0) + units
            eaten[resource] = units
    return eaten


def is_needy(agent, rules=DEFAULT_RULES):
    """True when some resource-backed need is above the threshold (stock already used up)."""
    return any(getattr(agent, need) > rules.seek_threshold for need in NEED_FOR_RESOURCE.values())


def labor_target(agent, rules=DEFAULT_RULES):
    """Labour an owner wants on hand: labor_buffer_steps steps of what its assets use."""
    return math.ceil(round(agent.labor_need * rules.labor_buffer_steps, 9))


def need_level(agent, resource):
    """How strong the need behind ``resource`` is (0 for labour, which has none)."""
    return getattr(agent, NEED_FOR_RESOURCE[resource]) if resource in NEED_FOR_RESOURCE else 0.0


def demand(agent, resource, rules=DEFAULT_RULES):
    """Units the agent wants to buy: enough to drop the need below the target, minus stock.

    For labour: once its labour falls below half its labour target, enough to refill it.
    """
    if resource == LABOR:
        target, stock = labor_target(agent, rules), agent.inventory.count(LABOR)
        return target - stock if stock < target / 2 else 0
    level = getattr(agent, NEED_FOR_RESOURCE[resource])
    if level <= rules.seek_threshold:
        return 0
    return max(0, units_to_satisfy(level, rules) - agent.inventory.count(resource))


def net_use(agent, resource, rules=DEFAULT_RULES):
    """Units of a good the agent uses per step beyond what its assets make (0 for labour)."""
    if resource not in NEED_FOR_RESOURCE:
        return 0.0
    rates = next((m.rates for m in agent.modules if hasattr(m, "rates")), {})
    used = rates.get(NEED_FOR_RESOURCE[resource], 0) / rules.relief_per_unit
    return max(0.0, used - agent.output_capacity.get(resource, 0))


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


def stock_floor(rules=DEFAULT_RULES):
    """Below this many units of a resource an agent goes out to restock (0 if the band is off)."""
    return rules.stock_cap * rules.restock_below if rules.selling_enabled else 0


def restock_shortfall(agent, resource, rules=DEFAULT_RULES):
    """Units of a good to buy to get back up to the cap, once its stock has fallen below the floor."""
    if resource == LABOR:
        return 0
    stock = agent.inventory.count(resource)
    return rules.stock_cap - stock if rules.selling_enabled and stock < stock_floor(rules) else 0


def surplus(agent, resource, rules=DEFAULT_RULES, scarcity=None):
    """Units above the stock cap (and above any reserve) that the agent goes out to sell.

    Labour: everything beyond what its own assets will need, so workers always offer work.
    """
    if resource == LABOR:
        return spare(agent, LABOR, rules)
    if not rules.selling_enabled:
        return 0
    keep = max(rules.stock_cap, stockpile_target(agent, resource, rules, scarcity),
               units_to_satisfy(need_level(agent, resource), rules))
    return max(0, agent.inventory.count(resource) - keep)


def wants_to_buy(agent, resource, rules=DEFAULT_RULES, scarcity=None):
    """Needs ``resource`` now, is short of its scarcity reserve, or is below its stock floor."""
    return (demand(agent, resource, rules) > 0 or stockpile_shortfall(agent, resource, rules, scarcity) > 0
            or restock_shortfall(agent, resource, rules) > 0)


def stockpile_shortfall(agent, resource, rules=DEFAULT_RULES, scarcity=None):
    return max(0, stockpile_target(agent, resource, rules, scarcity) - agent.inventory.count(resource))


def wants_anything(agent, rules=DEFAULT_RULES, scarcity=None):
    """Needs something now, is below a stockpile reserve or its stock floor, or needs labour."""
    return (is_needy(agent, rules) or demand(agent, LABOR, rules) > 0
            or any(stockpile_shortfall(agent, r, rules, scarcity) or restock_shortfall(agent, r, rules)
                   for r in RESOURCES))


def spare(agent, resource, rules=DEFAULT_RULES, scarcity=None):
    """Units the agent can give away without hurting its needs, its reserve or its stock floor.

    Labour: anything beyond the labour target of its own assets.
    """
    if resource == LABOR:
        return max(0, agent.inventory.count(LABOR) - labor_target(agent, rules))
    reserve = max(units_to_satisfy(need_level(agent, resource), rules),
                  stockpile_target(agent, resource, rules, scarcity), math.ceil(stock_floor(rules)))
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
    # Labour is only offered to a seller that needs it: anyone else would just watch it expire.
    others = [r for r in RESOURCES if r != buying and r not in needed_by_seller and r != LABOR]
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
    if resource == LABOR:
        return labor_target(buyer, rules)   # refill the buffer; no stocking-up multiplier
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
    wants = sorted(RESOURCES, key=lambda r: need_level(buyer, r), reverse=True)
    for resource in wants:
        need_goal = purchase_goal(buyer, resource, rules, rng)
        restock = rules.stock_cap if restock_shortfall(buyer, resource, rules) else 0
        goal = max(need_goal, stockpile_target(buyer, resource, rules, scarcity), restock)
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


def demand_pressure(buyers, sellers, resource, rules=DEFAULT_RULES):
    """((buyers + 1) / (sellers + 1)) ** price_elasticity[resource].

    The +1s keep it finite when nobody sells, and make 0 buyers vs 0 sellers neutral (x1).
    """
    return ((buyers + 1) / (sellers + 1)) ** rules.price_elasticity[resource]


def concentration(holdings):
    """How concentrated a supply is: 0 = spread evenly over its holders, 1 = one holder has it all.

    Normalised Herfindahl index over the agents: HHI = sum of squared shares, which
    is 1/n when n agents hold equal amounts and 1 for a single holder. Returns 0 when
    there is no supply or only one agent in the world.
    """
    total = sum(holdings)
    n = len(holdings)
    if total <= 0 or n < 2:
        return 0.0
    hhi = sum((h / total) ** 2 for h in holdings)
    return (hhi - 1 / n) / (1 - 1 / n)


def concentration_factor(level, resource, rules=DEFAULT_RULES):
    """1 + concentration_weight[resource] x level: x2 for a monopoly at weight 1."""
    return 1 + rules.concentration_weight[resource] * level


def demand_multiplier_target(buyers, sellers, resource, rules=DEFAULT_RULES, level=0.0):
    """Where the market pushes a resource's price multiplier: demand pressure x
    concentration factor, kept within [price_floor, price_cap]."""
    target = demand_pressure(buyers, sellers, resource, rules) * concentration_factor(level, resource, rules)
    return min(max(target, rules.price_floor), rules.price_cap)


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
