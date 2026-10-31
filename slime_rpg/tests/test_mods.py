import json
import tempfile
import unittest
from pathlib import Path

from mods.loader import load_mods
from game.battle import make_enemy
from game import progression


class TestModLoader(unittest.TestCase):
    def test_sample_mod_loads_and_defines_crystal_slime(self):
        mods_dir = Path(__file__).resolve().parents[1] / "mods"
        result = load_mods(mods_dir)
        self.assertEqual([m["id"] for m in result.loaded],
                         ["common_rocks", "crystal_slime_pack", "sandstone_colors", "snow_biome", "tree_species"])
        self.assertEqual(result.errors, [])
        self.assertEqual(len(result.slimes), 1)
        self.assertEqual(result.slimes[0]["name"], "Crystal Slime")
        self.assertEqual(result.slimes[0]["color_min"], (140.0, 140.0, 180.0))

    def test_bad_mod_is_skipped_without_blocking_other_mods(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bad = root / "bad"
            bad.mkdir()
            (bad / "mod.json").write_text(json.dumps({
                "id": "bad", "name": "Bad", "api_version": 1
            }), encoding="utf-8")
            (bad / "slimes.json").write_text("not json", encoding="utf-8")
            result = load_mods(root)
            self.assertEqual(result.loaded, [])
            self.assertEqual(len(result.errors), 1)

    def test_mod_slime_can_be_selected_for_a_battle(self):
        class PickLast:
            def uniform(self, lo, hi):
                return (lo + hi) / 2
            def randrange(self, stop):
                return stop - 1

        mods_dir = Path(__file__).resolve().parents[1] / "mods"
        result = load_mods(mods_dir)
        enemy = make_enemy(5, PickLast(), mod_slimes=result.slimes)
        self.assertEqual(enemy.name, "Crystal Slime")
        self.assertGreater(enemy.max_hp, progression.average_stats(5)["hp"])
        self.assertGreaterEqual(enemy.color[0], 140)
        self.assertGreaterEqual(enemy.color[1], 140)
        self.assertGreaterEqual(enemy.color[2], 180)

    def test_disabled_mod_is_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "off"
            folder.mkdir()
            (folder / "mod.json").write_text(json.dumps({
                "id": "off", "name": "Off", "api_version": 1, "enabled": False
            }), encoding="utf-8")
            (folder / "slimes.json").write_text("[]", encoding="utf-8")
            result = load_mods(tmp)
            self.assertEqual(result.loaded, [])
            self.assertEqual(result.errors, [])


if __name__ == "__main__":
    unittest.main()
