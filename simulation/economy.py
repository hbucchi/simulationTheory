"""Rules of the economy: what resources exist, what they satisfy, and how trading works.

Need scale reminder: 0.00 = satisfied, 1.00 = desperate.
"""

import math

from .rules import DEFAULT_RULES, GOODS, LABOR, PRICED, RESOURCES
from .catalog import OWN_USE_GOODS

# Which need a good relieves, and how much one unit relieves, come from the game's Rules
# (rules.need_of / rules.relief / rules.goods_for): several goods can relieve the same need,
# and goods from deeper industry layers relieve more per unit. Sleep is recovered by resting
# (modules/rest.py). Labour relieves no need: it is bought by asset owners to make goods.

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
    # Money people can spend: cash plus bank deposits.
    money = sum(a.money + sum(a.deposits.values()) + a.company_cash for a in agents)
    units = dict.fromkeys(RESOURCES, 0)
    for a in agents:   # whole units, as Inventory.count would give, without a call per good
        for r, n in a.inventory.items.items():
            if r in units:
                units[r] += n
        for r, n in a.inventory.totals.items():
            units[r] += int(n + 1e-9)
    total = sum(units.values())
    if total == 0:
        return {r: 0.0 for r in RESOURCES}
    return {r: money / total * (1 - units[r] / total) for r in RESOURCES}


def units_to_satisfy(level, rules=DEFAULT_RULES, per_unit=None):
    """Units (each relieving ``per_unit``, by default relief_per_unit) needed to bring a need
    strictly below the target level (0 if already below)."""
    per_unit = rules.relief_per_unit if per_unit is None else per_unit
    if level < rules.target_level or per_unit <= 0:
        return 0
    # round() guards against float noise such as 0.6 - 0.3 = 0.29999999999999993
    return math.floor(round((level - rules.target_level) / per_unit, 9)) + 1


def transfer(giver, receiver, resource, qty=1):
    """Move ``qty`` units. Perishable units keep their expiry date, oldest given first."""
    if resource in giver.inventory.perishable:
        for expires, units in giver.inventory.take(resource, qty):
            receiver.inventory.add(resource, units, expires=expires)
        return
    giver.inventory.remove(resource, qty)
    receiver.inventory.add(resource, qty)


def earn(agent, amount, source):
    """Record income for the report: source is "wages", "goods", "assets" or "government"."""
    agent.flow["income"] += amount
    agent.flow["sources"][source] = agent.flow["sources"].get(source, 0.0) + amount


def money_of(agent):
    """Money the agent can use: cash plus bank deposits."""
    return agent.money + sum(agent.deposits.values()) if agent.deposits else agent.money


def draw_company_cash(agent, amount):
    """Move up to ``amount`` of the agent's company cash (retained earnings) into its cash, to pay
    company costs (wages, building). Returns what was moved."""
    moved = min(max(0.0, amount), agent.company_cash)
    agent.company_cash -= moved
    agent.money += moved
    return moved


def pay(payer, payee, amount):
    """Pay for goods; whoever receives money (the payee, or the payer when it gets change)
    earns income from selling goods."""
    payer.money -= amount
    payee.money += amount
    earn(payee if amount > 0 else payer, abs(amount), "goods")


def held_relief(agent, need, rules=DEFAULT_RULES):
    """How much of ``need`` the agent's stock could relieve: units x relief over every good for it.
    Cached until the agent's inventory changes (or the rules do)."""
    inv = agent.inventory
    cache = agent.__dict__.setdefault("_held_cache", {})
    key = (need, inv.version, id(rules))
    if key not in cache:
        if len(cache) > 64:
            cache.clear()
        cache[key] = sum(inv.count(g) * rules.relief(g, need) for g in rules.goods_for(need))
    return cache[key]


def benefit(agent, good, rules=DEFAULT_RULES, target=None):
    """How good one unit of ``good`` is for this agent right now: its relief for ``target`` (the
    need being served) plus every side effect weighted by how pressing that need is (its level).
    Fast food is great for a hungry agent with good health and poor for one who is already ill."""
    return sum(change * (1.0 if need == target else getattr(agent, need))
               for need, change in rules.effects_of(good).items())


def apply_effects(agent, good, units, rules=DEFAULT_RULES):
    """Consuming ``units`` of ``good`` changes every need it affects (relieves or worsens)."""
    for need, change in rules.effects_of(good).items():
        setattr(agent, need, getattr(agent, need) - units * change)


