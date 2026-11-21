"""Labour: a capacity every agent has, sold each step in a labour market.

Labour is never stored. Each step every agent can work up to its labour capacity
(``labor_capacity``, scaled by its efficiency). Owners first use their own labour
on their own assets; the rest of their assets' jobs are offered to the market.
Every other agent offers part of its capacity (more when it needs money more).
The market then clears once per step: employers hire the cheapest workers first
and pay cash; the government may hire some of what is left with new money. Any
capacity nobody buys is simply lost. Hired labour goes straight into the
employer's assets that step.

Agent efficiency, wellbeing and need (the "labour capacity" module)
- efficiency = 1 - sum(weight[n] x need level n) - depression penalty, kept within
  [min_efficiency, 1]. It scales how much labour the agent can actually give.
- wellbeing = 1 - weighted average of its needs - depression penalty, in [0, 1].
- general need (for a job) = money_weight x how far its money is below a cushion of
  comfort_steps steps' cost of living + (1 - money_weight) x how pressing its needs
  are. Higher need -> it offers more of its capacity (labour supply) and asks less.
- willingness = participation_floor + (1 - participation_floor) x general need:
  the share of its free capacity it offers.
- asking wage = market wage x (1 + bargaining_spread x (wellbeing - general need)):
  agents who are well and don't need money ask more; desperate agents accept less.

Market wage
- base = labor_share x value one unit of labour produces (units per labour x price
  of the good, averaged over the jobs on offer).
- pressure = ((labour wanted + 1) / (capacity offered + 1)) ** price_elasticity[labor]:
  more capacity for the same jobs lowers the wage; more jobs raise it.
- the wage multiplier moves price_adjust_speed of the way toward the pressure each
  step, kept within [price_floor, price_cap]; wage = base x multiplier. With fixed
  prices the wage is fixed_prices[labor].
"""
import math


from . import economy, penalties

from .rules import NEEDS as NEEDS_FOR_WELLBEING


def efficiency(agent, rules):
    drag = sum(rules.efficiency_weights.get(n, 0) * getattr(agent, n) for n in NEEDS_FOR_WELLBEING)
    if agent.depressed:
        drag += rules.depression_penalty
    return min(1.0, max(rules.min_efficiency, 1 - drag))


def wellbeing(agent, rules):
    weights = rules.efficiency_weights
    total = sum(weights.values()) or 1
    level = sum(weights.get(n, 0) * getattr(agent, n) for n in NEEDS_FOR_WELLBEING) / total
    if agent.depressed:
        level += rules.depression_penalty
    return min(1.0, max(0.0, 1 - level))


def cost_of_living(agent, prices, rules):
    """Money per step the agent would spend buying all the goods it uses."""
    return economy.living_cost(agent, prices, rules)


def general_need(agent, prices, rules):
    """How much the agent needs a job, 0..1: short of money and/or pressing needs."""
    cushion = rules.comfort_steps * cost_of_living(agent, prices, rules)
    money_short = min(1.0, max(0.0, 1 - economy.money_of(agent) / cushion)) if cushion > 0 else 0.0
    pressing = max((getattr(agent, n) for n in rules.consumer_needs), default=0.0)
    return rules.money_weight * money_short + (1 - rules.money_weight) * pressing


