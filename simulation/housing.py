"""The housing market (rules.housing_enabled).

Houses are whole assets: each houses exactly one agent, whose shelter need it meets every day
(rules.house_relief); an agent without a house is homeless and its shelter need grows at
rules.homeless_shelter_rate (then the shelter penalties follow: health worsens twice as fast,
sleep recovers worse). Each house has an owner (an agent, or the government: public housing)
and maybe an occupant: its owner, a tenant, or nobody (vacant).

- New houses: homebuilders (owners of the housing industry) turn every rules.house_units units
  of housing they made into a house, and put it up for sale.
- Price: never below the minimum, house_min_multiple x the average price of goods (so it follows
  the price level); above it, the cost of the housing units x demand pressure (agents without a
  home / houses free to move into, between 0.5 and 3).
- Rent: price x rent_yield per day, paid by the tenant to the owner every day. A tenant who can't
  pay for eviction_days days in a row is evicted.
- Buying a home: an agent without a home of its own buys a vacant house for sale once its money
  (deposits included) covers the price on top of its monthly budget, and moves in.
- Buying to let: only an agent living in its own house may buy more, paying cash from money
  beyond its budget, when the rent yield beats the bank deposit rate; it rents them out.
- Renting: a homeless agent rents a vacant house it isn't buying if it can pay a month's rent.
- Selling: owners short of cash put a house they don't live in up for sale.
- Death: a dead owner's houses go to the nearest agents who can pay the price (the money leaves
  with the estate); what nobody can buy becomes public housing (rent to the treasury). A dead
  tenant's house becomes vacant.
"""
import math

from . import economy


class House:
    __slots__ = ("id", "owner", "occupant", "for_sale", "arrears", "built")

    def __init__(self, hid, owner, built):
        self.id = hid
        self.owner = owner          # Agent, or None = the government (public housing)
        self.occupant = None        # Agent living there, or None (vacant)
        self.for_sale = False
        self.arrears = 0            # days its tenant couldn't pay the rent, in a row
        self.built = built


