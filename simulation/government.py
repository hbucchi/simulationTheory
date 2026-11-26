"""The central government and its central bank.

Fiscal policy (the government):
- Taxes, collected into the treasury:
    production tax: a share of the money of every sale of goods (paid by the seller);
    salary tax: a share of every wage (withheld from the worker's pay);
    profit tax: a share of every company's and bank's profit (goods sold - wages, or interest).
- Spending, every step, from the treasury:
    1. public works: ``labor_purchase`` units of labour hired at each worker's asking wage; what
       the treasury can't pay is paid with newly created money (how money is injected);
    2. unemployment benefit: ``benefit_rate`` x the market wage for every unit of labour an agent
       offered and nobody hired (pro rata if the treasury runs short);
    3. the player's public spending policies, in order (policies.py: income support, resources
       given away, public services; by default a food and water safety net);
    4. with ``balanced_budget``, whatever is left hires more idle labour for public works, and what
       is still left (nobody idle) is paid out equally to every agent (transfers), so taxes go
       back into the economy instead of sitting in the treasury.

- ``min_wage``: the lowest wage per unit of labour (a day's work) anyone may be paid; workers
  never ask for less and employers pay at least this. 0 = no minimum wage.

Monetary policy (the central bank):
- ``min_rate``: no asset may be valued at a return below this rate. The effective return of an
  asset is max(its own asset_return, min_rate), so raising the rate lowers every asset's price
  (price = output x good price / return). Bank deposit rates never go below it.
- ``capital_ratio`` (Basel): a commercial bank's equity must be at least this share of its
  risk-weighted assets: its loans (cash reserves carry no risk, weight 0). At 12%, every $1 of
  equity backs at most $8.33 of loans. Equity is the owners' own money; deposits are third
  parties' money, so this caps how far a bank may lend other people's money against its own.
- ``reserve_requirement``: commercial banks must hold this share of their deposits in an
  account at the central bank (see banking.py). The central bank pays ``reserve_rate`` on it.
- ``lender_of_last_resort``: when on, the central bank lends to a solvent bank that runs out
  of cash (to pay depositors or meet the requirement), at the policy rate + ``llr_penalty``.
  That money is newly created and disappears again when the bank repays.

The policy starts from the game rules and can be changed while the game runs. With the
government switched off (``enabled`` False) none of this applies: no taxes, no spending, no
policy rate, no capital or reserve rules and no lender of last resort.
"""

POLICY = ("min_wage", "min_rate", "labor_purchase", "capital_ratio", "tax_production", "tax_wage", "tax_profit",
          "benefit_rate", "balanced_budget", "reserve_requirement", "reserve_rate", "lender_of_last_resort",
          "llr_penalty", "bonds_enabled", "debt_limit", "bond_spread", "bond_days", "pay_period",
          "min_contract_days", "severance_rate",
          "taylor_enabled", "inflation_target", "neutral_rate", "taylor_unemployment", "bond_risk_max")
TAXES = ("production", "wage", "profit")

from .bonds import PublicDebt  # noqa: E402
from .policies import AUDIENCES, DISTRIBUTIONS, KINDS, Policies  # noqa: E402

SPENDING = ("public_works", "benefits", "reserve_interest", "transfers", "interest", "debt_repaid")

POLICY_OPTIONS = {"kinds": KINDS, "audiences": AUDIENCES, "distributions": DISTRIBUTIONS}


def _policy(name):
    """A policy setting that reads as 0 / False while the government is switched off."""
    return property(lambda self: self._policy[name] if self.enabled else type(self._policy[name])(),
                    lambda self, v: self._policy.__setitem__(name, v))


