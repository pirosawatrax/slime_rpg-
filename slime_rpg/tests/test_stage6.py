"""Stage 6 tests: village commands, the boss and his lair, post-boss colours, saved village state."""
import json
import random
import tempfile
import unittest
from pathlib import Path

import numpy as np

import config as C
import items
import strings as T
from blocks import AIR, WOOD, ROCK, hardness_at
from game import battle as B, progression as P, village_data as VD
from game.inventory import Inventory
from game.stats import PlayerStats
from game.village import BossGate, Context, Flags, VillageBook, VillageSession
from save import game_save
from save.store import SaveStore
from tests.test_battle import FixedRNG, duel, GREEN, RED
from tests.test_core import flat_world
from world import boss_arena, villages
from world.world import World
from world.worldgen import generate_chunk_full

VILLAGE = villages.village_in_region(C.SEED, 0, 0)
OTHER = villages.village_in_region(C.SEED, 1, 0) or villages.village_in_region(C.SEED, -1, 0)


def common(n=1, variant=0):
    codes = [int(c) for c in items.TIER_CODES[0]]
    return items.item_of(codes[variant]), n


NOON = 0.5 * C.DAY_LENGTH
MIDNIGHT = 0.0


def make_ctx(**kw):
    ctx = Context(C.SEED, kw.get("inventory") or Inventory(), kw.get("stats") or PlayerStats(), kw.get("flags") or Flags(),
                  kw.get("book") or VillageBook(), lambda i: f"item{i}", kw.get("respawn"), kw.get("world_time", NOON))
    return ctx


def session(ctx=None, village=VILLAGE):
    ctx = ctx or make_ctx()
    return ctx, VillageSession(village, ctx)


def pick(s, label_start):
    sc = s.screen()
    for i, label in enumerate(sc.options):
        if label.startswith(label_start):
            s.choose(i)
            return s.screen()
    raise AssertionError(f"no option {label_start!r} in {sc.options}")


