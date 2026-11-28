"""Debate-panel scenario runner: python scen2.py NAME SEED '{rules}' '[[day, kind, {kwargs}], ...]'
Prints one JSON object with a row every 30 days. kind: epidemic | shortage | disaster."""
import sys, json, time; sys.path.insert(0, "/home/user/simulationTheory")
from simulation import World
from simulation.rules import Rules
name, seed, extra = sys.argv[1], int(sys.argv[2]), json.loads(sys.argv[3])
shocks = json.loads(sys.argv[4]) if len(sys.argv) > 4 else []
w = World(seed=seed, rules=Rules.from_dict({"agents": 200, **extra})); w.spawn_random_agents()
rows, t0 = [], time.time()
for d in range(1, 271):
    for day, kind, kw in shocks:
        if day == d:
            getattr(w.shocks, "trigger_" + kind)(w, **kw)
    w.step()
    if d % 30 == 0:
        h = w.recorder.history[-1]; L = w.labor.stats; g = w.government; p = w.current_prices()
        sh = w.shocks.to_dict()
        rows.append({"day": d, "alive": len(w.agents), "deaths": sum(s["deaths"] for s in w.recorder.history),
            "unemp": round(h["unemployment"], 2), "private_hired": round(L["hired"], 1), "gov_hired": round(L["gov_hired"], 1),
            "offered": round(L["offered"], 1), "wage": round(w.labor.wage), "water": round(p["water"]), "food": round(p["food"]),
            "real_wage_food": round(w.labor.wage / p["food"], 3) if p["food"] else None,
            "infl": round(h["inflation"], 2), "expected_infl": round(w.expected_inflation, 3),
            "policy_rate": round((1 + g.min_rate) ** 360 - 1, 3), "debt": round(g.debt.total),
            "bond_rate": round(g.debt.rate_year(w), 3), "gini": round(h["gini_wealth"], 2), "in_need": round(h["in_need"], 2),
            "approval": round(g.approval, 2), "owners": sum(1 for a in w.agents if a.assets),
            "built": round(sum(getattr(w, "assets_built", {}).values()), 1),
            "firms": w.firms.to_dict(w)["count"] if w.rules.firms_enabled else None,
            "homeless": w.housing.to_dict(w)["homeless"] if w.rules.housing_enabled else None,
            "mortgages": w.banking.to_dict(w)["mortgages"],
            "epidemic_infected": sum(e["total_infected"] for e in sh["epidemics"]),
            "epidemic_deaths": sum(e["total_deaths"] for e in sh["epidemics"])})
print(json.dumps({"scenario": name, "seed": seed, "rules": extra, "shocks": shocks, "rows": rows, "secs": round(time.time() - t0)}))