class Government:
    def __init__(self, min_rate=0.0, labor_purchase=0.0, capital_ratio=0.12, enabled=True, policies=None, **policy):
        self.enabled = enabled
        self._policy = {"min_rate": min_rate, "labor_purchase": labor_purchase, "capital_ratio": capital_ratio,
                        "min_wage": 0.0, "tax_production": 0.0, "tax_wage": 0.0, "tax_profit": 0.0, "benefit_rate": 0.0,
                        "balanced_budget": False, "reserve_requirement": 0.0, "reserve_rate": 0.0,
                        "lender_of_last_resort": False, "llr_penalty": 0.0,
                        "bonds_enabled": False, "debt_limit": 0.0, "bond_spread": 0.0, "bond_days": 360,
                        "pay_period": "daily", "min_contract_days": 0, "severance_rate": 0.0,
                        "taylor_enabled": False, "inflation_target": 0.02,
                        "neutral_rate": 0.02, "taylor_unemployment": 0.05, "bond_risk_max": 0.0}
        self._policy.update(policy)
        self.money_created = 0.0   # total new money paid out so far (public works the treasury couldn't pay)
        self.labor_bought = 0.0    # total labour bought so far
        self.last_spent = 0.0      # money created in the latest step
        self.treasury = 0.0        # taxes collected and not yet spent
        self.revenue = {t: 0.0 for t in TAXES}           # taxes collected so far, by tax
        self.step_revenue = {t: 0.0 for t in TAXES}      # ... in the latest step
        self.spent = {k: 0.0 for k in SPENDING}
        self.step_spent = {k: 0.0 for k in SPENDING}
        self.debt = PublicDebt()   # government bonds (bonds.py)
        self.llr_outstanding = 0.0   # central bank loans to banks not yet repaid (newly created money)
        self.llr_lent = 0.0          # all it has lent so far
        self.cb_income = 0.0         # interest banks paid on those loans (goes to the treasury)
        self.revenue_days = []      # taxes collected on each of the last 30 days
        self.rev_by_day = []        # {production, wage, profit} per day (last 30 days)
        self.spend_by_day = []      # {public_works, benefits, ...} per day (last 30 days)
        self.approval = 0.5         # 0..1 government approval rating (foundation for elections)
        self.approval_breakdown = {"wellbeing": 0.5, "employment": 0.5, "inflation": 0.5, "taxes": 0.5}
        self.taylor_last = None     # the latest Taylor-rule decision and its inputs
        self.policies = Policies(policies or ())   # public spending the player designed (policies.py)

    def receive(self, amount):
        """Central bank income (interest on its loans): into the treasury."""
        if amount > 0:
            self.treasury += amount
            self.cb_income += amount

    @classmethod
    def from_rules(cls, rules):
        return cls(rules.gov_min_rate, rules.gov_labor_purchase, rules.capital_ratio, rules.government_enabled,
                   policies=rules.gov_policies,
                   min_wage=rules.gov_min_wage, tax_production=rules.tax_production, tax_wage=rules.tax_wage, tax_profit=rules.tax_profit,
                   benefit_rate=rules.benefit_rate, balanced_budget=rules.balanced_budget,
                   reserve_requirement=rules.reserve_ratio, reserve_rate=rules.reserve_rate,
                   lender_of_last_resort=rules.lender_of_last_resort, llr_penalty=rules.llr_penalty,
                   bonds_enabled=rules.gov_bonds_enabled, debt_limit=rules.gov_debt_limit,
                   bond_spread=rules.gov_bond_spread, bond_days=rules.gov_bond_days, pay_period=rules.pay_period,
                   min_contract_days=rules.min_contract_days, severance_rate=rules.severance_rate,
                   taylor_enabled=rules.taylor_enabled, inflation_target=rules.inflation_target,
                   neutral_rate=rules.neutral_rate, taylor_unemployment=rules.taylor_unemployment,
                   bond_risk_max=rules.gov_bond_risk_max)

    # The policy in force: nothing while the government is switched off.
    min_wage = _policy("min_wage")
    min_rate = _policy("min_rate")
    labor_purchase = _policy("labor_purchase")
    capital_ratio = _policy("capital_ratio")
    tax_production = _policy("tax_production")
    tax_wage = _policy("tax_wage")
    tax_profit = _policy("tax_profit")
    benefit_rate = _policy("benefit_rate")
    balanced_budget = _policy("balanced_budget")
    reserve_requirement = _policy("reserve_requirement")
    reserve_rate = _policy("reserve_rate")
    lender_of_last_resort = _policy("lender_of_last_resort")
    llr_penalty = _policy("llr_penalty")
    bonds_enabled = _policy("bonds_enabled")
    debt_limit = _policy("debt_limit")
    bond_spread = _policy("bond_spread")
    bond_days = _policy("bond_days")
    pay_period = _policy("pay_period")
    min_contract_days = _policy("min_contract_days")
    severance_rate = _policy("severance_rate")
    taylor_enabled = _policy("taylor_enabled")
    inflation_target = _policy("inflation_target")
    neutral_rate = _policy("neutral_rate")
    taylor_unemployment = _policy("taylor_unemployment")
    bond_risk_max = _policy("bond_risk_max")

    def set(self, name, value):
        if name not in POLICY:
            raise KeyError(name)
        self._policy[name] = value

    def effective_return(self, rules, good):
        return max(rules.asset_return[good], self.min_rate)

    # ---------- taxes ----------

    def begin_step(self):
        # Taxes & spending of each of the last 30 days (for monthly budget breakdown).
        self.revenue_days.append(sum(self.step_revenue.values()))
        del self.revenue_days[:-30]
        self.rev_by_day.append(dict(self.step_revenue))
        del self.rev_by_day[:-30]
        self.spend_by_day.append(dict(self.step_spent))
        del self.spend_by_day[:-30]
        self.step_revenue = {t: 0.0 for t in TAXES}
        self.step_spent = {k: 0.0 for k in SPENDING}
        self.last_spent = 0.0

    def update_approval(self, world):
        """Compute government approval rating (0..1) from citizen wellbeing, employment,
        price stability, and tax burden — smoothed over time for future election mechanics."""
        if not world.agents:
            return
        wb = sum(a.wellbeing for a in world.agents) / len(world.agents)
        l = world.labor.stats
        unemp = (max(0.0, l.get("idle", 0.0)) / l["offered"]) if l.get("offered", 0.0) > 1e-9 else 0.0
        emp = max(0.0, min(1.0, 1.0 - unemp))
        hist = world.recorder.history
        inf = hist[-1].get("inflation", 0.0) if hist else 0.0
        inf_score = max(0.0, min(1.0, 1.0 - abs(inf - self.inflation_target) / 0.25))
        tax_sum = self.tax_production + self.tax_wage + self.tax_profit
        tax_score = max(0.0, min(1.0, 1.0 - tax_sum / 1.2))
        target = max(0.0, min(1.0, 0.45 * wb + 0.25 * emp + 0.15 * inf_score + 0.15 * tax_score))
        self.approval_breakdown = {
            "wellbeing": round(wb, 3),
            "employment": round(emp, 3),
            "inflation": round(inf_score, 3),
            "taxes": round(tax_score, 3),
        }
        if world.tick <= 1:
            self.approval = target
        else:
            self.approval += 0.10 * (target - self.approval)

    def budget_month(self, world):
        """30-day projected monthly inflows (by tax) and outflows (by spending category)."""
        month = world.rules.month_steps if world is not None else 30
        rev_rows = self.rev_by_day + ([self.step_revenue] if any(self.step_revenue.values()) else [])
        rev_rows = rev_rows[-month:]
        days_r = max(1, len(rev_rows))
        scale_r = month / days_r
        inflows = {t: round(sum(r.get(t, 0.0) for r in rev_rows) * scale_r, 2) for t in TAXES}
        inflows["total"] = round(sum(inflows.values()), 2)

        sp_rows = self.spend_by_day + ([self.step_spent] if any(self.step_spent.values()) else [])
        sp_rows = sp_rows[-month:]
        days_s = max(1, len(sp_rows))
        scale_s = month / days_s
        outflows = {k: round(sum(r.get(k, 0.0) for r in sp_rows) * scale_s, 2)
                    for k in ("public_works", "benefits", "interest", "transfers", "reserve_interest", "debt_repaid")}
        pol_days = max((len(p.daily) for p in self.policies.items), default=0)
        pol_sum = sum(sum(p.daily) for p in self.policies.items)
        outflows["policies"] = round(pol_sum * (month / pol_days), 2) if pol_days > 0 else 0.0
        outflows["total"] = round(sum(v for k, v in outflows.items() if k != "debt_repaid"), 2)
        return {
            "days": days_r,
            "month_steps": month,
            "inflows": inflows,
            "outflows": outflows,
            "net": round(inflows["total"] - outflows["total"], 2),
        }

    def tax(self, kind, base):
        """The tax due on ``base`` money of ``kind`` ("production", "wage" or "profit")."""
        rate = getattr(self, f"tax_{kind}")
        return base * rate if base > 0 and rate > 0 else 0.0

    def collect(self, kind, amount):
        if amount > 0:
            self.treasury += amount
            self.revenue[kind] += amount
            self.step_revenue[kind] += amount

    def spend(self, kind, amount):
        """Pay ``amount`` for ``kind``: from the treasury, the rest with new money. Returns the
        newly created part."""
        from_treasury = min(self.treasury, amount)
        self.treasury -= from_treasury
        created = amount - from_treasury
        if created < 1e-9:              # (float noise, not new money)
            self.treasury = max(0.0, self.treasury - created)
            created = 0.0
        self.money_created += created
        self.last_spent += created
        self.spent[kind] += amount
        self.step_spent[kind] += amount
        return created

    def taylor_rate(self, world):
        """The yearly rate the Taylor rule asks for now, and its inputs: (rate, inflation,
        unemployment, output gap); None before a quarter of national accounts exists."""
        hist = world.recorder.history
        if not hist or hist[-1].get("accounts_steps", 0) < 3 * world.rules.month_steps:
            return None
        inflation = hist[-1]["inflation"]
        recent = list(hist)[-world.rules.month_steps:]
        unemployment = sum(s["unemployment"] for s in recent) / len(recent)
        gap = -2.0 * (unemployment - self.taylor_unemployment)              # Okun's law
        rate = self.neutral_rate + inflation + 0.5 * (inflation - self.inflation_target) + 0.5 * gap
        return max(0.0, min(0.20, rate)), inflation, unemployment, gap

    def monthly(self, world):
        """Once a month: the central bank resets its rate by the Taylor rule (when on)."""
        if not (self.enabled and self.taylor_enabled):
            return
        found = self.taylor_rate(world)
        if found is None:
            return
        rate, inflation, unemployment, gap = found
        before = (1 + self.min_rate) ** world.year_steps() - 1
        self.set("min_rate", (1 + rate) ** (1 / world.year_steps()) - 1)
        self.taylor_last = {"rate": rate, "inflation": inflation, "unemployment": unemployment, "gap": gap}
        if abs(rate - before) >= 0.0025:
            world.log(f"Central bank {'raised' if rate > before else 'cut'} its rate to {rate:.2%} a year "
                      f"(inflation {inflation:.1%}, unemployment {unemployment:.0%})")

    def borrow_for(self, world, amount):
        """Make sure the treasury holds ``amount``: sell bonds for what is missing (if allowed)."""
        short = amount - self.treasury
        if short > 1e-6 and self.bonds_enabled:
            self.debt.borrow(world, short)

    def to_dict(self, world=None):
        return {"enabled": self.enabled, **self._policy,
                "money_created": self.money_created, "labor_bought": self.labor_bought,
                "last_spent": self.last_spent, "treasury": round(self.treasury, 2),
                "approval": round(self.approval, 4),
                "approval_breakdown": dict(self.approval_breakdown),
                "budget_month": self.budget_month(world),
                "revenue": {k: round(v, 2) for k, v in self.revenue.items()},
                "step_revenue": {k: round(v, 2) for k, v in self.step_revenue.items()},
                "spent": {k: round(v, 2) for k, v in self.spent.items()},
                "llr_outstanding": round(self.llr_outstanding, 2), "llr_lent": round(self.llr_lent, 2),
                "cb_income": round(self.cb_income, 2),
                "policies": self.policies.to_dict(),
                "taylor": self.taylor_last,
                "debt": self.debt.to_dict(world) if world is not None else None,
                "policy_options": POLICY_OPTIONS,
                "revenue_month": round(sum(self.revenue_days) * 30 / max(1, len(self.revenue_days)), 2),
                "step_spent": {k: round(v, 2) for k, v in self.step_spent.items()}}
