# MBA panel: brainstorming session on EconSim (full transcript)

**Date:** 2026-11-28 · **Model version:** commit `287bbdc` (branch `claude/nice-planck-80hu5l`)
**Format:** 8 MBA students (2 each from Wharton, Harvard Business School, Stanford GSB and
Trinity College Dublin), 10 rounds of discussion, then a vote. Facilitated by Claude.

> **Important for auditors:** the students are **fictional personas**, written by Claude to
> stress-test the product from different points of view. Their opinions are simulated, not real
> user research. Everything they react to is **real output** of the simulation: four scenarios run
> on the current code (200 agents, seed 11, 270 days). The raw data and the script are in
> [`data/`](data/). Every number quoted in the discussion comes from those files.

---

## The panel

| Seat | Name | Programme | Background | Lens they bring |
|---|---|---|---|---|
| 1 | Priya Raman | Wharton MBA | Ex-rates trader (investment bank) | Markets, prices, bonds, numbers that must add up |
| 2 | Marcus Delgado | Wharton MBA | Ex-research assistant at a central bank | Macro models, monetary policy, measurement |
| 3 | Elena Sokolova | Harvard Business School | Ex-strategy consultant | Case method, classroom flow, "so what?" |
| 4 | Daniel Okafor | Harvard Business School | Ex-hospital operations manager | Operations, health, public services |
| 5 | Kenji Watanabe | Stanford GSB | Ex-founder of an edtech start-up | Product, UX, onboarding, engagement |
| 6 | Sofia Alvarez | Stanford GSB | Behavioural economist turned data scientist | Behaviour, experiments, causal inference |
| 7 | Aoife Brennan | Trinity College Dublin MBA | Ex-financial-stability analyst at a central bank | Banking, credit, housing, debt sustainability |
| 8 | Rory Gallagher | Trinity College Dublin MBA | Ex-owner of an agrifood SME | Supply chains, small business, cash flow |

## What they used (real runs on the current code)

Before the session, each pair ran the same four scenarios on the platform (200 agents, seed 11,
9 months). Their key results:

| Scenario | Settings | Day 270: in need | Private hiring / public hiring (labour units/day) | CPI inflation (12 m) | Public debt | New capacity built | Deaths |
|---|---|---|---|---|---|---|---|
| **Baseline** | defaults | 91% | 11.7 / 0 | +165% | $2.54M | 45.1 | 0 |
| **Austerity** | no benefit, no spending policies, no bonds | 90% | 6.3 / 1.9 | +417% | $0 | 38.1 | 8 |
| **Welfare** | profit tax 35%, cash to poorest 30% ($60k/month), public health service ($40k/month) | 73% | 3.9 / 0.6 | +391% | $2.97M | 6.2 | 0 |
| **Sticky & tight** | prices 80% sticky, policy rate fixed at ~7.5%, no Taylor rule | 87% | 4.4 / 0 | +174% | $2.92M | 43.4 | 0 |

Other things they noticed in the runs:
- **Labour offered falls in every run:** about 52 units/day at day 45 → 8–32 by day 270.
- **The unemployment figure jumps** between 0% and 86% depending on whether public works are hiring.
- **Mortgages:** 0 in every scenario.
- **Inequality:** Gini 0.89–0.95.
- **Food costs $454–1,082 a unit**, while the wage is about $150 per unit of labour.
- **The Taylor rule** sits at its 20% ceiling from about month 4 in baseline, austerity and welfare.

---

## Round 1: First contact. What is it like to sit down and use this?

**Facilitator:** You've each had about two hours with the platform and run four scenarios. First impressions, good and bad.

**Kenji (Stanford):** Honestly? The corporate look is clean and the sidebar makes sense. But in the first ten minutes I had no idea what I was supposed to *do*. The setup screen has more settings than a Bloomberg terminal. I pressed "+1 month" and numbers moved. I didn't know if that was good or bad.

**Elena (HBS):** Same. In the case method you get a protagonist and a decision. Here I got a world. That's powerful for an instructor but intimidating for a student. Where's the question I'm meant to answer?

**Priya (Wharton):** I disagree a bit. I *liked* that it doesn't hold your hand. Markets don't. The Products table, with prices, producers, buyers to sellers and profit yield, is genuinely useful. I spent twenty minutes sorting by yield, watching which industries make money.

