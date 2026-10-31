"""Turn-based battle (design section 6). Engine-free. `act()` resolves a whole round at once, but also records it as a
list of Events (action line, sound, result line with the damage number, ...) so the UI can show it one line at a time,
terminal style. Each event carries a snapshot of the numbers AFTER it, so the HP shown on screen changes exactly when
the matching line appears."""
from dataclasses import dataclass, field

import config as C
import items
import strings as T
from game import colors, progression


@dataclass
class Enemy:
    level: int
    max_hp: int
    hp: int
    atk: int
    defense: int
    spd: int
    color: tuple
    name: str = "Slime"


@dataclass
class Event:
    text: str
    sound: str = None          # sound effect to play when the line starts (None = silent)
    kind: str = "act"          # act | result | note: the UI pauses longer after results
    snap: dict = field(default_factory=dict)


def random_color(rng, extended=False):
    lo, hi = C.EXTENDED_COLOR_RANGE if extended else C.BASE_COLOR_RANGE
    return tuple(rng.uniform(lo, hi) for _ in range(3))


def make_enemy(level, rng, extended=False, mod_slimes=()):
    """Create a vanilla slime or choose a data-only MOD archetype using weighted random selection."""
    avg = progression.average_stats(level)
    v = C.ENEMY_STAT_VARIATION
    stat = {s: max(1, int(round(avg[s] * C.ENEMY_STRENGTH * rng.uniform(1 - v, 1 + v)))) for s in progression.STATS}
    name = "Slime"
    color = random_color(rng, extended)
    choices = [m for m in mod_slimes if isinstance(m, dict) and m.get("weight", 0) > 0]
    # Vanilla slimes have weight 10, so a weight-2 MOD slime appears roughly 1 in 6 encounters.
    total = 10 + sum(m["weight"] for m in choices)
    roll = rng.randrange(total)
    if roll >= 10:
        roll -= 10
        for mod in choices:
            if roll < mod["weight"]:
                name = mod["name"]
                multiplier = mod["stat_multiplier"]
                stat = {k: max(1, int(round(value * multiplier))) for k, value in stat.items()}
                color = tuple(rng.uniform(lo, hi) for lo, hi in zip(mod["color_min"], mod["color_max"]))
                break
            roll -= mod["weight"]
    return Enemy(level, stat["hp"], stat["hp"], stat["atk"], stat["def"], stat["spd"], color, name)


def make_boss(rng, extended=False):
    """The Slime King: exactly the average stats of a BOSS_LEVEL slime (times BOSS_STAT_MULT), with no random variation."""
    avg = progression.average_stats(C.BOSS_LEVEL)
    stat = {k: max(1, int(round(avg[k] * C.BOSS_STAT_MULT[k]))) for k in progression.STATS}
    return Enemy(C.BOSS_LEVEL, stat["hp"], stat["hp"], stat["atk"], stat["def"], stat["spd"], random_color(rng, extended))


def base_damage(fraction, atk, defense, target_max_hp):
    """Damage scales with the TARGET's max HP, so a fight lasts about as many rounds at any level.
    Equal ATK and DEF give fraction / 2 of max HP before colour and luck."""
    return target_max_hp * fraction * atk / (atk + defense)


def throw_value(multiplier):
    """Signed strength of a thrown mineral: 0 at THROW_NEUTRAL, negative (heals the enemy) below it."""
    return (multiplier - C.THROW_NEUTRAL) * C.THROW_SLOPE


def _tag(m):
    return T.TAG_STRONG if m >= 1.15 else (T.TAG_WEAK if m <= 0.85 else "")


