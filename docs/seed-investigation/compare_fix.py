"""Seed spread before and after the balanced ownership rule (industry_owners), on the same code.
Usage: python compare_fix.py DAYS OUT.json"""
import sys, json, statistics, multiprocessing as mp
sys.path.insert(0, "/home/user/simulationTheory")
from simulation import World
from simulation.rules import Rules
DAYS, OUT = int(sys.argv[1]), sys.argv[2]
SEEDS = list(range(11, 19))
KEYS = ("in_need", "in_need_core", "food", "cpi", "built", "hired", "gini", "real_wage_days")

def run(job):
    owners, seed = job
    w = World(seed=seed, rules=Rules.from_dict({"agents": 200, "industry_owners": owners}))
    w.spawn_random_agents()
    for _ in range(DAYS):
        w.step()
    h = w.recorder.history[-1]; p = w.current_prices()
    return owners, seed, {"in_need": h["in_need"], "in_need_core": h["in_need_core"], "food": p["food"],
                          "cpi": h["cpi"], "built": sum(getattr(w, "assets_built", {}).values()),
                          "hired": w.labor.stats["hired"], "gini": h["gini_wealth"],
                          "real_wage_days": h["real_wage_days"]}

if __name__ == "__main__":
    jobs = [(o, s) for o in (0, 3) for s in SEEDS]
    with mp.Pool(4) as pool:
        res = pool.map(run, jobs)
    out = {"days": DAYS, "seeds": SEEDS, "runs": [{"industry_owners": o, "seed": s, **m} for o, s, m in res]}
    print("rule".ljust(22) + "".join(k.rjust(14) for k in KEYS))
    for o in (0, 3):
        vals = [m for oo, s, m in res if oo == o]
        mean = {k: statistics.mean(v[k] for v in vals) for k in KEYS}
        sd = {k: statistics.pstdev([v[k] for v in vals]) for k in KEYS}
        out[f"owners_{o}"] = {"mean": mean, "sd": sd}
        name = "lottery (0)" if o == 0 else f"balanced ({o})"
        print((name + " mean").ljust(22) + "".join(f"{mean[k]:14.3f}" for k in KEYS))
        print((name + " sd").ljust(22) + "".join(f"{sd[k]:14.3f}" for k in KEYS))
    json.dump(out, open(OUT, "w"), indent=1)
