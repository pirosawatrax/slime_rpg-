"""Placing blocks. Water cells accept only Wood (bridges, design 10.3)."""
from collections import namedtuple

import config as C
from blocks import AIR, WATER, WOOD, BLOCKS, PLACEABLE

PlaceResult = namedtuple("PlaceResult", "placed cell block")


def try_place(world, inventory, slot, hit, body):
    """hit: game.raycast.Hit. Returns PlaceResult; consumes one item when placed."""
    nothing = PlaceResult(False, None, None)
    item = inventory.item_at(slot)
    if hit is None or item is None or item not in PLACEABLE:
        return nothing
    if hit.block == WATER:
        # Built-in and MOD-added wood-family blocks can form bridges.
        if BLOCKS[item].sound != "wood":
            return nothing
        cell = hit.cell
    else:
        cell = hit.prev
        if cell is None:
            return nothing
    x, y, z = cell
    if not 0 <= y < C.WORLD_HEIGHT or world.get_block(x, y, z) not in (AIR, WATER):
        return nothing
    if body.overlaps_cell(x, y, z):
        return nothing
    inventory.take(slot, 1)
    world.set_block(x, y, z, item)
    return PlaceResult(True, cell, item)
