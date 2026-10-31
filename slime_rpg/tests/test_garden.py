"""Flower seed cultivation and persistence."""
import tempfile
import unittest

import numpy as np
import config as C
import items
from blocks import AIR, ROCK, GRASS, WATER, FLOWER
from game.garden import planting_cell, seed_drop_code
from game.inventory import Inventory
from game.mining import Miner
from game.raycast import Hit
from save import game_save
from save.store import SaveStore
from tests.test_core import flat_world
from world.world import World
from world.mesher import mesh_section
from world.manager import ChunkManager


class TestGarden(unittest.TestCase):
    def make_water_world(self):
        return flat_world(ground_y=10, water_cols=((1, 0),))

    def test_seed_can_only_be_planted_on_soil_next_to_water(self):
        w = self.make_water_world()
        hit = Hit((0, 10, 0), None, GRASS)
        self.assertEqual(planting_cell(w, hit), (0, 11, 0))
        self.assertIsNone(planting_cell(w, Hit((3, 10, 0), None, GRASS)))
        self.assertIsNone(planting_cell(w, Hit((0, 9, 0), None, ROCK)))

    def test_plant_metadata_survives_save_and_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = SaveStore(tmp)
            w = self.make_water_world()
            w.store = store
            code = 384
            self.assertTrue(w.plant_flower_seed(0, 11, 0, code, 123.5))
            game_save.save_game(store, w, Inventory(), {}, (0, 0, 0))
            w2 = self.make_water_world()
            w2.store = store
            self.assertEqual(w2.get_block(0, 11, 0), FLOWER)
            self.assertEqual(w2.get_plant(0, 11, 0), (code, 123.5))

    def test_flower_tile_is_not_a_full_height_collision_block(self):
        w = self.make_water_world()
        w.plant_flower_seed(0, 11, 0, 384, 0.0)
        self.assertFalse(w.is_blocking(0, 11, 0))
        self.assertTrue(w.is_blocking(0, 10, 0))  # ground remains solid

    def test_unripe_flower_returns_seed_and_ripe_flower_returns_mineral(self):
        for now, expected in ((100.0, items.seed_of(384)), (C.DAY_LENGTH + 10.0, items.item_of(384))):
            w = self.make_water_world()
            w.plant_flower_seed(0, 11, 0, 384, 0.0)
            inv = Inventory()
            miner = Miner(w, inv)
            miner.world_time = now
            result = miner.update(0.3, True, (0, 11, 0))
            self.assertTrue(result.broke)
            self.assertEqual(inv.count(expected), 1)
            self.assertEqual(w.get_block(0, 11, 0), AIR)

    def test_seedling_changes_mesh_when_one_day_passes(self):
        w = self.make_water_world()
        w.plant_flower_seed(0, 11, 0, 384, 0.0)
        ch = w.get_chunk(0, 0)
        padded = w.padded(0, 0)
        young = mesh_section(padded, 0, ch.minerals, ch.plants, 0.0)
        bloom = mesh_section(padded, 0, ch.minerals, ch.plants, C.DAY_LENGTH)
        self.assertIsNotNone(young)
        self.assertIsNotNone(bloom)
        self.assertNotEqual(young[0].shape, bloom[0].shape)  # mature flower has visible coloured petals
        self.assertFalse(np.array_equal(young[2], bloom[2]))
        # Both stages include the thin brown planter tile instead of an invisible air-cell plant.
        self.assertTrue(np.any(np.all(np.isclose(young[2][:, :3], (0.58, 0.39, 0.23)), axis=1)))
        self.assertTrue(np.any((young[0][:, 1] > 11.0) & (young[0][:, 1] < 11.14)))

    def test_chunk_manager_marks_flower_dirty_at_maturity(self):
        w = self.make_water_world()
        w.plant_flower_seed(0, 11, 0, 384, 10.0)
        manager = ChunkManager(w, lambda *_: None, lambda *_: None)
        manager.update_world_time(10.0)
        manager.update_world_time(10.0 + C.DAY_LENGTH)
        self.assertIn((0, 0, 0), w.dirty)

    def test_soil_mining_can_drop_a_seed_on_a_successful_roll(self):
        class AlwaysDrop:
            def random(self):
                return 0.0

            def randrange(self, stop):
                return 0

        w = self.make_water_world()
        inv = Inventory()
        miner = Miner(w, inv, rng=AlwaysDrop())
        result = miner.update(1.0, True, (0, 10, 0))
        self.assertTrue(result.broke)
        self.assertTrue(any(items.is_seed(item) for item, count in result.gained))

    def test_seed_drop_colours_follow_game_stage(self):
        import random
        rng = random.Random(3)
        base_codes = set(int(v) for pool in items.TIER_CODES for v in pool)
        extended_codes = set(range(items.N_COLORS))
        self.assertIn(seed_drop_code(rng, False), base_codes)
        self.assertIn(seed_drop_code(rng, True), extended_codes)

    def test_seed_stack_and_color_roundtrip(self):
        seed = items.seed_of(384)
        self.assertTrue(items.is_valid_item(seed))
        self.assertTrue(items.is_seed(seed))
        self.assertEqual(items.seed_code(seed), 384)
        inv = Inventory()
        self.assertEqual(inv.add(seed, 40), 0)
        self.assertEqual(inv.count(seed), 40)


if __name__ == "__main__":
    unittest.main()
