"""Game report: one snapshot per step, and summaries over a window of recent steps.

Each step the World records a snapshot (prices, money, wealth, income, inequality,
what was produced and consumed, labour flows, trades, deaths). ``build_report``
turns the last N snapshots plus the current state into the Report view's data.

Definitions
- wealth of an agent = money + inventory at current prices + asset shares at
  current asset prices.
- income of an agent in a step = money it received from selling goods, labour or
  assets (barter change included) and from the government.
- Gini = 0 when everyone holds the same, 1 when one agent holds everything.
"""

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


def agent_values(world):
    """Per-agent money, asset value and wealth at current prices."""
    prices = world.current_prices()
    asset_prices = world.asset_prices(prices)
    rows = []
    for a in world.agents:
        goods = sum(a.inventory.amount(r) * prices[r] for r in economy.RESOURCES)
        assets = sum(shares * asset_prices[g] for g, shares in a.assets.items())
        rows.append({"agent": a, "money": a.money, "assets": assets, "wealth": a.money + goods + assets})
    return rows


class Recorder:
    """Collects per-step flows from the agents and keeps the snapshot history."""

    def __init__(self):
        self.history = deque(maxlen=HISTORY_STEPS)
        self.step_counts = {}

    def begin_step(self, world):
        for a in world.agents:
            a.flow = new_flow()
        self.step_counts = {"deaths": 0, "goods_deals": 0, "labor_deals": 0,
                            "expired": 0.0, "asset_trades_before": world.asset_trades,
                            "gov_labor_before": world.government.labor_bought}

    def count(self, key, amount=1):
        self.step_counts[key] = self.step_counts.get(key, 0) + amount

    def end_step(self, world, dead_flows):
        flows = [a.flow for a in world.agents] + dead_flows
        rows = agent_values(world)
        prices = world.current_prices()
        sc = self.step_counts
        self.history.append({
            "tick": world.tick,
            "population": len(world.agents),
            "deaths": sc["deaths"],
            "prices": prices,
            "money": sum(r["money"] for r in rows),
            "wealth": sum(r["wealth"] for r in rows),
            "asset_value": sum(r["assets"] for r in rows),
            "income": sum(f["income"] for f in flows),
            "gini_money": gini([r["money"] for r in rows]),
            "gini_assets": gini([r["assets"] for r in rows]),
            "gini_wealth": gini([r["wealth"] for r in rows]),
            "top10_wealth": top_share([r["wealth"] for r in rows]),
            "produced": {g: sum(f["produced"].get(g, 0) for f in flows) for g in economy.GOODS},
            "consumed": {g: sum(f["consumed"].get(g, 0) for f in flows) for g in economy.GOODS},
            "labor_made": sum(f["labor_made"] for f in flows),
            "labor_used": sum(f["labor_used"] for f in flows),
            "labor_expired": sc["expired"],
            "labor_gov": world.government.labor_bought - sc["gov_labor_before"],
            "goods_deals": sc["goods_deals"],
            "labor_deals": sc["labor_deals"],
            "asset_trades": world.asset_trades - sc["asset_trades_before"],
            "gov_money": world.government.last_spent,
        })


def new_flow():
    return {"income": 0.0, "produced": {}, "consumed": {}, "labor_made": 0.0, "labor_used": 0.0}


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
    for r in economy.RESOURCES:
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
        "labor_made": sum(s["labor_made"] for s in history),
        "labor_used": sum(s["labor_used"] for s in history),
        "labor_expired": sum(s["labor_expired"] for s in history),
        "labor_gov": sum(s["labor_gov"] for s in history),
        "goods_deals": sum(s["goods_deals"] for s in history),
        "labor_deals": sum(s["labor_deals"] for s in history),
        "asset_trades": sum(s["asset_trades"] for s in history),
        "income": sum(s["income"] for s in history),
        "gov_money": sum(s["gov_money"] for s in history),
        "wealth_change": (last.get("wealth", 0) / first["wealth"] - 1) if history and first["wealth"] else 0.0,
        "population_start": first.get("population", len(world.agents)),
    }
    totals["income_per_agent_step"] = totals["income"] / steps / max(1, len(world.agents))
    return {
        "tick": world.tick,
        "series": series,
        "totals": totals,
        "prices": price_stats,
        "current": {
            "population": len(world.agents),
            "money": sum(r["money"] for r in rows),
            "wealth": sum(r["wealth"] for r in rows),
            "asset_value": sum(r["assets"] for r in rows),
            "gini_money": gini([r["money"] for r in rows]),
            "gini_assets": gini([r["assets"] for r in rows]),
            "gini_wealth": gini([r["wealth"] for r in rows]),
            "top10_wealth": top_share([r["wealth"] for r in rows]),
            "owners": sum(1 for a in world.agents if a.assets),
        },
        "lorenz": {key: lorenz([r[key] for r in rows]) for key in ("money", "assets", "wealth")},
        "top_agents": [{"id": r["agent"].id, "name": r["agent"].name, "color": r["agent"].color,
                        "wealth": r["wealth"], "share": r["wealth"] / total_wealth, "money": r["money"],
                        "assets": r["assets"]} for r in top],
    }
