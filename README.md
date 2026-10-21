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

### Game rules (setup screen)

The page opens on a **Game rules** screen (reopen it any time with *Game rules /
New game*). Everything there applies to the whole game:

- **World**: number of agents, seed, touch distance, how long traders walk apart
  and ignore each other.
- **Starting agents**, **production**, **consumption**: every per-agent value
  (food, water, games, money, movement, starting needs, production intervals,
  need growth rates, sleep recovery) has its own distribution:
  - *Fixed*: every agent gets the same value.
  - *Uniform*: anywhere between min and max.
  - *Normal (Gaussian)*: mean and std, cut off at mean ± N std (values
    outside are re-drawn). Optional skew: 0 = symmetric, positive = most
    agents low and a few high.
  - *Tiered* (inventory and money only): an average per agent and any number
    of tiers, e.g. top 1% of agents hold 50% of the total, next 10% hold 20%,
    everyone else shares the rest. At the start the total is shared out
    exactly; agents added later land in a tier at random with those odds.

  A histogram (or, for tiers, the agents per tier and what each gets) shows
  the result. *Copy to all resources / needs* reuses a row's distribution.
- **Trading**: a buyer buys its need × a random multiplier (1–3 by default),
  limited by what the seller can spare and what the buyer can pay, so it
  stocks up for later.
- **Need thresholds**: act above / until below, and how much 1 unit relieves.
- **Prices**: scarcity formula or fixed prices.
- **Life and death**: turn death and depression on/off, depression strength.

Presets (balanced, lean start, specialists, unequal wealth, drought, easy, barter) are
starting points. A preview explains what the rules mean for an average agent
(shortages, how long stocks last, time asleep, starting prices). *Restart* in
the toolbar starts over with the same rules.
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
     find the closest agent that has spare of what it needs (most urgent need
     first, skipping agents it has just met) and walk straight at that agent's
     current position (re-aiming as everyone moves).
   - *searching*: same, but nobody has any to sell: keep wandering.
   - *meeting*: another agent is seeking this one, walk toward that seeker.
   - *wandering*: random walk.

   Because the sought agent walks back toward its seeker, the gap shrinks by
   both agents' movement every step, so they always touch.

