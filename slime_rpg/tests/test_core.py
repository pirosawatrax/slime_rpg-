"""Engine-independent tests. Run from the project root:  python -m unittest discover -s tests -t ."""
import math
import tempfile
import time
import unittest
import wave
from pathlib import Path

import numpy as np

import config as C
from blocks import AIR, SOIL, GRASS, ROCK, WOOD, LEAF, WATER, BLOCKS
from audio import sfx
from game.building import try_place
from game.fog import fog_for_depth
from game.inventory import Inventory
from game.mining import Miner
from game.physics import Body
from game.raycast import raycast
from world.manager import ChunkManager
from world.mesher import mesh_section
from world.world import World
from world.worldgen import generate_chunk


def flat_world(ground_y=10, water_cols=()):
    """Test world: rock up to ground_y (grass on top); chosen (x, z) columns are 3 deep water instead."""
    def gen(seed, cx, cz):
        b = np.zeros((16, C.WORLD_HEIGHT, 16), np.uint8)
        b[:, :ground_y, :] = ROCK
        b[:, ground_y, :] = GRASS
        for (wx, wz) in water_cols:
            if wx >> 4 == cx and wz >> 4 == cz:
                lx, lz = wx & 15, wz & 15
                b[lx, ground_y - 2:ground_y + 1, lz] = WATER
        return b
    return World(generator=gen)


class TestWorldGen(unittest.TestCase):
    def test_deterministic_and_shaped(self):
        a = generate_chunk(C.SEED, 3, -2)
        b = generate_chunk(C.SEED, 3, -2)
        self.assertTrue((a == b).all())
        self.assertEqual(a.shape, (16, C.WORLD_HEIGHT, 16))
        self.assertTrue((a[:, 0, :] == ROCK).all())          # world floor
        self.assertNotEqual(generate_chunk(C.SEED + 1, 3, -2).tobytes(), a.tobytes())

    def test_chunk_generation_is_fast(self):
        t = time.perf_counter()
        for i in range(10):
            generate_chunk(C.SEED, i, i)
        per_chunk_ms = (time.perf_counter() - t) * 100
        self.assertLess(per_chunk_ms, 40)

    def test_terrain_has_all_materials_somewhere(self):
        seen = set()
        for cx in range(-6, 6):
            for cz in range(-6, 6):
                seen |= set(np.unique(generate_chunk(C.SEED, cx, cz)).tolist())
        self.assertTrue({AIR, SOIL, GRASS, ROCK, WOOD, LEAF}.issubset(seen))

    def test_water_exists_at_larger_scale(self):
        found = any((generate_chunk(C.SEED, cx, cz) == WATER).any()
                    for cx in range(-40, 40, 2) for cz in range(-40, 40, 2))
        self.assertTrue(found)


class TestWorldEdits(unittest.TestCase):
    def test_break_and_negative_coordinates(self):
        w = flat_world()
        w.set_block(-1, 5, -17, AIR)
        self.assertEqual(w.get_block(-1, 5, -17), AIR)
        self.assertEqual(w.get_block(-1, 6, -17), ROCK)

    def test_bridge_reverts_to_water(self):
        w = flat_world(water_cols=[(2, 2)])
        self.assertEqual(w.get_block(2, 10, 2), WATER)
        w.set_block(2, 10, 2, WOOD)                 # bridge block
        self.assertEqual(w.get_block(2, 10, 2), WOOD)
        w.remove_block(2, 10, 2)
        self.assertEqual(w.get_block(2, 10, 2), WATER)
        self.assertEqual(w.chunks[(0, 0)].edits, {})    # back to the generated state: no diff left
        w.remove_block(5, 10, 5)                         # ordinary block -> air
        self.assertEqual(w.get_block(5, 10, 5), AIR)

    def test_border_edit_marks_neighbour_sections_dirty(self):
        w = flat_world()
        w.get_chunk(0, 0); w.get_chunk(1, 0)
        w.pop_dirty()
        w.set_block(15, 15, 3, AIR)
        d = w.pop_dirty()
        self.assertTrue({(0, 0, 0), (1, 0, 0), (0, 0, 1)}.issubset(d))


