"""Game report: one snapshot per step, and summaries over a window of recent steps.

Each step the World records a snapshot (prices, money, wealth, income, inequality,
what was produced and consumed, labour flows, trades, deaths). ``build_report``
turns the last N snapshots plus the current state into the Report view's data.

Definitions
- wealth of an agent = money + goods it holds at current prices + its asset shares
  at current asset prices (profit-based, so assets that lose money are worth 0).
- income of an agent in a step = money it received, by source: wages (labour sold
  to employers), goods (sales of goods, barter change included), assets (shares
  sold) and government (labour hired by the government).
- Gini = 0 when everyone holds the same, 1 when one agent holds everything. Income
  and consumption inequality use each agent's smoothed per-step income/consumption.
- Asset ownership concentration uses shares owned (not their value, which can be 0).
- job capacity = labour all assets could employ at full capacity; funded jobs = the part
  employers can actually pay for (their spare cash ÷ the wage).
- employment rate = share of agents that worked this step (own assets or hired);
  participation = share that offered labour; unemployment = offered labour nobody
  hired / labour offered; capacity used = labour used on assets / capacity;
  unfilled jobs = jobs employers wanted but couldn't fill / jobs wanted.
- in need = share of agents with a need above the seek threshold; struggling =
  share whose need for a job is above 0.5. Deprivation tiers split it (DEPRIVATION_TIERS):
  survival (thirst, hunger), security (health, shelter, sleep), wellbeing (energy, boredom).
- labour force (ILO-style, people, not units; labour_force): each agent is counted once, by
  its main activity today: employee (hired by a firm), public employee, self-employed (works its
  own business), own-use producer (only autonomous production), unemployed (offered work, got
  none, did nothing else), unable to work (too ill), or not in the labour force (didn't look).
  Unemployment rate = unemployed / (employed + unemployed); participation = (employed +
  unemployed) / population. Own-use production isn't employment (ILO 2013 standard), but it is
  shown, and so is the broad underutilisation rate that counts it with the unemployed.
- real wage: how many days of a typical agent's living costs a day's full work at the market
  wage pays for (wage x average labour capacity / average living cost per day).
"""

# Needs grouped by how serious going without them is (the deprivation tiers).
DEPRIVATION_TIERS = {"survival": ("thirst", "hunger"), "security": ("health", "shelter", "sleep"),
                     "wellbeing": ("energy", "boredom")}


def deprivation(agents, rules):
    """{tier: share of agents with a need of that tier above the seek threshold}, plus
    "in_need_core" (survival or security) and "by_need" (agents per need)."""
    n = len(agents) or 1
    live = [need for need in rules.consumer_needs]
    by_need = {need: sum(1 for a in agents if getattr(a, need) > rules.seek_threshold) for need in live}
    out = {}
    for tier, needs in DEPRIVATION_TIERS.items():
        ns = [x for x in needs if x in live]
        out[f"need_{tier}"] = sum(1 for a in agents if any(getattr(a, x) > rules.seek_threshold for x in ns)) / n
    core = [x for t in ("survival", "security") for x in DEPRIVATION_TIERS[t] if x in live]
    out["in_need_core"] = sum(1 for a in agents if any(getattr(a, x) > rules.seek_threshold for x in core)) / n
    out["need_by"] = by_need
    return out


LF_CLASSES = ("employee", "public", "self_employed", "own_use", "unemployed", "unable", "outside")


def labour_force(world):
    """ILO-style labour statistics (see the module docstring)."""
    from . import penalties
    counts = {c: 0 for c in LF_CLASSES}
    for a in world.agents:
        public = a.employers.get("Government", 0.0) if a.employers else 0.0
        if a.labor_sold - public > 1e-9:
            c = "employee"
        elif public > 1e-9:
            c = "public"
        elif getattr(a, "own_labor", 0.0) > 1e-9:
            c = "self_employed"
        elif a.offered > 1e-9:
            c = "unemployed"
        elif getattr(a, "subsistence_labor", 0.0) > 1e-9:
            c = "own_use"
        elif penalties.labor_factors(a, world.rules).get("health") == 0.0 or a.capacity_now <= 1e-9:
            c = "unable"
        else:
            c = "outside"
        counts[c] += 1
    n = len(world.agents) or 1
    employed = counts["employee"] + counts["public"] + counts["self_employed"]
    force = employed + counts["unemployed"]
    return {"lf": counts,
            "lf_unemployment": counts["unemployed"] / force if force else 0.0,
            "lf_participation": force / n,
            "lf_employment_rate": employed / n,
            "lf_underutilisation": (counts["unemployed"] + counts["own_use"]) / (force + counts["own_use"])
                                   if force + counts["own_use"] else 0.0}