**Kenji:** You spent twenty minutes because you're a former trader. A marketing major will close the tab.

**Rory (TCD):** I ran a food business, so I went straight to food. Food at $820 a unit and the wage at $176 a day felt off. Then I realised a worker only sells half a unit of labour a day, so it's even worse. Nobody told me what a "unit" is.

**Daniel (HBS):** The agent cards are lovely, though. I opened a few: "thirsty: walks 30% slower", "too sick to work (14 of 180 days)". As someone who ran a hospital, that's the most human part. You *feel* the economy through one person.

**Sofia (Stanford):** Agreed. The individual view is the hook. The aggregate view is where I got lost. A dashboard number moves and I can't tell *why*.

**Marcus (Wharton):** My first reaction was suspicion, actually. CPI inflation of +165% in the baseline, with no money being printed? I'd need to understand the measurement before I'd teach with it.

**Aoife (TCD):** And I went to the Banks tab first: zero mortgages in every run. If housing exists and banks lend for houses, I want to see at least one mortgage.

**Facilitator:** So, summing up Round 1: the individual stories land, the controls are rich, but people don't know what to do, what units mean, or why numbers move. Ideas noted?

**Ideas captured:**
- **I-01** Guided scenarios ("missions") with a protagonist, a question and a learning objective.
- **I-02** A "why did this change?" explainer for every headline number.
- **I-21** Make units and purchasing power explicit: real wage, a day's wage in loaves of food, and so on.
- **I-25** "Learn mode": a plain-language tooltip and a teaching note on every metric and lever.

---

## Round 2: Do the labour-market mechanics behave as they should?

**Facilitator:** Look at the labour numbers. Baseline: unemployment 23%, then 0%, then 14%, then 0%, then 27%. Labour offered falls from 51.6 to 16.0.

**Marcus (Wharton):** That unemployment series is unusable for teaching. It flips because public works soak up idle workers on some days and not on others. A public-works job counts as "employed", fine, but then show me *private* employment, *public* employment and *self-employment* separately. The ILO definitions exist for a reason.

**Sofia (Stanford):** The bigger story is the participation collapse: 52 units offered on day 45, 16 on day 270, and 8 in austerity. People are leaving the labour force. In the real world we'd call them discouraged workers, but here I suspect it's mechanical. Their needs are high, the penalties cut their capacity, and specialisation makes them less able to do anything else.

**Rory (TCD):** Or they're making their own food and water. The autonomous production feature is clever: it's how you avoid mass starvation. But it competes with the labour market, and that's not obvious from the screen.

**Priya (Wharton):** Is it *wrong*, though? Subsistence farming in a recession is realistic. The Lewis model is literally that.

**Marcus:** It's realistic if the *student can see it*. Right now the unemployment rate says 0% while 91% of people are in need. That's a contradiction on the dashboard, and in class the first question will be "is the software broken?"

**Elena (HBS):** That's the teaching risk. If a metric contradicts intuition, we either explain it or we lose the room.

**Daniel (HBS):** The wage side looked sensible to me. It fell slowly, $176 → $152 over nine months, and never collapsed. "Sticky downward" matches what I saw managing nurses' pay.

**Marcus:** Agreed, the wage mechanics are the best-behaved part. Rises fast, falls slowly, as Bewley's interviews describe.

**Kenji:** Then put that on screen: "Wages are sticky downward: at most 0.2% a day". Make the rule visible.

**Ideas captured:**
- **I-03** Labour statistics done properly: private, public and self-employed (autonomous production) employment; participation rate; discouraged workers.
- **I-11** Investigate and fix the participation collapse (offered labour −70% to −85%), or explain it on screen if it's intended.
- **I-25** (again) Show each mechanism's rule where its result appears.

---

## Round 3: Prices and inflation. Believable?

**Facilitator:** CPI inflation: +165% (baseline), +417% (austerity), +391% (welfare), +174% (sticky). The policy rate sits at the 20% ceiling.

**Marcus (Wharton):** This is where I'd stop teaching with it. Three things.
1. Over the first year the CPI compares against **day 1** prices, which are formula prices, not market prices. Any adjustment in the first weeks reads as inflation.
2. Austerity has the *highest* inflation, which is the opposite of what we teach.
3. The Taylor rule hits 20% and stays there for six months with no effect. If a lever is pinned at its limit, the model is telling you the lever can't do the job.

