"""Slime RPG - stage 6: voxel world, villages with commands, day and night, minerals, terminal-style battles, the Slime King.
Run:  python main.py      (needs: pip install ursina numpy)
Ursina only does windowing, drawing and input here; all game logic lives in the engine-free modules."""
import atexit
import math
import os
import random
import sys
import textwrap
from pathlib import Path

# Panda3D streams sound files bigger than 1 MB from disk and refills them frame by frame; when a frame is slow the music
# stutters, goes silent or hisses. Our tunes are 2-4 MB, so tell Panda to load them whole. Must run before any sound loads.
try:
    from panda3d.core import loadPrcFileData
    loadPrcFileData("", "audio-preload-threshold 200000000")
except Exception:
    pass

# Linux: an active input method (fcitx5 / ibus) can swallow key-release events in the Panda3D window, which
# makes keys stick and Space stop working. This game has no text input, so detach the IME for this process.
# Must run BEFORE ursina is imported. Set SLIME_KEEP_IME=1 to opt out.
if sys.platform.startswith("linux") and not os.environ.get("SLIME_KEEP_IME"):
    os.environ["XMODIFIERS"] = "@im=none"

from ursina import Ursina, Entity, Text, Mesh, Color, Audio, Texture, Button
from ursina import camera, window, mouse, scene, held_keys, application, destroy
from ursina import time as game_time

import config as C
import items
import strings as T
from audio import music, sfx
from audio.director import MusicDirector
from blocks import BLOCKS, GRASS, WOOD, register_mod_block
from game import daytime, progression
from game.battle import Battle, make_boss, make_enemy
from mods.loader import load_mods
from game.building import try_place
from game.garden import planting_cell
from game.death import apply_death
from game.encounter import EncounterTracker
from game.fog import fog_for_depth
from game.inventory import Inventory
from game.mining import Miner
from game.presenter import BattlePresenter
from game.sprites import slime_sprite
from game.stats import PlayerStats
from game.village import BossGate, ConfirmGate, Context, Flags, VillageBook, VillageSession
from game.physics import Body
from game.raycast import raycast
from save import game_save
from save.store import SaveError, SaveStore
from world import boss_arena, seeds, villages
from world.spawn import find_spawn
from world.manager import ChunkManager
from world.world import World
from world.worldgen import surface_heights

app = Ursina(title=T.GAME_TITLE, borderless=False)
window.exit_button.visible = False

# ---------------------------------------------------------------- saves
# One save slot. SLIME_SAVE_DIR overrides the folder; `python main.py --new` sets the old save aside first.
SAVE_DIR = Path(os.environ.get("SLIME_SAVE_DIR") or Path(__file__).resolve().parent / "saves" / "default")
store = SaveStore(SAVE_DIR)

# Data-only MODs are loaded once at startup. No MOD Python code is executed. The folder is mods/ next to main.py,
# or the one named in SLIME_MODS_DIR. See MODDING.md.
MODS_DIR = Path(os.environ.get("SLIME_MODS_DIR") or Path(__file__).resolve().parent / "mods")
MODS = load_mods(MODS_DIR)
for _block in MODS.blocks:
    _block["runtime_id"] = register_mod_block(
        _block["mod_id"], _block["id"], _block["name"], _block["hardness"],
        _block["stack_limit"], _block["sound"], _block["top"], _block["side"],
        _block["bottom"], _block["placeable"])
for _mod in MODS.loaded:
    print(f"MOD loaded: {_mod['name']} ({_mod['slime_count']} slimes, {_mod['block_count']} blocks)")
for _error in MODS.errors:
    print(f"MOD skipped: {_error}")
for _warning in MODS.warnings:
    print(f"MOD warning: {_warning}")


def mod_notices():
    """Short in-game messages for the start of the game: the details are in the terminal."""
    notes = []
    if MODS.errors:
        notes.append(T.MOD_NOTICE_SKIPPED.format(n=len(MODS.errors), first=MODS.errors[0][:90]))
    if MODS.warnings:
        notes.append(T.MOD_NOTICE_WARNINGS.format(n=len(MODS.warnings)))
    return notes


def mod_summary():
    """One line for the pause menu."""
    text = (T.MENU_MODS.format(names=", ".join(
                f"{m['name']} (S:{m['slime_count']} B:{m['block_count']})" for m in MODS.loaded)[:80])
            if MODS.loaded else T.MENU_MODS_NONE)
    problems = len(MODS.errors) + len(MODS.warnings)
    return text + (T.MENU_MODS_PROBLEMS.format(n=problems) if problems else "")


def read_startup_save():
    """Returns (meta or None, [notices]). Unreadable saves are moved aside; saves from newer builds stop the game."""
    notices = []
    asked_for_seed = any(a == "--seed" or a.startswith("--seed=") for a in sys.argv)
    if ("--new" in sys.argv or asked_for_seed) and store.exists():        # --seed N means "a new game on that map"
        print("Previous save moved to", store.archive("old"))
    if not store.exists():
        return None, notices
    try:
        meta = store.load_meta()
    except SaveError as exc:
        if exc.kind == "too_new":                   # never touch a save we cannot understand
            sys.exit(T.SAVE_TOO_NEW.format(found=exc.detail, supported=C.SAVE_VERSION))
        print("Save unreadable:", exc, "-> moved to", store.archive("corrupt"))
        return None, [T.SAVE_CORRUPT]
    notices.append(T.WORLDGEN_CHANGED if meta.get("worldgen_version") != C.WORLDGEN_VERSION else T.LOADED)
    return meta, notices


