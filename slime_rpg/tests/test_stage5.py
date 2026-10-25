"""Stage 5 tests: battle events and presenter, pixel sprites, day/night, villages, water widths, saved time."""
import random
import tempfile
import unittest
from pathlib import Path

import numpy as np

import config as C
import items
from blocks import AIR, WOOD, LEAF, ROCK, GRASS, WATER
from game import daytime as D
from game.battle import Battle, Enemy
from game.encounter import EncounterTracker
from game.fog import fog_for_depth
from game.inventory import Inventory
from game.presenter import BattlePresenter
from game.sprites import slime_sprite
from game.stats import PlayerStats
from save import game_save
from save.store import SaveStore
from tests.test_battle import FixedRNG, duel, GREEN, RED
from tests.test_core import flat_world
from world import villages as V
from world.world import World
from world.worldgen_heights import surface_heights


class TestBattleEvents(unittest.TestCase):
    def test_round_is_action_then_result_for_each_side_in_speed_order(self):
        stats, enemy, inv, b = duel(e_spd=1)                              # player faster
        b.take_events()
        b.act("tackle")
        ev = b.take_events()
        self.assertEqual([e.kind for e in ev], ["act", "result", "act", "result"])
        self.assertEqual([e.sound for e in ev], ["whoosh", "impact", "whoosh", "impact"])
        self.assertTrue(ev[0].text.startswith("> You") and ev[1].text.startswith("  Slime takes"))
        self.assertTrue(ev[2].text.startswith("> Slime") and ev[3].text.startswith("  You take"))
        self.assertEqual(b.take_events(), [])                             # nothing new

    def test_enemy_first_when_faster(self):
        stats, enemy, inv, b = duel(e_spd=99)
        b.take_events()
        b.act("tackle")
        ev = b.take_events()
        self.assertTrue(ev[0].text.startswith("> Slime") and ev[2].text.startswith("> You"))

    def test_snapshots_change_only_when_the_damage_line_appears(self):
        stats, enemy, inv, b = duel(e_spd=1)
        b.take_events()
        b.act("tackle")
        act, result = b.take_events()[:2]
        self.assertEqual(act.snap["enemy_hp"], enemy.max_hp)             # "You tackle!" - nothing lost yet
        self.assertLess(result.snap["enemy_hp"], enemy.max_hp)           # damage line carries the new number
        self.assertEqual(result.snap["you_hp"], stats.max_hp)            # ... and the enemy has not struck yet

    def test_win_notices_and_sounds(self):
        stats, enemy, inv, b = duel(e_hp=1, level=4)
        stats.xp = 7
        b.take_events()
        b.act("tackle")
        ev = b.take_events()
        sounds = [e.sound for e in ev if e.sound]
        self.assertIn("win", sounds)
        self.assertIn("levelup", sounds)
        self.assertEqual(ev[-1].kind, "note")
        self.assertTrue(any(e.text.startswith("* +") and "XP" in e.text for e in ev))

    def test_defeat_ends_with_the_lose_sound(self):
        stats, enemy, inv, b = duel(e_spd=99, e_atk=999)
        stats.hp = 1
        b.take_events()
        b.act("tackle")
        ev = b.take_events()
        self.assertEqual(ev[-1].sound, "lose")
        self.assertEqual(ev[-1].snap["you_hp"], 0)

    def test_eat_event_carries_the_new_colour_and_hp(self):
        stats, enemy, inv, b = duel(e_spd=1)
        inv.add(RED, 1)
        b.take_events()
        c0 = stats.color
        b.act("eat", 0)
        act, result = b.take_events()[:2]
        self.assertEqual(act.snap["you_color"], c0)
        self.assertNotEqual(result.snap["you_color"], c0)

    def test_a_refused_action_still_explains_itself(self):
        stats, enemy, inv, b = duel()
        b.take_events()
        self.assertFalse(b.act("throw", 0))
        ev = b.take_events()
        self.assertEqual(len(ev), 1)
        self.assertIn("mineral", ev[0].text.lower())
        self.assertIsNone(ev[0].sound)


