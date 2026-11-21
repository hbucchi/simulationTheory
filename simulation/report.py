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
  share whose need for a job is above 0.5.
"""

INCOME_SOURCES = ("wages", "goods", "assets", "government", "benefits", "transfers", "banking")
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


class NationalAccounts:
    """GDP and price indexes over the last year (a year = 12 x month_steps steps).

    - nominal GDP = goods produced over the last year x today's prices;
    - real GDP = the same goods x the prices of a year ago (before a year has passed: of the
      first step), so it moves only with quantities;
    - GDP deflator = 100 x nominal / real: how much prices of what is produced changed;
    - CPI = 100 x (last year's consumption at today's prices) / (at a year-ago prices): how
      much the cost of what people buy changed; inflation = CPI / 100 - 1 (over a year).
    Running sums keep this cheap (no re-adding a year of steps)."""

    def __init__(self):
        self.window = deque()
        self.made = {g: 0.0 for g in economy.GOODS}
        self.used = {g: 0.0 for g in economy.GOODS}
        self.price_log = deque()

    def update(self, produced, consumed, prices, year):
        self.window.append((produced, consumed))
        self.price_log.append({g: prices[g] for g in economy.GOODS})
        for g in economy.GOODS:
            self.made[g] += produced[g]
            self.used[g] += consumed[g]
        while len(self.window) > year:
            old_p, old_c = self.window.popleft()
            for g in economy.GOODS:
                self.made[g] -= old_p[g]
                self.used[g] -= old_c[g]
        while len(self.price_log) > year + 1:
            self.price_log.popleft()
        then = self.price_log[0]
        nominal = sum(self.made[g] * prices[g] for g in economy.GOODS)
        real = sum(self.made[g] * then[g] for g in economy.GOODS)
        basket_now = sum(self.used[g] * prices[g] for g in economy.GOODS)
        basket_then = sum(self.used[g] * then[g] for g in economy.GOODS)
        cpi = 100 * basket_now / basket_then if basket_then > 0 else 100.0
        return {"gdp_nominal": nominal, "gdp_real": real,
                "deflator": 100 * nominal / real if real > 0 else 100.0,
                "cpi": cpi, "inflation": cpi / 100 - 1,
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
        self.step_counts = {"deaths": 0, "deaths_hunger": 0, "deaths_thirst": 0, "goods_deals": 0,
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
        accounts = self.national.update(produced, consumed, prices, world.year_steps())
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
            "owners": sum(1 for r in rows if r["shares"] > 1e-9),
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
            "struggling": sum(1 for a in agents if a.job_need > 0.5) / n,
            "deaths_hunger": sc["deaths_hunger"],
            "deaths_thirst": sc["deaths_thirst"],
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
            return {k: mean([v[k] for v in values]) for k in first}
        return sum(values) / len(values)
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
        "goods_deals": sum(s["goods_deals"] for s in history),
        "labor_deals": sum(s["labor_deals"] for s in history),
        "asset_trades": sum(s["asset_trades"] for s in history),
        "income": sum(s["income"] for s in history),
        "gov_money": sum(s["gov_money"] for s in history),
        "deaths_hunger": sum(s["deaths_hunger"] for s in history),
        "deaths_thirst": sum(s["deaths_thirst"] for s in history),
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
    groups = {"owners": group([r for r in rows if r["shares"] > 1e-9]),
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
            "owners": sum(1 for r in rows if r["shares"] > 1e-9),
            "goods_value": sum(r["goods"] for r in rows),
        },
        "lorenz": {"money": lorenz([r["money"] for r in rows]), "assets": lorenz([r["shares"] for r in rows]),
                   "wealth": lorenz([r["wealth"] for r in rows]),
                   "income": lorenz([r["agent"].income_avg for r in rows])},
        "top_agents": [{"id": r["agent"].id, "name": r["agent"].name, "color": r["agent"].color,
                        "wealth": r["wealth"], "share": r["wealth"] / total_wealth, "money": r["money"],
                        "assets": r["assets"]} for r in top],
    }