def read_menu_save():
    """For the in-game Load button: never moves or deletes anything. Returns (meta or None, error text)."""
    if not store.exists():
        return None, T.NO_SAVE
    try:
        return store.load_meta(), ""
    except SaveError:
        return None, T.LOAD_FAILED


# Filled in by start_session(); the update loop reads them as module globals.
world = inventory = miner = body = manager = stats = tracker = presenter = ctx = None
rng = random.Random()                    # battles and encounters (tests replace it with a seeded one)
SPAWN = (0.5, 40.0, 0.5)


_cli_seed = seeds.seed_from_args(sys.argv, os.environ)


def next_new_seed():
    """A new game gets a new random map. A seed asked for on purpose (--seed N / SLIME_SEED) is used once."""
    global _cli_seed
    seed, _cli_seed = (_cli_seed or seeds.random_seed()), None
    return seed


class State:
    yaw = 0.0
    pitch = 0.0
    selected = 0
    hit = None
    clock = 0.0
    last_full_msg = -99.0
    msg_until = 0.0
    hud_key = None
    info_timer = 0.0
    fog_timer = 0.0
    fog_depth = None
    autosave_timer = float(C.AUTOSAVE_SECONDS)
    paused = False
    skip_look = 0               # frames to ignore mouse movement after the cursor was released
    need_release = False        # ignore the dig button until it has been let go once (menu clicks)
    battle = None               # the running game.battle.Battle, or None
    last_xz = (0.0, 0.0)        # where the player was last frame (distance walked -> encounter steps)
    world_time = 0.0            # seconds; the day/night cycle (config.DAY_LENGTH)
    panel = None                # an open village / boss-gate screen (game.village.VillageSession or BossGate)
    on_tile = False             # standing on a village tile (a screen opens when you STEP onto it, not while you stay)
    on_boss_tile = False
    sky_key = None
    tinted = False
    music = None                # which background track should be playing: 'field' or 'battle'


st = State()


def item_name(item):
    if items.is_mineral(item):
        r, g, b = items.rgb(items.code_of(item))
        return T.MINERAL_NAME.format(r=r, g=g, b=b)
    if items.is_seed(item):
        r, g, b = items.rgb(items.seed_code(item))
        return T.FLOWER_SEED_NAME.format(r=r, g=g, b=b)
    return T.BLOCK_NAMES.get(BLOCKS[item].key, BLOCKS[item].key.split(":", 1)[-1].replace("_", " ").title())


# ---------------------------------------------------------------- sound
sfx.write_all()                      # procedural wavs, written once into assets/sfx
_sounds = {}
for _name in sfx.render_all():
    try:
        _sounds[_name] = Audio(_name, autoplay=False)
    except Exception as exc:         # a missing sound must never stop the game
        print("sound unavailable:", _name, exc)


# ---------------------------------------------------------------- background music (composed in code, audio/music.py)
class _Track:
    """One looping tune, driven through Panda3D's own sound object so we can ask whether it is really playing."""

    def __init__(self, stem):
        self.audio = Audio(stem, loop=True, autoplay=False, volume=C.MUSIC_VOLUME)

    def start(self):
        try:
            clip = self.audio.clip
            clip.setLoop(True)
            clip.setVolume(C.MUSIC_VOLUME)
            clip.setTime(0.0)
            clip.play()
        except Exception:
            self.audio.play()

    def stop(self):
        try:
            self.audio.clip.stop()
        except Exception:
            self.audio.pause()

    def is_playing(self):
        try:
            return self.audio.clip.status() == 2          # AudioSound.PLAYING
        except Exception:
            return True                                   # cannot tell: leave it alone

    def destroy(self):
        destroy(self.audio)


_director = None
if not os.environ.get("SLIME_NO_MUSIC"):                  # SLIME_NO_MUSIC=1 turns the music off
    try:
        _director = MusicDirector(music.MUSIC_DIR, _Track)
        _director.start()                                 # new tunes every launch (about a second); more are made in the background
    except Exception as exc:                              # no music must never stop the game
        print("music unavailable:", exc)
        _director = None


def set_music(track):
    """'field' (slow, major pentatonic) or 'battle' (fast, minor pentatonic)."""
    st.music = track
    if _director is not None:
        try:
            _director.set_track(track)
        except Exception as exc:
            print("music error:", exc)


def play(name):
    s = _sounds.get(name)
    if s is not None:
        s.play()


# ---------------------------------------------------------------- chunk rendering
chunk_entities = {}


def on_mesh(key, data):
    old = chunk_entities.pop(key, None)
    if old is not None:
        destroy(old)
    if data is None:
        return
    verts, tris, cols = data
    mesh = Mesh(vertices=verts.tolist(), triangles=tris.tolist(),
                colors=[Color(*c) for c in cols.tolist()])
    e = Entity(model=mesh, position=(key[0] * C.CHUNK_SIZE, 0, key[1] * C.CHUNK_SIZE))
    e.double_sided = True
    try:
        e.shader = None              # fixed pipeline: honours vertex colours and scene fog
    except Exception:
        pass
    chunk_entities[key] = e


def on_unload(cx, cz):
    for sy in range(C.SECTIONS_PER_CHUNK):
        e = chunk_entities.pop((cx, cz, sy), None)
        if e is not None:
            destroy(e)


# ---------------------------------------------------------------- camera rig, crack overlay, HUD
rig = Entity()
pivot = Entity(parent=rig)
camera.parent = pivot
camera.position = (0, 0, 0)
camera.rotation = (0, 0, 0)
camera.fov = 90
camera.clip_plane_far = C.RENDER_RADIUS * C.CHUNK_SIZE + 40
mouse.locked = True