class TestVillageMenus(unittest.TestCase):
    def test_main_menu_and_services_only_after_the_boss(self):
        ctx, s = session()
        sc = s.screen()
        self.assertEqual(sc.options, ["Inn", "Storage", "Trade", "Guide", "Request", "Leave"])
        self.assertLessEqual(len(sc.options), 10)
        ctx.flags.boss_defeated = True
        self.assertIn("Services", s.screen().options)
        pick(s, "Leave")
        self.assertTrue(s.closed)

    def test_inn_costs_a_common_mineral_heals_and_sets_the_respawn_point(self):
        ctx, s = session()
        ctx.stats.take_damage(20)
        pick(s, "Inn")
        sc = pick(s, "Stay")
        self.assertIn("mineral to pay", sc.note)                          # nothing to pay with
        self.assertEqual(ctx.respawn, None)
        item, n = common(3)
        ctx.inventory.add(item, n)
        sc = pick(s, "Stay")
        self.assertEqual(sc.note, T.V_STAY_OK)
        self.assertEqual(ctx.stats.hp, ctx.stats.max_hp)
        self.assertEqual(ctx.respawn, VILLAGE.stand)
        self.assertEqual(ctx.inventory.count(item), 2)
        self.assertIn("this village", " ".join(s.screen().lines))
        sc = pick(s, "Stay")                                             # rested and registered: free, no effect
        self.assertEqual(sc.note, T.V_STAY_NOTHING)
        self.assertEqual(ctx.inventory.count(item), 2)

    def test_a_night_at_the_inn_ends_in_the_morning(self):
        from game import daytime
        for hour in (21, 23.5, 2, 4.5):                                     # any time of the night
            ctx = make_ctx(world_time=hour / 24 * C.DAY_LENGTH)
            before = ctx.world_time
            s = VillageSession(VILLAGE, ctx)
            self.assertTrue(daytime.is_night(before))
            ctx.inventory.add(*common(2))
            pick(s, "Inn")
            sc = pick(s, "Stay")
            self.assertEqual(sc.note, T.V_STAY_OK_MORNING)
            self.assertFalse(daytime.is_night(ctx.world_time))
            self.assertGreater(ctx.world_time, before, "time only moves forward")
            self.assertAlmostEqual(daytime.phase(ctx.world_time), C.START_TIME, places=6)
            self.assertLess(ctx.world_time - before, C.DAY_LENGTH)
            self.assertEqual(ctx.inventory.count(common(0)[0]), 1)            # the usual fee, once
        # healthy and already registered, but it is night: staying is still allowed, and it skips the night
        ctx = make_ctx(world_time=MIDNIGHT, respawn=VILLAGE.stand)
        ctx.inventory.add(*common(2))
        s = VillageSession(VILLAGE, ctx)
        pick(s, "Inn")
        self.assertEqual(pick(s, "Stay").note, T.V_STAY_OK_MORNING)

    def test_a_day_at_the_inn_does_not_change_the_time(self):
        for hour in (7, 12, 16.5):
            ctx = make_ctx(world_time=hour / 24 * C.DAY_LENGTH)
            before = ctx.world_time
            ctx.stats.take_damage(10)
            ctx.inventory.add(*common(2))
            s = VillageSession(VILLAGE, ctx)
            pick(s, "Inn")
            self.assertEqual(pick(s, "Stay").note, T.V_STAY_OK)
            self.assertEqual(ctx.world_time, before)

    def test_wake_time_function(self):
        from game import daytime
        day = C.DAY_LENGTH
        morning = C.START_TIME * day
        self.assertEqual(daytime.wake_time(NOON), NOON)
        self.assertAlmostEqual(daytime.wake_time(0.0), morning)                       # after midnight: the same morning
        self.assertAlmostEqual(daytime.wake_time(0.20 * day), morning)
        self.assertAlmostEqual(daytime.wake_time(0.90 * day), day + morning)          # before midnight: the next morning
        self.assertAlmostEqual(daytime.wake_time(3 * day + 0.8 * day), 4 * day + morning)
        for t in (0.0, 0.1 * day, 0.8 * day, 0.99 * day, 5.2 * day):
            self.assertFalse(daytime.is_night(daytime.wake_time(t)))

    def test_staying_at_another_village_moves_the_respawn_point(self):
        if OTHER is None:
            self.skipTest("no second village")
        ctx, s = session()
        item, n = common(5)
        ctx.inventory.add(item, n)
        pick(s, "Inn"); pick(s, "Stay")
        s2 = VillageSession(OTHER, ctx)
        pick(s2, "Inn"); pick(s2, "Stay")
        self.assertEqual(ctx.respawn, OTHER.stand)
        self.assertEqual(ctx.inventory.count(item), 3)

    def test_the_fee_can_be_paid_with_any_colour_plainest_first(self):
        ctx, s = session()
        ctx.stats.take_damage(5)
        rare = items.item_of(items.code_from_rgb((200, 60, 60)))
        ctx.inventory.add(rare, 2)
        ctx.inventory.add(3, 10)                                            # rock never pays
        sc = pick(s, "Inn")
        self.assertIn(f"You would pay with: item{rare}", " ".join(sc.lines))
        self.assertEqual(pick(s, "Stay").note, T.V_STAY_OK, "a vivid mineral is enough to stay")
        self.assertEqual(ctx.inventory.count(rare), 1)
        plain, _ = common(1)
        ctx.inventory.add(plain, 2)
        ctx.stats.take_damage(5)
        self.assertIn(f"item{plain}", " ".join(s.screen().lines))           # the plainest colour is offered first
        pick(s, "Stay")
        self.assertEqual((ctx.inventory.count(plain), ctx.inventory.count(rare)), (1, 1))

    def test_rock_and_blocks_never_pay_a_fee(self):
        ctx, s = session()
        ctx.stats.take_damage(5)
        ctx.inventory.add(3, 30)
        ctx.inventory.add(4, 30)
        sc = pick(s, "Inn")
        self.assertIn(T.V_FEE_NONE, sc.lines)
        self.assertIn("mineral to pay", pick(s, "Stay").note)
        self.assertEqual(ctx.stats.hp, ctx.stats.max_hp - 5)

    def test_strict_mode_accepts_only_common_colours(self):
        from unittest import mock
        with mock.patch.object(C, "FEE_ANY_MINERAL", False):
            ctx, s = session()
            ctx.stats.take_damage(5)
            ctx.inventory.add(items.item_of(items.code_from_rgb((200, 60, 60))), 3)
            pick(s, "Inn")
            self.assertIn("common (muted-colour) mineral", pick(s, "Stay").note)
            ctx.inventory.add(*common(1))
            self.assertEqual(pick(s, "Stay").note, T.V_STAY_OK)

    def test_resting_when_nothing_is_needed_says_why_and_costs_nothing(self):
        ctx, s = session(make_ctx(respawn=VILLAGE.stand))                   # already registered here, full HP, daytime
        ctx.inventory.add(*common(2))
        pick(s, "Inn")
        self.assertEqual(pick(s, "Stay").note, T.V_STAY_NOTHING)
        self.assertEqual(ctx.inventory.count(common(0)[0]), 2)

    def test_storage_deposit_fee_and_withdraw(self):
        ctx, s = session()
        fee_item, _ = common(1, 0)
        rock = 3
        ctx.inventory.add(fee_item, 4)
        ctx.inventory.add(rock, 40)
        pick(s, "Storage")
        pick(s, "Deposit")
        sc = s.screen()
        self.assertTrue(any(o.startswith("item3 x40") for o in sc.options), sc.options)
        s.choose(next(i for i, o in enumerate(sc.options) if o.startswith("item3")))
        self.assertIn("Stored", s.screen().note)
        self.assertEqual(ctx.inventory.count(rock), 0)
        self.assertEqual(ctx.inventory.count(fee_item), 3)                # one common mineral paid
        self.assertEqual(ctx.book.get(VILLAGE.id).storage.count(rock), 40)
        pick(s, "Back"); pick(s, "Withdraw")
        pick(s, "item3")
        self.assertEqual(ctx.inventory.count(rock), 40)
        self.assertEqual(ctx.inventory.count(fee_item), 3)                # taking out is free

    def test_deposit_without_a_fee_mineral_does_nothing(self):
        ctx, s = session()
        ctx.inventory.add(3, 10)
        pick(s, "Storage"); pick(s, "Deposit"); pick(s, "item3")
        self.assertIn("mineral to pay", s.screen().note)
        self.assertEqual(ctx.inventory.count(3), 10)
        self.assertEqual(ctx.book.get(VILLAGE.id).storage.used_slots(), 0)

    def test_the_fee_can_come_from_the_stack_being_stored_only_if_something_is_left(self):
        item, _ = common(1)
        ctx, s = session()
        ctx.inventory.add(item, 1)                                          # a single mineral: it cannot pay for itself
        pick(s, "Storage"); pick(s, "Deposit"); pick(s, "item")
        self.assertIn("mineral to pay", s.screen().note)
        self.assertEqual(ctx.inventory.count(item), 1)
        ctx.inventory.add(item, 4)                                          # now 5: pay 1, store 4
        pick(s, "item")
        self.assertEqual(ctx.book.get(VILLAGE.id).storage.count(item), 4)
        self.assertEqual(ctx.inventory.count(item), 0)

    def test_storage_full_and_partial_moves(self):
        ctx, s = session()
        fee, _ = common()
        ctx.inventory.add(fee, 3)
        store = ctx.book.get(VILLAGE.id).storage
        for i in range(len(store.slots)):                                   # fill every slot with distinct stacks
            store.slots[i] = [3, 64] if i % 2 else [2, 64]
        ctx.inventory.add(1, 5)
        pick(s, "Storage"); pick(s, "Deposit"); pick(s, "item1")
        self.assertEqual(s.screen().note, T.V_STORAGE_FULL)
        self.assertEqual(ctx.inventory.count(1), 5)
        self.assertEqual(ctx.inventory.count(fee), 3, "no fee when nothing could be stored")
        ctx2, s2 = session(make_ctx(inventory=Inventory(2)))                # inventory with no room: withdraw is partial / refused
        ctx2.inventory.slots = [[2, 64], [3, 64]]
        ctx2.book.get(VILLAGE.id).storage.add(2, 10)
        pick(s2, "Storage"); pick(s2, "Withdraw"); pick(s2, "item2")
        self.assertEqual(s2.screen().note, T.V_NO_ROOM)
        self.assertEqual(ctx2.book.get(VILLAGE.id).storage.count(2), 10)

    def test_each_village_has_its_own_storage(self):
        if OTHER is None:
            self.skipTest("no second village")
        ctx, s = session()
        fee, _ = common()
        ctx.inventory.add(fee, 4); ctx.inventory.add(3, 5)
        pick(s, "Storage"); pick(s, "Deposit"); pick(s, "item3")
        self.assertEqual(ctx.book.get(OTHER.id).storage.count(3), 0)

    def test_long_lists_are_paged(self):
        ctx, s = session()
        for i in range(12):
            ctx.inventory.add(items.item_of(i * 7), 1)                      # 12 different stacks
        ctx.inventory.add(*common(2))
        pick(s, "Storage"); pick(s, "Deposit")
        sc = s.screen()
        self.assertEqual(len(sc.options), 10)                               # 8 entries + More + Back
        self.assertEqual(sc.options[-2], "More...")
        s.choose(8)
        sc2 = s.screen()
        self.assertNotEqual(sc.options[0], sc2.options[0])
        self.assertLessEqual(len(sc2.options), 10)
        pick(s, "Back")
        self.assertEqual(s.screen().options[0], "Deposit")

    def test_trade_offers_exchange_the_wanted_colours(self):
        offers = VD.trade_offers(C.SEED, VILLAGE)
        self.assertEqual(len(offers), 3)
        self.assertEqual(offers, VD.trade_offers(C.SEED, VILLAGE))
        if OTHER is not None:
            self.assertNotEqual(offers, VD.trade_offers(C.SEED, OTHER))
        ctx, s = session()
        o = offers[0]
        sc = pick(s, "Trade")
        self.assertEqual(len(sc.options), 4)                                # three offers + Back
        self.assertTrue(sc.options[0].startswith("2 item"), sc.options[0])   # "<qty> <wanted mineral>  ->  <goods>"
        self.assertIn("Wood", T.BLOCK_NAMES["wood"])
        s.choose(0)
        self.assertIn("do not have", s.screen().note)
        ctx.inventory.add(o.want_item, 5)
        s.choose(0)
        self.assertEqual(ctx.inventory.count(o.give_item), o.give_qty)
        self.assertEqual(ctx.inventory.count(o.want_item), 5 - o.want_qty)

    def test_trade_with_no_room_changes_nothing(self):
        offers = VD.trade_offers(C.SEED, VILLAGE)
        o = offers[0]
        ctx, s = session(make_ctx(inventory=Inventory(1)))
        ctx.inventory.add(o.want_item, o.want_qty)                          # the only slot holds what she wants
        ctx.inventory.slots[0][1] = o.want_qty
        pick(s, "Trade")
        s.choose(0)                                                         # the goods (Wood) then fit: slot freed by payment
        self.assertEqual(ctx.inventory.count(o.give_item), o.give_qty)
        ctx2, s2 = session(make_ctx(inventory=Inventory(1)))
        ctx2.inventory.add(o.want_item, o.want_qty + 1)
        pick(s2, "Trade")
        s2.choose(0)
        self.assertEqual(s2.screen().note, T.V_NO_ROOM)
        self.assertEqual(ctx2.inventory.count(o.want_item), o.want_qty + 1)   # undone, nothing lost

    def test_guide_tells_where_the_boss_lives_and_marks_it_known(self):
        ctx, s = session()
        pick(s, "Guide")
        for topic in ("Dangers", "Colours", "Minerals"):
            sc = pick(s, topic)
            self.assertTrue(len(sc.lines) >= 3)
            pick(s, "Back")
        self.assertFalse(ctx.flags.boss_known)
        sc = pick(s, "The Slime King")
        ax, az = boss_arena.arena_center(C.SEED)
        text = " ".join(sc.lines)
        self.assertIn(f"x {ax}", text); self.assertIn(f"z {az}", text); self.assertIn(f"level {C.BOSS_LEVEL}", text)
        self.assertTrue(ctx.flags.boss_known)
        ctx.flags.boss_defeated = True
        self.assertIn("is gone", " ".join(s.screen().lines))

    def test_request_pays_in_storage_slots_once(self):
        item, qty = VD.client_request(C.SEED, VILLAGE)
        self.assertEqual(items.tier(items.code_of(item)), 2)
        ctx, s = session()
        pick(s, "Request")
        s.choose(0)
        self.assertIn("do not have", s.screen().note)
        ctx.inventory.add(item, qty + 1)
        s.choose(0)
        st = ctx.book.get(VILLAGE.id)
        self.assertTrue(st.request_done)
        self.assertEqual(len(st.storage.slots), C.STORAGE_SLOTS + C.STORAGE_REQUEST_BONUS)
        self.assertEqual(ctx.inventory.count(item), 1)
        self.assertEqual(s.screen().options, ["Back"])                      # nothing more to hand over

    def test_services_after_the_boss_are_paid_in_new_colours_once_per_village(self):
        costs = VD.service_costs(C.SEED, VILLAGE)
        for item, qty in costs.values():
            self.assertFalse(items.in_base_range(items.code_of(item)), "post-boss colours")
        ctx, s = session(make_ctx(flags=Flags(boss_defeated=True)))
        ctx.inventory.add(*costs["expand"]); ctx.inventory.add(*costs["tonic"])
        pick(s, "Services")
        hp0 = ctx.stats.max_hp
        s.choose(0); s.choose(1)
        st = ctx.book.get(VILLAGE.id)
        self.assertEqual(len(st.storage.slots), C.STORAGE_SLOTS + C.STORAGE_EXPAND_BONUS)
        self.assertEqual((ctx.stats.max_hp, ctx.stats.hp), (hp0 + C.TONIC_HP, hp0 + C.TONIC_HP))
        ctx.inventory.add(*costs["expand"])
        s.choose(0)
        self.assertEqual(s.screen().note, T.V_S_BOUGHT)
        self.assertEqual(len(st.storage.slots), C.STORAGE_SLOTS + C.STORAGE_EXPAND_BONUS)
        ctx2, s2 = session(make_ctx(flags=Flags(boss_defeated=False)))     # not reachable before the boss
        s2._go("services")
        s2.screen()
        s2._do_service("tonic")
        self.assertEqual(ctx2.stats.max_hp, 50)

    def test_boss_gate(self):
        ctx = make_ctx()
        g = BossGate(ctx)
        sc = g.screen()
        self.assertEqual(sc.options, ["Fight", "Not yet"])
        g.choose(1)
        self.assertTrue(g.closed and not g.fight)
        g = BossGate(ctx); g.screen(); g.choose(0)
        self.assertTrue(g.closed and g.fight)
        ctx.flags.boss_defeated = True
        g = BossGate(ctx)
        self.assertEqual(g.screen().options, ["Leave"])
        g.choose(0)
        self.assertFalse(g.fight)


