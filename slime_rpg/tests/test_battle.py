"""Stage 4 tests: progression, enemies, battle rules, encounters, death, saved progress."""
import random
import tempfile
import unittest
from pathlib import Path

import config as C
import items
from blocks import ROCK
from game import progression as P
from game.battle import Battle, make_enemy, base_damage, throw_value, Enemy
from game.death import apply_death
from game.encounter import EncounterTracker
from game.inventory import Inventory
from game.stats import PlayerStats
from save import game_save
from save.store import SaveStore
from tests.test_core import flat_world

GREEN = items.item_of(items.code_from_rgb((60, 200, 60)))
RED = items.item_of(items.code_from_rgb((200, 60, 60)))


class FixedRNG:
    """Deterministic stand-in for random.Random: no damage jitter, chosen coin flips."""
    def __init__(self, coin=0.5, points=5):
        self.coin, self.points = coin, points

    def uniform(self, a, b):
        return (a + b) / 2.0

    def random(self):
        return self.coin

    def randint(self, a, b):
        return self.points

    def choices(self, population, weights=None, k=1):
        return [population[0]]


def duel(player_color=(130.0, 130.0, 130.0), enemy_color=(130.0, 130.0, 130.0), **kw):
    stats = PlayerStats(color=player_color)
    enemy = Enemy(level=kw.get("level", 1), max_hp=kw.get("e_hp", 50), hp=kw.get("e_hp", 50), atk=kw.get("e_atk", 10),
                  defense=kw.get("e_def", 6), spd=kw.get("e_spd", 8), color=enemy_color)
    inv = Inventory()
    return stats, enemy, inv, Battle(stats, enemy, inv, kw.get("rng", FixedRNG()), str)


class TestProgression(unittest.TestCase):
    def test_average_stats_grow_and_xp_curve_steepens(self):
        prev = P.average_stats(1)
        self.assertEqual(prev, C.START_STATS)
        for lv in range(2, 30):
            cur = P.average_stats(lv)
            self.assertTrue(all(cur[s] >= prev[s] for s in P.STATS))
            prev = cur
        needs = [P.xp_needed(lv) for lv in range(1, 20)]
        self.assertEqual(needs, sorted(needs))
        self.assertGreater(P.xp_needed(10) / P.xp_needed(5), 3.5)         # quadratic: later levels cost far more

    def test_xp_reward_prefers_strong_enemies(self):
        self.assertGreater(P.xp_reward(10, 5), P.xp_reward(10, 10))
        self.assertLess(P.xp_reward(3, 20), P.xp_reward(3, 3))
        lo, hi = C.XP_RATIO_RANGE
        self.assertEqual(P.xp_reward(10, 1), round(C.XP_BASE * 10 * hi))  # ratio is clamped
        self.assertEqual(P.xp_reward(1, 100), max(1, round(C.XP_BASE * 1 * lo)))

    def test_enemy_level_follows_depth_with_a_capped_distance_bonus(self):
        mean = lambda d, dist: sum(P.enemy_level(d, dist, random.Random(i)) for i in range(300)) / 300
        self.assertLess(mean(0, 0), 1.6)
        self.assertGreater(mean(10, 0), mean(0, 0) + 3)                   # depth is the main driver
        far = mean(0, 10 ** 7) - mean(0, 0)
        self.assertLessEqual(far, C.DISTANCE_LEVEL_MAX + 1.1)             # distance alone adds only a little
        self.assertGreater(mean(0, 600), mean(0, 0))

    def test_cap_before_boss_and_no_cap_after(self):
        cap = int(C.BOSS_LEVEL * C.ENEMY_CAP_FRACTION)
        self.assertEqual(P.enemy_level_cap(), cap)
        lv = [P.enemy_level(500, 10 ** 6, random.Random(i)) for i in range(50)]
        self.assertTrue(max(lv) <= cap and cap - 1 <= max(lv))
        self.assertGreater(max(P.enemy_level(500, 10 ** 6, random.Random(i), boss_defeated=True) for i in range(50)), cap)
        self.assertGreaterEqual(min(P.enemy_level(-5, -5, random.Random(i)) for i in range(50)), 1)


