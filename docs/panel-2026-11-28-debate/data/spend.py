"""Where does the government's money go? Prints spending by category after 270 days (seed 11)."""
import sys, json; sys.path.insert(0, "/home/user/simulationTheory")
from simulation import World
from simulation.rules import Rules
extra = json.loads(sys.argv[1])
w = World(seed=11, rules=Rules.from_dict({"agents": 200, **extra})); w.spawn_random_agents()
for _ in range(270): w.step()
g = w.government
print(json.dumps({"rules": extra, "spent": {k: round(v) for k, v in g.spent.items() if v},
                  "collected": {k: round(v) for k, v in getattr(g, "collected", {}).items() if v}}))
