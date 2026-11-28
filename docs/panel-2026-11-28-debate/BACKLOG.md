# Backlog from the MBA team debate (session 2, 2026-11-28)

Source: [transcript.md](transcript.md). Fictional personas; real simulation data in [data/](data/).
Teams: **Wharton + Stanford** ("Markets & Evidence") against **Harvard + Trinity** ("Institutions & People").
Votes: 8 participants × 10 points. Type: **C** = critique (something wrong today), **R** = recommendation, **I** = idea.

## Ranked items

| Rank | ID | Type | Item | Votes (W+S / H+T) | Evidence from the session | What to build | Links to session 1 |
|---|---|---|---|---|---|---|---|
| 1 | D-13 | C + R | **Labour-force decomposition and calibrated need penalties** | 10 (4 / 6) | Labour capacity after penalties fell 100 → 57.8 by day 45 and → 22.8 by day 270. Only 0.4 units were withheld by agents with 6+ months covered. Seriously ill agents went from 0 to 62 (96 with no benefit). Unemployment read 0%. | A labour-force panel: capacity lost to illness, hunger and fatigue; own business; offered; hired; withheld. Calibrate penalty sizes. Add a "poverty trap" teaching scenario. | Diagnoses #7 (participation collapse); feeds #2 |
| 2 | D-03 | R | **Ensemble mode: fan charts and a labelled story seed** | 9 (9 / 0) | On the same settings, seeds 11/12/13 gave food at $743/$51/$331, inflation +316%/+39%/+361% and in-need 91/78/80%. The seed spread (13 pts) exceeded the light-touch policy effect (−1/+7 pts). | Run N seeds; show the median and a 10–90% band on key charts; let the instructor highlight one seed with its percentile. | Extends #3 (scenario comparison) |
| 3 | D-05 | C + R | **Make the residual treasury rule an explicit fiscal choice** | 8 (5 / 3) | With no benefit and no policies, the government still paid $2.80M in equal transfers and borrowed to $2.52M. Leftover treasury money, including bond proceeds, goes to public works and then to everyone equally. No setting shows this. | Leftover-money options: hold / repay debt / public works / equal transfers / sovereign fund. Default "hold, then repay". Bond proceeds never fund untargeted transfers unless chosen. A "where the money went" waterfall. | New |
| 4 | D-09 | R | **Anchored expectations and a visible real policy rate** | 8 (5 / 3) | Expectations plus the other new modules: +1,043% vs +316% (seed 11), +447% vs +39% (seed 12). The expectations half-life is about 13.5 days. Expected inflation sits at its 200% cap. The policy rate is 0% for 90 days, then jumps to the 20% ceiling, giving a real rate of about −90%. | A credibility setting (weight on the target). A half-life of months by default. Flag the cap. Show the real rate and a Taylor-principle warning. Consider a gradual Taylor rule instead of the on/off jump. | Calibrates #12 (expectations, now built) |
| 5 | D-14 | R | **Predict–run–explain loop** | 7 (5 / 2) | Both teams made confident predictions in public that the data then refuted (moral hazard; redistribution kills investment). | The student records a prediction before a run; the platform scores it over the seed ensemble and asks for an explanation, linked to the "why did this change?" explainer. | Uses #1 and #3; supports #8 |
| 6 | D-12 | R | **Counterfactual "ghost line"** | 6 (4 / 2) | The shock run and the baseline match exactly until day 90, so the difference is a clean effect: labour 3.1 vs 16.8, capital 3.4 vs 29.1, real wage +17%. Without it, the grain shortage looked like it did nothing (food prices fell during it). | Each shock or scenario re-runs the same seed without the change and plots the difference. | Supports #3, #5 |
| 7 | D-15 | R | **Case pack format, with an SME cockpit as the first case** | 6 (0 / 6) | The firms module tracked 272 firm entities in the institutions run; nobody could see them from a case's point of view. | A case pack: scenario, locked seeds, protagonist role, 2–3 decision points, prediction prompts, teaching note, distributional impact card. First case: an SME owner (P&L, cash runway, the bank). | Extends #4, #8 |
| 8 | D-01 | C + R | **Tiered deprivation index** | 5 (0 / 5) | "91% in need" at day 270 was mostly boredom (181 of 200) and health (167). Only 24 were hungry and 12 thirsty. | Three tiers: survival (thirst, hunger), security (health, shelter, sleep), wellbeing (energy, boredom). The headline uses the first two. | Part of #2 |
| 9 | D-06 | R | **Efficiency–equity frontier chart** | 4 (3 / 1) | Low profit tax: more capital on both seeds (+34%, ×3) and no deprivation gain. Redistribution: lower deprivation on both seeds (−24, −9 pts), investment −62% / +100%. | Each run is a dot (x = capital built, y = deprivation) with seed bands; the trade-off, or its absence, is visible. | New |
| 10 | D-02 | C | **Health is the dominant real deprivation** | 4 (0 / 4) | 167 of 200 in health need; 62 seriously ill by day 270, from 0 at day 45. | Find out why health goods don't reach people: who makes them, at what price, and whether the public service reaches anyone. | New; related to I-38 |
| 11 | D-11 | R | **Historical shock presets** | 4 (0 / 4) | The default epidemic (1% daily lethality for 30 days) gives a case fatality of about 26%: 55 deaths among 197 infected. That is Black-Death scale, not COVID scale. | Named presets (COVID-19, 1918 flu, Black Death, 1973 oil embargo, a 2008–10 banking crisis) with parameters, sources and expected effects. Lethality per infection. | Calibrates #5 (shocks, now built) |
| 12 | D-04 | C | **Ownership KPI counts dust shares** | 3 (0 / 3) | All seeds start with 20 owners. Seed 12 shows 192 "owners" by day 30, the smallest holding 0.02 of a share. | An owner needs a minimum stake (for example at least 1 share or 10% of wealth); report small shareholders as "savers with equity". | Part of #2 |
| 13 | D-10 | C + R | **Per-module KPIs and one-factor-at-a-time experiments** | 3 (3 / 0) | Four modules switched on together; the inflation spiral couldn't be pinned on any one. Contracts, severance and inheritance left no visible trace. | KPIs per module (contracts active, severance paid; estates passed on; firm entries, exits, bankruptcies). A helper that switches on one module per run on the same seeds. | Extends #6 |
| 14 | D-07 | C | **Approval rating calibration** | 2 (1 / 1) | Approval ended between 0.45 and 0.58 whether inflation was +39% or +1,043%. The inflation score hits zero at about 27%, and the employment score reads the broken unemployment rate. | A smooth inflation penalty (for example logarithmic); use D-13's labour measure; show the breakdown. | New |
| 15 | D-08 | R | **Long-horizon runs (5–10 years)** | 1 (1 / 0) | The investment argument in Round 4 couldn't be settled in 9 months. A 5-year, 200-agent run takes about 6–7 minutes today. | Speed work so multi-year runs are practical in class. | Depends on I-22 (speed) |

