"""Flower cultivation rules, independent of Ursina."""
import items
from blocks import AIR, SOIL, GRASS, WATER


def planting_cell(world, hit):
    """A seed is planted in the air cell immediately above soil/grass, beside water."""
    if hit is None or hit.block not in (SOIL, GRASS):
        return None
    x, y, z = hit.cell
    cell = (x, y + 1, z)
    if world.get_block(*cell) != AIR:
        return None
    if not any(world.get_block(x + dx, y + 1, z + dz) == WATER
               or world.get_block(x + dx, y, z + dz) == WATER
               for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1))):
        return None
    return cell


def seed_drop_code(rng, extended=False):
    """Choose a colour from the mineral palette available at the current game stage."""
    pools = (tuple(a.tolist() + b.tolist() for a, b in zip(items.TIER_CODES, items.NEW_TIER_CODES))
             if extended else items.TIER_CODES)
    pool = pools[rng.randrange(len(pools))]
    return int(pool[rng.randrange(len(pool))])
