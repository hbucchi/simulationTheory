"""Why did this number change? Breakdowns of the headline numbers into their causes.

``explain(world, metric)`` returns
    {"metric", "title", "value", "summary", "parts": [{"label", "value", "share", "note"}],
     "notes": [...]}
where ``parts`` add up to the headline (or, for rates, show its drivers), so the UI can draw them
as a bar list. Metrics: inflation, labour, need, wage, approval, debt, mortgages.
"""
import math

from . import economy
from .labor import LOSS_CAUSES

LABELS = {"hunger": "Hunger", "thirst": "Thirst", "sleep": "Tiredness (sleep)", "health": "Sickness (health)",
          "energy": "No energy (power, heat)", "shelter": "No shelter", "boredom": "Boredom",
          "depression": "Depression"}
METRICS = ("inflation", "labour", "need", "wage", "approval", "debt", "mortgages")


def _part(label, value, total=None, note=""):
    share = (value / total) if total else None
    return {"label": label, "value": round(value, 4), "share": round(share, 4) if share is not None else None,
            "note": note}


def explain(world, metric):
    if metric not in METRICS:
        raise ValueError(f"metric must be one of: {', '.join(METRICS)}")
    return globals()[f"_{metric}"](world)


# ---------- inflation: which goods pushed the price index ----------

def _inflation(world):
    """CPI change split by good: each good's weight in the basket (its share of the basket's cost
    at the starting prices) x its own price change. The contributions add up to the CPI change."""
    nat = world.recorder.national
    h = world.recorder.history[-1] if world.recorder.history else {}
    if not nat.price_log or not h.get("cpi_days"):
        return {"metric": "inflation", "title": "Inflation", "value": 0.0,
                "summary": f"No reading yet: the first {world.rules.cpi_warmup_days} days are price discovery "
                           "(markets finding their level), not inflation. The index starts after them.",
                "parts": [], "notes": []}
    then, now = nat.price_log[0], world.current_prices()
    basket = {g: q for g, q in nat.used.items() if q > 0}
    cost_then = sum(q * then[g] for g, q in basket.items())
    parts = []
    for g, q in basket.items():
        if cost_then <= 0 or then[g] <= 0:
            continue
        weight = q * then[g] / cost_then
        parts.append((g, weight, now[g] / then[g] - 1))
    total = sum(w * c for _, w, c in parts)
    parts.sort(key=lambda t: abs(t[1] * t[2]), reverse=True)
    span = "the last 12 months" if h["cpi_days"] >= world.year_steps() else f"the {h['cpi_days']} days since the base day"
    out = [_part(g.replace("_", " ").capitalize(), w * c, None,
                 f"{w:.0%} of the basket; its price {'+' if c >= 0 else ''}{c:.0%}") for g, w, c in parts[:12]]
    rest = sum(w * c for _, w, c in parts[12:])
    if parts[12:]:
        out.append(_part(f"{len(parts) - 12} other goods", rest))
    ann = h.get("inflation_annualised")
    return {"metric": "inflation", "title": "Inflation", "value": h.get("inflation", 0.0),
            "summary": f"Consumer prices changed {total:+.1%} over {span}. Each bar is a good's contribution: its "
                       "weight in what people buy times its own price change.",
            "parts": out,
            "notes": [f"At a yearly pace over the last 3 months: {ann:+.1%}." if ann is not None else
                      "Too early for a 3-month yearly pace.",
                      "The bars use one fixed basket (today's), so their sum can differ a little from the headline, "
                      "which chains a new basket each month as statistics offices do.",
                      "The central bank and price expectations read the 12-month rate (or, in the first year, "
                      "the yearly pace since the base day once there are 3 months of index)."]}


# ---------- labour: where it went and what reduced it ----------

