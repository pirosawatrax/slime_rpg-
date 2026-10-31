"""Regression tests for the included natural-material block packs."""
import unittest
from pathlib import Path

import blocks
import items
import config as C
import numpy as np
from mods.loader import load_mods
from world.worldgen import generate_chunk
from game.building import try_place
from game.inventory import Inventory
from game.raycast import Hit


class DummyWorld:
    def __init__(self, hit_block):
        self.hit_block = hit_block
        self.placed = {}

    def get_block(self, x, y, z):
        return self.placed.get((x, y, z), 0)

    def set_block(self, x, y, z, block):
        self.placed[(x, y, z)] = block


class DummyBody:
    def overlaps_cell(self, x, y, z):
        return False


class TestNaturalMaterialMods(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[1] / "mods"
        cls.loaded = load_mods(cls.root)
        cls.runtime = {}
        for row in cls.loaded.blocks:
            cls.runtime[f"{row['mod_id']}:{row['id']}"] = blocks.register_mod_block(
                row["mod_id"], row["id"], row["name"], row["hardness"],
                row["stack_limit"], row["sound"], row["top"], row["side"],
                row["bottom"], row["placeable"])

    def test_both_sample_mods_load(self):
        self.assertEqual(self.loaded.errors, [])
        self.assertIn("sandstone_colors", {m["id"] for m in self.loaded.loaded})
        self.assertIn("tree_species", {m["id"] for m in self.loaded.loaded})
        self.assertIn("common_rocks", {m["id"] for m in self.loaded.loaded})
        self.assertIn("snow_biome", {m["id"] for m in self.loaded.loaded})

    def test_four_sandstone_variants_are_registered(self):
        for key in ("sandstone_colors:yellow_sandstone", "sandstone_colors:red_sandstone",
                    "sandstone_colors:white_sandstone", "sandstone_colors:gray_sandstone"):
            self.assertIn(key, self.runtime)
            self.assertIn(self.runtime[key], blocks.PLACEABLE)
            self.assertTrue(items.is_valid_item(self.runtime[key]))

    def test_sandstone_side_faces_have_horizontal_strata_pattern(self):
        from world.mesher import mesh_section
        yellow = self.runtime["sandstone_colors:yellow_sandstone"]
        padded = np.full((18, 66, 18), blocks.AIR, dtype=np.uint8)
        padded[2, 2, 2] = yellow
        vertices, triangles, colors = mesh_section(padded, 0)
        # A plain cube has 6 quads (24 vertices). Four side faces are each
        # split into seven sediment bands, while top and bottom stay solid.
        self.assertEqual(len(vertices), (4 * 7 + 2) * 4)
        side_colors = colors.reshape(-1, 4)[:4 * 7 * 4, :3]
        self.assertGreater(len(np.unique(np.round(side_colors, 4), axis=0)), 4)
        self.assertTrue(np.all(np.isfinite(vertices)))
        self.assertTrue(np.all(np.isfinite(triangles)))

    def test_four_common_rocks_are_registered_and_visually_distinct(self):
        names = ("granite", "basalt", "limestone", "red_rock")
        colors = []
        for name in names:
            block_id = self.runtime[f"common_rocks:{name}"]
            info = blocks.BLOCKS[block_id]
            self.assertEqual(info.sound, "rock")
            self.assertIn(block_id, blocks.PLACEABLE)
            self.assertTrue(items.is_valid_item(block_id))
            colors.append(np.array(info.side))
        # The side-face palette must not collapse to near-identical gray shades.
        for i in range(len(colors)):
            for j in range(i + 1, len(colors)):
                self.assertGreater(float(np.linalg.norm(colors[i] - colors[j])), 0.16)

    def test_four_common_rocks_generate_naturally_without_minerals(self):
        # The geological palette is intentionally local, so verify a small
        # exploration area around spawn rather than hard-coding distant chunks.
        generate = __import__("world.worldgen", fromlist=["generate_chunk_full"]).generate_chunk_full
        found = {name: False for name in ("granite", "basalt", "limestone", "red_rock")}
        common_ids = [self.runtime[f"common_rocks:{name}"] for name in found]
        ordinary_rock_cells = 0
        variant_rock_cells = 0
        for radius in range(5):
            for cx in range(-radius, radius + 1):
                for cz in range(-radius, radius + 1):
                    if max(abs(cx), abs(cz)) != radius:
                        continue
                    chunk, minerals = generate(12345, cx, cz)
                    ordinary_rock_cells += int(np.count_nonzero(chunk == blocks.ROCK))
                    variant_rock_cells += int(np.count_nonzero(np.isin(chunk, common_ids)))
                    for name in found:
                        block_id = self.runtime[f"common_rocks:{name}"]
                        if np.any(chunk == block_id):
                            found[name] = True
                            self.assertTrue(np.all(minerals[chunk == block_id] == 0))
        self.assertTrue(all(found.values()), found)
        total_stone = ordinary_rock_cells + variant_rock_cells
        self.assertGreater(total_stone, 0)
        # At least 80% of ordinary underground stone remains the mineral-host ROCK.
        self.assertGreaterEqual(ordinary_rock_cells / total_stone, 0.80)

    def test_three_tree_species_have_log_and_leaves(self):
        for species in ("birch", "pine", "darkwood"):
            log = self.runtime[f"tree_species:{species}_log"]
            leaves = self.runtime[f"tree_species:{species}_leaves"]
            self.assertEqual(blocks.BLOCKS[log].sound, "wood")
            self.assertEqual(blocks.BLOCKS[leaves].sound, "leaf")
            self.assertIn(log, blocks.PLACEABLE)
            self.assertIn(leaves, blocks.PLACEABLE)

    def test_sandstone_generates_in_desert_regions(self):
        chunk = generate_chunk(1, -4, 5)
        sandstone = [self.runtime[f"sandstone_colors:{name}_sandstone"]
                     for name in ("yellow", "red", "white", "gray")]
        self.assertTrue(any(np.any(chunk == block_id) for block_id in sandstone))

    def test_all_tree_species_generate_naturally(self):
        # These seed-1 chunks lie in the three deterministic climate regions.
        samples = ((-5, 0, "birch"), (2, 0, "pine"), (-4, 5, "darkwood"))
        for cx, cz, species in samples:
            with self.subTest(species=species):
                chunk = generate_chunk(1, cx, cz)
                log = self.runtime[f"tree_species:{species}_log"]
                self.assertTrue(np.any(chunk == log))


    def test_snow_biome_blocks_are_registered_and_generate_in_cold_regions(self):
        snow = self.runtime["snow_biome:snow"]
        ice = self.runtime["snow_biome:ice"]
        for block_id in (snow, ice):
            self.assertIn(block_id, blocks.PLACEABLE)
            self.assertTrue(items.is_valid_item(block_id))
            self.assertGreater(blocks.hardness_at(block_id, 10), 0)

        generate = __import__("world.worldgen", fromlist=["generate_chunk_full"]).generate_chunk_full
        # Fixed seed 12345 has a cold land patch and a frozen lake in these neighbouring chunks.
        snowy, snowy_ore = generate(12345, -8, 10)
        icy, icy_ore = generate(12345, -7, 10)
        self.assertGreater(int(np.count_nonzero(snowy == snow)), 0)
        self.assertGreater(int(np.count_nonzero(icy == ice)), 0)
        self.assertTrue(np.all(snowy_ore[snowy == snow] == 0))
        self.assertTrue(np.all(icy_ore[icy == ice] == 0))
        ice_cells = np.argwhere(icy == ice)
        self.assertTrue(np.all(ice_cells[:, 1] == C.SEA_LEVEL))
        below_ice = [int(icy[x, y - 1, z]) for x, y, z in ice_cells]
        self.assertTrue(all(v in (blocks.WATER, blocks.SOIL) for v in below_ice))
        self.assertIn(blocks.WATER, below_ice)
        # The same chunk remains deterministic, including the climate overlay.
        again, _ = generate(12345, -8, 10)
        np.testing.assert_array_equal(snowy, again)

    def test_generation_is_deterministic(self):
        a = generate_chunk(314159, 2, -3)
        b = generate_chunk(314159, 2, -3)
        np.testing.assert_array_equal(a, b)

    def test_mod_wood_can_be_placed_as_water_bridge(self):
        log = self.runtime["tree_species:birch_log"]
        inv = Inventory()
        inv.add(log, 1)
        world = DummyWorld(blocks.WATER)
        hit = Hit((2, 3, 4), (2, 3, 3), blocks.WATER)
        result = try_place(world, inv, 0, hit, DummyBody())
        self.assertTrue(result.placed)
        self.assertEqual(world.placed[(2, 3, 4)], log)
        self.assertEqual(inv.count(log), 0)


if __name__ == "__main__":
    unittest.main()
