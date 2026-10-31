"""Stage 3 tests: items, colours, eating, mineral generation, ore rendering, mining drops, saved stats."""
import math
import tempfile
import unittest
from pathlib import Path

import numpy as np

import config as C
import items
from blocks import AIR, ROCK, SOIL, GRASS
from game import colors, eating
from game.inventory import Inventory
from game.mining import Miner
from game.stats import PlayerStats
from save import game_save
from save.store import SaveStore
from tests.test_core import flat_world
from world import mesher
from world.mesher import mesh_section
from world.world import World
from world.worldgen import generate_chunk_full, surface_heights, _pick_codes

RARE = items.code_from_rgb((200, 60, 60))   # vivid -> tier 2
COMMON = items.code_from_rgb((60, 60, 60))  # grey  -> tier 0


class TestItems(unittest.TestCase):
    def test_code_roundtrip_and_range(self):
        for code in range(items.N_COLORS):
            r, g, b = items.levels(code)
            self.assertEqual(items.code_from_levels(r, g, b), code)
            self.assertTrue(all(40 <= c <= 220 and c % 20 == 0 for c in items.rgb(code)))
            self.assertEqual(items.code_from_rgb(items.rgb(code)), code)
        self.assertEqual(items.rgb(RARE), (200, 60, 60))

    def test_tiers_partition_all_colours(self):
        base = np.concatenate(items.TIER_CODES)
        new = np.concatenate(items.NEW_TIER_CODES)
        self.assertEqual(len(base), 512)
        self.assertEqual(sorted(base.tolist() + new.tolist()), list(range(1000)))
        self.assertTrue(all(items.in_base_range(int(c)) for c in base))
        self.assertFalse(any(items.in_base_range(int(c)) for c in new))
        self.assertEqual(items.tier(COMMON), 0)
        self.assertEqual(items.tier(RARE), 2)
        self.assertTrue(all(len(t) > 50 for t in items.TIER_CODES))
        self.assertTrue(all(len(t) > 20 for t in items.NEW_TIER_CODES))

    def test_old_save_items_are_converted(self):
        old_red = 1000 + ((7 << 6) | (0 << 3) | 0)                 # format 1: (200, 60, 60)
        self.assertEqual(items.rgb(items.code_of(items.old_item_to_current(old_red))), (200, 60, 60))
        old_grey = 1000 + ((0 << 6) | (0 << 3) | 0)                # (60, 60, 60)
        self.assertEqual(items.rgb(items.code_of(items.old_item_to_current(old_grey))), (60, 60, 60))

    def test_stack_and_hardness_follow_rarity(self):
        self.assertEqual(items.stack_limit(items.item_of(COMMON)), 32)
        self.assertEqual(items.stack_limit(items.item_of(RARE)), 16)
        self.assertEqual(items.stack_limit(ROCK), 64)
        self.assertLess(items.mineral_hardness(COMMON), items.mineral_hardness(RARE))
        self.assertTrue(2.0 <= items.mineral_hardness(COMMON) <= items.mineral_hardness(RARE) <= 4.0)

    def test_item_validity(self):
        self.assertTrue(items.is_valid_item(ROCK))
        self.assertTrue(items.is_valid_item(items.item_of(511)))
        for bad in (0, 6, GRASS, 999, 3000, -1, True, 1.5, "x"):
            self.assertFalse(items.is_valid_item(bad), bad)

    def test_mixed_inventory_stacking(self):
        inv = Inventory()
        self.assertEqual(inv.add(items.item_of(RARE), 40), 0)         # 16 + 16 + 8
        self.assertEqual(inv.used_slots(), 3)
        self.assertEqual(inv.add(items.item_of(COMMON), 1), 0)
        self.assertEqual(inv.used_slots(), 4)                          # a different colour is a different stack