def make_crack_textures(stages=5, size=16):
    try:
        import numpy as np
        from PIL import Image
    except ImportError:
        return []
    rng = np.random.default_rng(7)
    pixels = []
    for _ in range(7):                                  # a few random walks from near the centre
        x, y = rng.integers(4, size - 4, 2)
        for _ in range(12):
            pixels.append((int(x), int(y)))
            x = int(np.clip(x + rng.integers(-1, 2), 0, size - 1))
            y = int(np.clip(y + rng.integers(-1, 2), 0, size - 1))
    textures = []
    for s in range(stages):
        img = np.zeros((size, size, 4), dtype=np.uint8)
        for (px, py) in pixels[: int(len(pixels) * (s + 1) / stages)]:
            img[py, px] = (0, 0, 0, 210)
        tex = Texture(Image.fromarray(img, "RGBA"))
        try:
            tex.filtering = None                        # crisp pixels
        except Exception:
            pass
        textures.append(tex)
    return textures


crack_textures = make_crack_textures()
crack = Entity(model="cube", scale=1.004, enabled=False)

crosshair = Entity(parent=camera.ui, model="quad", color=Color(1, 1, 1, 0.8), scale=0.006)
hud_inventory = Text(text="", position=(-0.88, 0.36), origin=(-0.5, 0.5), scale=0.9)
hud_info = Text(text="", position=(-0.88, 0.48), origin=(-0.5, 0.5), scale=0.9)
hud_help = Text(text=T.HELP_TEXT, position=(-0.88, -0.46), origin=(-0.5, -0.5), scale=0.7)
message = Text(text="", position=(0, -0.18), origin=(0, 0), scale=1.4, color=Color(1, 0.35, 0.3, 1), enabled=False)


hud_status = Text(text="", position=(0.52, 0.48), origin=(-0.5, 0.5), scale=0.9)
swatch_you = Entity(parent=camera.ui, model="quad", position=(0.545, 0.16), scale=(0.06, 0.06))
swatch_held = Entity(parent=camera.ui, model="quad", position=(0.545, 0.08), scale=(0.06, 0.06))
label_you = Text(text=T.HUD_YOU, position=(0.58, 0.175), origin=(-0.5, 0.5), scale=0.8)
label_held = Text(text=T.HUD_HELD, position=(0.58, 0.095), origin=(-0.5, 0.5), scale=0.8)


hud_parts = [crosshair, hud_inventory, hud_status, hud_info, hud_help, swatch_you, swatch_held, label_you, label_held]


def set_hud(visible):
    """The everyday overlay (inventory, status, key help, crosshair...). Hidden on the full-screen battle and village screens."""
    for part in hud_parts:
        part.enabled = visible
    if not visible:
        message.enabled = False


def notify(text, seconds=1.5):
    message.text = text
    message.enabled = True
    st.msg_until = st.clock + seconds


def player_snapshot():
    return dict(x=body.x, y=body.y, z=body.z, yaw=st.yaw, pitch=st.pitch, selected=st.selected)


def save_now(announce=True):
    try:
        game_save.save_game(store, world, inventory, player_snapshot(), SPAWN, stats, st.world_time, ctx)
    except OSError as exc:
        if announce:
            notify(T.SAVE_FAILED.format(reason=exc.strerror or exc), 3.0)
        print("Save failed:", exc)
        return False
    if announce:
        notify(T.SAVED, 1.2)
    return True


def _save_on_exit():                      # also covers closing the window instead of using the menu
    try:
        game_save.save_game(store, world, inventory, player_snapshot(), SPAWN, stats, st.world_time, ctx)
    except Exception as exc:
        print("Save on exit failed:", exc)


atexit.register(_save_on_exit)


def refresh_inventory_hud():
    key = (inventory.version, st.selected, stats.version, stats.color)
    if key == st.hud_key:
        return
    st.hud_key = key
    h, sat, _v = stats.hsv()
    hud_status.text = (T.HUD_HP.format(level=stats.level, xp=stats.xp, need=progression.xp_needed(stats.level),
                                       hp=stats.hp, max_hp=stats.max_hp, atk=stats.atk, df=stats.defense, spd=stats.spd) + "\n"
                       + T.HUD_COLOR.format(r=stats.color[0], g=stats.color[1], b=stats.color[2], h=h, s=sat * 100))
    swatch_you.color = Color(stats.color[0] / 255, stats.color[1] / 255, stats.color[2] / 255, 1)
    held = inventory.item_at(st.selected)
    if held is not None and items.is_mineral(held):
        r, g, b = items.rgb(items.code_of(held))
        swatch_held.color = Color(r / 255, g / 255, b / 255, 1)
    else:
        swatch_held.color = Color(0.2, 0.2, 0.2, 0.5)
    used = inventory.used_slots()
    header = T.HUD_INVENTORY.format(used=used, total=len(inventory.slots))
    lines = [header]
    for i, s in enumerate(inventory.slots):
        if s is None and i != st.selected:
            continue
        label = T.EMPTY_SLOT if s is None else f"{item_name(s[0])} x{s[1]}"
        lines.append(f"{'>' if i == st.selected else ' '} {i + 1:2d} {label}")
    hud_inventory.text = "\n".join(lines)
    hud_inventory.color = Color(1, 0.3, 0.3, 1) if inventory.is_full() else Color(1, 1, 1, 1)


def apply_fog(depth):
    """Sky and distant fog share one colour, which follows the time of day (and fades to black underground)."""
    rgb, near, far = fog_for_depth(depth, daytime.sky_color(st.world_time))
    col = Color(rgb[0], rgb[1], rgb[2], 1)
    scene.fog_color = col
    scene.fog_density = (near, far)
    window.color = col
    tint = daytime.world_tint(st.world_time, depth)
    if tint != (1.0, 1.0, 1.0) or st.tinted:
        st.tinted = tint != (1.0, 1.0, 1.0)
        try:
            scene.setColorScale(tint[0], tint[1], tint[2], 1)   # only when NIGHT_WORLD_TINT is set (default: sky only)
        except Exception:
            pass


