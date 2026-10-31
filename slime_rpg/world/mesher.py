"""Turns a 16x16x16 section of blocks into vertex arrays (numpy only, no engine imports).
Hidden faces are culled. Vertex positions are relative to the chunk origin (x, z), absolute in y."""
import numpy as np

import config as C
import items
from blocks import AIR, WATER, ROCK, FLOWER, BLOCKS

S = C.CHUNK_SIZE
SH = C.SECTION_HEIGHT

# (neighbour offset, quad corners, shade, colour slot 0=top 1=side 2=bottom)
_FACES = [
    ((1, 0, 0),  [(1, 0, 0), (1, 1, 0), (1, 1, 1), (1, 0, 1)], 0.80, 1),
    ((-1, 0, 0), [(0, 0, 1), (0, 1, 1), (0, 1, 0), (0, 0, 0)], 0.80, 1),
    ((0, 1, 0),  [(0, 1, 0), (0, 1, 1), (1, 1, 1), (1, 1, 0)], 1.00, 0),
    ((0, -1, 0), [(0, 0, 1), (0, 0, 0), (1, 0, 0), (1, 0, 1)], 0.50, 2),
    ((0, 0, 1),  [(1, 0, 1), (1, 1, 1), (0, 1, 1), (0, 0, 1)], 0.65, 1),
    ((0, 0, -1), [(0, 0, 0), (0, 1, 0), (1, 1, 0), (1, 0, 0)], 0.65, 1),
]

_COLOR_TABLE = np.zeros((256, 3, 3), dtype=np.float32)
for _id, _info in BLOCKS.items():
    _COLOR_TABLE[_id, 0] = _info.top
    _COLOR_TABLE[_id, 1] = _info.side
    _COLOR_TABLE[_id, 2] = _info.bottom

_QUAD_TRIS = np.array([0, 1, 2, 0, 2, 3], dtype=np.int32)

# Ore blocks: each visible face is cut into 3x3 cells; some cells show the mineral colour, the rest dark rock.
_SUB_UV = np.array([[(i / 3, j / 3), ((i + 1) / 3, j / 3), ((i + 1) / 3, (j + 1) / 3), (i / 3, (j + 1) / 3)]
                    for i in range(3) for j in range(3)], dtype=np.float32)            # (9 cells, 4 corners, 2)
_rng = np.random.default_rng(3)
_PATTERNS = np.zeros((8, 9), dtype=bool)
for _p in _PATTERNS:
    _p[_rng.choice(9, size=C.ORE_CELLS, replace=False)] = True                           # ORE_CELLS of 9 cells coloured
_ROCK_DARK = np.array(BLOCKS[ROCK].side, dtype=np.float32) * C.ORE_ROCK_CELL_SHADE

# Simple sedimentary strata for sandstone: alternating broad bands and thin seams.
# The ranges run from the bottom to the top of each vertical side face.
_SANDSTONE_BANDS = (
    (0.00, 0.20, 0.94),
    (0.20, 0.25, 0.66),
    (0.25, 0.48, 1.04),
    (0.48, 0.53, 0.76),
    (0.53, 0.78, 0.96),
    (0.78, 0.83, 0.68),
    (0.83, 1.00, 1.03),
)


