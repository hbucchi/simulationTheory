"""The central government and its central bank: a policy interest rate, the Basel capital
ratio banks must meet, and money injected by buying labour.

- ``min_rate``: no asset may be valued at a return below this rate. The effective
  return of an asset is max(its own asset_return, min_rate), so raising the rate
  lowers every asset's price (price = output x good price / return).
- ``capital_ratio`` (Basel): the central bank's rule for commercial banks. A bank's equity
  must be at least this share of its risk-weighted assets: its loans (cash reserves carry
  no risk, weight 0). At 12%, every $1 of equity backs at most $8.33 of loans. Equity is the
  owners' own money; deposits are third parties' money, so this caps how far a bank may
  lend other people's money against its own.
- ``labor_purchase``: units of labour the government hires every step in the
  labour market (labor.py), from the capacity employers didn't hire, cheapest
  first, at each worker's asking wage. It pays with newly created money, which is
  how money is injected into the economy. The labour goes into public works.

The policy starts from the game rules and can be changed while the game runs. With the
government switched off (``enabled`` False) there is no policy rate, no labour bought and
no capital rule: banks lend as far as their reserves and services allow.
"""

class Government:
    def __init__(self, min_rate=0.0, labor_purchase=0.0, capital_ratio=0.12, enabled=True):
        self.enabled = enabled
        self._min_rate = min_rate
        self._labor_purchase = labor_purchase
        self._capital_ratio = capital_ratio
        self.money_created = 0.0   # total new money paid out so far
        self.labor_bought = 0.0    # total labour bought so far
        self.last_spent = 0.0      # money created in the latest step

    # The policy in force: nothing while the government is switched off.
    min_rate = property(lambda self: self._min_rate if self.enabled else 0.0,
                        lambda self, v: setattr(self, "_min_rate", v))
    labor_purchase = property(lambda self: self._labor_purchase if self.enabled else 0.0,
                              lambda self, v: setattr(self, "_labor_purchase", v))
    capital_ratio = property(lambda self: self._capital_ratio if self.enabled else 0.0,
                             lambda self, v: setattr(self, "_capital_ratio", v))

    def effective_return(self, rules, good):
        return max(rules.asset_return[good], self.min_rate)

    def to_dict(self):
        return {"enabled": self.enabled, "min_rate": self._min_rate, "labor_purchase": self._labor_purchase,
                "capital_ratio": self._capital_ratio,
                "money_created": self.money_created, "labor_bought": self.labor_bought,
                "last_spent": self.last_spent}
