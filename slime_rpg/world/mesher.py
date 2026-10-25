"""Turns a 16x16x16 section of blocks into vertex arrays (numpy only, no engine imports).
Hidden faces are culled. Vertex positions are relative to the chunk origin (x, z), absolute in y."""
import numpy as np

import config as C
import items
from blocks import AIR, WATER, ROCK, BLOCKS

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

_COLOR_TABLE = np.zeros((max(BLOCKS) + 1, 3, 3), dtype=np.float32)
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


def _ore_display_colors(codes):
    """Mineral colours as drawn: the true colour pushed toward full brightness (ORE_GLOW) so ore stands out at range."""
    lv = np.stack([(codes // 100) % 10, (codes // 10) % 10, codes % 10], axis=1).astype(np.float32)
    true = (items.LOW + items.STEP * lv) / 255.0
    bright = true / true.max(axis=1, keepdims=True) * 0.95
    return (1.0 - C.ORE_GLOW) * true + C.ORE_GLOW * bright


def mesh_section(padded, sy, minerals=None):
    """Return (vertices (N,3) f32, triangle indices (M,) i32, colours (N,4) f32) or None if nothing is visible.
    minerals: the chunk's (16, 64, 16) uint16 mineral array (0 = none, else 1 + colour code), or None."""
    y0 = sy * SH
    cur = padded[1:S + 1, y0 + 1:y0 + SH + 1, 1:S + 1]
    if not cur.any():
        return None
    ms = minerals[:, y0:y0 + SH, :] if minerals is not None else None
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
        visible = (((cur != AIR) & (cur != WATER) & open_side & ~ore)
                   | ((cur == WATER) & (nb == AIR)))
        ix, iy, iz = np.nonzero(visible)
        n = len(ix)
        if n == 0:
            continue
        ids = cur[visible]
        pos = np.stack([ix, iy + y0, iz], axis=1).astype(np.float32)           # (n, 3)
        quad = pos[:, None, :] + np.array(corners, dtype=np.float32)[None]     # (n, 4, 3)
        verts.append(quad.reshape(-1, 3))
        tris.append((np.arange(n, dtype=np.int32)[:, None] * 4 + base_index + _QUAD_TRIS[None]).reshape(-1))
        parity = ((ix + iy + iz) & 1).astype(np.float32) * 0.06 + 0.94         # subtle checker for depth cues
        rgb = _COLOR_TABLE[ids, slot] * (shade * parity)[:, None]
        rgba = np.concatenate([rgb, np.ones((n, 1), np.float32)], axis=1)
        cols.append(np.repeat(rgba, 4, axis=0))
        base_index += n * 4

    if not verts:
        return None
    return np.concatenate(verts), np.concatenate(tris), np.concatenate(cols)


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
