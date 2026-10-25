"""Terrain height as a pure function of world position (shared by terrain generation and village placement)."""
import numpy as np

import config as C
from world.noise import value_noise2


def surface_heights(seed, x, z):
    """Integer height of the top solid block for world columns (x, z)."""
    a, b, c = C.TERRAIN_SCALES
    n = (value_noise2(x, z, a, seed) * 1.0
         + value_noise2(x, z, b, seed + 1) * 0.5
         + value_noise2(x, z, c, seed + 2) * 0.25) / 1.75
    return np.rint(C.TERRAIN_BASE + (n - 0.5) * 2.0 * C.TERRAIN_AMP).astype(np.int64)