class TestBossLair(unittest.TestCase):
    def test_arena_is_deterministic_on_land_and_far_away(self):
        ax, az = boss_arena.arena_center(C.SEED)
        self.assertEqual((ax, az), boss_arena.arena_center(C.SEED))
        d = (ax * ax + az * az) ** 0.5
        self.assertTrue(C.BOSS_DISTANCE[0] - 3 <= d <= C.BOSS_DISTANCE[1] + 3, d)
        from world.worldgen_heights import surface_heights
        self.assertGreaterEqual(int(surface_heights(C.SEED, ax, az)), C.SEA_LEVEL + 1)
        self.assertNotEqual(boss_arena.arena_center(C.SEED), boss_arena.arena_center(C.SEED + 5))

    def test_room_tile_and_posts_in_every_chunk_order(self):
        ax, az = boss_arena.arena_center(C.SEED)
        chunks = sorted({((ax + dx) >> 4, (az + dz) >> 4) for dx in range(-10, 11) for dz in range(-10, 11)})
        worlds = []
        for order in (chunks, list(reversed(chunks))):
            w = World()
            for c in order:
                w.get_chunk(*c)
            worlds.append(w)
            self.assertEqual(w.get_block(ax, 0, az), WOOD, "the challenge tile")
            for dx, dz in ((-8, -8), (0, 0), (8, 8), (-8, 8), (3, -4)):
                for y in range(1, C.ARENA_HEIGHT + 1):
                    self.assertEqual(w.get_block(ax + dx, y, az + dz), AIR if abs(dx) != 2 or abs(dz) != 2 else WOOD)
            self.assertEqual(w.get_block(ax + 2, 2, az + 2), WOOD)          # a post
            self.assertEqual(w.get_block(ax + 9, 3, az), ROCK)              # solid wall beyond the room
            self.assertEqual(w.get_block(ax, C.ARENA_HEIGHT + 1, az), ROCK)  # solid ceiling
            self.assertIsNone(w.get_mineral(ax + 1, 3, az))
        for dx in range(-9, 10):
            for dz in range(-9, 10):
                for y in range(0, 11):
                    self.assertEqual(worlds[0].get_block(ax + dx, y, az + dz), worlds[1].get_block(ax + dx, y, az + dz))
        self.assertIsNone(hardness_at(WOOD, 0), "the floor cannot be dug out")
        self.assertTrue(boss_arena.arena_at(C.SEED, ax, az))
        self.assertFalse(boss_arena.arena_at(C.SEED, ax + 1, az))
        self.assertEqual(boss_arena.arena_near_chunk(C.SEED, ax >> 4, az >> 4), (ax, az))
        self.assertIsNone(boss_arena.arena_near_chunk(C.SEED, (ax >> 4) + 5, az >> 4))