class TestStatsGrowth(unittest.TestCase):
    def test_level_up_carries_xp_hands_out_points_and_adds_hp(self):
        s = PlayerStats()
        need = P.xp_needed(1)
        ups = s.add_xp(need + 3, random.Random(1))
        self.assertEqual((s.level, s.xp, len(ups)), (2, 3, 1))
        gained = sum(v // C.GROWTH_PER_POINT[k] for k, v in ups[0].gains.items())
        self.assertTrue(C.GROWTH_POINTS[0] <= gained <= C.GROWTH_POINTS[1])
        self.assertEqual(s.base["hp"], C.START_STATS["hp"] + ups[0].gains.get("hp", 0))
        self.assertEqual(s.hp, s.max_hp)

    def test_big_xp_gives_several_levels_and_current_hp_rises_by_the_gain(self):
        s = PlayerStats(); s.take_damage(30)
        before = s.hp
        ups = s.add_xp(P.xp_needed(1) + P.xp_needed(2) + 1, random.Random(2))
        self.assertEqual(s.level, 3)
        self.assertEqual(len(ups), 2)
        self.assertEqual(s.hp, before + sum(u.gains.get("hp", 0) for u in ups))

    def test_damage_kills_but_eating_cannot(self):
        s = PlayerStats()
        for _ in range(60):
            s.apply_hp(-40)
        self.assertEqual(s.hp, 1)
        self.assertFalse(s.take_damage(0))
        self.assertTrue(s.take_damage(5))
        self.assertEqual(s.hp, 0)


class TestEnemies(unittest.TestCase):
    def test_enemy_stats_and_colour(self):
        for level in (1, 9, 25):
            avg = P.average_stats(level)
            for i in range(60):
                e = make_enemy(level, random.Random(i))
                self.assertTrue(all(60 <= c <= 200 for c in e.color))
                self.assertEqual(e.hp, e.max_hp)
                for got, key in ((e.max_hp, "hp"), (e.atk, "atk"), (e.defense, "def"), (e.spd, "spd")):
                    lo = avg[key] * C.ENEMY_STRENGTH * (1 - C.ENEMY_STAT_VARIATION) - 1
                    hi = avg[key] * C.ENEMY_STRENGTH * (1 + C.ENEMY_STAT_VARIATION) + 1
                    self.assertTrue(lo <= got <= hi, (level, key, got))
        a, b = make_enemy(7, random.Random(5)), make_enemy(7, random.Random(5))
        self.assertEqual(a, b)


class TestBattleRules(unittest.TestCase):
    def test_tackle_damage_scales_with_target_hp_and_ratio(self):
        stats, enemy, inv, b = duel()
        self.assertTrue(b.act("tackle"))
        expected = round(base_damage(C.TACKLE_FRACTION, stats.atk, 6, 50))
        self.assertEqual(enemy.hp, 50 - expected)
        self.assertAlmostEqual(base_damage(0.4, 10, 10, 100), 20.0)       # equal stats: fraction / 2 of max HP

    def test_faster_side_acts_first_and_a_dead_enemy_does_not_strike_back(self):
        stats, enemy, inv, b = duel(e_hp=1, e_spd=1)                       # player is faster
        b.act("tackle")
        self.assertEqual(b.phase, "won")
        self.assertEqual(stats.hp, stats.max_hp, "enemy must not act after being defeated")
        stats, enemy, inv, b = duel(e_spd=99)                              # enemy is faster
        b.act("tackle")
        self.assertLess(stats.hp, stats.max_hp)
        self.assertLess(enemy.hp, enemy.max_hp)                            # both landed a hit this round

    def test_player_killed_first_never_acts_and_keeps_the_item(self):
        stats, enemy, inv, b = duel(e_spd=99, e_atk=999)
        stats.hp = 1
        inv.add(GREEN, 1)
        b.act("throw", 0)
        self.assertEqual(b.phase, "lost")
        self.assertEqual(inv.count(GREEN), 1)                              # the throw never happened
        self.assertEqual(enemy.hp, enemy.max_hp)
        self.assertFalse(b.act("tackle"))                                  # the battle is over

    def test_throw_uses_colour_matchup(self):
        # Green beats a red enemy (+120 degrees ahead), red loses to a green enemy.
        stats, enemy, inv, b = duel(enemy_color=(200.0, 60.0, 60.0), e_spd=1)
        inv.add(GREEN, 2)
        m = b.throw_multiplier(GREEN)
        self.assertGreater(m, 1.3)
        b.act("throw", 0)
        self.assertEqual(inv.count(GREEN), 1)                              # consumed
        dmg = 50 - enemy.hp
        self.assertGreater(dmg, round(base_damage(C.THROW_FRACTION, stats.atk, 6, 50)))
        self.assertGreater(throw_value(m), 1.0)

    def test_throw_with_a_bad_colour_heals_a_hurt_enemy_but_not_a_full_one(self):
        stats, enemy, inv, b = duel(enemy_color=(60.0, 200.0, 60.0), e_spd=1)
        inv.add(RED, 3)
        self.assertLess(b.throw_multiplier(RED), 0.7)
        b.act("throw", 0)                                                  # enemy at full HP: nothing to heal
        self.assertEqual(enemy.hp, enemy.max_hp)
        self.assertTrue(any("no effect" in line.lower() for line in b.log))
        enemy.hp = 20
        b.act("throw", 0)
        self.assertGreater(enemy.hp, 20)
        self.assertTrue(any("recovers" in line for line in b.log))

    def test_eating_in_battle_uses_the_turn(self):
        stats, enemy, inv, b = duel(e_spd=1)
        inv.add(RED, 1)
        c0 = stats.color
        b.act("eat", 0)
        self.assertEqual(inv.count(RED), 0)
        self.assertNotEqual(stats.color, c0)
        self.assertEqual(enemy.hp, enemy.max_hp)                           # no attack this round

    def test_throw_or_eat_needs_a_mineral_and_wastes_no_turn(self):
        stats, enemy, inv, b = duel()
        inv.add(ROCK, 1)
        for action, slot in (("throw", 0), ("eat", 0), ("throw", 5), ("eat", None)):
            self.assertFalse(b.act(action, slot))
        self.assertEqual((stats.hp, enemy.hp), (stats.max_hp, enemy.max_hp))
        self.assertTrue(any("mineral" in line.lower() for line in b.log))

    def test_flee_depends_on_speed(self):
        lo, hi = C.FLEE_LIMITS
        # equal speed -> 50%; slower enemy (spd 1 -> 71%) is easier to flee; much faster enemy bottoms out at the minimum
        for rng, e_spd, expect in ((FixedRNG(coin=0.49), 8, "fled"), (FixedRNG(coin=0.51), 8, "choose"),
                                   (FixedRNG(coin=0.70), 1, "fled"), (FixedRNG(coin=0.72), 1, "choose"),
                                   (FixedRNG(coin=lo - 0.01), 200, "fled"), (FixedRNG(coin=lo + 0.01), 200, "choose"),
                                   (FixedRNG(coin=hi - 0.01), -500, "fled"), (FixedRNG(coin=hi + 0.01), -500, "choose")):
            stats, enemy, inv, b = duel(e_spd=e_spd, rng=rng)
            b.act("flee")
            if expect == "choose":
                self.assertEqual(b.phase, "choose")
                self.assertLess(stats.hp, stats.max_hp, "a failed flee costs a hit")
            else:
                self.assertEqual(b.phase, "fled")

    def test_win_gives_xp_and_level_ups(self):
        stats, enemy, inv, b = duel(e_hp=1, level=4)
        stats.xp = P.xp_needed(1) - 1
        b.act("tackle")
        self.assertEqual(b.phase, "won")
        self.assertEqual(b.xp_gained, P.xp_reward(4, 1))
        self.assertGreaterEqual(stats.level, 2)
        self.assertTrue(any("LEVEL UP" in line for line in b.log))

    def test_matchup_applies_to_enemy_attacks_too(self):
        s1, e1, i1, b1 = duel(player_color=(60.0, 200.0, 60.0), enemy_color=(200.0, 60.0, 60.0), e_spd=1)   # I am green, enemy red
        s2, e2, i2, b2 = duel(player_color=(200.0, 60.0, 60.0), enemy_color=(60.0, 200.0, 60.0), e_spd=1)   # I am red, enemy green
        b1.act("tackle"); b2.act("tackle")
        self.assertLess(b1.stats.max_hp - s1.hp, b2.stats.max_hp - s2.hp)   # good colour: take less damage
        self.assertGreater(e1.max_hp - e1.hp, e2.max_hp - e2.hp)            # ... and deal more

    def test_fair_fights_are_mostly_won_and_short(self):
        for level in (1, 8, 15):
            wins = rounds = 0
            for i in range(300):
                r = random.Random(i)
                s = PlayerStats(level=1)
                while s.level < level:
                    s.add_xp(P.xp_needed(s.level), r)
                s.restore_full()
                b = Battle(s, make_enemy(level, r), Inventory(), r, str)
                n = 0
                while b.phase == "choose" and n < 100:
                    b.act("tackle"); n += 1
                wins += b.phase == "won"; rounds += n
            self.assertGreater(wins / 300, 0.85, level)
            self.assertLess(rounds / 300, 8, level)


class TestEncounters(unittest.TestCase):
    def test_nothing_during_the_safe_steps(self):
        t = EncounterTracker(safe_steps=12, chance=1.0)
        rng = random.Random(1)
        for _ in range(12):
            self.assertFalse(t.walk(1.0, False, rng))
        self.assertTrue(t.walk(1.0, False, rng))                            # step 13 with chance 1.0
        self.assertEqual(t.steps, 0)                                        # counter restarts

    def test_wood_is_safe_and_not_counted(self):
        t = EncounterTracker(safe_steps=2, chance=1.0)
        rng = random.Random(1)
        for _ in range(500):
            self.assertFalse(t.walk(1.0, True, rng))
        self.assertEqual(t.steps, 0)
        self.assertFalse(t.walk(1.0, False, rng)); self.assertFalse(t.walk(1.0, False, rng))
        self.assertTrue(t.walk(1.0, False, rng))

    def test_partial_steps_accumulate(self):
        t = EncounterTracker(safe_steps=0, chance=1.0)
        rng = random.Random(1)
        self.assertFalse(t.walk(0.4, False, rng)); self.assertFalse(t.walk(0.4, False, rng))
        self.assertTrue(t.walk(0.4, False, rng))                             # 1.2 blocks walked in total

    def test_average_gap_matches_the_settings(self):
        t = EncounterTracker()
        rng = random.Random(3)
        gaps, walked = [], 0
        for _ in range(60000):
            walked += 1
            if t.walk(1.0, False, rng):
                gaps.append(walked); walked = 0
        mean = sum(gaps) / len(gaps)
        expected = C.ENCOUNTER_SAFE_STEPS + 1 / C.ENCOUNTER_CHANCE
        self.assertAlmostEqual(mean, expected, delta=expected * 0.12)
        self.assertGreaterEqual(min(gaps), C.ENCOUNTER_SAFE_STEPS + 1)

    def test_reset_after_loading(self):
        t = EncounterTracker(safe_steps=5, chance=1.0)
        rng = random.Random(1)
        for _ in range(5):
            t.walk(1.0, False, rng)
        t.reset()
        self.assertFalse(t.walk(1.0, False, rng))


class TestDeath(unittest.TestCase):
    def test_everything_carried_is_lost_but_progress_stays(self):
        s = PlayerStats(level=4, color=(100.0, 150.0, 90.0)); s.take_damage(10 ** 6)
        inv = Inventory(); inv.add(ROCK, 70); inv.add(GREEN, 3)
        lost = apply_death(inv, s)
        self.assertEqual(lost, 3)
        self.assertEqual(inv.used_slots(), 0)
        self.assertEqual((s.hp, s.level, s.color), (s.max_hp, 4, (100.0, 150.0, 90.0)))


class TestSavedProgress(unittest.TestCase):
    def test_xp_and_grown_stats_roundtrip(self):
        s = PlayerStats()
        s.add_xp(P.xp_needed(1) + P.xp_needed(2) + 5, random.Random(4)); s.take_damage(7)
        with tempfile.TemporaryDirectory() as tmp:
            store = SaveStore(Path(tmp) / "w")
            game_save.save_game(store, flat_world(), Inventory(), {}, (0, 0, 0), s)
            r = game_save.restore_stats(SaveStore(store.dir).load_meta())
        self.assertEqual((r.level, r.xp, r.hp, r.base, r.color), (s.level, s.xp, s.hp, s.base, s.color))

    def test_old_saves_and_bad_values_fall_back(self):
        r = game_save.restore_stats({"stats": {"level": 6, "hp": 80, "color": [100, 100, 100]}})   # stage-3 save
        self.assertEqual((r.level, r.xp, r.base), (6, 0, P.average_stats(6)))
        r = game_save.restore_stats({"stats": {"level": 3, "xp": 10 ** 9, "base": {"hp": -1, "atk": "x"}}})
        self.assertEqual((r.xp, r.base), (0, P.average_stats(3)))
        r = game_save.restore_stats({"stats": {"level": 2, "base": {"hp": 70, "atk": 12, "def": 9, "spd": 10}, "hp": 1000}})
        self.assertEqual((r.base["hp"], r.hp), (70, 70))


if __name__ == "__main__":
    unittest.main()
