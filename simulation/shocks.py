"""Exogenous shocks: sudden resource shortages, disasters (housing/asset loss), and epidemics.

Can be triggered manually by a trainer (POST /api/shock) at any time, or occur randomly when
``rules.shocks_enabled`` and ``rules.shock_chance_year > 0``. Uses its own RNG stream so turning
shocks on/off doesn't perturb the rest of the simulation's randomness.
"""
import math
import random

from .rules import GOODS

DEFAULT_SHORTAGE_GOODS = ("grain", "water", "timber", "oil")


class Shocks:
    def __init__(self, rules, seed=None):
        self.enabled = rules.shocks_enabled
        self.chance_year = rules.shock_chance_year
        self.rng = random.Random(f"shocks-{seed}")
        self.next_id = 1
        self.shortages = []   # [{"id", "goods", "severity", "started", "ends"}]
        self.epidemics = []   # [{"id", "started", "contagion_rate", "lethality_rate", "health_impact",
                              #   "duration", "radius", "infected": {id: days_left}, "immune": set(),
                              #   "total_infected": int, "total_deaths": int}]
        self.history = []     # recent shock summaries (last 30)

    def _record(self, entry):
        self.history.append(entry)
        del self.history[:-30]

    # ---------- productivity modifier ----------

    def productivity_factor(self, good):
        """Multiplier on ``good``'s productivity from active shortages (1.0 when none)."""
        factor = 1.0
        for s in self.shortages:
            if good in s["goods"]:
                factor *= max(0.05, 1.0 - s["severity"])
        return factor

    # ---------- triggers ----------

    def trigger_shortage(self, world, goods=None, severity=0.5, days=60):
        """Sudden resource shortage: cuts productivity of ``goods`` by ``severity`` for ``days``."""
        active = world.rules.active_goods
        if goods:
            picked = [g for g in goods if g in active]
        else:
            candidates = [g for g in DEFAULT_SHORTAGE_GOODS if g in active] or list(active[:3])
            picked = [self.rng.choice(candidates)] if candidates else []
        if not picked:
            return None
        severity = min(0.95, max(0.05, float(severity)))
        days = max(1, int(days))
        shock = {"id": self.next_id, "kind": "shortage", "goods": picked, "severity": severity,
                 "started": world.tick, "ends": world.tick + days}
        self.next_id += 1
        self.shortages.append(shock)
        names = ", ".join(picked)
        msg = f"Resource shortage: {names} output -{severity * 100:.0f}% for {days} days"
        world.log(msg)
        self._record({"id": shock["id"], "kind": "shortage", "tick": world.tick, "summary": msg})
        return shock

    def trigger_disaster(self, world, house_loss=0.2, asset_loss=0.0):
        """Disaster: destroys a share of houses (and optionally industry assets)."""
        house_loss = min(1.0, max(0.0, float(house_loss)))
        asset_loss = min(0.9, max(0.0, float(asset_loss)))
        destroyed_houses = 0
        if world.rules.housing_enabled and house_loss > 0 and world.housing.houses:
            count = max(1, round(len(world.housing.houses) * house_loss))
            victims = self.rng.sample(world.housing.houses, min(count, len(world.housing.houses)))
            for h in victims:
                if h.occupant is not None:
                    world.housing.move_out(h.occupant)
                if h.owner is not None:
                    # Write off any mortgage tied to the destroyed house.
                    loan = world.banking.mortgage_on(h, h.owner)
                    if loan is not None:
                        bank = world.banking.bank_by_id(loan.bank_id)
                        if bank is not None and loan in bank.loans:
                            world.banking._write_off(world, bank, loan, "house destroyed in disaster")
                    if h in h.owner.houses:
                        h.owner.houses.remove(h)
                world.housing.houses.remove(h)
                destroyed_houses += 1
        destroyed_shares = 0.0
        if asset_loss > 0:
            for a in world.agents:
                for g in list(a.assets):
                    lost = a.assets[g] * asset_loss
                    a.assets[g] -= lost
                    destroyed_shares += lost
                    if a.assets[g] <= 1e-6:
                        del a.assets[g]
        sid = self.next_id
        self.next_id += 1
        parts = []
        if destroyed_houses:
            parts.append(f"{destroyed_houses} house{'s' if destroyed_houses != 1 else ''} destroyed")
        if destroyed_shares > 0.01:
            parts.append(f"{destroyed_shares:.1f} asset shares damaged")
        msg = "Disaster struck: " + (", ".join(parts) if parts else "no structures damaged")
        world.log(msg)
        entry = {"id": sid, "kind": "disaster", "tick": world.tick, "houses_destroyed": destroyed_houses,
                 "shares_destroyed": round(destroyed_shares, 2), "summary": msg}
        self._record(entry)
        return entry

    def trigger_epidemic(self, world, initial_infected=3, contagion_rate=0.15, lethality_rate=0.01,
                         health_impact=0.04, duration=30, radius=120.0):
        """Epidemic: infects initial agents; spreads to nearby agents, worsens health, and can kill."""
        if not world.agents:
            return None
        k = min(len(world.agents), max(1, int(initial_infected)))
        patient_zeros = self.rng.sample(world.agents, k)
        epi = {
            "id": self.next_id, "kind": "epidemic", "started": world.tick,
            "contagion_rate": min(1.0, max(0.0, float(contagion_rate))),
            "lethality_rate": min(1.0, max(0.0, float(lethality_rate))),
            "health_impact": max(0.0, float(health_impact)),
            "duration": max(1, int(duration)),
            "radius": max(1.0, float(radius)),
            "infected": {a.id: max(1, int(duration)) for a in patient_zeros},
            "immune": set(),
            "total_infected": k,
            "total_deaths": 0,
        }
        self.next_id += 1
        self.epidemics.append(epi)
        msg = (f"Epidemic outbreak: {k} infected (contagion {epi['contagion_rate']*100:.0f}%/day, "
               f"lethality {epi['lethality_rate']*100:.1f}%/day)")
        world.log(msg)
        self._record({"id": epi["id"], "kind": "epidemic", "tick": world.tick, "summary": msg})
        return epi

    # ---------- daily step ----------

    def step(self, world):
        # 1. Expire finished shortages.
        still = []
        for s in self.shortages:
            if world.tick >= s["ends"]:
                world.log(f"Resource shortage ended ({', '.join(s['goods'])})")
            else:
                still.append(s)
        self.shortages = still

        # 2. Advance active epidemics (health impact, lethality, contagion, recovery).
        active_epis = []
        for epi in self.epidemics:
            infected_ids = list(epi["infected"])
            new_cases = []
            for aid in infected_ids:
                agent = world.agent_by_id(aid)
                if agent is None or agent not in world.alive:
                    epi["infected"].pop(aid, None)
                    continue
                # Health deteriorates faster while infected.
                if epi["health_impact"] > 0:
                    agent.health = min(1.0, agent.health + epi["health_impact"])
                # Contagion to nearby susceptible agents.
                if epi["contagion_rate"] > 0:
                    r = epi["radius"]
                    for other in world.agents:
                        if other.id == aid or other.id in epi["infected"] or other.id in epi["immune"]:
                            continue
                        if math.hypot(agent.x - other.x, agent.y - other.y) <= r:
                            if self.rng.random() < epi["contagion_rate"]:
                                new_cases.append(other.id)
                # Lethality check (only when death_enabled).
                if world.rules.death_enabled and epi["lethality_rate"] > 0:
                    if self.rng.random() < epi["lethality_rate"]:
                        epi["infected"].pop(aid, None)
                        epi["total_deaths"] += 1
                        world._die(agent, "epidemic")
                        continue
                # Recovery countdown.
                epi["infected"][aid] -= 1
                if epi["infected"][aid] <= 0:
                    del epi["infected"][aid]
                    epi["immune"].add(aid)
            for nid in set(new_cases):
                if nid not in epi["infected"] and nid not in epi["immune"] and world.agent_by_id(nid) is not None:
                    epi["infected"][nid] = epi["duration"]
                    epi["total_infected"] += 1
            if epi["infected"]:
                active_epis.append(epi)
            else:
                world.log(f"Epidemic ended: {epi['total_infected']} infected in total, {epi['total_deaths']} died")
        self.epidemics = active_epis

        # 3. Optional random shocks when the module is enabled.
        if self.enabled and self.chance_year > 0 and world.agents:
            daily_chance = self.chance_year / max(1, world.year_steps())
            if self.rng.random() < daily_chance:
                kind = self.rng.choice(("shortage", "disaster", "epidemic"))
                if kind == "shortage":
                    self.trigger_shortage(world)
                elif kind == "disaster":
                    self.trigger_disaster(world)
                else:
                    self.trigger_epidemic(world)

    def to_dict(self):
        return {
            "enabled": self.enabled,
            "chance_year": self.chance_year,
            "shortages": [{"id": s["id"], "goods": list(s["goods"]), "severity": s["severity"],
                           "started": s["started"], "ends": s["ends"]} for s in self.shortages],
            "epidemics": [{"id": e["id"], "started": e["started"], "infected": len(e["infected"]),
                           "immune": len(e["immune"]), "total_infected": e["total_infected"],
                           "total_deaths": e["total_deaths"], "contagion_rate": e["contagion_rate"],
                           "lethality_rate": e["lethality_rate"]} for e in self.epidemics],
            "infected_ids": sorted({aid for e in self.epidemics for aid in e["infected"]}),
            "history": self.history[-15:],
        }
