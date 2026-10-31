"""Built-in block definitions plus runtime-registered data-only MOD blocks."""
from dataclasses import dataclass
from typing import Optional, Tuple
import math

AIR, SOIL, GRASS, ROCK, WOOD, LEAF, WATER, FLOWER = range(8)

Color3 = Tuple[float, float, float]


@dataclass(frozen=True)
class BlockInfo:
    key: str                      # key into strings.BLOCK_NAMES
    hardness: Optional[float]     # seconds of holding to break; None = unbreakable
    stack_limit: int
    sound: str                    # sound family: soft / rock / wood / leaf
    drop: Optional[int]           # item id dropped when broken (None = nothing)
    top: Color3
    side: Color3
    bottom: Color3


_SOIL = (0.45, 0.30, 0.18)
BLOCKS = {
    SOIL:  BlockInfo("soil",  0.6, 64, "soft", SOIL,  _SOIL, _SOIL, _SOIL),
    GRASS: BlockInfo("grass", 0.6, 64, "soft", SOIL,  (0.30, 0.65, 0.25), _SOIL, _SOIL),
    ROCK:  BlockInfo("rock",  2.0, 64, "rock", ROCK,  (0.52, 0.52, 0.55), (0.48, 0.48, 0.51), (0.42, 0.42, 0.45)),
    WOOD:  BlockInfo("wood",  1.5, 32, "wood", WOOD,  (0.88, 0.74, 0.50), (0.82, 0.66, 0.42), (0.74, 0.58, 0.36)),
    LEAF:  BlockInfo("leaf",  0.3, 64, "leaf", LEAF,  (0.20, 0.55, 0.20), (0.18, 0.50, 0.18), (0.16, 0.45, 0.16)),
    WATER: BlockInfo("water", None, 1, "soft", None,  (0.20, 0.42, 0.85), (0.18, 0.38, 0.80), (0.16, 0.34, 0.75)),
    FLOWER: BlockInfo("flower", 0.25, 1, "leaf", None, (0.22, 0.58, 0.18), (0.18, 0.48, 0.14), (0.14, 0.36, 0.12)),
}

# Items are block ids for now; minerals arrive in stage 3.
PLACEABLE = {SOIL, ROCK, WOOD, LEAF}
BASE_BLOCK_COUNT = 8
MAX_BLOCK_ID = 255


def register_mod_block(mod_id: str, block_id: str, name: str, hardness: float,
                       stack: int, sound: str, color_top: Color3,
                       color_side: Color3, color_bottom: Color3,
                       placeable: bool = True) -> int:
    """Register one validated data-only MOD block. IDs stay within the world's uint8 storage."""
    key = f"{mod_id}:{block_id}"
    if any(info.key == key for info in BLOCKS.values()):
        raise ValueError(f"duplicate block id: {key}")
    used = set(BLOCKS)
    new_id = next((i for i in range(BASE_BLOCK_COUNT, MAX_BLOCK_ID + 1) if i not in used), None)
    if new_id is None:
        raise ValueError("no free block IDs remain (maximum 255)")
    BLOCKS[new_id] = BlockInfo(key, hardness, stack, sound, new_id if placeable else None,
                               tuple(color_top), tuple(color_side), tuple(color_bottom))
    # The mesher reserves all uint8 IDs and is imported before MOD loading in the game.
    import sys
    mesher = sys.modules.get("world.mesher")
    if mesher is not None:
        mesher._COLOR_TABLE[new_id, 0] = color_top
        mesher._COLOR_TABLE[new_id, 1] = color_side
        mesher._COLOR_TABLE[new_id, 2] = color_bottom
    if placeable:
        PLACEABLE.add(new_id)
    return new_id


def block_name(block: int) -> str:
    """Human-readable fallback name for built-in and MOD blocks."""
    info = BLOCKS[block]
    return info.key.replace(":", " / ").replace("_", " ").title()


def id_for_key(key: str):
    """Resolve a persistent namespaced block key to this run's compact runtime ID."""
    for block_id, info in BLOCKS.items():
        if info.key == key:
            return block_id
    return None


def hardness_at(block: int, y: int) -> Optional[float]:
    """Seconds needed to break, or None if unbreakable (water, world floor at y == 0)."""
    if block == AIR or y <= 0:
        return None
    return BLOCKS[block].hardness


def stack_limit(item: int) -> int:
    return BLOCKS[item].stack_limit


def drop_of(block: int) -> Optional[int]:
    return BLOCKS[block].drop if block in BLOCKS else None
