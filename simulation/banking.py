"""Banks: an industry that takes deposits and makes loans.

A bank is an industry like any other. Its plant ("banking" asset shares) is built from
capital goods and run with labour and electricity, and it makes "banking services"
(the banking good). Those services are what lending uses up: every loan of
rules.loan_per_service money takes one unit, and units nobody uses expire. The good
can't be traded: each bank only uses its own.

Opening a bank needs two things:
- banking asset shares (at least MIN_BANK_SHARES), whether owned from the start or
  built from machinery and construction like any other industry;
- the founder's own money: at least rules.bank_min_capital is moved into the bank as
  its capital (equity). This is the Basel-style minimum capital. Borrowed money can't
  be used.

How a bank works (all per step, rates per step):
- Deposits. Agents with cash well above what they need on hand put deposit_share of
  the excess in the nearest open bank, and take it out when they are short or want
  to invest or build. Deposits earn the deposit rate, max(rules.deposit_rate, the
  government's minimum rate), on the share of them the bank has lent out (interest
  it earns from loans; idle cash earns nothing).
- Loans. Investors starting a building project can borrow what their own money doesn't
  cover, when the asset's yield beats the loan rate (deposit rate + loan_spread), up to
  max_loan_to_value of their assets. Agents that can't pay for what they need right now
  (consumer_credit) can borrow the gap, unsecured. Steps are days: nobody may owe more
  than loan_income_share (default 40%) of its monthly income (income per step x
  month_steps), whatever the loan is for. The bank lends only when:
    1. reserves stay at least reserve_ratio x deposits (cash kept for withdrawals);
    2. equity stays at least the central bank's capital ratio x loans (Basel) and at
       least bank_min_capital;
    3. it has the banking services to handle it (loan / loan_per_service units);
    4. the borrower can carry it (collateral or income, above).
  A loan is repaid over loan_steps steps: each step interest on the balance plus
  1/(steps left) of it. A borrower that can't pay for default_steps steps in a row
  defaults: the bank's owner takes asset shares worth the debt (paying the bank their
  value, as far as it can) and the rest is written off.
- Money creation. Lent money is spent and deposited again, so deposits can grow to
  about 1 / reserve_ratio times the cash put in (the money multiplier).
- Profit. Interest received minus interest paid. Each step the owner takes its
  payout_ratio (a personality trait) of the step's profit as a dividend; the rest is
  retained as equity, which raises how much the bank may lend (capital ratio).
- Failure. A bank whose equity (reserves + loans - deposits) falls below 0 fails: it
  stops lending and taking deposits and pays depositors back, pro rata, from whatever
  comes in. A bank also winds down when banking is switched off or its owner dies.
  An empty bank closes; its owner gets back any capital left.
"""
import math

from . import economy

# An agent needs at least this many banking shares to run a bank.
MIN_BANK_SHARES = 0.05
# Agents keep this many times their cash needs on hand before depositing anything.
DEPOSIT_KEEP = 2.0
# Deposits and withdrawals smaller than this aren't worth a trip to the bank.
MIN_DEPOSIT = 10.0


class Loan:
    def __init__(self, loan_id, bank, borrower, amount, rate, steps, tick, purpose):
        self.id = loan_id
        self.bank_id = bank.id
        self.borrower_id = borrower.id
        self.borrower_name = borrower.name
        self.principal = amount
        self.balance = amount
        self.rate = rate
        self.steps_left = steps
        self.missed = 0
        self.started = tick
        self.purpose = purpose

    def payment(self):
        """Interest on the balance plus an even share of it over the steps left."""
        return self.balance * self.rate + self.balance / max(1, self.steps_left)

    def to_dict(self):
        return {"id": self.id, "bank_id": self.bank_id, "borrower": self.borrower_name,
                "principal": round(self.principal, 2), "balance": round(self.balance, 2),
                "rate": self.rate, "steps_left": self.steps_left, "missed": self.missed,
                "started": self.started, "purpose": self.purpose}