class TestMesher(unittest.TestCase):
    def _mesh_single(self, cells):
        w = flat_world(ground_y=1)
        for c in cells:
            w.set_block(*c, ROCK)
        w.get_chunk(0, 0)
        return mesh_section(w.padded(0, 0), 0)

    def test_lone_block_has_six_faces_and_ground_hides_bottom(self):
        w = World(generator=lambda s, cx, cz: np.zeros((16, 64, 16), np.uint8))
        w.set_block(5, 5, 5, ROCK)
        v, t, c = mesh_section(w.padded(0, 0), 0)
        self.assertEqual(len(v), 24)
        self.assertEqual(len(t), 36)
        self.assertEqual(c.shape, (24, 4))
        self.assertTrue(t.max() < len(v))

    def test_adjacent_blocks_hide_shared_faces(self):
        w = World(generator=lambda s, cx, cz: np.zeros((16, 64, 16), np.uint8))
        w.set_block(5, 5, 5, ROCK)
        w.set_block(6, 5, 5, ROCK)
        v, t, c = mesh_section(w.padded(0, 0), 0)
        self.assertEqual(len(v), 10 * 4)       # 12 faces minus the 2 touching ones

    def test_empty_section_returns_none(self):
        w = World(generator=lambda s, cx, cz: np.zeros((16, 64, 16), np.uint8))
        w.get_chunk(0, 0)
        self.assertIsNone(mesh_section(w.padded(0, 0), 2))

    def test_no_faces_between_neighbouring_chunks(self):
        w = flat_world(ground_y=4)
        w.get_chunk(0, 0); w.get_chunk(1, 0); w.get_chunk(-1, 0); w.get_chunk(0, 1); w.get_chunk(0, -1)
        v, t, c = mesh_section(w.padded(0, 0), 0)
        # Flat ground: only the 16x16 top faces are visible (sides and bottom are buried).
        self.assertEqual(len(v), 256 * 4)

    def test_real_terrain_meshes_quickly(self):
        w = World()
        for dx in (-1, 0, 1):
            for dz in (-1, 0, 1):
                w.get_chunk(dx, dz)
        t0 = time.perf_counter()
        out = [mesh_section(w.padded(0, 0), s) for s in range(4)]
        ms = (time.perf_counter() - t0) * 1000
        self.assertTrue(any(o is not None for o in out))
        self.assertLess(ms, 60)


class TestManager(unittest.TestCase):
    def test_one_task_per_step_and_converges(self):
        w = World()
        built = {}
        m = ChunkManager(w, lambda k, d: built.__setitem__(k, d), lambda cx, cz: None)
        tasks = 0
        while True:
            r = m.step(0, 0)
            if r is None:
                break
            tasks += 1
            self.assertLess(tasks, 500)
        self.assertIn((0, 0), m.meshed)
        self.assertIn((C.RENDER_RADIUS, 0), m.meshed)
        self.assertNotIn((C.RENDER_RADIUS + 1, 0), m.meshed)
        self.assertTrue(w.has_chunk(C.DATA_RADIUS, 0))

    def test_edit_remeshes_immediately(self):
        w = flat_world()
        events = []
        m = ChunkManager(w, lambda k, d: events.append(k), lambda cx, cz: None)
        while m.step(0, 0):
            pass
        events.clear()
        w.set_block(3, 10, 3, AIR)
        m.step(0, 0)
        self.assertIn((0, 0, 0), events)

    def test_moving_unloads_far_chunks(self):
        w = flat_world()
        unloaded = []
        m = ChunkManager(w, lambda k, d: None, lambda cx, cz: unloaded.append((cx, cz)))
        while m.step(0, 0):
            pass
        m.step(20, 0)
        self.assertIn((0, 0), unloaded)


class TestInventory(unittest.TestCase):
    def test_stacking_and_limits(self):
        inv = Inventory()
        self.assertEqual(inv.add(ROCK, 100), 0)                 # 64 + 36 -> two slots
        self.assertEqual(inv.used_slots(), 2)
        self.assertEqual(inv.count(ROCK), 100)
        self.assertEqual(inv.add(WOOD, 40), 0)                  # wood stacks to 32
        self.assertEqual(inv.used_slots(), 4)

    def test_full_inventory_loses_items(self):
        inv = Inventory(2)
        inv.add(ROCK, 64); inv.add(SOIL, 64)
        self.assertTrue(inv.is_full())
        self.assertEqual(inv.add(WOOD, 1), 1)                   # no room -> lost
        self.assertEqual(inv.add(ROCK, 1), 1)                   # stack already at its limit
        inv.take(0, 1)
        self.assertEqual(inv.add(ROCK, 1), 0)                   # stack with room still accepts

    def test_take_empties_slot(self):
        inv = Inventory()
        inv.add(LEAF, 1)
        self.assertEqual(inv.take(0), LEAF)
        self.assertIsNone(inv.slots[0])
        self.assertIsNone(inv.take(0))


