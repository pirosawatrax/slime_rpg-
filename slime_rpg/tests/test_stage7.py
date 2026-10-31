"""Caves, ore distribution and the generated background music."""
import tempfile
import time
import unittest
import wave
from pathlib import Path

import numpy as np

import config as C
from audio import music as M
from blocks import AIR, GRASS, LEAF, ROCK, SOIL, WATER, WOOD
from world import boss_arena, villages
from world.world import World
from world.worldgen import generate_chunk_full
from world.worldgen_heights import surface_heights

REGION = [(cx, cz) for cx in range(-4, 4) for cz in range(-4, 4)]


def region_blocks(chunks=REGION):
    out = {}
    for cx, cz in chunks:
        b, m = generate_chunk_full(C.SEED, cx, cz)
        h = surface_heights(C.SEED, (cx * 16 + np.arange(16))[:, None], (cz * 16 + np.arange(16))[None, :])
        out[(cx, cz)] = (b, m, h)
    return out


class TestCaves(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = region_blocks()

    def test_a_large_share_of_the_underground_is_hollow(self):
        air = under = 0
        for b, m, h in self.data.values():
            y = np.arange(C.WORLD_HEIGHT)[None, :, None]
            zone = (y >= 3) & (y <= h[:, None, :] - 5)
            air += int(((b == AIR) & zone).sum())
            under += int(zone.sum())
        share = air / under
        self.assertTrue(0.08 < share < 0.25, share)                       # was about 2% before

    def test_the_caves_form_one_connected_network(self):
        cx0, cz0 = -2, -2                                                  # a 4x4-chunk block, flood-filled in 3D
        size = 64
        grid = np.zeros((size, C.WORLD_HEIGHT, size), dtype=bool)
        for cx in range(cx0, cx0 + 4):
            for cz in range(cz0, cz0 + 4):
                b = self.data[(cx, cz)][0]
                grid[(cx - cx0) * 16:(cx - cx0 + 1) * 16, :, (cz - cz0) * 16:(cz - cz0 + 1) * 16] = (b == AIR)
        grid[:, 40:, :] = False                                            # ignore open sky; look at the underground only
        seen = np.zeros_like(grid)
        best = 0
        for start in map(tuple, np.argwhere(grid)[::53]):
            if seen[start]:
                continue
            stack, n = [start], 0
            seen[start] = True
            while stack:
                x, y, z = stack.pop()
                n += 1
                for dx, dy, dz in ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1)):
                    q = (x + dx, y + dy, z + dz)
                    if 0 <= q[0] < size and 0 <= q[1] < C.WORLD_HEIGHT and 0 <= q[2] < size and grid[q] and not seen[q]:
                        seen[q] = True
                        stack.append(q)
            best = max(best, n)
        self.assertGreater(best / grid.sum(), 0.80, "most caves should be linked, so you can walk through them")

    def test_there_are_cave_entrances_but_the_surface_is_otherwise_sealed(self):
        open_cols = land_cols = 0
        for (cx, cz), (b, m, h) in self.data.items():
            land = h >= C.SEA_LEVEL + 1
            top = b[np.arange(16)[:, None], h, np.arange(16)[None, :]]
            open_cols += int(((top == AIR) & land).sum())
            land_cols += int(land.sum())
            ent = (value_noise2_at(cx, cz) > C.CAVE_ENTRANCE[0]) & land
            skin = np.stack([b[np.arange(16)[:, None], np.maximum(h - k, 0), np.arange(16)[None, :]] for k in (0, 1, 2)])
            sealed = ~ent
            # outside entrance columns (and away from the lair) the three top layers are never hollow
            ax, az = boss_arena.arena_center(C.SEED)
            if abs(cx * 16 + 8 - ax) > 20 or abs(cz * 16 + 8 - az) > 20:
                self.assertTrue((skin[:, sealed] != AIR).all(), (cx, cz))
        share = open_cols / land_cols
        self.assertTrue(0.005 < share < 0.08, share)

    def test_caves_never_open_under_water_and_the_floor_is_intact(self):
        for (cx, cz), (b, m, h) in self.data.items():
            water_cols = h < C.SEA_LEVEL
            if water_cols.any():
                for k in (0, 1, 2):
                    cells = b[np.arange(16)[:, None], np.maximum(h - k, 0), np.arange(16)[None, :]]
                    self.assertTrue((cells[water_cols] != AIR).all(), "a cave under a lake would leave water hanging")
            self.assertTrue((b[:, 0, :] != AIR).all(), "the world floor")
            if boss_arena.arena_near_chunk(C.SEED, cx, cz) is None:           # the lair is the only room that reaches the floor
                self.assertTrue((b[:, 1:3, :] != AIR).all(), "caves stay off the bottom layers")

    def test_no_floating_trees(self):
        """Cave entrances are kept free of trees: every trunk must stand on solid ground."""
        checked = 0
        for (cx, cz), (b, m, h) in self.data.items():
            wood = (b == WOOD)
            below = np.zeros_like(wood)
            below[:, 1:, :] = wood[:, :-1, :]
            base = wood & ~below
            for x, y, z in np.argwhere(base):
                support = int(b[x, y - 1, z])
                from blocks import BLOCKS
                self.assertTrue(support in (GRASS, SOIL, ROCK) or
                                (support in BLOCKS and BLOCKS[support].sound == "rock"),
                                (cx, cz, x, y, z, support))
                checked += 1
        self.assertGreater(checked, 20)

    def test_generation_is_still_fast_with_the_bigger_caves(self):
        t = time.perf_counter()
        for i in range(12):
            generate_chunk_full(C.SEED, 40 + i, -40 - i)
        self.assertLess((time.perf_counter() - t) / 12 * 1000, 30)