class Bank:
    def __init__(self, bank_id, owner, capital, tick):
        self.id = bank_id
        self.owner_id = owner.id
        self.name = f"Bank of {owner.name}"
        self.reserves = capital          # cash the bank holds itself (vault)
        self.cb_reserves = 0.0           # its account at the central bank (required reserves)
        self.cb_loans = 0.0              # what it owes the central bank (lender of last resort)
        self.bonds = 0.0                 # government bonds it holds (lent to the government; bonds.py)
        self.cb_interest = 0.0           # interest paid to the central bank so far
        self.capital_in = capital        # what the founder put in
        self.deposits = {}               # agent id -> balance
        self.loans = []
        self.status = "open"             # open | winding down | failed
        self.opened = tick
        self.interest_received = 0.0
        self.interest_paid = 0.0
        self.dividends = 0.0
        self.written_off = 0.0
        self.retained = 0.0              # profits kept as equity (not paid out)
        self.last_equity = capital       # equity after last step's dividend

    @property
    def deposit_total(self):
        return sum(self.deposits.values())

    @property
    def loan_total(self):
        return sum(l.balance for l in self.loans)

    @property
    def equity(self):
        """Assets (vault cash + central bank account + loans + government bonds) minus debts
        (deposits + central bank loans)."""
        return self.reserves + self.cb_reserves + self.loan_total + self.bonds - self.deposit_total - self.cb_loans

    def to_dict(self, world):
        owner = world.agent_by_id(self.owner_id)
        return {"id": self.id, "name": self.name, "owner": owner.name if owner else None,
                "status": self.status, "opened": self.opened,
                "reserves": round(self.reserves, 2), "deposits": round(self.deposit_total, 2),
                "cb_reserves": round(self.cb_reserves, 2), "cb_loans": round(self.cb_loans, 2),
                "bonds": round(self.bonds, 2),
                "cb_interest": round(self.cb_interest, 2),
                "loans": round(self.loan_total, 2), "equity": round(self.equity, 2),
                "capital_in": round(self.capital_in, 2), "depositors": len(self.deposits),
                "borrowers": len({l.borrower_id for l in self.loans}),
                "services": owner.inventory.count("banking") if owner else 0,
                "shares": round(owner.assets.get("banking", 0), 3) if owner else 0,
                "interest_received": round(self.interest_received, 2),
                "interest_paid": round(self.interest_paid, 2), "dividends": round(self.dividends, 2),
                "written_off": round(self.written_off, 2), "retained": round(self.retained, 2),
                "payout_ratio": owner.personality["payout_ratio"] if owner else None,
                "loan_list": [l.to_dict() for l in self.loans[:20]]}