class TestColours(unittest.TestCase):
    def test_neutral_cases(self):
        red, green = (200, 60, 60), (60, 200, 60)
        self.assertAlmostEqual(colors.matchup(red, red), 1.0)
        self.assertAlmostEqual(colors.matchup((130, 130, 130), red), 1.0)       # grey attacker: no edge
        self.assertAlmostEqual(colors.matchup(red, (130, 130, 130)), 1.0)       # grey defender: no edge
        self.assertAlmostEqual(colors.matchup(red, (60, 200, 200)), 1.0, places=6)   # opposite hue

    def test_one_way_three_cycle_and_mirrored_roles(self):
        red, green, blue = (200, 60, 60), (60, 200, 60), (60, 60, 200)
        self.assertGreater(colors.matchup(green, red), 1.2)             # +120 degrees ahead wins
        self.assertLess(colors.matchup(red, green), 0.8)
        self.assertGreater(colors.matchup(blue, green), 1.2)
        self.assertGreater(colors.matchup(red, blue), 1.2)              # ... and the cycle closes
        for a, d in ((red, green), (green, blue), (blue, red)):
            self.assertAlmostEqual(colors.matchup(a, d) - 1, -(colors.matchup(d, a) - 1), places=9)

    def test_range_and_vividness(self):
        k = C.MATCHUP_K
        rng = np.random.default_rng(1)
        for _ in range(500):
            a = tuple(int(60 + 20 * v) for v in rng.integers(0, 8, 3))
            d = tuple(int(60 + 20 * v) for v in rng.integers(0, 8, 3))
            self.assertTrue(1 - k - 1e-9 <= colors.matchup(a, d) <= 1 + k + 1e-9)
        vivid = abs(colors.matchup((200, 60, 60), (60, 200, 60)) - 1)
        muted = abs(colors.matchup((140, 120, 120), (120, 140, 120)) - 1)
        self.assertGreater(vivid, muted * 3)                            # muted colours matter far less

    def test_distance(self):
        self.assertAlmostEqual(colors.MAX_DISTANCE, 242.5, delta=0.1)
        self.assertEqual(colors.distance((1, 2, 3), (1, 2, 3)), 0)


class TestEating(unittest.TestCase):
    def test_heal_hurt_and_colour_shift(self):
        me = (130.0, 130.0, 130.0)
        delta, new = eating.eat_effect(me, me, 100)
        self.assertEqual(delta, round(100 * C.EAT_HEAL_MAX))
        self.assertEqual(new, me)
        far_delta, far_new = eating.eat_effect((60.0, 60.0, 60.0), (200.0, 200.0, 200.0), 100)
        self.assertEqual(far_delta, -round(100 * C.EAT_HURT_MAX))
        self.assertAlmostEqual(far_new[0], 60 + 140 * C.EAT_COLOR_MIX)
        mid, _ = eating.eat_effect(me, (130.0 + C.EAT_SAFE_DISTANCE / math.sqrt(3),) * 3, 100)
        self.assertEqual(mid, 0)                                         # exactly at the safe distance
        d_near, _ = eating.eat_effect(me, (150.0, 130.0, 130.0), 100)
        d_far, _ = eating.eat_effect(me, (200.0, 60.0, 60.0), 100)
        self.assertGreater(d_near, 0)
        self.assertLess(d_far, 0)

    def test_colour_never_leaves_the_allowed_range(self):
        rng = np.random.default_rng(2)
        base = np.concatenate(items.TIER_CODES)
        stats = PlayerStats()
        for _ in range(300):                                            # before the boss: only 60..200 minerals exist
            stats.eat(items.rgb(int(rng.choice(base))))
            self.assertTrue(all(60 <= c <= 200 for c in stats.color))
        stats = PlayerStats()
        for _ in range(300):                                            # after it: any of the 1000 colours, 40..220
            stats.eat(items.rgb(int(rng.integers(0, 1000))))
            self.assertTrue(all(40 <= c <= 220 for c in stats.color))

    def test_hp_is_clamped(self):
        stats = PlayerStats()
        self.assertEqual(stats.hp, stats.max_hp)
        for _ in range(60):
            stats.apply_hp(-30)
        self.assertEqual(stats.hp, 1)                                    # no death before stage 5
        stats.apply_hp(10 ** 6)
        self.assertEqual(stats.hp, stats.max_hp)


