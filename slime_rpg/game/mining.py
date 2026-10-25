"""Hold-to-break mining (design 8.3-8.5). Pure logic: the renderer reads the returned events."""
from dataclasses import dataclass, field

import config as C
import items
from blocks import AIR, ROCK, BLOCKS, hardness_at, drop_of


@dataclass
class MineResult:
    target: tuple = None
    progress: float = 0.0       # 0..1, drives the crack overlay
    block: int = AIR            # block being dug (for the hit sound family)
    tick: bool = False          # play a hit sound now
    broke: bool = False
    gained: list = field(default_factory=list)   # [(item, count)]
    lost: list = field(default_factory=list)     # [(item, count)]  inventory was full


class Miner:
    def __init__(self, world, inventory):
        self.world = world
        self.inventory = inventory
        self.target = None
        self.progress = 0.0
        self._tick_timer = 0.0
        self._cooldown = 0.0

    def reset(self):
        self.target = None
        self.progress = 0.0
        self._tick_timer = 0.0

    def update(self, dt, holding, target):
        """target: the cell under the crosshair (or None). Call once per frame."""
        self._cooldown = max(0.0, self._cooldown - dt)
        if not holding or target is None or target != self.target:
            self.reset()
            if not holding or target is None:
                return MineResult()
            self.target = target

        x, y, z = target
        block = self.world.get_block(x, y, z)
        hardness = hardness_at(block, y)
        mineral = self.world.get_mineral(x, y, z) if block == ROCK else None
        if hardness is not None and mineral is not None:
            hardness = items.mineral_hardness(mineral)             # richer ore is harder to dig out
        if hardness is None or self._cooldown > 0:
            return MineResult(target=target, block=block)

        res = MineResult(target=target, block=block)
        self._tick_timer -= dt
        if self._tick_timer <= 0:
            res.tick = True
            self._tick_timer += C.HIT_INTERVAL

        self.progress += dt / hardness
        res.progress = min(self.progress, 1.0)
        if self.progress >= 1.0:
            self.world.remove_block(x, y, z)
            drops = []
            if mineral is not None:
                drops.append(items.item_of(mineral))               # mineral first: if space is short, the plain rock is lost
            if drop_of(block) is not None:
                drops.append(drop_of(block))
            for item in drops:
                left = self.inventory.add(item, 1)
                if left < 1:
                    res.gained.append((item, 1))
                if left:
                    res.lost.append((item, left))
            res.broke = True
            self.reset()
            self._cooldown = C.BREAK_COOLDOWN
        return res
