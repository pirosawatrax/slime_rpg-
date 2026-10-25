"""Deterministic, vectorised value noise (numpy). No chunk-boundary seams: depends only on world coordinates."""
import numpy as np

_M32 = 0xFFFFFFFF


def _hash(ix, iy, iz, seed):
    """Integer lattice hash -> floats in [0, 1). Inputs are int arrays (broadcastable)."""
    with np.errstate(over="ignore"):
        return _hash_impl(ix, iy, iz, seed)


def _hash_impl(ix, iy, iz, seed):
    u32 = np.uint32
    h = ix.astype(u32) * u32(73856093)
    h = h ^ (iy.astype(u32) * u32(19349663))
    h = h ^ (iz.astype(u32) * u32(83492791))
    h = h ^ u32((seed * 2654435761) & _M32)
    h = h ^ (h >> u32(13))
    h = h * u32(0x5BD1E995)
    h = h ^ (h >> u32(15))
    h = h * u32(0x27D4EB2D)
    h = h ^ (h >> u32(16))
    return h.astype(np.float64) / 4294967296.0


def _smooth(t):
    return t * t * (3.0 - 2.0 * t)


def hash2(x, z, seed):
    """Per-cell random value for integer coordinates (used for trees)."""
    x = np.asarray(x, dtype=np.int64)
    z = np.asarray(z, dtype=np.int64)
    return _hash(x, np.zeros_like(x), z, seed)


def hash3(x, y, z, seed):
    """Per-cell random value for integer cell coordinates (broadcastable int arrays)."""
    return _hash(np.asarray(x, dtype=np.int64), np.asarray(y, dtype=np.int64), np.asarray(z, dtype=np.int64), seed)


def value_noise2(x, z, scale, seed):
    fx = np.asarray(x, dtype=np.float64) / scale
    fz = np.asarray(z, dtype=np.float64) / scale
    x0 = np.floor(fx)
    z0 = np.floor(fz)
    tx = _smooth(fx - x0)
    tz = _smooth(fz - z0)
    ix = x0.astype(np.int64)
    iz = z0.astype(np.int64)
    zero = np.zeros_like(ix)
    c00 = _hash(ix, zero, iz, seed)
    c10 = _hash(ix + 1, zero, iz, seed)
    c01 = _hash(ix, zero, iz + 1, seed)
    c11 = _hash(ix + 1, zero, iz + 1, seed)
    a = c00 + (c10 - c00) * tx
    b = c01 + (c11 - c01) * tx
    return a + (b - a) * tz


def value_noise3(x, y, z, scale, seed):
    fx = np.asarray(x, dtype=np.float64) / scale
    fy = np.asarray(y, dtype=np.float64) / scale
    fz = np.asarray(z, dtype=np.float64) / scale
    x0, y0, z0 = np.floor(fx), np.floor(fy), np.floor(fz)
    tx, ty, tz = _smooth(fx - x0), _smooth(fy - y0), _smooth(fz - z0)
    ix, iy, iz = x0.astype(np.int64), y0.astype(np.int64), z0.astype(np.int64)

    def c(dx, dy, dz):
        return _hash(ix + dx, iy + dy, iz + dz, seed)

    a0 = c(0, 0, 0) + (c(1, 0, 0) - c(0, 0, 0)) * tx
    b0 = c(0, 1, 0) + (c(1, 1, 0) - c(0, 1, 0)) * tx
    a1 = c(0, 0, 1) + (c(1, 0, 1) - c(0, 0, 1)) * tx
    b1 = c(0, 1, 1) + (c(1, 1, 1) - c(0, 1, 1)) * tx
    d0 = a0 + (b0 - a0) * ty
    d1 = a1 + (b1 - a1) * ty
    return d0 + (d1 - d0) * tz
