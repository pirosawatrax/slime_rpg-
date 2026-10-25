"""Terrain generation for one chunk. Pure function of (seed, cx, cz): the same chunk always comes out the same."""
import numpy as np

import config as C
from blocks import AIR, SOIL, GRASS, ROCK, WOOD, LEAF, WATER
import items
from world.noise import value_noise2, value_noise3, hash2, hash3
from world.worldgen_heights import surface_heights
from world import boss_arena, villages

S = C.CHUNK_SIZE
H = C.WORLD_HEIGHT


def generate_chunk(seed, cx, cz, extended=False):
    """Blocks only (kept for callers that do not care about minerals)."""
    return generate_chunk_full(seed, cx, cz, extended)[0]


def generate_chunk_full(seed, cx, cz, extended=False):
    """Returns (blocks (16,64,16) uint8, minerals (16,64,16) uint16). minerals[x,y,z] is 0 for none, otherwise
    1 + colour code (see items.py). Only ROCK cells can hold a mineral. extended=True (the boss has fallen) turns
    some of the ore into the new post-boss colours; ore positions and the other colours stay as they were."""
    x0, z0 = cx * S, cz * S

    # Heights for the chunk plus a 2-block margin, so trees from neighbouring chunks can spill leaves in.
    ex = np.arange(x0 - 2, x0 + S + 2)
    ez = np.arange(z0 - 2, z0 + S + 2)
    ext_h = surface_heights(seed, ex[:, None], ez[None, :])
    h = ext_h[2:2 + S, 2:2 + S]                      # (16, 16)

    y = np.arange(H)[None, :, None]
    hh = h[:, None, :]
    blocks = np.zeros((S, H, S), dtype=np.uint8)

    blocks[(y <= hh) & np.ones((S, H, S), bool)] = ROCK
    soil_layer = (y <= hh) & (y > hh - 4)
    blocks[soil_layer] = SOIL
    top = (y == hh) & (hh >= C.SEA_LEVEL)
    blocks[top] = GRASS

    # Caves (Minecraft-like): winding tunnels, a finer network and big caverns; never the world floor.
    wx = (x0 + np.arange(S))[:, None, None]
    wy = np.arange(H)[None, :, None]
    wz = (z0 + np.arange(S))[None, None, :]
    entrance = _entrance_mask(seed, x0 + np.arange(S)[:, None], z0 + np.arange(S)[None, :], h)[:, None, :]
    blocks[_caves(seed, wx, wy, wz, hh, entrance)] = AIR

    # Water fills low columns up to sea level.
    water = (y > hh) & (y <= C.SEA_LEVEL)
    blocks[water & np.ones((S, H, S), bool)] = WATER

    blocks[:, 0, :] = ROCK                            # world floor

    arena = boss_arena.arena_near_chunk(seed, cx, cz)
    if arena is not None:
        _carve_arena(blocks, arena, x0, z0)
    near = villages.villages_near_chunk(seed, cx, cz, pad=C.VILLAGE_TREE_MARGIN)
    keep_clear = _village_clear_mask(near, x0, z0)       # no trees / boulders where a village will stand
    keep_clear |= _entrance_mask(seed, ex[:, None], ez[None, :], ext_h)    # ... nor over a cave entrance
    outcrop = _place_outcrops(blocks, seed, x0, z0, ext_h, keep_clear)
    _plant_trees(blocks, seed, x0, z0, ext_h, keep_clear)
    for v in near:
        _build_village(blocks, h, v, x0, z0)             # after trees: it clears and levels its own ground
    minerals = _place_minerals(blocks, seed, wx, wy, wz, hh, outcrop, extended)
    return blocks, minerals


