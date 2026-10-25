"""Random worlds, safe spawns, fees by any mineral, the music director and the 'new world' confirmation."""
import math
import random
import unittest

import numpy as np

import config as C
from blocks import AIR, GRASS
from game.physics import Body
from world import boss_arena, villages
from world.seeds import MAX_SEED, random_seed, seed_from_args
from world.spawn import find_spawn
from world.world import World
from world.worldgen_heights import surface_heights


class TestSeeds(unittest.TestCase):
    def test_new_seeds_differ_and_are_valid(self):
        seeds = {random_seed() for _ in range(50)}
        self.assertGreater(len(seeds), 45, "every new game must get a different map")
        self.assertTrue(all(1 <= s <= MAX_SEED for s in seeds))
        r = random.Random(1)
        self.assertEqual(random_seed(r), random_seed(random.Random(1)))

    def test_seed_on_the_command_line_or_in_the_environment(self):
        self.assertEqual(seed_from_args(["main.py", "--seed", "4242"], {}), 4242)
        self.assertEqual(seed_from_args(["main.py", "--seed=77"], {}), 77)
        self.assertEqual(seed_from_args(["main.py"], {"SLIME_SEED": "9"}), 9)
        self.assertEqual(seed_from_args(["main.py", "--seed", "5"], {"SLIME_SEED": "9"}), 5, "the command line wins")
        for bad in (["--seed"], ["--seed", "x"], ["--seed", "0"], ["--seed", "-3"], ["--seed", str(MAX_SEED + 5)]):
            self.assertIsNone(seed_from_args(["main.py"] + bad, {}), bad)
        self.assertIsNone(seed_from_args(["main.py"], {"SLIME_SEED": "nope"}))


class TestRandomWorlds(unittest.TestCase):
    def test_any_seed_gives_a_playable_world(self):
        rng = random.Random(11)
        for _ in range(25):
            seed = random_seed(rng)
            w = World(seed)
            x, y, z = find_spawn(w)
            self.assertLessEqual(abs(x) + abs(z), 60, (seed, x, z))                       # starts near the origin
            cx, cy, cz = math.floor(x), int(round(y - 1.01)), math.floor(z)
            self.assertEqual(w.get_block(cx, cy, cz), GRASS)
            self.assertEqual(w.get_block(cx, cy + 1, cz), AIR, "no trunk or leaf at the spawn")
            self.assertFalse(w.is_blocking(cx, cy + 1, cz) or w.is_blocking(cx, cy + 2, cz))
            body = Body(w, x, y, z)
            for _ in range(60):
                body.update(1 / 60, 0, 0, False)
            self.assertTrue(body.on_ground and abs(body.y - y) < 0.2, (seed, body.y, y))
            near = villages.nearest_village(seed, x, z, reach=3)
            self.assertIsNotNone(near, seed)
            self.assertLess(near[1], 250, (seed, near[1]))
            ax, az = boss_arena.arena_center(seed)
            self.assertGreaterEqual(int(surface_heights(seed, ax, az)), C.SEA_LEVEL + 1, "the lair is on dry land")

    def test_different_seeds_give_different_terrain(self):
        a = surface_heights(1, np.arange(40)[:, None], np.arange(40)[None, :])
        b = surface_heights(2, np.arange(40)[:, None], np.arange(40)[None, :])
        self.assertFalse((a == b).all())

    def test_a_tree_in_the_way_is_skipped(self):
        w = World(C.SEED)
        x, y, z = find_spawn(w)
        # put a trunk where the first spawn would be: the search must move on to another column
        w.set_block(math.floor(x), math.floor(y), math.floor(z), 4)
        x2, y2, z2 = find_spawn(w)
        self.assertNotEqual((math.floor(x2), math.floor(z2)), (math.floor(x), math.floor(z)))


if __name__ == "__main__":
    unittest.main()
