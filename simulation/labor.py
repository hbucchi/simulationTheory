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

from . import economy

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
    return sum(economy.need_cost(agent, need, prices, rules) for need in rules.consumer_needs)


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

    @staticmethod
    def _empty_stats():
        return {"capacity": 0.0, "own_use": 0.0, "offered": 0.0, "wanted": 0.0, "hired": 0.0,
                "wanted_full": 0.0, "job_capacity": 0.0, "jobs_funded": 0.0,
                "gov_hired": 0.0, "unused": 0.0, "withheld": 0.0, "idle": 0.0, "hires": 0, "workers_hired": 0, "base_wage": 0.0, "pressure": 1.0}

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
        offers, employers, jobs_by_good = [], [], {}

        for a in world.agents:
            a.efficiency = efficiency(a, rules)
            a.wellbeing = wellbeing(a, rules)
            a.job_need = general_need(a, prices, rules)
            a.capacity_now = a.labor_capacity * a.efficiency
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
        self.wage = base * self.multiplier
        stats["base_wage"], stats["pressure"] = base, pressure

        # Each worker's asking wage; the cheapest are hired first.
        for a in offers:
            a.asking_wage = self.wage * min(3.0, max(0.1, 1 + rules.bargaining_spread * (a.wellbeing - a.job_need)))
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
            budget = max(0.0, economy.money_of(employer) - need)
            if budget > 0 and employer.deposits:
                # Wages are paid in cash: take what's needed out of the bank.
                world.banking.cash_up(employer, need + min(budget, want * ref_wage * 2))
                budget = min(budget, max(0.0, employer.money - need))
            for worker in offers:
                if want <= 1e-9 or budget <= 1e-9:
                    break
                if worker is employer or remaining[worker] <= 1e-9:
                    continue
                affordable = budget / worker.asking_wage if worker.asking_wage > 0 else remaining[worker]
                units = min(remaining[worker], want, affordable)
                self._hire(employer, worker, units, worker.asking_wage, stats)
                remaining[worker] -= units
                want -= units
                budget -= units * worker.asking_wage

        # The government hires from what is left, with new money (public works).
        gov = world.government
        gov.last_spent = 0.0
        wanted = gov.labor_purchase
        for worker in offers:
            if wanted <= 1e-9:
                break
            units = min(remaining[worker], wanted)
            if units <= 1e-9:
                continue
            pay = units * worker.asking_wage
            worker.money += pay
            economy.earn(worker, pay, "government")
            worker.labor_sold += units
            worker.employers["Government"] = worker.employers.get("Government", 0) + units
            remaining[worker] -= units
            wanted -= units
            gov.labor_bought += units
            gov.money_created += pay
            gov.last_spent += pay
            stats["gov_hired"] += units

        # Unused capacity = withheld (not offered: the agent didn't need to work) + idle
        # (offered but nobody hired it).
        stats["unused"] = stats["capacity"] - stats["own_use"] - stats["hired"] - stats["gov_hired"]
        stats["idle"] = max(0.0, stats["offered"] - stats["hired"] - stats["gov_hired"])
        stats["withheld"] = max(0.0, stats["unused"] - stats["idle"])
        stats["workers_hired"] = sum(1 for a in offers if a.labor_sold > 1e-9)
        self.stats = stats

    @staticmethod
    def _hire(employer, worker, units, wage, stats):
        pay = units * wage
        employer.money -= pay
        worker.money += pay
        economy.earn(worker, pay, "wages")
        worker.labor_sold += units
        worker.employers[employer.name] = worker.employers.get(employer.name, 0) + units
        employer.labor_available += units
        employer.labor_bought += units
        employer.flow["labor_used"] += units
        stats["hired"] += units
        stats["hires"] += 1

    def to_dict(self):
        return {"wage": self.wage, "multiplier": self.multiplier, **self.stats}
