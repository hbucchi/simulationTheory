import sys, json, time; sys.path.insert(0, "/home/user/simulationTheory")
from simulation import World, economy
from simulation.rules import Rules
name, extra = sys.argv[1], json.loads(sys.argv[2])
w = World(seed=11, rules=Rules.from_dict({"agents": 200, **extra})); w.spawn_random_agents()
rows, t0 = [], time.time()
for d in range(1, 271):
    w.step()
    if d % 45 == 0:
        h = w.recorder.history[-1]; L = w.labor.stats; g = w.government; p = w.current_prices()
        rows.append({"day": d, "alive": len(w.agents), "deaths": sum(s["deaths"] for s in w.recorder.history),
            "unemp": round(h["unemployment"], 2), "private_hired": round(L["hired"], 1), "gov_hired": round(L["gov_hired"], 1),
            "offered": round(L["offered"], 1), "wage": round(w.labor.wage), "water": round(p["water"]), "food": round(p["food"]),
            "infl": round(h["inflation"], 2), "policy_rate": round((1 + g.min_rate) ** 360 - 1, 3), "debt": round(g.debt.total),
            "bond_rate": round(g.debt.rate_year(w), 3), "gini": round(h["gini_wealth"], 2), "in_need": round(h["in_need"], 2),
            "owners": sum(1 for a in w.agents if a.assets), "built": round(sum(getattr(w, "assets_built", {}).values()), 1),
            "homeless": w.housing.to_dict(w)["homeless"] if w.rules.housing_enabled else None,
            "mortgages": w.banking.to_dict(w)["mortgages"]})
print(json.dumps({"scenario": name, "rules": extra, "rows": rows, "secs": round(time.time() - t0)}))
