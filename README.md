# simulationTheory
Simulation environments to test/train agents.

## Agent box simulation (v0)

Agents are dots living in a 1024×1024 box. Each one has:

| Property | Type | Meaning |
|---|---|---|
| `hunger`, `sleep`, `thirst`, `leisure` | float 0.00–1.00 | How strong the need is: 0.00 = satisfied, 1.00 = desperate. Always clamped. |
| `money` | float | Unbounded balance, used for trading later. |
| `movement` | int | Max pixels the agent can travel in one step. |
| `x`, `y` | float | Position inside the box (0–1024). |
| `inventory` | `Inventory` | `{item: quantity}`, starts empty. |

Time advances in **steps** (ticks). Each step every agent runs its modules,
then any two agents within `contact_distance` (12 px, two dots touching) are
"in touch" and `World.interact(a, b)` is called. Right now it only logs the
meeting; trading will plug in there.

### Run it

Needs Python 3.10+ and nothing else (standard library only).

```bash
python3 server.py                    # http://localhost:8000, 3 agents
python3 server.py --agents 10 --seed 42 --port 9000
```

In the page: **Step** (or →) for turn-based, **Play/Pause** (or Space) for
timed steps at the chosen interval, **Reset** to respawn agents at random
positions. Click a dot or card to highlight an agent.

### Tests

```bash
python3 -m unittest discover -s tests
```

### Layout

```
server.py                 local HTTP server + JSON API (/api/state, /api/step, /api/reset)
simulation/agent.py       Agent class (properties, movement helper)
simulation/inventory.py   Inventory class
simulation/world.py       World: the box, agents, step loop, contact detection
simulation/modules/       pluggable behaviours
    needs.py              NeedsDecay: needs grow every step
    wander.py             Wander: random walk, ≤ movement px per step
static/                   browser UI (canvas rendering)
```

### Adding a module

A module is any object with `on_step(agent, world)`:

```python
from simulation.modules import Module

class Drink(Module):
    def on_step(self, agent, world):
        if agent.inventory.remove("water"):
            agent.thirst -= 0.3

agent.add_module(Drink())
```
