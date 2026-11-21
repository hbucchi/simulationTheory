"""Public spending policies: where the treasury's money goes, to whom, and how it is shared.

A player designs fiscal spending as a list of policies, each with:

- ``kind``:
    "cash"    income support: money paid to the audience;
    "goods"   give away a resource: the government buys ``good`` from sellers with spare (at the
              market price, paying the production tax like anyone) and hands the units out;
    "service" public service: the government hires idle workers (at their asking wage) and their
              work relieves ``need`` of the audience directly, as much as the labour would make of
              the best good for that need x SERVICE_EFFICIENCY (no capital, no inputs);
- ``audience``: who may receive it (see AUDIENCES);
- ``share``: for "low_income", the poorest share of agents by income (0.2 = bottom 20%);
- ``budget``: money per month (spent evenly, a month's budget / month_steps per day);
  0 = as much as needed (while the treasury lasts);
- ``distribution``: "equal" (everyone in the audience gets the same) or "neediest" (cash: the
  poorest first, raised to a common level; goods and services: the most in need first).

Policies only spend what the treasury holds, in list order: the first is funded first, so a
player who promises more than taxes bring in sees the later policies underfunded. Each policy
records what it spent, to how many agents, and the share of its budget it could pay.
"""
import math

from . import economy

KINDS = {"cash": "Income support", "goods": "Give away a resource", "service": "Public service"}
AUDIENCES = {
    "everyone": "Everyone",
    "low_income": "Low income",                      # the poorest ``share`` by income
    "unemployed": "Unemployed",                      # offered work, nobody hired them
    "in_need": "In need of it",                      # its need above the seek threshold
    "cant_afford": "Can't afford food & water",      # hungry or thirsty and short of money for it
    "no_assets": "No assets",
}
DISTRIBUTIONS = {"equal": "Equal shares", "neediest": "Neediest first"}
# A public service delivers this share of what the same labour makes in its industry: it has
# no capital goods or inputs behind it.
SERVICE_EFFICIENCY = 0.5
# Days of spending kept per policy for "spent in the last month".
MONTH = 30

DEFAULTS = [{"name": "Food and water safety net", "kind": "cash", "audience": "cant_afford",
             "distribution": "neediest", "budget": 0}]


class Policy:
    FIELDS = ("name", "kind", "audience", "share", "good", "need", "budget", "distribution")

    def __init__(self, pid, kind="cash", audience="everyone", budget=0.0, distribution="equal",
                 share=0.2, good=None, need=None, name=None):
        self.id = pid
        self.kind, self.audience, self.budget, self.distribution = kind, audience, budget, distribution
        self.share, self.good, self.need = share, good, need
        self.name = name or ""
        self.spent = 0.0            # all it has spent
        self.daily = []             # money spent on each of the last MONTH days
        self.recipients = 0         # agents it reached yesterday
        self.delivered = 0.0        # units (goods) or relief (service) handed out yesterday
        self.hired = 0.0            # labour units hired yesterday (service)
        self.funded = 1.0           # share of yesterday's budget it could pay

    def update(self, **fields):
        for k, v in fields.items():
            if k in self.FIELDS:
                setattr(self, k, v)

    def label(self, rules):
        if self.name:
            return self.name
        what = {"cash": "Income support", "goods": f"Free {self.good}",
                "service": f"Public {self.need} service"}[self.kind]
        return f"{what} for {AUDIENCES[self.audience].lower()}"

    def to_dict(self, rules=None):
        return {"id": self.id, "name": self.name, "label": self.label(rules), "kind": self.kind,
                "audience": self.audience, "share": self.share, "good": self.good, "need": self.need,
                "budget": self.budget, "distribution": self.distribution,
                "spent": round(self.spent, 2), "spent_month": round(sum(self.daily), 2),
                "recipients": self.recipients, "delivered": round(self.delivered, 3),
                "hired": round(self.hired, 3), "funded": round(self.funded, 3)}


