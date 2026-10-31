"""Streams chunks around the player: at most ONE generate-or-mesh task per call, nearest first,
so walking never causes a big hitch. Engine-agnostic: the renderer plugs in callbacks."""
import config as C
from world.mesher import mesh_section


def _offsets(radius):
    offs = [(dx, dz) for dx in range(-radius, radius + 1) for dz in range(-radius, radius + 1)
            if dx * dx + dz * dz <= radius * radius + radius]
    offs.sort(key=lambda o: o[0] * o[0] + o[1] * o[1])
    return offs


class ChunkManager:
    def __init__(self, world, on_mesh, on_unload):
        """on_mesh((cx, cz, section), data_or_None); on_unload(cx, cz)."""
        self.world = world
        self.on_mesh = on_mesh
        self.on_unload = on_unload
        self.meshed = set()
        self._offsets = _offsets(C.DATA_RADIUS)
        self._last_center = None
        self.world_time = 0.0

    def update_world_time(self, world_time):
        """Invalidate chunks exactly when a planted seed crosses its one-day growth threshold."""
        previous = self.world_time
        self.world_time = float(world_time)
        if self.world_time <= previous:
            return
        for (cx, cz), chunk in self.world.chunks.items():
            for (lx, y, lz), (_, planted_at) in chunk.plants.items():
                if previous - planted_at < C.DAY_LENGTH <= self.world_time - planted_at:
                    self.world._mark_dirty(cx, cz, lx, y, lz)

    def _dist2(self, cx, cz, pcx, pcz):
        return (cx - pcx) ** 2 + (cz - pcz) ** 2

    def mesh_chunk(self, cx, cz):
        padded = self.world.padded(cx, cz)
        minerals = self.world.chunks[(cx, cz)].minerals
        for sy in range(C.SECTIONS_PER_CHUNK):
            self.on_mesh((cx, cz, sy), mesh_section(padded, sy, minerals, self.world.chunks[(cx, cz)].plants, self.world_time))
        self.meshed.add((cx, cz))

    def step(self, pcx, pcz):
        """Do pending edits plus at most one load task. Returns 'gen', 'mesh' or None (idle)."""
        w = self.world

        # Player edits are rebuilt immediately so digging feels instant.
        for (cx, cz, sy) in w.pop_dirty():
            if (cx, cz) in self.meshed and w.has_chunk(cx, cz):
                self.on_mesh((cx, cz, sy), mesh_section(w.padded(cx, cz), sy, w.chunks[(cx, cz)].minerals, w.chunks[(cx, cz)].plants, self.world_time))

        if self._last_center != (pcx, pcz):
            self._last_center = (pcx, pcz)
            self._unload_far(pcx, pcz)

        r2 = C.RENDER_RADIUS * C.RENDER_RADIUS + C.RENDER_RADIUS
        for dx, dz in self._offsets:
            cx, cz = pcx + dx, pcz + dz
            if not w.has_chunk(cx, cz):
                w.get_chunk(cx, cz)
                return "gen"
            if (cx, cz) not in self.meshed and dx * dx + dz * dz <= r2:
                if all(w.has_chunk(cx + a, cz + b) for a, b in ((1, 0), (-1, 0), (0, 1), (0, -1))):
                    self.mesh_chunk(cx, cz)
                    return "mesh"
        return None

    def _unload_far(self, pcx, pcz):
        limit = C.UNLOAD_RADIUS ** 2 + C.UNLOAD_RADIUS
        for cx, cz in list(self.meshed):
            if self._dist2(cx, cz, pcx, pcz) > limit:
                self.meshed.discard((cx, cz))
                self.on_unload(cx, cz)
        for cx, cz in list(self.world.chunks):
            if (cx, cz) not in self.meshed and self._dist2(cx, cz, pcx, pcz) > limit + 2 * C.UNLOAD_RADIUS:
                self.world.unload(cx, cz)