class HousingMarket:
    def __init__(self, rules):
        self.houses = []
        self.next_id = 1
        self.min_multiple = rules.house_min_multiple
        self.rent_yield = rules.rent_yield
        self.eviction_days = rules.eviction_days
        self.built = 0
        self.sales = 0
        self.evictions = 0
        self.built_days = []        # houses finished on each of the last 30 days
        self.sold_days = []
        self.rent_day = 0.0         # rent paid yesterday
        self._price = None          # (tick, price) once per day

    # ---------- houses and who lives where ----------

    def new_house(self, owner, tick):
        h = House(self.next_id, owner, tick)
        self.next_id += 1
        self.houses.append(h)
        if owner is not None:
            owner.houses.append(h)
        return h

    @staticmethod
    def move_in(agent, house):
        if agent.home is not None and agent.home is not house:
            HousingMarket.move_out(agent)
        house.occupant = agent
        house.arrears = 0
        agent.home = house

    @staticmethod
    def move_out(agent):
        if agent.home is not None:
            agent.home.occupant = None
            agent.home.arrears = 0
        agent.home = None

    @staticmethod
    def set_owner(house, owner):
        if house.owner is not None and house in house.owner.houses:
            house.owner.houses.remove(house)
        house.owner = owner
        if owner is not None:
            owner.houses.append(house)
        house.for_sale = False

    def setup(self, world, owners, others):
        """Starting houses: each owner of assets lives in one; the rest are its rentals, let to
        other agents (the last ones homeless)."""
        rules = world.rules
        n = round(len(world.agents) * rules.starting_houses)
        landlords = list(owners) or [None]
        houses = [self.new_house(landlords[i % len(landlords)], 0) for i in range(n)]
        free = list(houses)
        for a in owners:
            mine = next((h for h in free if h.owner is a), None)
            if mine is not None:
                self.move_in(a, mine)
                free.remove(mine)
        for a, h in zip(others, free):
            self.move_in(a, h)

    # ---------- prices ----------

    def min_price(self, world, prices=None):
        prices = prices or world.current_prices()
        goods = [prices[g] for g in world.rules.active_goods if g in prices]
        return self.min_multiple * (sum(goods) / len(goods) if goods else 0.0)

    def price(self, world):
        """Price of a house today (the same for every house)."""
        if self._price and self._price[0] == world.tick:
            return self._price[1]
        prices = world.current_prices()
        cost = world.rules.house_units * prices.get("housing", 0.0)
        wanting = sum(1 for a in world.agents if a.home is None or a.home.owner is not a)
        free = sum(1 for h in self.houses if h.occupant is None or h.for_sale)
        pressure = min(3.0, max(0.5, (0.25 * wanting + 1) / (free + 1)))
        value = max(self.min_price(world, prices), cost * pressure)
        self._price = (world.tick, value)
        return value

    def rent(self, world):
        return self.price(world) * self.rent_yield

    # ---------- every day ----------

    def step(self, world):
        rules, gov = world.rules, world.government
        tick = world.tick
        # 1. Homebuilders finish houses from the housing units they made.
        built = 0
        for a in world.agents:
            units = a.inventory.count("housing")
            while units >= rules.house_units:
                a.inventory.remove("housing", rules.house_units)
                units -= rules.house_units
                h = self.new_house(a, tick)
                h.for_sale = True
                built += 1
        if built:
            world.log(f"{built} new house{'s' if built > 1 else ''} built (now {len(self.houses)})")
        self.built += built
        self.built_days = (self.built_days + [built])[-30:]
        price, rent = self.price(world), self.rent(world)

        # 2. Rent: tenants pay their landlord (the treasury for public housing); evictions.
        paid = 0.0
        for h in self.houses:
            t = h.occupant
            if t is None or t is h.owner:
                continue
            if economy.money_of(t) >= rent:
                if t.money < rent:
                    world.banking.cash_up(t, rent)
                t.money -= rent
                paid += rent
                h.arrears = 0
                if h.owner is None:
                    gov.treasury += rent
                else:
                    h.owner.money += rent
                    economy.earn(h.owner, rent, "rent")
            else:
                h.arrears += 1
                if h.arrears >= self.eviction_days:
                    self.evictions += 1
                    world.log(f"{t.name} was evicted from house {h.id} (rent unpaid for {h.arrears} days)")
                    self.move_out(t)
        self.rent_day = paid

        # 3. Owners short of cash put a house they don't live in up for sale.
        for a in world.agents:
            if a.houses and economy.money_of(a) < rent * 30:
                spare = [h for h in a.houses if h.occupant is not a and not h.for_sale]
                if spare:
                    spare[0].for_sale = True

        # 4. Buying and renting.
        from .modules.invest import budget_needed
        prices = world.current_prices()
        sold = 0
        listings = [h for h in self.houses if h.for_sale]
        vacant_listings = [h for h in listings if h.occupant is None]
        order = list(world.agents)
        world.rng.shuffle(order)
        deposit_year = (1 + world.banking.deposit_rate) ** world.year_steps() - 1 if world.banking.enabled else 0.0
        yield_year = (1 + self.rent_yield) ** world.year_steps() - 1
        if price <= 0:
            order = []                       # no prices yet (no money in the game): nothing changes hands
        for a in order:
            owns_home = a.home is not None and a.home.owner is a
            if not owns_home:
                # A home of its own: a vacant house for sale it can pay for on top of its budget.
                mine = [h for h in vacant_listings if h.owner is not a]
                if mine and economy.money_of(a) >= price \
                        and economy.money_of(a) - budget_needed(a, prices, world) >= price:
                    h = mine[-1]
                    vacant_listings.remove(h)
                    listings.remove(h)
                    self._buy(world, a, h, price)
                    self.move_in(a, h)
                    sold += 1
                    continue
                if a.home is None:
                    rentable = next((h for h in self.houses if h.occupant is None and h.owner is not a), None)
                    if rentable is not None and economy.money_of(a) >= rent * rules.month_steps:
                        self.move_in(a, rentable)
                        if rentable in vacant_listings:
                            vacant_listings.remove(rentable)
                continue
            # Buy to let: only with its own home, cash beyond its budget, and rent beating deposits.
            if listings and yield_year > deposit_year and economy.money_of(a) >= price + rules.min_investment \
                    and economy.money_of(a) - budget_needed(a, prices, world) - rules.min_investment >= price:
                h = next((h for h in reversed(listings) if h.owner is not a), None)
                if h is None:
                    continue
                listings.remove(h)
                if h in vacant_listings:
                    vacant_listings.remove(h)
                self._buy(world, a, h, price)
                sold += 1
        self.sales += sold
        self.sold_days = (self.sold_days + [sold])[-30:]

    def _buy(self, world, buyer, house, price):
        if buyer.money < price:
            world.banking.cash_up(buyer, price)
        buyer.money -= price
        seller = house.owner
        if seller is None:
            world.government.treasury += price
        else:
            seller.money += price
            economy.earn(seller, price, "assets")
            if seller.home is house:
                self.move_out(seller)
        self.set_owner(house, buyer)
        world.log(f"{buyer.name} bought house {house.id} for {price:,.2f}"
                  + (f" from {seller.name}" if seller else " from the government"))

    # ---------- death ----------

    def on_death(self, world, dead, near):
        """A dead agent's home is vacated; its houses go to the nearest agents who can pay
        (``near``: agents nearest first), else to the government."""
        from .modules.invest import cash_needed
        if dead.home is not None:
            self.move_out(dead)
        if not dead.houses:
            return
        price = self.price(world)
        prices = world.current_prices()
        for h in list(dead.houses):
            buyer = next((o for o in near if o.money - cash_needed(o, prices, world.rules) >= price), None)
            if buyer is not None:
                buyer.money -= price            # the estate's money leaves with the dead
                self.set_owner(h, buyer)
                world.log(f"{buyer.name} bought house {h.id} from {dead.name}'s estate for {price:,.2f}")
            else:
                self.set_owner(h, None)
                world.log(f"House {h.id} from {dead.name}'s estate became public housing")

    # ---------- report ----------

    def to_dict(self, world):
        n = len(self.houses)
        owner_occupied = sum(1 for h in self.houses if h.occupant is not None and h.occupant is h.owner)
        rented = sum(1 for h in self.houses if h.occupant is not None and h.occupant is not h.owner)
        landlords = {}
        for h in self.houses:
            if h.owner is not None and h.occupant is not h.owner:
                landlords[h.owner.name] = landlords.get(h.owner.name, 0) + 1
        price = self.price(world) if world.agents else 0.0
        return {"houses": n, "owner_occupied": owner_occupied, "rented": rented,
                "vacant": sum(1 for h in self.houses if h.occupant is None),
                "for_sale": sum(1 for h in self.houses if h.for_sale),
                "public": sum(1 for h in self.houses if h.owner is None),
                "homeless": sum(1 for a in world.agents if a.home is None),
                "price": round(price, 2), "min_price": round(self.min_price(world), 2) if world.agents else 0.0,
                "rent": round(price * self.rent_yield, 2), "rent_paid_day": round(self.rent_day, 2),
                "built_month": sum(self.built_days), "sold_month": sum(self.sold_days),
                "built": self.built, "sales": self.sales, "evictions": self.evictions,
                "min_multiple": self.min_multiple, "rent_yield": self.rent_yield,
                "eviction_days": self.eviction_days,
                "landlords": sorted(landlords.items(), key=lambda kv: -kv[1])[:8]}
