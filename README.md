# simulationTheory
Simulation environments to test/train agents.

## Agent box simulation

Agents are dots living in a 1024×1024 box. Each one has:

| Property | Type | Meaning |
|---|---|---|
| `hunger`, `sleep`, `thirst`, `boredom`, `health`, `energy`, `shelter` | float 0.00–1.00 | How strong the need is: 0.00 = satisfied, 1.00 = desperate. Always clamped. |
| `money` | float | Balance (default 100). Tradable 1:1 like any resource. |
| `inventory` | `Inventory` | units of any of the 36 goods (see *Industry catalog*); goods with a shelf life are kept as dated batches that expire. |
| `movement` | int | Max pixels the agent can travel in one step. |
| `x`, `y` | float | Position inside the box (0–1024). |

### Modules: build your own economy

The setup screen starts with **Modules**: switch whole parts of the economy on or off.

| Module | What it does | Needs |
|---|---|---|
| Commerce | agents trade goods (money or barter) | – |
| Industries & labour | asset shares make goods with labour; the labour market | – |
| Selling surplus | stock band: agents sell what is above it | Commerce |
| Supply & demand pricing | prices follow buyers vs sellers and concentration | Commerce |
| Stockpiling | hoarding goods that are becoming scarce | Commerce |
| Investing | buying and selling asset shares | Industries |
| Building new capacity | new asset shares from capital goods | Industries, Investing |
| Commercial banks | deposits and loans (banking is an industry) | Industries, Commerce |
| Consumer credit | borrowing for what agents need now | Commercial banks |
| Government & central bank | policy rate, Basel rule, buying labour | – |
| Expiry, Death, Depression | goods go off; hunger/thirst kill; boredom depresses | – |

A module whose needs are off doesn't work: the server switches it off and the setup screen
greys it out and says why. Quick starts set a whole combination: **Survival: no
production** (trade only; nothing is made, so the starting stock runs out: in a 1000-agent
test everyone was gone by day 500), **Market of producers** (industries + trade),
**Capitalism without banks** (+ investing and building) and **Full economy**. In 1000-agent
tests (600 days, seed 1) the last three had no deaths. The industry picker (below) is the other
half: which industries exist.

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
   thirst +0.015, boredom +0.008, health +0.003, energy +0.004, shelter +0.002;
   configurable per agent).
2. **Production** – labour from the agent; goods only from its assets, worked by labour (see below).
3. **Consume** – a need above **0.5** is fed from own stock until it is **below 0.3**,
   using the goods that do the agent most good first (relief for that need plus side
   effects on its other needs, see *Effects*); every unit consumed has all its effects.
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
buys is lost. Goods are made **only by assets** (each industry's capital), worked by
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

### Industry catalog, layers and expiry

Every good is made by its own **industry**, whose capital is that good's assets.
`simulation/catalog.py` defines 37 industries named after the TRBC sectors and
industries that investing.com's screener uses (Energy, Basic Materials,
Industrials, Consumer Cyclicals, Consumer Non-Cyclicals, Healthcare, Technology,
Telecommunications, Utilities, Real Estate, Financials):

| Layer | Industries |
|---|---|
| 1 extraction | grain, livestock, water, timber, crude oil, natural gas, coal, metal ore, stone & sand, medicinal herbs |
| 2 | food, meat, beverages, beer/wine/spirits, electricity, fuel, steel, chemicals, lumber, cement, textiles, toys & games |
| 3 | packaged meals, fast food, plastics, pharmaceuticals, machinery, construction, housing, apparel |
| 4 | electronics, medical devices |
| 5 | telecom services, media, healthcare services |
| 6 | software & IT |

**Layers come from the recipes.** A primary industry (no inputs) is layer 1;
an industry that uses layer-n goods is layer n + 1. Up to 10 layers are allowed.
**`industry_layers`** (1–10, chosen on the setup screen before a game starts)
removes every industry deeper than that: nobody owns, holds or makes its goods.

