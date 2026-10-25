"""Save/load tests (engine-free)."""
import json
import tempfile
import unittest
from pathlib import Path

import config as C
from blocks import AIR, SOIL, ROCK, WOOD, LEAF, WATER
from game.inventory import Inventory
from save import game_save
from save.store import SaveStore, SaveError
from tests.test_core import flat_world
from world.world import World


def make(tmp, **kw):
    store = SaveStore(Path(tmp) / "world")
    return store, flat_world(**kw)


def attach(world, store):
    world.store = store
    return world


class TestRoundTrip(unittest.TestCase):
    def test_edits_survive_a_reload(self):
        with tempfile.TemporaryDirectory() as tmp:
            store, w = make(tmp, water_cols=[(2, 2)])
            attach(w, store)
            w.set_block(3, 9, 3, AIR)            # dug
            w.set_block(2, 10, 2, WOOD)          # bridge on water
            w.set_block(-5, 10, 20, LEAF)        # negative coords, other chunk
            inv = Inventory(); inv.add(ROCK, 70)
            n = game_save.save_game(store, w, inv, dict(x=1, y=2, z=3, yaw=4, pitch=5, selected=2), (0.5, 11, 0.5))
            self.assertEqual(n, 2)
            self.assertTrue(all(not ch.modified for ch in w.chunks.values()))

            w2 = attach(flat_world(water_cols=[(2, 2)]), SaveStore(store.dir))
            self.assertEqual(w2.get_block(3, 9, 3), AIR)
            self.assertEqual(w2.get_block(2, 10, 2), WOOD)
            self.assertEqual(w2.get_block(-5, 10, 20), LEAF)
            self.assertEqual(w2.get_block(4, 9, 4), ROCK)           # untouched
            w2.remove_block(2, 10, 2)                               # bridge still knows the water beneath
            self.assertEqual(w2.get_block(2, 10, 2), WATER)

    def test_only_modified_chunks_are_written_and_loading_is_lazy(self):
        with tempfile.TemporaryDirectory() as tmp:
            store, w = make(tmp)
            attach(w, store)
            w.set_block(1, 9, 1, AIR)
            w.get_chunk(5, 5)                                       # generated but never edited
            game_save.save_game(store, w, Inventory(), {}, (0, 0, 0))
            files = sorted(p.name for p in (store.dir / "chunks").glob("*.json"))
            self.assertEqual(files, ["c_0_0.json"])
            m1 = (store.dir / "chunks" / "c_0_0.json").stat().st_mtime_ns
            game_save.save_game(store, w, Inventory(), {}, (0, 0, 0))   # nothing changed
            self.assertEqual((store.dir / "chunks" / "c_0_0.json").stat().st_mtime_ns, m1)

    def test_reverting_an_edit_removes_its_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            store, w = make(tmp, water_cols=[(2, 2)])
            attach(w, store)
            w.set_block(2, 10, 2, WOOD)
            game_save.save_game(store, w, Inventory(), {}, (0, 0, 0))
            self.assertTrue((store.dir / "chunks" / "c_0_0.json").exists())
            w.remove_block(2, 10, 2)                                # back to water = generated state
            game_save.save_game(store, w, Inventory(), {}, (0, 0, 0))
            self.assertFalse((store.dir / "chunks" / "c_0_0.json").exists())

    def test_saved_chunks_can_be_unloaded_and_come_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            store, w = make(tmp)
            attach(w, store)
            w.set_block(1, 9, 1, AIR)
            w.unload(0, 0)
            self.assertTrue(w.has_chunk(0, 0), "unsaved edits must never be dropped")
            game_save.save_game(store, w, Inventory(), {}, (0, 0, 0))
            w.unload(0, 0)
            self.assertFalse(w.has_chunk(0, 0))
            self.assertEqual(w.get_block(1, 9, 1), AIR)             # reloaded from disk

    def test_no_temp_files_left_behind(self):
        with tempfile.TemporaryDirectory() as tmp:
            store, w = make(tmp)
            attach(w, store)
            w.set_block(1, 9, 1, AIR)
            game_save.save_game(store, w, Inventory(), {}, (0, 0, 0))
            self.assertEqual(list(store.dir.rglob("*.tmp")), [])


