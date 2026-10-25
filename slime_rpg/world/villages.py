"""Village placement and layout. Pure functions of the seed: the world is cut into square regions and each region hashes
to "no village" or one village at a fixed spot, so every chunk can find out about villages that touch it without any
stored state. A village is just a small levelled patch with ONE Wood tile in the middle and a signpost beside it;
stepping onto the tile opens the village commands. Everything here is engine-free."""
import math
from dataclasses import dataclass
from functools import lru_cache

import numpy as np

import config as C
from blocks import WATER
from world.noise import hash2
from world.worldgen_heights import surface_heights

R = C.VILLAGE_REGION
HALF = C.VILLAGE_HALF
_MARGIN = HALF + 14                         # keeps neighbouring villages apart and inside their own region


@dataclass(frozen=True)
class Village:
    rx: int
    rz: int
    x: int          # the Wood tile
    z: int
    ground: int     # Y of the tile (the top block of the levelled patch)

    @property
    def id(self):
        return f"{self.rx},{self.rz}"

    @property
    def stand(self):
        """Where a player who wakes up here (inn respawn) is put: on the tile."""
        return (self.x + 0.5, self.ground + 1.01, self.z + 0.5)


def _suitable(seed, x, z):
    """Land all around and gentle ground: the patch is levelled, so cliffs would look odd."""
    ring = HALF + 3
    xs = np.array([x, x - ring, x, x + ring, x - ring, x + ring, x - ring, x + ring, x])
    zs = np.array([z, z - ring, z - ring, z - ring, z, z, z + ring, z + ring, z + ring])
    h = surface_heights(seed, xs, zs)
    return bool((h >= C.SEA_LEVEL + 1).all() and h.max() - h.min() <= 4)


@lru_cache(maxsize=8192)
def village_in_region(seed, rx, rz):
    if float(hash2(rx, rz, seed + 7000)) >= C.VILLAGE_CHANCE:
        return None
    for k in range(8):                                   # a few candidate spots; the first suitable one wins
        x = rx * R + _MARGIN + int(float(hash2(rx * 37 + k, rz * 91 + 5, seed + 7101)) * (R - 2 * _MARGIN))
        z = rz * R + _MARGIN + int(float(hash2(rx * 53 + k * 7, rz * 29 + 11, seed + 7102)) * (R - 2 * _MARGIN))
        if _suitable(seed, x, z):
            return Village(rx, rz, x, z, int(surface_heights(seed, x, z)))
    return None


def village_at(seed, x, z):
    """The village whose Wood tile is exactly this column, or None."""
    v = village_in_region(seed, x // R, z // R)
    return v if v is not None and v.x == x and v.z == z else None


def villages_near_chunk(seed, cx, cz, pad):
    """Villages whose patch (plus `pad` blocks) touches the chunk."""
    x0, z0 = cx * C.CHUNK_SIZE, cz * C.CHUNK_SIZE
    reach = pad + HALF + 1
    found = []
    for rx in range((x0 - reach) // R, (x0 + C.CHUNK_SIZE + reach) // R + 1):
        for rz in range((z0 - reach) // R, (z0 + C.CHUNK_SIZE + reach) // R + 1):
            v = village_in_region(seed, rx, rz)
            if v is not None and x0 - reach <= v.x < x0 + C.CHUNK_SIZE + reach and z0 - reach <= v.z < z0 + C.CHUNK_SIZE + reach:
                found.append(v)
    return found


def nearest_village(seed, x, z, reach=2):
    """(Village, distance) of the closest village in the regions around (x, z), or None if there is none in range."""
    best = None
    rx0, rz0 = int(x) // R, int(z) // R
    for rx in range(rx0 - reach, rx0 + reach + 1):
        for rz in range(rz0 - reach, rz0 + reach + 1):
            v = village_in_region(seed, rx, rz)
            if v is not None:
                d = math.hypot(v.x - x, v.z - z)
                if best is None or d < best[1]:
                    best = (v, d)
    return best


def structure_blocks(v):
    """Everything built ABOVE the levelled patch, as {(dx, dy, dz): block} (dy up from the ground).
    One signpost at the north edge: a post, a crossbar and a tip, all made of WATER blocks. Water cannot be dug out, so the
    sign cannot be destroyed, and its blue cannot be mistaken for a tree. Nothing you can walk into."""
    out = {}
    for dy in range(1, 5):
        out[(0, dy, HALF)] = WATER
    for dx in range(-HALF, HALF + 1):
        out[(dx, 5, HALF)] = WATER
    out[(0, 6, HALF)] = WATER
    return out


_DIRS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")


def direction_name(dx, dz):
    """Compass name for an offset: +z is north, +x is east (the way the player faces at yaw 0 is north)."""
    if dx == 0 and dz == 0:
        return "-"
    return _DIRS[int(round(math.degrees(math.atan2(dx, dz)) / 45.0)) % 8]