def _plant_trees(blocks, seed, x0, z0, ext_h, keep_clear):
    ex = np.arange(x0 - 2, x0 + S + 2)
    ez = np.arange(z0 - 2, z0 + S + 2)
    chance = hash2(ex[:, None], ez[None, :], seed + 101)
    land = ext_h >= C.SEA_LEVEL + 1
    for i, j in np.argwhere((chance < C.TREE_CHANCE) & land & ~keep_clear):
        wx, wz = int(ex[i]), int(ez[j])
        ground = int(ext_h[i, j])
        trunk = 4 + int(hash2(wx, wz, seed + 202) * 3)
        top_y = ground + trunk
        if top_y + 2 >= H:
            continue
        lx, lz = wx - x0, wz - z0

        def put(px, py, pz, block, only_air):
            if 0 <= px < S and 0 <= pz < S and 0 <= py < H:
                if not only_air or blocks[px, py, pz] == AIR:
                    blocks[px, py, pz] = block

        # Crown: two wide layers, one narrow layer, one cap.
        for dy, r in ((-1, 2), (0, 2), (1, 1), (2, 1)):
            for dx in range(-r, r + 1):
                for dz in range(-r, r + 1):
                    if r == 2 and abs(dx) == 2 and abs(dz) == 2:
                        continue
                    put(lx + dx, top_y + dy, lz + dz, LEAF, True)
        for ty in range(ground + 1, top_y + 1):
            put(lx, ty, lz, WOOD, False)


def _entrance_mask(seed, xs, zs, heights):
    """Land columns where caves are allowed to break through to the surface (a sparse scatter of holes and chasms)."""
    thr, scale = C.CAVE_ENTRANCE
    return (value_noise2(xs, zs, scale, seed + 31) > thr) & (heights >= C.SEA_LEVEL + 1)


def _caves(seed, wx, wy, wz, hh, entrance):
    """Boolean mask of cells that become air. Tunnels are where TWO independent noise fields are both close to 0.5 (their
    intersection is a thin winding tube); a second, finer network and rare big caverns add variety."""
    yy = wy * C.CAVE_Y_SQUASH
    wa, sa = C.CAVE_TUNNEL
    wb, sb = C.CAVE_FINE
    thr, big_scale = C.CAVE_CAVERN
    tunnels = ((np.abs(value_noise3(wx, yy, wz, sa, seed + 11) - 0.5) < wa)
               & (np.abs(value_noise3(wx, yy, wz, sa, seed + 12) - 0.5) < wa))
    fine = ((np.abs(value_noise3(wx, yy, wz, sb, seed + 13) - 0.5) < wb)
            & (np.abs(value_noise3(wx, yy, wz, sb, seed + 14) - 0.5) < wb))
    caverns = value_noise3(wx, wy * 1.2, wz, big_scale, seed + 15) > thr
    limit = np.where(entrance, hh, hh - C.CAVE_SKIN)
    return (tunnels | fine | caverns) & (wy >= 3) & (wy <= limit)


def _place_outcrops(blocks, seed, x0, z0, ext_h, keep_clear):
    """Small surface boulders, so ore is visible from the surface and not only inside caves.
    Returns a bool mask of the cells that became outcrop rock."""
    mask = np.zeros(blocks.shape, dtype=bool)
    ex = np.arange(x0 - 2, x0 + S + 2)
    ez = np.arange(z0 - 2, z0 + S + 2)
    chance = hash2(ex[:, None], ez[None, :], seed + 303)
    land = ext_h >= C.SEA_LEVEL + 1
    for i, j in np.argwhere((chance < C.OUTCROP_CHANCE) & land & ~keep_clear):
        wx, wz = int(ex[i]), int(ez[j])
        ground = int(ext_h[i, j])
        r = 1 + int(hash2(wx, wz, seed + 404) * 2)            # radius 1 or 2
        for dy in range(0, r + 1):
            rad = r - dy
            for dx in range(-rad, rad + 1):
                for dz in range(-rad, rad + 1):
                    if dx * dx + dz * dz > rad * rad + (1 if rad else 0):
                        continue
                    px, py, pz = wx + dx - x0, ground + dy, wz + dz - z0
                    if 0 <= px < S and 0 <= pz < S and py < H and blocks[px, py, pz] in (AIR, GRASS, SOIL):
                        blocks[px, py, pz] = ROCK
                        mask[px, py, pz] = True
    return mask


