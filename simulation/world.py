"""The World: a WIDTH x HEIGHT box holding agents and advancing time in steps."""

import math
import random
from collections import deque
from itertools import islice

from . import distributions, economy, penalties
from .agent import Agent
from .inventory import Inventory
from .modules import Build, Consume, Invest, Mood, Navigate, NeedsDecay, Production, Rest
from .banking import Banking
from .government import Government
from .labor import LaborMarket
from .modules.invest import cash_needed, transfer_shares
from .report import Recorder
from .catalog import CAPITAL_GOODS
from .rules import NEEDS, SPREADS, Rules

# Soft but distinguishable colours, matching the UI palette.
AGENT_COLORS = ["#6c72f0", "#f08a6c", "#4fbf96", "#e9b949", "#a77de0", "#4aa3df", "#e77fa9", "#8cbf5f"]


# Perishable output: owners hold at most this share of its shelf life before they stop producing.
PERISHABLE_BUFFER = 0.5
# Sell-through (share of output that doesn't expire) is measured over this many days and
# never counts as less than MIN_SELL_THROUGH (so an industry can always restart).
SELL_THROUGH_DAYS = 60
MIN_SELL_THROUGH = 0.2
# A seeking agent drops the seller it is walking to for a new one only if that one is under
# this share of the distance away (see World._committed_seller).
SWITCH_DISTANCE = 0.5

# Games up to this many agents send every agent in full to the UI (bigger ones: only those asked for).
FULL_DETAIL_AGENTS = 100