def real_wage(world, prices):
    """(days of living a day's full work buys, average living cost per day)."""
    agents = world.agents
    if not agents:
        return 0.0, 0.0
    cost = sum(economy.living_cost(a, prices, world.rules) for a in agents) / len(agents)
    capacity = sum(a.labor_capacity for a in agents) / len(agents)
    wage = world.labor.wage
    return (wage * capacity / cost if cost > 0 else 0.0), cost

INCOME_SOURCES = ("wages", "goods", "assets", "government", "benefits", "transfers", "banking", "rent")
SMOOTHING = 0.05   # weight of the latest step in agents' smoothed income / consumption

from collections import deque

from . import economy

HISTORY_STEPS = 2000      # snapshots kept
MAX_POINTS = 300          # series are averaged into at most this many points
LORENZ_POINTS = 20


def gini(values):
    values = sorted(max(0.0, v) for v in values)
    n, total = len(values), sum(values)
    if n < 2 or total <= 0:
        return 0.0
    return sum((2 * i - n + 1) * v for i, v in enumerate(values)) / (n * total)


def top_share(values, fraction=0.1):
    """Share of the total held by the top ``fraction`` of agents (at least one agent)."""
    values = sorted(values, reverse=True)
    total = sum(values)
    if not values or total <= 0:
        return 0.0
    k = max(1, round(len(values) * fraction))
    return sum(values[:k]) / total