class TestSlimeKing(unittest.TestCase):
    def king(self, **kw):
        stats = kw.get("stats") or PlayerStats(level=kw.get("level", 25))
        rng = kw.get("rng") or random.Random(kw.get("seed", 1))
        boss = B.make_boss(rng)
        inv = kw.get("inv") or Inventory()
        return stats, boss, inv, B.Battle(stats, boss, inv, rng, str, boss=True)

    def test_make_boss_is_fixed_stats_of_the_boss_level(self):
        a, b = B.make_boss(random.Random(1)), B.make_boss(random.Random(99))
        avg = P.average_stats(C.BOSS_LEVEL)
        self.assertEqual((a.level, a.hp, a.atk, a.defense, a.spd), (b.level, b.hp, b.atk, b.defense, b.spd))
        self.assertEqual(a.level, C.BOSS_LEVEL)
        self.assertEqual(a.max_hp, round(avg["hp"] * C.BOSS_STAT_MULT["hp"]))
        self.assertEqual(a.defense, round(avg["def"] * C.BOSS_STAT_MULT["def"]))
        self.assertTrue(all(60 <= c <= 200 for c in a.color))
        self.assertTrue(all(40 <= c <= 220 for c in B.make_boss(random.Random(1), extended=True).color))

    def test_colour_changes_every_round_and_the_next_colour_is_known_in_advance(self):
        stats, boss, inv, b = self.king()
        b.take_events()
        for _ in range(4):
            before, announced = boss.color, b.next_color
            self.assertGreaterEqual(__import__("game.colors", fromlist=["x"]).distance(before, announced), C.BOSS_COLOR_MIN_DISTANCE)
            stats.restore_full()
            b.act("tackle")
            self.assertEqual(boss.color, announced, "the colour shown as 'next' is the one he takes")
            ev = b.take_events()
            self.assertEqual(ev[-1].kind, "note")
            self.assertIn("shifts to RGB", ev[-1].text)
            self.assertEqual(ev[-1].snap["enemy_color"], announced)
            self.assertEqual(ev[-1].snap["boss_next"], b.next_color)
            self.assertNotEqual(b.next_color, announced)

    def test_no_colour_change_once_the_fight_is_over(self):
        stats, boss, inv, b = self.king()
        stats.hp = 1
        boss.spd = 999
        b.take_events()
        b.act("tackle")
        self.assertEqual(b.phase, "lost")
        self.assertFalse(any("shifts" in e.text for e in b.take_events()))

    def test_one_hit_never_takes_more_than_the_cap(self):
        cap = round(C.BOSS_DAMAGE_CAP * B.make_boss(random.Random(1)).max_hp)
        stats = PlayerStats(level=1, hp=None)
        stats.base.update({"hp": 10 ** 5, "atk": 10 ** 5, "def": 10 ** 5, "spd": 10 ** 5})
        stats.restore_full()
        for _ in range(3):
            stats2, boss, inv, b = self.king(stats=stats)
            inv.add(GREEN, 5)
            hits = 0
            while b.phase == "choose" and hits < 30:
                before = boss.hp
                b.act("tackle")
                self.assertLessEqual(before - boss.hp, cap)
                hits += 1
            self.assertGreaterEqual(hits, round(1 / C.BOSS_DAMAGE_CAP), "at least 5 hits are always needed")
            self.assertEqual(b.phase, "won")
        stats3, boss, inv, b = self.king(stats=stats)
        inv.add(items.item_of(items.code_from_rgb((60, 200, 60))), 3)
        boss.color = (200.0, 60.0, 60.0)                                   # green beats red: the biggest possible throw
        b.next_color = (60.0, 60.0, 200.0)
        before = boss.hp
        b.act("throw", 0)
        self.assertEqual(before - boss.hp, cap)

    def test_no_escape(self):
        stats, boss, inv, b = self.king()
        b.take_events()
        color = boss.color
        self.assertFalse(b.act("flee"))
        ev = b.take_events()
        self.assertEqual(len(ev), 1)
        self.assertIn("no escape", ev[0].text.lower())
        self.assertEqual((b.phase, stats.hp, boss.color), ("choose", stats.max_hp, color))

    def test_victory_gives_triple_xp_and_the_flag(self):
        stats, boss, inv, b = self.king(level=30)
        boss.hp = 1
        boss.spd = 1
        b.act("tackle")
        self.assertEqual((b.phase, b.boss_won), ("won", True))
        self.assertEqual(b.xp_gained, round(P.xp_reward(C.BOSS_LEVEL, 30) * C.BOSS_XP_MULT))
        self.assertTrue(any("Slime King is beaten" in line for line in b.log))

    def test_a_normal_battle_is_not_a_boss_battle(self):
        stats, enemy, inv, b = duel()
        self.assertFalse(b.boss)
        self.assertFalse(b.snapshot()["boss"])
        self.assertIsNone(b.next_color)
        stats, enemy, inv, b = duel(rng=FixedRNG(coin=0.0))
        self.assertTrue(b.act("flee"))                                      # an ordinary slime can be fled from
        self.assertEqual(b.phase, "fled")

    def test_skilled_play_beats_plain_tackles(self):
        """The balance the numbers were chosen for: colours make the fight winnable below the boss's level."""
        from game import colors

        def fight(level, smart, seed):
            r = random.Random(seed)
            s = PlayerStats(level=1)
            while s.level < level:
                s.add_xp(P.xp_needed(s.level), r)
            s.restore_full()
            inv = Inventory()
            if smart:
                for c in r.sample([int(c) for c in np.concatenate(items.TIER_CODES)], 12):
                    inv.add(items.item_of(c), 3)
            b = B.Battle(s, B.make_boss(r), inv, r, str, boss=True)
            for _ in range(80):
                if b.phase != "choose":
                    break
                act, slot = "tackle", None
                minerals = [(i, sl[0]) for i, sl in enumerate(inv.slots) if sl]
                if smart and s.hp < 0.4 * s.max_hp and minerals:
                    i, it = min(minerals, key=lambda t: colors.distance(s.color, items.rgb(items.code_of(t[1]))))
                    if colors.distance(s.color, items.rgb(items.code_of(it))) < C.EAT_SAFE_DISTANCE:
                        act, slot = "eat", i
                if act == "tackle" and smart and minerals:
                    i, it = max(minerals, key=lambda t: b.throw_multiplier(t[1]))
                    if b.throw_multiplier(it) >= 1.25:
                        act, slot = "throw", i
                b.act(act, slot)
            return b.phase == "won"

        rate = lambda level, smart: sum(fight(level, smart, i) for i in range(60)) / 60
        self.assertLess(rate(25, False), 0.15)                             # plain tackles at level 25: hopeless
        self.assertGreater(rate(25, True), 0.45)                           # ... but playing the colours wins often
        self.assertGreater(rate(35, False), 0.70)                          # an over-levelled player gets through, slowly
        self.assertLess(rate(15, True), 0.10)                              # far too early: still no