def _ore_display_colors(codes):
    """Mineral colours as drawn: the true colour pushed toward full brightness (ORE_GLOW) so ore stands out at range."""
    lv = np.stack([(codes // 100) % 10, (codes // 10) % 10, codes % 10], axis=1).astype(np.float32)
    true = (items.LOW + items.STEP * lv) / 255.0
    bright = true / true.max(axis=1, keepdims=True) * 0.95
    return (1.0 - C.ORE_GLOW) * true + C.ORE_GLOW * bright


def mesh_section(padded, sy, minerals=None, plants=None, world_time=0.0):
    """Return (vertices (N,3) f32, triangle indices (M,) i32, colours (N,4) f32) or None if nothing is visible.
    minerals: the chunk's (16, 64, 16) uint16 mineral array (0 = none, else 1 + colour code), or None."""
    y0 = sy * SH
    cur = padded[1:S + 1, y0 + 1:y0 + SH + 1, 1:S + 1]
    if not cur.any():
        return None
    ms = minerals[:, y0:y0 + SH, :] if minerals is not None else None
    plant_colors = np.zeros(cur.shape, dtype=np.int16)
    if plants:
        for (lx, py, lz), value in plants.items():
            if y0 <= py < y0 + SH:
                plant_colors[lx, py - y0, lz] = int(value[0]) + 1
    ore = (cur == ROCK) & (ms > 0) if ms is not None else np.zeros(cur.shape, dtype=bool)

    verts, tris, cols = [], [], []
    base_index = 0
    for face_index, ((dx, dy, dz), corners, shade, slot) in enumerate(_FACES):
        nb = padded[1 + dx:S + 1 + dx, y0 + 1 + dy:y0 + SH + 1 + dy, 1 + dz:S + 1 + dz]
        open_side = (nb == AIR) | (nb == WATER)
        if ore.any():
            ox, oy, oz = np.nonzero(ore & open_side)
            if len(ox):
                base_index = _add_ore_faces(verts, tris, cols, base_index, ms, ox, oy, oz, y0, corners, shade, face_index)
        visible = (((cur != AIR) & (cur != WATER) & (cur != FLOWER) & open_side & ~ore)
                   | ((cur == WATER) & (nb == AIR)))
        ix, iy, iz = np.nonzero(visible)
        n = len(ix)
        if n == 0:
            continue
        ids = cur[visible]
        pos = np.stack([ix, iy + y0, iz], axis=1).astype(np.float32)           # (n, 3)
        quad = pos[:, None, :] + np.array(corners, dtype=np.float32)[None]     # (n, 4, 3)
        # Sandstone side faces are split into horizontal strata so they cannot be
        # mistaken for the smooth vertical grain of tree trunks.
        parity = ((ix + iy + iz) & 1).astype(np.float32) * 0.06 + 0.94         # subtle checker for depth cues
        is_sandstone = np.fromiter(
            ("sandstone" in BLOCKS.get(int(bid), BLOCKS[ROCK]).key for bid in ids),
            dtype=bool, count=n)
        if slot == 1 and is_sandstone.any():
            plain = ~is_sandstone
            if plain.any():
                plain_pos, plain_ids, plain_parity = pos[plain], ids[plain], parity[plain]
                verts.append((plain_pos[:, None, :] + np.array(corners, dtype=np.float32)[None]).reshape(-1, 3))
                count = len(plain_pos)
                tris.append((np.arange(count, dtype=np.int32)[:, None] * 4 + base_index + _QUAD_TRIS[None]).reshape(-1))
                rgb = _COLOR_TABLE[plain_ids, slot] * (shade * plain_parity)[:, None]
                rgba = np.concatenate([rgb, np.ones((count, 1), np.float32)], axis=1)
                cols.append(np.repeat(rgba, 4, axis=0))
                base_index += count * 4
            base_index = _add_sandstone_faces(
                verts, tris, cols, base_index, pos[is_sandstone], corners,
                ids[is_sandstone], shade, parity[is_sandstone])
        else:
            verts.append(quad.reshape(-1, 3))
            tris.append((np.arange(n, dtype=np.int32)[:, None] * 4 + base_index + _QUAD_TRIS[None]).reshape(-1))
            rgb = _COLOR_TABLE[ids, slot] * (shade * parity)[:, None]
            flower_mask = ids == FLOWER
            if flower_mask.any():
                codes = plant_colors[ix[flower_mask], iy[flower_mask], iz[flower_mask]] - 1
                valid = plant_colors[ix[flower_mask], iy[flower_mask], iz[flower_mask]] > 0
                if valid.any():
                    flower_rows = np.flatnonzero(flower_mask)
                    rgb[flower_rows] *= 0.35
                    flower_rgb = _ore_display_colors(codes[valid])
                    rgb[flower_rows[valid]] = flower_rgb * (shade * parity[flower_mask][valid])[:, None]
            rgba = np.concatenate([rgb, np.ones((n, 1), np.float32)], axis=1)
            cols.append(np.repeat(rgba, 4, axis=0))
            base_index += n * 4

    # A planted flower occupies its own cell, but is drawn as a small brown planter
    # tile with a simple sprout/blossom pictogram. This keeps the ground visually
    # continuous instead of leaving an invisible one-block hole.
    fx, fy, fz = np.nonzero(cur == FLOWER)
    if len(fx):
        flower_verts, flower_tris, flower_cols = [], [], []
        flower_index = base_index
        green = np.array([0.18, 0.58, 0.16], dtype=np.float32)
        brown_top = np.array([0.58, 0.39, 0.23], dtype=np.float32)
        brown_side = np.array([0.39, 0.25, 0.14], dtype=np.float32)
        yellow = np.array([1.0, 0.78, 0.20], dtype=np.float32)

        def add_plant_quad(points, rgb):
            nonlocal flower_index
            points = np.asarray(points, dtype=np.float32)
            flower_verts.append(points)
            flower_tris.append(flower_index + _QUAD_TRIS)
            rgba = np.concatenate([np.tile(np.asarray(rgb, dtype=np.float32), (4, 1)), np.ones((4, 1), dtype=np.float32)], axis=1)
            flower_cols.append(rgba)
            flower_index += 4

        for lx, ly, lz in zip(fx, fy, fz):
            x, y, z = float(lx), float(ly + y0), float(lz)
            value = plants.get((int(lx), int(ly + y0), int(lz))) if plants else None
            planted_at = float(value[1]) if value else world_time
            mature = world_time - planted_at >= C.DAY_LENGTH
            code = int(value[0]) if value else 0
            petal = _ore_display_colors(np.array([code], dtype=np.int64))[0] if value else np.array([0.9, 0.25, 0.65], dtype=np.float32)

            # Thin, solid-looking brown tile: top plus four short sides.
            x0, x1, z0, z1, y1 = x + 0.08, x + 0.92, z + 0.08, z + 0.92, y + 0.13
            add_plant_quad([(x0,y1,z0),(x0,y1,z1),(x1,y1,z1),(x1,y1,z0)], brown_top)
            add_plant_quad([(x0,y,z0),(x1,y,z0),(x1,y1,z0),(x0,y1,z0)], brown_side)
            add_plant_quad([(x1,y,z1),(x0,y,z1),(x0,y1,z1),(x1,y1,z1)], brown_side)
            add_plant_quad([(x0,y,z1),(x0,y,z0),(x0,y1,z0),(x0,y1,z1)], brown_side)
            add_plant_quad([(x1,y,z0),(x1,y,z1),(x1,y1,z1),(x1,y1,z0)], brown_side)

            # Stem and two leaves, drawn as crossed thin planes.
            top_y = y + (0.76 if mature else 0.48)
            half = 0.025
            add_plant_quad([(x+0.5-half,y1,z+0.5),(x+0.5-half,top_y,z+0.5),
                            (x+0.5+half,top_y,z+0.5),(x+0.5+half,y1,z+0.5)], green)
            add_plant_quad([(x+0.5,y1,z+0.5-half),(x+0.5,top_y,z+0.5-half),
                            (x+0.5,top_y,z+0.5+half),(x+0.5,y1,z+0.5+half)], green)
            # Two small leaves make the young stage read as a sprout.
            leaf_y = y + 0.34
            add_plant_quad([(x+0.5,leaf_y,z+0.5),(x+0.28,leaf_y+0.10,z+0.5),
                            (x+0.40,leaf_y+0.13,z+0.5),(x+0.5,leaf_y+0.04,z+0.5)], green)
            add_plant_quad([(x+0.5,leaf_y,z+0.5),(x+0.5,leaf_y+0.10,z+0.28),
                            (x+0.5,leaf_y+0.13,z+0.40),(x+0.5,leaf_y+0.04,z+0.5)], green)

            if mature:
                # Four coloured petals around a small yellow centre.
                cy = y + 0.78
                add_plant_quad([(x+0.50,cy,z+0.50),(x+0.50,cy+0.07,z+0.30),
                                (x+0.50,cy+0.10,z+0.40),(x+0.50,cy+0.04,z+0.50)], petal)
                add_plant_quad([(x+0.50,cy,z+0.50),(x+0.50,cy+0.07,z+0.70),
                                (x+0.50,cy+0.10,z+0.60),(x+0.50,cy+0.04,z+0.50)], petal)
                add_plant_quad([(x+0.50,cy,z+0.50),(x+0.30,cy+0.07,z+0.50),
                                (x+0.40,cy+0.10,z+0.50),(x+0.50,cy+0.04,z+0.50)], petal)
                add_plant_quad([(x+0.50,cy,z+0.50),(x+0.70,cy+0.07,z+0.50),
                                (x+0.60,cy+0.10,z+0.50),(x+0.50,cy+0.04,z+0.50)], petal)
                add_plant_quad([(x+0.46,cy+0.08,z+0.46),(x+0.46,cy+0.08,z+0.54),
                                (x+0.54,cy+0.08,z+0.54),(x+0.54,cy+0.08,z+0.46)], yellow)
            else:
                # A small green bud at the tip while the plant is growing.
                by = y + 0.49
                add_plant_quad([(x+0.46,by,z+0.49),(x+0.50,by+0.07,z+0.46),
                                (x+0.54,by,z+0.51),(x+0.50,by-0.01,z+0.54)], green)

        verts.append(np.concatenate(flower_verts, axis=0))
        tris.append(np.concatenate(flower_tris, axis=0))
        cols.append(np.concatenate(flower_cols, axis=0))
        base_index = flower_index

    if not verts:
        return None
    return np.concatenate(verts), np.concatenate(tris), np.concatenate(cols)



def _add_sandstone_faces(verts, tris, cols, base_index, pos, corners, ids, shade, parity):
    """Emit horizontal sediment bands on the vertical faces of sandstone blocks."""
    n = len(pos)
    c = np.asarray(corners, dtype=np.float32)
    vertical = c[1] - c[0]
    across = c[3] - c[0]
    base_rgb = _COLOR_TABLE[ids, 1] * (shade * parity)[:, None]
    for low, high, tint in _SANDSTONE_BANDS:
        quad = (pos[:, None, :] + c[0]
                + np.array([low, low, high, high], dtype=np.float32)[None, :, None] * vertical
                + np.array([0.0, 1.0, 1.0, 0.0], dtype=np.float32)[None, :, None] * across)
        verts.append(quad.reshape(-1, 3))
        tris.append((np.arange(n, dtype=np.int32)[:, None] * 4
                      + base_index + _QUAD_TRIS[None]).reshape(-1))
        rgb = np.clip(base_rgb * tint, 0.0, 1.0)
        rgba = np.concatenate([rgb, np.ones((n, 1), np.float32)], axis=1)
        cols.append(np.repeat(rgba, 4, axis=0))
        base_index += n * 4
    return base_index


def _add_ore_faces(verts, tris, cols, base_index, ms, ox, oy, oz, y0, corners, shade, face_index):
    n = len(ox)
    codes = ms[ox, oy, oz].astype(np.int64) - 1
    pos = np.stack([ox, oy + y0, oz], axis=1).astype(np.float32)                        # (n, 3)
    c = np.array(corners, dtype=np.float32)
    e1, e2 = c[1] - c[0], c[3] - c[0]
    u, v = _SUB_UV[..., 0], _SUB_UV[..., 1]                                             # (9, 4)
    quads = (pos[:, None, None, :] + c[0] + u[None, :, :, None] * e1 + v[None, :, :, None] * e2)   # (n, 9, 4, 3)
    verts.append(quads.reshape(-1, 3))
    sub = np.arange(n * 9, dtype=np.int32)[:, None] * 4 + base_index + _QUAD_TRIS[None]
    tris.append(sub.reshape(-1))

    pattern = _PATTERNS[(ox * 7 + oy * 13 + oz * 29 + face_index * 5 + codes) % len(_PATTERNS)]     # (n, 9)
    ore_rgb = _ore_display_colors(codes) * (0.6 + 0.4 * shade)                          # ore stays bright on side faces
    rgb = np.where(pattern[:, :, None], ore_rgb[:, None, :], (_ROCK_DARK * shade)[None, None, :])   # (n, 9, 3)
    rgba = np.concatenate([rgb, np.ones((n, 9, 1), np.float32)], axis=2).reshape(-1, 4)
    cols.append(np.repeat(rgba, 4, axis=0).astype(np.float32))
    return base_index + n * 9 * 4
