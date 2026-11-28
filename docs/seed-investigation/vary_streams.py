"""Which random draws make seeds diverge? Vary one random stream at a time (others fixed at seed 11).
Usage: python vary_streams.py DAYS OUT.json [rules-json]"""
import sys, json, statistics, multiprocessing as mp
sys.path.insert(0, "/home/user/simulationTheory")
from simulation import World
from simulation.rules import Rules

DAYS = int(sys.argv[1]); OUT = sys.argv[2]
EXTRA = json.loads(sys.argv[3]) if len(sys.argv) > 3 else {}
BASE, ALTS = 11, [12, 13, 14, 15, 16]
STREAMS = ["money", "inventory", "assets", "owners", "positions", "traits", "personality", "homes", "luck", "run"]

def run(job):
    stream, s = job
    seeds = {} if stream == "base" else ({k: s for k in World.STREAMS} if stream == "ALL" else {stream: s})
    w = World(seed=BASE, rules=Rules.from_dict({"agents": 200, **EXTRA}), stream_seeds=seeds)
    w.spawn_random_agents()
    food30 = None
    for d in range(1, DAYS + 1):
        w.step()
        if d == 30:
            food30 = w.current_prices()["food"]
    h = w.recorder.history[-1]; p = w.current_prices()
    return stream, s, {"in_need": h["in_need"], "food": p["food"], "food_d30": food30, "inflation": h["inflation"],
                       "built": sum(getattr(w, "assets_built", {}).values()), "hired": w.labor.stats["hired"],
                       "wage": w.labor.wage, "gini": h["gini_wealth"],
                       "big_owners": sum(1 for a in w.agents if sum(a.assets.values()) >= 1)}

if __name__ == "__main__":
    jobs = [("base", BASE)] + [(st, s) for st in STREAMS + ["ALL"] for s in ALTS]
    with mp.Pool(4) as pool:
        res = pool.map(run, jobs)
    base = res[0][2]
    out = {"days": DAYS, "rules": EXTRA, "base": base, "streams": {}}
    for st in STREAMS + ["ALL"]:
        vals = [base] + [m for k, s, m in res if k == st]
        out["streams"][st] = {"runs": vals, "sd": {k: statistics.pstdev([v[k] for v in vals]) for k in base},
                              "range": {k: [min(v[k] for v in vals), max(v[k] for v in vals)] for k in base}}
    json.dump(out, open(OUT, "w"), indent=1)
    keys = ["in_need", "food", "food_d30", "inflation", "built", "hired", "gini"]
    print("stream".ljust(12) + "".join(k.rjust(11) for k in keys))
    for st in STREAMS + ["ALL"]:
        sd = out["streams"][st]["sd"]
        print(st.ljust(12) + "".join(f"{sd[k]:11.3f}" for k in keys))
