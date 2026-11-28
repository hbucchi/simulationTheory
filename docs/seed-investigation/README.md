# Why do seeds give such different economies? (investigation, 2026-11-28)

## The question

With identical settings, seeds 11, 12 and 13 gave food at $743, $51 and $331 after 270 days, and
"inflation" of +316%, +39% and +361% (panel session 2). Which random draws cause this, and how do
we fix it?

## Method: vary one random stream at a time

Every random draw now comes from its own named stream (`World.STREAMS`), each seeded from the
world seed unless overridden with `World(..., stream_seeds={name: seed})`:

| Stream | What it decides |
|---|---|
| money | starting money per agent (only random with a tiered spread; the default is $3,000 each) |
| inventory | starting goods per agent (default: the same for everyone) |
| assets | which agents draw each industry's shares, and how many |
| owners | which 10% of agents become the starting owners |
| positions | where agents start on the map |
| traits | starting need levels, how fast each need grows, sleep recovery, walking speed |
| personality | lavishness, risk appetite, payout ratio |
| homes | who gets which starting house |
| luck | lucky businesses |
| shocks | random shocks and epidemics |
| run | everything day to day: who meets whom, how much a buyer buys, hiring ties, housing queue |

Because the streams are independent, two worlds can share every draw except one ("common random
numbers"). The investigation held all streams at seed 11 and changed one stream at a time to seeds
12–16. The spread of the outcomes (standard deviation across the 6 runs) shows how much that
stream alone matters. Script: [`vary_streams.py`](vary_streams.py), data:
[`vary_180.json`](vary_180.json), 200 agents, day 180. (This first experiment ran before the
treasury change, when leftover taxes were still spent automatically. The fix comparison below ran
with both versions of the ownership rule on the same, current code.)

| Stream varied alone | In need (sd) | Food price (sd) | Food price day 30 (sd) | CPI change (sd) | Capital built (sd) | Hired (sd) |
|---|---|---|---|---|---|---|
| money | 0 | 0 | 0 | 0 | 0 | 0 |
| inventory | 0 | 0 | 0 | 0 | 0 | 0 |
| **assets** | **0.110** | **265** | 189 | **1.31** | 4.1 | 6.4 |
| **owners** | **0.106** | **216** | **292** | **1.60** | **12.3** | 5.0 |
| positions | 0.031 | 80 | 105 | 0.50 | 5.6 | 5.8 |
| traits | 0.031 | 73 | 123 | 0.43 | 4.9 | 2.6 |
| personality | 0.015 | 37 | 47 | 0.43 | 2.3 | 6.2 |
| homes | 0.018 | 57 | 90 | 0.44 | 4.8 | 3.0 |
| luck | 0.013 | 95 | 0 | 0.25 | 3.0 | 4.2 |
| run (day to day) | 0.051 | 86 | 16 | 0.39 | **18.2** | **8.0** |
| ALL (a different seed) | 0.107 | 64 | 309 | 0.62 | 6.9 | 10.1 |

**Finding:** the starting ownership structure (`assets` + `owners`) is the dominant source. Either
draw alone moves deprivation as much as changing the whole seed, and moves food prices 3–4× more.
Day-to-day randomness matters most for how much capital gets built. Map positions and traits are
second-order. Starting money and goods draw nothing by default.

(With 6 values per row, each standard deviation is itself uncertain by roughly ±30%. The ranking
is clear; the exact numbers are not.)

## The mechanism: a lottery for market concentration

The old setup drew, for every industry separately, which 10% of agents (20 of 200) get its shares.
It then picked 20 owners separately and kept only the shares those owners had drawn. So the number
of owners per industry was random: on average 2, sometimes 1 (a monopoly), and when none of the
owners had drawn an industry it was split among all 20.

| Seed | Water | Grain | Food | Industries split among all 20 owners |
|---|---|---|---|---|
| 11 | 3 owners | 2 | 2 | meat, electricity, textiles, software |
| 12 | **1 owner (monopoly)** | 2 | 2 | herbs, spirits, medical devices |
| 13 | **1 owner (monopoly)** | 4 | **20** | coal, food, steel, housing |

Prices include a concentration markup and owners decide output, so a monopoly on water (the most
urgent need) gives a completely different economy from a three-way split. The seed wasn't adding
noise. It was choosing the market structure, industry by industry.

## The fix: balanced starting ownership

New rule `industry_owners` (default **3**, in Setup → World & People): every industry starts with
exactly that many owners in equal stakes. Owners take industries in turn, so each owner gets about
the same number of industries. The seed now decides *who* the owners are, not how concentrated each
market is. `0` restores the old lottery.

Result on the same code, 8 seeds, day 180 (script [`compare_fix.py`](compare_fix.py), data
[`compare_180.json`](compare_180.json)):

| | Lottery: mean | Lottery: sd | Balanced (3): mean | Balanced (3): sd | Spread cut by |
|---|---|---|---|---|---|
| Food price | $344 | ±$133 | $146 | **±$27** | 5× |
| CPI (100 = base day) | 50.2 | ±14.3 | 50.2 | **±2.9** | 5× |
| Real wage (days of living per day's work) | 1.29 | ±0.29 | 1.43 | **±0.04** | 7× |
| Private hiring (units/day) | 13.6 | ±5.4 | 9.9 | **±1.6** | 3× |
| Survival & security need | 78% | ±5.9 pts | 71% | ±5.5 pts | same |
| Capital built | 4.4 | ±3.1 | 8.1 | ±3.0 | same |

Prices, the price level and the real wage are now stable across seeds. Two spreads didn't shrink,
deprivation and capital built, because they come from the remaining streams (day-to-day randomness,
positions, traits). That is the kind of variation a teaching tool should keep, and show as a band
(panel item D-03), not hide.

## What remains random, and whether to fix it

- **Day to day (`run`)**: who meets whom, purchase sizes, hiring ties. It's the largest remaining
  source for investment. Reducing it would change how markets work, so it's better shown than
  removed: ensemble runs with fan charts (D-03).
- **Positions**: with a 600 px trade radius on a 1,024 px map, geography decides who can trade with
  whom. A fixed layout option (for example a grid, or clustered towns) would remove it if wanted.
- **Traits**: need rates and starting needs. These are the "people" of the economy; keep them.