**Priya (Wharton):** On point two, I'm not so sure it's wrong. In austerity, output collapses (private hiring 1.8 by day 90) and prices are cost-based with demand multipliers. Supply falls faster than demand, so you get stagflation. That's a legitimate lesson, if it's real.

**Marcus:** *If* it's real. We can't tell, because we can't decompose it. Is the inflation coming from wages, from the inventory factor, from the demand multiplier, or from the base period?

**Sofia (Stanford):** That's the causal explainer again. Every price should break down as base cost × demand × inventory × discounts, with today's values. The model already computes it; just show it.

**Rory (TCD):** And food at $454–1,082 with water at $21–329 is a wild range. In sticky-tight, water fell to $21 while food stayed around $850. Stickiness should make prices *move less*, but water swung tenfold.

**Aoife (TCD):** Probably the clearance and cash-flow discounts. A seller short of cash dumps water at 30% off, and the inventory factor moves 5% a day. Those per-seller discounts bypass the stickiness.

**Priya:** That's a feature, honestly. Fire sales exist. But label them.

**Elena (HBS):** I'd add one thing for the classroom: a "price of a basket" card, what a month of living costs versus a month's wage. That's the number students will remember.

**Ideas captured:**
- **I-04** Fix the inflation measurement: a chained monthly index, base period after a warm-up, annualised monthly rate alongside the 12-month rate.
- **I-05** Monetary policy guard-rails: show when the Taylor rule is pinned at its bounds; explain why (cost-push vs demand-pull).
- **I-02** (again) Price decomposition per product: cost, demand, inventory, discounts.
- **I-21** (again) A "cost of living vs wage" card.

---

## Round 4: Money, banking, bonds and public debt

**Facilitator:** Public debt reaches $2.5–3.0M in every scenario with bonds on, on a money supply of about $650k. Mortgages are 0 everywhere. Bond rates reach 33% in baseline and welfare.

**Aoife (TCD):** Debt at four times the money supply is possible in a real economy, since money recirculates, but the *speed* is the issue. Baseline: $683k by day 45, $2.5M by day 180. That's savers buying bonds with idle money, the treasury spending it, owners saving it again. The loop is right; the gain is too high. And debt sustainability isn't visible: I want **r versus g**, the interest rate against the growth rate. With bonds at 33% and growth near zero, this government is insolvent in any textbook.

**Priya (Wharton):** I liked the risk premium, though. Watching the bond rate go 1.7% → 2.9% → 27% → 33% is a great classroom moment. That's Greece 2010.

**Marcus (Wharton):** Except 27–33% is mostly the *policy rate* at 20%, not the risk premium. The central bank is fighting phantom inflation (Round 3) and pushing the government's borrowing costs through the roof. So the measurement bug spills into fiscal sustainability.

**Aoife:** Which is why the measurement fix is upstream of everything.

**Daniel (HBS):** Mortgages: zero is a red flag for anyone from Dublin. House prices follow the typical worker's income, but workers here barely earn, so nobody passes the 35% test. Either the house price floor (100× food, so $45–100k) is too high, or incomes are too low.

**Rory (TCD):** Or the first-time-buyer deposit: 10% of $50k is $5k, and most workers have under $100.

**Aoife:** Then the simulation is teaching that housing is unaffordable, which is a lesson too, but we should *see* the affordability ratio, not discover it by absence.

**Kenji (Stanford):** Product note: when something is zero all game, tell the user why. "No mortgages: 0 of 180 applicants passed the income test." One line.

**Ideas captured:**
- **I-31** Debt-sustainability panel: r vs g, debt/GDP path, interest burden; separate the risk premium from the policy rate.
- **I-13** Housing affordability calibration and a visible affordability ratio (price ÷ income, share of applicants who qualify).
- **I-33** "Why is this zero?" messages for features that never trigger (mortgages, foreclosures, luck).
- **I-30** Bank lending to firms, and a credit cycle (Aoife: "banks only lend to consumers and homebuyers today").

---

## Round 5: Inequality, ownership and mobility

**Facilitator:** Gini is 0.89–0.95 everywhere. Only 20–68 of 200 agents own anything in most runs, except in welfare, where all 200 became owners.

**Sofia (Stanford):** The welfare result is fascinating and nobody predicted it. Cash transfers to the poorest 30% gave everyone enough spare money to buy a sliver of a business. That's the "property-owning democracy" idea. But in-need was still 73%. Ownership without income doesn't fix need.