class World:
    # After two agents meet they walk apart for rules.depart_steps and ignore
    # each other for rules.cooldown_steps, so they don't instantly re-meet.
    # Departure = straight away from the partner, turned by a random angle in
    # [-MAX_TURN, +MAX_TURN]: a 180-degree window that never points back at them.
    MAX_TURN = math.radians(90)
    PRICE_HISTORY = 200  # steps of price history kept for the charts
    CAPITAL_STOCK = 5    # units of a capital good its makers keep ready for builders (usable_jobs)

    def __init__(self, width=1024, height=1024, seed=None, rules=None):
        self.width = width
        self.height = height
        self.rules = rules or Rules()
        # Two agents are "in touch" (able to interact) when their centres are
        # at most this many pixels apart. 12 = two dots of radius 6 touching.
        self.contact_distance = self.rules.contact_distance
        self.seed = seed
        self.rng = random.Random(seed)
        # Personality traits come from their own stream, so adding traits doesn't change the rest.
        self.personality_rng = random.Random(f"personality-{seed}")
        self.agents = []
        self.tick = 0
        self.events = []  # newest last; trimmed to keep the payload small
        self.cooldowns = {}  # frozenset({id_a, id_b}) -> (tick until which they ignore each other, after a deal?)
        self.labor = LaborMarket()
        self.government = Government.from_rules(self.rules)
        self.banking = Banking(self.rules, self.government)
        self.retained_total = 0.0
        self.sell_through = {}        # good -> share of recent output that didn't expire
        self.price_level = 1.0        # scales every price (money_velocity: M x V = P x Y)
        self.price_level_set = False
        self.assets_depreciated = {}   # asset shares worn out so far, by industry   # company profits kept in companies so far
        self._by_id = {}
        self.recorder = Recorder()  # per-step snapshots for the Report view
        self._dead_flows = []       # flows of agents that died this step (still counted)
        self.asset_trades = 0        # purchases of asset shares between agents
        self.assets_built = {}       # good -> new asset shares built from capital goods (Build)
        self.asset_trade_money = 0.0
        # Units of each good one unit of labour makes right now (grows every step), and labour
        # one asset share employs right now (shrinks every step with labour-saving progress).
        self.productivity_now = dict(self.rules.productivity)
        self.asset_labor_now = dict(self.rules.asset_labor)
        # Average units per living agent of each resource, one entry per step, for the
        # last scarcity_window steps; scarcity = how much that average fell over the window.
        self.per_agent_history = {r: deque(maxlen=self.rules.scarcity_window + 1) for r in economy.RESOURCES}
        self.scarcity = {r: 0.0 for r in economy.RESOURCES}
        # Demand pressure: buyers/sellers counted each step, the price multiplier they push
        # toward, and the last PRICE_HISTORY prices for the charts.
        self.buyers = {r: 0 for r in economy.RESOURCES}
        self.buyer_agents = {r: [] for r in economy.RESOURCES}  # who wants each resource (this step)
        self.sellers = {r: 0 for r in economy.RESOURCES}
        self.price_multiplier = {r: 1.0 for r in economy.RESOURCES}
        # Concentration of each resource's available (sellable) supply: 0 even, 1 one holder.
        self.concentration = {r: 0.0 for r in economy.RESOURCES}
        self.buyer_concentration = {r: 0.0 for r in economy.RESOURCES}   # of buying power
        self.price_history = {r: deque(maxlen=self.PRICE_HISTORY) for r in economy.PRICED}
        self.next_id = 1
        self.alive = set()          # the agents list as a set, for fast "still alive?" checks
        # Per-step caches (set at the start of step(), cleared at its end): one price list for the
        # whole step, asset prices, owners short of cash, and who is seeking whom.
        self._step_cache = None
        self.grid = {}              # spatial grid for contact checks: cell -> {agent: None} (a dict, so the order is the same every run)
        self._cell = {}             # agent -> its cell
        # {good: {agent: units it can spare}}, worked out once per step in update_demand and used
        # to pick sellers to walk to (the trade itself re-checks what the seller can spare).
        self.spare_table = {}
        self.buyer_sets = {}   # {good: agents that want it this step}
        self.surplus_table = None   # {agent: {good: surplus}} at the start of this step (update_demand)
        self.profitable = {}   # {good: its industry pays the wage at current prices} (update_profitability)
        self.step_prices = None

    def clamp_position(self, x, y):
        return (min(max(x, 0.0), self.width), min(max(y, 0.0), self.height))

    def random_position(self):
        return (self.rng.uniform(0, self.width), self.rng.uniform(0, self.height))

    def add_agent(self, agent):
        agent.id = self.next_id
        self.next_id += 1
        agent.name = agent.name or f"Agent {agent.id}"
        if agent.color is None:
            agent.color = AGENT_COLORS[(agent.id - 1) % len(AGENT_COLORS)]
        self.agents.append(agent)
        self._by_id[agent.id] = agent
        self.alive.add(agent)
        return agent

    def create_agent(self, *, inventory=None, money=None, labor_capacity=None,
                     rates=None, sleep_recovery=None, movement=None, needs=None, name=None,
                     x=None, y=None, assets=None, payout_ratio=None, risk_appetite=None):
        """Create an agent with the standard modules. Anything omitted comes from the rules.

        ``inventory`` overrides per good; ``labor_capacity`` is the most labour it can give per step;
        ``rates`` overrides how fast each need grows per step;
        ``sleep_recovery`` is how much sleep drops per step while resting;
        ``needs`` overrides starting need levels;
        ``x`` / ``y`` default to a random position.
        Values not given are drawn from the rules' spreads (see distributions.py).
        """
        r = self.rules

        def draw(spec, whole=False, field=None):
            low, high = SPREADS[field][1:3] if field else (-math.inf, math.inf)
            return distributions.sample(spec, self.rng, whole, low, high)

        rx, ry = self.random_position()
        x, y = self.clamp_position(rx if x is None else x, ry if y is None else y)
        start_needs = {n: round(draw(r.start_needs, field="start_needs"), 2) for n in NEEDS}
        start_needs.update(needs or {})
        # Rest runs first so a resting agent's sleep never grows that step.
        modules = [Rest(draw(r.sleep_recovery, field="sleep_recovery") if sleep_recovery is None else sleep_recovery),
                   NeedsDecay({**{n: draw(v, field="rates") for n, v in r.rates.items()}, **(rates or {})}),
                   Production(),
                   Consume()]
        modules.append(Build())
        modules.append(Invest())
        if r.depression_enabled:
            modules.append(Mood())
        modules.append(Navigate())
        agent = Agent(
            x, y, name=name, **start_needs,
            money=round(draw(r.money, field="money"), 2) if money is None else money,
            movement=draw(r.movement, True, "movement") if movement is None else movement,
            inventory=self.new_inventory({**{k: draw(v, True, "inventory") for k, v in r.inventory.items()},
                                          **(inventory or {})}),
            modules=modules,
        )
        agent.depression_factor = r.depression_factor
        agent.labor_capacity = draw(r.labor_capacity, field="labor_capacity") if labor_capacity is None else labor_capacity
        drawn = {k: draw(v, False, "assets") for k, v in r.assets.items()}
        agent.assets = {k: v for k, v in {**drawn, **(assets or {})}.items() if v and r.is_active(k)}
        agent.personality["payout_ratio"] = round(distributions.sample(
            r.payout_ratio, self.personality_rng, False, 0, 1), 3) if payout_ratio is None else payout_ratio
        agent.personality["risk_appetite"] = round(distributions.sample(
            r.risk_appetite, self.personality_rng, False, 0, 1), 3) if risk_appetite is None else risk_appetite
        return self.add_agent(agent)

    # A starting stock is spread over this many batches of different ages, so it doesn't all
    # expire on the same step.
    START_BATCHES = 10

    def new_inventory(self, items):
        """An inventory for this game's rules: goods with a shelf life are perishable (when expiry
        is on). Starting units of a perishable good are spread evenly over ages, so they expire
        bit by bit over one shelf life. Goods of industries not in this game are left out."""
        r = self.rules
        life = {g: d for g, d in r.shelf_life.items() if d > 0 and r.is_active(g)} if r.expiry_enabled else {}
        inventory = Inventory(perishable=life, now=self.tick)
        for good, qty in items.items():
            if not r.is_active(good):
                continue
            if good not in life:
                inventory.items[good] = qty
                continue
            batches = max(1, min(int(qty), self.START_BATCHES))
            for i in range(batches):
                part = qty // batches + (1 if i < qty % batches else 0)
                if part:
                    inventory.add(good, part, expires=self.tick + math.ceil(life[good] * (i + 1) / batches))
        return inventory

    def update_agent(self, agent, *, name=None, x=None, y=None, needs=None, inventory=None,
                     money=None, movement=None, labor_capacity=None, rates=None, sleep_recovery=None,
                     assets=None, payout_ratio=None, risk_appetite=None):
        """Change any of an existing agent's settings; omitted fields stay as they are."""
        if payout_ratio is not None:
            agent.personality["payout_ratio"] = payout_ratio
        if risk_appetite is not None:
            agent.personality["risk_appetite"] = risk_appetite
        for resource, count in (assets or {}).items():
            agent.assets[resource] = count
        if name:
            agent.name = name
        agent.x, agent.y = self.clamp_position(agent.x if x is None else x, agent.y if y is None else y)
        for need, level in (needs or {}).items():
            setattr(agent, need, level)
        for resource, qty in (inventory or {}).items():
            agent.inventory.set(resource, qty)
        if money is not None:
            agent.money = float(money)
        if movement is not None:
            agent.movement = int(movement)
        if labor_capacity is not None:
            agent.labor_capacity = labor_capacity
        for module in agent.modules:
            if isinstance(module, NeedsDecay) and rates:
                module.rates.update(rates)
            if isinstance(module, Rest) and sleep_recovery is not None:
                module.recovery = sleep_recovery
        return agent

    def remove_agent(self, agent):
        self.agents.remove(agent)
        self._by_id.pop(agent.id, None)
        self.banking.forget(self, agent)
        self.alive.discard(agent)
        self._grid_remove(agent)
        for other in self.agents:
            if other.target_id == agent.id:
                other.target_id = None

    def spawn_random_agents(self, count=None):
        """Create the starting agents. Tiered inventory/money is shared out between them
        exactly (e.g. the top 1% really hold 50%); other values are drawn per agent."""
        n = self.rules.agents if count is None else count
        r = self.rules
        money = distributions.allocate(r.money, n, self.rng, False, *SPREADS["money"][1:3])
        stock = {k: distributions.allocate(v, n, self.rng, True, *SPREADS["inventory"][1:3])
                 for k, v in r.inventory.items()}
        assets = {k: distributions.allocate(v, n, self.rng, False, *SPREADS["assets"][1:3])
                  for k, v in r.assets.items()}
        # Starting banks: banking plants for rules.starting_banks agents that can put up the
        # minimum capital, spread evenly over them from richest to poorest (no random draws, so
        # the rest of the game is the same with or without banks); the richest if too few can.
        if r.is_active("banking") and r.starting_banks:
            richest = sorted(range(n), key=lambda i: -money[i])
            able = [i for i in richest if money[i] >= r.bank_min_capital]
            k = min(len(able), r.starting_banks)
            chosen = [able[j * len(able) // k] for j in range(k)] if k else []
            chosen += [i for i in richest if i not in chosen][:r.starting_banks - k]
            for i in chosen:
                assets["banking"][i] = assets["banking"][i] + r.starting_bank_shares
        else:
            chosen = []
        # Only asset_owner_share of agents start owning assets (the rest own only their labour):
        # every industry's starting shares are handed to them, in proportion to what they drew.
        if 0 < r.asset_owner_share < 1 and n > 1:
            pick = random.Random(f"owners-{self.seed}")
            k = max(1, round(n * r.asset_owner_share))
            owners = set(chosen)              # bank founders always keep their banks
            if k > len(owners):
                owners |= set(pick.sample([i for i in range(n) if i not in owners], k - len(owners)))
            for good, shares in assets.items():
                total = sum(shares)
                kept = sum(shares[i] for i in owners)
                for i in range(n):
                    if i not in owners:
                        shares[i] = 0.0
                    elif kept > 0:
                        shares[i] *= total / kept
                    else:
                        shares[i] = total / len(owners)
        for i in range(n):
            self.create_agent(money=round(money[i], 2), inventory={k: v[i] for k, v in stock.items()},
                              assets={k: v[i] for k, v in assets.items()})
        self.update_price_level()   # starting prices already at the money's level (M x V = P x Y)

    def in_cooldown(self, a, b):
        """True while a and b ignore each other. After a deal (not after a meeting where nothing
        could be traded) an agent that is hungry, thirsty or running low on food or water
        (economy.alarmed) may go straight back: it can't wait a week for the nearest seller."""
        entry = self.cooldowns.get(frozenset((a.id, b.id)))
        if entry is None or entry[0] < self.tick:
            return False
        return not (entry[1] and (economy.alarmed(a, self.rules) or economy.alarmed(b, self.rules)))

    def agent_by_id(self, agent_id):
        return self._by_id.get(agent_id)

    def owners_of(self, good):
        """Agents holding asset shares of ``good`` (once per step; fresh outside a step)."""
        cache = self._step_cache
        if cache is None:
            return [a for a in self.agents if a.assets.get(good, 0) > 0]
        owners = cache.get("owners")
        if owners is None:
            owners = cache["owners"] = {}
            for a in self.agents:
                for g, shares in a.assets.items():
                    if shares > 0:
                        owners.setdefault(g, []).append(a)
        return [a for a in owners.get(good, ()) if a in self.alive and a.assets.get(good, 0) > 0]

    def spare_total(self, good):
        """Units of ``good`` all agents together can spare this step (from spare_table)."""
        cache = self._step_cache
        if cache is None:
            return sum(self.spare_table.get(good, {}).values())
        totals = cache.setdefault("spare_total", {})
        if good not in totals:
            totals[good] = sum(self.spare_table.get(good, {}).values())
        return totals[good]

    def surpluses_of(self, agent):
        """{good: units above what the agent keeps}, from this step's table (fresh if there's none)."""
        if self.surplus_table is not None and self._step_cache is not None:
            return self.surplus_table.get(agent, {})
        out = {}
        for r in self.rules.active_goods:
            n = economy.surplus(agent, r, self.rules, self.scarcity)
            if n:
                out[r] = n
        return out

    def note_target(self, agent, partner):
        """Keep the step's index of who is heading for whom up to date (see seekers_of)."""
        if self._step_cache:
            self._step_cache["seekers"].setdefault(partner.id, []).append(agent)

    def seekers_of(self, agent):
        """Agents currently seeking ``agent`` (and allowed to meet it). During a step, candidates come
        from an index of targets built at its start (so this doesn't scan every agent)."""
        cache = self._step_cache
        candidates = cache["seekers"].get(agent.id, ()) if cache else self.agents
        return list({o: None for o in candidates
                     if o.activity == "seeking" and o.target_id == agent.id and o in self.alive
                     and not self.in_cooldown(agent, o)})

    def nearest_seller(self, agent, stockpile=False):
        """Closest agent with spare of what ``agent`` needs: (seller, resource) or (None, None).
        Nobody, when commerce is off.

        Needs are tried most urgent first, so a thirsty and slightly hungry agent
        looks for water before food. With ``stockpile`` it looks instead for
        resources it is short of in its reserve. Agents it has just met are skipped.
        """
        if not self.rules.commerce_enabled:
            return None, None
        if stockpile:
            wanted = [r for r in self.rules.active_goods
                      if economy.stockpile_shortfall(agent, r, self.rules, self.scarcity) > 0
                      or economy.restock_shortfall(agent, r, self.rules) > 0
                      or economy.input_shortfall(agent, r, self.rules) > 0
                      or economy.project_shortfall(agent, r) > 0]
            # Goods for its most pressing need first (water before herbs for a thirsty agent),
            # then the ones getting scarcer.
            wanted.sort(key=lambda r: (economy.need_urgency(agent, r, self.rules), self.scarcity[r]), reverse=True)
        else:
            # Most pressing need first (by priority, see economy.urgency); any good that relieves it will do, so the nearest agent
            # with spare of any of them is chosen (and the most effective good it has is named).
            rules = self.rules
            for need in sorted(rules.consumer_needs, key=lambda n: economy.urgency(agent, n, rules), reverse=True):
                goods = [g for g in rules.goods_for(need) if economy.demand(agent, g, rules) > 0]
                if not goods:
                    continue
                # Only agents with spare of one of these goods (spare_table) are candidates.
                candidates = {}
                for g in reversed(goods):            # the most effective good each seller has wins
                    for o in self.spare_table.get(g, {}):
                        candidates[o] = g
                best, best_d = None, math.inf
                for o, have in candidates.items():
                    if o is agent or o not in self.alive or self.in_cooldown(agent, o):
                        continue
                    d = agent.distance_to(o)
                    if d < best_d:
                        best, best_d = (o, have), d
                if best:
                    return self._committed_seller(agent, best)
            return None, None
        for resource in wanted:
            sellers = [o for o in self.spare_table.get(resource, {}) if o is not agent and o in self.alive
                       and not self.in_cooldown(agent, o)]
            if sellers:
                return min(sellers, key=agent.distance_to), resource
        return None, None

    def _committed_seller(self, agent, best):
        """Keep walking to the seller it was already seeking while that seller still has spare
        of a good for one of its pressing needs, unless ``best`` is under SWITCH_DISTANCE of the
        way. Without this an agent whose hunger and thirst take turns at the top heads for a
        food seller, then a water seller, then back, and never arrives anywhere."""
        if agent.activity != "seeking" or agent.target_id is None:
            return best
        current = self.agent_by_id(agent.target_id)
        if current is None or current is best[0] or current not in self.alive or self.in_cooldown(agent, current):
            return best
        rules = self.rules
        for need in rules.consumer_needs:
            if getattr(agent, need) <= rules.seek_threshold:
                continue
            for g in rules.goods_for(need):
                if current in self.spare_table.get(g, {}) and economy.demand(agent, g, rules) > 0:
                    if agent.distance_to(best[0]) < SWITCH_DISTANCE * agent.distance_to(current):
                        return best
                    return current, g
        return best

    def update_scarcity(self):
        """Record average units per agent and how much it fell over the scarcity window."""
        n = len(self.agents)
        for r, history in self.per_agent_history.items():
            history.append(sum(a.inventory.count(r) for a in self.agents) / n if n else 0.0)
            past, now = history[0], history[-1]
            full = len(history) == history.maxlen
            self.scarcity[r] = max(0.0, 1 - now / past) if full and past > 0 else 0.0

    def yearly_basket(self):
        """{good: units} people consume in a year. It starts from what their needs call for (each
        need met with its most effective good) and shifts to what they actually consumed (scaled
        up to a year) over the first month, so the price level doesn't jump when the measured
        figure takes over."""
        acc = self.recorder.national
        year = self.year_steps()
        expected = {}
        n = len(self.agents)
        for need in self.rules.consumer_needs:
            best = self.rules.goods_for(need)[0]
            rate = distributions.mean(self.rules.rates[need])
            expected[best] = expected.get(best, 0.0) + rate * n * year / self.rules.relief(best, need)
        days = len(acc.window)
        if not days:
            return expected
        weight = min(1.0, days / self.rules.month_steps)   # how much the measured basket counts
        measured = {g: u * year / days for g, u in acc.used.items() if u > 0}
        return {g: weight * measured.get(g, 0.0) + (1 - weight) * expected.get(g, 0.0)
                for g in set(measured) | set(expected)}

    def update_price_level(self):
        """Move the price level toward money supply x velocity / (a year's consumption at the
        scarcity formula's prices): M x V = P x Y."""
        rules = self.rules
        if rules.money_velocity <= 0 or rules.price_mode == "fixed" or not self.agents:
            self.price_level = 1.0
            return
        base = economy.market_prices(self.agents, rules)
        spending = sum(units * base[g] * self.price_multiplier[g] for g, units in self.yearly_basket().items())
        if spending <= 0:
            return
        money = sum(economy.money_of(a) + a.company_cash for a in self.agents)
        target = money * rules.money_velocity / spending
        if self.price_level_set:
            self.price_level += rules.price_level_speed * (target - self.price_level)
        else:
            self.price_level, self.price_level_set = target, True

    def update_demand(self):
        """Count buyers and sellers of each resource, measure how concentrated its sellable
        supply is, and move its price multiplier toward demand pressure x concentration
        (a fraction price_adjust_speed of the way per step)."""
        rules = self.rules
        self.surplus_table = {}
        # What each agent wants, worked out need by need (one pass per agent, not per agent x good).
        wanted = [economy.wanted_goods(a, rules, self.scarcity) for a in self.agents]
        # Spare and surplus of every good each agent holds (one pass over its inventory).
        spare_by_good = {r: {} for r in rules.active_goods}
        for a in self.agents:
            for r in [r for r in rules.active_goods if a.inventory.count(r)]:
                spare, surplus = economy.spare_and_surplus(a, r, rules, self.scarcity)
                if spare > 0:
                    spare_by_good[r][a] = spare
                if surplus:
                    self.surplus_table.setdefault(a, {})[r] = surplus
        n_agents = len(self.agents)
        purse = {a: economy.money_of(a) for a in self.agents}   # buying power
        for r in rules.active_goods:
            self.buyer_agents[r] = [a for a, w in zip(self.agents, wanted) if r in w]
            self.buyer_sets[r] = set(self.buyer_agents[r])
            self.buyers[r] = len(self.buyer_agents[r])
            self.spare_table[r] = spare_by_good[r]
            self.sellers[r] = len(spare_by_good[r])
            # Agents with none to spare count as zeros.
            spares = list(spare_by_good[r].values())
            self.concentration[r] = economy.concentration(spares + [0] * (n_agents - len(spares)))
            # How concentrated the buying power (money) of those who want it is, over all agents.
            power = [purse[a] for a in self.buyer_agents[r]]
            self.buyer_concentration[r] = economy.concentration(power + [0] * (n_agents - len(power)))
            if rules.demand_pricing_enabled:
                target = economy.demand_multiplier_target(self.buyers[r], self.sellers[r], r, rules,
                                                          self.concentration[r], self.buyer_concentration[r])
                self.price_multiplier[r] += rules.price_adjust_speed * (target - self.price_multiplier[r])
            else:
                self.price_multiplier[r] = 1.0
        for r, price in self.current_prices().items():
            self.price_history[r].append(price)

    def productivity_growth_per_step(self, good):
        """Per-step growth so productivity grows productivity_growth over productivity_growth_steps."""
        return (1 + self.rules.productivity_growth[good]) ** (1 / self.rules.productivity_growth_steps) - 1

    def labor_saving_per_step(self, good):
        """Per-step fall so labour per asset falls labor_saving over productivity_growth_steps."""
        return 1 - (1 - self.rules.labor_saving[good]) ** (1 / self.rules.productivity_growth_steps)

    def grow_assets(self):
        for g in self.productivity_now:
            self.productivity_now[g] *= 1 + self.productivity_growth_per_step(g)
            self.asset_labor_now[g] *= 1 - self.labor_saving_per_step(g)
        self.depreciate()

    def year_steps(self):
        return 12 * self.rules.month_steps

    def depreciation_per_step(self, good):
        """Daily wear such that a share loses depreciation[good] over a year (compounding)."""
        return 1 - (1 - self.rules.depreciation.get(good, 0.0)) ** (1 / self.year_steps())

    def depreciate(self):
        """Plants wear out: every asset share shrinks a little each step (see rules.depreciation)."""
        rates = {g: self.depreciation_per_step(g) for g in self.rules.active_goods}
        for a in self.agents:
            for g in list(a.assets):
                lost = a.assets[g] * rates.get(g, 0.0)
                if lost:
                    a.assets[g] -= lost
                    self.assets_depreciated[g] = self.assets_depreciated.get(g, 0.0) + lost
                    if a.assets[g] <= 1e-6:
                        del a.assets[g]

    def asset_jobs(self, good, shares):
        """Labour per step ``shares`` of a ``good`` asset can employ right now."""
        return shares * self.asset_labor_now[good]

    def usable_jobs(self, agent, good):
        """Labour per step the agent's ``good`` industry can use right now: what its asset
        shares employ, cut to what its inputs in stock (plus input credit) can keep busy.

        0 (the industry doesn't work, so its labour goes where output is wanted) when:
        - it doesn't pay: value added per unit of labour is below the wage (self.profitable);
        - unsold output is piling up: the owner holds rules.max_output_stock units, or more than
          rules.output_buffer_steps steps of this industry's output beyond its own input buffer."""
        if not self.rules.industries_enabled or not self.profitable.get(good, True):
            return 0.0   # (no industries module: nothing is made)
        rules = self.rules
        shares = agent.assets.get(good, 0)
        held = agent.inventory.count(good)
        if rules.max_output_stock and held >= rules.max_output_stock:
            return 0.0
        if rules.output_buffer_steps:
            # Capital goods are made so slowly that a few steps' output is less than one project
            # needs; their makers keep at least CAPITAL_STOCK units on hand for builders.
            least = self.CAPITAL_STOCK if good in CAPITAL_GOODS else 1.0
            # A perishable good: hold at most half its shelf life of output (or it rots unsold).
            days = rules.output_buffer_steps
            life = rules.shelf_life.get(good, 0) if rules.expiry_enabled else 0
            if life:
                days = min(days, life * PERISHABLE_BUFFER)
            buffer = max(least, self.asset_output(good, shares) * days)
            if held >= buffer + economy.input_target(agent, good, rules):
                return 0.0
        # Owners of a good that goes to waste make less of it for a while (sell-through: the share
        # of recent output that didn't expire).
        jobs = self.asset_jobs(good, shares) * self.sell_through.get(good, 1.0)
        productivity = self.productivity_now[good]
        for item, per_unit in self.rules.inputs.get(good, {}).items():
            stock = agent.inventory.count(item) + agent.input_credit.get(item, 0.0)
            jobs = min(jobs, stock / per_unit / productivity if productivity > 0 else 0.0)
        return jobs

    def labor_value(self, agent, prices):
        """Value created by one unit of labour in the agent's most valuable working industry:
        productivity x (price - inputs). 0 if none of its industries can use labour now."""
        return max((self.productivity_now[g] * self.value_added(g, prices)
                    for g in agent.assets if self.usable_jobs(agent, g) > 0), default=0.0)

    def build_cost_money(self, good, prices=None):
        """Money the capital goods for one new asset share of ``good`` cost at current prices
        (None if one of them doesn't exist in this game, so it can't be built)."""
        prices = prices or self.step_prices or self.current_prices()
        cost = self.rules.build_cost.get(good, {})
        if not cost or any(not self.rules.is_active(k) for k in cost):
            return None
        return sum(units * prices[k] for k, units in cost.items())

    def update_sell_through(self):
        """Share of each good's output over the last SELL_THROUGH_DAYS that didn't go to waste:
        1 - expired / produced (between MIN_SELL_THROUGH and 1; 1 when nothing was made)."""
        recent = list(islice(reversed(self.recorder.history), SELL_THROUGH_DAYS))
        for g in self.rules.active_goods:
            made = sum(s["produced"].get(g, 0) for s in recent)
            lost = sum(s["expired"].get(g, 0) for s in recent)
            self.sell_through[g] = max(MIN_SELL_THROUGH, 1 - lost / made) if made > 0 else 1.0

    def update_profitability(self):
        """Which industries pay at current prices: value added by one unit of labour
        (productivity x (price - inputs)) at least the wage. With no wage yet, all of them."""
        prices = self.current_prices()
        self.step_prices = prices   # prices at the start of the step (used to rank industries)
        wage = prices[economy.LABOR]
        self.profitable = {g: not self.rules.profit_check or wage <= 0
                           or self.productivity_now[g] * self.value_added(g, prices) >= wage - 1e-9
                           for g in self.rules.active_goods}

    def input_cost(self, good, prices):
        """Cost of the inputs used to make one unit of ``good`` (0 for primary industries)."""
        return sum(per_unit * prices[item] for item, per_unit in self.rules.inputs.get(good, {}).items())

    def recent_flow(self, key, steps=20):
        """Average per step of a recorded flow ("produced" or "used") per good over the last ``steps``."""
        recent = list(islice(reversed(self.recorder.history), steps))
        return {g: sum(s.get(key, {}).get(g, 0) for s in recent) / len(recent) if recent else 0.0 for g in economy.GOODS}

    def unit_cost(self, good, prices):
        """Cost of making one unit of ``good``: its inputs plus the labour it takes at the wage."""
        productivity = self.productivity_now[good]
        labour = self.labor.wage / productivity if productivity > 0 else 0.0
        return self.input_cost(good, prices) + labour

    def value_added(self, good, prices):
        """Price of one unit of ``good`` minus the inputs it used, never below 0."""
        return max(0.0, prices[good] - self.input_cost(good, prices))

    def asset_output(self, good, shares, labor=None):
        """Units per step made by ``shares`` of a ``good`` asset: productivity x labour used,
        where labour used is at most what the asset can employ (all of it if ``labor`` is None)."""
        jobs = self.asset_jobs(good, shares)
        used = jobs if labor is None else min(labor, jobs)
        return used * self.productivity_now[good]

    def step_asset_prices(self):
        """asset_prices at this step's prices, worked out once per step (fresh outside a step)."""
        cache = self._step_cache
        if not cache:
            return self.asset_prices()
        if "asset_prices" not in cache:
            cache["asset_prices"] = self.asset_prices(self.current_prices())
        return cache["asset_prices"]

    def asset_prices(self, prices=None):
        """Price of one whole asset: profit per step at full capacity / effective return.

        Profit = output x (price of the good - its inputs) - labour it employs x the wage. The effective
        return is the asset's return, or the government's minimum rate if higher. Never below 0.
        """
        prices = prices or self.current_prices()
        out = {}
        for g in economy.GOODS:
            # Output that expires unsold earns nothing: value only what sells (sell-through).
            sold = self.sell_through.get(g, 1.0)
            profit = (self.asset_output(g, 1) * sold * self.value_added(g, prices)
                      - self.asset_jobs(g, 1) * sold * prices[economy.LABOR])
            out[g] = max(0.0, profit) / self.government.effective_return(self.rules, g)
        return out

    def nearest_buyer(self, agent, resource):
        """Closest agent (not just met) that wants ``resource`` and has money, or None.
        Nobody, when commerce is off.

        Candidates come from this step's buyer list (update_demand) and are re-checked,
        so the search doesn't scan every agent for every seller.
        """
        if not self.rules.commerce_enabled:
            return None
        candidates = [o for o in self.buyer_agents[resource] if o is not agent and o in self.alive
                      and economy.money_of(o) > 0 and not self.in_cooldown(agent, o)]
        # Closest first; the (costlier) re-check stops at the first that still wants it.
        for o in sorted(candidates, key=agent.distance_to):
            if economy.wants_to_buy(o, resource, self.rules, self.scarcity):
                return o
        return None

    def current_prices(self, include_labor=True):
        """Goods: base price (scarcity formula or fixed) x demand-pressure multiplier.
        With rules.cost_floor, a secondary good never costs less than the inputs it is made
        from (see input_cost). Labour: the labour market's wage.

        During a step the goods prices are worked out once (after the labour market) and reused:
        trades only move goods and money between agents, so the totals behind them barely change
        within a step. Outside a step they are always worked out fresh."""
        cache = self._step_cache
        if cache and "prices" in cache:
            # The same dict for every caller while the wage is unchanged (callers never modify
            # it), so per-price memos such as economy.liquidity_cost hit.
            key = ("prices_with", self.labor.wage) if include_labor else ("prices_without",)
            prices = cache.get(key)
            if prices is None:
                prices = dict(cache["prices"])
                if include_labor:
                    prices[economy.LABOR] = self.labor.wage
                cache[key] = prices
            return prices
        base = economy.market_prices(self.agents, self.rules)
        level = self.price_level if self.rules.price_mode != "fixed" else 1.0
        prices = {r: base[r] * self.price_multiplier[r] * level for r in economy.RESOURCES}
        if self.rules.cost_floor and self.rules.price_mode != "fixed":
            # Nothing sells below what it costs to make (inputs + the labour per unit at the wage)
            # plus a normal margin, so every industry can at least pay its way. Shallow layers
            # first, so each good's inputs already carry their own floor.
            rules = self.rules
            for g in sorted(rules.active_goods, key=rules.layer):
                prices[g] = max(prices[g], self.unit_cost(g, prices) * (1 + rules.cost_floor_margin))
        if include_labor:
            prices[economy.LABOR] = self.labor.wage
        return prices

    def unit_markups(self):
        """Per-unit price rise inside a deal: only where buyers outnumber sellers."""
        rules = self.rules
        return {r: rules.unit_markup if rules.demand_pricing_enabled and self.buyers[r] > self.sellers[r] else 0
                for r in economy.RESOURCES}

    def contacts(self):
        """All pairs of agents currently close enough to interact."""
        # Bucket agents into cells as wide as the touch distance, then only compare agents in
        # neighbouring cells: O(n) instead of comparing all n^2 / 2 pairs. Same pairs, same order.
        size = max(self.contact_distance, 1e-9)
        order = {a: i for i, a in enumerate(self.agents)}
        cells = {}
        for a in self.agents:
            cells.setdefault((int(a.x // size), int(a.y // size)), []).append(a)
        pairs = []
        for a in self.agents:
            cx, cy = int(a.x // size), int(a.y // size)
            i = order[a]
            near = [b for dx in (-1, 0, 1) for dy in (-1, 0, 1) for b in cells.get((cx + dx, cy + dy), ())
                    if order[b] > i and a.distance_to(b) <= self.contact_distance]
            near.sort(key=order.get)
            pairs.extend((a, b) for b in near)
        return pairs

    def step(self):
        """Advance the simulation by one tick.

        Agents act one after another, and contacts are checked right after
        each agent moves. Checking only at the end of the tick would let a
        seeker reach its target's spot and then see the target step away
        before the check ran.
        """
        self.tick += 1
        self.government.begin_step()
        self.recorder.begin_step(self)
        self._dead_flows = []
        self.grow_assets()
        self.update_scarcity()
        self.update_demand()
        self.update_price_level()
        self.update_sell_through()
        self.update_profitability()
        self.government.debt.step(self)     # interest on government bonds, repayments
        self.labor.clear(self)
        seekers = {}
        for agent in self.agents:
            agent.inventory.now = self.tick
            self.discard_expired(agent)
            if agent.target_id is not None:
                seekers.setdefault(agent.target_id, []).append(agent)
        self._step_cache = {"seekers": seekers}
        self._step_cache["prices"] = self.current_prices(include_labor=False)
        self._rebuild_grid()
        try:
            for agent in list(self.agents):
                if agent not in self.alive:
                    continue
                agent.step(self)
                if self.check_death(agent):
                    continue
                self._grid_move(agent)
                for other in self._neighbours(agent):
                    if (other is not agent and agent.distance_to(other) <= self.contact_distance
                            and not self.in_cooldown(agent, other)):
                        self.interact(agent, other)
        finally:
            self._step_cache = None
        self.retain_earnings()
        self.banking.step(self)
        self.recorder.end_step(self, self._dead_flows)

    # ---- spatial grid: contacts are only looked for in the 3 x 3 cells around an agent ----

    def _cell_size(self):
        return max(self.contact_distance, 16.0)

    def _cell_of(self, agent):
        size = self._cell_size()
        return int(agent.x // size), int(agent.y // size)

    def _rebuild_grid(self):
        self.grid, self._cell = {}, {}
        for agent in self.agents:
            cell = self._cell_of(agent)
            self.grid.setdefault(cell, {})[agent] = None
            self._cell[agent] = cell

    def _grid_remove(self, agent):
        cell = self._cell.pop(agent, None)
        if cell is not None:
            self.grid.get(cell, {}).pop(agent, None)

    def _grid_move(self, agent):
        cell = self._cell_of(agent)
        if self._cell.get(agent) != cell:
            self._grid_remove(agent)
            self.grid.setdefault(cell, {})[agent] = None
            self._cell[agent] = cell

    def _neighbours(self, agent):
        """Agents in the 3 x 3 grid cells around ``agent`` (a cell is at least the touch distance)."""
        cx, cy = self._cell.get(agent) or self._cell_of(agent)
        found = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                found.extend(self.grid.get((cx + dx, cy + dy), ()))
        return found

    # Expiries smaller than this (per agent and good, in one step) aren't written to the event log.
    LOG_EXPIRED_FROM = 5

    def discard_expired(self, agent):
        """Throw away the agent's units past their shelf life, and count them for the report."""
        for good, qty in agent.inventory.expire().items():
            agent.flow["expired"][good] = agent.flow["expired"].get(good, 0) + qty
            if qty >= self.LOG_EXPIRED_FROM:
                self.log(f"{agent.name} threw away {qty:g} {good} (expired)")

    def check_death(self, agent):
        """Hunger or thirst at 1.00 (after eating/drinking what it had) kills the agent.

        It disappears along with its inventory and money. Off when the rules disable death.
        """
        if not self.rules.death_enabled:
            return False
        if agent.critical_health_days >= penalties.HEALTH_DEATH_DAYS:
            self._die(agent, "health")
            return True
        for need in ("hunger", "thirst"):
            if getattr(agent, need) >= economy.CRITICAL_LEVEL:
                self._die(agent, need)
                return True
        return False

    def _die(self, agent, cause):
        prices = self.current_prices()
        asset_prices = self.asset_prices(prices)
        self.remove_agent(agent)
        self.settle_estate(agent, prices, asset_prices)
        self._dead_flows.append(agent.flow)
        self.recorder.count("deaths")
        self.recorder.count(f"deaths_{cause}")
        self.log(f"{agent.name} died of {cause}" if cause != "health"
                 else f"{agent.name} died of illness ({penalties.HEALTH_DEATH_DAYS} days at health 1.00)")

    def settle_estate(self, dead, prices, asset_prices):
        """Sell a dead agent's goods and asset shares at market price to whoever is nearest
        and can pay, nearest first. Buyers only spend money above what they need on hand
        (the same rule as investing); what nobody can afford is lost. The sale price and the
        dead agent's own money leave the economy with it."""
        near = sorted(self.agents, key=lambda o: math.hypot(o.x - dead.x, o.y - dead.y))
        sold = {}   # buyer name -> {"goods": money, "units": n, "shares": n}
        rules = self.rules

        def sell(price, quantity, whole):
            """Hand ``quantity`` to buyers in turn; yields (buyer, amount, cost)."""
            for buyer in near:
                if quantity <= 1e-9:
                    return
                if buyer.deposits:
                    self.banking.cash_up(buyer, economy.money_of(buyer))
                budget = max(0.0, buyer.money - cash_needed(buyer, prices, rules))
                amount = quantity if price <= 0 else min(quantity, budget / price)
                if whole:
                    amount = math.floor(amount + 1e-9)
                if amount <= (0 if whole else 1e-6):
                    continue
                quantity -= amount
                yield buyer, amount, amount * price

        for resource in economy.GOODS:
            for buyer, units, cost in sell(prices[resource], math.floor(dead.inventory.count(resource) + 1e-9), True):
                economy.transfer(dead, buyer, resource, units)
                buyer.money -= cost
                got = sold.setdefault(buyer.name, {"cost": 0.0, "items": []})
                got["cost"] += cost
                got["items"].append(f"{units:g} {resource}")
        for resource, shares in list(dead.assets.items()):
            for buyer, amount, cost in sell(asset_prices.get(resource, 0.0), shares, False):
                transfer_shares(dead, buyer, resource, amount)
                buyer.money -= cost
                got = sold.setdefault(buyer.name, {"cost": 0.0, "items": []})
                got["cost"] += cost
                got["items"].append(f"{amount:.2f} {resource} asset")
                self.asset_trades += 1
                self.asset_trade_money += cost
        if sold:
            parts = "; ".join(f"{name} bought {', '.join(g['items'])} for ${g['cost']:,.2f}" for name, g in sold.items())
            self.log(f"{dead.name}'s estate sold at market price: {parts}")
        else:
            self.log(f"{dead.name}'s estate found no buyer")

    def interact(self, a, b):
        """Two agents touched. If either needs something they trade, then walk apart.

        Afterwards the pair ignores each other for rules.cooldown_steps after a deal,
        or rules.retry_steps when nothing could be traded (the seller may have some
        to spare again soon, and with few sellers a long wait can be fatal). An agent
        that is still in need after the deal doesn't walk away: it goes straight on
        to the next seller.
        """
        rules = self.rules
        scarcity = self.scarcity
        if not rules.commerce_enabled:
            return  # no commerce: agents don't trade
        if not (economy.wants_anything(a, rules, scarcity) or economy.wants_anything(b, rules, scarcity)):
            return  # a casual bump: nobody needs anything
        prices = self.current_prices()
        # Paying "by card": both can spend their bank deposits (they redeposit the spare later).
        for x in (a, b):
            if x.deposits:
                self.banking.cash_up(x, economy.money_of(x))
        deals = economy.trade(a, b, prices, rules, self.rng, scarcity, self.unit_markups())
        for buyer, seller, bought, paid, stocked, unit_prices in deals:
            self.recorder.count("goods_deals")
            # Production tax: the seller pays its share of the money it got for the goods.
            tax = min(max(0.0, seller.money), self.government.tax("production", paid.get("money", 0.0)))
            if tax > 0:
                seller.money -= tax
                self.government.collect("production", tax)
            # Units bought beyond its needs: industry inputs or a stockpile.
            inputs = {r: n for r, n in stocked.items() if economy.input_target(buyer, r, rules)}
            hoard = {r: n for r, n in stocked.items() if r not in inputs}
            note = f" ({economy.describe(inputs)} as industry inputs)" if inputs else ""
            note += f" ({economy.describe(hoard)} to stockpile)" if hoard else ""
            rising = [f"{r} {lo:.2f}→{hi:.2f}" for r, (lo, hi) in unit_prices.items() if hi > lo + 1e-9]
            if rising:
                note += f" [price rose per unit: {', '.join(rising)}]"
            self.log(f"{buyer.name} got {economy.describe(bought)} from {seller.name} "
                     f"for {economy.describe_payment(paid)}{note}")
        for reason in economy.unmet(a, b, rules, scarcity) + economy.unmet(b, a, rules, scarcity):
            self.log(f"No trade: {reason}")

        wait = rules.cooldown_steps if deals else rules.retry_steps
        self.cooldowns[frozenset((a.id, b.id))] = (self.tick + wait, bool(deals))
        if deals:
            self.depart(a, b)
            for agent in (a, b):
                if economy.is_needy(agent, rules) or economy.alarmed(agent, rules):
                    agent.depart_steps = 0

    def depart(self, a, b):
        """Send a and b off in roughly opposite directions."""
        away = math.atan2(a.y - b.y, a.x - b.x)
        if a.x == b.x and a.y == b.y:
            away = self.rng.uniform(-math.pi, math.pi)
        steps = self.rules.depart_steps
        a.depart(away + self.rng.uniform(-self.MAX_TURN, self.MAX_TURN), steps)
        b.depart(away + math.pi + self.rng.uniform(-self.MAX_TURN, self.MAX_TURN), steps)

    def log(self, message):
        self.events.append({"tick": self.tick, "message": message})
        del self.events[:-200]

    def reserve_of(self, agent):
        """{good: units} the agent wants in reserve because the good is becoming scarce."""
        if not self.rules.stockpiling_enabled:
            return {}
        scarce = [r for r, d in self.scarcity.items() if d >= self.rules.scarcity_trigger and self.rules.is_active(r)]
        return {r: n for r in scarce if (n := economy.stockpile_target(agent, r, self.rules, self.scarcity))}

    def base_money(self):
        """All the money there is: agents' cash, their companies' cash and the banks' cash.
        Trades, wages, deposits, loans and dividends only move it; the government creates it."""
        return (sum(a.money + a.company_cash for a in self.agents)
                + sum(b.reserves + b.cb_reserves for b in self.banking.banks) + self.government.treasury)

    def money_issued(self):
        """New money put in so far: by the government (public works, interest on reserves) and the
        central bank's loans to banks still outstanding. base_money() = starting money + this."""
        return self.government.money_created + self.government.llr_outstanding

    def retain_earnings(self):
        """Each owner's companies keep part of this step's profit (goods sold minus wages paid) as
        company cash and pay the rest out to the owner as dividends: the owner's payout_ratio
        (a personality trait) decides the split. Company cash pays wages and builds new capacity
        in the owner's own industries (Build). Two limits, as for real companies:
        - the owner always takes enough to cover its own budget (it has to live);
        - a company keeps only what it can use (company_cash_cap: a month of wages plus one new
          asset share); the rest is paid out.
        An agent that no longer owns any company gets its company cash back."""
        from .modules.invest import budget_needed
        prices = self.current_prices()
        for a in self.agents:
            wages = a.flow.get("wages_paid", 0.0)
            a.wage_avg = 0.95 * getattr(a, "wage_avg", 0.0) + 0.05 * wages
            if not a.assets:
                if a.company_cash:
                    a.money += a.company_cash
                    a.company_cash = 0.0
                continue
            profit = a.flow["sources"].get("goods", 0.0) - wages
            if profit > 0:
                # Profit tax first, then the split between dividends and retained earnings.
                tax = min(a.money, self.government.tax("profit", profit))
                if tax > 0:
                    a.money -= tax
                    self.government.collect("profit", tax)
                    profit -= tax
                keep = min(a.money, profit * (1 - a.personality["payout_ratio"]))
                if keep > 0:
                    a.money -= keep
                    a.company_cash += keep
                    self.retained_total += keep
            if a.company_cash <= 0:
                continue
            # The owner's own budget comes first, then nothing idle above what the company can use.
            short = budget_needed(a, prices, self) - economy.money_of(a)
            excess = a.company_cash - self.company_cash_cap(a, prices)
            payout = min(a.company_cash, max(short, excess, 0.0))
            if payout > 0:
                a.company_cash -= payout
                a.money += payout
                self.retained_total -= payout

    def company_cash_cap(self, agent, prices):
        """Most company cash an owner's companies keep: a month of its wage bill plus what one new
        asset share of its most expensive industry costs to build."""
        build = max((c for g in agent.assets if (c := self.build_cost_money(g, prices))), default=0.0)
        return self.rules.month_steps * getattr(agent, "wage_avg", 0.0) + build

    def _agent_entry(self, agent, full, prices):
        entry = dict(agent.to_dict(self.rules, full=full), reserve=self.reserve_of(agent))
        if full:
            from .modules.invest import budget
            b = budget(agent, prices, self)
            entry["budget"] = {k: round(v, 2) for k, v in b.items()}
            entry["budget"]["spare"] = round(economy.money_of(agent) - b["total"], 2)
            entry["income"] = round(agent.income_avg, 2)
        return entry

    def to_dict(self, detail=None):
        """The whole state for the UI. ``detail``: ids of agents to describe in full ("all" for
        everyone); the rest get a compact entry (position, needs, goods, activity). By default
        everyone is in full in games of up to FULL_DETAIL_AGENTS agents."""
        if detail is None:
            detail = "all" if len(self.agents) <= FULL_DETAIL_AGENTS else ()
        if detail != "all":
            detail = set(detail)
        prices = self.current_prices()
        return {
            "tick": self.tick,
            "width": self.width,
            "height": self.height,
            "contact_distance": self.contact_distance,
            "seed": self.seed,
            "rules": self.rules.to_dict(),
            # This game's industries: layer (from the recipes), whether it exists (layer <= the
            # game's industry_layers), the need it relieves and how much one unit relieves.
            "industries": {g: {"layer": self.rules.layer(g), "active": self.rules.is_active(g),
                               "need": self.rules.need_of(g), "relief": self.rules.relief(g),
                               "effects": self.rules.effects_of(g)}
                           for g in economy.GOODS},
            "consumer_needs": list(self.rules.consumer_needs),
            "banking": self.banking.to_dict(self),
            # National accounts of the latest step (GDP over the last year, price indexes).
            "macro": ({k: round(self.recorder.history[-1][k], 4) for k in
                       ("gdp_nominal", "gdp_real", "deflator", "cpi", "inflation", "accounts_steps")}
                      if self.recorder.history else None),
            # Industries left out because their recipe needs a good that isn't in this game.
            "auto_excluded": list(self.rules.auto_excluded),
            "government": self.government.to_dict(self),
            "market": {
                "prices": self.current_prices(),
                "base_prices": economy.market_prices(self.agents, self.rules),
                "multiplier": self.price_multiplier,
                "pressure": {r: economy.demand_pressure(self.buyers[r], self.sellers[r], r, self.rules)
                             for r in economy.RESOURCES},
                "concentration": self.concentration,
                "concentration_factor": {r: economy.concentration_factor(self.concentration[r], r, self.rules)
                                         for r in economy.RESOURCES},
                "buyers": self.buyers,
                "sellers": self.sellers,
                "markups": self.unit_markups(),
                "price_history": {r: list(h) for r, h in self.price_history.items()},
                "assets": {g: sum(a.assets.get(g, 0) for a in self.agents) for g in economy.GOODS},
                "asset_prices": self.asset_prices(),
                "asset_output_each": {g: self.asset_output(g, 1) for g in economy.GOODS},
                "productivity": self.productivity_now,
                "asset_output": {g: self.asset_output(g, sum(a.assets.get(g, 0) for a in self.agents))
                                 for g in economy.GOODS},
                "asset_labor": self.asset_labor_now,
                # Average units made / used as inputs per step over the last 20 steps.
                "produced_recent": self.recent_flow("produced"),
                "used_recent": self.recent_flow("used"),
                "expired_recent": self.recent_flow("expired"),
                "consumed_recent": self.recent_flow("consumed"),
                "labor": self.labor.to_dict(),
                "asset_trades": self.asset_trades,
                "assets_built": self.assets_built,
                "assets_depreciated": {g: round(v, 3) for g, v in self.assets_depreciated.items()},
                "build_cost_money": {g: self.build_cost_money(g) for g in self.rules.active_goods},
                "asset_trade_money": self.asset_trade_money,
                # Average units per agent over the scarcity window (oldest first) and how much it fell.
                "per_agent_history": {r: list(h) for r, h in self.per_agent_history.items()},
                "scarcity": self.scarcity,
                "price_level": round(self.price_level, 4),
                "sell_through": {g: round(v, 3) for g, v in self.sell_through.items()},
                "buyer_concentration": {r: round(v, 3) for r, v in self.buyer_concentration.items()},
                # Per product: agents owning its industry, and those that made some this step.
                "owners": {g: sum(1 for a in self.agents if a.assets.get(g, 0) > 0) for g in self.rules.active_goods},
                "producing": {g: sum(1 for a in self.agents if a.flow["produced"].get(g, 0) > 0)
                              for g in self.rules.active_goods},
                "stockpiling": {r: self.rules.stockpiling_enabled and d >= self.rules.scarcity_trigger
                                for r, d in self.scarcity.items()},
                "money": sum(a.money for a in self.agents),
                "company_cash": round(sum(a.company_cash for a in self.agents), 2),
                "retained_total": round(self.retained_total, 2),
                "units": {r: sum(a.inventory.count(r) for a in self.agents) for r in economy.RESOURCES},
            },
            "agents": [self._agent_entry(a, detail == "all" or a.id in detail, prices) for a in self.agents],
            # Only pairs that can interact; pairs in cooldown just overlap.
            "contacts": [[a.id, b.id] for a, b in self.contacts() if not self.in_cooldown(a, b)],
            "events": self.events[-50:],
        }
