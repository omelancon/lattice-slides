class Cache:
    """v1 as first written, with the bug the morph slide fixes (segments: spec 8.10)."""

    def __init__(self, capacity):
        self.capacity = capacity
        self.items = {}
        self.order = []

    def put(self, key, value):
        if key in self.items:
            # @refresh
            self.order.remove(key)
            # @end
        # @full
        elif len(self.items) > self.capacity:
        # @end
            # @evict
            oldest = self.order.pop(0)
            del self.items[oldest]
            # @end
        self.items[key] = value
        self.order.append(key)
