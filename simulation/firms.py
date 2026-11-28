"""Firm Entity module (rules.firms_enabled).

When ``firms_enabled`` is False, businesses operate as simplified local stores directly on
``agent.assets``. When True, each active (owner, industry) business is tracked as a corporate
``Firm`` entity with:
- Income Statement (revenue, COGS, wages, depreciation, overhead, taxes, net income)
- Balance Sheet (cash, inventory, plant value, debt, equity)
- Cash Flow Statement (operating, investing, financing)
- Market Capitalization and P/E ratio
"""
from collections import deque

from . import economy


class Firm:
    def __init__(self, firm_id, owner_id, good, created_tick):
        self.id = firm_id
        self.owner_id = owner_id
        self.good = good
        self.created_tick = created_tick
        # Rolling 30-day statement flows (daily tuples: revenue, cogs, wages, dep, overhead, tax, net, op_cf, inv_cf, fin_cf)
        self.daily = deque(maxlen=30)
        # Latest snapshot values
        self.income_statement = {"revenue": 0.0, "cogs": 0.0, "wages": 0.0, "depreciation": 0.0,
                                 "overhead": 0.0, "taxes": 0.0, "net_income": 0.0}
        self.balance_sheet = {"cash": 0.0, "inventory": 0.0, "plant": 0.0, "total_assets": 0.0,
                              "debt": 0.0, "equity": 0.0}
        self.cash_flow = {"operating": 0.0, "investing": 0.0, "financing": 0.0, "net": 0.0}
        self.market_cap = 0.0
        self.pe_ratio = None

    def to_dict(self, world):
        owner = world.agent_by_id(self.owner_id)
        shares = owner.assets.get(self.good, 0.0) if owner else 0.0
        return {
            "id": self.id,
            "name": f"{owner.name} · {self.good}" if owner else f"Firm {self.id} ({self.good})",
            "owner_id": self.owner_id,
            "owner": owner.name if owner else None,
            "good": self.good,
            "shares": round(shares, 3),
            "market_cap": round(self.market_cap, 2),
            "pe_ratio": round(self.pe_ratio, 1) if self.pe_ratio is not None else None,
            "income_statement": {k: round(v, 2) for k, v in self.income_statement.items()},
            "balance_sheet": {k: round(v, 2) for k, v in self.balance_sheet.items()},
            "cash_flow": {k: round(v, 2) for k, v in self.cash_flow.items()},
        }


class FirmRegistry:
    def __init__(self, rules):
        self.enabled = rules.firms_enabled
        self.overhead_rate = rules.firm_overhead_rate   # daily overhead as share of plant value
        self.firms = {}       # (owner_id, good) -> Firm
        self.next_id = 1

    def step(self, world):
        """Sync corporate entities with active agent.assets and update financial statements."""
        if not self.enabled:
            return
        prices = world.current_prices()
        asset_prices = world.step_asset_prices()
        year = world.year_steps()
        gov = world.government

        active_keys = set()
        for a in world.agents:
            if not a.assets:
                continue
            # Total asset value for allocating owner-level company_cash, wages, and debt across firms.
            vals = {g: s * max(asset_prices.get(g, 0.0), world.build_cost_money(g, prices) or 0.0)
                    for g, s in a.assets.items() if s > 1e-6 and g in economy.GOODS}
            total_val = sum(vals.values()) or 1.0
            total_jobs = sum(world.asset_jobs(g, s) for g, s in a.assets.items() if s > 1e-6 and g in economy.GOODS) or 1.0
            owner_wages = a.flow.get("wages_paid", 0.0)
            owner_goods_rev = a.flow["sources"].get("goods", 0.0)
            # Estimate revenue split by produced value of each good this step.
            prod_vals = {g: a.flow["produced"].get(g, 0) * prices.get(g, 0.0) for g in vals}
            total_prod_val = sum(prod_vals.values())

            for g, plant_val in vals.items():
                key = (a.id, g)
                active_keys.add(key)
                firm = self.firms.get(key)
                if firm is None:
                    firm = self.firms[key] = Firm(self.next_id, a.id, g, world.tick)
                    self.next_id += 1
                shares = a.assets[g]
                val_share = plant_val / total_val
                job_share = world.asset_jobs(g, shares) / total_jobs

                # Income statement flows (today)
                rev_share = (prod_vals[g] / total_prod_val) if total_prod_val > 0 else val_share
                revenue = owner_goods_rev * rev_share
                made = a.flow["produced"].get(g, 0)
                cogs = made * world.input_cost(g, prices)
                wages = owner_wages * job_share
                dep_rate = world.depreciation_per_step(g)
                depreciation = plant_val * dep_rate
                overhead = plant_val * self.overhead_rate / year
                if overhead > 0:
                    # Fixed operating overhead paid from company cash (or owner cash).
                    pay = min(overhead, a.company_cash)
                    a.company_cash -= pay
                    rem = overhead - pay
                    if rem > 0 and a.money > 0:
                        take = min(rem, a.money)
                        a.money -= take
                ebt = revenue - cogs - wages - depreciation - overhead
                taxes = gov.tax("production", revenue) + (gov.tax("profit", ebt) if ebt > 0 else 0.0)
                net_income = ebt - taxes

                # Cash flow statement (today)
                op_cf = net_income + depreciation
                inv_cf = -(a.project["reinvested"] / max(1, world.rules.month_steps)) if (
                    a.project and a.project.get("good") == g and a.project.get("reinvested")) else 0.0
                payout = a.personality.get("payout_ratio", 0.5)
                fin_cf = -(net_income * payout) if net_income > 0 else 0.0

                firm.daily.append((revenue, cogs, wages, depreciation, overhead, taxes, net_income, op_cf, inv_cf, fin_cf))
                # Roll up 30-day statements
                sums = [sum(row[i] for row in firm.daily) for i in range(10)]
                firm.income_statement = {
                    "revenue": sums[0], "cogs": sums[1], "wages": sums[2],
                    "depreciation": sums[3], "overhead": sums[4], "taxes": sums[5], "net_income": sums[6],
                }
                firm.cash_flow = {
                    "operating": sums[7], "investing": sums[8], "financing": sums[9],
                    "net": sums[7] + sums[8] + sums[9],
                }

                # Balance sheet (point-in-time)
                cash = a.company_cash * val_share
                inv_val = a.inventory.count(g) * prices.get(g, 0.0)
                debt = a.debt * val_share
                total_assets = cash + inv_val + plant_val
                firm.balance_sheet = {
                    "cash": cash, "inventory": inv_val, "plant": plant_val,
                    "total_assets": total_assets, "debt": debt, "equity": total_assets - debt,
                }

                # Market capitalization & P/E
                firm.market_cap = max(0.0, plant_val + cash - debt)
                days = len(firm.daily)
                annual_net = sums[6] * (year / days) if days else 0.0
                firm.pe_ratio = (firm.market_cap / annual_net) if annual_net > 1e-6 else None

        # Remove firms whose owner died or sold all shares of that industry.
        for key in list(self.firms):
            if key not in active_keys:
                del self.firms[key]

    def to_dict(self, world):
        firms_list = sorted(self.firms.values(), key=lambda f: -f.market_cap)
        return {
            "enabled": self.enabled,
            "count": len(firms_list),
            "total_market_cap": round(sum(f.market_cap for f in firms_list), 2),
            "total_net_income_30d": round(sum(f.income_statement["net_income"] for f in firms_list), 2),
            "top_firms": [f.to_dict(world) for f in firms_list[:20]],
        }