def lorenz(values):
    """Points (share of agents, share of total held), poorest first, for a Lorenz curve."""
    values = sorted(max(0.0, v) for v in values)
    n, total = len(values), sum(values)
    if not n or total <= 0:
        return [[0, 0], [1, 1]]
    points, running = [[0.0, 0.0]], 0.0
    step = max(1, n // LORENZ_POINTS)
    for i, v in enumerate(values, 1):
        running += v
        if i % step == 0 or i == n:
            points.append([i / n, running / total])
    return points


def ownership_classes(rows, cohort=0.8):
    """(big owners, SMEs) as sets of agents: ranked by asset value (shares if no value), largest
    first, the smallest top group holding ``cohort`` of the total are the owners; the others with
    any assets are SMEs."""
    holders = [r for r in rows if r["shares"] > 1e-9]
    key = "assets" if sum(r["assets"] for r in holders) > 0 else "shares"
    holders.sort(key=lambda r: r[key], reverse=True)
    total = sum(r[key] for r in holders)
    owners, running = set(), 0.0
    for r in holders:
        if running >= cohort * total - 1e-9:
            break
        owners.add(r["agent"])
        running += r[key]
    return owners, {r["agent"] for r in holders} - owners


def bottom_share(values, fraction=0.5):
    """Share of the total held by the bottom ``fraction`` of agents."""
    values = sorted(values)
    total = sum(values)
    if not values or total <= 0:
        return 0.0
    k = max(1, round(len(values) * fraction))
    return sum(values[:k]) / total


def agent_values(world):
    """Per-agent money, goods, asset value, shares and wealth at current prices."""
    prices = world.current_prices()
    asset_prices = world.asset_prices(prices)
    rows = []
    for a in world.agents:
        goods = sum(a.inventory.amount(r) * prices[r] for r in economy.GOODS)
        assets = sum(shares * asset_prices[g] for g, shares in a.assets.items())
        rows.append({"agent": a, "money": a.money, "goods": goods, "assets": assets,
                     "shares": sum(a.assets.values()), "wealth": a.money + goods + assets})
    return rows


def _ownership_counts(rows, cohort):
    big, smes = ownership_classes(rows, cohort)
    return {"owners": len(big), "smes": len(smes), "asset_holders": len(big) + len(smes)}


class NationalAccounts:
    """GDP and price indexes over the last year (a year = 12 x month_steps steps).

    - nominal GDP = goods produced over the last year x today's prices;
    - real GDP = the same goods x the prices of a year ago (before a year has passed: of the
      first step), so it moves only with quantities;
    - GDP deflator = 100 x nominal / real: how much prices of what is produced changed;
    - CPI: a chained monthly index, like statistics offices publish. The first ``warmup`` days
      are price discovery (markets finding their level from the starting prices) and are not
      counted: the index is 100 at the end of them (the base day). Each month's link compares the
      cost of the basket (consumption over the last year) at today's prices with its cost at the
      prices of the start of the month; the links multiply.
    - inflation (the headline): the CPI's change over the last 12 months, or since the base day
      while there is less than a year of index (``cpi_days`` says how long);
    - inflation_annualised: the change over the last 3 months (or since the base day, if at least
      a month) at a yearly rate: (CPI now / CPI then)^(year / days) - 1;
    - inflation_policy: what the central bank and price expectations read: the 12-month rate
      once there is a year of index, before that the annualised rate since the base day (once
      there are 3 months), else None (no reading yet).
    Running sums keep this cheap (no re-adding a year of steps)."""

    def __init__(self):
        self.window = deque()
        self.made = {g: 0.0 for g in economy.GOODS}
        self.used = {g: 0.0 for g in economy.GOODS}
        self.price_log = deque()
        self.steps = 0
        self.level_log = deque()      # chained CPI level on each day since the base day (a year + 1 kept)
        self.link_prices = None       # prices at the start of the current month's link
        self.link_level = 100.0

    def update(self, produced, consumed, prices, year, month=30, warmup=0):
        self.steps += 1
        self.window.append((produced, consumed))
        for g in economy.GOODS:
            self.made[g] += produced[g]
            self.used[g] += consumed[g]
        while len(self.window) > year:
            old_p, old_c = self.window.popleft()
            for g in economy.GOODS:
                self.made[g] -= old_p[g]
                self.used[g] -= old_c[g]
        measured = self.steps > warmup
        if measured:
            self.price_log.append({g: prices[g] for g in economy.GOODS})
            while len(self.price_log) > year + 1:
                self.price_log.popleft()
        then = self.price_log[0] if self.price_log else prices
        nominal = sum(self.made[g] * prices[g] for g in economy.GOODS)
        real = sum(self.made[g] * then[g] for g in economy.GOODS)
        level = 100.0
        if measured:
            if self.link_prices is None:                       # the base day
                self.link_prices, self.link_level = dict(prices), 100.0
            basket_now = sum(self.used[g] * prices[g] for g in economy.GOODS)
            basket_link = sum(self.used[g] * self.link_prices[g] for g in economy.GOODS)
            level = self.link_level * basket_now / basket_link if basket_link > 0 else self.link_level
            self.level_log.append(level)
            while len(self.level_log) > year + 1:
                self.level_log.popleft()
            days = self.steps - warmup
            if days % month == 0:                               # month end: start the next link
                self.link_prices, self.link_level = dict(prices), level
        days = len(self.level_log) - 1 if self.level_log else 0        # days of index since the base
        start = self.level_log[0] if self.level_log else 100.0
        headline = level / start - 1 if self.level_log else 0.0
        back = min(days, 3 * month)
        annualised = ((level / self.level_log[-1 - back]) ** (year / back) - 1
                      if back >= month and self.level_log[-1 - back] > 0 else None)
        if days >= year:
            policy = headline
        elif days >= 3 * month:
            policy = (level / 100.0) ** (year / days) - 1
        else:
            policy = None
        return {"gdp_nominal": nominal, "gdp_real": real,
                "deflator": 100 * nominal / real if real > 0 else 100.0,
                "cpi": level, "inflation": headline, "inflation_annualised": annualised,
                "inflation_policy": policy, "cpi_days": days,
                "accounts_steps": len(self.window)}


class Recorder:
    """Collects per-step flows from the agents and keeps the snapshot history."""

    def __init__(self):
        self.history = deque(maxlen=HISTORY_STEPS)
        self.step_counts = {}
        self.national = NationalAccounts()

    def begin_step(self, world):
        for a in world.agents:
            a.flow = new_flow()
        self.step_counts = {"deaths": 0, "deaths_hunger": 0, "deaths_thirst": 0, "deaths_health": 0, "goods_deals": 0,
                            "asset_trades_before": world.asset_trades}

    def count(self, key, amount=1):
        self.step_counts[key] = self.step_counts.get(key, 0) + amount

    def end_step(self, world, dead_flows):
        flows = [a.flow for a in world.agents] + dead_flows
        for a in world.agents:
            a.income_avg += SMOOTHING * (a.flow["income"] - a.income_avg)
            a.consumption_avg += SMOOTHING * (sum(a.flow["consumed"].values()) - a.consumption_avg)
        rows = agent_values(world)
        prices = world.current_prices()
        sc = self.step_counts
        agents = world.agents
        n = len(agents) or 1
        L = world.labor.stats
        produced = {g: sum(f["produced"].get(g, 0) for f in flows) for g in economy.GOODS}
        sources = {k: sum(f["sources"].get(k, 0.0) for f in flows) for k in INCOME_SOURCES}
        output_value = sum(produced[g] * prices[g] for g in economy.GOODS)
        consumed = {g: sum(f["consumed"].get(g, 0) for f in flows) for g in economy.GOODS}
        accounts = self.national.update(produced, consumed, prices, world.year_steps(), world.rules.month_steps,
                                        world.rules.cpi_warmup_days)
        worked = sum(1 for a in agents if a.labor_sold > 1e-9 or min(a.capacity_now, a.labor_need) > 1e-9)
        offering = sum(1 for a in agents if a.offered > 1e-9)
        self.history.append({
            **accounts,
            "tick": world.tick,
            "population": len(world.agents),
            "deaths": sc["deaths"],
            "prices": prices,
            "money": sum(r["money"] for r in rows),
            "wealth": sum(r["wealth"] for r in rows),
            "asset_value": sum(r["assets"] for r in rows),
            "income": sum(f["income"] for f in flows),
            "gini_money": gini([r["money"] for r in rows]),
            "gini_assets": gini([r["shares"] for r in rows]),
            "gini_wealth": gini([r["wealth"] for r in rows]),
            "gini_income": gini([a.income_avg for a in agents]),
            "gini_consumption": gini([a.consumption_avg for a in agents]),
            "top10_wealth": top_share([r["wealth"] for r in rows]),
            "bottom50_wealth": bottom_share([r["wealth"] for r in rows]),
            **_ownership_counts(rows, world.rules.owner_cohort_share),
            "income_sources": sources,
            "output_value": output_value,
            "labor_share_output": (sources["wages"] / output_value) if output_value else 0.0,
            "employment": worked / n,
            "participation": offering / n,
            "unemployment": (L["idle"] / L["offered"]) if L["offered"] else 0.0,
            "utilisation": (L["own_use"] + L["hired"]) / L["capacity"] if L["capacity"] else 0.0,
            "job_capacity": L["job_capacity"],
            "jobs_funded": L["jobs_funded"],
            "funded_share": (L["jobs_funded"] / L["job_capacity"]) if L["job_capacity"] else 0.0,
            "supply_vs_jobs": (L["capacity"] / L["job_capacity"]) if L["job_capacity"] else 0.0,
            "unfilled_jobs": (max(0.0, L["wanted"] - L["hired"]) / L["wanted"]) if L["wanted"] else 0.0,
            "in_need": sum(1 for a in agents if economy.is_needy(a, world.rules)) / n,
            **deprivation(agents, world.rules),
            **labour_force(world),
            **dict(zip(("real_wage_days", "living_cost_day"), real_wage(world, prices))),
            "labour_breakdown": dict(world.labor.stats.get("breakdown", {})),
            "labour_lost_by": dict(world.labor.stats.get("lost_by", {})),
            "struggling": sum(1 for a in agents if a.job_need > 0.5) / n,
            "deaths_hunger": sc["deaths_hunger"],
            "deaths_thirst": sc["deaths_thirst"],
            "deaths_health": sc["deaths_health"],
            "produced": produced,
            "consumed": {g: sum(f["consumed"].get(g, 0) for f in flows) for g in economy.GOODS},
            "used": {g: sum(f["used"].get(g, 0) for f in flows) for g in economy.GOODS},   # as industry inputs
            "expired": {g: sum(f["expired"].get(g, 0) for f in flows) for g in economy.GOODS},
            # Labour: capacity (after efficiency), used on assets (own + hired), hired by the
            # government, unused (nobody bought it), and the wage.
            "labor_made": world.labor.stats["capacity"],
            "labor_used": world.labor.stats["own_use"] + world.labor.stats["hired"],
            "labor_expired": world.labor.stats["unused"],
            "labor_gov": world.labor.stats["gov_hired"],
            # Autonomous production (subsistence): labour agents put into making their own water or
            # food, the share of agents doing it and its share of all units produced.
            "labor_auto": world.labor.stats.get("subsistence", 0.0),
            "auto_agents": world.labor.stats.get("subsistence_agents", 0) / n,
            "auto_output": (world.labor.stats.get("subsistence_units", 0.0)
                            / max(sum(produced.values()), world.labor.stats.get("subsistence_units", 0.0), 1e-9)),
            "labor_offered": world.labor.stats["offered"],
            "labor_wanted": world.labor.stats["wanted"],
            "wage": world.labor.wage,
            "efficiency": (sum(a.efficiency for a in world.agents) / len(world.agents)) if world.agents else 0.0,
            "wellbeing": (sum(a.wellbeing for a in world.agents) / len(world.agents)) if world.agents else 0.0,
            "job_need": (sum(a.job_need for a in world.agents) / len(world.agents)) if world.agents else 0.0,
            "goods_deals": sc["goods_deals"],
            "labor_deals": world.labor.stats["hires"],
            "asset_trades": world.asset_trades - sc["asset_trades_before"],
            "gov_money": world.government.last_spent,
            "tax_revenue": sum(world.government.step_revenue.values()),
            "taxes": dict(world.government.step_revenue),
            "benefits_paid": world.government.step_spent["benefits"],
            "public_works": world.government.step_spent["public_works"],
            "transfers": world.government.step_spent["transfers"],
            "treasury": world.government.treasury,
        })


def new_flow():
    return {"income": 0.0, "sources": {}, "produced": {}, "consumed": {}, "used": {}, "expired": {}, "labor_made": 0.0,
            "labor_used": 0.0}


def _average(snapshots):
    """Average a bucket of snapshots field by field (nested dicts too); keep the last tick."""
    def mean(values):
        first = values[0]
        if isinstance(first, dict):
            return {k: mean([v.get(k) for v in values if isinstance(v, dict)]) for k in first}
        nums = [v for v in values if isinstance(v, (int, float))]
        return sum(nums) / len(nums) if nums else values[-1]     # (None: no reading yet)
    out = {k: mean([s[k] for s in snapshots]) for k in snapshots[0] if k != "tick"}
    out["tick"] = snapshots[-1]["tick"]
    return out


def build_report(world, window=None):
    history = list(world.recorder.history)
    if window:
        history = history[-window:]
    size = max(1, -(-len(history) // MAX_POINTS))
    series = [_average(history[i:i + size]) for i in range(0, len(history), size)]

    rows = agent_values(world)
    total_wealth = sum(r["wealth"] for r in rows) or 1
    top = sorted(rows, key=lambda r: r["wealth"], reverse=True)[:5]
    steps = len(history) or 1
    first, last = (history[0], history[-1]) if history else ({}, {})
    price_stats = {}
    for r in economy.PRICED:
        values = [s["prices"][r] for s in history] or [0]
        start = first.get("prices", {}).get(r, 0)
        now = world.current_prices()[r]
        price_stats[r] = {"now": now, "min": min(values), "max": max(values), "avg": sum(values) / len(values),
                          "change": (now / start - 1) if start else 0.0}
    totals = {
        "steps": len(history),
        "from_tick": first.get("tick", world.tick),
        "deaths": sum(s["deaths"] for s in history),
        "produced": {g: sum(s["produced"][g] for s in history) for g in economy.GOODS},
        "consumed": {g: sum(s["consumed"][g] for s in history) for g in economy.GOODS},
        "used": {g: sum(s.get("used", {}).get(g, 0) for s in history) for g in economy.GOODS},
        "expired": {g: sum(s.get("expired", {}).get(g, 0) for s in history) for g in economy.GOODS},
        "labor_made": sum(s["labor_made"] for s in history),
        "labor_used": sum(s["labor_used"] for s in history),
        "labor_expired": sum(s["labor_expired"] for s in history),
        "labor_gov": sum(s["labor_gov"] for s in history),
        "labor_auto": sum(s.get("labor_auto", 0.0) for s in history),
        "goods_deals": sum(s["goods_deals"] for s in history),
        "labor_deals": sum(s["labor_deals"] for s in history),
        "asset_trades": sum(s["asset_trades"] for s in history),
        "income": sum(s["income"] for s in history),
        "gov_money": sum(s["gov_money"] for s in history),
        "deaths_hunger": sum(s["deaths_hunger"] for s in history),
        "deaths_thirst": sum(s["deaths_thirst"] for s in history),
        "deaths_health": sum(s.get("deaths_health", 0) for s in history),
        "income_sources": {k: sum(s["income_sources"][k] for s in history) for k in INCOME_SOURCES},
        "output_value": sum(s["output_value"] for s in history),
        "wealth_change": (last.get("wealth", 0) / first["wealth"] - 1) if history and first["wealth"] else 0.0,
        "population_start": first.get("population", len(world.agents)),
    }
    totals["income_per_agent_step"] = totals["income"] / steps / max(1, len(world.agents))
    # Owners vs workers, and wealth by fifths of the population (poorest first).
    def group(members):
        k = len(members) or 1
        return {"count": len(members),
                "wealth": sum(r["wealth"] for r in members) / k,
                "money": sum(r["money"] for r in members) / k,
                "income": sum(r["agent"].income_avg for r in members) / k,
                "wellbeing": sum(r["agent"].wellbeing for r in members) / k,
                "job_need": sum(r["agent"].job_need for r in members) / k,
                "worked": sum(1 for r in members if r["agent"].labor_sold > 1e-9
                              or min(r["agent"].capacity_now, r["agent"].labor_need) > 1e-9) / k,
                "share": sum(r["wealth"] for r in members) / total_wealth}
    big, smes = ownership_classes(rows, world.rules.owner_cohort_share)
    groups = {"owners": group([r for r in rows if r["agent"] in big]),
              "smes": group([r for r in rows if r["agent"] in smes]),
              "workers": group([r for r in rows if r["shares"] <= 1e-9])}
    ordered = sorted(rows, key=lambda r: r["wealth"])
    quintiles = []
    for q in range(5):
        members = ordered[round(len(ordered) * q / 5):round(len(ordered) * (q + 1) / 5)]
        quintiles.append(group(members))

    return {
        "tick": world.tick,
        "start": history[0] if history else None,
        "end": history[-1] if history else None,
        "groups": groups,
        "quintiles": quintiles,
        "series": series,
        "totals": totals,
        "prices": price_stats,
        "current": {
            "population": len(world.agents),
            "money": sum(r["money"] for r in rows),
            "wealth": sum(r["wealth"] for r in rows),
            "asset_value": sum(r["assets"] for r in rows),
            "gini_money": gini([r["money"] for r in rows]),
            "gini_assets": gini([r["shares"] for r in rows]),
            "gini_wealth": gini([r["wealth"] for r in rows]),
            "top10_wealth": top_share([r["wealth"] for r in rows]),
            "bottom50_wealth": bottom_share([r["wealth"] for r in rows]),
            **_ownership_counts(rows, world.rules.owner_cohort_share),
            "goods_value": sum(r["goods"] for r in rows),
        },
        "lorenz": {"money": lorenz([r["money"] for r in rows]), "assets": lorenz([r["shares"] for r in rows]),
                   "wealth": lorenz([r["wealth"] for r in rows]),
                   "income": lorenz([r["agent"].income_avg for r in rows])},
        "top_agents": [{"id": r["agent"].id, "name": r["agent"].name, "color": r["agent"].color,
                        "wealth": r["wealth"], "share": r["wealth"] / total_wealth, "money": r["money"],
                        "assets": r["assets"]} for r in top],
    }
