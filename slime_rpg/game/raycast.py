"""Voxel ray traversal (Amanatides & Woo). Cell space: block (x, y, z) occupies [x, x+1)."""
import math
from collections import namedtuple

from blocks import AIR

Hit = namedtuple("Hit", "cell prev block")   # prev = last empty cell before the hit (None if none)


def raycast(get_block, origin, direction, max_dist):
    ox, oy, oz = origin
    dx, dy, dz = direction
    length = math.sqrt(dx * dx + dy * dy + dz * dz)
    if length == 0:
        return None
    dx, dy, dz = dx / length, dy / length, dz / length

    cell = [math.floor(ox), math.floor(oy), math.floor(oz)]
    pos = (ox, oy, oz)
    d = (dx, dy, dz)
    step, tmax, tdelta = [0, 0, 0], [math.inf] * 3, [math.inf] * 3
    for i in range(3):
        if d[i] > 0:
            step[i] = 1
            tmax[i] = (cell[i] + 1 - pos[i]) / d[i]
            tdelta[i] = 1.0 / d[i]
        elif d[i] < 0:
            step[i] = -1
            tmax[i] = (pos[i] - cell[i]) / -d[i]
            tdelta[i] = 1.0 / -d[i]

    prev = None
    while True:
        block = get_block(cell[0], cell[1], cell[2])
        if block != AIR:
            return Hit(tuple(cell), prev, block)
        prev = tuple(cell)
        axis = 0 if tmax[0] <= tmax[1] and tmax[0] <= tmax[2] else (1 if tmax[1] <= tmax[2] else 2)
        if tmax[axis] > max_dist:
            return None
        cell[axis] += step[axis]
        tmax[axis] += tdelta[axis]
