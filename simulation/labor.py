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
from itertools import islice

# Days of sales revenue the base wage looks back over (see base_wage).
REVENUE_DAYS = 30


from . import economy, penalties

from .rules import NEEDS as NEEDS_FOR_WELLBEING
from .rules import Rules as _Rules

# What each good relieves in the full catalog (for subsistence goods missing from a game).
_FULL = _Rules.from_dict({"housing_enabled": False})
CATALOG_NEED = {g: _FULL.need_of(g) for g in _FULL.active_goods}
CATALOG_RELIEF = {(g, n): _FULL.relief(g, n) for g in _FULL.active_goods for n in _FULL.consumer_needs}


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


def skill(agent, good, rules):
    """How many units of labour one unit of this agent's time is worth in ``good``'s industry
    (specialization): 1 + (skill_max - 1) x (1 - e^(-experience / skill_scale)). Learning with
    diminishing returns, up to skill_max (10x)."""
    if not rules.specialization_enabled or good is None:
        return 1.0
    xp = agent.experience.get(good, 0.0)
    return 1.0 + (rules.skill_max - 1.0) * (1.0 - math.exp(-xp / rules.skill_scale)) if xp > 0 else 1.0


def autonomous_factor(agent, rules, good=None):
    """Share of its starting productivity in autonomous production the agent keeps: specialised
    workers lose the knack of fending for themselves in unrelated goods, down to auto_skill_floor
    (5%) as their experience in other industries grows (same learning curve as skill)."""
    if not rules.specialization_enabled:
        return 1.0
    xp = sum(v for k, v in agent.experience.items() if good is None or k != good)
    if xp <= 0:
        return 1.0
    learned = 1.0 - math.exp(-xp / rules.skill_scale)
    return 1.0 - (1.0 - rules.auto_skill_floor) * learned


