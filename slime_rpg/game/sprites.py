"""Pixel-art slime (32x32 by default), drawn in code and tinted by any RGB colour, so the player and every enemy
are the same slime in different colours. Cel-shaded in four bands with a dark outline, a highlight and two black dot eyes.
Transparent pixels are (0, 0, 0, 0): on the black battle screen they simply disappear."""
import numpy as np

SHADE_BANDS = (0.58, 0.78, 1.00, 1.20)      # darkest ... lightest multiplier of the base colour
OUTLINE = 0.38
_LIGHT = np.array([-0.40, 0.60, 0.70])
_LIGHT = _LIGHT / np.linalg.norm(_LIGHT)


def _mask(size):
    """Slime silhouette: a squashed dome with a flat base."""
    top, bottom = int(size * 0.16), int(size * 0.88)
    cx = (size - 1) / 2.0
    a = size * 0.44
    ys, xs = np.mgrid[0:size, 0:size]
    nx = (xs - cx) / a
    ny = (ys - bottom) / float(bottom - top)                  # -1 at the top, 0 at the base
    wobble = 1.0 + 0.035 * np.sin(xs * 0.9) * (ny > -0.7)     # slightly uneven edge
    mask = (np.abs(nx) ** 2.3 + np.abs(ny) ** 2.0 <= wobble) & (ny <= 0.0) & (ys >= top)
    return mask, nx, ny, top, bottom, cx


def slime_sprite(rgb, size=32):
    """(size, size, 4) uint8 RGBA image of a slime of the given colour (0..255 per channel)."""
    base = np.array(rgb, dtype=np.float64) / 255.0
    mask, nx, ny, top, bottom, cx = _mask(size)
    v = np.clip(-ny, 0.0, 1.0)
    nz = np.sqrt(np.clip(1.0 - nx ** 2 - v ** 2 * 0.55, 0.05, 1.0))
    normal = np.stack([nx, v, nz], axis=-1)
    normal /= np.linalg.norm(normal, axis=-1, keepdims=True)
    lambert = np.clip(normal @ _LIGHT, 0.0, 1.0)
    band = np.digitize(lambert, [0.30, 0.52, 0.72])           # 0..3
    factor = np.array(SHADE_BANDS)[band]

    img = np.zeros((size, size, 4), dtype=np.float64)
    img[..., :3] = np.clip(base[None, None, :] * factor[..., None], 0.0, 1.0)
    img[..., 3] = 1.0

    # outline: body pixels that touch the outside
    pad = np.pad(mask, 1, constant_values=False)
    inside = pad[1:-1, 1:-1] & pad[:-2, 1:-1] & pad[2:, 1:-1] & pad[1:-1, :-2] & pad[1:-1, 2:]
    edge = mask & ~inside
    img[edge, :3] = np.clip(base * OUTLINE, 0.0, 1.0)

    def paint(x, y, color, alpha=1.0):
        if 0 <= x < size and 0 <= y < size and mask[y, x]:
            img[y, x, :3] = img[y, x, :3] * (1 - alpha) + np.array(color) * alpha

    # highlight (upper left)
    hx, hy = int(cx - size * 0.17), top + int(size * 0.16)
    for dx, dy in ((0, 0), (1, 0), (0, 1), (2, 1)):
        paint(hx + dx, hy + dy, (1, 1, 1), 0.55)
    # eyes: two small black dots (no whites, no mouth: cuter)
    ey = bottom - int(size * 0.40)
    for side in (-1, 1):
        ex = int(round(cx + side * size * 0.15)) - (0 if side < 0 else 1)
        for dx in (0, 1):
            for dy in (0, 1, 2):
                paint(ex + dx, ey + dy, (0.04, 0.04, 0.07))

    out = np.zeros((size, size, 4), dtype=np.uint8)
    out[..., :3] = np.rint(img[..., :3] * 255).astype(np.uint8)
    out[..., 3] = np.where(mask, 255, 0).astype(np.uint8)
    out[~mask, :3] = 0                                        # transparent pixels are black
    return out