apply_fog(0)


# ---------------------------------------------------------------- session (new game or loaded save)
def start_session(meta):
    """(Re)build the whole game state from a save (or from scratch when meta is None)."""
    global world, inventory, miner, body, manager, stats, tracker, ctx, SPAWN, _cli_seed
    if meta:
        _cli_seed = None                                 # a saved game keeps its own map: a seed asked for at launch is moot
    for e in list(chunk_entities.values()):
        destroy(e)
    chunk_entities.clear()

    world = World(meta["seed"] if meta else next_new_seed(), store=store)
    inventory = game_save.restore_inventory(meta.get("inventory")) if meta else Inventory()
    miner = Miner(world, inventory)
    stats = game_save.restore_stats(meta) if meta else PlayerStats()
    ctx = Context(world.seed, inventory, stats, game_save.restore_flags(meta) if meta else Flags(),
                  game_save.restore_book(meta) if meta else VillageBook(), item_name,
                  game_save.restore_respawn(meta) if meta else None)
    world.extended = ctx.flags.boss_defeated            # new ore colours exist once the Slime King has fallen
    spawn = game_save.restore_spawn(meta, None) if meta else None
    SPAWN = spawn if spawn is not None else find_spawn(world)
    start = game_save.restore_player(meta, SPAWN) if meta else (*SPAWN, 0.0, 0.0, 0)
    body = Body(world, start[0], start[1], start[2])
    st.yaw, st.pitch, st.selected = start[3], start[4], start[5]
    st.hud_key = None
    st.fog_depth = None
    st.autosave_timer = float(C.AUTOSAVE_SECONDS)
    st.battle = None
    st.last_xz = (body.x, body.z)
    st.world_time = game_save.restore_clock(meta) if meta else daytime.start_seconds()
    st.sky_key = None
    st.panel = None
    fx, fz = math.floor(body.x), math.floor(body.z)
    st.on_tile = villages.village_at(world.seed, fx, fz) is not None          # do not pop a screen open just for loading in
    st.on_boss_tile = boss_arena.arena_at(world.seed, fx, fz)
    tracker = EncounterTracker()
    battle_ui.enabled = False
    panel_ui.enabled = False
    set_hud(True)
    set_music("field")
    manager = ChunkManager(world, on_mesh, on_unload)
    manager.update_world_time(st.world_time)
    for _ in range(60):                  # small head start so the first frame is not an empty void
        manager.step(int(math.floor(body.x)) >> 4, int(math.floor(body.z)) >> 4)


# ---------------------------------------------------------------- pause menu (Esc)
menu = Entity(parent=camera.ui, enabled=False)
Entity(parent=menu, model="quad", color=Color(0, 0, 0, 0.65), scale=(3, 2))
Text(parent=menu, text=T.MENU_TITLE, origin=(0, 0), position=(0, 0.28), scale=2)
menu_status = Text(parent=menu, text="", origin=(0, 0), position=(0, -0.29), scale=1.1)
Text(parent=menu, text=T.MENU_LOAD_HINT, origin=(0, 0), position=(0, -0.35), scale=0.8)
menu_seed = Text(parent=menu, text="", origin=(0, 0), position=(0, -0.43), scale=0.8)
menu_mods = Text(parent=menu, text="", origin=(0, 0), position=(0, -0.47), scale=0.8)


def set_paused(flag):
    st.paused = flag
    menu.enabled = flag
    mouse.locked = not flag
    if flag:
        miner.reset()
        crack.enabled = False
        menu_status.text = ""
        menu_seed.text = T.MENU_SEED.format(seed=world.seed)
        menu_mods.text = mod_summary()
    else:
        st.skip_look = 2
        st.need_release = True


def menu_save():
    menu_status.text = T.SAVED if save_now(announce=False) else T.SAVE_FAILED.format(reason="see console")


def menu_load():
    meta, err = read_menu_save()
    if meta is None:
        menu_status.text = err
        return
    start_session(meta)                  # unsaved progress since the last save is discarded, by design
    set_paused(False)
    notify(T.LOADED, 1.5)


def menu_new_world():
    set_paused(False)
    open_panel(ConfirmGate(T.NEW_WORLD_TITLE, T.NEW_WORLD_LINES, T.NEW_WORLD_YES, T.NEW_WORLD_NO))


def new_world():
    """Keep the old game in a backup folder and start a fresh game on a new random map."""
    save_now(announce=False)
    kept = store.archive("backup")
    print("The old world was kept in", kept)
    start_session(None)
    notify(T.NEW_WORLD.format(seed=world.seed), 5.0)


def menu_end():
    save_now(announce=False)
    application.quit()


for _i, (_label, _action) in enumerate(((T.MENU_RESUME, lambda: set_paused(False)), (T.MENU_SAVE, menu_save),
                                        (T.MENU_LOAD, menu_load), (T.MENU_NEW, menu_new_world), (T.MENU_END, menu_end))):
    Button(parent=menu, text=_label, position=(0, 0.17 - _i * 0.09), scale=(0.4, 0.07), on_click=_action)