def consume(agent, rules=DEFAULT_RULES):
    """Consume from own stock for every need above the seek threshold (most pressing first), the
    goods that do the agent most good first (relief for that need, deeper layers relieve more,
    plus side effects on its other needs; goods that would do more harm than good are skipped),
    until the need is below the target. Each unit also has its side effects.

    Returns {resource: units consumed}.
    """
    eaten = {}
    for need in sorted(rules.consumer_needs, key=lambda n: getattr(agent, n), reverse=True):
        if getattr(agent, need) <= rules.seek_threshold:
            continue
        held = [g for g in rules.goods_for(need) if agent.inventory.count(g)]
        held.sort(key=lambda g: benefit(agent, g, rules, need), reverse=True)
        for good in held:
            level = getattr(agent, need)
            if level < rules.target_level:
                break
            if benefit(agent, good, rules, need) <= 0:
                break
            units = min(units_to_satisfy(level, rules, rules.relief(good, need)), agent.inventory.count(good))
            if units:
                agent.inventory.remove(good, units)
                apply_effects(agent, good, units, rules)
                agent.flow["consumed"][good] = agent.flow["consumed"].get(good, 0) + units
                eaten[good] = eaten.get(good, 0) + units
    return eaten


def is_needy(agent, rules=DEFAULT_RULES):
    """True when a need some good can relieve is above the threshold (stock already used up)."""
    return any(getattr(agent, need) > rules.seek_threshold for need in rules.consumer_needs)


# Needs that kill at 1.00 (with death on). They count FATAL_WEIGHT times as urgent as the
# others, so a thirsty agent drinks before it goes looking for games however bored it is.
FATAL_NEEDS = ("hunger", "thirst")
FATAL_WEIGHT = 2.0
# A fatal need above this is close to killing: the agent drops everything else to meet it.
DESPERATE_LEVEL = 0.85


def urgency(agent, need, rules=DEFAULT_RULES):
    """How urgent ``need`` is for ``agent``: its level, x FATAL_WEIGHT for needs that kill."""
    level = getattr(agent, need)
    return level * FATAL_WEIGHT if rules.death_enabled and need in FATAL_NEEDS else level


def in_danger(agent, rules=DEFAULT_RULES):
    """True when a need that kills is above the seek threshold (its stock already used up)."""
    return rules.death_enabled and any(getattr(agent, n) > rules.seek_threshold for n in FATAL_NEEDS
                                       if n in rules.consumer_needs)


def is_desperate(agent, rules=DEFAULT_RULES):
    """True when a need that kills is above DESPERATE_LEVEL."""
    return rules.death_enabled and any(getattr(agent, n) > DESPERATE_LEVEL for n in FATAL_NEEDS
                                       if n in rules.consumer_needs)


def need_level(agent, resource, rules=DEFAULT_RULES):
    """How strong the need behind ``resource`` is (0 for goods that relieve none, and labour)."""
    need = rules.need_of(resource)
    return getattr(agent, need) if need else 0.0


def need_urgency(agent, resource, rules=DEFAULT_RULES):
    """urgency() of the need behind ``resource`` (0 for goods that relieve none, and labour)."""
    need = rules.need_of(resource)
    return urgency(agent, need, rules) if need else 0.0


def demand(agent, resource, rules=DEFAULT_RULES):
    """Units of ``resource`` the agent would need to buy to bring a need it relieves below the
    target (the neediest such need), after what its stock of every good for that need can relieve.
    0 when none of those needs is above the seek threshold, and for goods that relieve no need."""
    units = 0
    for need, change in rules.effects_of(resource).items():
        if change <= 0:
            continue
        level = getattr(agent, need)
        if level > rules.seek_threshold:
            units = max(units, units_to_satisfy(level - held_relief(agent, need, rules), rules, change))
    return units


def net_use(agent, resource, rules=DEFAULT_RULES, need=None):
    """Units of a good the agent would use per step if it relied on this good alone for ``need``
    (default: its main need), beyond what its assets make (0 for goods relieving no need)."""
    need = need or rules.need_of(resource)
    per_unit = rules.relief(resource, need) if need else 0
    if per_unit <= 0:
        return 0.0
    used = _rates(agent).get(need, 0) / per_unit
    return max(0.0, used - agent.output_capacity.get(resource, 0))


def need_cost(agent, need, prices, rules=DEFAULT_RULES):
    """Cheapest money per step to keep ``need`` from growing, choosing the good with the lowest
    price per unit of relief (net of what the agent's own assets make)."""
    costs = [net_use(agent, g, rules, need) * prices[g] for g in rules.goods_for(need) if g in prices]
    return min(costs, default=0.0)