class Banking:
    """All the banks in the world. Live settings (on/off, rates) start from the rules and can
    be changed while the game runs."""

    def __init__(self, rules, government=None):
        self.gov = government
        self.enabled = rules.banking_enabled
        self.deposit_rate = rules.deposit_rate
        self.loan_spread = rules.loan_spread
        self.liquidity = rules.bank_liquidity   # vault cash each bank keeps (share of deposits)
        self.min_capital = rules.bank_min_capital
        self.loan_income_share = rules.loan_income_share
        self.banks = []
        self.closed = 0
        self.failed = 0
        self.blocked = set()   # agents told they can't open a bank (so the log says it once)
        self.next_bank_id = 1
        self.next_loan_id = 1

    # ---------- rates and lookups ----------

    def available(self, world):
        """Banking exists in this game (its industry wasn't left out) and is switched on."""
        return self.enabled and world.rules.is_active("banking")

    def deposit_rate_now(self, world):
        return max(self.deposit_rate, world.government.min_rate)

    def loan_rate_now(self, world):
        return self.deposit_rate_now(world) + self.loan_spread

    def open_banks(self):
        return [b for b in self.banks if b.status == "open"]

    def bank_by_id(self, bank_id):
        return next((b for b in self.banks if b.id == bank_id), None)

    def nearest_open(self, world, agent, key=None):
        banks = [b for b in self.open_banks() if key is None or key(b)]
        if not banks:
            return None

        def dist(b):
            owner = world.agent_by_id(b.owner_id)
            return math.hypot(owner.x - agent.x, owner.y - agent.y) if owner else math.inf
        return min(banks, key=dist)

    def deposits_of(self, agent):
        return sum(b.deposits.get(agent.id, 0.0) for b in self.banks)

    def payments_of(self, agent):
        """What the agent's loans cost it per step (interest + repayment)."""
        return sum(l.payment() for b in self.banks for l in b.loans if l.borrower_id == agent.id)

    def debt_of(self, agent):
        return sum(l.balance for b in self.banks for l in b.loans if l.borrower_id == agent.id)

    # ---------- deposits ----------

    def deposit(self, world, agent, amount):
        bank = self.nearest_open(world, agent)
        if bank is None or amount < MIN_DEPOSIT:
            return 0.0
        amount = min(amount, agent.money)
        agent.money -= amount
        bank.reserves += amount
        bank.deposits[agent.id] = bank.deposits.get(agent.id, 0.0) + amount
        _sync(agent, self)
        return amount

    def withdraw(self, agent, amount):
        """Take out up to ``amount``, from the banks with the most cash first (a bank can only
        pay out the reserves it has). Returns what it got."""
        got = 0.0
        for bank in sorted(self.banks, key=lambda b: -(b.reserves + b.cb_reserves)):
            if got >= amount - 1e-9:
                break
            held = bank.deposits.get(agent.id, 0.0)
            want = min(held, amount - got)
            if want <= 0:
                continue
            self._raise_cash(bank, want)
            take = min(want, max(0.0, bank.reserves))
            if take <= 0:
                continue
            bank.reserves -= take
            bank.deposits[agent.id] = held - take
            if bank.deposits[agent.id] <= 1e-6:
                del bank.deposits[agent.id]
            agent.money += take
            got += take
        _sync(agent, self)
        return got

    def _raise_cash(self, bank, amount):
        """Get ``amount`` of vault cash: from its central bank account, then (if the central bank is
        a lender of last resort and the bank is solvent) by borrowing from the central bank."""
        short = amount - bank.reserves
        if short <= 0:
            return
        move = min(short, bank.cb_reserves)
        bank.cb_reserves -= move
        bank.reserves += move
        short -= move
        if short > 1e-9:
            self._llr(bank, short)

    def _llr(self, bank, amount):
        """The central bank lends ``amount`` of new money to a solvent bank. Returns what it lent."""
        gov = self.gov
        if gov is None or not gov.lender_of_last_resort or bank.status != "open" or bank.equity <= 0:
            return 0.0
        bank.cb_loans += amount
        bank.reserves += amount
        gov.llr_outstanding += amount
        gov.llr_lent += amount
        return amount

    def cash_up(self, agent, amount):
        """Make sure the agent holds ``amount`` in cash, withdrawing from its deposits."""
        if agent.money < amount and agent.deposits:
            self.withdraw(agent, amount - agent.money)

    # ---------- loans ----------

    def credit_limit(self, world, agent, extra_collateral=0.0):
        """How much more the agent may borrow: max_loan_to_value x (value of its asset shares,
        plus what the loan pays for) minus what it already owes."""
        prices = world.step_asset_prices()
        held = sum(shares * prices.get(g, 0.0) for g, shares in agent.assets.items())
        return max(0.0, world.rules.max_loan_to_value * (held + extra_collateral) - self.debt_of(agent))

    def income_limit(self, world, agent):
        """How much more the agent may borrow on its income: loan_income_share of a month's
        income (income per step x month_steps) minus what it already owes."""
        monthly = agent.income_avg * world.rules.month_steps
        return max(0.0, self.loan_income_share * monthly - self.debt_of(agent))

    def required(self, bank):
        """Reserves the central bank requires the bank to hold in its account there."""
        return (self.gov.reserve_requirement if self.gov else 0.0) * bank.deposit_total

    def lendable(self, world, bank):
        """Most a bank can lend now (reserve ratio, capital ratio, banking services)."""
        owner = world.agent_by_id(bank.owner_id)
        if owner is None or bank.status != "open":
            return 0.0
        # Vault cash above its own liquidity buffer; nothing while it misses the reserve requirement
        # or owes the central bank.
        by_reserves = bank.reserves - self.liquidity * bank.deposit_total
        if bank.cb_loans > 0 or bank.cb_reserves < self.required(bank) - 0.01:
            by_reserves = 0.0
        basel = world.government.capital_ratio    # set by the central bank
        by_capital = (bank.equity / basel - bank.loan_total if basel > 0 else math.inf)
        # (A cent of slack: dividends leave equity at exactly the minimum, give or take float noise.)
        if bank.equity < self.min_capital - 0.01:
            by_capital = 0.0
        by_services = owner.inventory.count("banking") * world.rules.loan_per_service
        return max(0.0, min(by_reserves, by_capital, by_services))

    def borrow(self, world, agent, amount, purpose, extra_collateral=0.0, unsecured=False):
        """Lend the agent up to ``amount`` from the nearest open bank that can. Returns the amount.
        Secured loans (building) are limited by collateral; unsecured ones (consumption) by what
        the agent's income can repay."""
        if not self.available(world) or amount <= 0:
            return 0.0
        # Consumer loans (no collateral) are limited by income; business loans by collateral (the
        # assets it owns and the plant it builds).
        limit = self.income_limit(world, agent) if unsecured else self.credit_limit(world, agent, extra_collateral)
        amount = min(amount, limit)
        if amount < MIN_DEPOSIT:
            return 0.0
        bank = self.nearest_open(world, agent, key=lambda b: self.lendable(world, b) >= MIN_DEPOSIT
                                 and b.owner_id != agent.id)
        if bank is None:
            return 0.0
        amount = min(amount, self.lendable(world, bank))
        owner = world.agent_by_id(bank.owner_id)
        units = math.ceil(round(amount / world.rules.loan_per_service, 9))
        owner.inventory.remove("banking", min(units, owner.inventory.count("banking")))
        bank.reserves -= amount
        agent.money += amount
        loan = Loan(self.next_loan_id, bank, agent, amount, self.loan_rate_now(world), world.rules.loan_steps, world.tick, purpose)
        self.next_loan_id += 1
        bank.loans.append(loan)
        _sync(agent, self)
        world.log(f"{bank.name} lent {agent.name} {amount:.2f} for {purpose} at "
                  f"{((1 + loan.rate) ** (12 * world.rules.month_steps) - 1) * 100:.1f}% a year over "
                  f"{loan.steps_left / world.rules.month_steps:.0f} months")
        return amount

    # ---------- each step ----------

    def step(self, world):
        self._open_new(world)
        for bank in list(self.banks):
            self._central_bank(world, bank)
            self._collect(world, bank)
            owner = world.agent_by_id(bank.owner_id)
            if bank.status == "open":
                if bank.equity < 0:
                    bank.status = "failed"
                    self.failed += 1
                    world.log(f"{bank.name} failed: it owes depositors {bank.deposit_total:.2f} but has only "
                              f"{bank.reserves + bank.loan_total:.2f} in cash and loans")
                elif not self.available(world) or owner is None:
                    bank.status = "winding down"
                    world.log(f"{bank.name} is winding down" +
                              (" (banking switched off)" if owner else " (its owner died)"))
            if bank.status == "open":
                self._pay_interest(world, bank)
                self._pay_dividend(world, bank, owner)
            else:
                self._wind_down(world, bank, owner)
        if self.available(world):
            self._move_cash(world)

    def _central_bank(self, world, bank):
        """Settle with the central bank: keep the required reserves in the bank's account there
        (topping it up from the vault, or borrowing as a last resort), get interest on reserves,
        pay interest on central bank loans and repay them when it can."""
        gov = world.government
        if bank.cb_reserves > 0 and gov.reserve_rate > 0:
            interest = bank.cb_reserves * gov.reserve_rate
            gov.spend("reserve_interest", interest)
            bank.reserves += interest
        if bank.cb_loans > 0:
            interest = bank.cb_loans * (gov.min_rate + gov.llr_penalty)
            paid = min(interest, bank.reserves)
            bank.reserves -= paid
            bank.cb_interest += paid
            gov.receive(paid)
        required = self.required(bank) if bank.status == "open" else 0.0
        gap = required - bank.cb_reserves
        if gap > 0:
            move = min(gap, max(0.0, bank.reserves))
            bank.reserves -= move
            bank.cb_reserves += move
            if gap - move > 1e-9 and self._llr(bank, gap - move):
                bank.reserves -= gap - move
                bank.cb_reserves += gap - move
                world.log(f"Central bank lent {bank.name} {gap - move:.2f} to meet its reserve requirement")
        elif gap < 0:
            bank.cb_reserves += gap          # the excess goes back to the vault
            bank.reserves -= gap
        if bank.cb_loans > 0:
            spare = bank.reserves - self.liquidity * bank.deposit_total
            repay = min(bank.cb_loans, max(0.0, spare))
            if repay > 0:
                bank.reserves -= repay
                bank.cb_loans -= repay
                gov.llr_outstanding -= repay   # the central bank's money disappears again

    def _open_new(self, world):
        if not self.available(world):
            return
        owners = {b.owner_id for b in self.banks}
        for agent in world.agents:
            if agent.id in owners or agent.assets.get("banking", 0) < MIN_BANK_SHARES:
                continue
            # The minimum capital is the founder's own cash (it may draw on its own deposits).
            self.cash_up(agent, self.min_capital)
            if agent.money < self.min_capital:
                if agent.id not in self.blocked:
                    self.blocked.add(agent.id)
                    world.log(f"{agent.name} owns a banking plant but can't open a bank: "
                              f"needs {self.min_capital:.2f} of its own capital")
                continue
            agent.money -= self.min_capital
            bank = Bank(self.next_bank_id, agent, self.min_capital, world.tick)
            self.next_bank_id += 1
            self.banks.append(bank)
            self.blocked.discard(agent.id)
            world.log(f"{agent.name} opened {bank.name} with {self.min_capital:.2f} of capital")

    def _collect(self, world, bank):
        """Borrowers pay interest and principal, but only out of money left after what they need
        to buy right now (food and water come before debt); long-unpaid loans default."""
        prices = world.current_prices()
        for loan in list(bank.loans):
            borrower = world.agent_by_id(loan.borrower_id)
            if borrower is None:
                self._write_off(world, bank, loan, "its borrower died")
                continue
            due = loan.payment()
            needs_now = economy.shopping_cost(borrower, prices, world.rules)
            self.cash_up(borrower, due + needs_now)
            if borrower.money - needs_now + 1e-9 < due:
                loan.missed += 1
                if loan.missed >= world.rules.default_steps:
                    self._default(world, bank, loan, borrower)
                continue
            interest = loan.balance * loan.rate
            borrower.money -= due
            bank.reserves += due
            bank.interest_received += interest
            loan.balance -= due - interest
            loan.steps_left -= 1
            loan.missed = 0
            if loan.balance <= 0.01 or loan.steps_left <= 0:
                bank.loans.remove(loan)
            _sync(borrower, self)

    def _default(self, world, bank, loan, borrower):
        """The bank's owner takes asset shares worth the debt and pays the bank their value
        (as far as it can); the rest is written off."""
        owner = world.agent_by_id(bank.owner_id)
        prices = world.step_asset_prices()
        recovered = 0.0
        taken = {}
        for good in sorted(borrower.assets, key=lambda g: -prices.get(g, 0.0)):
            price = prices.get(good, 0.0)
            if price <= 0 or recovered >= loan.balance or owner is None:
                continue
            shares = min(borrower.assets[good], (loan.balance - recovered) / price)
            value = min(shares * price, owner.money)
            if value <= 0:
                break
            shares = value / price
            borrower.assets[good] -= shares
            if borrower.assets[good] <= 1e-9:
                del borrower.assets[good]
            owner.assets[good] = owner.assets.get(good, 0.0) + shares
            owner.money -= value
            bank.reserves += value
            recovered += value
            taken[good] = shares
        lost = loan.balance - recovered
        bank.written_off += lost
        bank.loans.remove(loan)
        _sync(borrower, self)
        seized = ", ".join(f"{n:.2f} {g}" for g, n in taken.items()) or "nothing"
        world.log(f"{borrower.name} defaulted on {bank.name}: {seized} taken (worth {recovered:.2f}), "
                  f"{lost:.2f} written off")

    def _write_off(self, world, bank, loan, why):
        bank.written_off += loan.balance
        bank.loans.remove(loan)
        world.log(f"{bank.name} wrote off {loan.balance:.2f} lent to {loan.borrower_name} ({why})")

    def _pay_interest(self, world, bank):
        """Depositors earn the deposit rate on the part of deposits the bank has lent out (a bank
        can only pay interest it earns: cash sitting in its vault earns nothing)."""
        rate = self.deposit_rate_now(world)
        total = bank.deposit_total
        if rate <= 0 or total <= 0 or not bank.loans:
            return
        rate *= min(1.0, bank.loan_total / total)
        for agent_id, balance in bank.deposits.items():
            interest = balance * rate
            bank.deposits[agent_id] = balance + interest
            bank.interest_paid += interest
        for agent_id in bank.deposits:
            agent = world.agent_by_id(agent_id)
            if agent is not None:
                _sync(agent, self)

    def _pay_dividend(self, world, bank, owner):
        """The owner's payout_ratio (a personality trait) of this step's profit is paid out as a
        dividend; the rest is retained as equity, which lets the bank lend more (capital ratio).
        Never below the capital it must keep, and only from cash it can spare."""
        profit = bank.equity - bank.last_equity
        dividend = 0.0
        if profit > 0:
            # Profit tax first (paid from its cash).
            tax = min(world.government.tax("profit", profit), max(0.0, bank.reserves))
            if tax > 0:
                bank.reserves -= tax
                world.government.collect("profit", tax)
                profit -= tax
            keep = max(self.min_capital, world.government.capital_ratio * bank.loan_total)
            cash = bank.reserves - self.liquidity * bank.deposit_total
            dividend = min(owner.personality["payout_ratio"] * profit, bank.equity - keep, cash)
            if dividend > 0.01:
                bank.reserves -= dividend
                owner.money += dividend
                economy.earn(owner, dividend, "banking")
                bank.dividends += dividend
            else:
                dividend = 0.0
            bank.retained += profit - dividend
        bank.last_equity = bank.equity

    def _wind_down(self, world, bank, owner):
        """Pay depositors back pro rata from the cash it has (after repaying the central bank);
        close once nothing is left."""
        bank.reserves += bank.cb_reserves
        bank.cb_reserves = 0.0
        if bank.cb_loans > 0:
            repay = min(bank.cb_loans, bank.reserves)
            bank.reserves -= repay
            bank.cb_loans -= repay
            world.government.llr_outstanding -= repay
        total = bank.deposit_total
        if total > 0 and bank.reserves > 0:
            paid = min(bank.reserves, total)
            for agent_id, balance in list(bank.deposits.items()):
                share = balance / total * paid
                bank.deposits[agent_id] = balance - share
                agent = world.agent_by_id(agent_id)
                if agent is not None:
                    agent.money += share
                if bank.deposits[agent_id] <= 1e-6:
                    del bank.deposits[agent_id]
                if agent is not None:
                    _sync(agent, self)
            bank.reserves -= paid
        if bank.loans:
            return
        if bank.cb_loans > 1e-9 and bank.reserves <= 1e-9:
            # Nothing left to repay the central bank with: that new money stays out there.
            world.government.llr_outstanding -= bank.cb_loans
            world.government.money_created += bank.cb_loans
            bank.cb_loans = 0.0
        if bank.status == "failed" and bank.deposits and bank.reserves <= 1e-6:
            # Nothing left to pay with: depositors lose the rest.
            for agent_id in list(bank.deposits):
                agent = world.agent_by_id(agent_id)
                del bank.deposits[agent_id]
                if agent is not None:
                    _sync(agent, self)
        if not bank.deposits:
            if owner is not None and bank.reserves > 0:
                owner.money += bank.reserves
            self.banks.remove(bank)
            self.closed += 1
            world.log(f"{bank.name} closed")

    def _move_cash(self, world):
        """Agents short of cash take some out; agents with plenty put some in."""
        from .modules.invest import cash_needed
        prices = world.current_prices()
        rules = world.rules
        has_open = bool(self.open_banks())
        for agent in world.agents:
            need = cash_needed(agent, prices, rules)
            if agent.money < need and agent.deposits:
                self.withdraw(agent, DEPOSIT_KEEP * need - agent.money)
            behind = agent.debt and any(l.missed for b in self.banks for l in b.loans if l.borrower_id == agent.id)
            if rules.consumer_credit and has_open and agent.money < need and not behind:
                # Can't pay for what it needs right now: borrow the gap (if its income allows).
                short = economy.shopping_cost(agent, prices, rules) - agent.money
                if short >= MIN_DEPOSIT:
                    self.borrow(world, agent, short, "consumption", unsecured=True)
            elif has_open:
                keep = DEPOSIT_KEEP * need + rules.min_investment
                if agent.money > keep + MIN_DEPOSIT:
                    self.deposit(world, agent, rules.deposit_share * (agent.money - keep))

    # ---------- deaths ----------

    def forget(self, world, agent):
        """A dead or removed agent's deposits stay with the bank; its loans are written off."""
        for bank in self.banks:
            bank.deposits.pop(agent.id, None)
            for loan in [l for l in bank.loans if l.borrower_id == agent.id]:
                self._write_off(world, bank, loan, "its borrower is gone")
        agent.deposits = {}

    # ---------- state ----------

    def to_dict(self, world):
        open_banks = self.open_banks()
        cash = sum(a.money + a.company_cash for a in world.agents)   # people's and companies' cash
        deposits = sum(b.deposit_total for b in self.banks)
        reserves = sum(b.reserves + b.cb_reserves for b in self.banks)
        return {
            "enabled": self.enabled, "available": self.available(world),
            "industry_active": world.rules.is_active("banking"),
            "deposit_rate": self.deposit_rate, "loan_spread": self.loan_spread,
            "liquidity": self.liquidity, "reserve_requirement": world.government.reserve_requirement,
            "capital_ratio": world.government.capital_ratio,
            "lender_of_last_resort": world.government.lender_of_last_resort,
            "cb_reserves": round(sum(b.cb_reserves for b in self.banks), 2),
            "cb_loans": round(sum(b.cb_loans for b in self.banks), 2),
            "min_capital": self.min_capital, "loan_income_share": self.loan_income_share,
            "month_steps": world.rules.month_steps,
            "deposit_rate_now": self.deposit_rate_now(world), "loan_rate_now": self.loan_rate_now(world),
            "banks": [b.to_dict(world) for b in self.banks], "open": len(open_banks),
            "closed": self.closed, "failed": self.failed,
            "deposits": round(deposits, 2), "loans": round(sum(b.loan_total for b in self.banks), 2),
            "reserves": round(reserves, 2),
            # Money people can spend (cash + deposits) per unit of base money (cash + bank reserves).
            "money_supply": round(cash + deposits, 2),
            "multiplier": round((cash + deposits) / (cash + reserves), 3) if cash + reserves > 0 else 1.0,
        }


def _sync(agent, banking):
    """Keep agent.deposits ({bank id: balance}) in step with the banks' books."""
    agent.deposits = {b.id: b.deposits[agent.id] for b in banking.banks if agent.id in b.deposits}
    agent.debt = banking.debt_of(agent)