class Policies:
    def __init__(self, specs=()):
        self.items = []
        self.next_id = 1
        for spec in specs:
            self.add(spec)

    def add(self, spec):
        p = Policy(self.next_id, **{k: v for k, v in spec.items() if k in Policy.FIELDS})
        self.next_id += 1
        self.items.append(p)
        return p

    def remove(self, pid):
        self.items = [p for p in self.items if p.id != pid]

    def get(self, pid):
        return next((p for p in self.items if p.id == pid), None)

    def to_dict(self, rules=None):
        return [p.to_dict(rules) for p in self.items]

    # ---------- running them ----------

    def run(self, world, offers=None, remaining=None, stats=None):
        """Pay every policy for today, in order, from the treasury."""
        gov = world.government
        prices = world.current_prices()
        for p in self.items:
            p.recipients, p.delivered, p.hired = 0, 0.0, 0.0
            want = p.budget / world.rules.month_steps if p.budget > 0 else math.inf
            people = audience(world, p, prices, remaining)
            spent = 0.0
            if people and gov.treasury > 1e-6:
                limit = min(want, gov.treasury)
                if p.kind == "cash":
                    spent = _cash(world, p, people, limit, prices)
                elif p.kind == "goods" and p.good in prices:
                    spent = _goods(world, p, people, limit, prices)
                elif p.kind == "service" and p.need and offers is not None:
                    spent = _service(world, p, people, limit, offers, remaining, stats)
            p.spent += spent
            p.daily.append(spent)
            del p.daily[:-MONTH]
            if not people:
                p.funded = 1.0                              # nobody to pay today
            elif want == math.inf:
                p.funded = 1.0 if gov.treasury > 1e-6 else 0.0   # "as needed": did the money run out?
            else:
                p.funded = min(1.0, spent / want)


def _need_of(world, p):
    """The need a policy aims at: its service need, its good's need, or (cash) none."""
    if p.kind == "service":
        return p.need
    if p.kind == "goods":
        return world.rules.need_of(p.good)
    return None


def audience(world, p, prices, remaining=None):
    """Agents a policy may pay (alive, in the audience)."""
    rules = world.rules
    agents = world.agents
    a = p.audience
    if a == "everyone":
        return list(agents)
    if a == "low_income":
        ranked = sorted(agents, key=lambda x: x.income_avg)
        return ranked[:max(1, round(len(ranked) * p.share))] if ranked else []
    if a == "unemployed":
        if remaining is not None:
            return [x for x in agents if remaining.get(x, 0) > 1e-9]
        return [x for x in agents if x.offered - x.labor_sold > 1e-9]
    if a == "in_need":
        need = _need_of(world, p)
        if need:
            return [x for x in agents if getattr(x, need) > rules.seek_threshold]
        return [x for x in agents if economy.is_needy(x, rules)]
    if a == "cant_afford":
        return [x for x in agents if economy.in_danger(x, rules) and _food_gap(x, prices, rules) > 0]
    if a == "no_assets":
        return [x for x in agents if not x.assets]
    return []


def _food_gap(agent, prices, rules):
    return economy.shopping_cost(agent, prices, rules, economy.FATAL_NEEDS) - economy.money_of(agent)


def _pay(world, agent, amount):
    gov = world.government
    gov.treasury -= amount
    gov.spent["transfers"] += amount
    gov.step_spent["transfers"] += amount
    agent.money += amount
    economy.earn(agent, amount, "transfers")