def living_cost(agent, prices, rules=DEFAULT_RULES):
    """Money per step it costs the agent to live: for every need, the cheapest way to buy what
    keeps it from growing (food, water, housing, ...), net of what its own assets make.
    Cached for the same prices (once per step)."""
    cached = agent.__dict__.get("_living")
    if cached and cached[0] is prices and cached[1] is agent.output_capacity:
        return cached[2]
    value = sum(need_cost(agent, need, prices, rules) for need in rules.consumer_needs)
    agent._living = (prices, agent.output_capacity, value)
    return value


def shopping_cost(agent, prices, rules=DEFAULT_RULES, needs=None):
    """Money to buy what it needs right now, the cheapest way for each need (only ``needs``,
    if given)."""
    total = 0.0
    for need in rules.consumer_needs:
        if needs is not None and need not in needs:
            continue
        if getattr(agent, need) <= rules.seek_threshold:
            continue
        costs = [n * prices[g] for g in rules.goods_for(need) if (n := demand(agent, g, rules))]
        total += min(costs, default=0.0)
    return total


_liquidity_memo = {}   # id(prices) -> (prices, rules, value): the same for every agent at given prices


def liquidity_cost(prices, rules=DEFAULT_RULES):
    """Price of rules.liquidity_units baseline units of relief (relief_per_unit each) for every
    need, bought the cheapest way: the cash an agent keeps on hand."""
    hit = _liquidity_memo.get(id(prices))
    if hit and hit[0] is prices and hit[1] is rules:
        return hit[2]
    total = 0.0
    for need in rules.consumer_needs:
        per_relief = [prices[g] / rules.relief(g, need) for g in rules.goods_for(need) if g in prices]
        total += min(per_relief, default=0.0) * rules.relief_per_unit
    if len(_liquidity_memo) > 8:
        _liquidity_memo.clear()
    # Keeping prices in the entry keeps its id from being reused by another dict.
    _liquidity_memo[id(prices)] = (prices, rules, rules.liquidity_units * total)
    return _liquidity_memo[id(prices)][2]


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


def need_rate(agent, need):
    """How fast the agent's ``need`` grows per step."""
    return _rates(agent).get(need, 0.0)


def _rates(agent):
    """The agent's need growth rates (its NeedsDecay module's table, found once)."""
    rates = agent.__dict__.get("_rates")
    if rates is None:
        rates = next((m.rates for m in agent.modules if hasattr(m, "rates")), {})
        agent._rates = rates
    return rates


def band_relief(agent, need, rules=DEFAULT_RULES, fraction=1.0):
    """The stock band for one need, in relief: enough to cover stock_steps steps of the agent's own
    growth of that need; fraction=restock_below gives the floor. 0 if the band is off."""
    if not rules.selling_enabled:
        return 0.0
    return need_rate(agent, need) * rules.stock_steps * fraction


def _kept_for_need(agent, resource, relief_wanted, rules):
    """Units of ``resource`` the agent keeps so its stock relieves ``relief_wanted`` of the good's
    need, filling it with the most effective goods first."""
    need = rules.need_of(resource)
    left = relief_wanted
    for g in rules.goods_for(need):
        if left <= 1e-9:
            return 0
        per_unit = rules.relief(g, need)
        kept = min(agent.inventory.count(g), math.ceil(round(left / per_unit, 9)))
        if g == resource:
            return kept
        left -= kept * per_unit
    return 0


def _need_gap(agent, resource, rules):
    """Relief the agent still wants for its need right now (to get strictly below the target)."""
    level = need_level(agent, resource, rules)
    return level - rules.target_level + 1e-6 if level >= rules.target_level else 0.0


def input_target(agent, resource, rules=DEFAULT_RULES):
    """Units of ``resource`` the agent keeps as industry input: input_buffer_steps steps of what its
    secondary industries use at full capacity (agent.output_capacity). 0 if it uses none."""
    # Worked out for all inputs at once and cached until output_capacity (set each step) changes.
    capacity = agent.output_capacity
    cached = agent.__dict__.get("_input_targets")
    if cached is None or cached[0] is not capacity or cached[1] is not rules:
        use = {}
        for g, cap in capacity.items():
            for item, per_unit in rules.inputs.get(g, {}).items():
                use[item] = use.get(item, 0) + cap * per_unit
        targets = {item: math.ceil(round(u * rules.input_buffer_steps, 9)) for item, u in use.items() if u > 0}
        cached = (capacity, rules, targets)
        agent._input_targets = cached
    return cached[2].get(resource, 0)


