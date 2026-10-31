"""Terrain generation for one chunk. Pure function of (seed, cx, cz): the same chunk always comes out the same."""
import numpy as np

import config as C
from blocks import AIR, SOIL, GRASS, ROCK, WOOD, LEAF, WATER, id_for_key
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

    # Arid regions get a shallow, mineable sandstone layer before caves/structures are finalized.
    _apply_sandstone_biomes(blocks, seed, x0, z0, h)

    blocks[:, 0, :] = ROCK                            # world floor

    arena = boss_arena.arena_near_chunk(seed, cx, cz)
    _apply_common_rock_formations(blocks, seed, x0, z0, h, arena)
    if arena is not None:
        _carve_arena(blocks, arena, x0, z0)
    near = villages.villages_near_chunk(seed, cx, cz, pad=C.VILLAGE_TREE_MARGIN)
    keep_clear = _village_clear_mask(near, x0, z0)       # no trees / boulders where a village will stand
    keep_clear |= _entrance_mask(seed, ex[:, None], ez[None, :], ext_h)    # ... nor over a cave entrance
    outcrop = _place_outcrops(blocks, seed, x0, z0, ext_h, keep_clear)
    _place_common_rock_outcrops(blocks, seed, x0, z0, ext_h, keep_clear)
    _plant_trees(blocks, seed, x0, z0, ext_h, keep_clear)
    for v in near:
        _build_village(blocks, h, v, x0, z0)             # after trees: it clears and levels its own ground
    _apply_snow_biome(blocks, seed, x0, z0, h, near)
    minerals = _place_minerals(blocks, seed, wx, wy, wz, hh, outcrop, extended)
    return blocks, minerals


def _mod_id(key):
    """Return a registered MOD block ID, or None when its pack is disabled/missing."""
    return id_for_key(key)


def _apply_sandstone_biomes(blocks, seed, x0, z0, heights):
    """Replace the upper four solid layers in dry regions with deterministic sandstone variants."""
    yellow = _mod_id("sandstone_colors:yellow_sandstone")
    red = _mod_id("sandstone_colors:red_sandstone")
    white = _mod_id("sandstone_colors:white_sandstone")
    gray = _mod_id("sandstone_colors:gray_sandstone")
    if None in (yellow, red, white, gray):
        return
    xs = x0 + np.arange(S)[:, None]
    zs = z0 + np.arange(S)[None, :]
    dryness = value_noise2(xs, zs, 92.0, seed + 501)
    palette = value_noise2(xs, zs, 37.0, seed + 502)
    # Keep the starting area temperate so a new player always finds the familiar grass surface nearby.
    desert = (dryness > 0.64) & (heights >= C.SEA_LEVEL + 1) & ((np.abs(xs) + np.abs(zs)) > 60)
    # Large desert regions have a dominant yellow base; smaller geological patches vary the colour.
    surface_id = np.where(palette < 0.20, red,
                 np.where(palette < 0.42, white,
                 np.where(palette > 0.84, gray, yellow)))
    for depth in range(4):
        yy = heights - depth
        valid = desert & (yy > 0)
        for block_id in (yellow, red, white, gray):
            cols = valid & (surface_id == block_id)
            if cols.any():
                ix, iz = np.where(cols)
                iy = yy[cols]
                solid = (blocks[ix, iy, iz] != AIR) & (blocks[ix, iy, iz] != WATER)
                blocks[ix[solid], iy[solid], iz[solid]] = block_id



def _apply_snow_biome(blocks, seed, x0, z0, heights, nearby_villages):
    """Turn cold-climate surface grass into snow and the top of lakes into solid ice.

    The climate field is the same deterministic temperature field used by tree species,
    so snowy regions blend naturally into the existing forests rather than forming a
    separate map. Underground terrain and mineral generation are left untouched.
    """
    snow = _mod_id("snow_biome:snow")
    ice = _mod_id("snow_biome:ice")
    if snow is None or ice is None:
        return

    xs = x0 + np.arange(S)[:, None]
    zs = z0 + np.arange(S)[None, :]
    temperature = value_noise2(xs, zs, 115.0, seed + 511)
    cold = temperature < 0.34
    land = heights >= C.SEA_LEVEL

    # Leave village plots clear so paths, floors and buildings keep their intended palette.
    if nearby_villages:
        village_clear = _village_clear_mask(nearby_villages, x0, z0)[2:S + 2, 2:S + 2]
        cold &= ~village_clear

    # A snow block replaces only the exposed grass surface. The ground height stays the
    # same, so spawn positions, caves and the terrain silhouette do not shift.
    top = heights.astype(np.int64)
    ix, iz = np.where(cold & land)
    for lx, lz in zip(ix, iz):
        y = int(top[lx, lz])
        if 0 <= y < H and blocks[lx, y, lz] == GRASS:
            blocks[lx, y, lz] = snow

    # Lakes retain their water below; only the exposed water surface becomes walkable ice.
    frozen = cold & ~land & (blocks[:, C.SEA_LEVEL, :] == WATER)
    blocks[:, C.SEA_LEVEL, :][frozen] = ice

