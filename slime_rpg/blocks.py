"""Block definitions. Six block types only (design doc section 8.2)."""
from dataclasses import dataclass
from typing import Optional, Tuple

AIR, SOIL, GRASS, ROCK, WOOD, LEAF, WATER = range(7)

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
}

# Items are block ids for now; minerals arrive in stage 3.
PLACEABLE = {SOIL, ROCK, WOOD, LEAF}


def hardness_at(block: int, y: int) -> Optional[float]:
    """Seconds needed to break, or None if unbreakable (water, world floor at y == 0)."""
    if block == AIR or y <= 0:
        return None
    return BLOCKS[block].hardness


def stack_limit(item: int) -> int:
    return BLOCKS[item].stack_limit


def drop_of(block: int) -> Optional[int]:
    return BLOCKS[block].drop if block in BLOCKS else None
