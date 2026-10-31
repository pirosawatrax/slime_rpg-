"""Where a new game starts: the nearest open patch of grass to the world origin."""
import numpy as np

import config as C
from blocks import GRASS, id_for_key
from world.worldgen_heights import surface_heights


def _ring(r):
    if r == 0:
        return [(0, 0)]
    return ([(x, z) for x in (-r, r) for z in range(-r, r + 1)] + [(x, z) for z in (-r, r) for x in range(-r + 1, r)])


def find_spawn(world, max_radius=400):
    """(x, y, z) just above the grass nearest to the origin where a slime fits: two free cells above, not a tree, a
    hole or a village. Terrain height decides which columns are worth looking at, so no chunks are made for nothing."""
    snow = id_for_key("snow_biome:snow")
    spawn_blocks = (GRASS, snow) if snow is not None else (GRASS,)
    for r in range(max_radius + 1):
        ring = _ring(r)
        pts = np.array(ring)
        heights = surface_heights(world.seed, pts[:, 0], pts[:, 1])
        for (x, z), h in zip(ring, heights):
            if h < C.SEA_LEVEL + 1:
                continue
            y = world.surface_y(x, z)
            if y >= C.SEA_LEVEL and world.get_block(x, y, z) in spawn_blocks and not world.is_blocking(x, y + 1, z) \
                    and not world.is_blocking(x, y + 2, z):
                return x + 0.5, y + 1.01, z + 0.5
    return 0.5, C.TERRAIN_BASE + 6.0, 0.5