def _cash(world, p, people, limit, prices):
    rules = world.rules
    if p.audience == "cant_afford":
        # Each gets what it is short for food and water, most in danger first.
        people = sorted(people, key=lambda x: max(x.hunger, x.thirst), reverse=True)
        spent = 0.0
        for x in people:
            amount = min(_food_gap(x, prices, rules), limit - spent)
            if amount <= 1e-9:
                break
            _pay(world, x, amount)
            spent += amount
            p.recipients += 1
        return spent
    if limit == math.inf:
        return 0.0          # "as needed" only makes sense for the food and water gap
    if p.distribution == "equal":
        each = limit / len(people)
        for x in people:
            _pay(world, x, each)
        p.recipients = len(people)
        return limit
    # Neediest first: raise the poorest agents' money to a common level (water-filling).
    gifts = water_fill([economy.money_of(x) for x in people], limit)
    for x, g in zip(people, gifts):
        if g > 1e-9:
            _pay(world, x, g)
            p.recipients += 1
    return sum(gifts)


def water_fill(levels, budget):
    """Gifts that raise the lowest ``levels`` to a common level, using ``budget``."""
    order = sorted(range(len(levels)), key=lambda i: levels[i])
    gifts = [0.0] * len(levels)
    left, k = budget, 0
    level = levels[order[0]] if order else 0.0
    while k < len(order) and left > 1e-9:
        k += 1                                    # the k poorest are raised together
        nxt = levels[order[k]] if k < len(order) else math.inf
        rise = min(nxt - level, left / k)
        level += rise
        left -= rise * k
    for i in order[:k]:
        gifts[i] = max(0.0, level - levels[i])
    return gifts