class TestMineralGeneration(unittest.TestCase):
    def test_deterministic_and_only_in_rock(self):
        b1, m1 = generate_chunk_full(C.SEED, 2, -3)
        b2, m2 = generate_chunk_full(C.SEED, 2, -3)
        self.assertTrue((b1 == b2).all() and (m1 == m2).all())
        self.assertTrue(((m1 > 0) <= (b1 == ROCK)).all())
        codes = (m1[m1 > 0] - 1).astype(int)
        self.assertTrue(len(codes) > 0 and all(items.in_base_range(int(c)) for c in codes),
                        "before the boss only 60..200 colours exist")

    def test_density_is_reasonable(self):
        ore = rock = 0
        for cx in range(-4, 4):
            for cz in range(-4, 4):
                b, m = generate_chunk_full(C.SEED, cx, cz)
                ore += int((m > 0).sum()); rock += int((b == ROCK).sum())
        self.assertTrue(0.005 < ore / rock < 0.05, ore / rock)

    def test_depth_gates_rarity(self):
        n = 4000
        u = np.random.default_rng(5).random(n)
        u2 = np.random.default_rng(6).random(n)
        tiers = lambda depth: np.array([items.tier(int(c)) for c in _pick_codes(u, u2, np.full(n, depth))])
        self.assertTrue((tiers(0) == 0).all() and (tiers(7) == 0).all())
        t_mid = tiers(10)
        self.assertTrue((t_mid <= 1).all() and (t_mid == 1).any())
        t_deep = tiers(30)
        self.assertTrue((t_deep == 2).any() and (t_deep == 0).any())

    def test_surface_outcrops_exist_and_hold_ore(self):
        outcrop_cells = ore_cells = 0
        for cx in range(-6, 6):
            for cz in range(-6, 6):
                b, m = generate_chunk_full(C.SEED, cx, cz)
                h = surface_heights(C.SEED, (cx * 16 + np.arange(16))[:, None], (cz * 16 + np.arange(16))[None, :])
                above = np.arange(C.WORLD_HEIGHT)[None, :, None] > h[:, None, :]
                rock_above = (b == ROCK) & above
                outcrop_cells += int(rock_above.sum())
                ore_cells += int(((m > 0) & rock_above).sum())
        self.assertGreater(outcrop_cells, 50)
        self.assertGreater(ore_cells, 10)

    def test_generation_still_fast(self):
        import time
        t = time.perf_counter()
        for i in range(10):
            generate_chunk_full(C.SEED, i, -i)
        self.assertLess((time.perf_counter() - t) * 100, 40)


def ore_world(code=COMMON):
    """Flat test world with one ore block at (3, 9, 3)."""
    w = flat_world()
    ch = w.get_chunk(0, 0)
    ch.minerals[3, 9, 3] = code + 1
    return w