def _labour(world):
    s = world.labor.stats
    b, lost = s.get("breakdown", {}), s.get("lost_by", {})
    full = b.get("full_capacity", 0.0) or 1.0
    parts = [_part(f"Lost: {LABELS[c].lower()}", lost.get(c, 0.0), full) for c in LOSS_CAUSES if lost.get(c, 0.0) > 1e-6]
    if b.get("survival_extra", 0.0) > 1e-6:
        parts.append(_part("Extra survival effort (beyond what penalties leave)", -b["survival_extra"], full))
    for key, label in (("own_business", "Own business"), ("hired_private", "Hired by firms"),
                       ("hired_public", "Hired by the government"), ("autonomous", "Autonomous production (own food, water)"),
                       ("looking", "Looking for work (offered, not hired)"), ("not_offered", "Not offered")):
        parts.append(_part(label, b.get(key, 0.0), full))
    h = world.recorder.history[-1] if world.recorder.history else {}
    lf = h.get("lf", {})
    return {"metric": "labour", "title": "Where labour goes", "value": b.get("lost", 0.0) / full,
            "summary": f"Of {full:,.1f} units agents could work at full health today, {b.get('lost', 0.0):,.1f} "
                       f"({b.get('lost', 0.0) / full:.0%}) were lost to unmet needs. Bars are units of labour.",
            "parts": parts,
            "notes": [f"People (ILO-style): {lf.get('employee', 0)} employees, {lf.get('public', 0)} public employees, "
                      f"{lf.get('self_employed', 0)} self-employed, {lf.get('own_use', 0)} own-use producers, "
                      f"{lf.get('unemployed', 0)} unemployed, {lf.get('unable', 0)} too ill, {lf.get('outside', 0)} not looking.",
                      f"Unemployment rate {h.get('lf_unemployment', 0):.0%} of the labour force; "
                      f"participation {h.get('lf_participation', 0):.0%}.",
                      "Lost labour: every unmet need lowers efficiency in proportion to its weight; needs past "
                      "0.8 add penalties (penalties.py). Shares of a multiplied penalty are split by its log."]}


# ---------- need: which needs, how serious ----------

def _need(world):
    h = world.recorder.history[-1] if world.recorder.history else {}
    n = len(world.agents) or 1
    by = h.get("need_by", {})
    parts = [_part(LABELS.get(k, k), v / n, None, f"{v} agents") for k, v in sorted(by.items(), key=lambda t: -t[1])]
    return {"metric": "need", "title": "People in need", "value": h.get("in_need_core", 0.0),
            "summary": f"{h.get('in_need_core', 0):.0%} lack a survival or security need (thirst, hunger, health, "
                       f"shelter, sleep); {h.get('need_wellbeing', 0):.0%} lack a wellbeing need (energy, boredom). "
                       "Bars: share of people above the seek threshold for each need (one person can have several).",
            "parts": parts,
            "notes": [f"Survival tier: {h.get('need_survival', 0):.0%} · security: {h.get('need_security', 0):.0%} · "
                      f"wellbeing: {h.get('need_wellbeing', 0):.0%} · any need: {h.get('in_need', 0):.0%}."]}


# ---------- wage: what moved it ----------

def _wage(world):
    L, s, r = world.labor, world.labor.stats, world.rules
    wanted, offered = s.get("wanted", 0.0), s.get("offered", 0.0)
    gap = (wanted - offered) / max(wanted, offered) if max(wanted, offered) > 0 else 0.0
    parts = [_part("Labour employers can pay for (units)", wanted), _part("Labour offered (units)", offered),
             _part("Hired by firms (units)", s.get("hired", 0.0)), _part("Hired by the government (units)", s.get("gov_hired", 0.0))]
    notes = [f"Excess demand for labour: {gap:+.0%} (positive pushes the wage up, negative down).",
             f"Wages move up to {r.wage_adjust_speed:.0%} a month up / {r.wage_down_speed:.0%} down at first, "
             f"faster while the pressure lasts ({L.wage_streak_days} days so far)." if hasattr(L, "wage_streak_days") else ""]
    if r.expectations_enabled:
        notes.append(f"Indexation: wages also rise with {r.wage_indexation:.0%} of expected inflation "
                     f"({world.expected_inflation:.1%} a year).")
    if world.government.min_wage:
        notes.append(f"Minimum wage: {world.government.min_wage:,.2f}.")
    return {"metric": "wage", "title": "Wage", "value": L.wage,
            "summary": "The wage follows the labour market: it rises when employers can pay for more labour than is "
                       "offered, and falls when more is offered than they can pay for.",
            "parts": parts, "notes": [x for x in notes if x]}


# ---------- approval ----------

def _approval(world):
    g = world.government
    bd = g.approval_breakdown
    weights = {"wellbeing": 0.45, "employment": 0.25, "inflation": 0.15, "taxes": 0.15}
    parts = [_part(f"{k.capitalize()} (weight {w:.0%}, score {bd.get(k, 0):.2f})", w * bd.get(k, 0)) for k, w in weights.items()]
    return {"metric": "approval", "title": "Government approval", "value": g.approval,
            "summary": "Approval moves 10% a day toward 45% wellbeing + 25% employment + 15% price stability + 15% low "
                       "taxes. Bars: each part's points toward the target.",
            "parts": parts,
            "notes": [f"Price stability uses a log scale: an excess of {world.rules.approval_inflation_half:.0%} over "
                      "the target halves its score, and every further multiplication of prices costs less again."]}