**Elena (HBS):** That's a perfect discussion question: "Why didn't universal ownership end poverty?" I'd build a case around it.

**Priya (Wharton):** But the profit tax at 35% cut new building to 6.2 assets, versus about 40 elsewhere. Textbook: taxing returns to capital lowers investment. I want students to *see* that trade-off on one screen: redistribution versus capital formation.

**Rory (TCD):** And the 10% starting ownership is harsh. Real economies have pension funds and index funds. Workers own capital indirectly. Maybe a "fund" asset class that pools small savings?

**Marcus (Wharton):** Gini 0.95 is beyond any real country's wealth Gini. The most unequal are around 0.85–0.90. So either the starting distribution is too extreme, or the dynamics concentrate too fast.

**Daniel (HBS):** Add the levers we don't have: inheritance tax (the user's idea), wealth tax, a progressive income tax. Right now taxes are flat.

**Sofia:** And a mobility view. Gini tells you the snapshot; a transition matrix tells you whether the poor ever move up. Luck exists (3% of businesses a year), but does it actually lift anyone?

**Ideas captured:**
- **I-14** Distribution tools: mobility matrix, wealth by decile over time, progressive income tax, wealth tax, inheritance tax.
- **I-15** Investment dashboard: capacity built, by industry and by who builds, next to the tax rates.
- **I-34** Pooled investment funds (pension or index fund) so small savers own capital indirectly.
- **I-35** Revisit the starting wealth distribution and the concentration speed (Gini ≥ 0.89 everywhere).

---

## Round 6: Predictable or surprising? Can students reason from cause to effect?

**Facilitator:** You ran four quite different policies. Did you predict the results?

**Sofia (Stanford):** Partly. Predicted: welfare reduces need (73% vs 91%); the profit tax lowers investment; austerity raises deaths (8 vs 0). Surprising: austerity had the highest inflation; in-need ends at 73–91% *whatever we do*; everyone becomes an owner under welfare. A good teaching model should be mostly predictable with a few intelligible surprises. Here the surprises outnumber the explanations.

**Marcus (Wharton):** The bigger problem is that policy barely matters for the headline outcome. In-need ends between 73% and 91% across four very different regimes. If the levers don't move the outcome, students learn that policy is pointless, which is the wrong lesson and probably a calibration issue.

**Priya (Wharton):** Counterpoint: maybe this economy is just stuck in a demand trap, and *no* tax-and-transfer setting gets it out within nine months. That's a real lesson too: structural problems need structural fixes.

**Marcus:** Then show me a scenario where it *does* get out, so students can contrast. Right now there's no "good" baseline to compare against.

**Elena (HBS):** That's the comparison feature. Run A and B with the same seed, side by side, and highlight where they diverge. In a classroom, the difference between two runs is the lesson, not the level of one run.

**Kenji (Stanford):** And lock the seed by default, so two teams with the same settings get the same economy. Otherwise every debate becomes "your run was lucky".

**Sofia:** Plus multiple seeds behind the scenes, to show the spread. "Welfare beats baseline in 9 of 10 seeds" is a strong statement; one run isn't.

**Aoife (TCD):** And a model health check: does the economy reproduce basic regularities like Okun's law, a Phillips-curve slope, and the consumption share of GDP? If it fails, the instructor should know before class.

**Ideas captured:**
- **I-06** A/B scenario comparison with the same seed, side-by-side charts and highlighted divergence.
- **I-07** Reproducibility: seed locking, saved run configurations, multi-seed spread ("9 of 10 seeds").
- **I-12** Policy-sensitivity audit: make sure the levers move the outcomes, and include a reference "healthy economy" scenario.
- **I-26** A model health page: stylized facts (Okun, Phillips, consumption share, wage share) checked automatically.

---

## Round 7: Using it in a classroom: roles, flow, debrief

**Facilitator:** Imagine a 90-minute session. How would you run it?

