"""Day and night (stage 5). Time is a number of seconds; one full day lasts C.DAY_LENGTH.
phase 0.0 = midnight, 0.25 = sunrise, 0.5 = noon, 0.75 = sunset. Pure functions."""
import math

import config as C


def phase(seconds):
    return (seconds / C.DAY_LENGTH) % 1.0


def start_seconds():
    return C.START_TIME * C.DAY_LENGTH


def _smoothstep(a, b, x):
    t = max(0.0, min(1.0, (x - a) / (b - a)))
    return t * t * (3.0 - 2.0 * t)


def _elevation(p):
    """Sun height: +1 at noon, -1 at midnight, 0 at sunrise and sunset."""
    return math.sin(2.0 * math.pi * (p - 0.25))


def daylight(seconds):
    """0 = full night, 1 = full day, with a short soft transition around sunrise and sunset."""
    return _smoothstep(-0.20, 0.20, _elevation(phase(seconds)))


def sky_color(seconds):
    """Sky (and distant fog) colour: dark blue at night, light blue by day, warm orange around sunrise/sunset."""
    d = daylight(seconds)
    e = _elevation(phase(seconds))
    warm = math.exp(-(e / 0.18) ** 2) * 0.55            # strongest exactly at sunrise / sunset
    base = [n + (dy - n) * d for n, dy in zip(C.SKY_NIGHT, C.SKY_DAY)]
    return tuple(min(1.0, b + (u - b) * warm) for b, u in zip(base, C.SKY_DUSK))


def world_tint(seconds, depth):
    """Colour multiplier for the whole world: a mild blue-dark tint at night, fading out underground."""
    d = daylight(seconds)
    deep = max(0.0, min(1.0, depth / C.FOG_FULL_DARK_DEPTH))
    out = []
    for n in C.NIGHT_WORLD_TINT:
        night_value = n + (1.0 - n) * d
        out.append(night_value + (1.0 - night_value) * deep)
    return tuple(out)


def encounter_multiplier(seconds, depth):
    """Encounter chance multiplier: up to NIGHT_ENCOUNTER_MULT in full darkness, but only near the surface."""
    if depth > C.NIGHT_UNDERGROUND_DEPTH:
        return 1.0
    return 1.0 + (C.NIGHT_ENCOUNTER_MULT - 1.0) * (1.0 - daylight(seconds))


def clock_text(seconds):
    minutes = int(phase(seconds) * 24 * 60)
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def is_night(seconds):
    return daylight(seconds) < 0.5


def wake_time(seconds):
    """Time after a night's sleep: the next morning (START_TIME of a day). During the day nothing changes."""
    if not is_night(seconds):
        return seconds
    day = int(seconds // C.DAY_LENGTH)
    morning = (day + (0 if phase(seconds) < C.START_TIME else 1)) * C.DAY_LENGTH + C.START_TIME * C.DAY_LENGTH
    return morning
