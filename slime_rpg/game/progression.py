"""Levels, experience and enemy strength (design sections 3, 6.3). Pure functions."""
import math

import config as C

STATS = ("hp", "atk", "def", "spd")


def mean_growth():
    """Average stat gain per level-up with the configured random growth."""
    pts = sum(C.GROWTH_POINTS) / 2.0
    total = sum(C.GROWTH_WEIGHTS.values())
    return {s: pts * C.GROWTH_WEIGHTS[s] / total * C.GROWTH_PER_POINT[s] for s in STATS}


def average_stats(level):
    """What a typical level-`level` slime has. Enemies use it; a player who levels up gets about the same."""
    g = mean_growth()
    return {s: int(round(C.START_STATS[s] + (level - 1) * g[s])) for s in STATS}


def xp_needed(level):
    return int(C.XP_NEED * level * level)


def xp_reward(enemy_level, player_level):
    lo, hi = C.XP_RATIO_RANGE
    ratio = max(lo, min(hi, enemy_level / max(1, player_level)))
    return max(1, int(round(C.XP_BASE * enemy_level * ratio)))


def enemy_level_cap(boss_defeated=False):
    """Highest level an ordinary enemy can have. After the boss falls the cap is lifted (design 6.3)."""
    return None if boss_defeated else max(1, int(C.BOSS_LEVEL * C.ENEMY_CAP_FRACTION))


def enemy_level(depth, distance, rng, boss_defeated=False):
    """Depth below the surface is the main driver; horizontal distance adds a little, saturating."""
    raw = (1.0 + max(0.0, depth) * C.LEVEL_PER_DEPTH
           + C.DISTANCE_LEVEL_MAX * (1.0 - math.exp(-max(0.0, distance) / C.DISTANCE_SCALE)))
    level = int(round(raw + rng.uniform(-1.0, 1.0)))
    cap = enemy_level_cap(boss_defeated)
    return max(1, level if cap is None else min(level, cap))
