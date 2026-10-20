"""A minimal item store every agent owns.

Items are kept as ``{item_name: quantity}``. It starts empty; later modules
(trading, gathering, ...) will add and remove items through this API.
"""


class Inventory:
    def __init__(self, items=None):
        self.items = dict(items or {})

    def add(self, item, quantity=1):
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        self.items[item] = self.items.get(item, 0) + quantity

    def remove(self, item, quantity=1):
        """Remove ``quantity`` of ``item``. Returns False if there isn't enough."""
        if self.items.get(item, 0) < quantity:
            return False
        self.items[item] -= quantity
        if self.items[item] == 0:
            del self.items[item]
        return True

    def set(self, item, quantity):
        if quantity < 0:
            raise ValueError("quantity must be >= 0")
        self.items[item] = quantity

    def count(self, item):
        return self.items.get(item, 0)

    def to_dict(self):
        return dict(self.items)