**Elena (HBS):** Turn-based. Each "turn" is one month. Teams hold roles (central bank, finance ministry, a bank, an industrialist, a workers' union) and each team controls only its levers. After each month, a two-minute debrief. After 12 turns, the full debrief.

**Kenji (Stanford):** That's multiplayer with permissions. Big build, but it's the killer feature. Right now everyone controls everything, so it's a sandbox, not a game.

**Priya (Wharton):** Hidden information matters too. The central bank shouldn't see next month's fiscal plan. Real policy is a coordination problem.

**Daniel (HBS):** And shocks. As an instructor, I'd want to inject a drought, a bank failure, a pandemic that raises the health need, an oil shock. Then watch each team react.

**Rory (TCD):** Supply shocks especially. Destroy 30% of the grain capacity and see who adapts.

**Marcus (Wharton):** A shock library with known textbook effects doubles as a validation tool. If a negative supply shock *doesn't* raise prices, something's broken.

**Elena:** For the debrief, an automatic timeline: "Day 92: the central bank hit 20%. Day 135: debt passed the limit. Day 180: in-need passed 80%." Plus the five charts that matter. Instructors don't have time to dig.

**Sofia:** And export everything to CSV, so the analytics-minded students can run their own regressions.

**Kenji:** Disagree on priority. Exports are table stakes but nobody's *learning* happens in Excel. The timeline and the "why" explainer do the teaching.

**Sofia:** Learning happens in Excel at Stanford, Kenji.

*(laughter)*

**Ideas captured:**
- **I-08** Role-play mode: teams with role-specific levers, turn-based months, hidden information.
- **I-23** Instructor console: pause, lock settings, inject events.
- **I-24** A shock library (drought, oil shock, pandemic, bank failure, capacity destruction) with expected textbook effects.
- **I-10** An auto-generated debrief: an event timeline plus key charts.
- **I-27** CSV and Excel export of every series and every agent.

---

## Round 8: Agents and behaviour. Do they feel like people?

**Facilitator:** Agents have needs, penalties, personalities (frugal–lavish), specialisation, autonomous production, luck. How convincing is that?

**Daniel (HBS):** The needs and penalties are the strongest part. Illness taking six months to kill, shelter affecting health: these are real mechanisms. But in-need at 91% with only 0–8 deaths means people live for months in hardship and the simulation never tells you who or where.

**Sofia (Stanford):** Behaviourally it's thin, but the frugal–lavish slider is a good start. Next I'd add: present bias (saving vs spending now), loss aversion (selling assets at a loss), and herding (investing where others invest). Each gives you a classroom experiment.

**Priya (Wharton):** Careful: more sliders, more confusion (Round 1). Add them, but behind "advanced".

**Rory (TCD):** The purchasing department fix was clearly needed. Businesses should behave like businesses. I'd go further: **firms as real entities**, with balance sheets, bankruptcy, and new firms starting up. Right now ownership is "shares of an industry", which is abstract.

**Aoife (TCD):** Agreed. Bankruptcy and firm entry/exit are where credit, unemployment and productivity meet. And creative destruction, Schumpeter, is a core MBA concept.

**Kenji:** Specialisation (up to 10× skill) is great, but invisible. Show a skills distribution chart: "the share of agents who are specialists".

**Marcus (Wharton):** Something no one has said: **expectations**. Agents react to today's prices only. Without expected inflation there's no credibility, no forward guidance, no anchoring. You can't teach modern central banking without it.

**Priya:** That's a big model change.

**Marcus:** It's *the* model change for monetary policy. But I'll concede it's not top-10 for a first-term class.

**Ideas captured:**
- **I-19** Firms as entities: balance sheets, bankruptcy, start-ups (entry and exit).
- **I-20** More behavioural traits (present bias, loss aversion, herding), behind "advanced".
- **I-18** Inflation expectations: how anchored they are, forward guidance.
- **I-36** Hardship map and roster: who is in need, where, for how long.
- **I-37** A skills and specialisation distribution view.

---

## Round 9: The economy's structure. What's missing?

**Facilitator:** From an MBA economics syllabus: what's missing entirely?

**Priya (Wharton):** Foreign trade. An open economy with an exchange rate, imports and exports. Half of macro is open-economy macro, and Ireland is the poster child.

**Aoife (TCD):** Thank you. Ireland's economy is a case study in FDI, trade and tax policy. I'd love a "small open economy" scenario.

**Rory (TCD):** Industrial policy levers: subsidies and investment tax credits. The facilitator mentioned they're planned. In Ireland we used them heavily (IDA grants, 12.5% corporate tax).

**Daniel (HBS):** Public services as real production: hospitals and schools staffed by public employees, not just "relief of a need". Then you see the trade-off between private and public employment.

**Kenji (Stanford):** Visualising the supply chain itself, a flow diagram of who sells to whom. The purchasing-department story only made sense when the facilitator explained it. A Sankey chart of goods flowing between layers would show it in five seconds.

**Marcus (Wharton):** Externalities: pollution from coal and oil, carbon pricing. Every MBA covers it now.

**Sofia (Stanford):** Competition policy: a concentration index per market (already computed) plus antitrust levers.

**Elena (HBS):** I'll be the contrarian: none of this should be top-10. We haven't fixed what's on screen (the measurement, the explainer, the comparison). New modules on a shaky base multiply the confusion. First make what exists explainable and trustworthy.

**Priya:** I partly agree. Fix the base first, but keep trade as #11.

**Ideas captured:**
- **I-17** Foreign trade and the exchange rate (a small open economy scenario).
- **I-16** Industrial policy levers: subsidies, investment tax credit.
- **I-38** Public services as real production (public employees producing services).
- **I-29** A supply-chain flow diagram (Sankey of goods between layers).
- **I-39** Externalities and carbon pricing.
- **I-40** Competition policy: concentration index per market, antitrust levers.

---

## Round 10: Synthesis and vote

**Facilitator:** We have 40 ideas. Each of you has 10 points to spread as you like, then we argue about the result.

**Votes cast:**

| Idea | Priya | Marcus | Elena | Daniel | Kenji | Sofia | Aoife | Rory | **Total** |
|---|---|---|---|---|---|---|---|---|---|
| I-02 "Why did this change?" explainer | 2 | 2 | 2 | 1 | 3 | 3 | 1 | 2 | **16** |
| I-04 + I-03 + I-21 Trustworthy indicators (inflation, labour stats, real wage) | 2 | 4 | 1 | 1 | 1 | 2 | 2 | 1 | **14** |
| I-06 + I-07 Scenario comparison with locked seeds | 1 | 2 | 2 | 1 | 1 | 2 | 1 | 1 | **11** |
| I-08 Role-play turn-based mode | 1 | 0 | 3 | 2 | 3 | 0 | 0 | 1 | **10** |
| I-23 + I-24 Instructor console and shock library | 1 | 1 | 1 | 2 | 0 | 0 | 2 | 2 | **9** |
| I-12 Policy-sensitivity audit and a healthy reference scenario | 1 | 1 | 0 | 1 | 0 | 2 | 1 | 1 | **7** |
| I-11 Participation collapse fix | 0 | 0 | 0 | 1 | 0 | 1 | 1 | 1 | **4** |
| I-01 + I-25 Missions and learn mode | 0 | 0 | 1 | 0 | 2 | 0 | 0 | 0 | **3** |
| I-10 Auto debrief | 0 | 0 | 0 | 1 | 0 | 0 | 1 | 0 | **2** |
| I-31 Debt sustainability panel | 1 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | **2** |
| I-19 Firms as entities | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | **2** |

**Kenji (Stanford):** I'm surprised missions and learn mode only got 3. Onboarding is why products die.

**Elena (HBS):** Because role-play *is* the onboarding for a class. The instructor gives the mission; the software gives the roles.

**Marcus (Wharton):** I want to argue the indicators should be #1, not #2. If the inflation number is wrong, the explainer explains a wrong number.

**Sofia (Stanford):** But the explainer will *expose* the wrong number. Decomposing the CPI shows the base-period problem at once. They're complementary; build the measurement fix first in time, keep the explainer first in value.

**Marcus:** I can live with that if the measurement fix ships in the same release.

**Aoife (TCD):** I'd merge debt sustainability into the indicators item. It's a measurement and visibility problem too.

**Rory (TCD):** Then put participation, and the "why is this zero?" messages, with the policy-sensitivity audit. All three are "the mechanics produce something weird and nobody can tell why".

**Elena:** Agreed. That gives us room for missions and the debrief, which together are the classroom wrapper.

**Facilitator:** Proposed final top 10, merging as discussed. Any objections?

**Priya:** Firms as entities should be #11. Note that.

**Marcus:** Expectations as #12, noted with protest.

*(agreement)*

---

## Outcome

The final **top 10 (backlog)** and the **parked ideas** are in [`BACKLOG.md`](BACKLOG.md).