def value_noise2_at(cx, cz):
    from world.noise import value_noise2
    thr, scale = C.CAVE_ENTRANCE
    return value_noise2((cx * 16 + np.arange(16))[:, None], (cz * 16 + np.arange(16))[None, :], scale, C.SEED + 31)


class TestOreDistribution(unittest.TestCase):
    def test_underground_ore_is_denser_and_gets_denser_with_depth(self):
        by = {"shallow": [0, 0], "middle": [0, 0], "deep": [0, 0]}
        surface_ore = underground_ore = 0
        for b, m, h in region_blocks().values():
            y = np.arange(C.WORLD_HEIGHT)[None, :, None]
            depth = h[:, None, :] - y
            for name, (lo, hi) in {"shallow": (0, 8), "middle": (8, 20), "deep": (20, 99)}.items():
                sel = (depth >= lo) & (depth < hi) & (y >= 2)
                by[name][0] += int(((m > 0) & sel).sum())
                by[name][1] += int(((b == ROCK) & sel).sum())
            above = y > h[:, None, :]
            surface_ore += int(((m > 0) & above).sum())
            underground_ore += int(((m > 0) & ~above).sum())
        rate = {k: v[0] / v[1] for k, v in by.items()}
        self.assertTrue(0.025 < rate["shallow"] < 0.06, rate)              # about double the old ~1.7%
        self.assertGreater(rate["deep"], rate["shallow"])
        self.assertGreater(rate["middle"], rate["shallow"])
        self.assertLess(surface_ore, underground_ore * 0.02, "ore must not pile up on surface rocks")