**Choosing the industries (a modular game).** On the setup screen, *Game size:
layers and industries* has quick starts (*Simple · layer 1*, *Basic · layers 1–2*,
*Standard · layers 1–3*, *Full*) and a checkbox per industry, grouped by layer.
Unticked industries go into **`excluded_industries`** and don't exist in the game.
An industry still needs every input of its recipe, so leaving one out also leaves
out everything made from it, all the way down (no grain → no food, beverages,
packaged meals or fast food); the picker greys those out and says which input is
missing, and the state reports them as `auto_excluded`. With *Size starting
industries to this game* ticked (the default), the server sizes the starting
industries for exactly the industries that are left, and stock of a missing good
becomes the same relief in the best remaining good for that need. The preview
warns when a need has nothing left to relieve it; for hunger or thirst that means
everyone dies, and the game asks before starting.

**Effects: one good, several needs.** Every good has an effect profile
(`effects`: {need: fit}, fit from −1 to +1): what consuming one unit does to each
need. Almost all goods can be consumed; a few are pure inputs (ore, steel, cement,
plastics, machinery). A positive fit relieves the need by

    relief_per_unit × fit × (1 + layer_bonus × (layer − 1))     (layer_bonus 0.5)

so deeper industries address needs better (water 0.10 thirst, beverages 0.15;
herbs 0.06 health, pharmaceuticals 0.20, healthcare services 0.30). A negative fit
worsens the need by relief_per_unit × |fit| (harm isn't scaled by layer). Examples:

| Good | Effects per unit |
|---|---|
| fast food (layer 3) | hunger +0.20, boredom +0.08, health −0.04 |
| beer, wine & spirits (layer 2) | boredom +0.105, thirst +0.03, health −0.05, sleep −0.01 |
| beverages (layer 2) | thirst +0.15, boredom +0.03, health −0.01 |
| coal (layer 1) | energy +0.04, health −0.03 |
| electronics (layer 4) | boredom +0.15, energy −0.02 (they use power), sleep −0.01 |
| housing (layer 3) | shelter +0.20, health +0.02, energy +0.02 |

Sleep can only be harmed by goods (it is recovered by resting). A good's biggest
benefit is its *main need* (used for the stock band and to size industries).

**Choosing what to consume or buy.** For the need being served, an agent scores a good:

    benefit = relief for that need + Σ other effects × that need's current level

so side effects count as much as the agent currently cares about them: fast food
beats packaged meals for a hungry, healthy agent (the fun outweighs a small health
cost) but not for one whose health is already poor. Goods with a negative benefit
are never consumed. Agents buy for a **need**: they go to the nearest agent with any
good for their most pressing need and buy the most benefit per dollar. Demand and the
stock band count the relief from every good already held for that need.

**Expiry.** Every good has a shelf life in steps (0 = never): services barely keep
(electricity 20, telecom and healthcare 25, media 40), fresh food a little longer
(meat 50, herbs 100, meals 150, food 200), processed goods much longer (beverages
600, grain 800, pharmaceuticals 800, fuel 1,500, apparel 3,000), and raw materials
and durable goods never expire. Units are kept as dated batches: the oldest are used
first, a trade passes on their dates, and anything past its date is thrown away at
the start of each step (counted in the market panel and the report; losses of 5+
units are logged). Starting stock is spread over ages so it doesn't all expire on the
same step. Agents only stock a perishable good up to what they would consume in 80%
of its shelf life. Turn expiry off with `expiry_enabled`.

**Capital goods and building new capacity.** Industries no longer only change hands:
new asset shares can be **built** out of capital goods.

- Capital-goods industries: **machinery** (Industrials, layer 3: steel + coal) and
  **construction** (Construction & Engineering, layer 3: cement + steel + lumber);
  **electronics** doubles as technology equipment. Their plants (and **housing**'s)
  have about a tenth of the usual capacity per asset (`asset_labor` 0.02 / 0.05 jobs per
  share), so capital and homes are made slowly, while labour per unit stays normal for
  their layer.
- `build_cost[g]`: capital goods per new share of industry g. Defaults: extraction
  2 machinery + 1 construction; layers 2–3: 3 machinery + 2 construction; deeper:
  2 machinery + 2 construction + 2 electronics; technology services (telecom, media,
  healthcare, software): 2 construction + 3 electronics; housing: 2 construction + 1 machinery.
- **Build module**: an investor with spare cash (same cash rules as investing) compares
  each industry's asset value with what its capital goods cost now (Tobin's q). If the
  best q ≥ `build_min_q` (1) and those capital goods are actually for sale (not already
  claimed by other projects), it starts a project for up to 1 share, goes out to buy the
  goods (activity *building*; it never sells them), and once it holds them all turns them
  into new shares. Projects unfinished after `project_steps` (300) are dropped. While it has
  a project it doesn't buy existing shares.
- Capital-goods makers keep at least 5 units ready for builders before they pause
  production. Building compounds: new machinery plants raise machinery output, which
  speeds up further building. In a 30-agent game about 100 new shares (roughly as many
  as existed at the start) get built over 1,600 steps; 3-agent games build ~20.
- Sellers now walk toward a buyer coming for their goods before going on any shopping
  trip of their own (otherwise sellers busy building could not be caught).

The market panel tags capital goods, shows each industry's build cost and q, and totals
the assets built; agent cards show a project's progress.

**Production** is fixed proportions (Leontief): output is limited by whatever runs
out first: labour, capital (asset shares × jobs per asset) or inputs.

- The labour market only hires labour an industry can use with the inputs in stock.
- Owners of secondary industries keep `input_buffer_steps` (20) steps of inputs and go
  out to buy more (activity *sourcing*) below `input_reorder` (half) of that.
- **Produce to demand**: an industry stops working while its owner holds more than
  `output_buffer_steps` (30) steps of its output (or `max_output_stock`, 200 units).
- **Cost floor**: a secondary good never sells below the cost of its inputs.
- Optional: `profit_check` (stop hiring when labour costs more than it adds) and
  `labor_priority` = `value` (labour goes to the most valuable industries first).
  Both are off by default: while prices adjust they starved agents of cheap essentials.

**Labour by layer.** Deeper industries need less labour per unit on average: units
per unit of labour are 4 at layer 1, +1 per layer (5, 6, 7, 8, software 9), so labour
per unit falls from 0.25 to 0.11. Labour-intensive industries are exceptions with
their own productivity in the catalog: housing 4 (layer default 6), fast food 5 (6),
healthcare services 6 (8). The average still falls with every layer.

**Default calibration.** Default industry sizes are
sized to demand: each need is split over its goods (e.g. thirst 70% water, 30%
beverages), the inputs are added down the layers, and each industry gets twice the
capacity that takes. An input people also consume (grain, livestock, water,
electricity, ...) is counted twice over for the industries it feeds: some of it gets
eaten directly instead of milled, and without that margin the industries made from
it starve. For a game with fewer layers or left-out industries both the sizes and the
starting stock are worked out for the industries that exist (stock of missing goods
becomes the same relief in the best remaining good). With these defaults, games of 3,
10, 30 and 200 agents with 1 to 6 layers run 1,500 steps without anyone starving,
and so do games without grain, electricity or capital goods. Leaving out several staples
at once (say livestock and crude oil) makes a tighter economy that can lose agents.

### Investment

- **Existing assets** are the starting ones (*Starting agents*, any distribution)
  plus whatever gets built from capital goods (see *Capital goods*). They change hands between agents, as
  **shares** (0.5 of a food asset employs half as much labour).
- **Asset price = profit per step at full capacity ÷ return** (1%), where
  profit = output × price of the good − labour × wage, never below 0. A dearer
  good or higher productivity makes assets dearer; higher wages make them
  cheaper.
- Each step an agent keeps cash for what it needs to buy now plus 3 units of
  every resource. Once at least `min_investment` is spare, it also checks the
  **capitalist cash rule**: after the purchase it must still hold at least
  `capital_cash_ratio` (0.2) × the value of all its assets in cash, so it can pay
  the labour those assets need (it spends at most (cash − r × assets) / (1 + r)).
  Then it buys shares
  of the best-returning asset of a good it **lacks**, from owners that:
  - are **short of cash**: just enough shares to cover the gap, or
  - hold **more than the stock cap** of that good: up to a quarter of those
    assets per deal.

**Funded labour demand.** Employers only *want* the labour they can pay for
(their spare cash ÷ the last wage), not everything their assets could employ.
Wages respond to funded demand, so unaffordable jobs no longer push wages up
while workers sit idle. The full job capacity is still shown in the Report's
"Economy capacity" scorecards.

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

### Central government and central bank

- **Capital ratio (Basel)**, set by the central bank (default 12%): a commercial bank's equity
  (its owners' own money) must be at least this share of its risk-weighted assets, its loans
  (cash reserves carry no risk, weight 0). Loans are made from third parties' money
  (deposits), so this caps how much of other people's money a bank may lend against its own:
  at 12%, $1 of equity backs at most $1 ÷ 0.12 = $8.33 of loans.
- **Minimum interest rate**: no asset is valued at a return below it. The
  effective return of an asset is max(its own return, the policy rate), so
  raising the rate makes every asset cheaper (price = output × good price ÷
  return) and changes which asset investors prefer.
- **Buying labour**: every step the government buys the chosen number of
  labour units at the current labour price from agents with labour to spare
  (in random order), paying with **newly created money**. The labour is used up
  in public works. This is how money is injected into the economy.

All three start from the setup screen (*Central government*) and can be changed while the
game runs in the **Government** tab, which also shows money created, labour bought and the
effect on prices. The government can be switched off there too (no policy rate, no labour
bought, no capital rule: banks are then limited only by their reserves and services).

### Banks

Banks are an industry (**Banking**, sector Financials), so they need resources to exist:

- **A banking plant**: asset shares of the banking industry. Like any industry it is built
  from capital goods (3 machinery + 2 construction per share) and run with labour and
  electricity (0.3 per unit), so it is a layer-3 industry: games with fewer layers, or
  without electricity, have no banks. The plant makes **banking services**, and every loan
  uses them up (one unit per `loan_per_service` lent, default $1,000). Services can't be
  traded and expire after 50 steps.
- **Minimum capital** (`bank_min_capital`, default $5,000, Basel-style): the founder's own
  money, moved into the bank as its equity before it can open. Borrowed money doesn't
  count. An agent that owns a banking plant but can't put up the capital can't open a
  bank (the log says so). An investor only starts building a bank plant if it can also
  pay the minimum capital.

How a bank works (rates per step):

- **Deposits.** Agents keep what their budget needs (below) on hand and deposit part of
  the rest (`deposit_share`) in the nearest bank. They can spend deposits like cash, as if
  paying by card. Depositors earn the deposit rate, max(`deposit_rate`, the government's
  minimum rate), on the share of deposits the bank has lent out: cash in the vault earns
  the bank nothing, so it can't pay interest on it.
- **Loans.** The loan rate is the deposit rate + `loan_spread`. Investors borrow to build when
  the asset earns more than the loan costs, up to `max_loan_to_value` of their assets (the
  collateral). Agents short of cash for what they need now can borrow the gap
  (**consumer credit**, unsecured). **Steps are days**: nobody may owe more than
  `loan_income_share` (default 40%) of its monthly income, i.e. income per step ×
  `month_steps` (30), whatever the loan is for. This can be changed during the game. Loans are repaid over `loan_steps` steps:
  each step interest on the balance + balance ÷ steps left.
- **Limits on lending.** A bank keeps `reserve_ratio` of deposits as cash, and its equity
  must stay at least the central bank's capital ratio × its loans (Basel, default 12%) and
  at least the minimum capital. So $5,000 of capital supports up to $5,000 ÷ 0.12 = $41,667
  of loans.
- **Money creation.** Lent money is spent, the seller deposits it, and the bank lends part of
  it again. With reserve ratio *ρ*, deposits can grow to 1 + (1 − *ρ*) + (1 − *ρ*)² + … = 1/*ρ*
  times the cash first put in (the **money multiplier**, shown in the Banking panel).
- **Repayment and default.** Agents pay for what they need now first and the loan only
  out of what's left. A loan unpaid for `default_steps` steps in a row defaults: the bank's
  owner takes asset shares worth the debt (paying the bank their value) and the rest is
  written off.
- **Profit and failure.** Profit = interest received − interest paid. Each step the owner
  takes its *payout ratio* of the profit as a dividend and the bank keeps the rest as
  equity, so a bank whose owner reinvests can lend more over time (12% capital ratio:
  every $1 retained supports $8.33 more of loans). A bank whose equity falls below zero
  fails: it stops lending and pays depositors back pro rata from what comes in.

**Turning banking on and off.** On the setup screen (*Banking*: on/off, number of starting
banks and their plant size, minimum capital, ratios, rates, days in a month, credit limit) and
at any time during a game in the **Commercial banks** tab (on/off, rates, ratios, minimum
capital, lend up to % of a month's income), which also lists every bank. Switched off,
banks stop lending, pay depositors back, collect their loans and close; switched on again,
owners with a plant and the capital reopen them. To leave banks out of a game entirely,
untick *Banking* in the industry picker.

### Dividends or reinvestment (every company)

Each step a company's profit (goods sold − wages paid) is split by its owner's **payout
ratio**, a personality trait (setup: *Personality: pays out*, default uniform 20%–80% per
agent; editable per agent in the Agents tab):

- the payout share goes to the owner as **dividends** (its own money);
- the rest stays in the company as **company cash** (retained earnings). Company cash pays
  the wages first, and once it reaches `min_investment` it **reinvests**: it builds new asset
  shares of an industry the owner already owns (the one worth most per unit of cost),
  so the company's asset base grows.

Two limits, as for real companies: the owner always takes enough to cover its own budget
(it has to live), and a company keeps only what it can use (a month of wages + one new asset
share); the rest is paid out. Banks work the same way with equity (above).

In 30-agent test games, companies with the default personalities built 53–100 new asset
shares in 1,500 steps, against 41–66 when every owner pays everything out.

### Budget

Every agent knows its **budget** for the next `budget_steps` steps (default 30, "a month"):

    budget = cash needed now + budget_steps × (living cost per step + loan payments per step)

The living cost is the cheapest way to keep each need from growing (food, water, housing,
energy, ...), net of what the agent's own industries make. Investing and building only use
money (cash + deposits) **above** the budget. Agent cards show the budget and what's left
to invest (or how short it is).

### Stock band

For each need, agents keep enough goods to cover **`stock_steps` (100) steps** of
that need's own growth (e.g. hunger at 0.01/step: 1.0 of relief, about 7 food or 17
grain), and restock when they fall below half of that (`restock_below`). Goods
above it are surplus they go out to **sell**. They never sell below the floor.
Goods that relieve no need are never kept for the band: producers sell all of them.
(The band used to be "100 units of each good"; with many goods per need and expiry
that hoarded raw grain as food and let perishables rot.)

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
python3 server.py --lan              # also reachable from a phone on the same Wi-Fi
```

### Big games (100–5000 agents)

The simulation is plain Python, so each step costs about *agents × industries*
checks (every agent asks, for every good, "do I want it, can I spare it?"). Measured
on one core:

| agents | layer 1 (10 industries) | layers 1–2 (22) | all layers (36) |
|---|---|---|---|
| 100 | 20 ms/step | 29 ms/step | 47 ms/step |
| 300 | 61 ms/step | 93 ms/step | 127 ms/step |
| 1000 | 260 ms/step | 420 ms/step | 560 ms/step |

What keeps it that fast:

- **Nothing compares every pair of agents.** Agents are bucketed into a grid of cells
  as wide as the touch distance (spatial hashing), so contacts and "who is near me"
  only look at the 9 cells around an agent: O(n) instead of O(n²).
- **Per-step tables.** Who wants which good, who can spare it and how much, who owns
  which asset, prices, the best assets to buy or build: worked out once per step and
  shared by every agent, instead of each agent recomputing them.
- **Need by need, not good by good.** Whether an agent wants a good is decided per
  need (one check covers every good for hunger) and cached until its inventory changes.
- **A light state.** With more than 100 agents the browser gets every agent's position,
  needs, goods and activity, but full details (labour, modules, input buffers) only for
  the agent cards on screen (at most 40, plus the selected one); search, filter or sort
  to see others, or tap a dot. 1000 agents: about 0.7 MB per update.

To play bigger games faster:

- **Steps per tick** (next to *Speed*): run 2, 5, 10 or 25 steps per update. The map
  redraws less often, but the game moves that many times faster.
- **Fewer industries**: layer 1 runs about twice as fast as the full catalog.
- **PyPy**: the code is standard-library only, so it also runs on
  [PyPy](https://pypy.org), a Python with a just-in-time compiler that is typically
  several times faster on loop-heavy code like this: `pypy3 server.py --agents 1000`.

### Playing on a phone (e.g. Samsung Galaxy S23)

1. On your computer run `python3 server.py --lan`. It prints the address to open,
   e.g. `On your phone (same Wi-Fi): http://192.168.1.23:8000`.
2. On the phone (same Wi-Fi network) open that address in Chrome or Samsung Internet.
3. Optional: browser menu -> *Add to Home screen* for a full-screen app icon.

If the page doesn't load, allow Python through the computer's firewall for private
networks. While `--lan` is on, anyone on that network can open and control the game.

On narrow screens the play controls move to a bar at the bottom, the map's dots and
labels grow so they stay readable and tappable, and the rules screen, tabs and
report collapse to one column.

In the page: **Step** (or →) for turn-based, **Play/Pause** (or Space) for
timed steps at the chosen interval (and *steps per tick*), **+100** to fast-forward,
**Reset** to respawn agents at random positions.

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
python3 -m unittest discover -s tests          # unit tests (small, fast)
python3 tools/scenario.py                      # a 1000-agent game, 1500 steps (~10-15 min)
python3 tools/scenario.py --steps 600 --rules '{"banking_enabled": false}'
```

Changes are checked on **1000-agent games** with `tools/scenario.py`: it prints population,
deaths, unemployment, prices, the wage, money, loans, industry capacity and wealth inequality
every 100 steps.

### Layout

```
server.py                 local HTTP server + JSON API (see the docstring at the top)
simulation/agent.py       Agent class (properties, movement helper)
simulation/inventory.py   Inventory class
simulation/catalog.py     the 37 industries: sector, recipe, effects on needs, shelf life, defaults
simulation/economy.py     needs, consumption and trading rules
simulation/rules.py       Rules: every game-wide setting chosen on the setup screen
simulation/distributions.py  fixed / uniform / normal / skewed per-agent values
simulation/world.py       World: the box, agents, step loop, contacts, departures
simulation/banking.py     banks: minimum capital, deposits, loans, reserve/capital ratios, default, failure
simulation/modules/       pluggable behaviours (build.py: new assets from capital goods)
    needs.py              NeedsDecay: needs grow every step
    production.py         Production: industries (assets) worked by labour, using inputs
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
