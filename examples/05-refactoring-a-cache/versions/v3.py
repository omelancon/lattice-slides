from collections import OrderedDict


class Cache:
    def __init__(self, capacity):
        self.capacity = capacity
        self.items = OrderedDict()
        self.hits = self.misses = 0

    def get(self, key):
        if key not in self.items:
            self.misses += 1
            return None
        self.hits += 1
        self.items.move_to_end(key)
        return self.items[key]

    def put(self, key, value):
        if key in self.items:
            self.items.move_to_end(key)
        elif len(self.items) == self.capacity:
            self.items.popitem(last=False)
        self.items[key] = value
