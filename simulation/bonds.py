"""Government bonds: how the government borrows.

When the treasury can't pay for what the government has promised (its spending policies and the
unemployment benefit), it sells bonds for the shortfall, as long as its debt stays under
``debt_limit`` x a year's nominal GDP:

- buyers: commercial banks first, with vault cash beyond what they keep for depositors (a bond is
  a safe asset: it counts in a bank's equity and carries no capital requirement), then agents
  with money (bank deposits included) above their monthly budget, richest first;
- rate: the central bank's policy rate + ``bond_spread``, fixed for the bond's life, so the
  central bank's rate sets what the government pays to borrow;
- interest is paid every day from the treasury, borrowing it if taxes don't cover it (new money
  only if nobody will lend: the central bank stands behind its government);
- after ``bond_days`` a bond is repaid from the treasury, or rolled over (the holder gets a new
  bond at today's rate) when the treasury can't repay it;
- with a balanced budget, taxes left after spending repay debt early (soonest maturity first)
  before buying more public works.

Selling bonds only moves money (from buyers to the treasury), it doesn't create any. A dead
agent's bonds are cancelled with the rest of its estate's money.
"""
from . import economy


class Bond:
    __slots__ = ("id", "holder", "principal", "rate", "issued", "due")

    def __init__(self, bid, holder, principal, rate, issued, due):
        self.id, self.holder, self.principal, self.rate = bid, holder, principal, rate
        self.issued, self.due = issued, due


def _is_bank(holder):
    return hasattr(holder, "deposits") and hasattr(holder, "cb_reserves")