class TestPostBossColours(unittest.TestCase):
    def test_ore_positions_stay_and_new_colours_only_appear_after_the_boss(self):
        any_new = 0
        for cx, cz in ((0, 0), (3, -2), (-4, 5)):
            _, base = generate_chunk_full(C.SEED, cx, cz, extended=False)
            _, ext = generate_chunk_full(C.SEED, cx, cz, extended=True)
            self.assertTrue(((base > 0) == (ext > 0)).all(), "the same cells hold ore")
            codes_b = base[base > 0].astype(int) - 1
            codes_e = ext[ext > 0].astype(int) - 1
            self.assertTrue(all(items.in_base_range(int(c)) for c in codes_b))
            new = [c for c in codes_e if not items.in_base_range(int(c))]
            any_new += len(new)
            kept = (base == ext) & (base > 0)
            self.assertTrue(kept.sum() > 0.45 * (base > 0).sum(), "most existing ore keeps its colour")
        self.assertGreater(any_new, 20)

    def test_world_flag_and_forgetting_unmodified_chunks(self):
        w = World()
        self.assertFalse(w.extended)
        w.get_chunk(0, 0); w.get_chunk(1, 0)
        w.set_block(3, 40, 3, AIR)                                          # chunk (0, 0) is modified
        before = w.chunks[(1, 0)].minerals.copy()
        w.extended = True
        w.forget_unmodified()
        self.assertIn((0, 0), w.chunks)
        self.assertNotIn((1, 0), w.chunks)
        w.get_chunk(1, 0)
        after = w.chunks[(1, 0)].minerals
        self.assertTrue(((before > 0) == (after > 0)).all())
        self.assertFalse((before == after).all(), "the regenerated chunk holds new colours")

    def test_enemies_and_levels_lift_their_limits(self):
        cap = P.enemy_level_cap()
        self.assertIsNone(P.enemy_level_cap(boss_defeated=True))
        self.assertGreater(P.enemy_level(200, 10 ** 6, random.Random(1), boss_defeated=True), cap)
        self.assertTrue(all(40 <= c <= 220 for c in B.make_enemy(5, random.Random(2), extended=True).color))
        wide = [B.make_enemy(5, random.Random(i), extended=True).color for i in range(200)]
        self.assertTrue(any(min(c) < 60 or max(c) > 200 for c in wide))


