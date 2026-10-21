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
2. **Production** – labour from the agent; goods only from its assets, worked by labour (see below).
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
angle in ±90° (a 180° window that never points back), for 15 steps, unless
someone is coming to buy from them (then they go and meet that buyer) or they
are still in need themselves. The pair then ignores each other for 60 steps
after a deal, or 10 steps when nothing could be traded, so a needy agent moves
on to the next-closest agent instead of retrying the same one. Sellers never
sell below their stock floor, even to an agent in need. Agents that bump into
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

### Market dynamics: demand and concentration

    price = base price × multiplier
    base price = total money / total units × (1 − share of the resource)
    multiplier → demand pressure × concentration   (closing 20% of the gap each step,
                                                    kept within base × [0.25, 4])
    demand pressure = ((buyers + 1) / (sellers + 1)) ^ elasticity[resource]
    concentration   = 1 + weight[resource] × C

- **Base price**: how much of the resource exists compared with money and the
  other commodities.
- **Demand pressure**: buyers are agents that want it (need it, are short of
  their reserve, or are below the stock floor); sellers are agents with some
  to spare. The **elasticity is set per resource** (0.5 by default): with 0
  buyers and sellers don't matter, with 1 twice as many buyers doubles the price.
- **Concentration**: C measures how concentrated the sellable supply is:
  0 when it is spread evenly over the agents, 1 when one agent holds all of it
  (a normalised Herfindahl index). With weight 1 (per resource) a monopoly
  doubles the price.
- When buyers outnumber sellers, each extra unit in the same deal costs 5% more
  than the one before, and the event log shows the rise.

The Overview market panel shows base × multiplier with both parts, buyers vs
sellers, C, an arrow and a price chart.

### Labour, assets and productivity

**Labour is a capacity, not a stock** (`simulation/labor.py`). Each step every
agent can work up to `labor_capacity` (0.5 by default) × its efficiency. Labour
is never stored: it is sold in the labour market that step, and anything nobody
buys is lost. Food, water and games are made **only by assets**, worked by
labour:

    output of a good = productivity × min(labour available, shares × labour per asset)

**Labour market (clears once per step, before agents act)**
- Owners first use their own labour on their own assets; the rest of the jobs
  their assets offer (full capacity) is what they want to hire.
- Every agent offers part of its free capacity:
  `participation_floor + (1 − participation_floor) × need for a job`.
- Market wage = base × multiplier. Base = `labor_share` (60%) × value one unit
  of labour makes (units per labour × price of the good). The multiplier moves
  toward `((labour wanted + 1) / (capacity offered + 1)) ^ labour elasticity`,
  so more workers offering for the same jobs lower the wage.
- Each worker asks `wage × (1 + bargaining_spread × (wellbeing − need))`.
  Employers hire the cheapest workers first and pay cash (keeping enough for
  their own needs). The government may then hire some of what is left with
  newly created money.

**Labour capacity module (efficiency, wellbeing, need)**
- Efficiency = 1 − Σ weight × need level (hunger 0.3, thirst 0.3, sleep 0.2,
  boredom 0.1) − depression penalty (0.3), at least `min_efficiency` (0.2).
- Wellbeing = 1 − weighted average of needs − depression penalty.
- Need for a job = `money_weight` × how far its money is below
  `comfort_steps` (50) steps of its cost of living + the rest × its most
  pressing need. Higher need → offers more labour and asks a lower wage.

**Industries get less labour-intensive**: every `productivity_growth_steps`
(50) steps productivity (units per labour) grows `productivity_growth` (5%) and
the labour one asset needs falls `labor_saving` (3%).

By default, for each good 10% of the agents own all its assets (drawn
separately per good), so most agents are **workers** who live by selling
labour.

### Investment

- **No assets are created.** The only ones are the starting assets (*Starting
  agents*, any distribution). They only change hands between agents, as
  **shares** (0.5 of a food asset employs half as much labour).
