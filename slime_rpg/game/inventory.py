"""20 slots. Items stack up to a per-item limit; same item = same stack (minerals will join in stage 3)."""
import config as C
from items import stack_limit


class Inventory:
    def __init__(self, size=C.INVENTORY_SLOTS):
        self.slots = [None] * size            # each: [item_id, count] or None
        self.version = 0                      # bumped on every change (HUD refresh)

    def used_slots(self):
        return sum(1 for s in self.slots if s is not None)

    def is_full(self):
        return self.used_slots() == len(self.slots)

    def free_space_for(self, item):
        limit = stack_limit(item)
        room = 0
        for s in self.slots:
            if s is None:
                room += limit
            elif s[0] == item:
                room += limit - s[1]
        return room

    def add(self, item, count=1):
        """Add items; returns how many did NOT fit (they are simply lost, see design 8.5)."""
        limit = stack_limit(item)
        left = count
        for s in self.slots:                  # top up existing stacks first
            if left and s is not None and s[0] == item and s[1] < limit:
                n = min(left, limit - s[1])
                s[1] += n
                left -= n
        for i, s in enumerate(self.slots):    # then open empty slots
            if left and s is None:
                n = min(left, limit)
                self.slots[i] = [item, n]
                left -= n
        if left != count:
            self.version += 1
        return left

    def take(self, index, count=1):
        """Remove items from a slot. Returns the item id removed, or None if the slot is empty."""
        s = self.slots[index]
        if s is None:
            return None
        item = s[0]
        s[1] -= count
        if s[1] <= 0:
            self.slots[index] = None
        self.version += 1
        return item

    def item_at(self, index):
        s = self.slots[index]
        return None if s is None else s[0]

    def count(self, item):
        return sum(s[1] for s in self.slots if s is not None and s[0] == item)

    def grow(self, extra):
        """More slots (storage expansion)."""
        self.slots.extend([None] * extra)
        self.version += 1

    def remove_item(self, item, count):
        """Take `count` of an item from any stacks. Returns False (changing nothing) if there are not enough."""
        if self.count(item) < count:
            return False
        for i, s in enumerate(self.slots):
            if count and s is not None and s[0] == item:
                n = min(count, s[1])
                s[1] -= n
                count -= n
                if s[1] == 0:
                    self.slots[i] = None
        self.version += 1
        return True