class TestMining(unittest.TestCase):
    def setUp(self):
        self.w = flat_world()
        self.inv = Inventory()
        self.miner = Miner(self.w, self.inv)

    def hold(self, target, seconds, dt=1 / 60):
        results = []
        for _ in range(int(round(seconds / dt))):
            results.append(self.miner.update(dt, True, target))
        return results

    def test_takes_hardness_time_to_break(self):
        target = (3, 9, 3)                                       # rock, 2.0 s
        r = self.hold(target, 1.5)
        self.assertFalse(any(x.broke for x in r))
        self.assertAlmostEqual(r[-1].progress, 0.75, delta=0.02)
        r = self.hold(target, 0.6)
        self.assertTrue(any(x.broke for x in r))
        self.assertEqual(self.w.get_block(*target), AIR)
        self.assertEqual(self.inv.count(ROCK), 1)

    def test_grass_gives_soil_and_is_faster(self):
        r = self.hold((3, 10, 3), 0.7)
        self.assertTrue(any(x.broke for x in r))
        self.assertEqual(self.inv.count(SOIL), 1)

    def test_release_or_retarget_resets_progress(self):
        self.hold((3, 9, 3), 1.0)
        self.assertGreater(self.miner.progress, 0.4)
        self.miner.update(1 / 60, False, (3, 9, 3))
        self.assertEqual(self.miner.progress, 0.0)
        self.hold((3, 9, 3), 0.5)
        r = self.miner.update(1 / 60, True, (4, 9, 3))
        self.assertLess(r.progress, 0.05)

    def test_hit_ticks_repeat_while_holding(self):
        r = self.hold((3, 9, 3), 1.0)
        ticks = sum(x.tick for x in r)
        self.assertTrue(3 <= ticks <= 5, ticks)

    def test_unbreakable_water_and_floor(self):
        w = flat_world(water_cols=[(2, 2)])
        m = Miner(w, Inventory())
        for _ in range(300):
            res = m.update(1 / 60, True, (2, 10, 2))
        self.assertFalse(res.broke)
        self.assertEqual(w.get_block(2, 10, 2), WATER)
        for _ in range(600):
            res = m.update(1 / 60, True, (3, 0, 3))
        self.assertEqual(w.get_block(3, 0, 3), ROCK)

    def test_full_inventory_still_breaks_but_loses_drop(self):
        self.inv = Inventory(1)
        self.inv.add(WOOD, 32)
        miner = Miner(self.w, self.inv)
        out = []
        for _ in range(200):
            out.append(miner.update(1 / 60, True, (3, 9, 3)))
        done = [x for x in out if x.broke][0]
        self.assertEqual(done.lost, [(ROCK, 1)])
        self.assertEqual(done.gained, [])
        self.assertEqual(self.w.get_block(3, 9, 3), AIR)         # block gone anyway
        self.assertEqual(self.inv.count(ROCK), 0)