def _pick_codes(u_tier, u_color, depth, pools=None):
    """Colour codes for cells: the deeper the cell, the rarer (more vivid) the colours that can appear."""
    pools = pools or items.TIER_CODES
    d1, d2 = C.TIER_DEPTHS
    tier = np.zeros(u_tier.shape, dtype=np.int64)
    mid = (depth >= d1) & (depth < d2)
    deep = depth >= d2
    tier[mid & (u_tier >= 0.60)] = 1
    tier[deep & (u_tier >= 0.40)] = 1
    tier[deep & (u_tier >= 0.75)] = 2
    codes = np.zeros(u_tier.shape, dtype=np.int64)
    for t, pool in enumerate(pools):
        sel = tier == t
        if sel.any():
            codes[sel] = pool[np.minimum((u_color[sel] * len(pool)).astype(np.int64), len(pool) - 1)]
    return codes


def _place_minerals(blocks, seed, wx, wy, wz, hh, outcrop, extended=False):
    rich = value_noise3(wx, wy, wz, 9.0, seed + 21) > C.MINERAL_RICH_THRESHOLD
    depth = np.maximum(hh - wy, 0)
    boost = 1.0 + C.MINERAL_DEPTH_BOOST * np.minimum(1.0, depth / C.DEPTH_BOOST_FULL)     # deeper = richer
    p = np.where(rich, C.MINERAL_RICH_P, C.MINERAL_BASE_P) * boost
    p = np.where(outcrop, C.OUTCROP_MINERAL_P, p)
    has = (blocks == ROCK) & (hash3(wx, wy, wz, seed + 22) < p) & (wy >= 2)
    depth = np.where(outcrop, np.maximum(depth, C.OUTCROP_DEPTH), depth)
    u_tier, u_color = hash3(wx, wy, wz, seed + 23), hash3(wx, wy, wz, seed + 24)
    codes = _pick_codes(u_tier, u_color, depth)
    if extended:                                      # post-boss: part of the ore turns into the new colours
        fancy = hash3(wx, wy, wz, seed + 25) < C.NEW_COLOR_SHARE
        codes = np.where(fancy, _pick_codes(u_tier, u_color, depth, items.NEW_TIER_CODES), codes)
    return np.where(has, codes + 1, 0).astype(np.uint16)


def _village_clear_mask(near, x0, z0):
    """(20, 20) mask over the chunk plus its 2-block margin: columns too close to a village for trees or boulders."""
    mask = np.zeros((S + 4, S + 4), dtype=bool)
    reach = C.VILLAGE_HALF + C.VILLAGE_TREE_MARGIN
    for v in near:
        xs = np.abs(np.arange(x0 - 2, x0 + S + 2) - v.x) <= reach
        zs = np.abs(np.arange(z0 - 2, z0 + S + 2) - v.z) <= reach
        mask |= xs[:, None] & zs[None, :]
    return mask


def _build_village(blocks, h, v, x0, z0):
    """Level a small patch, put ONE Wood tile in its middle and raise the signpost. Only the part inside this chunk is
    written, so a village on a chunk border comes out identical whichever chunk is generated first."""
    ph = v.ground
    half = C.VILLAGE_HALF
    for lx in range(S):
        if abs(x0 + lx - v.x) > half:
            continue
        for lz in range(S):
            if abs(z0 + lz - v.z) > half:
                continue
            col = blocks[lx, :, lz]
            top = int(h[lx, lz])
            col[ph + 1:min(H, ph + 12)] = AIR            # cut hills, trees and anything else above the patch
            lo = max(0, ph - 3)
            col[lo:ph] = SOIL
            if top < lo - 1:
                col[top + 1:lo] = SOIL                   # fill valleys and any water below
            col[ph] = WOOD if (x0 + lx, z0 + lz) == (v.x, v.z) else GRASS
    for (dx, dy, dz), block in villages.structure_blocks(v).items():
        px, py, pz = v.x + dx - x0, ph + dy, v.z + dz - z0
        if 0 <= px < S and 0 <= pz < S and 0 <= py < H:
            blocks[px, py, pz] = block


def _carve_arena(blocks, arena, x0, z0):
    """The boss lair at the bottom of the world (clipped to this chunk, so it is identical from every chunk)."""
    ax, az = arena
    for (dx, y, dz), block in boss_arena.structure_blocks().items():
        px, pz = ax + dx - x0, az + dz - z0
        if 0 <= px < S and 0 <= pz < S:
            blocks[px, y, pz] = block
