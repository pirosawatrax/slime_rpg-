"""Block storage. Chunks are (16, 64, 16) uint8 arrays indexed [x, y, z]; world Y is up."""
import numpy as np

import config as C
from blocks import AIR, ROCK, LEAF, WOOD, WATER
from world.worldgen import generate_chunk_full

S = C.CHUNK_SIZE
H = C.WORLD_HEIGHT


class Chunk:
    __slots__ = ("cx", "cz", "blocks", "minerals", "base", "edits", "ore_cleared", "modified")

    def __init__(self, cx, cz, blocks, minerals=None):
        self.cx, self.cz = cx, cz
        self.blocks = blocks
        # 0 = none, else 1 + colour code. Cleared whenever the cell is edited (a mined mineral never returns).
        self.minerals = minerals if minerals is not None else np.zeros(blocks.shape, dtype=np.uint16)
        self.base = blocks.copy()   # untouched generated terrain (bridges revert to water using this)
        self.edits = {}             # (lx, y, lz) -> block id: the diff over generated terrain that gets saved
        self.ore_cleared = set()    # cells whose generated mineral was dug out: always kept in the diff, even if the
                                    # block is back to its generated type, or the ore would reappear after a reload
        self.modified = False       # changed since the last save/load


class World:
    def __init__(self, seed=C.SEED, generator=None, store=None):
        self.seed = seed
        self.store = store          # SaveStore or None; saved edits are applied lazily as chunks are generated
        self.extended = False       # True once the boss has fallen: new ore colours appear in chunks generated from now on
        self._generator = generator or (lambda seed_, cx, cz: generate_chunk_full(seed_, cx, cz, self.extended))
        self.chunks = {}
        self.dirty = set()          # (cx, cz, section) whose meshes need rebuilding

    # ---- chunk access -------------------------------------------------
    def has_chunk(self, cx, cz):
        return (cx, cz) in self.chunks

    def get_chunk(self, cx, cz):
        ch = self.chunks.get((cx, cz))
        if ch is None:
            made = self._generator(self.seed, cx, cz)      # blocks, or (blocks, minerals)
            blocks, minerals = made if isinstance(made, tuple) else (made, None)
            ch = Chunk(cx, cz, blocks, minerals)
            self._apply_saved_edits(ch)
            self.chunks[(cx, cz)] = ch
        return ch

    def _apply_saved_edits(self, ch):
        if self.store is None:
            return
        for (lx, y, lz), block in self.store.load_chunk_edits(ch.cx, ch.cz).items():
            ch.blocks[lx, y, lz] = block
            if ch.minerals[lx, y, lz]:
                ch.ore_cleared.add((lx, y, lz))
                ch.minerals[lx, y, lz] = 0
            if int(ch.base[lx, y, lz]) != block or (lx, y, lz) in ch.ore_cleared:
                ch.edits[(lx, y, lz)] = block

    def unload(self, cx, cz):
        """Drop a chunk's data from memory. Unsaved changes are never dropped; with a save store, saved edits
        are reloaded from disk when the chunk comes back."""
        ch = self.chunks.get((cx, cz))
        if ch is None or ch.modified:
            return
        if self.store is not None or not ch.edits:
            del self.chunks[(cx, cz)]

    def forget_unmodified(self):
        """Drop every chunk the player has not changed since the last save, so it is generated again the next time it is
        needed. Used when the boss falls: regenerated chunks hold the post-boss ore colours. Edits are kept."""
        for cx, cz in list(self.chunks):
            self.unload(cx, cz)

    # ---- block access -------------------------------------------------
    def get_block(self, x, y, z):
        if y < 0:
            return ROCK
        if y >= H:
            return AIR
        ch = self.get_chunk(x >> 4, z >> 4)
        return int(ch.blocks[x & 15, y, z & 15])

    def get_mineral(self, x, y, z):
        """Colour code (0..511) of the mineral in this rock cell, or None."""
        if not 0 <= y < H:
            return None
        v = int(self.get_chunk(x >> 4, z >> 4).minerals[x & 15, y, z & 15])
        return v - 1 if v else None

    def set_block(self, x, y, z, block):
        if not 0 <= y < H:
            return
        cx, cz = x >> 4, z >> 4
        lx, lz = x & 15, z & 15
        ch = self.get_chunk(cx, cz)
        ch.blocks[lx, y, lz] = block
        if ch.minerals[lx, y, lz]:
            ch.ore_cleared.add((lx, y, lz))
            ch.minerals[lx, y, lz] = 0
        ch.modified = True
        if int(ch.base[lx, y, lz]) == block and (lx, y, lz) not in ch.ore_cleared:
            ch.edits.pop((lx, y, lz), None)
        else:
            ch.edits[(lx, y, lz)] = block
        self._mark_dirty(cx, cz, lx, y, lz)

    def remove_block(self, x, y, z):
        """Break a block. A bridge block placed on water turns back into water."""
        ch = self.get_chunk(x >> 4, z >> 4)
        base = int(ch.base[x & 15, y, z & 15]) if 0 <= y < H else AIR
        self.set_block(x, y, z, WATER if base == WATER else AIR)

    def _mark_dirty(self, cx, cz, lx, y, lz):
        sy = y // C.SECTION_HEIGHT
        self.dirty.add((cx, cz, sy))
        if lx == 0:
            self.dirty.add((cx - 1, cz, sy))
        if lx == S - 1:
            self.dirty.add((cx + 1, cz, sy))
        if lz == 0:
            self.dirty.add((cx, cz - 1, sy))
        if lz == S - 1:
            self.dirty.add((cx, cz + 1, sy))
        if y % C.SECTION_HEIGHT == 0 and sy > 0:
            self.dirty.add((cx, cz, sy - 1))
        if y % C.SECTION_HEIGHT == C.SECTION_HEIGHT - 1 and sy < C.SECTIONS_PER_CHUNK - 1:
            self.dirty.add((cx, cz, sy + 1))

    def pop_dirty(self):
        d, self.dirty = self.dirty, set()
        return d

    # ---- queries ------------------------------------------------------
    def is_blocking(self, x, y, z):
        """Collision test for one cell. Water blocks the body, and an invisible wall above water
        stops the player from standing on its surface (bridges are the only way across)."""
        if self.get_block(x, y, z) != AIR:
            return True
        below = self.get_block(x, y - 1, z)
        if below == WATER:
            return True
        if below == AIR and self.get_block(x, y - 2, z) == WATER:
            return True
        return False

    def surface_y(self, x, z):
        """Y of the highest block that is not a tree part (-1 if the column is empty)."""
        for y in range(H - 1, -1, -1):
            if self.get_block(x, y, z) not in (AIR, LEAF, WOOD):
                return y
        return -1

    def padded(self, cx, cz):
        """(18, 66, 18) copy of a chunk with a one-cell border from its neighbours, for face culling.
        Missing neighbours count as solid so no faces are drawn toward unloaded terrain."""
        p = np.full((S + 2, H + 2, S + 2), ROCK, dtype=np.uint8)
        p[:, H + 1, :] = AIR
        p[1:S + 1, 1:H + 1, 1:S + 1] = self.chunks[(cx, cz)].blocks
        nb = self.chunks.get((cx - 1, cz))
        if nb is not None:
            p[0, 1:H + 1, 1:S + 1] = nb.blocks[S - 1]
        nb = self.chunks.get((cx + 1, cz))
        if nb is not None:
            p[S + 1, 1:H + 1, 1:S + 1] = nb.blocks[0]
        nb = self.chunks.get((cx, cz - 1))
        if nb is not None:
            p[1:S + 1, 1:H + 1, 0] = nb.blocks[:, :, S - 1]
        nb = self.chunks.get((cx, cz + 1))
        if nb is not None:
            p[1:S + 1, 1:H + 1, S + 1] = nb.blocks[:, :, 0]
        return p
