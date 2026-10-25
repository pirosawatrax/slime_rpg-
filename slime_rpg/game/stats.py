"""Player stats: level, experience, the four stats (grown by random points at each level-up), HP and colour."""
from dataclasses import dataclass

import config as C
from game import colors, eating, progression


@dataclass
class LevelUp:
    level: int
    gains: dict            # stat -> amount gained, e.g. {"hp": 8, "atk": 1}


class PlayerStats:
    def __init__(self, level=1, hp=None, color=C.START_COLOR, xp=0, base=None):
        self.level = level
        self.xp = xp
        self.base = dict(base) if base else progression.average_stats(level)
        self.color = tuple(float(c) for c in color)
        self.hp = self.max_hp if hp is None else hp
        self.version = 0                         # bumped on change (HUD refresh)

    max_hp = property(lambda self: self.base["hp"])
    atk = property(lambda self: self.base["atk"])
    defense = property(lambda self: self.base["def"])
    spd = property(lambda self: self.base["spd"])

    def apply_hp(self, delta):
        """Healing, and self-inflicted loss such as eating: never kills (HP stays at 1 or more)."""
        self.hp = max(1, min(self.max_hp, self.hp + delta))
        self.version += 1

    def take_damage(self, amount):
        """Damage from an enemy. Returns True when this killed the player."""
        self.hp = max(0, self.hp - amount)
        self.version += 1
        return self.hp <= 0

    def restore_full(self):
        self.hp = self.max_hp
        self.version += 1

    def eat(self, mineral_rgb):
        """Returns the HP change. The colour moves toward the mineral either way."""
        delta, new_color = eating.eat_effect(self.color, mineral_rgb, self.max_hp)
        self.color = new_color
        self.apply_hp(delta)
        return delta

    def add_xp(self, amount, rng):
        """Add experience; returns a list of LevelUp (possibly several). Each level hands out random growth points."""
        self.xp += amount
        ups = []
        while self.xp >= progression.xp_needed(self.level):
            self.xp -= progression.xp_needed(self.level)
            self.level += 1
            gains = {s: 0 for s in progression.STATS}
            for _ in range(rng.randint(*C.GROWTH_POINTS)):
                pick = rng.choices(progression.STATS, weights=[C.GROWTH_WEIGHTS[s] for s in progression.STATS])[0]
                gains[pick] += C.GROWTH_PER_POINT[pick]
            for s, g in gains.items():
                self.base[s] += g
            self.hp = min(self.max_hp, self.hp + gains["hp"])      # new max HP comes as current HP too
            ups.append(LevelUp(self.level, {s: g for s, g in gains.items() if g}))
        self.version += 1
        return ups

    def hsv(self):
        return colors.hsv(self.color)