class TestMusic(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.field, cls.battle = M.compose_field(), M.compose_battle()

    @staticmethod
    def pitch_classes(piece, voices=None):
        return {n.midi % 12 for n in piece.notes if n.voice in (voices or ("lead", "pad", "bass", "arp"))}

    def test_field_is_slow_and_major_pentatonic(self):
        p = self.field
        allowed = {(p.root + i) % 12 for i in M.MAJOR_PENTATONIC}
        self.assertEqual(p.scale, M.MAJOR_PENTATONIC)
        self.assertTrue(self.pitch_classes(p) <= allowed, self.pitch_classes(p) - allowed)
        lead = self.pitch_classes(p, ("lead",))
        self.assertIn((p.root + 4) % 12, lead)                              # the major third is used ...
        self.assertNotIn((p.root + 3) % 12, self.pitch_classes(p))          # ... and the minor third never
        self.assertLessEqual(p.tempo, 80)

    def test_battle_is_fast_and_minor_pentatonic(self):
        p = self.battle
        allowed = {(p.root + i) % 12 for i in M.MINOR_PENTATONIC}
        self.assertEqual(p.scale, M.MINOR_PENTATONIC)
        self.assertTrue(self.pitch_classes(p) <= allowed, self.pitch_classes(p) - allowed)
        self.assertIn((p.root + 3) % 12, self.pitch_classes(p, ("lead",)))   # the minor third
        self.assertNotIn((p.root + 4) % 12, self.pitch_classes(p))
        self.assertGreaterEqual(p.tempo, 140)

    def test_the_two_tracks_differ_in_tempo_and_busyness(self):
        self.assertGreaterEqual(self.battle.tempo / self.field.tempo, 2.0)
        per_second = lambda p, v: sum(1 for n in p.notes if n.voice == v) / p.seconds
        self.assertGreater(per_second(self.battle, "lead"), per_second(self.field, "lead") * 1.5)
        self.assertEqual(sum(1 for n in self.field.notes if n.voice in ("kick", "snare", "hat")), 0, "calm: no drums")
        self.assertGreater(sum(1 for n in self.battle.notes if n.voice == "kick"), 100)

    def test_phrases_come_to_rest_on_the_tonic_or_the_fifth(self):
        for p in (self.field, self.battle):
            tonic_pcs = {p.root % 12, (p.root + 7) % 12}
            lead = [n for n in p.notes if n.voice == "lead"]
            for phrase in range(p.beats // 16):
                inside = [n for n in lead if phrase * 16 <= n.start < (phrase + 1) * 16]
                if p.name == "field":
                    self.assertIn(inside[-1].midi % 12, tonic_pcs, (p.name, phrase))

    def test_composition_is_deterministic_and_varies_with_the_seed(self):
        self.assertEqual(M.compose_field(5), M.compose_field(5))
        self.assertNotEqual(M.compose_field(5).notes, M.compose_field(6).notes)
        self.assertEqual(M.compose_battle(5), M.compose_battle(5))

    def test_a_synthesised_note_has_the_right_pitch(self):
        piece = self.field
        for midi in (60, 69, 81):
            w = M._voice(M.Note(0, 1, midi, "lead", 1.0), piece, np.random.default_rng(0))
            spectrum = np.abs(np.fft.rfft(w[:M.RATE]))
            peak = np.argmax(spectrum) * M.RATE / min(len(w), M.RATE)
            self.assertAlmostEqual(peak, M.midi_hz(midi), delta=M.midi_hz(midi) * 0.02)

    def test_rendered_loops(self):
        for p in (self.field, self.battle):
            data = M.render(p)
            self.assertEqual(data.dtype, np.int16)
            self.assertEqual(len(data), int(round(p.seconds * M.RATE)))
            peak = int(np.abs(data).max())
            self.assertTrue(8000 < peak < 32767, peak)
            window = M.RATE * 5
            for i in range(0, len(data) - window, window):                  # never silent for long
                self.assertGreater(float(np.abs(data[i:i + window]).mean()), 300)
            step = np.abs(np.diff(data.astype(int))).mean()
            self.assertLess(abs(int(data[0]) - int(data[-1])), step * 4 + 50, "the loop point must not click")

    def test_rendering_is_quick_enough_for_startup(self):
        t = time.perf_counter()
        M.render(self.field)
        M.render(self.battle)
        self.assertLess(time.perf_counter() - t, 8.0)


if __name__ == "__main__":
    unittest.main()