class LaborMarket:
    def __init__(self):
        self.multiplier = 1.0
        self.wage = 0.0
        self.stats = self._empty_stats()
        # Wages earned and not yet paid (weekly or monthly pay): {(employer id, worker id): money}.
        self.payroll = {}
        self.paid_last = 0.0      # wages paid on the latest payday
        self.reservation = 0.0    # the reservation wage (see reservation_wage)
        self.unpaid_last = 0.0    # ... and what employers couldn't pay then (arrears)
        self.wage_streak_dir = 0  # +1 upward pressure, -1 downward pressure, 0 neutral
        self.wage_streak_days = 0 # consecutive days with pressure in the same direction

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
                "gov_hired": 0.0, "benefits": 0.0, "subsistence": 0.0,
                "subsistence_agents": 0, "subsistence_units": 0.0, "unused": 0.0, "withheld": 0.0, "idle": 0.0, "hires": 0, "workers_hired": 0, "base_wage": 0.0, "pressure": 1.0}

    def base_wage(self, world, prices, jobs):
        """labor_share x value added by one unit of labour (output minus the inputs it used),
        weighted by the jobs on offer."""
        rules = world.rules
        weights = {g: jobs.get(g, 0) for g in world.rules.active_goods}
        if sum(weights.values()) <= 0:
            weights = {g: 1 for g in world.rules.active_goods}
        value = sum(w * world.productivity_now[g] * world.value_added(g, prices)
                    for g, w in weights.items()) / sum(weights.values())
        # Firms can only pay out of what they actually sell: once there is a month of history, a
        # unit of labour is worth at most the sales revenue per unit of labour worked.
        hist = world.recorder.history
        h = list(islice(hist, max(0, len(hist) - REVENUE_DAYS), None))
        worked = sum(s["labor_used"] for s in h)
        if len(h) >= 3 and worked > 0:
            value = min(value, sum(s["income_sources"]["goods"] for s in h) / worked)
        return rules.labor_share * value

    def reservation_wage(self, world, prices):
        """What a unit of labour makes in autonomous production (the best of its goods at today's
        prices): the least anyone works for. 0 without autonomous production."""
        rules = world.rules
        if not (rules.subsistence_enabled and rules.industries_enabled) or rules.price_mode == "cost":
            # (With cost prices every price is proportional to the wage, so a floor tied to the
            # price of water either never binds or lifts wages without end.)
            return 0.0
        return max((rate * prices.get(g, 0.0) for g, rate in self.subsistence_options(rules)), default=0.0)

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
            # The industry it hires for (and learns in): the one with the most jobs.
            a.main_good = max(jobs, key=jobs.get) if jobs and max(jobs.values()) > 0 else None
            a.labor_need = sum(jobs.values())
            a.output_capacity = {g: world.asset_output(g, s) for g, s in a.assets.items() if g in economy.GOODS}
            for g, j in jobs.items():
                jobs_by_good[g] = jobs_by_good.get(g, 0) + j
            own_skill = skill(a, a.main_good, rules) if a.main_good else 1.0
            own = min(a.capacity_now, a.labor_need / own_skill) if own_skill > 0 else 0.0
            own_effective = own * own_skill
            a.labor_available = own_effective
            a.own_labor = own
            if own > 0 and a.main_good and rules.specialization_enabled:
                a.experience[a.main_good] = a.experience.get(a.main_good, 0.0) + own
            a.labor_sold = 0.0
            a.labor_bought = 0.0
            a.employers = {}
            stats["capacity"] += a.capacity_now
            stats["own_use"] += own
            a.flow["labor_made"] += a.capacity_now
            a.flow["labor_used"] += own_effective
            free = a.capacity_now - own
            a.offered = free * (rules.participation_floor + (1 - rules.participation_floor) * a.job_need)
            # Fewer than labor_offer_months of living costs left (money + goods for its needs):
            # it looks for work with all the labour it can spare.
            if rules.labor_offer_months > 0:
                a.months_left = economy.months_covered(a, prices, rules)
                if a.months_left < rules.labor_offer_months:
                    a.offered = free
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
        # (Company cash pays wages too; wages already owed don't.)
        stats["wanted"] = sum(
            min(e.labor_need - e.labor_available,
                max(0.0, economy.money_of(e) + e.company_cash - cash_needed(e, prices, rules) - owed.get(e.id, 0.0))
                / ref_wage if ref_wage > 0 else 0.0)
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
        if rules.wage_adjust_speed > 0 and self.wage > 0 and rules.price_mode != "fixed":
            # Wages follow the labour market symmetrically (excess demand or supply): starting at
            # wage_adjust_speed (or wage_down_speed) per month, doubling each consecutive month the
            # pressure persists in the same direction (2% -> 4% -> 8% ...) up to wage_speed_max.
            gap = (stats["wanted"] - stats["offered"]) / max(stats["offered"], stats["wanted"], 1e-9)
            gap = max(-1.0, min(1.0, gap))
            direction = 1 if gap > 1e-6 else (-1 if gap < -1e-6 else 0)
            if direction == 0:
                self.wage_streak_dir, self.wage_streak_days = 0, 0
            elif direction == self.wage_streak_dir:
                self.wage_streak_days += 1
            else:
                self.wage_streak_dir, self.wage_streak_days = direction, 1
            months = (self.wage_streak_days - 1) // max(1, rules.month_steps) if self.wage_streak_days else 0
            base_monthly = rules.wage_adjust_speed if gap > 0 else rules.wage_down_speed
            monthly_speed = min(rules.wage_speed_max, base_monthly * (2 ** months))
            daily_speed = (1 + monthly_speed) ** (1 / max(1, rules.month_steps)) - 1
            exp_daily = 0.0
            if rules.expectations_enabled and world.expected_inflation > 0:
                exp_daily = (1 + world.expected_inflation) ** (1 / max(1, world.year_steps())) - 1
            wage = self.wage * (1 + daily_speed * gap + exp_daily)
        else:
            wage = base * self.multiplier
        # Floors: the minimum wage (government policy) and the reservation wage (nobody works for
        # less than its labour would make it on its own, in autonomous production).
        self.reservation = self.reservation_wage(world, prices)
        self.wage = max(wage, world.government.min_wage, self.reservation)
        stats["base_wage"], stats["pressure"] = base, pressure
        stats["reservation_wage"] = self.reservation

        # Each worker's asking wage; the cheapest are hired first.
        for a in offers:
            a.asking_wage = max(world.government.min_wage, self.reservation,
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
            good = employer.main_good
            # Specialization: the cheapest labour per unit of work done in its industry first
            # (asking wage / skill), so experienced workers are hired first.
            pool = offers if not rules.specialization_enabled or good is None else sorted(
                offers, key=lambda w: w.asking_wage / skill(w, good, rules))
            for worker in pool:
                if want <= 1e-9 or budget <= 1e-9:
                    break
                if worker is employer or remaining[worker] <= 1e-9:
                    continue
                s = skill(worker, good, rules)
                affordable = budget / worker.asking_wage if worker.asking_wage > 0 else remaining[worker]
                units = min(remaining[worker], want / s, affordable)       # units of the worker's time
                self._hire(employer, worker, units, worker.asking_wage, stats, world.government,
                           self.payroll if period > 1 else None, effective=units * s, good=good)
                remaining[worker] -= units
                want -= units * s
                budget -= units * worker.asking_wage

        # Government spending (public works, then unemployment benefits; see government.py).
        gov = world.government
        stats["gov_hired"] += self._public_works(world, offers, remaining, gov.labor_purchase, stats)
        if gov.benefit_rate > 0:
            self._benefits(world, offers, remaining, stats)
        if gov.enabled and world.agents:
            # The player's spending policies (income support, give-aways, public services).
            gov.policies.run(world, offers, remaining, stats)
        if gov.balanced_budget and gov.treasury > 1e-6 and gov.debt.bonds and gov.debt.room(world) <= 0:
            # Over the debt limit: taxes left over repay debt first (soonest due first). Otherwise
            # the treasury spends what it has, savers' bond money included, so savings come back
            # into the economy as wages and transfers.
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
            stats["subsistence"] = self._subsistence(world, stats)

        # Unused capacity = withheld (not offered: the agent didn't need to work) + idle
        # (offered but nobody hired it).
        stats["unused"] = max(0.0, stats["capacity"] - stats["own_use"] - stats["hired"] - stats["gov_hired"]
                              - stats.get("subsistence", 0.0))     # (autonomous production uses labour too)
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
    def subsistence_options(rules):
        """[(good, units per unit of labour)] agents can make on their own: rules.subsistence_rates
        (water and food by default). A good that doesn't exist in this game is replaced by the best
        one that does for the same need, at a rate giving the same relief per unit of labour."""
        options = {}
        for g, rate in rules.subsistence_rates.items():
            if rate <= 0:
                continue
            need = CATALOG_NEED.get(g)
            if g in rules.active_goods and rules.need_of(g) in rules.consumer_needs:
                options[g] = max(options.get(g, 0.0), rate)
            elif need in rules.consumer_needs and rules.goods_for(need):
                best = rules.goods_for(need)[0]
                relief = rate * CATALOG_RELIEF.get((g, need), 0.0)
                if relief > 0:
                    options[best] = max(options.get(best, 0.0), relief / rules.relief(best, need))
        return list(options.items())

    @staticmethod
    def _subsistence(world, stats=None):
        """Autonomous production: every agent puts the labour it has left (after its own
        industries and any job) into making a little water or food on its own, at
        rules.subsistence_rates units per unit of labour (about enough to live on if it works at
        nothing else). Each day it makes the one its most urgent need calls for (less so when it
        holds some already). Fractions of a unit accumulate until a whole unit is made.
        Returns the labour used."""
        rules = world.rules
        options = LaborMarket.subsistence_options(rules)
        used, agents, units = 0.0, 0, 0.0
        for a in world.agents:
            a.subsistence_made = {}
            if not options:
                continue
            spare = a.capacity_now - getattr(a, "own_labor", 0.0) - a.labor_sold
            if rules.survival_effort > 0 and economy.alarmed(a, rules):
                # However weak (hungry, ill, tired), an agent short of food or water can still put
                # survival_effort of its base labour into fetching water or growing food.
                spare = max(spare, a.labor_capacity * rules.survival_effort
                            - getattr(a, "own_labor", 0.0) - a.labor_sold)
            if spare <= 1e-9:
                continue
            # Most urgent need first; for a need it already has stock of, less so.
            def score(opt):
                need = rules.need_of(opt[0])
                return (economy.urgency(a, need, rules) - economy.held_relief(a, need, rules), opt[1])
            good, rate = max(options, key=score)
            # Producing a good autonomously builds experience in it and raises output per labour;
            # experience in unrelated industries still reduces self-sufficiency (autonomous_factor).
            made = spare * rate * skill(a, good, rules) * autonomous_factor(a, rules, good)
            if rules.specialization_enabled:
                a.experience[good] = a.experience.get(good, 0.0) + spare
            done = a.subsistence.get(good, 0.0) + made
            whole = int(done + 1e-9)
            if whole:
                a.inventory.add(good, whole)
                a.flow["produced"][good] = a.flow["produced"].get(good, 0) + whole
            a.subsistence[good] = done - whole
            a.subsistence_made[good] = made
            used += spare
            agents += 1
            units += made
        if stats is not None:
            stats["subsistence_agents"] = agents
            stats["subsistence_units"] = units
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
    def _hire(employer, worker, units, wage, stats, gov=None, payroll=None, effective=None, good=None):
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
        if good is not None:
            worker.experience[good] = worker.experience.get(good, 0.0) + units   # learning on the job
        done = units if effective is None else effective      # work done: time x skill
        employer.labor_available += done
        employer.labor_bought += done
        employer.flow["labor_used"] += done
        stats["hired"] += units
        stats["hires"] += 1

    def to_dict(self):
        return {"wage": self.wage, "multiplier": self.multiplier, **self.stats,
                "wages_owed": round(sum(self.payroll.values()), 2), "paid_last": round(self.paid_last, 2),
                "unpaid_last": round(self.unpaid_last, 2)}