# ---------------------------------------------------------------- battle screen (terminal style)
GREEN_TXT = Color(0.35, 1.0, 0.45, 1)
battle_ui = Entity(parent=camera.ui, enabled=False)
Entity(parent=battle_ui, model="quad", color=Color(0.01, 0.025, 0.012, 0.97), scale=(3, 2))
Text(parent=battle_ui, text=T.BATTLE_TITLE, position=(-0.86, 0.47), origin=(-0.5, 0.5), scale=1.0, color=GREEN_TXT)
Text(parent=battle_ui, text="=" * 78, position=(-0.86, 0.43), origin=(-0.5, 0.5), scale=0.9, color=GREEN_TXT)
you_sprite = Entity(parent=battle_ui, model="quad", position=(-0.48, 0.21), scale=(0.34, 0.34))
enemy_sprite = Entity(parent=battle_ui, model="quad", position=(0.48, 0.21), scale=(0.34, 0.34))
you_header = Text(parent=battle_ui, text="", position=(-0.86, 0.02), origin=(-0.5, 0.5), scale=0.9, color=GREEN_TXT)
enemy_header = Text(parent=battle_ui, text="", position=(0.08, 0.02), origin=(-0.5, 0.5), scale=0.9, color=GREEN_TXT)
Text(parent=battle_ui, text="-" * 78, position=(-0.86, -0.095), origin=(-0.5, 0.5), scale=0.9, color=GREEN_TXT)
battle_log = Text(parent=battle_ui, text="", position=(-0.86, -0.125), origin=(-0.5, 0.5), scale=0.95, color=GREEN_TXT)
battle_held = Text(parent=battle_ui, text="", position=(-0.86, -0.335), origin=(-0.5, 0.5), scale=0.85, color=GREEN_TXT)
battle_prompt = Text(parent=battle_ui, text="", position=(-0.86, -0.375), origin=(-0.5, 0.5), scale=0.95, color=GREEN_TXT)
battle_held_swatch = Entity(parent=battle_ui, model="quad", position=(0.80, -0.35), scale=(0.035, 0.035))
boss_next_swatch = Entity(parent=battle_ui, model="quad", position=(0.82, -0.045), scale=(0.04, 0.04), enabled=False)

_sprite_cache = {}
_sprite_shown = {}


def sprite_texture(rgb):
    """Pixel-art slime tinted with this colour (cached). None when Pillow is unavailable."""
    key = tuple(int(round(c)) for c in rgb)
    if key not in _sprite_cache:
        try:
            from PIL import Image
            tex = Texture(Image.fromarray(slime_sprite(key), "RGBA"))
            try:
                tex.filtering = None                          # crisp pixels, no smoothing
            except Exception:
                pass
        except Exception:
            tex = None
        if len(_sprite_cache) > 200:
            _sprite_cache.clear()
        _sprite_cache[key] = tex
    return _sprite_cache[key]


def set_sprite(entity, rgb):
    key = tuple(int(round(c)) for c in rgb)
    if _sprite_shown.get(id(entity)) == key:
        return
    _sprite_shown[id(entity)] = key
    tex = sprite_texture(key)
    if tex is not None:
        entity.texture = tex
        entity.color = Color(1, 1, 1, 1)
    else:                                                       # no Pillow: a flat coloured square
        entity.color = Color(key[0] / 255, key[1] / 255, key[2] / 255, 1)


def refresh_battle_ui():
    """Draw the battle from the presenter's numbers and lines (so HP and colours change when the line appears)."""
    b = st.battle
    if b is None or presenter is None:
        return
    snap = presenter.snap
    ec, yc = snap["enemy_color"], snap["you_color"]
    set_sprite(enemy_sprite, ec)
    set_sprite(you_sprite, yc)
    if snap.get("boss"):                                      # the Slime King: bigger, and the colour he takes next is shown
        nc = snap["boss_next"]
        enemy_header.text = T.BATTLE_HEADER_BOSS.format(level=snap["enemy_level"], hp=snap["enemy_hp"], max_hp=snap["enemy_max"],
                                                        r=ec[0], g=ec[1], b=ec[2], nr=nc[0], ng=nc[1], nb=nc[2])
        boss_next_swatch.color = Color(nc[0] / 255, nc[1] / 255, nc[2] / 255, 1)
        boss_next_swatch.enabled = True
        enemy_sprite.scale, enemy_sprite.position = (0.46, 0.46), (0.48, 0.24)
    else:
        enemy_header.text = T.BATTLE_HEADER_ENEMY.format(name=snap["enemy_name"], level=snap["enemy_level"], hp=snap["enemy_hp"], max_hp=snap["enemy_max"],
                                                         r=ec[0], g=ec[1], b=ec[2])
        boss_next_swatch.enabled = False
        enemy_sprite.scale, enemy_sprite.position = (0.34, 0.34), (0.48, 0.21)
    you_header.text = T.BATTLE_HEADER_YOU.format(level=snap["you_level"], hp=snap["you_hp"], max_hp=snap["you_max"],
                                                 r=yc[0], g=yc[1], b=yc[2])
    battle_log.text = "\n".join(presenter.lines(last=6))
    held = inventory.item_at(st.selected)
    if held is not None and items.is_mineral(held):
        r, g, bl = items.rgb(items.code_of(held))
        battle_held.text = T.BATTLE_HELD.format(name=item_name(held), throw=b.throw_multiplier(held), tackle=b.tackle_multiplier())
        battle_held_swatch.color = Color(r / 255, g / 255, bl / 255, 1)
    else:
        battle_held.text = T.BATTLE_HELD_NONE.format(tackle=b.tackle_multiplier())
        battle_held_swatch.color = Color(0.0, 0.0, 0.0, 0.0)
    idle = not presenter.busy
    battle_prompt.text = (T.PROMPT_WAIT if not idle else T.PROMPT_CHOOSE if b.phase == "choose" else T.PROMPT_CONTINUE)
    for btn in battle_buttons:
        btn.enabled = idle and b.phase == "choose"
    btn_continue.enabled = idle and b.phase != "choose"