class TestPresenter(unittest.TestCase):
    def setUp(self):
        self.stats, self.enemy, self.inv, self.b = duel(e_spd=1)
        self.p = BattlePresenter(self.b.snapshot(), self.b.log)
        self.b.take_events()
        self.b.act("tackle")
        self.p.push(self.b.take_events())

    def run_for(self, seconds, step=1 / 60):
        sounds = []
        for _ in range(int(seconds / step)):
            sounds += self.p.update(step)
        return sounds

    def test_lines_type_out_one_by_one_with_sounds_at_line_start(self):
        self.assertTrue(self.p.busy)
        before = len(self.p.done)
        sounds = self.p.update(1 / 60)
        self.assertEqual(sounds, ["whoosh"])                              # the first line starts: its sound plays
        self.assertTrue(self.p.lines()[-1].endswith("_"))                 # typing cursor, line not finished
        self.assertEqual(len(self.p.done), before)
        all_sounds = sounds + self.run_for(8)
        self.assertEqual(all_sounds, ["whoosh", "impact", "whoosh", "impact"])
        self.assertFalse(self.p.busy)
        self.assertEqual(len(self.p.done), before + 4)

    def test_numbers_update_when_the_result_line_finishes(self):
        start_hp = self.p.snap["enemy_hp"]
        self.p.update(1 / 60)                                             # line 1 begins
        self.assertEqual(self.p.snap["enemy_hp"], start_hp)
        t = 0
        while self.p.snap["enemy_hp"] == start_hp and t < 5:
            self.p.update(1 / 60); t += 1 / 60
        self.assertLess(self.p.snap["enemy_hp"], start_hp)
        self.assertEqual(self.p.snap["you_hp"], self.stats.max_hp)       # enemy's turn has not been shown yet
        self.assertTrue(self.p.busy)

    def test_pacing_is_readable_and_skip_finishes_everything(self):
        self.run_for(0.5)
        self.assertTrue(self.p.busy)                                      # not instant
        self.p.skip()
        self.assertFalse(self.p.busy)
        self.assertEqual(self.p.snap, self.b.snapshot())
        self.assertEqual(self.p.lines()[-1], self.b.log[-1])
        total = BattlePresenter(self.b.snapshot())
        total.push(self.b.events[-4:])
        elapsed = 0.0
        while total.busy and elapsed < 30:
            total.update(1 / 60); elapsed += 1 / 60
        self.assertTrue(1.5 < elapsed < 6.0, elapsed)                     # a round takes a few seconds to read

    def test_lines_window(self):
        self.p.skip()
        self.assertLessEqual(len(self.p.lines(3)), 3)


class TestSprites(unittest.TestCase):
    def test_shape_silhouette_and_transparency(self):
        a, b = slime_sprite((130, 130, 130)), slime_sprite((200, 60, 60))
        self.assertEqual((a.shape, a.dtype), ((32, 32, 4), np.uint8))
        self.assertTrue((a[..., 3] == b[..., 3]).all(), "colour variants must share one silhouette")
        body = int((a[..., 3] > 0).sum())
        self.assertTrue(250 < body < 700, body)
        self.assertTrue(set(np.unique(a[..., 3]).tolist()) <= {0, 255})
        self.assertEqual(int(a[a[..., 3] == 0][:, :3].sum()), 0)           # transparent pixels are black
        self.assertEqual(slime_sprite((90, 90, 90), size=48).shape, (48, 48, 4))

    def test_pixel_art_look_few_colours_with_outline_and_black_dot_eyes(self):
        for rgb in ((130, 130, 130), (200, 60, 60), (60, 200, 60), (60, 60, 200), (100, 160, 80)):
            s = slime_sprite(rgb)
            body = s[..., 3] > 0
            colours = {tuple(p) for p in s[body][:, :3].tolist()}
            self.assertLessEqual(len(colours), 16, rgb)                    # limited palette = pixel art
            self.assertGreaterEqual(len(colours), 6, rgb)                  # but not flat
            self.assertEqual(int(((s[..., :3] >= 250).all(axis=-1) & body).sum()), 0, "no white eyes")
            pad = np.pad(body, 1)
            inner = body & pad[:-2, 1:-1] & pad[2:, 1:-1] & pad[1:-1, :-2] & pad[1:-1, 2:]
            dark = inner & (s[..., :3].max(axis=-1) <= 20)
            ys, xs = np.nonzero(dark)
            self.assertEqual(len(ys), 12, "two eyes of 2x3 black pixels and nothing else dark (no mouth)")
            left, right = xs < s.shape[1] / 2, xs >= s.shape[1] / 2
            self.assertEqual((int(left.sum()), int(right.sum())), (6, 6))
            self.assertEqual(sorted(ys[left].tolist()), sorted(ys[right].tolist()), "the eyes are level")
        s = slime_sprite((200, 60, 60))
        alpha = s[..., 3] > 0
        pad = np.pad(alpha, 1)
        edge = alpha & ~(pad[:-2, 1:-1] & pad[2:, 1:-1] & pad[1:-1, :-2] & pad[1:-1, 2:])
        lum = s[..., :3].astype(float) @ np.array([0.299, 0.587, 0.114])
        self.assertLess(lum[edge].mean(), lum[alpha & ~edge].mean() * 0.6)  # dark outline

    def test_each_colour_reads_as_that_colour(self):
        for rgb in ((200, 60, 60), (60, 200, 60), (60, 60, 200)):
            s = slime_sprite(rgb)
            body = s[s[..., 3] > 0][:, :3].astype(float)
            body = body[body.sum(axis=1) > 120]                            # ignore the near-black outline and eye dots
            self.assertEqual(int(np.argmax(body.mean(axis=0))), int(np.argmax(rgb)))
        self.assertFalse((slime_sprite((200, 60, 60)) == slime_sprite((60, 200, 60))).all())


