"""Glue between the live game objects and the save files. Engine-free."""
import math
import time

import config as C
import items
from game import progression
from game.inventory import Inventory
from game.stats import PlayerStats
from game.village import Flags, VillageBook, VillageState


def build_meta(world, inventory, player, spawn, stats=None, clock=None, game=None):
    meta = {
        "save_version": C.SAVE_VERSION,
        "worldgen_version": C.WORLDGEN_VERSION,
        "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "seed": world.seed,
        "player": dict(player),                       # x, y, z, yaw, pitch, selected
        "spawn": [float(v) for v in spawn],
        "inventory": [None if s is None else [int(s[0]), int(s[1])] for s in inventory.slots],
    }
    if clock is not None:
        meta["time"] = float(clock)
    if game is not None:
        meta["flags"] = {"boss_defeated": bool(game.flags.boss_defeated), "boss_known": bool(game.flags.boss_known)}
        meta["respawn"] = None if game.respawn is None else [float(v) for v in game.respawn]
        meta["villages"] = {vid: {"storage": [None if sl is None else [int(sl[0]), int(sl[1])] for sl in st.storage.slots],
                                  "request_done": st.request_done, "expanded": st.expanded, "tonic": st.tonic}
                            for vid, st in game.book.states.items()}
    if stats is not None:
        meta["stats"] = {"level": stats.level, "xp": stats.xp, "hp": stats.hp,
                         "base": dict(stats.base), "color": [float(c) for c in stats.color]}
    return meta


def save_game(store, world, inventory, player, spawn, stats=None, clock=None, game=None):
    """Write every changed chunk, then meta. Returns the number of chunk files written."""
    written = 0
    for ch in list(world.chunks.values()):
        if ch.modified:
            store.save_chunk_edits(ch.cx, ch.cz, ch.edits)
            ch.modified = False                       # only after the write succeeded
            written += 1
    store.save_meta(build_meta(world, inventory, player, spawn, stats, clock, game))
    return written


def restore_inventory(rows, size=C.INVENTORY_SLOTS):
    """Rebuild an inventory from saved rows, dropping anything invalid rather than crashing."""
    inv = Inventory(size)
    if not isinstance(rows, list):
        return inv
    for i, row in enumerate(rows[:size]):
        try:
            item, count = row
            if items.is_valid_item(item) and isinstance(count, int) and not isinstance(count, bool):
                inv.slots[i] = [item, max(1, min(count, items.stack_limit(item)))]
        except (TypeError, ValueError):
            continue
    inv.version += 1
    return inv


def restore_player(meta, default_pos):
    """Returns (x, y, z, yaw, pitch, selected), falling back to defaults for anything unusable."""
    p = meta.get("player") if isinstance(meta.get("player"), dict) else {}

    def num(key, default, lo, hi):
        v = p.get(key)
        if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and lo <= v <= hi:
            return float(v)
        return default

    x = num("x", default_pos[0], -1e7, 1e7)
    y = num("y", default_pos[1], -5.0, C.WORLD_HEIGHT + 50.0)
    z = num("z", default_pos[2], -1e7, 1e7)
    yaw = num("yaw", 0.0, -1e6, 1e6)
    pitch = num("pitch", 0.0, -89.0, 89.0)
    selected = int(num("selected", 0, 0, C.INVENTORY_SLOTS - 1))
    return x, y, z, yaw, pitch, selected


def restore_spawn(meta, default):
    s = meta.get("spawn")
    if (isinstance(s, list) and len(s) == 3
            and all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in s)):
        return tuple(float(v) for v in s)
    return default


def restore_stats(meta):
    """PlayerStats from a save; anything unusable falls back to the defaults (never crashes)."""
    raw = meta.get("stats") if isinstance(meta.get("stats"), dict) else {}
    level = raw.get("level")
    level = level if isinstance(level, int) and not isinstance(level, bool) and 1 <= level <= 9999 else 1
    lo, hi = items.LOW, items.LOW + items.STEP * (items.LEVELS - 1)
    color = raw.get("color")
    if not (isinstance(color, list) and len(color) == 3 and all(
            isinstance(c, (int, float)) and not isinstance(c, bool) and math.isfinite(c) and lo <= c <= hi for c in color)):
        color = C.START_COLOR
    xp = raw.get("xp")
    xp = xp if isinstance(xp, int) and not isinstance(xp, bool) and 0 <= xp < progression.xp_needed(level) else 0
    base = raw.get("base")
    if not (isinstance(base, dict) and all(
            isinstance(base.get(k), int) and not isinstance(base.get(k), bool) and 1 <= base[k] <= 100000
            for k in progression.STATS)):
        base = None                                   # missing/invalid: use the average for this level
    stats = PlayerStats(level=level, color=color, xp=xp, base={k: base[k] for k in progression.STATS} if base else None)
    hp = raw.get("hp")
    if isinstance(hp, int) and not isinstance(hp, bool):
        stats.hp = max(1, min(hp, stats.max_hp))
    return stats


def restore_clock(meta):
    """World time in seconds; a missing or unusable value means a new morning."""
    t = meta.get("time")
    if isinstance(t, (int, float)) and not isinstance(t, bool) and math.isfinite(t) and 0 <= t < 1e9:
        return float(t)
    return C.START_TIME * C.DAY_LENGTH


def restore_flags(meta):
    raw = meta.get("flags") if isinstance(meta.get("flags"), dict) else {}
    return Flags(boss_defeated=raw.get("boss_defeated") is True, boss_known=raw.get("boss_known") is True)


def restore_respawn(meta):
    """(x, y, z) of the last inn slept at, or None (= the start point)."""
    r = meta.get("respawn")
    if (isinstance(r, list) and len(r) == 3
            and all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in r)):
        return tuple(float(v) for v in r)
    return None


def restore_book(meta):
    """Per-village storage and progress. Anything unusable is dropped, never fatal."""
    book = VillageBook()
    raw = meta.get("villages")
    if not isinstance(raw, dict):
        return book
    for vid, entry in raw.items():
        if not isinstance(vid, str) or not isinstance(entry, dict):
            continue
        rows = entry.get("storage")
        size = len(rows) if isinstance(rows, list) else C.STORAGE_SLOTS
        size = max(C.STORAGE_SLOTS, min(size, 500))
        st = VillageState()
        st.storage = restore_inventory(rows, size)
        st.request_done, st.expanded, st.tonic = (entry.get("request_done") is True, entry.get("expanded") is True,
                                                  entry.get("tonic") is True)
        book.states[vid] = st
    return book