def _apply_common_rock_formations(blocks, seed, x0, z0, heights, arena=None):
    """Replace ordinary underground rock with broad, deterministic mineral-free formations."""
    granite = _mod_id("common_rocks:granite")
    basalt = _mod_id("common_rocks:basalt")
    limestone = _mod_id("common_rocks:limestone")
    red_rock = _mod_id("common_rocks:red_rock")
    if None in (granite, basalt, limestone, red_rock):
        return

    xs = x0 + np.arange(S)[:, None]
    zs = z0 + np.arange(S)[None, :]
    # Keep ordinary ROCK as the dominant underground material because only
    # that block type can host mineral deposits. Geological variants should
    # be occasional, compact patches rather than vast regions that suppress
    # ore discovery. A high threshold limits coverage to roughly 10-15% of
    # land columns; the smaller scale makes the patches less continent-sized.
    formation = value_noise2(xs, zs, 20.0, seed + 601) > 0.80
    if arena is not None:
        ax, az = arena
        arena_margin = C.ARENA_HALF + 2
        formation &= ~((np.abs(xs - ax) <= arena_margin) & (np.abs(zs - az) <= arena_margin))
    palette = value_noise2(xs, zs, 18.0, seed + 602)
    y = np.arange(H)[None, :, None]
    deep_solid = (blocks == ROCK) & (y > 1) & (y <= heights[:, None, :] - 4)
    replace = deep_solid & formation[:, None, :]

    for block_id, region in (
        (granite, palette < 0.25),
        (basalt, (palette >= 0.25) & (palette < 0.50)),
        (limestone, (palette >= 0.50) & (palette < 0.75)),
        (red_rock, palette >= 0.75),
    ):
        mask = replace & region[:, None, :]
        blocks[mask] = block_id


def _place_common_rock_outcrops(blocks, seed, x0, z0, ext_h, keep_clear):
    """Expose small mineral-free geological boulders on the surface.

    Underground formations are the main source, but surface outcrops make the
    four rock families discoverable without having to dig first. Candidate
    positions and rock type depend only on world coordinates and seed, so
    adjacent chunks agree at their borders.
    """
    names = ("granite", "basalt", "limestone", "red_rock")
    ids = [_mod_id(f"common_rocks:{name}") for name in names]
    if any(block_id is None for block_id in ids):
        return

    ex = np.arange(x0 - 2, x0 + S + 2)
    ez = np.arange(z0 - 2, z0 + S + 2)
    xx, zz = ex[:, None], ez[None, :]
    chance = hash2(xx, zz, seed + 701)
    palette = value_noise2(xx, zz, 25.0, seed + 702)
    land = ext_h >= C.SEA_LEVEL + 1
    # Surface boulders are rare landmarks, not continuous fields.
    candidates = (chance < 0.0018) & land & ~keep_clear

    for i, j in np.argwhere(candidates):
        wx, wz = int(ex[i]), int(ez[j])
        ground = int(ext_h[i, j])
        rock_index = min(3, int(float(palette[i, j]) * 4))
        block_id = ids[rock_index]
        roll = hash2(wx, wz, seed + 703)
        radius = 1 if roll < 0.55 else 2
        height = 1 if roll < 0.72 else 2
        for dy in range(height + 1):
            rad = max(0, radius - (1 if dy == height and height > 1 else 0))
            for dx in range(-rad, rad + 1):
                for dz in range(-rad, rad + 1):
                    if dx * dx + dz * dz > rad * rad + (1 if rad else 0):
                        continue
                    px, py, pz = wx + dx - x0, ground + dy, wz + dz - z0
                    if (0 <= px < S and 0 <= pz < S and 0 < py < H
                            and blocks[px, py, pz] in (AIR, GRASS, SOIL)):
                        blocks[px, py, pz] = block_id


