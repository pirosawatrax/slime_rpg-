"""What eating a mineral does (design 5.2): close colours heal, distant colours hurt, and the slime's colour
moves a fixed fraction toward the mineral."""
import config as C
from game import colors


def eat_effect(player_rgb, mineral_rgb, max_hp):
    """Returns (hp_delta, new_player_rgb)."""
    d = colors.distance(player_rgb, mineral_rgb)
    if d <= C.EAT_SAFE_DISTANCE:
        delta = round(max_hp * C.EAT_HEAL_MAX * (1.0 - d / C.EAT_SAFE_DISTANCE))
    else:
        span = max(1e-9, colors.MAX_DISTANCE - C.EAT_SAFE_DISTANCE)
        delta = -round(max_hp * C.EAT_HURT_MAX * min(1.0, (d - C.EAT_SAFE_DISTANCE) / span))
    mix = C.EAT_COLOR_MIX
    new = tuple(p + (m - p) * mix for p, m in zip(player_rgb, mineral_rgb))
    return int(delta), new