def project_need(agent, resource):
    """Units of ``resource`` the agent's building project needs in total (0 without a project)."""
    return agent.project["need"].get(resource, 0) if agent.project else 0


def project_shortfall(agent, resource):
    """Units of ``resource`` still to buy for the agent's building project."""
    return max(0, project_need(agent, resource) - agent.inventory.count(resource))


def input_shortfall(agent, resource, rules=DEFAULT_RULES):
    """Units to buy to refill the input buffer, once stock fell below input_reorder of it."""
    target = input_target(agent, resource, rules)
    stock = agent.inventory.count(resource)
    return target - stock if target and stock < target * rules.input_reorder else 0


# A perishable good is only stocked up to what its owner would use in this share of its shelf life.
USE_BEFORE_EXPIRY = 0.8


def useful_stock(agent, resource, rules=DEFAULT_RULES):
    """Most units of a perishable good worth holding for the agent's own needs: what it would
    consume within USE_BEFORE_EXPIRY of the shelf life (relying on this good alone). None when
    the good doesn't expire (no limit)."""
    life = rules.shelf_life.get(resource, 0) if rules.expiry_enabled else 0
    need = rules.need_of(resource)
    if not life or not need:
        return None
    return math.ceil(need_rate(agent, need) / rules.relief(resource) * life * USE_BEFORE_EXPIRY)


def restock_shortfall(agent, resource, rules=DEFAULT_RULES):
    """Units of ``resource`` to buy to bring the agent's relief for its need back up to the cap,
    once its stock for that need fell below the floor. A perishable good is bought only up to
    useful_stock (no point hoarding what would expire). 0 for goods that relieve no need: those
    are bought as industry inputs (input_shortfall)."""
    need = rules.need_of(resource)
    if not need or not rules.selling_enabled:
        return 0
    held = held_relief(agent, need, rules)
    if held >= band_relief(agent, need, rules, rules.restock_below):
        return 0
    units = math.ceil(round((band_relief(agent, need, rules) - held) / rules.relief(resource), 9))
    limit = useful_stock(agent, resource, rules)
    if limit is not None:
        units = min(units, limit - agent.inventory.count(resource))
    return max(0, units)


def surplus(agent, resource, rules=DEFAULT_RULES, scarcity=None):
    """Units above what the agent keeps (its share of the stock cap for the good's need, any
    reserve, its own input buffer) that it goes out to sell."""
    if not rules.selling_enabled or resource in OWN_USE_GOODS:
        return 0
    keep = 0
    need = rules.need_of(resource)
    if need:
        keep = _kept_for_need(agent, resource, band_relief(agent, need, rules) + _need_gap(agent, resource, rules), rules)
    keep = max(keep, stockpile_target(agent, resource, rules, scarcity)) + input_target(agent, resource, rules)
    keep += project_need(agent, resource)
    return max(0, agent.inventory.count(resource) - keep)


def wants_to_buy(agent, resource, rules=DEFAULT_RULES, scarcity=None):
    """Needs ``resource`` now, is short of its scarcity reserve, below its stock floor, or short of inputs."""
    return (demand(agent, resource, rules) > 0 or stockpile_shortfall(agent, resource, rules, scarcity) > 0
            or restock_shortfall(agent, resource, rules) > 0 or input_shortfall(agent, resource, rules) > 0
            or project_shortfall(agent, resource) > 0)


def wanted_goods(agent, rules=DEFAULT_RULES, scarcity=None):
    """Every active good wants_to_buy() is true for, worked out need by need instead of good by
    good (the same answer, much faster for big catalogs: used once per step per agent)."""
    wanted = set()
    seek, target = rules.seek_threshold, rules.target_level
    restock = rules.selling_enabled
    for need in rules.consumer_needs:
        level = getattr(agent, need)
        held = None
        if level > seek:
            held = held_relief(agent, need, rules)
            if level - held >= target:                 # demand() > 0 for every good relieving it
                wanted.update(rules.goods_for(need))
        if restock:
            if held is None:
                held = held_relief(agent, need, rules)
            if held < band_relief(agent, need, rules, rules.restock_below):
                for g in rules.main_goods_for(need):
                    if g not in wanted and restock_shortfall(agent, g, rules) > 0:
                        wanted.add(g)
    if scarcity and rules.stockpiling_enabled:
        for g, decline in scarcity.items():
            if decline >= rules.scarcity_trigger and g not in wanted and rules.is_active(g) \
                    and stockpile_shortfall(agent, g, rules, scarcity) > 0:
                wanted.add(g)
    if agent.output_capacity:
        input_target(agent, "", rules)                 # fills the cached table of targets
        for g in agent._input_targets[2]:
            if g not in wanted and rules.is_active(g) and input_shortfall(agent, g, rules) > 0:
                wanted.add(g)
    if agent.project:
        for g in agent.project["need"]:
            if g not in wanted and rules.is_active(g) and project_shortfall(agent, g) > 0:
                wanted.add(g)
    return wanted


