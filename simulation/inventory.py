"""A minimal item store every agent owns.

Items are kept as ``{item_name: quantity}``. It starts empty; later modules
(trading, gathering, ...) will add and remove items through this API.

Perishable items (``perishable={item: lifetime}``) are kept as batches that each
expire ``lifetime`` steps after they were made (lifetime 0: batches never expire). ``now`` is the current step (the
World updates it); ``expire()`` throws away batches past their date. Removing or
using a perishable item takes the oldest batches first, and ``take()`` hands the
batches over so they keep their expiry date when they change owner. Quantities
of perishable items may be fractional; ``count()`` reports whole units.
"""

import math
from collections import deque


class Inventory:
    def __init__(self, items=None, perishable=None, now=0):
        self.perishable = dict(perishable or {})
        self.now = now
        self.items = {}
        self.batches = {item: deque() for item in self.perishable}  # item -> deque of [expires, qty], oldest first
        for item, quantity in (items or {}).items():
            if item in self.perishable:
                if quantity:
                    self.add(item, quantity)
            else:
                self.items[item] = quantity

    def add(self, item, quantity=1, expires=None):
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        if item not in self.perishable:
            self.items[item] = self.items.get(item, 0) + quantity
            return
        if expires is None:
            lifetime = self.perishable[item]
            expires = self.now + lifetime if lifetime else math.inf
        batches = self.batches[item]
        if batches and batches[-1][0] == expires:
            batches[-1][1] += quantity
        elif not batches or batches[-1][0] < expires:
            batches.append([expires, quantity])
        else:  # older than the newest batch (e.g. bought): keep the deque sorted by expiry
            batches.append([expires, quantity])
            self.batches[item] = deque(sorted(batches, key=lambda b: b[0]))

    def take(self, item, quantity):
        """Remove ``quantity`` of a perishable item, oldest first. Returns [(expires, qty), ...]."""
        taken = []
        batches = self.batches[item]
        while quantity > 1e-9 and batches:
            expires, qty = batches[0]
            used = min(qty, quantity)
            taken.append((expires, used))
            quantity -= used
            if qty - used <= 1e-9:
                batches.popleft()
            else:
                batches[0][1] = qty - used
        return taken

    def remove(self, item, quantity=1):
        """Remove ``quantity`` of ``item``. Returns False if there isn't enough."""
        if self.amount(item) + 1e-9 < quantity:
            return False
        if item in self.perishable:
            self.take(item, quantity)
            return True
        self.items[item] -= quantity
        if self.items[item] == 0:
            del self.items[item]
        return True

    def set(self, item, quantity):
        if quantity < 0:
            raise ValueError("quantity must be >= 0")
        if item in self.perishable:
            self.batches[item].clear()
            if quantity:
                self.add(item, quantity)
            return
        self.items[item] = quantity

    def expire(self):
        """Throw away perishable batches past their date. Returns {item: quantity expired}."""
        expired = {}
        for item, batches in self.batches.items():
            while batches and batches[0][0] <= self.now:
                expired[item] = expired.get(item, 0) + batches.popleft()[1]
        return expired

    def amount(self, item):
        """Exact quantity, including fractions of perishable items."""
        if item in self.perishable:
            return sum(qty for _, qty in self.batches[item])
        return self.items.get(item, 0)

    def count(self, item):
        """Whole units held."""
        if item in self.perishable:
            return int(self.amount(item) + 1e-9)
        return self.items.get(item, 0)

    def to_dict(self):
        return {**self.items, **{item: self.count(item) for item in self.perishable}}
