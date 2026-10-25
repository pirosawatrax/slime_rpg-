"""Where the boss lives (design 6.4: the deepest place). One fixed spot per seed, a few hundred blocks from the
origin: a room carved at the very bottom of the world with a single Wood tile in the middle. You dig down to it
(the guide in a village tells you where) and step on the tile to challenge the boss. Engine-free."""
import math
from functools import lru_cache

import config as C
from blocks import AIR, WOOD
from world.noise import hash2
from world.worldgen_heights import surface_heights

HALF = C.ARENA_HALF
HEIGHT = C.ARENA_HEIGHT


@lru_cache(maxsize=64)
def arena_center(seed):
    """(x, z) of the Wood tile. The first of a few hashed spots that lies on dry land."""
    lo, hi = C.BOSS_DISTANCE
    for k in range(32):
        angle = float(hash2(k * 7 + 1, 3, seed + 8101)) * 2 * math.pi
        dist = lo + float(hash2(k * 13 + 2, 5, seed + 8102)) * (hi - lo)
        x, z = int(round(math.cos(angle) * dist)), int(round(math.sin(angle) * dist))
        if int(surface_heights(seed, x, z)) >= C.SEA_LEVEL + 1:
            return x, z
    return int(hi), 0


def arena_at(seed, x, z):
    """True if this column is the challenge tile."""
    return (x, z) == arena_center(seed)


def arena_near_chunk(seed, cx, cz):
    """The arena centre if the room touches this chunk, else None."""
    ax, az = arena_center(seed)
    x0, z0 = cx * C.CHUNK_SIZE, cz * C.CHUNK_SIZE
    if x0 - HALF <= ax < x0 + C.CHUNK_SIZE + HALF and z0 - HALF <= az < z0 + C.CHUNK_SIZE + HALF:
        return ax, az
    return None


def structure_blocks():
    """{(dx, y, dz): block} relative to the tile, with absolute y. Interior air, the Wood tile in the floor,
    and four short Wood posts around it."""
    out = {}
    for dx in range(-HALF, HALF + 1):
        for dz in range(-HALF, HALF + 1):
            for y in range(1, HEIGHT + 1):
                out[(dx, y, dz)] = AIR
    out[(0, 0, 0)] = WOOD
    for sx in (-2, 2):
        for sz in (-2, 2):
            for y in (1, 2, 3):
                out[(sx, y, sz)] = WOOD
    return out
