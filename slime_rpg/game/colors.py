"""Colour maths for the RGB system (design section 4). Channels are 0..255."""
import colorsys
import math

import config as C

_MAX_SAT = (C.BASE_COLOR_RANGE[1] - C.BASE_COLOR_RANGE[0]) / C.BASE_COLOR_RANGE[1]      # 0.7: the most vivid colour before the boss


def hsv(rgb):
    """(hue degrees 0..360, saturation 0..1, value 0..1)."""
    h, s, v = colorsys.rgb_to_hsv(rgb[0] / 255.0, rgb[1] / 255.0, rgb[2] / 255.0)
    return h * 360.0, s, v


def normalized_saturation(rgb):
    """Saturation scaled so the most vivid colour that can exist (60..200 range) is 1.0."""
    return min(1.0, hsv(rgb)[1] / _MAX_SAT)


def distance(a, b):
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


MAX_DISTANCE = distance((C.BASE_COLOR_RANGE[0],) * 3, (C.BASE_COLOR_RANGE[1],) * 3)   # ~242.5 (post-boss colours go further: capped)


def matchup(attacker, defender, k=C.MATCHUP_K):
    """Damage multiplier for attacker colour vs defender colour: 1 + k * sin(hue difference) * saturation factor.
    Three-way cycle: ~+120 degrees ahead wins, ~120 behind loses; same colour, opposite colour and greys are neutral.
    The result is mirrored when roles swap, so a good colour attacks well AND defends well."""
    d = math.radians(hsv(attacker)[0] - hsv(defender)[0])
    sat = math.sqrt(normalized_saturation(attacker) * normalized_saturation(defender))
    return 1.0 + k * math.sin(d) * sat