def stockpile_shortfall(agent, resource, rules=DEFAULT_RULES, scarcity=None):
    return max(0, stockpile_target(agent, resource, rules, scarcity) - agent.inventory.count(resource))


def wants_anything(agent, rules=DEFAULT_RULES, scarcity=None):
    """Needs something now, or is below a stockpile reserve, its stock floor or an input buffer."""
    return (is_needy(agent, rules)
            or any(stockpile_shortfall(agent, r, rules, scarcity) or restock_shortfall(agent, r, rules)
                   or input_shortfall(agent, r, rules) or project_shortfall(agent, r) for r in rules.active_goods))


def spare(agent, resource, rules=DEFAULT_RULES, scarcity=None):
    """Units the agent can give away without hurting its needs, its reserve, its stock floor
    (in relief for the good's need) or the input buffer of its own industries. Services made
    for the owner's own use (banking) are never given away."""
    if resource in OWN_USE_GOODS:
        return 0
    keep = 0
    need = rules.need_of(resource)
    if need:
        wanted = max(band_relief(agent, need, rules, rules.restock_below), _need_gap(agent, resource, rules))
        keep = _kept_for_need(agent, resource, wanted, rules)
    keep = max(keep, stockpile_target(agent, resource, rules, scarcity)) + input_target(agent, resource, rules)
    keep += project_need(agent, resource)
    return max(0, agent.inventory.count(resource) - keep)


def spare_and_surplus(agent, resource, rules=DEFAULT_RULES, scarcity=None):
    """(spare(...), surplus(...)) in one go, sharing the work they have in common."""
    count = agent.inventory.count(resource)
    if not count or resource in OWN_USE_GOODS:
        return 0, 0
    extra = input_target(agent, resource, rules) + project_need(agent, resource)
    reserve = stockpile_target(agent, resource, rules, scarcity)
    need = rules.need_of(resource)
    gap = _need_gap(agent, resource, rules) if need else 0.0
    keep = _kept_for_need(agent, resource, max(band_relief(agent, need, rules, rules.restock_below), gap),
                          rules) if need else 0
    spare_units = max(0, count - (max(keep, reserve) + extra))
    if not spare_units or not rules.selling_enabled:
        return spare_units, 0
    keep = _kept_for_need(agent, resource, band_relief(agent, need, rules) + gap, rules) if need else 0
    return spare_units, max(0, count - (max(keep, reserve) + extra))


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
    needed_by_seller = [r for r in rules.active_goods if r != buying
                        and (demand(seller, r, rules) > 0 or input_shortfall(seller, r, rules) > 0)]
    others = [r for r in rules.active_goods if r != buying and r not in needed_by_seller]
    for option in needed_by_seller + ["money"] + others:
        if option == "money":
            if buyer.money >= price:
                return None, price
            continue
        if option not in prices or spare(buyer, option, rules, scarcity) == 0:
            continue
        diff = price - prices[option]   # > 0: buyer tops up; < 0: seller gives change
        payer = buyer if diff > 0 else seller
        if payer.money >= abs(diff):
            return option, diff
    return None


def purchase_goal(buyer, resource, rules, rng=None):
    """How many units the buyer wants to hold after buying ``resource``.

    It needs demand(...) more units of this good; it buys that times a random multiplier in
    [purchase_min, purchase_max] (rounded up), so it stocks up for later. With no
    rng the multiplier is purchase_min. Returns 0 if it doesn't need the resource.
    """
    needed = demand(buyer, resource, rules)
    if not needed:
        return 0
    multiplier = rng.uniform(rules.purchase_min, rules.purchase_max) if rng else rules.purchase_min
    return buyer.inventory.count(resource) + math.ceil(round(needed * multiplier, 9))