class TestWorldMinerals(unittest.TestCase):
    def test_edits_clear_minerals(self):
        w = ore_world()
        self.assertEqual(w.get_mineral(3, 9, 3), COMMON)
        self.assertIsNone(w.get_mineral(4, 9, 3))
        w.set_block(3, 9, 3, AIR)
        self.assertIsNone(w.get_mineral(3, 9, 3))
        w.set_block(3, 9, 3, ROCK)                                       # placing rock back does not bring the ore back
        self.assertIsNone(w.get_mineral(3, 9, 3))

    def test_mined_ore_stays_gone_after_reload(self):
        """Mine an ore, put plain rock back (block type == generated type), save, reload: the ore must not reappear."""
        def gen(seed, cx, cz):                                            # deterministic world that always has this ore
            b = np.zeros((16, C.WORLD_HEIGHT, 16), np.uint8)
            b[:, :10, :] = ROCK
            m = np.zeros(b.shape, np.uint16)
            m[3, 9, 3] = RARE + 1
            m[8, 9, 8] = COMMON + 1
            return b, m

        with tempfile.TemporaryDirectory() as tmp:
            store = SaveStore(Path(tmp) / "w")
            w = World(generator=gen, store=store)
            w.remove_block(3, 9, 3)
            w.set_block(3, 9, 3, ROCK)                                    # same block type as generated
            game_save.save_game(store, w, Inventory(), {}, (0, 0, 0))
            self.assertTrue((store.dir / "chunks" / "c_0_0.json").exists(), "the cleared ore must be in the diff")

            w2 = World(generator=gen, store=SaveStore(store.dir))
            self.assertIsNone(w2.get_mineral(3, 9, 3))
            self.assertEqual(w2.get_block(3, 9, 3), ROCK)
            self.assertEqual(w2.get_mineral(8, 9, 8), COMMON)             # untouched ore is still there

            w2.set_block(3, 9, 3, ROCK)                                   # a second round trip keeps it gone
            game_save.save_game(w2.store, w2, Inventory(), {}, (0, 0, 0))
            w3 = World(generator=gen, store=SaveStore(store.dir))
            self.assertIsNone(w3.get_mineral(3, 9, 3))


class TestOreRendering(unittest.TestCase):
    def _air_world_with(self, cells):
        w = World(generator=lambda s, cx, cz: np.zeros((16, 64, 16), np.uint8))
        for c in cells:
            w.set_block(*c, ROCK)
        return w

    def test_ore_block_is_cut_into_cells_and_plain_rock_is_not(self):
        w = self._air_world_with([(5, 5, 5), (9, 5, 9)])
        w.get_chunk(0, 0).minerals[5, 5, 5] = RARE + 1
        v, t, c = mesh_section(w.padded(0, 0), 0, w.chunks[(0, 0)].minerals)
        self.assertEqual(len(v), 6 * 9 * 4 + 6 * 4)                      # ore: 6 faces x 9 cells; plain: 6 faces
        self.assertTrue(t.max() < len(v) and t.min() >= 0 and len(t) % 6 == 0)
        plain = mesh_section(w.padded(0, 0), 0)                          # no mineral array: both blocks plain
        self.assertEqual(len(plain[0]), 48)

    def test_ore_hides_faces_against_neighbours(self):
        w = self._air_world_with([(5, 5, 5), (6, 5, 5)])
        w.get_chunk(0, 0).minerals[5, 5, 5] = COMMON + 1
        v, t, c = mesh_section(w.padded(0, 0), 0, w.chunks[(0, 0)].minerals)
        self.assertEqual(len(v), 5 * 9 * 4 + 5 * 4)

    def test_ore_patch_is_small_and_clear_up_close(self):
        """Ore must not dominate the scenery (a calm patch, ORE_CELLS of 9), but up close every one of the 1000 colours
        must still stand out from the plain rock cells next to it (all 1000, including the post-boss ones)."""
        disp = mesher._ore_display_colors(np.arange(1000))
        cell_contrast = np.linalg.norm(disp - mesher._ROCK_DARK, axis=1)
        self.assertGreater(float(cell_contrast.min()), 0.15)
        coverage = mesher._PATTERNS.sum(axis=1).mean() / 9.0
        self.assertLessEqual(coverage, 0.40)
        self.assertTrue((disp <= 1.0).all())

    def test_every_pattern_colours_the_configured_number_of_cells(self):
        self.assertTrue((mesher._PATTERNS.sum(axis=1) == C.ORE_CELLS).all())

    def test_vivid_colours_keep_their_hue(self):
        disp = mesher._ore_display_colors(np.array([RARE]))[0]
        self.assertEqual(int(np.argmax(disp)), 0)                        # still red-dominant
        self.assertGreater(disp[0] - disp[1], 0.15)


