"""Why does labour offered fall? Decomposes labour at day 45 and day 270 (seed 11)."""
import sys, json; sys.path.insert(0, "/home/user/simulationTheory")
from simulation import World
from simulation.rules import Rules
extra = json.loads(sys.argv[1])
w = World(seed=11, rules=Rules.from_dict({"agents": 200, **extra})); w.spawn_random_agents()
out = {"rules": extra}
for d in range(1, 271):
    w.step()
    if d in (45, 270):
        A = w.agents; r = w.rules
        base = sum(a.labor_capacity for a in A); cap = sum(a.capacity_now for a in A)
        own = sum(a.own_labor for a in A); offered = sum(a.offered for a in A)
        free = cap - own
        covered = [a for a in A if getattr(a, "months_left", 0) >= r.labor_offer_months]
        out[f"day{d}"] = {"base_capacity": round(base, 1), "capacity_after_penalties": round(cap, 1),
            "own_business_labour": round(own, 1), "free": round(free, 1), "offered": round(offered, 1),
            "withheld_by_covered_agents": round(sum(a.capacity_now - a.own_labor - a.offered for a in covered), 1),
            "agents_covered_6m": len(covered), "agents_sick_health_over_0.8": sum(1 for a in A if a.health >= 0.8),
            "median_months_left": sorted(getattr(a, "months_left", 0) for a in A)[len(A) // 2]}
print(json.dumps(out))