# ---------- public debt ----------

def _debt(world):
    gov, debt = world.government, world.government.debt
    total = debt.total
    year = world.year_steps()
    banks = sum(b.principal for b in debt.bonds if hasattr(b.holder, "deposits") and hasattr(b.holder, "cb_reserves"))
    parts = [_part("Held by banks", banks, total), _part("Held by savers", total - banks, total)]
    pol = (1 + gov.min_rate) ** year - 1
    spread = (1 + gov.bond_spread) ** year - 1
    risk = (1 + debt.risk_premium(world)) ** year - 1
    sus = debt.sustainability(world)
    notes = [f"New bonds pay {debt.rate_year(world):.1%} a year = policy rate {pol:.1%} + spread {spread:.1%} + risk "
             f"premium {risk:.1%} (grows with debt / limit, squared)."]
    if sus.get("r") is not None and sus.get("g") is not None:
        notes.append(f"r (average rate on the debt) {sus['r']:.1%} vs g (nominal GDP growth) {sus['g']:.1%}: "
                     + ("debt grows faster than the economy unless the budget runs a primary surplus."
                        if sus["r"] > sus["g"] else "the economy outgrows the debt's interest."))
    if sus.get("interest_burden") is not None:
        notes.append(f"Interest takes {sus['interest_burden']:.0%} of tax revenue.")
    notes.append(f"Treasury cash held: {gov.treasury:,.0f} (what you don't allocate stays there).")
    return {"metric": "debt", "title": "Public debt", "value": total,
            "summary": f"The government owes {total:,.0f} in bonds, {debt.to_dict(world)['debt_to_gdp']:.0%} of a "
                       "year's real GDP.", "parts": parts, "notes": notes}


# ---------- mortgages: why are there none? ----------

def _mortgages(world):
    bank = world.banking
    loans = [l for b in bank.banks for l in b.loans if getattr(l, "house", None) is not None]
    if not world.rules.housing_enabled:
        return {"metric": "mortgages", "title": "Mortgages", "value": 0, "summary": "The housing market is off.",
                "parts": [], "notes": []}
    price = world.housing.price(world)
    deposit = price * (1 - bank.mortgage_ltv)
    renters = [a for a in world.agents if not (a.home is not None and a.home.owner is a)]
    from .modules.invest import budget_needed
    prices = world.current_prices()
    steps = round(bank.mortgage_years * world.year_steps())
    from .banking import annuity
    installment = annuity(price * bank.mortgage_ltv, bank.mortgage_rate(world), steps) if price > 0 else 0.0
    has_deposit = [a for a in renters if economy.money_of(a) - budget_needed(a, prices, world) >= deposit]
    passes_income = [a for a in has_deposit if installment <= bank.mortgage_dti * a.income_avg]
    for_sale = sum(1 for h in world.housing.houses if h.for_sale and h.occupant is None)
    n = len(renters) or 1
    parts = [_part("Without a home of their own", len(renters), n),
             _part(f"... with the deposit ({deposit:,.0f}) on top of their budget", len(has_deposit), n),
             _part(f"... and income for the installment ({installment * world.rules.month_steps:,.0f} a month "
                   f"≤ {bank.mortgage_dti:.0%} of income)", len(passes_income), n)]
    notes = [f"A house costs {price:,.0f}; banks lend up to {bank.mortgage_ltv:.0%} over {bank.mortgage_years:g} years "
             f"at {(1 + bank.mortgage_rate(world)) ** world.year_steps() - 1:.1%} a year.",
             f"{for_sale} vacant houses for sale.",
             f"{len(bank.open_banks()) if hasattr(bank, 'open_banks') else 0} banks open."]
    why = ("Nobody without a home can put down the deposit." if not has_deposit else
           "Those with a deposit don't earn enough for the installment." if not passes_income else
           "No vacant house is for sale." if not for_sale else
           "Some can buy: watch the next days.")
    return {"metric": "mortgages", "title": "Mortgages", "value": len(loans),
            "summary": f"{len(loans)} mortgages. {why if not loans else ''}".strip(),
            "parts": parts, "notes": notes}
