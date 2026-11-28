"""The default economy after the changes: 3 seeds x 270 days, a row every 30 days."""
import sys, json, multiprocessing as mp
sys.path.insert(0, "/home/user/simulationTheory")
from simulation import World
from simulation.rules import Rules

def run(seed):
    w = World(seed=seed, rules=Rules.from_dict({"agents": 200})); w.spawn_random_agents()
    rows = []
    for d in range(1, 271):
        w.step()
        if d % 30 == 0:
            h = w.recorder.history[-1]; g = w.government; b = w.labor.stats["breakdown"]
            rows.append({"day": d, "deaths": sum(s["deaths"] for s in w.recorder.history),
                         "cpi": round(h["cpi"], 1), "inflation": round(h["inflation"], 3),
                         "inflation_policy": None if h["inflation_policy"] is None else round(h["inflation_policy"], 3),
                         "policy_rate": round((1 + g.min_rate) ** 360 - 1, 4), "in_need_core": round(h["in_need_core"], 2),
                         "need_wellbeing": round(h["need_wellbeing"], 2), "lf_unemployment": round(h["lf_unemployment"], 2),
                         "real_wage_days": round(h["real_wage_days"], 2), "labour_lost": round(b["lost"] / b["full_capacity"], 2),
                         "food": round(w.current_prices()["food"]), "wage": round(w.labor.wage), "treasury": round(g.treasury),
                         "debt": round(g.debt.total), "approval": round(g.approval, 2), "owners": h["owners"], "smes": h["smes"],
                         "built": round(sum(getattr(w, "assets_built", {}).values()), 1)})
    return {"seed": seed, "rows": rows}

if __name__ == "__main__":
    with mp.Pool(3) as p:
        out = p.map(run, [11, 12, 13])
    json.dump(out, open("after_270.json", "w"), indent=1)
    for o in out:
        print("seed", o["seed"])
        for r in o["rows"]:
            print("  ", r)