class LaborMarket:
    def __init__(self):
        self.multiplier = 1.0
        self.wage = 0.0
        self.stats = self._empty_stats()
        # Wages earned and not yet paid (weekly or monthly pay): {(employer id, worker id): money}.
        self.payroll = {}
        self.paid_last = 0.0      # wages paid on the latest payday
        self.unpaid_last = 0.0    # ... and what employers couldn't pay then (arrears)

    @staticmethod
    def pay_days(world):
        """Days between paydays under the government's pay law (1 = paid every day)."""
        period = world.government.pay_period
        return {"weekly": 7, "monthly": world.rules.month_steps}.get(period, 1)

    def owed_by(self, agent_id):
        return sum(v for (e, _), v in self.payroll.items() if e == agent_id)

    def owed_to(self, agent_id):
        return sum(v for (_, w), v in self.payroll.items() if w == agent_id)

    def payday(self, world):
        """Employers pay the wages earned since the last payday; the salary tax is withheld from
        each payment. What an employer can't pay stays owed (arrears) until the next payday. Wages
        owed by or to an agent that died are lost."""
        gov = world.government
        by_employer = {}
        for (e, w), owed in self.payroll.items():
            by_employer.setdefault(e, []).append((w, owed))
        self.payroll, paid, unpaid = {}, 0.0, 0.0
        for e, lines in by_employer.items():
            employer = world.agent_by_id(e)
            if employer is None:
                continue
            total = sum(o for _, o in lines)
            if employer.company_cash:
                economy.draw_company_cash(employer, total)
            if employer.deposits and employer.money < total:
                world.banking.cash_up(employer, total)
            for w, owed in lines:
                worker = world.agent_by_id(w)
                if worker is None:
                    continue
                pay = min(owed, max(0.0, employer.money))
                if pay > 0:
                    employer.money -= pay
                    tax = gov.tax("wage", pay)
                    gov.collect("wage", tax)
                    worker.money += pay - tax
                    economy.earn(worker, pay - tax, "wages")
                    paid += pay
                if owed - pay > 1e-9:
                    self.payroll[(e, w)] = owed - pay
                    unpaid += owed - pay
        self.paid_last, self.unpaid_last = paid, unpaid
        if unpaid > 0.01:
            world.log(f"Payday: {paid:,.2f} of wages paid, {unpaid:,.2f} owed by employers short of cash")

    @staticmethod
    def _empty_stats():
        return {"capacity": 0.0, "own_use": 0.0, "offered": 0.0, "wanted": 0.0, "hired": 0.0,
                "wanted_full": 0.0, "job_capacity": 0.0, "jobs_funded": 0.0,
                "gov_hired": 0.0, "benefits": 0.0, "subsistence": 0.0, "unused": 0.0, "withheld": 0.0, "idle": 0.0, "hires": 0, "workers_hired": 0, "base_wage": 0.0, "pressure": 1.0}

    def base_wage(self, world, prices, jobs):
        """labor_share x value added by one unit of labour (output minus the inputs it used),
        weighted by the jobs on offer."""
        rules = world.rules
        weights = {g: jobs.get(g, 0) for g in world.rules.active_goods}
        if sum(weights.values()) <= 0:
            weights = {g: 1 for g in world.rules.active_goods}
        value = sum(w * world.productivity_now[g] * world.value_added(g, prices)
                    for g, w in weights.items()) / sum(weights.values())
        return rules.labor_share * value

    def clear(self, world):
        """Run this step's labour market. Sets agent.labor_available and labour flows."""
        from .modules.invest import cash_needed  # local import: invest imports economy, not labor
        rules = world.rules
        prices = world.current_prices(include_labor=False)
        stats = self._empty_stats()
        period = self.pay_days(world)
        if self.payroll and (period == 1 or world.tick % period == 0):
            self.payday(world)                 # wages earned since the last payday
        owed = {}
        for (e, _), v in self.payroll.items():
            owed[e] = owed.get(e, 0.0) + v
        offers, employers, jobs_by_good = [], [], {}

        for a in world.agents:
            a.efficiency = efficiency(a, rules)
            a.wellbeing = wellbeing(a, rules)
            a.job_need = general_need(a, prices, rules)
            # Unmet needs cut what it can give (hungry, tired, sick, cold, depressed: penalties.py).
            a.capacity_now = a.labor_capacity * a.efficiency * penalties.labor_factor(a, rules)
            # Jobs its industries can actually use: secondary ones only as far as their inputs go.
            jobs = {g: world.usable_jobs(a, g) for g in a.assets if g in economy.GOODS}
            a.labor_need = sum(jobs.values())
            a.output_capacity = {g: world.asset_output(g, s) for g, s in a.assets.items() if g in economy.GOODS}
            for g, j in jobs.items():
                jobs_by_good[g] = jobs_by_good.get(g, 0) + j
            own = min(a.capacity_now, a.labor_need)
            a.labor_available = own
            a.labor_sold = 0.0
            a.labor_bought = 0.0
            a.employers = {}
            stats["capacity"] += a.capacity_now
            stats["own_use"] += own
            a.flow["labor_made"] += a.capacity_now
            a.flow["labor_used"] += own
            free = a.capacity_now - own
            a.offered = free * (rules.participation_floor + (1 - rules.participation_floor) * a.job_need)
            if a.offered > 1e-9:
                offers.append(a)
            if a.labor_need - own > 1e-9:
                employers.append(a)
        stats["offered"] = sum(a.offered for a in offers)
        stats["job_capacity"] = sum(a.labor_need for a in world.agents)
        stats["wanted_full"] = sum(a.labor_need - a.labor_available for a in employers)

        base = self.base_wage(world, prices, jobs_by_good)
        # What employers actually want to hire is what they can pay for (at last step's wage),
        # not everything their assets could employ: unfunded jobs don't push wages up.
        ref_wage = self.wage if self.wage > 0 else base
        stats["wanted"] = sum(
            min(e.labor_need - e.labor_available,
                max(0.0, economy.money_of(e) - cash_needed(e, prices, rules)) / ref_wage if ref_wage > 0 else 0.0)
            for e in employers)
        stats["jobs_funded"] = stats["own_use"] + stats["wanted"]

        # Market wage.
        pressure = economy.demand_pressure(stats["wanted"], stats["offered"], economy.LABOR, rules)
        if rules.price_mode == "fixed":
            self.multiplier, base = 1.0, rules.fixed_prices[economy.LABOR]
        elif rules.demand_pricing_enabled:
            target = min(max(pressure, rules.price_floor), rules.price_cap)
            self.multiplier += rules.price_adjust_speed * (target - self.multiplier)
        else:
            self.multiplier = 1.0
        # A minimum wage (government policy) is a floor: nobody works for less.
        self.wage = max(base * self.multiplier, world.government.min_wage)
        stats["base_wage"], stats["pressure"] = base, pressure

        # Each worker's asking wage; the cheapest are hired first.
        for a in offers:
            a.asking_wage = max(world.government.min_wage,
                                self.wage * min(3.0, max(0.1, 1 + rules.bargaining_spread * (a.wellbeing - a.job_need))))
        offers.sort(key=lambda a: a.asking_wage)
        remaining = {a: a.offered for a in offers}
        # Employers whose labour creates the most value hire first (as if they outbid the
        # others): a good that becomes scarce gets dearer, and its producers get workers first.
        # Ties (and equal values) are broken at random.
        world.rng.shuffle(employers)
        if rules.labor_priority == "value":
            employers.sort(key=lambda e: world.labor_value(e, prices), reverse=True)
        for employer in employers:
            want = employer.labor_need - employer.labor_available
            need = cash_needed(employer, prices, rules)
            # Wages come out of company cash (retained earnings) first, then the owner's money.
            # Wages it already owes (weekly or monthly pay) aren't free to spend on more hiring.
            budget = max(0.0, economy.money_of(employer) + employer.company_cash - need - owed.get(employer.id, 0.0))
            if budget > 0 and employer.company_cash:
                economy.draw_company_cash(employer, min(budget, want * ref_wage * 2))
            if budget > 0 and employer.deposits:
                # Wages are paid in cash: take what's needed out of the bank.
                world.banking.cash_up(employer, need + min(budget, want * ref_wage * 2))
            budget = min(budget, max(0.0, employer.money - need - owed.get(employer.id, 0.0)))
            for worker in offers:
                if want <= 1e-9 or budget <= 1e-9:
                    break
                if worker is employer or remaining[worker] <= 1e-9:
                    continue
                affordable = budget / worker.asking_wage if worker.asking_wage > 0 else remaining[worker]
                units = min(remaining[worker], want, affordable)
                self._hire(employer, worker, units, worker.asking_wage, stats, world.government,
                           self.payroll if period > 1 else None)
                remaining[worker] -= units
                want -= units
                budget -= units * worker.asking_wage

        # Government spending (public works, then unemployment benefits; see government.py).
        gov = world.government
        stats["gov_hired"] += self._public_works(world, offers, remaining, gov.labor_purchase, stats)
        if gov.benefit_rate > 0:
            self._benefits(world, offers, remaining, stats)
        if gov.enabled and world.agents:
            # The player's spending policies (income support, give-aways, public services).
            gov.policies.run(world, offers, remaining, stats)
        if gov.balanced_budget and gov.treasury > 1e-6 and gov.debt.bonds:
            # Taxes left over repay government debt first (soonest due first).
            gov.debt.repay_early(world, gov.treasury)
        if gov.balanced_budget and gov.treasury > 1e-6:
            # Whatever the treasury has left hires more idle labour: taxes go back into the economy.
            stats["gov_hired"] += self._public_works(world, offers, remaining, math.inf, stats, budget=gov.treasury)
        if gov.balanced_budget and gov.treasury > 1e-6 and world.agents:
            # Nobody left to hire: the rest is paid out equally to everyone (transfers).
            each = gov.treasury / len(world.agents)
            for a in world.agents:
                a.money += each
                economy.earn(a, each, "transfers")
            gov.spent["transfers"] += gov.treasury
            gov.step_spent["transfers"] += gov.treasury
            gov.treasury = 0.0

        if rules.subsistence_enabled and rules.industries_enabled:
            stats["subsistence"] = self._subsistence(world)

        # Unused capacity = withheld (not offered: the agent didn't need to work) + idle
        # (offered but nobody hired it).
        stats["unused"] = stats["capacity"] - stats["own_use"] - stats["hired"] - stats["gov_hired"]
        stats["idle"] = max(0.0, stats["offered"] - stats["hired"] - stats["gov_hired"])
        stats["withheld"] = max(0.0, stats["unused"] - stats["idle"])
        stats["workers_hired"] = sum(1 for a in offers if a.labor_sold > 1e-9)
        self.stats = stats

    @staticmethod
    def _public_works(world, offers, remaining, wanted, stats, budget=math.inf):
        """The government hires up to ``wanted`` units of the labour nobody else hired, at each
        worker's asking wage, spending at most ``budget``: from the treasury, the rest with new
        money. Returns the units hired."""
        gov = world.government
        hired = 0.0
        for worker in offers:
            if wanted - hired <= 1e-9 or budget <= 1e-9:
                break
            units = min(remaining[worker], wanted - hired)
            if worker.asking_wage > 0:
                units = min(units, budget / worker.asking_wage)
            if units <= 1e-9:
                continue
            pay = units * worker.asking_wage
            gov.spend("public_works", pay)
            budget -= pay
            tax = gov.tax("wage", pay)
            gov.collect("wage", tax)
            worker.money += pay - tax
            economy.earn(worker, pay - tax, "government")
            worker.labor_sold += units
            worker.employers["Government"] = worker.employers.get("Government", 0) + units
            remaining[worker] -= units
            hired += units
            gov.labor_bought += units
        return hired

    @staticmethod
    def _subsistence(world):
        """Agents with no assets spend the labour nobody hired making a little of a basic good on
        their own (rules.subsistence_rates units per unit of labour: fetching water, a garden,
        gathering wood or herbs, collecting stone). Each makes the good for its most urgent need
        that it holds least of. Fractions of a unit accumulate until a whole unit is made.
        Returns the labour used."""
        rules = world.rules
        options = [(g, rate) for g, rate in rules.subsistence_rates.items()
                   if rate > 0 and g in rules.active_goods and rules.need_of(g) in rules.consumer_needs]
        used = 0.0
        for a in world.agents:
            a.subsistence_made = {}
            if a.assets or not options:
                continue
            spare = a.capacity_now - a.labor_sold
            if spare <= 1e-9:
                continue
            # Most urgent need first; for a need it already has stock of, less so.
            def score(opt):
                need = rules.need_of(opt[0])
                return (economy.urgency(a, need, rules) - economy.held_relief(a, need, rules), opt[1])
            good, rate = max(options, key=score)
            made = spare * rate
            done = a.subsistence.get(good, 0.0) + made
            whole = int(done + 1e-9)
            if whole:
                a.inventory.add(good, whole)
                a.flow["produced"][good] = a.flow["produced"].get(good, 0) + whole
            a.subsistence[good] = done - whole
            a.subsistence_made[good] = made
            used += spare
        return used

    def _benefits(self, world, offers, remaining, stats):
        """Unemployment benefit: benefit_rate x the wage for every unit of labour offered and not
        hired, paid from the treasury (pro rata when it can't pay it all)."""
        gov = world.government
        wage = self.wage
        owed = {w: remaining[w] * wage * gov.benefit_rate for w in offers if remaining[w] > 1e-9}
        total = sum(owed.values())
        if total > 0:
            gov.borrow_for(world, total)      # short of taxes: sell bonds (if allowed)
        if total <= 0 or gov.treasury <= 0:
            return
        scale = min(1.0, gov.treasury / total)
        for worker, amount in owed.items():
            pay = amount * scale
            gov.treasury -= pay
            gov.spent["benefits"] += pay
            gov.step_spent["benefits"] += pay
            worker.money += pay
            economy.earn(worker, pay, "benefits")
        stats["benefits"] = total * scale

    @staticmethod
    def _hire(employer, worker, units, wage, stats, gov=None, payroll=None):
        pay = units * wage
        employer.flow["wages_paid"] = employer.flow.get("wages_paid", 0.0) + pay   # a cost when worked
        if payroll is not None:
            # Weekly or monthly pay: earned today, paid (and taxed) on payday.
            key = (employer.id, worker.id)
            payroll[key] = payroll.get(key, 0.0) + pay
        else:
            employer.money -= pay
            tax = gov.tax("wage", pay) if gov else 0.0     # salary tax, withheld from the pay
            if tax:
                gov.collect("wage", tax)
            worker.money += pay - tax
            economy.earn(worker, pay - tax, "wages")
        worker.labor_sold += units
        worker.employers[employer.name] = worker.employers.get(employer.name, 0) + units
        employer.labor_available += units
        employer.labor_bought += units
        employer.flow["labor_used"] += units
        stats["hired"] += units
        stats["hires"] += 1

    def to_dict(self):
        return {"wage": self.wage, "multiplier": self.multiplier, **self.stats,
                "wages_owed": round(sum(self.payroll.values()), 2), "paid_last": round(self.paid_last, 2),
                "unpaid_last": round(self.unpaid_last, 2)}