def _goods(world, p, people, limit, prices):
    """Buy units of p.good from sellers with spare and hand them out."""
    rules, gov, good = world.rules, world.government, p.good
    price = prices[good]
    if price <= 0:
        return 0.0
    units = int(limit // price) if limit != math.inf else sum(_goods_wanted(world, p, x) for x in people)
    if units <= 0:
        return 0.0
    sellers = sorted(((o, economy.spare(o, good, rules, world.scarcity)) for o in world.agents),
                     key=lambda t: t[1], reverse=True)
    bought, spent, pool = 0, 0.0, []
    for seller, spare in sellers:
        if spare <= 0 or bought >= units:
            break
        n = min(spare, units - bought)
        cost = n * price
        if good in seller.inventory.perishable:
            pool.extend(seller.inventory.take(good, n))     # keeps its expiry date
        else:
            seller.inventory.remove(good, n)
            pool.append((None, n))
        tax = gov.tax("production", cost)
        gov.treasury -= cost
        gov.collect("production", tax)
        seller.money += cost - tax
        economy.earn(seller, cost - tax, "goods")
        bought += n
        spent += cost
    gov.spent["transfers"] += spent
    gov.step_spent["transfers"] += spent
    if not bought:
        return 0.0
    # Hand the units out: one at a time to whoever is most in need of the good (neediest), or
    # round-robin (equal).
    need = rules.need_of(good)
    relief = rules.relief(good, need) if need else 0.0
    got = {}
    if p.distribution == "neediest" and need:
        pending = {x: getattr(x, need) for x in people}
        for _ in range(bought):
            x = max(pending, key=pending.get)
            got[x] = got.get(x, 0) + 1
            pending[x] -= relief
    else:
        order = sorted(people, key=lambda x: x.id)
        for i in range(bought):
            x = order[i % len(order)]
            got[x] = got.get(x, 0) + 1
    for x, n in sorted(got.items(), key=lambda kv: kv[0].id):
        while n > 1e-9 and pool:
            expires, left = pool[0]
            used = min(n, left)
            x.inventory.add(good, used, expires=expires)
            n -= used
            if left - used <= 1e-9:
                pool.pop(0)
            else:
                pool[0] = (expires, left - used)
    p.recipients = len(got)
    p.delivered = bought
    return spent


def _goods_wanted(world, p, agent):
    """Units of p.good an agent needs now (for an "as needed" give-away)."""
    return economy.demand(agent, p.good, world.rules)


def service_relief_per_labor(world, need):
    """Relief of ``need`` one unit of public labour provides: what that labour would make of the
    best good for the need (productivity x relief per unit) x SERVICE_EFFICIENCY."""
    rules = world.rules
    best = max((world.productivity_now.get(g, 0.0) * rules.relief(g, need) for g in rules.goods_for(need)
                if g in world.productivity_now), default=0.0)
    return best * SERVICE_EFFICIENCY


def _service(world, p, people, limit, offers, remaining, stats):
    """Hire idle labour and turn it into relief of p.need for the audience."""
    gov = world.government
    per_labor = service_relief_per_labor(world, p.need)
    if per_labor <= 0:
        return 0.0
    # Labour wanted: enough to bring everyone's need down to the target level.
    wanted = sum(max(0.0, getattr(x, p.need) - world.rules.target_level) for x in people) / per_labor
    spent, hired = 0.0, 0.0
    for worker in offers:
        if hired >= wanted - 1e-9 or spent >= limit - 1e-9:
            break
        units = min(remaining[worker], wanted - hired)
        if worker.asking_wage > 0:
            units = min(units, (limit - spent) / worker.asking_wage)
        if units <= 1e-9:
            continue
        pay = units * worker.asking_wage
        gov.treasury -= pay
        gov.spent["public_works"] += pay
        gov.step_spent["public_works"] += pay
        tax = gov.tax("wage", pay)
        gov.collect("wage", tax)
        worker.money += pay - tax
        economy.earn(worker, pay - tax, "government")
        worker.labor_sold += units
        worker.employers["Government"] = worker.employers.get("Government", 0) + units
        remaining[worker] -= units
        gov.labor_bought += units
        if stats is not None:
            stats["gov_hired"] += units
        hired += units
        spent += pay
    relief = hired * per_labor
    # Deliver the relief: equal shares, or to the most in need first.
    if p.distribution == "neediest":
        for x in sorted(people, key=lambda x: getattr(x, p.need), reverse=True):
            if relief <= 1e-9:
                break
            give = min(relief, max(0.0, getattr(x, p.need) - world.rules.target_level))
            setattr(x, p.need, getattr(x, p.need) - give)
            relief -= give
            p.recipients += give > 0
    else:
        each = relief / len(people)
        for x in people:
            setattr(x, p.need, max(0.0, getattr(x, p.need) - each))
        p.recipients = len(people)
    p.delivered = hired * per_labor - relief
    p.hired = hired
    return spent


def clean(spec):
    """A validated policy spec (dict) from JSON. Raises ValueError with a readable message."""
    from .rules import GOODS, NEEDS
    if not isinstance(spec, dict):
        raise ValueError("a policy must be an object")
    unknown = set(spec) - set(Policy.FIELDS) - {"id"}
    if unknown:
        raise ValueError(f"unknown policy field(s): {', '.join(sorted(unknown))}")
    out = {}
    kind = spec.get("kind", "cash")
    if kind not in KINDS:
        raise ValueError(f"policy kind must be one of {', '.join(KINDS)}")
    out["kind"] = kind
    for key, table in (("audience", AUDIENCES), ("distribution", DISTRIBUTIONS)):
        value = spec.get(key, next(iter(table)))
        if value not in table:
            raise ValueError(f"policy {key} must be one of {', '.join(table)}")
        out[key] = value
    for key, low, high, default in (("budget", 0, 1e12, 0.0), ("share", 0.01, 1, 0.2)):
        value = spec.get(key, default)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not low <= value <= high:
            raise ValueError(f"policy {key} must be a number from {low:g} to {high:g}")
        out[key] = float(value)
    if kind == "goods":
        if spec.get("good") not in GOODS:
            raise ValueError("a give-away policy needs a resource (good)")
        out["good"] = spec["good"]
    if kind == "service":
        if spec.get("need") not in NEEDS or spec.get("need") == "sleep":
            raise ValueError("a public service needs a need to relieve (" + ", ".join(n for n in NEEDS if n != "sleep") + ")")
        out["need"] = spec["need"]
    name = spec.get("name") or ""
    if not isinstance(name, str) or len(name) > 60:
        raise ValueError("policy name must be text of at most 60 characters")
    out["name"] = name.strip()
    return out