def buy(buyer, seller, prices, rules=DEFAULT_RULES, rng=None, scarcity=None, markups=None):
    """Buyer acquires what it needs (times a random multiplier) from seller at market prices,
    plus any stockpile reserve it is missing.

    It stops when it reaches its goal, the seller has no spare left, or it
    can't pay. Units bought only for the reserve are paid in money, up to
    stockpile_budget of the money the buyer had at the start (none while it is hungry or
    thirsty: see in_danger). ``markups``
    ({resource: rate}) makes each extra unit of a resource in this deal cost
    that much more than the previous one (price x (1 + rate) ** k).
    Returns (bought, paid, stocked, unit_prices): bought = {resource: units};
    paid = {resource: units, "money": net money buyer -> seller (negative =
    change)}; stocked = {resource: units of bought that went to the reserve};
    unit_prices = {resource: [first unit price, last unit price]}.
    """
    bought, paid, stocked, unit_prices = {}, {}, {}, {}
    budget = buyer.money * rules.stockpile_budget
    # Hungry or thirsty: every dollar goes on what it needs now, nothing on reserves.
    no_reserves = in_danger(buyer, rules)
    spent_on_reserve = 0.0
    # Most pressing need first (hunger and thirst count double, see urgency); for each need the
    # good that does the buyer most good per dollar
    # first (relief plus side effects, see benefit). Goods relieving no need (inputs) come last.
    def order(r):
        helped = [n for n, change in rules.effects_of(r).items() if change > 0]
        if not helped:
            return (0.0, math.inf)
        target = max(helped, key=lambda n: urgency(buyer, n, rules))
        good = benefit(buyer, r, rules, target)
        value = -good / prices[r] if prices.get(r, 0) > 0 else -good * 1e9
        return (-urgency(buyer, target, rules), value)
    # Only goods it wants can have a goal above its stock (see wanted_goods). Paying with a good
    # (barter) can make it wanted mid-deal, so goods it holds stay in the running.
    wanted = wanted_goods(buyer, rules, scarcity)
    given_away = set()
    wants = sorted((r for r in rules.active_goods if r in prices and (r in wanted or buyer.inventory.count(r))),
                   key=order)
    for resource in wants:
        if resource not in wanted and resource not in given_away:
            continue
        need_goal = purchase_goal(buyer, resource, rules, rng)
        shortfall = restock_shortfall(buyer, resource, rules)
        restock = buyer.inventory.count(resource) + shortfall if shortfall else 0
        inputs = input_target(buyer, resource, rules) if input_shortfall(buyer, resource, rules) else 0
        goal = max(need_goal, stockpile_target(buyer, resource, rules, scarcity), restock, inputs,
                   project_need(buyer, resource))
        markup = (markups or {}).get(resource, 0)
        while buyer.inventory.count(resource) < goal and spare(seller, resource, rules, scarcity) > 0:
            unit_price = prices[resource] * (1 + markup) ** bought.get(resource, 0)
            for_reserve = buyer.inventory.count(resource) >= need_goal
            if for_reserve and (no_reserves or spent_on_reserve + unit_price > budget):
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
                given_away.add(given)
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
    for need in rules.consumer_needs:
        goods = [g for g in rules.goods_for(need) if demand(buyer, g, rules)]
        if not goods:
            continue
        best = goods[0]
        what = f"{demand(buyer, best, rules)} {best}" + (f" (or other {need} goods)" if len(goods) > 1 else "")
        held = [g for g in goods if seller.inventory.count(g)]
        if not held:
            why = f"{seller.name} has none"
        elif all(spare(seller, g, rules, scarcity) == 0 for g in held):
            why = f"{seller.name} keeps its {', '.join(f'{seller.inventory.count(g)} {g}' for g in held[:3])} for itself"
        else:
            why = "nothing left to pay with"
        reasons.append(f"{buyer.name} still needs {what}: {why}")
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


def buyer_power_factor(level, resource, rules=DEFAULT_RULES):
    """1 / (1 + buyer_power_weight x buyer concentration): x0.5 when one buyer holds all the
    buying power at weight 1 (monopsony), x1 when buying power is spread evenly."""
    return 1 / (1 + rules.buyer_power_weight.get(resource, 0.0) * level)


def demand_multiplier_target(buyers, sellers, resource, rules=DEFAULT_RULES, level=0.0, buyer_level=0.0):
    """Where the market pushes a resource's price multiplier: demand pressure x seller
    concentration factor x buying power factor, kept within [price_floor, price_cap]."""
    target = (demand_pressure(buyers, sellers, resource, rules) * concentration_factor(level, resource, rules)
              * buyer_power_factor(buyer_level, resource, rules))
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