def _plant_trees(blocks, seed, x0, z0, ext_h, keep_clear):
    """Plant biome-specific MOD trees. Candidate coordinates and species are seed-stable across chunk borders."""
    ex = np.arange(x0 - 2, x0 + S + 2)
    ez = np.arange(z0 - 2, z0 + S + 2)
    xx, zz = ex[:, None], ez[None, :]
    chance = hash2(xx, zz, seed + 101)
    land = ext_h >= C.SEA_LEVEL + 1

    birch_log = _mod_id("tree_species:birch_log")
    birch_leaf = _mod_id("tree_species:birch_leaves")
    pine_log = _mod_id("tree_species:pine_log")
    pine_leaf = _mod_id("tree_species:pine_leaves")
    dark_log = _mod_id("tree_species:darkwood_log")
    dark_leaf = _mod_id("tree_species:darkwood_leaves")
    have_species = all(v is not None for v in (birch_log, birch_leaf, pine_log, pine_leaf, dark_log, dark_leaf))

    # Broad climate fields create contiguous forests rather than random individual tree colours.
    temperature = value_noise2(xx, zz, 115.0, seed + 511)
    moisture = value_noise2(xx, zz, 78.0, seed + 512)
    forest = moisture > 0.43
    desert = value_noise2(xx, zz, 92.0, seed + 501) > 0.64
    candidates = (chance < C.TREE_CHANCE) & land & ~keep_clear

    for i, j in np.argwhere(candidates):
        wx, wz = int(ex[i]), int(ez[j])
        ground = int(ext_h[i, j])
        if have_species and forest[i, j] and not desert[i, j]:
            temp = temperature[i, j]
            wet = moisture[i, j]
            if temp < 0.38:
                species = (pine_log, pine_leaf, "pine")
            elif wet > 0.72:
                species = (dark_log, dark_leaf, "darkwood")
            else:
                species = (birch_log, birch_leaf, "birch")
        else:
            species = (WOOD, LEAF, "normal")
        log_block, leaf_block, kind = species

        roll = hash2(wx, wz, seed + 202)
        if kind == "pine":
            trunk = 6 + int(roll * 4)
        elif kind == "darkwood":
            trunk = 5 + int(roll * 3)
        else:
            trunk = 4 + int(roll * 3)
        top_y = ground + trunk
        crown = 3 if kind == "pine" else (2 if kind == "darkwood" else 1)
        if top_y + crown >= H:
            continue
        lx, lz = wx - x0, wz - z0

        def put(px, py, pz, block, only_air):
            if 0 <= px < S and 0 <= pz < S and 0 <= py < H:
                if not only_air or blocks[px, py, pz] == AIR:
                    blocks[px, py, pz] = block

        if kind == "pine":
            # Tall conical crown, one layer wider every two levels toward the bottom.
            for dy in range(-3, 4):
                radius = min(2, max(1, (3 - dy) // 2)) if dy <= 1 else 1
                for dx in range(-radius, radius + 1):
                    for dz in range(-radius, radius + 1):
                        if abs(dx) + abs(dz) <= radius + 1:
                            put(lx + dx, top_y + dy, lz + dz, leaf_block, True)
        elif kind == "darkwood":
            # Broad, rounded canopy with a sturdy trunk.
            for dy, radius in ((-1, 2), (0, 2), (1, 2), (2, 1)):
                for dx in range(-radius, radius + 1):
                    for dz in range(-radius, radius + 1):
                        if dx * dx + dz * dz <= radius * radius + 2:
                            put(lx + dx, top_y + dy, lz + dz, leaf_block, True)
        else:
            # Birch has a compact, slightly taller crown; normal trees keep the original shape.
            layers = ((-1, 2), (0, 2), (1, 1), (2, 1)) if kind == "normal" else ((-1, 2), (0, 2), (1, 1))
            for dy, radius in layers:
                for dx in range(-radius, radius + 1):
                    for dz in range(-radius, radius + 1):
                        if radius != 2 or abs(dx) != 2 or abs(dz) != 2:
                            put(lx + dx, top_y + dy, lz + dz, leaf_block, True)
        for ty in range(ground + 1, top_y + 1):
            put(lx, ty, lz, log_block, False)


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