class TestDayNight(unittest.TestCase):
    def sec(self, hour):
        return hour / 24.0 * C.DAY_LENGTH

    def test_cycle_and_daylight(self):
        self.assertAlmostEqual(D.phase(C.DAY_LENGTH * 3 + 5), 5 / C.DAY_LENGTH)
        self.assertAlmostEqual(D.daylight(self.sec(12)), 1.0)
        self.assertAlmostEqual(D.daylight(self.sec(0)), 0.0)
        self.assertAlmostEqual(D.daylight(self.sec(6)), 0.5, delta=0.05)
        morning = [D.daylight(self.sec(h / 4)) for h in range(16, 32)]      # 4:00 .. 8:00
        self.assertEqual(morning, sorted(morning))                           # rises monotonically at dawn
        self.assertEqual(D.clock_text(self.sec(13.5)), "13:30")

    def test_sky_colour_changes_dark_blue_night_light_day_warm_dusk(self):
        night, noon, sunset = D.sky_color(self.sec(0)), D.sky_color(self.sec(12)), D.sky_color(self.sec(18))
        self.assertEqual(tuple(round(c, 2) for c in noon), C.SKY_DAY)
        self.assertLess(sum(night), sum(noon) * 0.2)
        self.assertGreater(night[2], night[0])                               # bluish night
        self.assertGreater(sunset[0], sunset[2])                             # orange-ish at sunset
        self.assertTrue(all(0.0 <= c <= 1.0 for c in sunset))

    def test_fog_follows_the_sky_and_goes_dark_underground(self):
        night = D.sky_color(self.sec(0))
        rgb, near, far = fog_for_depth(0, night)
        self.assertEqual(rgb, night)
        deep_day = fog_for_depth(C.FOG_FULL_DARK_DEPTH, D.sky_color(self.sec(12)))[0]
        deep_night = fog_for_depth(C.FOG_FULL_DARK_DEPTH, night)[0]
        for a, b in zip(deep_day, deep_night):
            self.assertAlmostEqual(a, b)                                     # time of day does not reach underground
        self.assertEqual(fog_for_depth(0)[0], C.FOG_COLOR_SURFACE)           # old call style still works

    def test_world_tint(self):
        self.assertEqual(D.world_tint(self.sec(12), 0), (1.0, 1.0, 1.0))
        self.assertEqual(D.world_tint(self.sec(0), 0), C.NIGHT_WORLD_TINT)
        self.assertEqual(D.world_tint(self.sec(0), C.FOG_FULL_DARK_DEPTH), (1.0, 1.0, 1.0))

    def test_night_raises_encounter_chance_on_the_surface_only(self):
        self.assertAlmostEqual(D.encounter_multiplier(self.sec(12), 0), 1.0)
        self.assertAlmostEqual(D.encounter_multiplier(self.sec(0), 0), C.NIGHT_ENCOUNTER_MULT)
        self.assertAlmostEqual(D.encounter_multiplier(self.sec(0), 2), C.NIGHT_ENCOUNTER_MULT)
        self.assertEqual(D.encounter_multiplier(self.sec(0), C.NIGHT_UNDERGROUND_DEPTH + 1), 1.0)
        mid = D.encounter_multiplier(self.sec(6), 0)
        self.assertTrue(1.2 < mid < C.NIGHT_ENCOUNTER_MULT)

    def test_tracker_uses_the_multiplier(self):
        def mean_gap(mult):
            t, rng, gaps, walked = EncounterTracker(), random.Random(3), [], 0
            for _ in range(80000):
                walked += 1
                if t.walk(1.0, False, rng, mult):
                    gaps.append(walked); walked = 0
            return sum(gaps) / len(gaps)
        day, night = mean_gap(1.0), mean_gap(C.NIGHT_ENCOUNTER_MULT)
        self.assertAlmostEqual(night, C.ENCOUNTER_SAFE_STEPS + 1 / (C.ENCOUNTER_CHANCE * C.NIGHT_ENCOUNTER_MULT),
                               delta=night * 0.12)
        self.assertLess(night, day * 0.7)
        t = EncounterTracker(safe_steps=0, chance=0.6)
        self.assertTrue(t.walk(1.0, False, FixedRNG(coin=0.9), chance_multiplier=2.0))   # 0.6 * 2 caps at 1.0

    def test_world_time_is_saved_and_old_saves_start_in_the_morning(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = SaveStore(Path(tmp) / "w")
            game_save.save_game(store, flat_world(), Inventory(), {}, (0, 0, 0), None, 123.5)
            self.assertEqual(game_save.restore_clock(SaveStore(store.dir).load_meta()), 123.5)
        self.assertEqual(game_save.restore_clock({}), C.START_TIME * C.DAY_LENGTH)
        for bad in ("x", -5, float("nan"), True, 1e12):
            self.assertEqual(game_save.restore_clock({"time": bad}), C.START_TIME * C.DAY_LENGTH)


class TestVillages(unittest.TestCase):
    def villages(self, n=6):
        out = [v for rx in range(-n, n) for rz in range(-n, n) if (v := V.village_in_region(C.SEED, rx, rz))]
        self.assertGreater(len(out), 20)
        return out

    def test_placement_is_deterministic_and_reasonably_common(self):
        found = self.villages()
        self.assertEqual(found, self.villages())
        share = len(found) / 144
        self.assertTrue(0.40 < share < 0.85, share)
        self.assertNotEqual({(v.x, v.z) for v in found},
                            {(v.x, v.z) for v in [V.village_in_region(C.SEED + 1, rx, rz)
                                                  for rx in range(-6, 6) for rz in range(-6, 6)] if v})

    def test_every_village_is_on_gentle_dry_land_inside_its_region(self):
        for v in self.villages():
            self.assertTrue(v.rx * V.R <= v.x - V.HALF and v.x + V.HALF < (v.rx + 1) * V.R, v)
            self.assertTrue(v.rz * V.R <= v.z - V.HALF and v.z + V.HALF < (v.rz + 1) * V.R, v)
            self.assertGreaterEqual(v.ground, C.SEA_LEVEL + 1)
            xs, zs = np.meshgrid(np.arange(v.x - 6, v.x + 7, 2), np.arange(v.z - 6, v.z + 7, 2))
            self.assertGreaterEqual(int(surface_heights(C.SEED, xs, zs).min()), C.SEA_LEVEL)

    def test_lookup_functions(self):
        v = self.villages()[0]
        self.assertEqual(V.village_at(C.SEED, v.x, v.z), v)
        for dx, dz in ((1, 0), (0, 1), (-1, -1), (V.HALF, 0)):
            self.assertIsNone(V.village_at(C.SEED, v.x + dx, v.z + dz), "only the single tile counts")
        v2, dist = V.nearest_village(C.SEED, v.x + 20, v.z + 20)
        self.assertEqual(v2, v)
        self.assertAlmostEqual(dist, 800 ** 0.5, places=6)
        best = min(self.villages(), key=lambda q: (q.x - 5) ** 2 + (q.z - 5) ** 2)
        self.assertEqual(V.nearest_village(C.SEED, 5, 5)[0].id, best.id)
        self.assertIn(v, V.villages_near_chunk(C.SEED, v.x >> 4, v.z >> 4, pad=0))
        self.assertEqual(V.direction_name(0, 10), "N")
        self.assertEqual(V.direction_name(10, 0), "E")
        self.assertEqual(V.direction_name(-7, -7), "SW")
        self.assertEqual(v.stand, (v.x + 0.5, v.ground + 1.01, v.z + 0.5))

    def test_patch_tile_and_signpost_match_the_layout_in_every_chunk_order(self):
        v = V.village_in_region(C.SEED, 0, 0)
        layout = V.structure_blocks(v)
        chunks = sorted({((v.x + dx) >> 4, (v.z + dz) >> 4) for dx in range(-3, 4) for dz in range(-3, 4)})
        worlds = []
        for order in (chunks, list(reversed(chunks))):
            w = World()
            for c in order:
                w.get_chunk(*c)
            worlds.append(w)
            for dx in range(-V.HALF, V.HALF + 1):
                for dz in range(-V.HALF, V.HALF + 1):
                    expected = WOOD if (dx, dz) == (0, 0) else GRASS
                    self.assertEqual(w.get_block(v.x + dx, v.ground, v.z + dz), expected, (dx, dz))
                    for dy in range(1, 12):
                        self.assertEqual(w.get_block(v.x + dx, v.ground + dy, v.z + dz), layout.get((dx, dy, dz), AIR), (dx, dy, dz))
        for dx in range(-4, 5):
            for dz in range(-4, 5):
                for dy in range(-4, 12):
                    self.assertEqual(worlds[0].get_block(v.x + dx, v.ground + dy, v.z + dz),
                                     worlds[1].get_block(v.x + dx, v.ground + dy, v.z + dz))

    def test_the_tile_can_be_stepped_on_and_the_signpost_is_unbreakable_water(self):
        from blocks import hardness_at
        v = V.village_in_region(C.SEED, 0, 0)
        w = World()
        self.assertEqual(w.get_block(v.x, v.ground, v.z), WOOD)
        self.assertEqual(w.get_block(v.x, v.ground + 1, v.z), AIR)
        self.assertEqual(w.get_block(v.x, v.ground + 2, v.z), AIR)
        layout = V.structure_blocks(v)
        self.assertEqual(set(layout.values()), {WATER}, "the sign is made of water only: not a tree, and it cannot be dug")
        self.assertEqual(w.get_block(v.x, v.ground + 4, v.z + V.HALF), WATER)      # the post stands beside the tile
        self.assertEqual(len(layout), 4 + (2 * V.HALF + 1) + 1)
        self.assertIsNone(hardness_at(WATER, v.ground + 3))
        from game.mining import Miner
        miner = Miner(w, Inventory())
        for _ in range(600):
            res = miner.update(1 / 60, True, (v.x, v.ground + 3, v.z + V.HALF))
        self.assertFalse(res.broke)
        self.assertEqual(w.get_block(v.x, v.ground + 3, v.z + V.HALF), WATER)

    def test_no_buildings_no_trees_near_the_village(self):
        v = V.village_in_region(C.SEED, 0, 0)
        layout = V.structure_blocks(v)
        w = World()
        reach = V.HALF + C.VILLAGE_TREE_MARGIN
        for dx in range(-reach, reach + 1):
            for dz in range(-reach, reach + 1):
                inside = abs(dx) <= V.HALF and abs(dz) <= V.HALF
                for dy in range(1, 14):
                    b = w.get_block(v.x + dx, v.ground + dy, v.z + dz)
                    if not inside:
                        self.assertNotEqual(b, WOOD, ("trunk near the village", dx, dy, dz))
                        if max(abs(dx), abs(dz)) <= V.HALF + 1:
                            self.assertNotEqual(b, LEAF, ("leaf next to the patch", dx, dy, dz))
                if inside:
                    for dy in range(-3, 12):
                        self.assertIsNone(w.get_mineral(v.x + dx, v.ground + dy, v.z + dz))
        self.assertEqual(len(layout), 4 + 5 + 1, "just a signpost: no huts")

    def test_the_tile_is_safe_ground_for_encounters(self):
        v = V.village_in_region(C.SEED, 0, 0)
        w = World()
        foot = w.get_block(v.x, v.ground, v.z)
        self.assertEqual(foot, WOOD)
        t = EncounterTracker(safe_steps=0, chance=1.0)
        self.assertFalse(any(t.walk(1.0, foot == WOOD, random.Random(1)) for _ in range(100)))


class TestWorldShape(unittest.TestCase):
    def test_water_bodies_are_narrow_enough_to_bridge(self):
        X = np.arange(-1500, 1500, 2)[:, None]
        Z = np.arange(-1500, 1500, 2)[None, :]
        water = surface_heights(C.SEED, X, Z) < C.SEA_LEVEL
        self.assertTrue(0.06 < water.mean() < 0.25, water.mean())
        runs = []
        for row in water[::9]:
            n = 0
            for cell in row:
                if cell:
                    n += 1
                elif n:
                    runs.append(n * 2); n = 0
        runs = np.array(runs)
        self.assertLessEqual(np.percentile(runs, 90), 55)                      # ~ 2 slots of Wood
        self.assertLessEqual(np.percentile(runs, 99), 100)                     # ~ 3 slots of Wood
        self.assertGreater(runs.max(), 100)                                    # a wide sea is still possible, but rare

    def test_land_is_walkable_without_digging(self):
        X = np.arange(-600, 600)[:, None]
        Z = np.arange(-600, 600)[None, :]
        h = surface_heights(C.SEED, X, Z)
        land = (h >= C.SEA_LEVEL)
        for axis in (0, 1):
            step = np.abs(np.diff(h, axis=axis))
            both = np.diff(land.astype(int), axis=axis) == 0
            self.assertLess(float(((step >= 2) & both & land[:-1] if axis == 0 else (step >= 2) & both & land[:, :-1]).mean()), 0.005)


if __name__ == "__main__":
    unittest.main()