def battle_tick(dt):
    """Per frame during a battle: advance the typewriter and play the sounds of lines that just started."""
    for name in presenter.update(dt):
        play(name)
    refresh_battle_ui()


def open_battle(boss=False):
    """Start a fight. Enemy level comes from depth below the ORIGINAL surface and distance from the start point;
    boss=True starts the Slime King fight instead (fixed level and stats)."""
    global presenter
    done = ctx.flags.boss_defeated                          # after the boss: no level cap, and the wider colour range
    if boss:
        st.battle = Battle(stats, make_boss(rng, extended=done), inventory, rng, item_name, boss=True, extended=done)
    else:
        top = max(int(surface_heights(world.seed, math.floor(body.x), math.floor(body.z))), C.SEA_LEVEL)
        depth = top - int(body.y)
        distance = math.hypot(body.x - SPAWN[0], body.z - SPAWN[2])
        enemy = make_enemy(progression.enemy_level(depth, distance, rng, boss_defeated=done), rng, extended=done, mod_slimes=MODS.slimes)
        st.battle = Battle(stats, enemy, inventory, rng, item_name, extended=done)
    presenter = BattlePresenter(st.battle.snapshot())
    presenter.push(st.battle.take_events())
    miner.reset()
    crack.enabled = False
    mouse.locked = False
    set_hud(False)
    battle_ui.enabled = True
    set_music("battle")
    refresh_battle_ui()


def battle_act(action):
    b = st.battle
    if b is None or b.phase != "choose" or presenter.busy:
        return
    b.act(action, st.selected if action in ("throw", "eat") else None)
    presenter.push(b.take_events())                 # the round is resolved; the screen plays it back line by line
    refresh_battle_ui()
    refresh_inventory_hud()


def battle_advance():
    """Enter / Space: skip the text that is still typing, or (when it is all shown) leave a finished battle."""
    b = st.battle
    if b is None:
        return
    if presenter.busy:
        presenter.skip()
        refresh_battle_ui()
    elif b.phase != "choose":
        battle_continue()


def die():
    """Sudden death (design 8.6): everything carried is lost; you wake at the start point. Saved at once so quitting does not undo it."""
    apply_death(inventory, stats)
    body.x, body.y, body.z = ctx.respawn or SPAWN              # the last inn you slept at, else the start point
    body.vy = 0.0
    st.last_xz = (body.x, body.z)
    fx, fz = math.floor(body.x), math.floor(body.z)
    st.on_tile = villages.village_at(world.seed, fx, fz) is not None
    st.on_boss_tile = False
    tracker.reset()
    save_now(announce=False)
    notify(T.DEATH_NOTICE + ("\n" + T.RESPAWN_INN if ctx.respawn else ""), 4.0)


def battle_continue():
    b = st.battle
    if b is None or b.phase == "choose" or presenter.busy:
        return
    outcome = b.phase
    st.battle = None
    battle_ui.enabled = False
    set_hud(True)
    set_music("field")
    mouse.locked = True
    st.skip_look = 2
    st.need_release = True
    tracker.reset()
    if outcome == "lost":
        die()
    elif outcome == "won" and b.boss_won:
        on_boss_defeated()
    refresh_inventory_hud()


def on_boss_defeated():
    """The Slime King falls: enemies lose their level cap, new ore colours appear (chunks not changed by you are made again),
    and the villages offer new services. Saved at once."""
    ctx.flags.boss_defeated = True
    world.extended = True
    world.forget_unmodified()
    for e in list(chunk_entities.values()):
        destroy(e)
    chunk_entities.clear()
    manager.meshed.clear()
    save_now(announce=False)
    notify(T.NOTE_BOSS_FALLS, 5.0)


_btn_x = (-0.45, -0.15, 0.15, 0.45)
battle_buttons = [
    Button(parent=battle_ui, text=label, position=(_btn_x[i], -0.45), scale=(0.27, 0.06), color=Color(0.03, 0.14, 0.05, 1),
           text_color=GREEN_TXT, on_click=fn)
    for i, (label, fn) in enumerate(((T.BTN_TACKLE, lambda: battle_act("tackle")), (T.BTN_THROW, lambda: battle_act("throw")),
                                     (T.BTN_EAT, lambda: battle_act("eat")), (T.BTN_FLEE, lambda: battle_act("flee"))))]
btn_continue = Button(parent=battle_ui, text=T.BTN_CONTINUE, position=(0, -0.45), scale=(0.34, 0.06), color=Color(0.03, 0.14, 0.05, 1),
                      text_color=GREEN_TXT, on_click=battle_continue, enabled=False)

# ---------------------------------------------------------------- village / boss-gate screen (terminal style)
panel_ui = Entity(parent=camera.ui, enabled=False)
Entity(parent=panel_ui, model="quad", color=Color(0.01, 0.025, 0.012, 0.97), scale=(3, 2))
panel_title = Text(parent=panel_ui, text="", position=(-0.86, 0.47), origin=(-0.5, 0.5), scale=1.1, color=GREEN_TXT)
Text(parent=panel_ui, text="=" * 78, position=(-0.86, 0.43), origin=(-0.5, 0.5), scale=0.9, color=GREEN_TXT)
panel_lines = Text(parent=panel_ui, text="", position=(-0.86, 0.39), origin=(-0.5, 0.5), scale=0.95, color=GREEN_TXT)
panel_note = Text(parent=panel_ui, text="", position=(-0.86, 0.1), origin=(-0.5, 0.5), scale=0.95, color=Color(1.0, 0.85, 0.4, 1))
panel_buttons = []


