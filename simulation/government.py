"""The central government: a policy interest rate and money injected by buying labour.

- ``min_rate``: no asset may be valued at a return below this rate. The effective
  return of an asset is max(its own asset_return, min_rate), so raising the rate
  lowers every asset's price (price = output x good price / return).
- ``labor_purchase``: units of labour the government hires every step in the
  labour market (labor.py), from the capacity employers didn't hire, cheapest
  first, at each worker's asking wage. It pays with newly created money, which is
  how money is injected into the economy. The labour goes into public works.

The policy starts from the game rules and can be changed while the game runs.
"""

class Government:
    def __init__(self, min_rate=0.0, labor_purchase=0.0):
        self.min_rate = min_rate
        self.labor_purchase = labor_purchase
        self.money_created = 0.0   # total new money paid out so far
        self.labor_bought = 0.0    # total labour bought so far
        self.last_spent = 0.0      # money created in the latest step

    def effective_return(self, rules, good):
        return max(rules.asset_return[good], self.min_rate)

    def to_dict(self):
        return {"min_rate": self.min_rate, "labor_purchase": self.labor_purchase,
                "money_created": self.money_created, "labor_bought": self.labor_bought,
                "last_spent": self.last_spent}
