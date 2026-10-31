"""Custom block MOD loading, registration, item handling and mesh colours."""
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import blocks
import items
from mods.loader import load_mods
from world.mesher import mesh_section
from save.store import SaveStore
from save.game_save import restore_inventory, _saved_item_id


class TestModBlocks(unittest.TestCase):
    def make_mod(self, root, blocks_data, *, slimes_file=False):
        folder = Path(root) / "stone_pack"
        folder.mkdir()
        (folder / "mod.json").write_text(json.dumps({
            "id": "stone_pack", "name": "Stone Pack", "api_version": 1
        }), encoding="utf-8")
        (folder / "blocks.json").write_text(json.dumps(blocks_data), encoding="utf-8")
        if slimes_file:
            (folder / "slimes.json").write_text("[]", encoding="utf-8")
        return folder

    def test_block_only_mod_loads_without_slimes_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.make_mod(tmp, [{"id": "granite", "name": "Granite", "color": [100, 110, 120]}])
            result = load_mods(tmp)
        self.assertEqual(result.errors, [])
        self.assertEqual(len(result.blocks), 1)
        self.assertEqual(result.blocks[0]["id"], "granite")
        self.assertEqual(result.blocks[0]["top"], tuple(v / 255 for v in (100, 110, 120)))
        self.assertEqual(result.loaded[0]["block_count"], 1)

    def test_bad_block_skips_only_that_mod(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.make_mod(tmp, [{"id": "bad", "name": "Bad", "hardness": 0}])
            result = load_mods(tmp)
        self.assertEqual(result.blocks, [])
        self.assertEqual(len(result.errors), 1)

    def test_register_block_integrates_with_items_and_mesher(self):
        block_id = blocks.register_mod_block(
            "test_pack", "test_slate", "Test Slate", 2.5, 32, "rock",
            (0.2, 0.3, 0.4), (0.15, 0.25, 0.35), (0.1, 0.2, 0.3), True)
        self.assertGreaterEqual(block_id, blocks.BASE_BLOCK_COUNT)
        self.assertIn(block_id, blocks.BLOCKS)
        self.assertIn(block_id, blocks.PLACEABLE)
        self.assertTrue(items.is_valid_item(block_id))
        self.assertEqual(items.stack_limit(block_id), 32)
        self.assertEqual(blocks.drop_of(block_id), block_id)
        self.assertEqual(blocks.hardness_at(block_id, 4), 2.5)
        self.assertTrue(np.allclose(__import__("world.mesher", fromlist=["_COLOR_TABLE"])._COLOR_TABLE[block_id, 1],
                                    (0.15, 0.25, 0.35)))
        padded = np.full((18, 66, 18), blocks.AIR, dtype=np.uint8)
        padded[1, 2, 1] = block_id
        mesh = mesh_section(padded, 0)
        self.assertIsNotNone(mesh)
        self.assertTrue(np.all(np.isfinite(mesh[2])))


    def test_custom_block_save_uses_namespaced_key(self):
        block_id = blocks.register_mod_block(
            "save_pack", "save_stone", "Save Stone", 1.5, 24, "rock",
            (0.4, 0.4, 0.4), (0.3, 0.3, 0.3), (0.2, 0.2, 0.2), True)
        self.assertEqual(_saved_item_id(block_id), "save_pack:save_stone")
        inv = restore_inventory([["save_pack:save_stone", 3]])
        self.assertEqual(inv.slots[0], [block_id, 3])
        with tempfile.TemporaryDirectory() as tmp:
            store = SaveStore(tmp)
            store.save_chunk_edits(0, 0, {(1, 2, 3): block_id})
            raw = json.loads((Path(tmp) / "chunks" / "c_0_0.json").read_text())
            self.assertEqual(raw["edits"][0][3], "save_pack:save_stone")
            self.assertEqual(store.load_chunk_edits(0, 0), {(1, 2, 3): block_id})

    def test_non_placeable_block_has_no_drop_item(self):
        block_id = blocks.register_mod_block(
            "test_pack", "unplaceable", "Unplaceable", 1.0, 16, "rock",
            (0.4, 0.4, 0.4), (0.3, 0.3, 0.3), (0.2, 0.2, 0.2), False)
        self.assertNotIn(block_id, blocks.PLACEABLE)
        self.assertIsNone(blocks.drop_of(block_id))


if __name__ == "__main__":
    unittest.main()
