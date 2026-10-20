# simulationTheory
Simulation environments to test/train agents.

## Agent box simulation

Agents are dots living in a 1024×1024 box. Each one has:

| Property | Type | Meaning |
|---|---|---|
| `hunger`, `sleep`, `thirst`, `boredom` | float 0.00–1.00 | How strong the need is: 0.00 = satisfied, 1.00 = desperate. Always clamped. |
| `money` | float | Balance (default 100). Tradable 1:1 like any resource. |
| `inventory` | `Inventory` | food / water / games (default 100 each). |
| `movement` | int | Max pixels the agent can travel in one step. |
| `x`, `y` | float | Position inside the box (0–1024). |

### Rules (`simulation/economy.py`)

Every step each agent runs its modules in this order:

1. **NeedsDecay** – needs rise (hunger +0.010, sleep +0.005, thirst +0.015, boredom +0.008).
2. **Production** – +1 food / water / games every N steps (default N = 10, configurable per agent).
3. **Consume** – a need above **0.5** is fed from own stock until it is **below 0.3**.
   1 food = −0.1 hunger, 1 water = −0.1 thirst, 1 game = −0.1 boredom.
4. **Navigate** – *leaving* (just met someone) › *seeking* (a need is still above 0.5
   because stock ran out: walk to the nearest agent it hasn't just met) › *wandering*.

When two agents touch (centres ≤ 12 px apart) they **trade** at 1:1: each buys
exactly enough to bring its needs below 0.3. The seller only sells what it
doesn't need itself. The buyer pays with something the seller needs (barter),
otherwise money, otherwise any other spare resource. Afterwards both walk
**away from each other**, turned by a random angle in ±90° (a 180° window
that never points back), for 15 steps, and ignore each other for 60 steps.

Sleep has no resource yet, so it only rises and never triggers seeking.

### Run it

Needs Python 3.10+ and nothing else (standard library only).

```bash
python3 server.py                    # http://localhost:8000, 3 agents
python3 server.py --agents 10 --seed 42 --port 9000
```

In the page: **Step** (or →) for turn-based, **Play/Pause** (or Space) for
timed steps at the chosen interval, **+100** to fast-forward, **Reset** to
respawn agents at random positions. **Add agent** creates one more agent with
editable starting food / water / games / money and production rates.
To see trading quickly, add an agent with 0 food and 0 water.
A dashed line shows who a seeking agent is heading for.

### Tests

```bash
python3 -m unittest discover -s tests
```

### Layout

```
server.py                 local HTTP server + JSON API (/api/state, /api/step, /api/reset, /api/agents)
simulation/agent.py       Agent class (properties, movement helper)
simulation/inventory.py   Inventory class
simulation/economy.py     resources, consumption and trading rules
simulation/world.py       World: the box, agents, step loop, contacts, departures
simulation/modules/       pluggable behaviours
    needs.py              NeedsDecay: needs grow every step
    production.py         Production: +1 resource every N steps
    consume.py            Consume: eat/drink/play from own stock
    navigate.py           Navigate: leave / seek nearest / wander
static/                   browser UI (canvas rendering)
```

### Adding a module

A module is any object with `on_step(agent, world)`:

```python
from simulation.modules import Module

class Nap(Module):
    def on_step(self, agent, world):
        if agent.sleep > 0.8 and agent.activity == "wandering":
            agent.sleep -= 0.05

agent.add_module(Nap())
```