def panel_choose(i):
    s_ = st.panel
    if s_ is None:
        return
    s_.choose(i)
    st.world_time = ctx.world_time                       # a night at the inn ends in the morning
    refresh_inventory_hud()
    close_panel() if s_.closed else panel_refresh()


def panel_refresh():
    sc = st.panel.screen()
    panel_title.text = sc.title
    rows = [textwrap.fill(line, 70) for line in sc.lines]
    panel_lines.text = "\n".join(rows)
    y = 0.39 - sum(r.count("\n") + 1 for r in rows) * 0.036 - 0.025       # the note and buttons sit below however many lines
    panel_note.y = y
    panel_note.text = ("> " + textwrap.fill(sc.note, 70)) if sc.note else ""
    y -= 0.075 if sc.note else 0.04
    for i, btn in enumerate(panel_buttons):
        btn.enabled = i < len(sc.options)
        if btn.enabled:
            btn.text = f"{(i + 1) % 10}) {sc.options[i]}"
            btn.y = y - i * 0.052


for _i in range(10):
    panel_buttons.append(Button(parent=panel_ui, text="", position=(-0.30, 0.0), scale=(0.9, 0.046), color=Color(0.03, 0.14, 0.05, 1),
                                text_color=GREEN_TXT, on_click=(lambda i=_i: panel_choose(i)), enabled=False))


def open_panel(session):
    st.panel = session
    ctx.world_time = st.world_time
    miner.reset()
    crack.enabled = False
    mouse.locked = False
    set_hud(False)
    panel_ui.enabled = True
    panel_refresh()


def close_panel():
    s_ = st.panel
    st.panel = None
    panel_ui.enabled = False
    set_hud(True)
    mouse.locked = True
    st.skip_look = 2
    st.need_release = True
    save_now(announce=False)                              # what you did in the village is kept
    if isinstance(s_, BossGate) and s_.fight:
        open_battle(boss=True)
    elif isinstance(s_, ConfirmGate) and s_.confirmed:
        new_world()


_meta, _notices = read_startup_save()
_notices = _notices + mod_notices()
start_session(_meta)
if _notices:
    notify("\n".join(_notices), 3.0)


# ---------------------------------------------------------------- per-frame update
def update():
    dt = min(game_time.dt, 0.05)
    st.clock += dt
    if _director is not None:
        _director.update(dt)                            # keeps the music going, even if the sound system dropped it
    if st.battle is not None:                           # battle: the world stands still, the text keeps typing
        battle_tick(dt)
        return
    if st.paused or st.panel is not None:               # a menu or village screen is open: the world stands still
        return
    st.world_time += dt
    miner.world_time = st.world_time
    if manager is not None:
        manager.update_world_time(st.world_time)

    # look (skipped for a moment after the cursor was released, to avoid a view jump)
    if st.skip_look > 0:
        st.skip_look -= 1
    else:
        st.yaw += mouse.velocity[0] * C.MOUSE_SENSITIVITY
        st.pitch = max(-89.0, min(89.0, st.pitch - mouse.velocity[1] * C.MOUSE_SENSITIVITY))

    # move
    fwd = held_keys["w"] - held_keys["s"]
    side = held_keys["d"] - held_keys["a"]
    yaw = math.radians(st.yaw)
    vx = math.sin(yaw) * fwd + math.cos(yaw) * side
    vz = math.cos(yaw) * fwd - math.sin(yaw) * side
    norm = math.hypot(vx, vz)
    if norm > 1:
        vx, vz = vx / norm, vz / norm
    body.update(dt, vx * C.MOVE_SPEED, vz * C.MOVE_SPEED, held_keys["space"] > 0)
    if body.y < -20:                                    # fell out of the world: back to spawn
        body.x, body.y, body.z = SPAWN
        body.vy = 0.0
        st.last_xz = (body.x, body.z)

    # stepping onto a village tile opens the village commands; the Slime King's tile asks if you want to fight
    fx, fz = math.floor(body.x), math.floor(body.z)
    v_here = villages.village_at(world.seed, fx, fz)
    on_tile = v_here is not None and body.y < v_here.ground + 2.5          # (a jump on the tile does not count as leaving it)
    on_boss = boss_arena.arena_at(world.seed, fx, fz) and body.y < 3
    opened = None
    if on_tile and not st.on_tile:
        opened = VillageSession(v_here, ctx)
    elif on_boss and not st.on_boss_tile:
        opened = BossGate(ctx)
    st.on_tile, st.on_boss_tile = on_tile, on_boss
    if opened is not None:
        open_panel(opened)
        return

    # random encounters: blocks walked on the ground count as steps; a Wood floor or bridge is safe
    moved = math.hypot(body.x - st.last_xz[0], body.z - st.last_xz[1])
    st.last_xz = (body.x, body.z)
    if body.on_ground and moved < 1.5:                  # (a bigger jump is a teleport, not walking)
        foot = world.get_block(math.floor(body.x), math.floor(body.y - 0.05), math.floor(body.z))
        multiplier = daytime.encounter_multiplier(st.world_time, st.fog_depth or 0)
        if tracker.walk(moved, foot == WOOD, rng, multiplier):
            open_battle()
            return

    eye = (body.x, body.y + C.EYE_HEIGHT, body.z)
    rig.position = eye
    rig.rotation_y = st.yaw
    pivot.rotation_x = st.pitch

    # aim + mine
    f = camera.forward
    st.hit = raycast(world.get_block, eye, (f.x, f.y, f.z), C.REACH)
    target = st.hit.cell if st.hit else None
    if st.need_release and held_keys["left mouse"] == 0:
        st.need_release = False
    res = miner.update(dt, held_keys["left mouse"] > 0 and not st.need_release, target)

    family = BLOCKS[res.block].sound if res.block in BLOCKS else "soft"
    if res.tick:
        play(f"hit_{family}")
    if res.broke:
        play(f"break_{family}")
    if res.lost and st.clock - st.last_full_msg >= C.MESSAGE_COOLDOWN:
        st.last_full_msg = st.clock
        notify(T.INVENTORY_FULL + "\n" + ", ".join(
            T.LOST_FMT.format(name=item_name(i), count=n) for i, n in res.lost))
        play("full")

    if res.target and res.progress > 0 and not res.broke:
        x, y, z = res.target
        crack.position = (x + 0.5, y + 0.5, z + 0.5)
        if crack_textures:
            crack.texture = crack_textures[min(len(crack_textures) - 1, int(res.progress * len(crack_textures)))]
            crack.color = Color(1, 1, 1, 1)
        else:
            crack.color = Color(0, 0, 0, 0.15 + 0.55 * res.progress)
        crack.enabled = True
    else:
        crack.enabled = False

    # world streaming (one generate-or-mesh task per frame)
    manager.step(int(math.floor(body.x)) >> 4, int(math.floor(body.z)) >> 4)

    # HUD, fog
    refresh_inventory_hud()
    if message.enabled and st.clock >= st.msg_until:
        message.enabled = False
    st.info_timer -= dt
    st.fog_timer -= dt
    st.autosave_timer -= dt
    if st.autosave_timer <= 0:
        st.autosave_timer = float(C.AUTOSAVE_SECONDS)
        save_now(announce=False)
    if st.fog_timer <= 0:
        st.fog_timer = 0.25
        # Depth below the ORIGINAL terrain surface, so digging a shaft does not make it bright again.
        top = max(int(surface_heights(world.seed, math.floor(body.x), math.floor(body.z))), C.SEA_LEVEL)
        depth = top - int(eye[1])
        sky_key = (depth, int(daytime.daylight(st.world_time) * 40), int(daytime.phase(st.world_time) * 200))
        if sky_key != st.sky_key:
            st.sky_key = sky_key
            st.fog_depth = depth
            apply_fog(depth)

    if st.info_timer <= 0:
        st.info_timer = 0.2
        near = villages.nearest_village(world.seed, body.x, body.z)
        village_line = (T.HUD_VILLAGE.format(dist=near[1], dir=villages.direction_name(near[0].x - body.x, near[0].z - body.z))
                        if near else T.HUD_VILLAGE_NONE)
        boss_line = ""
        if ctx.flags.boss_known and not ctx.flags.boss_defeated:
            ax, az = boss_arena.arena_center(world.seed)
            boss_line = "\n" + T.HUD_BOSS.format(dist=math.hypot(ax - body.x, az - body.z), dir=villages.direction_name(ax - body.x, az - body.z))
        night = daytime.daylight(st.world_time) < 0.5
        hud_info.text = "\n".join((T.HUD_POSITION.format(x=body.x, y=body.y, z=body.z, depth=max(0, st.fog_depth or 0)),
                                   T.HUD_TIME.format(clock=daytime.clock_text(st.world_time), phase=T.PHASE_NIGHT if night else T.PHASE_DAY),
                                   village_line)) + boss_line