class TestMetaAndValidation(unittest.TestCase):
    def test_meta_roundtrip_and_inventory(self):
        with tempfile.TemporaryDirectory() as tmp:
            store, w = make(tmp)
            inv = Inventory(); inv.add(ROCK, 70); inv.add(WOOD, 3); inv.take(0, 1)
            player = dict(x=1.5, y=40.0, z=-2.5, yaw=90.0, pitch=-10.0, selected=3)
            game_save.save_game(store, w, inv, player, (0.5, 39.0, 0.5))
            meta = SaveStore(store.dir).load_meta()
            self.assertEqual(meta["seed"], w.seed)
            inv2 = game_save.restore_inventory(meta["inventory"])
            self.assertEqual([s for s in inv2.slots], [s for s in inv.slots])
            self.assertEqual(game_save.restore_player(meta, (0, 0, 0)), (1.5, 40.0, -2.5, 90.0, -10.0, 3))
            self.assertEqual(game_save.restore_spawn(meta, None), (0.5, 39.0, 0.5))

    def test_bad_inventory_rows_are_dropped_not_fatal(self):
        rows = [[ROCK, 9999], [99, 1], "junk", [WOOD, -4], None, [SOIL, 2, 3], [WATER, 1], [LEAF, 5]]
        inv = game_save.restore_inventory(rows)
        self.assertEqual(inv.slots[0], [ROCK, 64])               # clamped to the stack limit
        self.assertIsNone(inv.slots[1]); self.assertIsNone(inv.slots[2])
        self.assertEqual(inv.slots[3], [WOOD, 1])
        self.assertIsNone(inv.slots[5]); self.assertIsNone(inv.slots[6])    # bad row / water is not an item
        self.assertEqual(inv.slots[7], [LEAF, 5])
        self.assertEqual(len(inv.slots), C.INVENTORY_SLOTS)
        self.assertEqual(len(game_save.restore_inventory("nonsense").slots), C.INVENTORY_SLOTS)

    def test_bad_player_values_fall_back(self):
        meta = {"player": {"x": "a", "y": 1e99, "z": float("nan"), "yaw": 5, "pitch": 500, "selected": 99}}
        x, y, z, yaw, pitch, sel = game_save.restore_player(meta, (7.0, 8.0, 9.0))
        self.assertEqual((x, y, z), (7.0, 8.0, 9.0))
        self.assertEqual((yaw, pitch, sel), (5.0, 0.0, 0))
        self.assertEqual(game_save.restore_spawn({"spawn": [1, 2]}, "dflt"), "dflt")

    def test_corrupt_and_newer_saves(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = SaveStore(Path(tmp) / "w")
            store.dir.mkdir()
            (store.dir / "meta.json").write_text("{not json")
            with self.assertRaises(SaveError) as cm:
                store.load_meta()
            self.assertEqual(cm.exception.kind, "corrupt")
            (store.dir / "meta.json").write_text(json.dumps({"save_version": C.SAVE_VERSION + 1, "seed": 1}))
            with self.assertRaises(SaveError) as cm:
                store.load_meta()
            self.assertEqual(cm.exception.kind, "too_new")
            (store.dir / "meta.json").write_text(json.dumps({"save_version": 1}))
            with self.assertRaises(SaveError):
                store.load_meta()                                  # no seed

    def test_corrupt_chunk_file_is_skipped_and_set_aside(self):
        with tempfile.TemporaryDirectory() as tmp:
            store, w = make(tmp)
            (store.dir / "chunks").mkdir(parents=True)
            (store.dir / "chunks" / "c_0_0.json").write_text("oops")
            attach(w, store)
            self.assertEqual(w.get_block(1, 9, 1), ROCK)           # world still loads, terrain only
            self.assertTrue(store.warnings)
            self.assertTrue((store.dir / "chunks" / "c_0_0.json.corrupt").exists())

    def test_invalid_edit_rows_are_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            store, w = make(tmp)
            (store.dir / "chunks").mkdir(parents=True)
            rows = [[1, 9, 1, 0], [99, 9, 1, 0], [1, 999, 1, 0], [1, 9, 1, 77], [1, 9], "x", [2, 9, 2, 0]]
            (store.dir / "chunks" / "c_0_0.json").write_text(json.dumps({"v": 1, "edits": rows}))
            edits = store.load_chunk_edits(0, 0)
            self.assertEqual(edits, {(1, 9, 1): 0, (2, 9, 2): 0})

    def test_archive_moves_instead_of_deleting(self):
        with tempfile.TemporaryDirectory() as tmp:
            store, w = make(tmp)
            game_save.save_game(store, w, Inventory(), {}, (0, 0, 0))
            moved = store.archive("old")
            self.assertTrue((moved / "meta.json").exists())
            self.assertFalse(store.exists())


if __name__ == "__main__":
    unittest.main()
