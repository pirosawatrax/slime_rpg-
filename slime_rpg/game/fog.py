"""Fog and darkness follow how deep the player is below the surface (design 10.1). Pure maths."""
import config as C


def _lerp(a, b, t):
    return a + (b - a) * t


def fog_for_depth(depth, sky=None):
    """depth = blocks below the open-sky surface (<= 0 means at or above it). `sky` is the current sky colour
    (day/night); the fog fades from it to the dark underground colour. Returns (rgb, near, far)."""
    t = max(0.0, min(1.0, depth / C.FOG_FULL_DARK_DEPTH))
    rgb = tuple(_lerp(a, b, t) for a, b in zip(sky or C.FOG_COLOR_SURFACE, C.FOG_COLOR_DEEP))
    near = _lerp(C.FOG_SURFACE[0], C.FOG_DEEP[0], t)
    far = _lerp(C.FOG_SURFACE[1], C.FOG_DEEP[1], t)
    return rgb, near, far