Contacts are checked right after each agent moves (not once at the end of the
tick). When two agents touch and at least one needs something, they **trade**
at market prices: each buys what brings its needs below 0.3, times a random
multiplier between `purchase_min` and `purchase_max` (1–3 by default). The
seller only sells what it doesn't need itself. The buyer pays with something
the seller needs (barter, with the price difference settled in money),
otherwise money, otherwise any other spare resource. If a need can't be met
the log says why (e.g. *"No trade: Agent 4 still needs 7 water: Agent 2 has
none"*). After a trade both walk **away from each other**, turned by a random
angle in ±90° (a 180° window that never points back), for 15 steps. Either
way the pair ignores each other for 60 steps, so a needy agent moves on to the
next-closest agent instead of retrying the same one. Agents that bump into
each other without needing anything just carry on.

### Market dynamics: stockpiling

Each step the world records the average units per living agent of every
resource. When that average has fallen by at least the trigger (10%) over the
window (100 steps), the resource is *becoming scarce* and agents start
hoarding it:

- An agent wants a **reserve** of its own net use (use minus own production)
  for `stockpile_steps` steps (100), scaled by how fast the resource is
  falling: a fall of 1× the trigger → 1× the reserve, 2× → 2×, capped at 3×.
  Agents that produce enough themselves don't stockpile.
- An agent below its reserve goes to the nearest seller even when it isn't in
  need yet (activity *stockpiling*). Reserve units are paid in money only, at
  most `stockpile_budget` (half) of its money per trade.
- Sellers don't sell into their own reserve, so hoarding also shrinks supply.

The Overview market panel shows units per agent, the fall over the window, a
trend line and an *agents stockpiling* badge; cards show each agent's reserve.
All of it is set in the *Market dynamics* section of the setup screen.

### Market dynamics: demand pressure

Each step, for every resource the world counts **buyers** (agents that need it
or are short of their reserve) and **sellers** (agents with some to spare):

    target multiplier = ((buyers + 1) / (sellers + 1)) ^ sensitivity     (0.5)
    multiplier += speed × (target − multiplier)                          (0.2 per step)
    price = base price × multiplier, kept within base × [0.25, 4]

Many buyers for few sellers push the price up; many sellers for few buyers
push it down. When buyers outnumber sellers, each extra unit in the same deal
costs 5% more than the one before, and the event log shows the rise. The
Overview market panel shows base price × multiplier, buyers vs sellers, an
arrow and a price chart. All of it is set in *Market dynamics: demand
pressure* on the setup screen.

### Investment

Each step an agent keeps **liquidity**: enough money to buy 3 units of every
resource at current prices. Everything above that it spends on **assets**.

- One asset per resource type. Owning n assets of a resource raises the
  owner's production of it by n × asset return (1% by default): e.g. 9 water
  assets make water come 9% faster. Asset price and return are set per
  resource on the setup screen (10 money and 1% by default).
- The agent buys as many as it can afford of the asset that adds the most
  income per money spent: return ÷ steps per unit × current price ÷ asset
  price. Assets for a resource it doesn't produce add nothing, so they are
  never bought.
- Agents can start with assets: the *Starting agents* section has a row per
  asset with the usual distributions (fixed, uniform, normal, tiered).
- The buyer first buys existing assets from agents that are **short of cash**
  (less than their liquidity plus the cost of what they need to buy right
  now), most cash-short first, and pays them; a seller stops once it has the
  cash it needs. Only the rest are new assets.
- Money for new assets goes to the **asset builder**, which pays 1% of what it holds
  back to all living agents each step, split evenly (like wages). Total money
  stays constant, and the builder's money still counts toward the price level.
  Agents reinvest the income, so production keeps growing.

The market panel shows assets owned, the builder's funds and the totals
invested and paid back; cards show each agent's assets and production boost;
*Manage agents* can edit assets.

### Prices

Prices are recomputed from what everyone holds at the moment of each trade:

    price(r) = total money / total units of all resources × (1 − share of r)
    share of r = units of r / total units

A scarce resource has a small share, so it costs more. The Overview tab shows
the current prices. With no goods left at all, every price is 0.

### Death and depression

- **Hunger or thirst at 1.00** (after eating/drinking whatever it had) → the
  agent **dies** and disappears with its inventory and money.
- **Boredom at 1.00** → the agent becomes **depressed**: its movement and its
  sleep recovery are halved. It recovers when boredom drops below 0.3.

**Sleep** is recovered by standing still (`Rest` module). When sleep rises
above 0.5 the agent stops where it is and recovers 0.05 per step
(*sleep recovery*, editable per agent) until sleep is below 0.3, then moves
again. Sleep doesn't grow while resting. A resting agent doesn't seek or walk
toward seekers, but others can still walk up to it and trade. It spends about
`growth ÷ (growth + recovery)` of its time asleep, 9% with the defaults.

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

- **Overview** – market prices, the event log, then a card per agent (needs,
  inventory, money, what it is doing). Search agents by name, filter them by
  activity (seeking, searching, sleeping, depressed, ...) and sort them by any
  resource, need, money or movement; agents filtered out fade on the map.
  A dashed line shows who a seeking agent is heading for.
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
simulation/rules.py       Rules: every game-wide setting chosen on the setup screen
simulation/distributions.py  fixed / uniform / normal / skewed per-agent values
simulation/world.py       World: the box, agents, step loop, contacts, departures
simulation/modules/       pluggable behaviours
    needs.py              NeedsDecay: needs grow every step
    production.py         Production: +1 resource every N steps
    consume.py            Consume: eat/drink/play from own stock
    navigate.py           Navigate: leave / seek nearest / wander
static/                   browser UI (canvas rendering); setup.js is the Game rules screen
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