class PublicDebt:
    def __init__(self):
        self.bonds = []
        self.next_id = 1
        self.issued = 0.0          # all bonds ever sold
        self.repaid = 0.0          # principal paid back
        self.interest_paid = 0.0
        self.step_interest = 0.0
        self.step_borrowed = 0.0
        self.step_repaid = 0.0
        self.unsold = 0.0          # borrowing wanted that nobody would (or could) lend, so far

    @property
    def total(self):
        return sum(b.principal for b in self.bonds)

    def held_by(self, holder):
        return sum(b.principal for b in self.bonds if b.holder is holder)

    # ---------- limits and rates ----------

    @staticmethod
    def yearly_gdp(world):
        """Real GDP over a year (at year-ago prices, annualised before a year has passed): the
        debt limit doesn't grow with inflation."""
        h = world.recorder.history
        if not h or not h[-1].get("accounts_steps"):
            return 0.0
        return h[-1]["gdp_real"] * world.year_steps() / h[-1]["accounts_steps"]

    def room(self, world):
        """How much more the government may borrow under its debt limit."""
        gov = world.government
        if not gov.bonds_enabled:
            return 0.0
        return max(0.0, gov.debt_limit * self.yearly_gdp(world) - self.total)

    @staticmethod
    def rate(world):
        """Daily rate on a new bond: the policy rate + the spread."""
        gov = world.government
        return gov.min_rate + gov.bond_spread

    # ---------- borrowing ----------

    def borrow(self, world, amount):
        """Sell bonds for up to ``amount`` into the treasury. Returns what was raised."""
        amount = min(amount, self.room(world))
        if amount <= 1e-6:
            return 0.0
        gov, rules = world.government, world.rules
        rate = self.rate(world)
        raised = 0.0
        for holder, spare in self._lenders(world):
            if raised >= amount - 1e-9:
                break
            take = min(spare, amount - raised)
            if take <= 1e-6:
                continue
            if _is_bank(holder):
                holder.reserves -= take
                holder.bonds += take
            else:
                world.banking.cash_up(holder, take)
                take = min(take, holder.money)
                holder.money -= take
            due = world.tick + gov.bond_days
            same = next((b for b in reversed(self.bonds) if b.holder is holder and b.due == due and b.rate == rate), None)
            if same:
                same.principal += take          # bought more of today's issue
            else:
                self.bonds.append(Bond(self.next_id, holder, take, rate, world.tick, due))
                self.next_id += 1
            raised += take
        gov.treasury += raised
        self.issued += raised
        self.step_borrowed += raised
        self.unsold += amount - raised
        if raised > 0:
            world.log(f"Government sold {raised:,.2f} of bonds at {self.rate_year(world):.2%} a year "
                      f"(debt now {self.total:,.2f})")
        return raised

    def sell_to(self, world, holder, amount):
        """A saver buys bonds with idle money (up to the debt limit). Returns what it lent."""
        gov = world.government
        if not gov.enabled or not gov.bonds_enabled:
            return 0.0
        amount = min(amount, self.room(world))
        if amount < world.rules.min_investment:
            return 0.0
        world.banking.cash_up(holder, amount)
        amount = min(amount, holder.money)
        if amount <= 0:
            return 0.0
        holder.money -= amount
        rate, due = self.rate(world), world.tick + gov.bond_days
        same = next((b for b in reversed(self.bonds) if b.holder is holder and b.due == due and b.rate == rate), None)
        if same:
            same.principal += amount
        else:
            self.bonds.append(Bond(self.next_id, holder, amount, rate, world.tick, due))
            self.next_id += 1
        gov.treasury += amount
        self.issued += amount
        self.step_borrowed += amount
        return amount

    def rate_year(self, world):
        return (1 + self.rate(world)) ** world.year_steps() - 1

    def _lenders(self, world):
        """(holder, money it can lend): banks with spare vault cash, then agents with money above
        their budget, richest first."""
        from .modules.invest import budget_needed
        out = []
        banking = world.banking
        for bank in banking.open_banks():
            if bank.cb_loans > 0:
                continue
            spare = bank.reserves - banking.liquidity * bank.deposit_total - banking.required(bank)
            if spare > 0:
                out.append((bank, spare))
        # Savers with money beyond their budget, richest first (worked out once a day; what they
        # lend today is taken off below).
        cache = world._step_cache
        people = cache.get("bond_savers") if cache else None
        if people is None:
            prices = world.current_prices()
            floor = world.rules.min_investment
            people = []
            for a in world.agents:
                money = economy.money_of(a)
                if money > floor:
                    spare = money - budget_needed(a, prices, world)
                    if spare > floor:
                        people.append([a, spare])
            people.sort(key=lambda t: t[1], reverse=True)
            if cache is not None:
                cache["bond_savers"] = people
        return out + [(a, min(spare, economy.money_of(a))) for a, spare in people if a in world.alive]

    # ---------- every day ----------

    def step(self, world):
        """Pay a day's interest and repay (or roll over) bonds that are due."""
        gov = world.government
        self.step_interest = self.step_borrowed = self.step_repaid = 0.0
        if not self.bonds:
            return
        alive = world.alive
        kept = []
        for b in self.bonds:
            if not _is_bank(b.holder) and b.holder not in alive:
                continue                         # died: cancelled with its estate
            if _is_bank(b.holder) and b.holder.status != "open":
                self._pay_holder(world, b.holder, b.principal, principal=True)   # a closing bank is paid back now
                gov.spend("debt_repaid", b.principal)
                self.repaid += b.principal
                continue
            kept.append(b)
        self.bonds = kept
        interest = 0.0
        for b in self.bonds:
            coupon = b.principal * b.rate
            if coupon > 0:
                self._pay_holder(world, b.holder, coupon)
                interest += coupon
        if interest > 0:
            gov.borrow_for(world, interest)        # short of taxes: borrow it (new money only if nobody lends)
            gov.spend("interest", interest)
            self.interest_paid += interest
            self.step_interest = interest
        for b in [b for b in self.bonds if b.due <= world.tick]:
            if gov.treasury >= b.principal:
                gov.treasury -= b.principal
                self._settle(world, b)
            else:                                  # roll over at today's rate
                b.rate = self.rate(world)
                b.due = world.tick + gov.bond_days

    def redeem(self, world, holder):
        """Repay every bond ``holder`` holds now (a bank winding down): from the treasury, new
        money for what it can't pay."""
        gov = world.government
        for b in [b for b in self.bonds if b.holder is holder]:
            gov.spend("debt_repaid", b.principal)
            self._pay_holder(world, holder, b.principal, principal=True)
            self.repaid += b.principal
            self.step_repaid += b.principal
            self.bonds.remove(b)

    def repay_early(self, world, money):
        """Use up to ``money`` of the treasury to repay bonds, soonest due first. Returns spent."""
        gov = world.government
        spent = 0.0
        for b in sorted(self.bonds, key=lambda b: b.due):
            if money - spent <= 1e-6:
                break
            part = min(b.principal, money - spent)
            gov.treasury -= part
            spent += part
            if part >= b.principal - 1e-9:
                self._settle(world, b)
            else:
                b.principal -= part
                self._pay_holder(world, b.holder, part, principal=True)
                self.repaid += part
                self.step_repaid += part
                gov.spent["debt_repaid"] += part
                gov.step_spent["debt_repaid"] += part
        return spent

    def _settle(self, world, b):
        """Repay bond ``b`` (the treasury already paid) and drop it."""
        gov = world.government
        self._pay_holder(world, b.holder, b.principal, principal=True)
        self.repaid += b.principal
        self.step_repaid += b.principal
        gov.spent["debt_repaid"] += b.principal
        gov.step_spent["debt_repaid"] += b.principal
        self.bonds.remove(b)

    @staticmethod
    def _pay_holder(world, holder, amount, principal=False):
        """Pay a holder interest, or (``principal``) part of what it lent back."""
        if _is_bank(holder):
            holder.reserves += amount
            if principal:
                holder.bonds = max(0.0, holder.bonds - amount)
        else:
            holder.money += amount
            if not principal:
                economy.earn(holder, amount, "assets")

    def to_dict(self, world):
        total = self.total
        gdp = self.yearly_gdp(world)
        return {"debt": round(total, 2), "bonds": len(self.bonds),
                "holders_banks": round(sum(b.principal for b in self.bonds if _is_bank(b.holder)), 2),
                "holders_agents": round(sum(b.principal for b in self.bonds if not _is_bank(b.holder)), 2),
                "rate": self.rate(world), "rate_year": round(self.rate_year(world), 6),
                "gdp_year": round(gdp, 2), "debt_to_gdp": round(total / gdp, 4) if gdp > 0 else 0.0,
                "room": round(self.room(world), 2), "issued": round(self.issued, 2), "repaid": round(self.repaid, 2),
                "interest_paid": round(self.interest_paid, 2), "step_interest": round(self.step_interest, 2),
                "step_borrowed": round(self.step_borrowed, 2), "step_repaid": round(self.step_repaid, 2),
                "unsold": round(self.unsold, 2)}