class Battle:
    def __init__(self, stats, enemy, inventory, rng, name_of, boss=False, extended=False):
        """name_of(item) -> display name (the UI owns the strings for item names). boss=True: the Slime King rules apply
        (colour change every round with the next colour shown in advance, per-hit damage cap, no fleeing)."""
        self.stats, self.enemy, self.inventory, self.rng, self.name_of = stats, enemy, inventory, rng, name_of
        self.boss, self.extended = boss, extended
        self.who = T.BOSS_NAME if boss else getattr(enemy, "name", "Slime")
        self.next_color = self._pick_boss_color() if boss else None
        self.boss_won = False
        self.phase = "choose"            # choose | won | lost | fled
        self.log = []                    # every line shown so far (plain text)
        self.events = []                 # every Event so far
        self._unread = 0
        self.xp_gained = 0
        self.level_ups = []
        name = getattr(enemy, "name", "Slime")
        self._emit(T.BATTLE_APPEARED if name == "Slime" or boss else T.BATTLE_APPEARED_NAMED.format(name=name), None, "note")

    # ---- events -------------------------------------------------------
    def snapshot(self):
        s, e = self.stats, self.enemy
        return {"you_hp": max(0, s.hp), "you_max": s.max_hp, "you_level": s.level, "you_color": s.color,
                "enemy_hp": max(0, e.hp), "enemy_max": e.max_hp, "enemy_level": e.level, "enemy_color": e.color, "enemy_name": e.name,
                "boss": self.boss, "boss_next": self.next_color}

    def _emit(self, text, sound=None, kind="act"):
        self.events.append(Event(text, sound, kind, self.snapshot()))
        self.log.append(text)

    def take_events(self):
        """Events added since the last call (the UI feeds them to its presenter)."""
        new = self.events[self._unread:]
        self._unread = len(self.events)
        return new

    # ---- previews for the UI ------------------------------------------
    def tackle_multiplier(self):
        return colors.matchup(self.stats.color, self.enemy.color)

    def throw_multiplier(self, item):
        return colors.matchup(items.rgb(items.code_of(item)), self.enemy.color)

    # ---- one round ----------------------------------------------------
    def act(self, action, slot=None):
        """action: 'tackle' | 'throw' | 'eat' | 'flee'. Returns False (and uses no turn) if the action is not possible."""
        if self.phase != "choose":
            return False
        item = None
        if action in ("throw", "eat"):
            item = self.inventory.item_at(slot) if slot is not None else None
            if item is None or not items.is_mineral(item):
                self._emit(T.NOTE_NEED_MINERAL, None, "note")
                return False

        if action == "flee" and self.boss:
            self._emit(T.NOTE_NO_ESCAPE, None, "note")
            return False

        player_first = self.stats.spd >= self.enemy.spd
        for who in (("player", "enemy") if player_first else ("enemy", "player")):
            if self.phase != "choose":
                break
            if who == "player":
                self._player(action, slot, item)
            else:
                self._enemy()
        if self.boss and self.phase == "choose":
            self._boss_shift()                      # the colour changes at the end of every round
        return True

    # ---- the Slime King -----------------------------------------------
    def _pick_boss_color(self):
        """A new colour at least BOSS_COLOR_MIN_DISTANCE away from the current one, so a change always matters."""
        best = None
        for _ in range(30):
            c = random_color(self.rng, self.extended)
            if colors.distance(c, self.enemy.color) >= C.BOSS_COLOR_MIN_DISTANCE:
                return c
            best = c
        return best

    def _boss_shift(self):
        self.enemy.color = self.next_color
        self.next_color = self._pick_boss_color()
        r, g, b = self.enemy.color
        self._emit(T.NOTE_BOSS_SHIFT.format(r=r, g=g, b=b), "whoosh", "note")

    def _cap(self, n):
        """Per-hit damage cap on the boss (design 6.4): it takes at least 1 / BOSS_DAMAGE_CAP hits to beat him."""
        return min(n, max(1, int(round(self.enemy.max_hp * C.BOSS_DAMAGE_CAP)))) if self.boss else n

    def _roll(self):
        return 1.0 + self.rng.uniform(-C.DAMAGE_RANDOM, C.DAMAGE_RANDOM)

    def _player(self, action, slot, item):
        e, s = self.enemy, self.stats
        if action == "tackle":
            self._emit(T.ACT_TACKLE, "whoosh", "act")
            m = self.tackle_multiplier()
            n = max(1, int(round(base_damage(C.TACKLE_FRACTION, s.atk, e.defense, e.max_hp) * m * self._roll())))
            n = self._cap(n)
            e.hp -= n
            self._emit(T.RES_ENEMY_DAMAGE.format(who=self.who, n=n, tag=_tag(m)), "impact", "result")
        elif action == "throw":
            name = self.name_of(item)
            self.inventory.take(slot, 1)
            self._emit(T.ACT_THROW.format(name=name), "whoosh", "act")
            m = self.throw_multiplier(item)
            value = base_damage(C.THROW_FRACTION, s.atk, e.defense, e.max_hp) * throw_value(m) * self._roll()
            if value >= 1:
                n = self._cap(int(round(value)))
                e.hp -= n
                self._emit(T.RES_ENEMY_DAMAGE.format(who=self.who, n=n, tag=_tag(m)), "impact", "result")
            elif value <= -1 and e.hp < e.max_hp:
                n = min(e.max_hp - e.hp, int(round(-value)))
                e.hp += n
                self._emit(T.RES_ENEMY_HEAL.format(who=self.who, n=n), "heal", "result")
            else:
                self._emit(T.RES_NO_EFFECT, None, "result")
        elif action == "eat":
            self.inventory.take(slot, 1)
            self._emit(T.ACT_EAT.format(name=self.name_of(item)), "eat", "act")
            delta = s.eat(items.rgb(items.code_of(item)))
            self._emit(T.RES_EAT.format(delta=delta), "heal" if delta > 0 else ("impact" if delta < 0 else None), "result")
        elif action == "flee":
            self._emit(T.ACT_FLEE, "whoosh", "act")
            lo, hi = C.FLEE_LIMITS
            p = max(lo, min(hi, C.FLEE_BASE + C.FLEE_PER_SPD * (s.spd - e.spd)))
            if self.rng.random() < p:
                self.phase = "fled"
                self._emit(T.RES_FLEE_OK, None, "result")
            else:
                self._emit(T.RES_FLEE_FAIL, None, "result")
        if self.phase == "choose" and e.hp <= 0:
            self._win()

    def _enemy(self):
        e, s = self.enemy, self.stats
        self._emit(T.ACT_ENEMY_TACKLE.format(who=self.who), "whoosh", "act")
        m = colors.matchup(e.color, s.color)
        n = max(1, int(round(base_damage(C.TACKLE_FRACTION, e.atk, s.defense, s.max_hp) * m * self._roll())))
        dead = s.take_damage(n)
        self._emit(T.RES_YOU_DAMAGE.format(n=n, tag=_tag(m)), "impact", "result")
        if dead:
            self.phase = "lost"
            self._emit(T.NOTE_LOSE, "lose", "note")

    def _win(self):
        self.phase = "won"
        self.xp_gained = progression.xp_reward(self.enemy.level, self.stats.level)
        if self.boss:
            self.xp_gained = int(round(self.xp_gained * C.BOSS_XP_MULT))
            self.boss_won = True
        self._emit(T.NOTE_WIN.format(who=self.who), "win", "note")
        self.level_ups = self.stats.add_xp(self.xp_gained, self.rng)
        self._emit(T.NOTE_XP.format(xp=self.xp_gained), None, "note")
        for up in self.level_ups:
            gains = ", ".join(f"{k.upper()} +{v}" for k, v in up.gains.items())
            self._emit(T.NOTE_LEVEL_UP.format(level=up.level, gains=gains), "levelup", "note")