class TestMiningOre(unittest.TestCase):
    def run_dig(self, world, inv, seconds):
        miner = Miner(world, inv)
        out = []
        for _ in range(int(seconds * 60)):
            out.append(miner.update(1 / 60, True, (3, 9, 3)))
        return [r for r in out if r.broke], miner

    def test_ore_takes_longer_by_rarity_and_drops_mineral_then_rock(self):
        w = ore_world(COMMON); inv = Inventory()
        broke, _ = self.run_dig(w, inv, 2.1)
        self.assertEqual(broke, [])                                      # plain rock would be done at 2.0 s
        broke, _ = self.run_dig(ore_world(COMMON), inv, 2.5)
        self.assertEqual(len(broke), 1)
        self.assertEqual(broke[0].gained, [(items.item_of(COMMON), 1), (ROCK, 1)])
        self.assertEqual(inv.count(items.item_of(COMMON)), 1)
        w2 = ore_world(RARE)
        broke, _ = self.run_dig(w2, Inventory(), 3.5)
        self.assertEqual(broke, [])                                      # rare ore needs ~3.8 s
        broke, _ = self.run_dig(ore_world(RARE), Inventory(), 4.0)
        self.assertEqual(len(broke), 1)

    def test_full_inventory_loses_the_rock_not_the_mineral(self):
        inv = Inventory(1)                                               # one empty slot
        broke, _ = self.run_dig(ore_world(RARE), inv, 4.0)
        self.assertEqual(broke[0].gained, [(items.item_of(RARE), 1)])
        self.assertEqual(broke[0].lost, [(ROCK, 1)])

    def test_plain_rock_unchanged(self):
        w = flat_world(); inv = Inventory()
        broke, _ = self.run_dig(w, inv, 2.1)
        self.assertEqual(len(broke), 1)
        self.assertEqual(broke[0].gained, [(ROCK, 1)])


class TestSavedStats(unittest.TestCase):
    def test_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = SaveStore(Path(tmp) / "w")
            w = flat_world()
            stats = PlayerStats(level=3, color=(100.5, 80.0, 190.0)); stats.apply_hp(-20)
            inv = Inventory(); inv.add(items.item_of(RARE), 5); inv.add(ROCK, 2)
            game_save.save_game(store, w, inv, {}, (0, 0, 0), stats)
            meta = SaveStore(store.dir).load_meta()
            s2 = game_save.restore_stats(meta)
            self.assertEqual((s2.level, s2.hp, s2.color), (3, stats.hp, (100.5, 80.0, 190.0)))
            inv2 = game_save.restore_inventory(meta["inventory"])
            self.assertEqual(inv2.slots[:2], [[items.item_of(RARE), 5], [ROCK, 2]])

    def test_bad_stats_fall_back(self):
        s = game_save.restore_stats({"stats": {"level": "x", "hp": 99999, "color": [1, 2, 3]}})
        self.assertEqual((s.level, s.color), (1, C.START_COLOR))
        self.assertEqual(s.hp, s.max_hp)                                  # clamped
        s = game_save.restore_stats({"stats": {"level": 2, "hp": -5, "color": [100, 100, float("nan")]}})
        self.assertEqual((s.level, s.hp, s.color), (2, 1, C.START_COLOR))
        self.assertEqual(game_save.restore_stats({}).level, 1)
        rows = [[items.item_of(COMMON), 99], [3000, 1], [items.item_of(COMMON), "x"]]
        inv = game_save.restore_inventory(rows)
        self.assertEqual(inv.slots[0], [items.item_of(COMMON), 32])        # clamped to the common stack limit
        self.assertIsNone(inv.slots[1]); self.assertIsNone(inv.slots[2])


if __name__ == "__main__":
    unittest.main()
