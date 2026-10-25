"""Item ids. Blocks keep their block ids (1..6). Minerals are 1000 + colour code. A colour has three levels (r, g, b),
each 0..9 meaning 40 + 20 * level (40..220), and code = r*100 + g*10 + b (1000 colours).
Before the boss falls only levels 1..8 (60..200) occur; the extra colours (a level 0 or 9 in any channel) appear after."""
import numpy as np

import blocks

MINERAL_BASE = 1000
LEVELS = 10
LOW = 40
STEP = 20
N_COLORS = LEVELS ** 3
BASE_LEVEL_RANGE = (1, 8)             # levels that exist before the boss (60..200)

STACK_BY_TIER = (32, 24, 16)          # common, uncommon, rare
HARDNESS_BY_TIER = (2.3, 3.0, 3.8)    # seconds to dig a rock that holds such a mineral


def is_mineral(item):
    return MINERAL_BASE <= item < MINERAL_BASE + N_COLORS


def item_of(code):
    return MINERAL_BASE + int(code)


def code_of(item):
    return int(item) - MINERAL_BASE


def levels(code):
    code = int(code)
    return (code // 100) % 10, (code // 10) % 10, code % 10


def code_from_levels(r, g, b):
    return r * 100 + g * 10 + b


def code_from_rgb(rgb):
    """Nearest mineral colour code for an RGB colour."""
    lv = [max(0, min(LEVELS - 1, int(round((c - LOW) / STEP)))) for c in rgb]
    return code_from_levels(*lv)


def rgb(code):
    return tuple(LOW + STEP * lv for lv in levels(code))


def in_base_range(code):
    lo, hi = BASE_LEVEL_RANGE
    return all(lo <= lv <= hi for lv in levels(code))


def tier(code):
    """0 common (muted colours), 1 uncommon, 2 rare (vivid colours): by spread between the channels."""
    lv = levels(code)
    spread = max(lv) - min(lv)
    return 0 if spread <= 2 else (1 if spread <= 4 else 2)


def mineral_hardness(code):
    return HARDNESS_BY_TIER[tier(code)]


def _pools():
    codes = np.arange(N_COLORS)
    r, g, b = (codes // 100) % 10, (codes // 10) % 10, codes % 10
    spread = np.maximum(np.maximum(r, g), b) - np.minimum(np.minimum(r, g), b)
    lo, hi = BASE_LEVEL_RANGE
    base = ((r >= lo) & (r <= hi) & (g >= lo) & (g <= hi) & (b >= lo) & (b <= hi))
    tiers = (spread <= 2, (spread > 2) & (spread <= 4), spread > 4)
    return (tuple(codes[base & t] for t in tiers), tuple(codes[~base & t] for t in tiers))


# Colour codes per rarity tier: the ones that exist from the start, and the ones that only exist after the boss.
TIER_CODES, NEW_TIER_CODES = _pools()


def is_valid_item(item):
    return (isinstance(item, int) and not isinstance(item, bool)
            and (is_mineral(item) or item in blocks.PLACEABLE))


def stack_limit(item):
    if is_mineral(item):
        return STACK_BY_TIER[tier(code_of(item))]
    return blocks.stack_limit(item)


def old_item_to_current(item):
    """Save format 1 packed three 3-bit levels (60..200) as r*64+g*8+b; convert such an item id to the current ids."""
    code = int(item) - MINERAL_BASE
    r, g, b = (code >> 6) & 7, (code >> 3) & 7, code & 7
    return item_of(code_from_levels(r + 1, g + 1, b + 1))
