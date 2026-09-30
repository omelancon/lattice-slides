class Cache:
    def __init__(self, capacity):
        self.capacity = capacity
        self.items = {}
        self.order = []

    def get(self, key):
        if key not in self.items:
            return None
        self.order.remove(key)
        self.order.append(key)
        return self.items[key]

    def put(self, key, value):
        if key in self.items:
            self.order.remove(key)
        elif len(self.items) == self.capacity:
            oldest = self.order.pop(0)
            del self.items[oldest]
        self.items[key] = value
        self.order.append(key)
