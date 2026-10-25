"""Player body: gravity, jumping and axis-separated AABB collision against voxels (no engine colliders)."""
import math

import config as C

EPS = 1e-4


class Body:
    def __init__(self, world, x, y, z):
        self.world = world
        self.x, self.y, self.z = x, y, z       # position of the feet centre
        self.vy = 0.0
        self.on_ground = False
        self.hw = C.PLAYER_WIDTH / 2
        self.h = C.PLAYER_HEIGHT

    def collides(self, x, y, z):
        hw, h = self.hw, self.h
        x0, x1 = math.floor(x - hw), math.floor(x + hw - 1e-9)
        y0, y1 = math.floor(y), math.floor(y + h - 1e-9)
        z0, z1 = math.floor(z - hw), math.floor(z + hw - 1e-9)
        blocking = self.world.is_blocking
        for ix in range(x0, x1 + 1):
            for iy in range(y0, y1 + 1):
                for iz in range(z0, z1 + 1):
                    if blocking(ix, iy, iz):
                        return True
        return False

    def overlaps_cell(self, cx, cy, cz):
        hw = self.hw
        return (self.x - hw < cx + 1 and self.x + hw > cx and
                self.y < cy + 1 and self.y + self.h > cy and
                self.z - hw < cz + 1 and self.z + hw > cz)

    def update(self, dt, move_x, move_z, jump):
        """move_x / move_z are world-space velocity components (blocks per second)."""
        steps = max(1, math.ceil(dt / (1 / 90)))
        sdt = dt / steps
        for _ in range(steps):
            self._step(sdt, move_x, move_z, jump)
            jump = False                      # a jump request applies to the first sub-step only

    def _step(self, dt, move_x, move_z, jump):
        if jump and self.on_ground:
            self.vy = C.JUMP_SPEED
            self.on_ground = False
        self.vy = max(self.vy - C.GRAVITY * dt, C.TERMINAL_VELOCITY)

        # X
        nx = self.x + move_x * dt
        if self.collides(nx, self.y, self.z):
            if move_x > 0:
                nx = math.floor(nx + self.hw) - self.hw - EPS
            else:
                nx = math.floor(nx - self.hw) + 1 + self.hw + EPS
            if self.collides(nx, self.y, self.z):
                nx = self.x
        self.x = nx
        # Z
        nz = self.z + move_z * dt
        if self.collides(self.x, self.y, nz):
            if move_z > 0:
                nz = math.floor(nz + self.hw) - self.hw - EPS
            else:
                nz = math.floor(nz - self.hw) + 1 + self.hw + EPS
            if self.collides(self.x, self.y, nz):
                nz = self.z
        self.z = nz
        # Y
        ny = self.y + self.vy * dt
        self.on_ground = False
        if self.collides(self.x, ny, self.z):
            if self.vy > 0:
                ny = math.floor(ny + self.h) - self.h - EPS
            else:
                ny = math.floor(ny) + 1 + EPS
                self.on_ground = True
            self.vy = 0.0
            if self.collides(self.x, ny, self.z):
                ny = self.y
        self.y = ny