class TestSavedVillageState(unittest.TestCase):
    def test_everything_round_trips(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = SaveStore(Path(tmp) / "w")
            ctx = make_ctx(flags=Flags(boss_defeated=True, boss_known=True), respawn=VILLAGE.stand)
            st = ctx.book.get(VILLAGE.id)
            st.storage.add(3, 40); st.storage.add(items.item_of(77), 3); st.storage.grow(10)
            st.request_done, st.tonic = True, True
            game_save.save_game(store, flat_world(), Inventory(), {}, (0, 0, 0), ctx.stats, 5.0, game=ctx)
            meta = SaveStore(store.dir).load_meta()
            self.assertEqual(game_save.restore_flags(meta), Flags(True, True))
            self.assertEqual(game_save.restore_respawn(meta), VILLAGE.stand)
            book = game_save.restore_book(meta)
            r = book.get(VILLAGE.id)
            self.assertEqual((r.storage.count(3), r.storage.count(items.item_of(77)), len(r.storage.slots)), (40, 3, 30))
            self.assertEqual((r.request_done, r.expanded, r.tonic), (True, False, True))
            self.assertIsNot(book.get("9,9"), r)

    def test_bad_data_falls_back_quietly(self):
        self.assertEqual(game_save.restore_flags({"flags": "x"}), Flags())
        self.assertEqual(game_save.restore_flags({"flags": {"boss_defeated": 1}}), Flags())    # only a real True counts
        self.assertIsNone(game_save.restore_respawn({"respawn": [1, 2]}))
        self.assertIsNone(game_save.restore_respawn({"respawn": [1, 2, float("nan")]}))
        self.assertEqual(game_save.restore_respawn({"respawn": [1, 2, 3]}), (1.0, 2.0, 3.0))
        book = game_save.restore_book({"villages": {"0,0": {"storage": [[3, 999], [99999, 1], "x", None], "tonic": 1},
                                                    5: "bad", "1,1": "bad"}})
        s = book.get("0,0")
        self.assertEqual(s.storage.slots[0], [3, 64])
        self.assertEqual(sum(1 for x in s.storage.slots if x), 1)
        self.assertEqual(len(s.storage.slots), C.STORAGE_SLOTS)
        self.assertFalse(s.tonic)
        self.assertEqual(game_save.restore_book({}).states, {})

    def test_old_format_1_saves_get_their_minerals_converted(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp) / "old"
            d.mkdir()
            old_red = 1000 + ((7 << 6) | (0 << 3) | 0)                      # (200, 60, 60) in the 8-level format
            (d / "meta.json").write_text(json.dumps({"save_version": 1, "seed": 7, "inventory": [[old_red, 4], [3, 9], None]}))
            meta = SaveStore(d).load_meta()
            self.assertEqual(meta["save_version"], 2)
            item, count = meta["inventory"][0]
            self.assertEqual((items.rgb(items.code_of(item)), count), ((200, 60, 60), 4))
            self.assertEqual(meta["inventory"][1], [3, 9])
            inv = game_save.restore_inventory(meta["inventory"])
            self.assertEqual(inv.count(item), 4)


if __name__ == "__main__":
    unittest.main()
