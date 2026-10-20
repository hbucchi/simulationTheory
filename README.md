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

1. **NeedsDecay** – needs rise each step (defaults: hunger +0.010, sleep +0.005,
   thirst +0.015, boredom +0.008; configurable per agent).
2. **Production** – +1 food / water / games every N steps (default N = 10, configurable per agent).
3. **Consume** – a need above **0.5** is fed from own stock until it is **below 0.3**.
   1 food = −0.1 hunger, 1 water = −0.1 thirst, 1 game = −0.1 boredom.
4. **Navigate** – in priority order:
   - *leaving*: just traded, walk away.
   - *seeking*: a need is still above 0.5 because stock ran out. Every step,
     find the closest agent it hasn't just met and walk straight at that
     agent's current position (re-aiming as everyone moves).
   - *meeting*: another agent is seeking this one, walk toward that seeker.
   - *wandering*: random walk.

   Because the sought agent walks back toward its seeker, the gap shrinks by
   both agents' movement every step, so they always touch.

Contacts are checked right after each agent moves (not once at the end of the
tick). When two agents touch and at least one needs something, they **trade**
at 1:1: each buys exactly enough to bring its needs below 0.3. The seller only
sells what it doesn't need itself. The buyer pays with something the seller
needs (barter), otherwise money, otherwise any other spare resource. If a need
can't be met the log says why (e.g. *"No trade: Agent 4 still needs 7 water:
Agent 2 has none"*). After a trade both walk **away from each other**, turned
by a random angle in ±90° (a 180° window that never points back), for 15
steps. Either way the pair ignores each other for 60 steps, so a needy agent
moves on to the next-closest agent instead of retrying the same one. Agents
that bump into each other without needing anything just carry on.

Sleep has no resource yet, so it only rises and never triggers seeking.

### Run it

Needs Python 3.10+ and nothing else (standard library only).

```bash
python3 server.py                    # http://localhost:8000, 3 agents
python3 server.py --agents 10 --seed 42 --port 9000
```

In the page: **Step** (or →) for turn-based, **Play/Pause** (or Space) for
timed steps at the chosen interval, **+100** to fast-forward, **Reset** to
respawn agents at random positions.

The sidebar has two tabs:

- **Overview** – a card per agent (needs, inventory, money, what it is doing)
  and the event log. A dashed line shows who a seeking agent is heading for.
- **Manage agents** – create, edit and remove agents while the simulation
  runs. Pick an agent (chip, card *Edit* button, or click its dot) to edit
  name, position, movement, money, current needs, need growth rates,
  inventory and production. Untouched fields keep updating live; only the
  fields you change are saved. The form also shows, per resource, units used
  per step (need rate ÷ 0.1) vs units made (1 ÷ N).

### Tests

```bash
python3 -m unittest discover -s tests
```

### Layout

```
server.py                 local HTTP server + JSON API (see the docstring at the top)
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