## Where the teams still disagree

- **Time horizon:** whether low profit taxes pay off over years (Kenji) or just leave empty capacity (Rory). Needs D-08.
- **Wellbeing in the headline:** Rory wants boredom and energy kept visible as quality of life; Priya wants them out of the headline. D-01 keeps them in a separate tier.
- **Platform vs course:** agreed on "cases first, on the platform"; the teams still disagree on the ratio.

## Parked from this session

| Idea | Raised by | Notes |
|---|---|---|
| Why seed 12 becomes deflationary | Sofia | Hypothesis: diffuse share ownership spreads demand. Not tested. |
| Population renewal (births, migration) | Aoife | Without it, any death shock is permanent (55 lost, never replaced). |
| Distributional impact card on every decision | Aoife | Folded into D-15 for now. |
| Pre-registered hypotheses for instructors' experiments | Sofia | Folded into D-14. |

## How this relates to the session-1 backlog

Session 2 diagnosed or calibrated several session-1 items rather than adding new themes:
- **#7 participation collapse** is now explained: penalties cut capacity in a poverty trap (D-13).
- **#2 trustworthy indicators** gains three concrete fixes: D-01, D-04, D-07.
- **#3 scenario comparison** gains ensembles (D-03) and counterfactuals (D-12).
- **#5 shocks** and **#12 expectations** exist now but need calibration (D-11, D-09).

**New themes from session 2:** the hidden fiscal rule (D-05), the efficiency–equity frontier (D-06), health supply (D-02) and the predict–run–explain loop (D-14).