class TestPhysicsAndPlacing(unittest.TestCase):
    def test_lands_walks_and_is_stopped_by_wall(self):
        w = flat_world(ground_y=10)
        for y in range(11, 14):
            w.set_block(8, y, 3, ROCK)
        b = Body(w, 3.5, 14.0, 3.5)
        for _ in range(120):
            b.update(1 / 60, 0, 0, False)
        self.assertTrue(b.on_ground)
        self.assertAlmostEqual(b.y, 11.0, delta=0.01)
        for _ in range(240):
            b.update(1 / 60, C.MOVE_SPEED, 0, False)
        self.assertLess(b.x, 8 - b.hw + 0.01)
        self.assertGreater(b.x, 7.0)

    def test_jump_clears_one_block_but_not_two(self):
        w = flat_world(ground_y=10)
        w.set_block(6, 11, 3, ROCK)
        b = Body(w, 4.5, 11.0, 3.5)
        b.update(1 / 60, 0, 0, False)
        for i in range(120):
            b.update(1 / 60, C.MOVE_SPEED * 0.5, 0, jump=(i == 5))
        self.assertGreater(b.x, 6.5)
        w2 = flat_world(ground_y=10)
        w2.set_block(6, 11, 3, ROCK); w2.set_block(6, 12, 3, ROCK)
        b2 = Body(w2, 4.5, 11.0, 3.5)
        b2.update(1 / 60, 0, 0, False)
        for i in range(120):
            b2.update(1 / 60, C.MOVE_SPEED * 0.5, 0, jump=(i % 30 == 5))
        self.assertLess(b2.x, 6.0)

    def test_cannot_walk_onto_water_but_can_cross_a_bridge(self):
        cols = [(8, 3), (9, 3), (10, 3)]
        w = flat_world(ground_y=10, water_cols=cols)
        b = Body(w, 5.5, 11.0, 3.5)
        for i in range(300):
            b.update(1 / 60, C.MOVE_SPEED, 0, jump=(i % 40 == 5))
        self.assertLess(b.x, 8.0)                                # blocked at the water edge, even jumping
        for (x, z) in cols:
            w.set_block(x, 10, z, WOOD)                          # build the bridge
        b = Body(w, 5.5, 11.0, 3.5)
        for i in range(300):
            b.update(1 / 60, C.MOVE_SPEED, 0, False)
        self.assertGreater(b.x, 11.0)                            # crossed to the far side

    def test_raycast_hits_and_reports_previous_cell(self):
        w = flat_world(ground_y=10)
        hit = raycast(w.get_block, (3.5, 12.5, 3.5), (0, -1, 0), 6)
        self.assertEqual(hit.cell, (3, 10, 3))
        self.assertEqual(hit.prev, (3, 11, 3))
        self.assertIsNone(raycast(w.get_block, (3.5, 12.5, 3.5), (0, 1, 0), 6))
        hit = raycast(w.get_block, (3.5, 11.5, 3.5), (1, -0.001, 0), 10)   # sideways along the ground: no hit
        self.assertIsNone(hit)
        w.set_block(7, 11, 3, ROCK)
        hit = raycast(w.get_block, (3.5, 11.5, 3.5), (1, 0, 0), 10)
        self.assertEqual((hit.cell, hit.prev), ((7, 11, 3), (6, 11, 3)))

    def test_place_rules(self):
        w = flat_world(ground_y=10, water_cols=[(8, 3)])
        inv = Inventory()
        inv.add(ROCK, 2); inv.add(WOOD, 2)
        body = Body(w, 3.5, 11.0, 3.5)
        far = raycast(w.get_block, (6.5, 13.5, 6.5), (0, -1, 0), 6)
        self.assertTrue(try_place(w, inv, 0, far, body).placed)           # rock onto ground
        self.assertEqual(w.get_block(6, 11, 6), ROCK)
        self.assertEqual(inv.count(ROCK), 1)
        water = raycast(w.get_block, (8.5, 13.5, 3.5), (0, -1, 0), 6)
        self.assertFalse(try_place(w, inv, 0, water, body).placed)        # rock cannot go on water
        self.assertTrue(try_place(w, inv, 1, water, body).placed)         # wood can: bridge
        self.assertEqual(w.get_block(8, 10, 3), WOOD)
        under_feet = raycast(w.get_block, (3.5, 13.5, 3.5), (0, -1, 0), 6)
        self.assertFalse(try_place(w, inv, 0, under_feet, body).placed)   # would trap the player


class TestFogAndAudio(unittest.TestCase):
    def test_fog_gets_darker_and_tighter_with_depth(self):
        (c0, n0, f0), (c1, n1, f1) = fog_for_depth(0), fog_for_depth(C.FOG_FULL_DARK_DEPTH)
        self.assertLess(sum(c1), sum(c0))
        self.assertLess(f1, f0)
        self.assertEqual(fog_for_depth(-50), fog_for_depth(0))

    def test_sound_files_are_written(self):
        with tempfile.TemporaryDirectory() as d:
            sfx.write_all(d)
            names = {p.stem for p in Path(d).glob("*.wav")}
            for fam in sfx.FAMILIES:
                self.assertIn(f"hit_{fam}", names)
                self.assertIn(f"break_{fam}", names)
            self.assertTrue({"place", "full"}.issubset(names))
            with wave.open(str(Path(d) / "hit_rock.wav")) as f:
                self.assertEqual(f.getnchannels(), 1)
                self.assertGreater(f.getnframes(), 500)
            rendered = sfx.render_all()
            self.assertTrue(all(np.abs(v).max() > 1000 for v in rendered.values()))


if __name__ == "__main__":
    unittest.main()