- **Asset price = profit per step at full capacity ÷ return** (1%), where
  profit = output × price of the good − labour × wage, never below 0. A dearer
  good or higher productivity makes assets dearer; higher wages make them
  cheaper.
- Each step an agent keeps cash for what it needs to buy now plus 3 units of
  every resource. Once at least `min_investment` (10) is spare, it buys shares
  of the best-returning asset of a good it **lacks**, from owners that:
  - are **short of cash**: just enough shares to cover the gap, or
  - hold **more than the stock cap** of that good: up to a quarter of those
    assets per deal.

### Report

The **Report** view (top bar: *Simulation | Report*) is a dashboard of the
current game over the last 100 / 250 / 500 / all recorded steps (the world
keeps one snapshot per step, up to 2,000):

- headline numbers in three groups, each with its change since the start of
  the window (holdings compare first and last step; per-step flows compare the
  average of the first and last ~5% of the window):
  - **Distribution**: Gini of wealth, money, asset shares, income and
    consumption; share held by the richest 10% and the poorest 50%; number of
    asset owners;
  - **Employment**: employment rate (agents who worked, on their own assets or
    hired), participation (agents offering labour), unemployment (offered
    labour nobody hired), unfilled jobs, capacity used, wage, labour share of
    output (wages / value of goods produced), government spending;
  - **Living standards**: population and deaths by cause, total wealth and
    wealth per agent (money / goods / assets), income and consumption per agent,
    wellbeing, share in need, share struggling (need for a job above 0.5);
- prices of every resource over time, with now / min / avg / max / change;
- production vs consumption of each good per step, with totals;
- employment rates over time and an owners-vs-workers table;
- labour capacity, used, unused and bought by the government;
- workers' condition and hardship (in need, struggling, deaths by cause);
- inequality of holdings (Gini) and Lorenz curves (money, shares, wealth,
  income); inequality of income and consumption; wealth by fifth;
- income by source (wages, goods sales, asset sales, government);
- total wealth, income per step, the richest agents, trading activity and
  population.

**What wealth means.** An agent's wealth = money + the goods it holds at
today's prices + its asset shares at today's asset prices. Asset prices come
from profit (output value minus wages, over the return), so an asset that
doesn't cover its wages is worth 0 even though it still produces; that is why
asset *ownership* inequality is measured on shares, not value. Everyone starts
with the same money and money is most of wealth, so the wealth Gini starts near
0 and moves slowly; uneven or smaller starting money makes differences show up
sooner. Income = money received, tagged by source. Income and consumption
inequality use each agent's smoothed per-step income/consumption.
`GET /api/report?window=N` returns the same data.

Money is shown in dollars with two decimals. Agents start with $22,500, so at
the default stock (100 of each good) the starting price is
22,500 / 300 units × (1 − 1/3) = **$50** for every good. The "lean start" preset
cuts money to $2,250 to keep that $50.

When an agent dies, its goods and asset shares are **sold at market price** to
the nearest agents who can pay (nearest first). Buyers spend only the money
above what they want on hand (the same cash rule as investing), so a poor
neighbour can't buy. What nobody can afford is lost, and the sale price leaves
the economy together with the dead agent's own money.

### Central government

- **Minimum interest rate**: no asset is valued at a return below it. The
  effective return of an asset is max(its own return, the policy rate), so
  raising the rate makes every asset cheaper (price = output × good price ÷
  return) and changes which asset investors prefer.
- **Buying labour**: every step the government buys the chosen number of
  labour units at the current labour price from agents with labour to spare
  (in random order), paying with **newly created money**. The labour is used up
  in public works. This is how money is injected into the economy.

Both start from the setup screen (*Central government*) and can be changed
while the game runs in the **Government** tab, which also shows money created,
labour bought and the effect on prices.

### Stock band

Agents keep between the floor (50) and the cap (100) units of each resource.
Above the cap they go out to **sell** the surplus to agents that want it, to
make money; below the floor they go out to **restock** back up to the cap,
paying in money. They never sell below the floor. Between floor and cap they
keep what they have, which also stops assets going back and forth.

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