def eat_selected():
    item = inventory.item_at(st.selected)
    if item is None or not items.is_mineral(item):
        notify(T.EAT_NOT_MINERAL, 1.2)
        return
    inventory.take(st.selected, 1)
    delta = stats.eat(items.rgb(items.code_of(item)))
    play("eat")
    notify(T.EAT_HEAL.format(n=delta) if delta > 0 else T.EAT_HURT.format(n=-delta) if delta < 0 else T.EAT_NOTHING, 1.5)


# ---------------------------------------------------------------- input
def input(key):
    if st.battle is not None:                           # in a fight: commands, skip, and which slot to throw / eat
        if key in ("enter", "space"):
            battle_advance()
        elif key == "scroll up":
            st.selected = (st.selected - 1) % len(inventory.slots)
        elif key == "scroll down":
            st.selected = (st.selected + 1) % len(inventory.slots)
        elif len(key) == 1 and key.isdigit():
            st.selected = (int(key) - 1) % 10
        elif key in ("a", "t", "e", "f"):
            battle_act({"a": "tackle", "t": "throw", "e": "eat", "f": "flee"}[key])
        refresh_battle_ui()
        return
    if st.panel is not None:                            # village / boss-gate screen: pick an option, Esc leaves
        if key == "escape":
            st.panel.closed = True
            close_panel()
        elif len(key) == 1 and key.isdigit():
            panel_choose((int(key) - 1) % 10)
        return
    if key == "escape":
        set_paused(not st.paused)
        return
    if st.paused:
        return
    if key == "right mouse down":
        held = inventory.item_at(st.selected)
        if held is not None and items.is_seed(held):
            cell = planting_cell(world, st.hit)
            if cell is not None and not body.overlaps_cell(*cell):
                code = items.seed_code(held)
                if world.plant_flower_seed(*cell, code, st.world_time):
                    inventory.take(st.selected, 1)
                    notify(T.FLOWER_PLANTED, 1.8)
                    play("place")
        elif try_place(world, inventory, st.selected, st.hit, body).placed:
            play("place")
    elif key == "scroll up":
        st.selected = (st.selected - 1) % len(inventory.slots)
    elif key == "scroll down":
        st.selected = (st.selected + 1) % len(inventory.slots)
    elif len(key) == 1 and key.isdigit():
        st.selected = (int(key) - 1) % 10
    elif key == "q":
        inventory.take(st.selected, 1)                  # discard: items just vanish (design 8.1)
    elif key == "e":
        eat_selected()


if __name__ == "__main__":
    app.run()
