"""Run a game without the browser and print how the economy is doing.

    python3 tools/scenario.py                         # 1000 agents, 1500 steps, seed 1
    python3 tools/scenario.py --agents 1000 --steps 600 --seed 3 --rules '{"banking_enabled": false}'

Every --every steps it prints one line: population, deaths so far, unemployment, the price of
food and water, the wage, money (cash + deposits), loans, asset shares (industry capacity), and
wealth inequality (Gini). Ends with a summary. Use it to check a change on a big game.
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from simulation import World  # noqa: E402
from simulation.rules import Rules  # noqa: E402


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--agents", type=int, default=1000)
    p.add_argument("--steps", type=int, default=1500)
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--every", type=int, default=100)
    p.add_argument("--rules", default="{}", help="JSON rule overrides")
    args = p.parse_args()
    w = World(seed=args.seed, rules=Rules.from_dict({"agents": args.agents, **json.loads(args.rules)}))
    w.spawn_random_agents()
    start_shares = sum(sum(a.assets.values()) for a in w.agents)
    t0 = time.time()
    print(f"{'step':>5} {'alive':>5} {'dead':>5} {'unemp':>6} {'food':>7} {'water':>7} {'wage':>7} "
          f"{'money':>10} {'loans':>9} {'shares':>7} {'gini_w':>6}", flush=True)
    for step in range(1, args.steps + 1):
        w.step()
        if step % args.every == 0 or step == args.steps:
            h = w.recorder.history
            s = h[-1]
            prices = w.current_prices()
            b = w.banking.to_dict(w)
            print(f"{step:>5} {len(w.agents):>5} {sum(x['deaths'] for x in h):>5} {s['unemployment']:>6.2f} "
                  f"{prices['food']:>7.1f} {prices['water']:>7.1f} {w.labor.wage:>7.1f} "
                  f"{b['money_supply']:>10.0f} {b['loans']:>9.0f} {sum(sum(a.assets.values()) for a in w.agents):>7.1f} "
                  f"{s['gini_wealth']:>6.2f}", flush=True)
    h = w.recorder.history
    print(json.dumps({
        "agents": args.agents, "steps": args.steps, "seed": args.seed, "rules": json.loads(args.rules),
        "alive": len(w.agents), "deaths": sum(x["deaths"] for x in h),
        "deaths_hunger": sum(x["deaths_hunger"] for x in h), "deaths_thirst": sum(x["deaths_thirst"] for x in h),
        "shares_start": round(start_shares, 1), "shares_end": round(sum(sum(a.assets.values()) for a in w.agents), 1),
        "banks_open": len(w.banking.open_banks()), "loans": round(w.banking.to_dict(w)["loans"], 2),
        "seconds_per_step": round((time.time() - t0) / args.steps, 3),
    }), flush=True)


if __name__ == "__main__":
    main()
