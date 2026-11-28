# MBA panel, session 2: the team debate (full transcript)

**Date:** 2026-11-28 · **Model version:** commit `69d36a5` (branch `claude/nice-planck-80hu5l`), which includes the
merged shocks, firms, inflation expectations, inheritance and labour-contract modules
**Format:** the same 8 MBA students as [session 1](../panel-2026-11-28/transcript.md), now split into two
teams: **Wharton + Stanford** against **Harvard + Trinity College Dublin**. 8 debate rounds, each on a motion,
then closing statements and a vote on up to 15 ideas, critiques and recommendations. Facilitated by Claude.

> **Important for auditors:** the students are **fictional personas** written by Claude. Their
> profiles are built from what each school says it looks for in candidates (sources at the end),
> which is a stereotype of a school, not a description of any real person. Their opinions are
> simulated, not user research. **Every number they quote is real**: it comes from runs of the
> current code (200 agents, 270 days) saved in [`data/`](data/), with the scripts that made them.
> Where the facilitator ran something during a round, the transcript says so and names the file.

---

## Contents

- [The panel and where each profile comes from](#the-panel-and-where-each-profile-comes-from)
- [Rules of the debate](#rules-of-the-debate)
- [Evidence pack](#evidence-pack)
- [Round 1: Is "91% in need" a crisis or a measurement artefact?](#round-1)
- [Round 2: Is one run just an anecdote?](#round-2)
- [Round 3: Is "small government" an illusion in this model?](#round-3)
- [Round 4: Profit-tax cuts against redistribution](#round-4)
- [Round 5: Do inflation expectations make the model more realistic?](#round-5)
- [Round 6: Is the shock library ready for the classroom?](#round-6)
- [Round 7: Do people stop working because the state pays them?](#round-7)
- [Round 8: Platform or course?](#round-8)
- [Round 9: Closing statements](#round-9)
- [Round 10: The vote](#round-10)
- [Appendix A: The concepts behind the arguments](#appendix-a)
- [Appendix B: Sources for the personas](#appendix-b)

---

## The panel and where each profile comes from

### What each school says it looks for

| School | What its admissions material emphasises | How that shows in the personas |
|---|---|---|
| **Wharton** | The application guide asks what you will contribute to the classroom, the community and your career, and the office describes a "read to admit" approach. Third-party guides describe a Team-Based Discussion in the interview. Recent classes are heavy in consulting (about 28–31%) and private equity/venture capital (about 15%), with about a third from STEM. It is widely known for finance and rigorous quantitative training. | Numbers first. Prices, rates and balance sheets must reconcile. They argue in structured teams and want models calibrated to data. |
| **Stanford GSB** | Three criteria: **intellectual vitality** (seeking new knowledge, a willingness to *test and challenge assumptions*, developing new ideas), **demonstrated leadership potential** (creating impact or change) and **personal qualities and contributions**. It says there is no "typical" student. | They treat every claim as a hypothesis to test. They want falsifiable predictions, experiments and a product that scales. Founder energy. |
| **Harvard Business School** | Historically: a **habit of leadership**, **analytical aptitude and appetite**, and **engaged community citizenship**. Since a 2023 change in admissions leadership the wording is **business-minded, leadership-focused, growth-oriented**. Teaching is by the case method. | Every model needs a protagonist and a decision. They care about people, organisations and what a leader does on Monday morning. |
| **Trinity College Dublin** | A one-year full-time MBA with a deliberately small class (45–50) and at least 3 years of work experience. Selection weighs professional experience, academic achievement and **business ethics**, plus GMAT, referees and an interview. Its mission is to **"Transform Business for Good"**, and the programme includes a Strategic Company Project with optional Social Enterprise and Scaling projects. | A small open European economy and stakeholder capitalism. Ethics and who bears the cost. Real small firms and real banks. |

### The two teams

**Team "Markets & Evidence" (Wharton + Stanford)**

| Name | School | Background | What they push for |
|---|---|---|---|
| Priya Raman | Wharton | Ex-rates trader | Incentives, prices, fiscal arithmetic |
| Marcus Delgado | Wharton | Ex-research assistant at a central bank | Monetary policy, expectations, measurement |
| Kenji Watanabe | Stanford GSB | Ex-founder of an edtech start-up | Product, scale, speed, onboarding |
| Sofia Alvarez | Stanford GSB | Behavioural economist turned data scientist | Experiments, replication, causal inference |

**Team "Institutions & People" (Harvard + Trinity)**

| Name | School | Background | What they push for |
|---|---|---|---|
| Elena Sokolova | Harvard | Ex-strategy consultant | Case method, decisions, classroom flow |
| Daniel Okafor | Harvard | Ex-hospital operations manager | Health, operations, public services |
| Aoife Brennan | Trinity | Ex-financial-stability analyst at a central bank | Banking, credit, debt, stress tests |
| Rory Gallagher | Trinity | Ex-owner of an agrifood SME | Small business, supply chains, cash flow, ethics |

To keep the teams from becoming strawmen, every persona is written to concede at least one
point to the other side when the evidence goes against them. Where that happened it is marked
**[concession]**.

---

## Rules of the debate

1. Each round has a **motion**. One team proposes it, the other opposes it.
2. **Openings:** one speaker from each side, then **cross-examination** (questions across the table).
3. **Evidence check:** the facilitator reads the real numbers, or runs something new, and says
   whether the evidence **supports**, **refutes** or is **mixed** on each side's claims.
4. **Rebuttals and concessions**, then the round's **items** are logged (D-01 … D-15). Each item is
   an **Idea**, a **Critique** (something wrong today) or a **Recommendation** (a concrete change).
5. A team may ask for a replication on another seed. The facilitator runs it if it takes under
   five minutes.

---

## Evidence pack

All runs use 200 agents for 270 days, with seed 11 unless marked. Rows every 30 days are in
`data/d_<name>.json`. Values below are at day 270.

| Run | Settings | In need | Capital built | Gini (wealth) | Approval | Inflation (12 m) | Wage | Food price | Labour offered/day | Public debt |
|---|---|---|---|---|---|---|---|---|---|---|
| `baseline_s11` | defaults | 91% | 29.1 | 0.94 | 0.50 | +316% | $136 | $743 | 16.8 | $2.59M |
| `baseline_s12` | defaults, seed 12 | 78% | 3.7 | 0.89 | 0.46 | +39% | $99 | $51 | 39.0 | $3.32M |
| `baseline_s13` | defaults, seed 13 | 80% | 45.2 | 0.94 | 0.49 | +361% | $163 | $331 | 29.5 | $3.03M |
| `light_touch` | profit tax 5%, no benefit, no spending policies | 90% | 38.9 | 0.96 | 0.49 | +103% | $129 | $486 | 11.6 | $2.52M |
| `light_touch_s12` | same, seed 12 | 85% | 11.1 | 0.90 | 0.45 | +117% | $163 | $53 | 25.2 | $3.23M |
| `stakeholder` | profit tax 35%, cash to poorest 30% ($60k/month), public health service ($40k/month), 90-day contracts, 50% severance | 67% | 11.1 | 0.90 | 0.52 | +451% | $134 | $559 | 31.7 | $2.70M |
| `stakeholder_s12` | same, seed 12 (run during Round 4) | 69% | 7.4 | 0.82 | 0.58 | +125% | $175 | $66 | 19.5 | $3.20M |
| `institutions` | firms, inflation expectations, inheritance, 90-day contracts, 50% severance | 87% | 22.2 | 0.93 | 0.49 | +1,043% | $309 | $2,010 | 18.4 | $2.22M |
| `institutions_s12` | same, seed 12 (run during Round 5) | 71% | 15.3 | 0.89 | 0.53 | +447% | $335 | $200 | 36.9 | $3.21M |
| `shocks` | defaults + epidemic at day 90 + 50% grain and water shortage for 60 days from day 180 | 90% | 3.4 | 0.94 | 0.46 | +329% | $171 | $796 | 3.1 | $1.22M |

In every run the policy rate is **0% for the first 90 days and then jumps straight to its 20% ceiling**
by day 120, where it stays (only the seed-12 baseline falls back to 0%, at day 270). The Taylor rule
behaves like an on/off switch. Mortgages were 0 in every run.

Diagnostics the facilitator ran during the session:
- `data/sp_baseline.json`, `data/sp_light.json`: government spending by category (Round 3).
- `data/pa_baseline.json`, `data/pa_light.json`: where the labour goes (Round 7).
- The needs breakdown in Round 1 came from a one-off script on the same seed-11 baseline (the counts are quoted in the round).

---

<a id="round-1"></a>
## Round 1: Is "91% in need" a crisis or a measurement artefact?

**Motion:** *"The 91% 'in need' headline is a measurement artefact, not a welfare crisis."*
**Proposing:** Markets & Evidence (Priya leads) · **Opposing:** Institutions & People (Daniel leads)

**Priya (Wharton), opening:** Last session we spent an hour agonising over "91% in need". So I looked at what it counts. An agent is "in need" if *any one* of seven needs is above the threshold. On the seed-11 baseline at day 270, here is who is in need of what:

| Need | Agents above the threshold (of 200) |
|---|---|
| Boredom | 181 |
| Health | 167 |
| Energy | 122 |
| Hunger | 24 |
| Sleep | 12 |
| Thirst | 12 |
| Shelter | 6 |

The headline is driven by boredom. Only 24 agents are hungry and 12 thirsty, and **nobody died** in this run. We'd be telling a room of executives that nine in ten people are in crisis because they're bored. In a trading book you'd call that a broken risk metric: one input dominates and nobody knows it.

**Daniel (HBS), opening:** I'll take your table and read the second row. **167 of 200 are in health need.** I ran wards. When 84% of a population has a health problem, that is the crisis, whatever the headline says. Boredom is noise, I'll give you that. But don't throw out the one row that matters along with it.

**Cross-examination**

**Elena (HBS) → Priya:** Would you show a CEO a headcount report that lumps "skipped lunch" together with "on long-term sick leave"?

**Priya:** No, which is exactly my motion. Split it.

**Marcus (Wharton) → Daniel:** If 167 are unwell, why is nobody dying?

**Daniel:** Because illness only kills after 180 days at the critical level. The clock is running. We're looking at a nine-month film and complaining that the second act has no bodies in it. Facilitator, how many are seriously ill?

**Facilitator (evidence check):** On the same run, **62 agents have health at 0.8 or above** at day 270, which is the warning level where penalties start. At day 45 the number was **0** (file `data/pa_baseline.json`). So the sickness built up over the run, and the 180-day death clock started for some of them during it.

**Sofia (Stanford):** **[concession]** Then I'll give Daniel this: health isn't just one need among seven. It's the transmission channel. Sick agents work less, so it's the need that feeds back into the economy. Boredom doesn't.

**Rory (TCD):** And I won't fully let boredom go. In Ireland we'd call it quality of life. A pub closing in a village is not nothing. But it shouldn't sit in the same number as thirst.

**Verdict:** Evidence **mixed, both sides partly right**. The headline really is inflated by boredom (the proposition's point). The health deprivation is real and growing (the opposition's point).

**Items logged**
- **D-01 Critique + Recommendation: tiered deprivation index.** Replace the single "in need" with three tiers: *survival* (thirst, hunger), *security* (health, shelter, sleep) and *wellbeing* (energy, boredom). The headline shows survival and security, with wellbeing reported separately.
- **D-02 Critique: health is the dominant real deprivation.** Investigate why health goods don't reach people (who makes them, at what price, and whether the public health service reaches anyone).

---

<a id="round-2"></a>
## Round 2: Is one run just an anecdote?

**Motion:** *"One run is an anecdote: the platform must never show a single seed as 'the result'."*
**Proposing:** Markets & Evidence (Sofia leads) · **Opposing:** Institutions & People (Elena leads)

**Sofia (Stanford), opening:** Same settings, three random seeds:

| | Seed 11 | Seed 12 | Seed 13 |
|---|---|---|---|
| Food price, day 270 | $743 | $51 | $331 |
| Inflation (12 m) | +316% | +39% | +361% |
| Capital built | 29.1 | 3.7 | 45.2 |
| In need | 91% | 78% | 80% |
| Policy rate at day 270 | 20% | 0% | 20% |

Seed 12 isn't a slightly different economy. It's a *different regime*: deflation, with a zero policy rate. And here is the worrying part: the gap in "in need" between seeds is **13 points**. The effect of the whole light-touch policy package on that same number is **−1 point on seed 11 and +7 on seed 12**. **The seed matters more than the policy.** If you teach from one seed, you are teaching noise with a confident face.

**Elena (HBS), opening:** History has a sample size of one. Ireland didn't get to rerun 2008 with a different seed. A case is a single realisation: a protagonist, a decision and consequences nobody could fully predict. Path dependence *is* the lesson. "Why did seed 12 go deflationary?" is a fantastic ninety-minute discussion. If you average it into a fan chart, the story disappears.

**Cross-examination**

**Kenji (Stanford) → Elena:** So the instructor picks seed 12 and tells the class "this is what light-touch policy does"?

**Elena:** No. They pick seed 12 and say "this happened; what would you have done?" That's different.

**Kenji:** Only if they *know* it's an outlier. Today nothing tells them.

**Aoife (TCD) → Sofia:** In financial stability we don't stress-test the average. We stress-test the tail, because that's what kills banks. Isn't the tail what matters?

**Sofia:** Then show the tail *as* a tail. The Bank of England publishes its inflation forecast as a fan chart. It doesn't pick one path and call it the forecast.

**Aoife:** **[concession]** ...Fine, that's a precedent I respect. A fan chart with a highlighted path is something a central banker would recognise.

**Marcus (Wharton):** Something else in that table bothers me. Facilitator, seed 12 ends with **196 "owners"**, seed 11 with 45 and seed 13 with 38. All three start with exactly 20. What happened?

**Facilitator (evidence check):** All three seeds start with **20 owners** holding 813 asset shares between them. By day 30, seed 12 has **192 agents holding shares**, but the smallest holdings are **0.02 of a share**. On seed 13 it is still 20 owners, the smallest holding 3.7 shares. So the "owners" figure counts dust: any agent that bought a sliver of a business with spare savings.

**Rory (TCD):** An agent with 0.02 of a timber mill isn't an owner. It's a saver. If I put €50 into an index fund, I don't run a company.

**Sofia:** And that may be the reason seed 12 diverged: wider ownership spreads dividend income, so demand is spread out too. But that's a hypothesis, not a finding. We haven't tested it.

**Verdict:** Evidence **supports the proposition** on variance: the spread between seeds is bigger than some policy effects. It **supports the opposition** on teaching value: one chosen, well-explained path is a good teaching device. Ownership is mis-measured.

**Items logged**
- **D-03 Recommendation: ensemble mode.** Run N seeds and show the median with a 10–90% band (fan chart) on each key chart. The instructor can mark one "story seed" path, labelled with where it sits in the distribution ("seed 12: lowest-inflation 10% of runs").
- **D-04 Critique: the ownership KPI counts dust.** Define an owner by a materiality threshold (for example at least 1 share, or at least 10% of the agent's wealth) and report small shareholders separately as "savers with equity".
- *Parked question:* why seed 12 becomes deflationary (hypothesis: diffuse share ownership). Not tested this session.

---

<a id="round-3"></a>
## Round 3: Is "small government" an illusion in this model?

**Motion:** *"The model's 'small government' is an illusion: it quietly runs a debt-financed basic income."*
**Proposing:** Markets & Evidence (Priya leads) · **Opposing:** Institutions & People (Aoife leads)

**Priya (Wharton), opening:** I set up the most libertarian economy the settings allow: profit tax 5%, no unemployment benefit, no spending policies. After nine months, **public debt was $2.52M**, almost the same as the baseline's $2.59M. So I asked the facilitator where the money went.

**Facilitator (evidence check, files `data/sp_light.json` and `data/sp_baseline.json`):** Government spending over 270 days:

| Category | Baseline | Light touch |
|---|---|---|
| Transfers (paid equally to everyone) | $3.81M | **$2.80M** |
| Public works (hiring idle labour) | $0.71M | $0.73M |
| Unemployment benefit | $0.30M | $0 |
| Interest on bonds | $0.14M | $0.12M |
| Debt repaid early | $0.49M | $0.19M |

The rule behind this is in `simulation/labor.py`. With a balanced budget, whatever is left in the treasury each day, including money raised by **selling bonds to savers**, first hires idle labour as public works. Anything still left is **paid out equally to every agent**. No setting on the Government tab says this.

**Priya:** There it is. The government borrows from the rich, at a 33% bond rate, and hands it out equally to everyone. That's a universal basic income financed by debt, and the player **cannot switch it off**. It's also why debt hits the limit in every run, and why the bond rate sits at 33%: the 20% policy rate, plus the spread, plus a risk premium that climbs as debt nears the limit. You can't teach fiscal policy when the most important fiscal rule is hidden.

**Aoife (TCD), opening:** Two different things are mixed up here. **Automatic stabilisers** are real and good: when the economy falls, spending holds up without anyone voting for it. Ireland had them in 2008 and they kept people fed. **[concession]** But I agree with Priya on the specific rule. No finance ministry I know borrows on the bond market to fund *untargeted* equal payments by default. A surplus goes into a fund or pays down debt. The Irish government literally set up a reserve fund for this.

**Cross-examination**

**Elena (HBS) → Priya:** Your problem is that it's hidden, or that it exists?

**Priya:** Both, but mostly hidden. If a student chooses a UBI, great: that's a policy. If the engine chooses it for them, it's a bug.

**Daniel (HBS) → Priya:** Last session the austerity run had **8 deaths**. Every other run had none. What if those transfers are what keeps people alive?

**Priya:** Then the lesson is "transfers save lives", and the student should learn it by switching them on, not because the engine does it silently.

**Marcus (Wharton):** And notice what this does to the bond story. Savers' money goes into bonds, then the bond money is handed back out as transfers. It's a recycling loop. Crowding out can't happen in the textbook way because the money never sits still.

**Verdict:** Evidence **supports the proposition**: the rule is real, large and invisible. The opposition's point stands that some automatic support prevents deaths (session 1's austerity run). That's an argument for making it a choice, not for deleting it.

**Items logged**
- **D-05 Critique + Recommendation: make the residual treasury rule an explicit fiscal choice.** Options on the Government tab for what happens to money left over: *hold it*, *repay debt*, *public works*, *equal transfers*, *sovereign fund*. The default is "hold, then repay debt". Bond proceeds must never fund untargeted transfers unless the player chooses it. Add a "where the money went" waterfall chart to the Government tab.

---

<a id="round-4"></a>
## Round 4: Profit-tax cuts against redistribution

**Motion:** *"Cutting profit tax does more good than redistribution."*
**Proposing:** Markets & Evidence (Priya and Kenji) · **Opposing:** Institutions & People (Rory and Daniel)

**Priya (Wharton), opening:** On both seeds, low profit tax builds more capital. Seed 11: **38.9 units vs 29.1** in the baseline (+34%). Seed 12: **11.1 vs 3.7**, three times as much. Capital is what makes an economy richer. Redistribution divides the pie; investment grows it.

**Rory (TCD), opening:** Capital built *for whom*? Light touch on seed 11: 38.9 units of capital and **90% still in need**. On seed 12 it's worse than doing nothing: **85% vs 78%**. My farm never sold more because more farms opened down the road. It sold more when customers had money in their pockets. More capacity with no customers is just more empty sheds.

**Daniel (HBS):** And the stakeholder package, with redistribution plus a public health service, cut deprivation from **91% to 67%** on seed 11. That's 48 more people out of need. And wealth inequality fell from 0.94 to 0.90.

**Cross-examination**

**Kenji (Stanford) → Rory:** You're judging a twenty-year asset on nine months. Factories take time to pay off. Of course deprivation hasn't fallen yet.

**Rory:** Then run it for five years and show me.

**Facilitator:** A 5-year run of 200 agents takes about 6–7 minutes on this machine. That's over the five-minute rule for this session, so I'm logging it as an item rather than running it.

**Sofia (Stanford):** I have to object to my own side's framing, and to the opposition's evidence. The stakeholder result is **one seed**. Facilitator, I'm requesting a seed-12 replication.

**Facilitator (evidence check, run during the round, file `data/d_stakeholder_s12.json`):**

| | Seed 11 | Seed 12 |
|---|---|---|
| In need: baseline → stakeholder | 91% → 67% (**−24 pts**) | 78% → 69% (**−9 pts**) |
| Gini: baseline → stakeholder | 0.94 → 0.90 | 0.89 → 0.82 |
| Capital built: baseline → stakeholder | 29.1 → 11.1 (**−62%**) | 3.7 → 7.4 (**+100%**) |
| Approval: baseline → stakeholder | 0.50 → 0.52 | 0.46 → 0.58 |

**Sofia:** **[concession]** So the deprivation gain **replicates**, smaller on seed 12 but the same direction. The "redistribution kills investment" story, which is *our* side's story, **doesn't replicate**: investment fell on one seed and doubled on the other. I'm not going to defend a claim that flips sign between two seeds.

**Priya:** Two seeds isn't proof either way.

**Sofia:** Agreed. But it's two more than we had for the claim you opened with.

**Elena (HBS):** Can I raise the approval numbers? Every policy we tried ends with approval between **0.45 and 0.58**. Inflation was 39% in one run and 1,043% in another. A politician who can't lose votes over thousand-percent inflation isn't a politician.

**Facilitator (evidence check, `simulation/government.py`):** Approval targets 45% wellbeing + 25% employment + 15% inflation score + 15% tax score, smoothed. The inflation score is `1 − |inflation − target| / 0.25`, so it reaches **zero at about 27% inflation**. Every run is above that, so the inflation part is always zero and can't tell 39% from 1,043%. The employment part uses the unemployment rate, which reads 0% for most of every run (see Round 7), so it is nearly always at its maximum. In practice only wellbeing and taxes move approval.

**Marcus (Wharton):** So approval is two numbers with a lot of decoration.

**Verdict:** Evidence **refutes** the proposition as stated. Lower profit tax builds more capital on both seeds, but with no deprivation gain in nine months. Redistribution lowers deprivation on both seeds, and its effect on investment is **inconclusive**. The time horizon is too short to settle Kenji's point.

**Items logged**
- **D-06 Recommendation: efficiency–equity frontier chart.** Plot each run as a dot (x = capital built, y = deprivation), with seed bands, so the trade-off, or its absence, is visible at a glance.
- **D-07 Critique: approval rating calibration.** The inflation score saturates at about 27%, and the employment score reads a broken unemployment rate. Use a smooth penalty for inflation (for example logarithmic), use the labour-force measure from D-13, and show the breakdown on the card.
- **D-08 Recommendation: long-horizon runs.** Runs of 5–10 years at a usable speed, so investment arguments can be settled. This depends on speed work (session 1's I-22).

---

<a id="round-5"></a>
## Round 5: Do inflation expectations make the model more realistic?

**Motion:** *"Switching on inflation expectations makes the model more realistic."*
**Proposing:** Markets & Evidence (Marcus leads) · **Opposing:** Institutions & People (Rory leads, Aoife partly crosses the floor)

**Marcus (Wharton), opening:** I switched on the new expectations module with the other new institutions: firms, inheritance, 90-day contracts and 50% severance. Seed 11: the wage went **from $179 to $309** while the baseline wage *fell* to $136. Food reached **$2,010**, and inflation hit **+1,043%** against +316% in the baseline. Seed 12, which I asked the facilitator to run (`data/d_institutions_s12.json`): **+447% vs +39%**, wage $335 vs $99. That's the 1970s mechanism, and it replicates: workers expect prices to rise, so they ask for more, firms pass it into prices, and the expectation comes true. Realistic.

**Rory (TCD), opening:** Realistic mechanism, maybe. Realistic economy, no. Name me a European economy that went from normal to a thousand percent in nine months without a war or a currency collapse. And I switched on contracts and severance in this same run, and I can't find them anywhere. How many contracts? How much severance was paid? Did anyone stop firing people? The run doesn't tell me.

**Aoife (TCD):** **[crosses the floor, partly]** I'm with Marcus on the mechanism and with Rory on the size. I worked on this at a central bank. Two things are wrong with the size. First, **speed**. The module updates expected inflation by 5% of the gap every day. That means half the gap closes in about **two weeks**. In the euro area, expectations move over quarters, sometimes years. A two-week half-life is a hyperinflation economy. Second, there's **no anchor**. When a central bank is credible, expectations stick near its target even when today's inflation jumps. Here they just chase the past, and they're capped at 200%, which is where they sit for most of the run.

**Cross-examination**

**Daniel (HBS) → Marcus:** You switched on four modules at once. Which one caused the spiral?

**Marcus:** ...Expectations, almost certainly. Wages rose 73% while the baseline wage fell.

**Sofia (Stanford), on Marcus's own team:** "Almost certainly" isn't a result. Inheritance did nothing visible because nobody died. Contracts and firms could both push wages. You ran a four-factor experiment with one observation per seed. **[concession, on behalf of the team]** We can't attribute this result to any one module.

**Marcus:** **[concession]** Fair. I bundled them because I wanted "the realistic economy". It was bad design of experiments.

**Elena (HBS) → Marcus:** And what did the central bank do while prices went up tenfold?

**Marcus:** Hit its ceiling. The policy rate has been at **20%** since day 120. That's the real failure. When Volcker took rates to about 20%, inflation was about 14%: the *real* rate was positive. Here it's 20% against 1,000% inflation, a real rate of about **−90%**. The Taylor principle says the nominal rate must rise *more* than one-for-one with inflation. A 20% cap makes that impossible, so no central bank in this model can stop a spiral.

**Verdict:** Evidence **mixed**. The spiral mechanism is real and replicates on two seeds (proposition). The size is unrealistic: too fast, no anchor, a capped central bank (opposition and Aoife). Attribution to expectations alone is **not established** (Sofia).

**Items logged**
- **D-09 Recommendation: anchored expectations and a visible real policy rate.** Add a credibility setting: expected inflation = credibility × target + (1 − credibility) × adaptive estimate. Slow the default speed to a half-life of months, not days. Show when the 200% cap binds. Show the **real** policy rate (nominal minus expected inflation) on the Central bank tab, with a warning when the Taylor principle is violated.
- **D-10 Critique + Recommendation: modules can't be attributed.** Every module needs its own KPIs (contracts: number active, severance paid, layoffs avoided; inheritance: estates passed on and their value; firms: entries, exits, bankruptcies). Add a "one factor at a time" experiment helper that switches on one module per run on the same seeds (builds on D-03).

---

<a id="round-6"></a>
## Round 6: Is the shock library ready for the classroom?

**Motion:** *"The shock library is ready for the classroom."*
**Proposing:** Institutions & People (Elena leads) · **Opposing:** Markets & Evidence (Sofia and Marcus). Daniel breaks with his own team.

**Elena (HBS), opening:** Instructors have wanted the "case moment" since session 1: the day the world changes and the protagonist has to decide. The new shocks deliver it. I ran an epidemic at day 90 and a grain-and-water shortage at day 180. The class would remember that run for years.

**Facilitator (evidence check, `data/d_shocks.json` vs `data/d_baseline_s11.json`):** Both runs use the same seed and are identical up to day 90, so the baseline is an exact counterfactual for the shock run.

| Day 270 | No shock (baseline) | Epidemic + shortage |
|---|---|---|
| Alive | 200 | **145** (55 deaths) |
| Ever infected | 0 | **197** of 200 |
| Labour offered/day | 16.8 | **3.1** |
| Capital built | 29.1 | **3.4** |
| Real wage (food per unit of labour) | 0.183 | 0.214 (+17%) |
| Public debt | $2.59M | $1.22M |
| Homeless | 5 | 0 |

The epidemic used the default settings: 15% daily contagion, **1% daily lethality** for 30 days, radius 120.

**Daniel (HBS), breaking with his team:** I ran a hospital through COVID, so I'm going to oppose my own side. A 1% chance of dying *every day* for 30 days is a case fatality of 1 − 0.99³⁰ ≈ **26%**. That matches what the run shows: 55 deaths among 197 infected. COVID's infection fatality rate was well under 1% overall. The 1918 flu killed perhaps 2–3% of those infected. **26% is the Black Death.** If an instructor clicks "epidemic" and gets the Black Death, we're teaching panic, not public health.

**Sofia (Stanford), opening for the opposition:** And here's the irony: some of it *is* historically right. After the Black Death, real wages in England rose because labour became scarce. Here real wages rose 17% against the counterfactual. That's a good result, but nobody can see it without the counterfactual next to it.

**Marcus (Wharton):** Look at the shortage too. Grain and water supply were cut by half at day 180, and food prices *fell*, from $882 to $707, during the shortage. That isn't a bug. By day 180 the economy is already demand-constrained: hardly anyone can afford grain, so cutting supply doesn't bind. Supply shocks only bite when supply is the constraint. That's a great lesson, but it's invisible. A student would just conclude that shortages don't matter.

**Aoife (TCD):** And labour never comes back. There are no births and no migration, so a 27% population loss is permanent. The closest European case I know is Ireland after the Famine, and there it was emigration, more than the deaths, that kept the population falling for decades.

**Cross-examination**

**Elena → Daniel:** Would you rather have no epidemic button?

**Daniel:** No. I'd rather the button say "COVID-like", "1918-like" or "Black-Death-like", with the numbers next to it and a source.

**Rory (TCD) → Sofia:** If every shock needs a counterfactual run, doesn't that double the cost?

**Sofia:** Same seed, same code: it's one extra run, and it's the only honest way to say "the shock caused this".

**Verdict:** Evidence **refutes** the motion as stated. The mechanics exist and some effects are historically right (the post-epidemic rise in real wages). But the default epidemic is about 30 times too lethal for a "typical" epidemic, the shortage effect is invisible without a counterfactual, and population never recovers.

**Items logged**
- **D-11 Recommendation: historical shock presets.** Named, calibrated presets (COVID-19, 1918 flu, Black Death; 1973 oil embargo; a 2008–10 style banking crisis), each with its parameters, sources and the expected textbook effect. Lethality per infection, not per day.
- **D-12 Recommendation: counterfactual "ghost line".** Every shock (and any scenario if asked) automatically re-runs the same seed without the shock and draws the difference on each chart.
- *Parked:* population renewal (births, migration), without which any death shock is permanent.

---

<a id="round-7"></a>
## Round 7: Do people stop working because the state pays them?

**Motion:** *"Labour participation collapses because the state pays people not to work."*
**Proposing:** Markets & Evidence (Priya leads) · **Opposing:** Institutions & People (Daniel leads)

**Priya (Wharton), opening:** Session 1's seventh backlog item was the participation collapse: labour offered falls from about 52 units a day to 17. Round 3 just showed the government hands out millions in transfers. Agents only look for work when they hold less than six months of living costs. Put those together: transfers top people up, they feel covered, they stop offering labour. That's moral hazard.

**Daniel (HBS), opening:** I'll bet you a pint it's illness. Round 1: 62 seriously ill. Sick people don't work. The penalties module cuts labour when needs go critical, and a critically ill agent can't work at all.

**Facilitator (evidence check, run during the round, files `data/pa_baseline.json` and `data/pa_light.json`):** Where the labour goes, seed 11, units per day (200 agents × 0.5 = 100 units of capacity):

| | Baseline, day 45 | Baseline, day 270 | Light touch (no benefit), day 270 |
|---|---|---|---|
| Base capacity | 100.0 | 100.0 | 100.0 |
| Capacity left after need penalties | 57.8 | **22.8** | **17.6** |
| Used in own business | 5.9 | 5.6 | 5.9 |
| Offered on the labour market | 51.9 | 16.8 | 11.6 |
| **Withheld by agents with 6+ months covered** | 0.0 | **0.4** | 0.0 |
| Agents seriously ill (health ≥ 0.8) | 0 | 62 | **96** |
| Median months of living costs held | 2.5 | **0.32** | **0.06** |

**Priya:** **[concession]** I owe Daniel a pint. Only 0.4 units are withheld by people who feel covered. The rest of the fall is capacity lost to penalties. And the economy *without* any benefit has the lowest participation and the most sick people. It's not moral hazard. They're broke and sick.

**Marcus (Wharton):** Let me reframe it so it's a lesson rather than a bug. This is a **poverty trap**: sick → can't work → can't earn → can't buy health → sicker. Banerjee and Duflo describe exactly this with nutrition and productivity. There's a threshold: above it, people earn enough to stay healthy; below it, they slide. The median agent holds a third of a month of living costs. That's below any threshold.

**Kenji (Stanford):** And meanwhile the dashboard shows **0% unemployment**, because unemployment only counts labour that is *offered* and not hired. Capacity has fallen 77% and the headline says everything's fine. That's the worst kind of metric: reassuring and wrong.

**Cross-examination**

**Sofia (Stanford) → Daniel:** Capacity is already down to 58% at **day 45**, before anyone is seriously ill. What's eating it?

**Daniel:** Fatigue and hunger penalties, I'd guess: energy, sleep, hunger.

**Sofia:** Then the penalty *sizes* are doing a lot of work, and nobody has calibrated them. Malnourished workers really are less productive, but losing 42% of a market economy's labour in six weeks is far more than any data I know of shows.

**Daniel:** **[concession]** I'll accept that. The direction is right; the magnitude is a guess.

**Rory (TCD):** And look at prices. A day's labour buys **0.18 units of food** on seed 11. Of course people slide. Food at $743 a unit with a wage of $136 is a famine price.

**Verdict:** Evidence **refutes** the motion. Withholding by covered agents explains almost nothing (0.4 of a 35-unit fall). The fall is capacity lost to need penalties, in a poverty trap where health, income and food prices reinforce each other. Penalty magnitudes are uncalibrated (Sofia).

**Items logged**
- **D-13 Critique + Recommendation: labour-force decomposition, and calibrated penalties.** Replace the single unemployment rate with a labour-force panel: capacity lost to illness, hunger and fatigue; own business; offered; hired; withheld. Calibrate penalty sizes against published productivity effects. Add a "poverty trap" teaching scenario showing the threshold.

---

<a id="round-8"></a>
## Round 8: Platform or course?

**Motion:** *"EconSim should be a platform for experiments, not a course."*
**Proposing:** Markets & Evidence (Kenji and Sofia) · **Opposing:** Institutions & People (Elena and Rory)

**Kenji (Stanford), opening:** Every round today ended with "we need another run", "we need another seed", "we need the counterfactual". That's a platform: an experiment designer, seeds, ensembles, CSV export, an API. Let instructors build their own content. Platforms scale; courses don't.

**Elena (HBS), opening:** HBS doesn't sell a platform. It sells cases: a protagonist, a decision, a 75-minute session plan and a teaching note. An instructor with 60 students and one evening to prepare will not design an experiment. They'll pick a case off the shelf. If EconSim doesn't come with cases, it will be used once and admired.

**Rory (TCD):** And at Trinity our best module was the Strategic Company Project: a real firm, a real decision, a real owner on the phone. The firms module now tracks **272 firm entities** with income statements and balance sheets in the institutions run, and nobody here has looked at one. Give me an SME owner's view: cash runway, P&L, the bank manager's letter. That's the case.

**Aoife (TCD):** And Trinity's mission is "business for good". Every decision in a case should come with a **distributional impact card**: who gained, who lost, who got sick. Round 4 showed redistribution helps deprivation. Show the student who bears the cost.

**Cross-examination**

**Sofia (Stanford) → Elena:** What stops a case becoming a script, where the student "discovers" the answer the teaching note wanted?

**Elena:** A good case doesn't have an answer. But I take the risk.

**Sofia:** Then here's a bridge. Before every run the student writes a **prediction**: "inflation will rise more than 50%". The platform runs it over the seed ensemble and scores the prediction. Today we were wrong in public several times: Priya on moral hazard, our side on investment. That was the best learning in the room.

**Elena:** **[concession]** That's actually the case method with a scoreboard. Predict, decide, find out you were wrong, discuss why. I'll take it, if it lives inside a case.

**Kenji:** **[concession]** And I'll accept that the first ten things we ship should be cases built on the platform, not an empty platform.

**Verdict:** **Synthesis, not a winner.** A platform underneath with cases on top, joined by a predict–run–explain loop.

**Items logged**
- **D-14 Recommendation: predict–run–explain loop.** Before a run the student records a prediction on a chosen metric. After the run (or ensemble) the platform scores it and asks for an explanation, using the "why did this change?" explainer (session 1, item #1).
- **D-15 Recommendation: case pack format.** A packaged case: scenario, locked seed set, protagonist role, 2–3 decision points, prediction prompts, a teaching note and a distributional impact card. Rory's SME cockpit (firm-level P&L, cash runway, bank) is the first case it should support.

---

<a id="round-9"></a>
## Round 9: Closing statements

Each team gave its red lines (what it won't give up) and one concession.

**Markets & Evidence (Wharton + Stanford), delivered by Marcus**
- *Red line 1:* no headline number shown without a seed band. One seed is never "the result" (D-03).
- *Red line 2:* no hidden policy. Every fiscal and monetary rule that moves money must be a visible choice (D-05).
- *Red line 3:* the central bank must be able to win. Anchored expectations and a visible real rate (D-09).
- *Concession:* "We came in saying incentives explain the labour collapse, and that redistribution kills investment. The data said no to the first and 'don't know' to the second. We take that."

**Institutions & People (Harvard + Trinity), delivered by Elena**
- *Red line 1:* health and survival come first in every indicator. Boredom doesn't sit next to thirst (D-01, D-02, D-13).
- *Red line 2:* the product ships cases, not an empty sandbox (D-15).
- *Red line 3:* shocks must be calibrated to real history, with sources, before they go in front of a class (D-11).
- *Concession:* "We wanted the single dramatic run. Sofia showed that the seed can matter more than the policy. A story seed inside a fan chart is a better story, because it's an honest one."

**Facilitator's summary of where the teams still disagree**
1. **Time horizon** (Kenji vs Rory): whether low profit taxes pay off over years can't be settled in nine months. That needs D-08.
2. **What counts as deprivation** (Rory vs Priya): Rory wants wellbeing (boredom, energy) kept visible as quality of life; Priya wants it out of the headline. D-01 keeps it but in a separate tier.
3. **Platform vs course priority** (Kenji vs Elena): agreed as "cases first, on the platform", but they still disagree on the ratio.

---

<a id="round-10"></a>
## Round 10: The vote

Each participant had 10 points to spread across the 15 items as they liked. Ties are broken by
the number of voters, then by support from both teams, then by how strong the session's
evidence was.

| Item | Priya (W) | Marcus (W) | Kenji (S) | Sofia (S) | Elena (H) | Daniel (H) | Aoife (T) | Rory (T) | **Total** | Wharton + Stanford | Harvard + Trinity |
|---|---|---|---|---|---|---|---|---|---|---|---|
| D-13 Labour-force decomposition + penalties | | 1 | 2 | 1 | | 4 | | 2 | **10** | 4 | 6 |
| D-03 Ensemble mode, fan charts, story seed | 2 | 1 | 3 | 3 | | | | | **9** | 9 | 0 |
| D-05 Residual treasury rule as a choice | 3 | 2 | | | 1 | | 2 | | **8** | 5 | 3 |
| D-09 Anchored expectations, real rate | 1 | 4 | | | | | 3 | | **8** | 5 | 3 |
| D-14 Predict–run–explain | | | 3 | 2 | 2 | | | | **7** | 5 | 2 |
| D-12 Counterfactual ghost line | | 2 | 1 | 1 | 1 | | 1 | | **6** | 4 | 2 |
| D-15 Case pack format | | | | | 4 | | | 2 | **6** | 0 | 6 |
| D-01 Tiered deprivation index | | | | | 2 | 1 | | 2 | **5** | 0 | 5 |
| D-06 Efficiency–equity frontier | 2 | | 1 | | | | | 1 | **4** | 3 | 1 |
| D-02 Health deprivation | | | | | | 3 | | 1 | **4** | 0 | 4 |
| D-11 Historical shock presets | | | | | | 2 | 2 | | **4** | 0 | 4 |
| D-04 Ownership KPI (dust) | | | | | | | 1 | 2 | **3** | 0 | 3 |
| D-10 Per-module KPIs, one factor at a time | | | | 3 | | | | | **3** | 3 | 0 |
| D-07 Approval calibration | 1 | | | | | | 1 | | **2** | 1 | 1 |
| D-08 Long-horizon runs | 1 | | | | | | | | **1** | 1 | 0 |
| **Total** | 10 | 10 | 10 | 10 | 10 | 10 | 10 | 10 | **80** | 40 | 40 |

**Reading the vote**
- **Cross-team consensus** (points from both teams): D-13, D-05, D-09, D-14, D-12, D-06, D-07. The top item, D-13, came out of a round in which the proposing team lost the argument and then voted for the fix.
- **One team only, with no objection from the other:** D-03 (Wharton + Stanford; the other side accepted fan charts in Round 2 but spent its points on cases), and D-15, D-01, D-02, D-11, D-04 (Harvard + Trinity).
- **Points cast across team lines:** Elena on D-05, D-12 and D-14; Aoife on D-09 and D-07; Rory on D-06; Marcus, Kenji and Sofia on D-13. Both teams cast exactly 40 points.

The ranked list, with what each item changes, is in [BACKLOG.md](BACKLOG.md).

---

<a id="appendix-a"></a>
## Appendix A: The concepts behind the arguments

Short explanations of the ideas the students used, for readers who want the fundamentals.

**1. Adaptive expectations and the half-life (Round 5).**
The module updates expected inflation every day by a fixed share λ of the gap between actual and expected inflation:
π^e(t) = π^e(t−1) + λ · (π(t) − π^e(t−1)).
After n days without new surprises, the share of an old gap still left is (1 − λ)ⁿ. Half of it is gone when (1 − λ)ⁿ = ½, so n = ln ½ / ln(1 − λ). With λ = 0.05 a day, n = 0.693 / 0.0513 ≈ **13.5 days**. For a half-life of 6 months (180 days) you'd need λ ≈ 0.0038.
*Anchoring* adds the central bank's target: π^e = c · target + (1 − c) · adaptive estimate, where the credibility c runs from 0 (nobody believes the bank) to 1 (everyone does).

**2. The Fisher equation, the real rate and the Taylor principle (Round 5).**
The real interest rate is roughly the nominal rate minus expected inflation: r ≈ i − π^e. (Exactly: 1 + r = (1 + i) / (1 + π^e).) With i = 20% and π = 1,000%, 1 + r = 1.2 / 11 ≈ 0.11, so r ≈ **−89%**. Borrowing is effectively free, and nothing slows demand.
The Taylor rule sets i = r* + π + 0.5(π − π*) + 0.5·gap. The coefficient on inflation is 1.5 in total, more than 1. That is the **Taylor principle**: when inflation rises 1 point, the nominal rate rises 1.5 points, so the real rate rises and cools the economy. A ceiling on i breaks this as soon as inflation passes the ceiling.

**3. Case fatality from a daily rate (Round 6).**
If each day an infected agent dies with probability p, the chance of surviving n days is (1 − p)ⁿ. The chance of dying is 1 − (1 − p)ⁿ. With p = 1% and n = 30: 1 − 0.99³⁰ = 1 − 0.740 ≈ **26%**. To get a 0.5% fatality over 30 days you'd need p ≈ 0.017% a day.

**4. Why seeds matter: sampling variation (Round 2).**
A seed fixes the random draws (who starts rich, where agents stand, who gets lucky). Different seeds are like different possible histories. With N seeds you can estimate the spread of an outcome (its standard deviation σ). The uncertainty in the *average* outcome shrinks like σ / √N: 4 seeds halve it compared with 1, and 16 seeds halve it again. A **policy effect** is only believable when it is larger than this noise. That's why Sofia compared the 13-point gap between seeds with the policy effect of −1 to +7 points.

**5. Counterfactuals (Round 6).**
The effect of a shock is the outcome *with* the shock minus the outcome in the same world *without* it. Real economies never show us the second world. A simulation can, because the same seed replays the same history up to the shock (the two runs here match exactly until day 90). The difference between them is a clean causal estimate.

**6. Effective demand and supply shocks (Rounds 4 and 6).**
Firms produce what they can *sell*, and sales depend on what buyers can afford (Keynes's *effective demand*), not only on what they'd like. When demand is the binding constraint, extra capacity sits idle (Rory's "empty sheds") and a cut in supply doesn't push prices up (Marcus's shortage). A supply shock raises prices only when supply was the binding constraint.

**7. Poverty traps (Round 7).**
Suppose next year's health h(t+1) depends on this year's: h(t+1) = f(h(t)), because health → work → income → food and medicine → health. If f is S-shaped, it crosses the 45° line (h(t+1) = h(t)) three times. The low and high crossings are stable resting points; the middle one is a threshold. Below the threshold, each year is worse than the last, and people slide to the low point. Above it, they climb to the high one. A one-off push across the threshold (for example a health service) can move people for good, whereas a small push that leaves them below it fades away.

**8. Automatic stabilisers (Round 3).**
Taxes and transfers that respond to the economy without a new decision: tax receipts fall and benefits rise in a downturn, which props up demand. They are a real and useful feature. The panel's complaint wasn't that they exist, but that the model's version is debt-financed, untargeted and hidden.

---

<a id="appendix-b"></a>
## Appendix B: Sources for the personas

These describe what each school says it looks for. Most are the schools' own pages; some are
admissions-consultant summaries, marked as such.

- Stanford GSB: [Evaluation criteria](https://www.gsb.stanford.edu/programs/mba/admission/evaluation-criteria) (official); [Poets&Quants: what Stanford seeks](https://poetsandquants.com/2018/07/12/what-does-stanford-seek-in-applicants/)
- Harvard Business School: [GMAC: Harvard MBA application insider (Aug 2026)](https://www.gmac.com/resources/learners/how-to-apply/application-guidance/harvard-mba-application-insider) (on the new criteria); [Poets&Quants: what HBS seeks](https://poetsandquants.com/2018/06/13/what-does-harvard-business-school-seek-in-applicants/) (the historical three criteria, consultant source)
- Wharton: [Application guide 2023–24 (PDF)](https://mba.wharton.upenn.edu/wp-content/uploads/2023/09/App-Guide-2023-24.pdf) (official); [Class profile](https://mba.wharton.upenn.edu/class-profile) (official); [Clear Admit: how to get into Wharton](https://www.clearadmit.com/2023/04/how-to-get-into-the-wharton-mba-program/) (Team-Based Discussion, consultant source); [Poets&Quants: Class of 2026](https://poetsandquants.com/2025/03/05/meet-whartons-mba-class-of-2026/2/)
- Trinity College Dublin: [Full-time MBA application & FAQs](https://tcd.ie/business/programmes/mba/full-time-mba/application--faqs) (official); [Full-time MBA highlights](https://tcd.ie/business/programmes/mba/full-time-mba/highlights) (official); [Why Trinity Business School](https://www.tcd.ie/business/student-experience/why-trinity-business-school/) (official, "Transform Business for Good")
