"""Runs main.py's game loop against a FAKE 'ursina' module, to catch Python-level mistakes in the glue code
(typos, wrong attribute use, logic errors). It cannot check the real Ursina API: that needs a real run.
Usage (project root):  python tests/smoke_stub.py"""
import collections
import importlib
import os
import sys
import tempfile
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config as _C                                            # noqa: E402

_tmp = tempfile.mkdtemp(prefix="slime_smoke_")
os.environ["SLIME_SEED"] = str(_C.SEED)                        # a fixed map for this script (new games are random otherwise)
os.environ["SLIME_SAVE_DIR"] = os.path.join(_tmp, "save")      # never touch a real save

# a MODs folder with one good MOD (with a misspelt key = a warning) and one broken MOD
import json as _json                                           # noqa: E402
_mods = os.path.join(_tmp, "mods")
os.environ["SLIME_MODS_DIR"] = _mods
for _folder, _meta, _slimes in (
        ("smoke_ok", {"id": "smoke_ok", "name": "Smoke Mod", "api_version": 1},
         [{"id": "smoke_slime", "name": "Smoke Slime", "weight": 1, "colour": [1, 2, 3]}]),
        ("smoke_bad", {"id": "smoke_bad", "name": "Bad Mod", "api_version": 1, "enabled": "yes"}, [])):
    os.makedirs(os.path.join(_mods, _folder))
    _json.dump(_meta, open(os.path.join(_mods, _folder, "mod.json"), "w"))
    _json.dump(_slimes, open(os.path.join(_mods, _folder, "slimes.json"), "w"))


class Fake:
    def __init__(self, *a, **k):
        self.__dict__.update(k)
        self.args = a

    def __getattr__(self, name):      # unknown attributes read as harmless fakes
        if name.startswith("__"):
            raise AttributeError(name)
        return Fake()


played = []
destroyed = []
fake = types.ModuleType("ursina")
for n in ("Ursina", "Entity", "Text", "Mesh", "Color", "Texture", "Button"):
    setattr(fake, n, type(n, (Fake,), {}))


music_log = []


class FakeClip:
    """Stands in for Panda3D's AudioSound: remembers whether it is playing."""

    def __init__(self, name):
        self.name, self.playing = name, False

    def setLoop(self, *a): pass
    def setVolume(self, *a): pass
    def setTime(self, *a): pass

    def play(self):
        self.playing = True
        music_log.append(("start", self.name))

    def stop(self):
        self.playing = False
        music_log.append(("stop", self.name))

    def status(self):
        return 2 if self.playing else 1


class Audio(Fake):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.clip = FakeClip(str(a[0]))

    def play(self, *a):
        if str(self.args[0]).startswith("bgm_"):
            self.clip.play()
        else:
            played.append(self.args[0])


fake.Audio = Audio
fake.camera = Fake(forward=Fake(x=0.0, y=-1.0, z=0.0), ui=Fake())
fake.window = Fake(exit_button=Fake(), color=None)
fake.mouse = Fake(velocity=(0.0, 0.0, 0.0), locked=False)
tints = []
fake.scene = Fake(setColorScale=lambda *a: tints.append(a))
fake.held_keys = collections.defaultdict(float)
quit_calls = []
fake.application = Fake(quit=lambda: quit_calls.append(1))
fake.destroy = lambda e: destroyed.append(e)
fake.time = Fake(dt=1 / 60)
sys.modules["ursina"] = fake

import random                    # noqa: E402
import main                      # noqa: E402  (builds the world, prefetches chunks, loads sounds)
import config as C               # noqa: E402
from blocks import BLOCKS        # noqa: E402

main.rng = random.Random(1)      # deterministic: no surprise battles while this script walks around
main.tracker.chance = 0.0
# MODs: the good one loaded, the broken one was skipped, the typo was reported, and the player is told in the game
assert [m["id"] for m in main.MODS.loaded] == ["smoke_ok"], main.MODS.loaded
assert len(main.MODS.errors) == 1 and "enabled" in main.MODS.errors[0], main.MODS.errors
assert len(main.MODS.warnings) == 1 and "colour" in main.MODS.warnings[0], main.MODS.warnings
assert "skipped" in main.message.text and "warning" in main.message.text, main.message.text
main.message.enabled = False                               # (the notice has been read; later checks look at fresh messages)
assert main.mod_summary() == "MODs: Smoke Mod (S:1 B:0)   (2 problem(s): see the terminal)", main.mod_summary()
assert music_log[0][0] == "start" and music_log[0][1].startswith("bgm_field_v1_"), music_log[:2]
assert not any("bgm_battle" in n and e == "start" for e, n in music_log), "only the field tune plays at the start"

print("spawn:", tuple(round(v, 2) for v in main.SPAWN), "| entities after prefill:", len(main.chunk_entities))
assert main.chunk_entities, "no chunk meshes were built"

for _ in range(120):             # settle onto the ground
    main.update()
print("on ground:", main.body.on_ground, "y=%.2f" % main.body.y)
assert main.body.on_ground

# Shrink the inventory to 1 slot so "full" is reachable (with 4 block types and stacks of 64 a real
# 20-slot inventory takes ~1000 blocks to fill; minerals in stage 3 will make it fill much faster).
main.inventory.slots = [None] * 1

# Dig straight down with the button held, as a player would.
fake.held_keys["left mouse"] = 1.0
broke_at = []
for frame in range(60 * 120):
    main.update()
    if main.inventory.used_slots() and not broke_at:
        broke_at.append(frame)
    if main.message.enabled:
        break
print("first block after %.2fs; sounds so far: %s" % (broke_at[0] / 60 if broke_at else -1, sorted(set(played))))
assert broke_at and any(s.startswith("hit_") for s in played) and any(s.startswith("break_") for s in played)

print("inventory:", main.inventory.slots[:4], "| used", main.inventory.used_slots())
print("message shown:", main.message.enabled, repr(main.message.text))
assert main.inventory.is_full(), "digging should eventually fill the inventory"
assert "Inventory full" in main.message.text and "full" in played

print("depth/fog after digging a shaft:", main.st.fog_depth)
assert main.st.fog_depth >= 2, "a dug shaft must still count as deep"

# Back on the surface: place with right-click while aiming at the ground ahead.
from blocks import ROCK          # noqa: E402
sx, sy, sz = main.SPAWN
main.body.x, main.body.z = sx + 3, sz            # away from the shaft we just dug
main.body.y = main.world.surface_y(int(sx + 3), int(sz)) + 1.01
main.body.vy = 0.0
main.inventory.slots = [None] * C.INVENTORY_SLOTS
main.inventory.add(ROCK, 5)
main.input("1")
fake.camera.forward = Fake(x=0.0, y=-0.6, z=0.8)
for _ in range(30):
    main.update()
before = main.inventory.count(ROCK)
main.input("right mouse down")
after = main.inventory.count(ROCK)
print("place: rock %d -> %d | 'place' sound played: %s" % (before, after, "place" in played))
assert after == before - 1 and "place" in played
main.input("q")
assert main.inventory.count(ROCK) == after - 1

# Walk around to exercise streaming / unloading.
fake.held_keys["w"] = 1.0
fake.mouse.velocity = (0.0, 0.0, 0.0)
fake.camera.forward = Fake(x=0.0, y=0.0, z=1.0)
fake.held_keys["space"] = 1.0
for _ in range(60 * 12):
    main.update()
print("walked to z=%.1f | meshed chunks: %d | entities: %d | destroyed: %d"
      % (main.body.z, len(main.manager.meshed), len(main.chunk_entities), len(destroyed)))
print("fog depth state:", main.st.fog_depth)
fake.held_keys["w"] = 0.0
fake.held_keys["space"] = 0.0

# ---- eating a mineral with E (stage 3)
import items                    # noqa: E402
main.inventory.slots = [None] * C.INVENTORY_SLOTS
rare = items.item_of(items.code_from_rgb((200, 60, 60)))           # vivid red
main.inventory.add(rare, 2)
main.inventory.add(ROCK, 1)
main.input("1")
c0, hp0 = main.stats.color, main.stats.hp
main.input("e")
assert main.inventory.count(rare) == 1, "eating should consume one mineral"
assert main.stats.color[0] > c0[0] and main.stats.color[1] < c0[1], "colour should move toward the mineral"
assert main.stats.hp < hp0, "a distant colour should hurt"
assert main.message.text.startswith("Ate mineral: HP -"), main.message.text
assert "eat" in played
main.input("2")
main.input("e")
assert main.message.text == "Select a mineral to eat (E)" and main.inventory.count(ROCK) == 1
main.update()
assert "HP" in main.hud_status.text and "Hue" in main.hud_status.text, main.hud_status.text
print("eat: hp %d -> %d, colour %s -> %s" % (hp0, main.stats.hp, tuple(round(v) for v in c0),
                                             tuple(round(v) for v in main.stats.color)))


# ---- battle through the real UI functions (stage 4)
import json                      # noqa: E402
from blocks import WOOD, AIR     # noqa: E402

def last_idx(kind, prefix):
    return max(i for i, (e, n) in enumerate(music_log) if e == kind and n.startswith(prefix))


def act(action):
    """Play a battle command the way a player does: wait for the text to finish (here: skip it), then choose."""
    main.presenter.skip()
    main.battle_act(action)


def finish():
    main.presenter.skip()
    main.battle_continue()


main.rng = random.Random(5)
main.stats.base = {"hp": 400, "atk": 60, "def": 30, "spd": 30}
main.stats.restore_full()
lv0, xp0 = main.stats.level, main.stats.xp
main.open_battle()
assert main.st.battle is not None and main.battle_ui.enabled and not main.mouse.locked
HUD = ("hud_inventory", "hud_status", "hud_info", "hud_help", "swatch_you", "swatch_held", "crosshair", "label_you", "label_held")
assert all(getattr(main, n).enabled is False for n in HUD), "the everyday text must be hidden during a battle"
assert last_idx("stop", "bgm_field") < last_idx("start", "bgm_battle") == len(music_log) - 1, music_log[-3:]
frozen = (main.body.x, main.body.y, main.body.z)
fake.held_keys["w"] = 1.0
for _ in range(20):
    main.update()
assert (main.body.x, main.body.y, main.body.z) == frozen, "player moved during a battle"
assert main.presenter.busy, "the opening line should be typing"
assert "HP" in main.enemy_header.text and "RGB" in main.enemy_header.text
main.battle_act("tackle")                                         # refused: the first line is still being typed
assert main.st.battle.phase == "choose" and main.stats.hp == main.stats.max_hp and len(main.st.battle.events) == 1
for _ in range(200):
    main.update()                                                 # the typewriter finishes the opening line
assert not main.presenter.busy and "choose" in main.battle_prompt.text
assert "appears" in main.battle_log.text
# one real round played back line by line, with sounds, and numbers that change only when their line has appeared
hp_before = main.presenter.snap["enemy_hp"]
n_sounds = len(played)
main.battle_act("tackle")
assert main.presenter.busy and "Enter" in main.battle_prompt.text
assert main.presenter.snap["enemy_hp"] == hp_before, "HP must not change until its line is shown"
assert not main.battle_buttons[0].enabled, "commands are locked while the round plays"
seen = set()
for _ in range(60 * 10):
    main.update()
    seen.update(main.battle_log.text.splitlines())
    if not main.presenter.busy:
        break
assert any(line.startswith("> You tackle") for line in seen), seen
assert any("takes" in line and "damage" in line for line in seen), seen
assert main.presenter.snap["enemy_hp"] < hp_before
assert played[n_sounds:].count("whoosh") >= 1 and "impact" in played[n_sounds:]
assert main.battle_buttons[0].enabled or main.st.battle.phase != "choose"
print("terminal playback ok:", main.battle_log.text.splitlines()[-3:])
main.input("escape")
assert not main.st.paused, "Esc must not open the menu during a battle"
fake.held_keys["w"] = 0.0
hp_now, enemy_now = main.stats.hp, main.st.battle.enemy.hp
act("throw")                                           # nothing selected: refused, no turn used
assert main.st.battle.phase == "choose" and (main.stats.hp, main.st.battle.enemy.hp) == (hp_now, enemy_now)
for _ in range(60):
    if main.st.battle.phase != "choose":
        break
    act("tackle")
assert main.st.battle.phase == "won", main.st.battle.log
assert (main.stats.level, main.stats.xp) != (lv0, xp0), "winning should give experience"
assert "Continue" in main.btn_continue.text
finish()
assert main.st.battle is None and main.mouse.locked and not main.battle_ui.enabled
assert all(getattr(main, n).enabled is True for n in HUD), "the everyday text comes back after the battle"
assert last_idx("start", "bgm_battle") < last_idx("stop", "bgm_battle") < last_idx("start", "bgm_field") == len(music_log) - 1, music_log[-4:]
main._director.wait()                                    # new tunes are being composed in the background: let them finish
print("battle won: Lv %d xp %d; log tail: %s" % (main.stats.level, main.stats.xp, main.battle_log.text.splitlines()[-1] if main.battle_log.text else ""))

battle_starts = [n for e, n in music_log if e == "start" and n.startswith("bgm_battle")]
print("battle tunes so far:", battle_starts)
# a battle against a slime from a MOD: chosen by weight, named on the screen, fought like any other
class PickLast(random.Random):
    def randrange(self, stop, *a):
        return stop - 1                                         # always the last entry = the MOD slime


main.rng = PickLast(7)
main.stats.base = {"hp": 400, "atk": 60, "def": 30, "spd": 30}
main.stats.restore_full()
main.open_battle()
assert main.st.battle.enemy.name == "Smoke Slime", main.st.battle.enemy
for _ in range(200):
    main.update()
assert "Smoke Slime appears" in main.battle_log.text, main.battle_log.text
for _ in range(60):
    if main.st.battle.phase != "choose":
        break
    act("tackle")
assert main.st.battle.phase == "won" and any("Smoke Slime takes" in line for line in main.st.battle.log), main.st.battle.log
finish()
main.rng = random.Random(5)
print("MOD slime: fought and beaten")

# defeat = sudden death: all items lost, back at spawn, saved immediately
main.inventory.add(ROCK, 5)
main.stats.base = {"hp": 5, "atk": 1, "def": 1, "spd": 1}
main.stats.restore_full()
main.body.x += 3
main.open_battle()
main.st.battle.enemy.atk, main.st.battle.enemy.spd = 999, 99
for _ in range(20):                      # damage is a share of max HP, so a full-HP slime survives the first hit
    if main.st.battle.phase != "choose":
        break
    act("tackle")
assert main.st.battle.phase == "lost", main.st.battle.log
for _ in range(60 * 12):                 # watch the last round's text for real, so its sounds play
    main.update()
    if not main.presenter.busy:
        break
assert "defeated" in main.battle_log.text and "lose" in played, main.battle_log.text
finish()
assert main.inventory.used_slots() == 0, "death must empty the inventory"
assert main.stats.hp == main.stats.max_hp
assert (round(main.body.x, 3), round(main.body.z, 3)) == (round(main.SPAWN[0], 3), round(main.SPAWN[2], 3))
assert "died" in main.message.text and "lose" in played
saved = json.load(open(os.path.join(_tmp, "save", "meta.json")))
assert all(slot is None for slot in saved["inventory"]), "death must be saved at once"
print("defeat: inventory emptied, respawned at the start point, saved")
battle_starts = [n for e, n in music_log if e == "start" and n.startswith("bgm_battle")]
assert len(battle_starts) >= 2 and battle_starts[-1] != battle_starts[0], battle_starts       # the next fight had a different tune
# the sound system drops the music: the director notices within a couple of seconds and starts it again
field_clip = main._director.current["field"][1].audio.clip
assert field_clip.playing
field_clip.playing = False
before = main._director.restarts
for _ in range(120):
    main.update()
assert field_clip.playing and main._director.restarts == before + 1, "silent music must be restarted"

# encounters: a Wood floor is safe, ordinary ground is not
main.stats.base = {"hp": 400, "atk": 60, "def": 30, "spd": 30}
main.stats.restore_full()
main.tracker.safe_steps, main.tracker.chance = 0, 1.0
main.tracker.reset()
X, Z = 40, 40
P = main.world.surface_y(X, Z) + 8
for dx in range(0, 4):
    for dz in range(0, 14):
        main.world.set_block(X + dx, P, Z + dz, WOOD)
        main.world.set_block(X + 6 + dx, P, Z + dz, ROCK)
        for dy in (1, 2, 3):
            main.world.set_block(X + dx, P + dy, Z + dz, AIR)
            main.world.set_block(X + 6 + dx, P + dy, Z + dz, AIR)
main.body.x, main.body.y, main.body.z = X + 1.5, P + 1.01, Z + 1.0
main.body.vy = 0.0
main.st.last_xz = (main.body.x, main.body.z)
main.st.yaw = 0.0
for _ in range(5):
    main.update()
fake.held_keys["w"] = 1.0
for _ in range(60 * 2):
    main.update()
assert main.st.battle is None, "walking on Wood must never start a battle"
assert main.body.z > Z + 5, "the player should have walked along the wood platform"
main.body.x, main.body.y, main.body.z = X + 7.5, P + 1.01, Z + 1.0
main.body.vy = 0.0
main.st.last_xz = (main.body.x, main.body.z)
for _ in range(60 * 2):
    main.update()
    if main.st.battle is not None:
        break
assert main.st.battle is not None, "walking on ordinary ground should start a battle"
print("encounters: none on Wood, battle on stone after", main.tracker.steps, "steps")
fake.held_keys["w"] = 0.0
for _ in range(80):
    if main.st.battle.phase != "choose":
        break
    act("tackle")
finish()
main.tracker.chance = 0.0
main.body.x, main.body.y, main.body.z = main.SPAWN
main.body.vy = 0.0
main.st.last_xz = (main.body.x, main.body.z)
main.stats.base = {"hp": 50, "atk": 10, "def": 6, "spd": 8}
main.stats.restore_full()


# ---- day and night, villages (stage 5)
from game import daytime        # noqa: E402
from world import boss_arena, villages      # noqa: E402

noon = 0.5 * C.DAY_LENGTH
midnight = 0.0
main.st.world_time = noon
main.st.sky_key = None
main.st.fog_timer = 0.0
main.update()
sky_noon = main.window.color.args[:3]
main.st.world_time = midnight
main.st.sky_key = None
main.st.fog_timer = 0.0
main.update()
sky_night = main.window.color.args[:3]
assert sum(sky_night) < sum(sky_noon) * 0.25, (sky_noon, sky_night)
assert not tints, "by default only the sky darkens at night; the world itself is not tinted"
assert "night" in main.hud_info.text or main.st.info_timer > 0
main.st.info_timer = 0.0
main.update()
assert "Time" in main.hud_info.text and "Village" in main.hud_info.text, main.hud_info.text
t0 = main.st.world_time
for _ in range(60):
    main.update()
assert main.st.world_time > t0, "time must advance"
print("sky noon %s -> midnight %s, hud: %s" % (tuple(round(c, 2) for c in sky_noon), tuple(round(c, 2) for c in sky_night),
                                              main.hud_info.text.replace("\n", " | ")))

# ---- a village: step on the Wood tile and the commands open (no buildings)
import items                     # noqa: E402
v = villages.village_in_region(main.world.seed, 0, 0)
assert main.world.get_block(v.x, v.ground, v.z) == WOOD


def stand_on(x, y, z):
    main.body.x, main.body.y, main.body.z = x, y, z
    main.body.vy = 0.0
    main.st.last_xz = (main.body.x, main.body.z)


stand_on(v.x + 4.5, v.ground + 1.01, v.z - 4.5)
for _ in range(10):
    main.update()
assert main.st.panel is None, "the commands must not open away from the tile"
stand_on(v.x + 0.5, v.ground + 1.01, v.z + 0.5)
main.update()
assert main.st.panel is not None and main.panel_ui.enabled and not main.mouse.locked
assert main.panel_title.text == "VILLAGE " + v.id, main.panel_title.text
assert all(getattr(main, n).enabled is False for n in HUD), "the everyday text must be hidden on the village screen"
before = (main.body.x, main.body.y, main.body.z)
fake.held_keys["w"] = 1.0
for _ in range(20):
    main.update()
fake.held_keys["w"] = 0.0
assert (main.body.x, main.body.y, main.body.z) == before, "the world must stand still while the commands are open"
assert "Inn" in main.panel_buttons[0].text and "Leave" in main.panel_buttons[5].text, [b.text for b in main.panel_buttons[:7]]

# inn through the number keys: needs a common mineral, then heals and becomes the respawn point
main.stats.take_damage(15)
main.input("1")                                          # Inn
main.input("1")                                          # Stay: no mineral to pay with yet
assert "mineral to pay" in main.panel_note.text, main.panel_note.text
common_item = items.item_of(int(items.TIER_CODES[0][0]))
main.inventory.add(common_item, 5)
main.input("1")                                          # Stay
assert main.ctx.respawn == v.stand and main.stats.hp == main.stats.max_hp
assert main.inventory.count(common_item) == 4
# storage: deposit a stack (fee: one common mineral), see it in the village storage, take it back
main.inventory.add(3, 20)
main.input("2")                                          # Back to the main menu ("Back" is option 2 on the inn page)
main.input("2")                                          # Storage
main.input("1")                                          # Deposit
labels = [b.text for b in main.panel_buttons if b.enabled]
idx = next(i for i, t in enumerate(labels) if "Rock" in t)
main.input(str((idx + 1) % 10))
assert main.ctx.book.get(v.id).storage.count(3) == 20 and main.inventory.count(3) == 0, main.panel_note.text
# guide: the boss location; HUD gets a line about him afterwards
main.panel_choose(len([b for b in main.panel_buttons if b.enabled]) - 1)      # Back (to storage)
main.input("3")                                          # Back (storage -> main) is option 3 on the storage page
main.input("4")                                          # Guide
main.input("4")                                          # The Slime King
assert "dig straight down" in main.panel_lines.text.lower(), main.panel_lines.text
assert main.ctx.flags.boss_known
main.input("1")                                          # Back
main.input("5")                                          # Back to the main menu
assert main.panel_title.text.startswith("VILLAGE")
main.input("escape")                                     # Esc leaves
assert main.st.panel is None and main.mouse.locked and not main.panel_ui.enabled
assert all(getattr(main, n).enabled is True for n in HUD)
for _ in range(10):
    main.update()
assert main.st.panel is None, "still standing on the tile: it must not open again"
stand_on(v.x + 3.5, v.ground + 1.01, v.z + 0.5)
main.update()
stand_on(v.x + 0.5, v.ground + 1.01, v.z + 0.5)
main.update()
assert main.st.panel is not None, "stepping off and on again opens it again"
main.input("escape")
main.st.info_timer = 0.0
main.update()
assert "Slime King" in main.hud_info.text, main.hud_info.text

# dying after an inn stay: you wake up on the village tile
main.stats.base = {"hp": 5, "atk": 1, "def": 1, "spd": 1}
main.stats.restore_full()
main.inventory.add(3, 3)
main.open_battle()
main.st.battle.enemy.atk, main.st.battle.enemy.spd = 999, 99
for _ in range(20):
    if main.st.battle.phase != "choose":
        break
    act("tackle")
finish()
assert (round(main.body.x, 2), round(main.body.z, 2)) == (round(v.stand[0], 2), round(v.stand[2], 2)), (main.body.x, main.body.z)
assert main.inventory.used_slots() == 0 and "inn" in main.message.text.lower(), main.message.text
assert main.ctx.book.get(v.id).storage.count(3) == 20, "storage survives death"
for _ in range(5):
    main.update()
assert main.st.panel is None, "waking up on the tile must not pop the commands open"
main.stats.base = {"hp": 50, "atk": 10, "def": 6, "spd": 8}
main.stats.restore_full()
print("village: commands opened on the tile, inn/storage/guide worked, respawn at the inn")

# a night at the inn ends in the morning (and a stay by day leaves the time alone)
stand_on(v.x + 3.5, v.ground + 1.01, v.z + 0.5)
main.update()
main.st.world_time = 0.0                                 # midnight
stand_on(v.x + 0.5, v.ground + 1.01, v.z + 0.5)
main.update()
assert main.st.panel is not None
main.stats.take_damage(10)
main.inventory.add(common_item, 3)
main.input("1"); main.input("1")                         # Inn -> Stay
assert "morning" in main.panel_note.text, main.panel_note.text
assert daytime.daylight(main.st.world_time) > 0.9 and abs(daytime.phase(main.st.world_time) - C.START_TIME) < 1e-6, main.st.world_time
main.input("escape")
main.st.sky_key = None
main.st.fog_timer = 0.0
main.update()
assert sum(main.window.color.args[:3]) > 1.5, "the sky is bright again"
stand_on(v.x + 3.5, v.ground + 1.01, v.z + 0.5)
main.update()
stand_on(v.x + 0.5, v.ground + 1.01, v.z + 0.5)
main.update()
assert main.st.panel is not None and not daytime.is_night(main.st.world_time)
t_day = main.st.world_time                               # (no frames run while the screen is open)
main.stats.take_damage(10)
main.input("1"); main.input("1")
assert main.st.world_time == t_day, "a stay by day does not move the clock"
main.input("escape")
print("inn at night: slept until morning (%s)" % daytime.clock_text(main.st.world_time))

# ---- the Slime King: dig down to his lair, step on the tile, win, the world changes
ax, az = boss_arena.arena_center(main.world.seed)
stand_on(ax + 3.5, 1.01, az + 3.5)
for _ in range(10):
    main.update()
assert main.st.panel is None and main.body.on_ground
stand_on(ax + 0.5, 1.01, az + 0.5)
main.update()
assert main.st.panel is not None and main.panel_title.text == "SLIME KING", main.panel_title.text
main.input("2")                                          # Not yet
assert main.st.panel is None and main.st.battle is None
stand_on(ax + 3.5, 1.01, az + 0.5)
main.update()
stand_on(ax + 0.5, 1.01, az + 0.5)
main.update()
main.input("1")                                          # Fight
assert main.st.battle is not None and main.st.battle.boss and main.battle_ui.enabled
for _ in range(60 * 3):
    main.update()
assert "BOSS" in main.enemy_header.text and "NEXT" in main.enemy_header.text, main.enemy_header.text
assert main.boss_next_swatch.enabled
first_color = main.st.battle.enemy.color
hp_boss = main.st.battle.enemy.max_hp
main.stats.base = {"hp": 4000, "atk": 400, "def": 400, "spd": 400}
main.stats.restore_full()
act("flee")                                              # refused: no escape
assert main.st.battle.phase == "choose" and "no escape" in main.st.battle.log[-1].lower(), main.st.battle.log[-1]
act("tackle")
assert main.st.battle.enemy.color != first_color, "the Slime King changes colour every round"
assert hp_boss - main.st.battle.enemy.hp <= round(hp_boss * C.BOSS_DAMAGE_CAP), "per-hit damage cap"
for _ in range(60):
    if main.st.battle.phase != "choose":
        break
    act("tackle")
assert main.st.battle.phase == "won" and main.st.battle.boss_won
finish()
assert main.ctx.flags.boss_defeated and main.world.extended
assert "rumbles" in main.message.text, main.message.text
assert main.st.battle is None and main.mouse.locked
# afterwards: enemies lose the level cap and use wider colours; villages offer services; the lair is just a room
main.rng = random.Random(3)
main.stats.base = {"hp": 400, "atk": 60, "def": 30, "spd": 30}
main.stats.restore_full()
stand_on(ax + 0.5, 1.01, az + 0.5)
for _ in range(5):
    main.update()
assert main.st.panel is None, "still standing on the tile after the fight: nothing pops up"
stand_on(ax + 3.5, 1.01, az + 0.5)
main.update()
stand_on(ax + 0.5, 1.01, az + 0.5)
main.update()
assert main.st.panel is not None and "gone" in main.panel_lines.text, main.panel_lines.text
main.input("escape")
stand_on(v.x + 3.5, v.ground + 1.01, v.z + 0.5)
main.update()
stand_on(v.x + 0.5, v.ground + 1.01, v.z + 0.5)
main.update()
assert "Services" in [b.text.split(") ", 1)[-1] for b in main.panel_buttons if b.enabled], [b.text for b in main.panel_buttons if b.enabled]
main.input("escape")
main.stats.base = {"hp": 50, "atk": 10, "def": 6, "spd": 8}
main.stats.restore_full()
stand_on(*main.SPAWN)
main.st.last_xz = (main.body.x, main.body.z)
print("boss: lair entered, fight played, flags set; the world is now in its post-boss state")

# ---- save / reload round trip through main.py itself
placed_cell = None
sx, sy, sz = main.SPAWN
main.body.x, main.body.z = sx + 3, sz + 3
main.body.y = main.world.surface_y(int(sx + 3), int(sz + 3)) + 1.01
main.body.vy = 0.0
for _ in range(20):
    main.update()
main.inventory.add(ROCK, 7)
slot = next(i for i, sl in enumerate(main.inventory.slots) if sl and sl[0] == ROCK)
main.input(str(slot + 1) if slot < 9 else "0")
fake.camera.forward = Fake(x=0.0, y=-0.6, z=0.8)        # the ground ahead (straight down would target our own cell)
main.update()
placed_cell = main.st.hit.prev
main.input("right mouse down")
assert main.world.get_block(*placed_cell) == ROCK, "placement failed"
time_before = main.st.world_time
stats_before = (main.stats.level, main.stats.hp, main.stats.color)
pos_before = (main.body.x, main.body.y, main.body.z)
inv_before = [list(x) if x else None for x in main.inventory.slots]

# ---- Esc opens the menu; the world stands still while it is open
main.input("escape")
assert main.st.paused and main.menu.enabled
assert "Smoke Mod" in main.menu_mods.text and "problem" in main.menu_mods.text, main.menu_mods.text
frozen = (main.body.x, main.body.y, main.body.z)
fake.held_keys["w"] = 1.0
for _ in range(30):
    main.update()
assert (main.body.x, main.body.y, main.body.z) == frozen, "player moved while paused"
count = main.inventory.count(ROCK)
main.input("right mouse down")
main.input("q")
assert main.inventory.count(ROCK) == count, "game input leaked through the menu"
fake.held_keys["w"] = 0.0

# ---- Save button
main.menu_save()
assert main.menu_status.text == "Game saved", main.menu_status.text
assert os.path.exists(os.path.join(_tmp, "save", "meta.json"))
print("saved; chunk files:", sorted(os.listdir(os.path.join(_tmp, "save", "chunks"))))

# ---- change things, then Load button must roll them back
main.world.set_block(*placed_cell, 0)
main.inventory.add(ROCK, 3)
main.body.x += 5
main.menu_load()
assert not main.st.paused and not main.menu.enabled, "menu should close after loading"
assert main.world.get_block(*placed_cell) == ROCK, "Load did not restore the saved block"
assert [list(x) if x else None for x in main.inventory.slots] == inv_before, "Load did not restore the inventory"
assert abs(main.body.x - pos_before[0]) < 1e-6
assert (main.stats.level, main.stats.hp, main.stats.color) == stats_before, "HP/colour not restored by Load"
assert main.message.text == "Save loaded"
fake.held_keys["left mouse"] = 1.0                      # still "held" from clicking the menu button
main.update()
assert main.miner.progress == 0.0, "dig button held from a menu click must not start digging"
fake.held_keys["left mouse"] = 0.0
main.update()
print("menu: pause, save, load-with-rollback OK")

# ---- Load with no save file reports instead of crashing
import shutil
tmp_store_dir = os.path.join(_tmp, "save")
shutil.move(tmp_store_dir, tmp_store_dir + "_hidden")
main.input("escape")
main.menu_load()
assert main.st.paused and main.menu_status.text == "No save to load", main.menu_status.text
shutil.move(tmp_store_dir + "_hidden", tmp_store_dir)
main.input("escape")
assert not main.st.paused

# ---- Save and quit
main.input("escape")
main.menu_end()
assert quit_calls, "Save and quit did not quit"
main.input("escape")

fake.held_keys["w"] = 0.0
fake.held_keys["space"] = 0.0
main = importlib.reload(main)                  # = starting the game again
main.tracker.chance = 0.0
main.rng = random.Random(2)
assert main.world.get_block(*placed_cell) == ROCK, "placed block lost after reload"
assert [list(x) if x else None for x in main.inventory.slots] == inv_before, "inventory differs after reload"
assert (main.stats.level, main.stats.hp, main.stats.color) == stats_before, "HP/colour differ after reload"
assert main.ctx.flags.boss_defeated and main.ctx.flags.boss_known and main.world.extended, "flags lost on reload"
assert main.ctx.respawn == villages.village_in_region(main.world.seed, 0, 0).stand, "inn respawn point lost on reload"
assert main.ctx.book.get("0,0").storage.count(3) == 20, "village storage lost on reload"
assert abs(main.st.world_time - time_before) < 2.0, "time of day not restored after reload"   # a few frames pass before the last save
assert main.st.world_time > 1.0, "a restored game must not start the clock from zero"
assert abs(main.body.x - pos_before[0]) < 1e-6 and abs(main.body.z - pos_before[2]) < 1e-6
assert main.message.text.startswith("Save loaded"), main.message.text            # (the MOD notice follows it)
print("reloaded: block, inventory and position restored")


# ---- a brand new game gets a brand new random map (asked through the menu, with a yes/no question)
old_seed = main.world.seed
main.save_now(False)
main.input("escape")
main.menu_new_world()
assert main.st.panel is not None and main.panel_title.text == "NEW WORLD" and not main.st.paused
main.input("2")                                          # No
assert main.world.seed == old_seed and main.st.panel is None
main.input("escape")
assert str(old_seed) in main.menu_seed.text, main.menu_seed.text
main.menu_new_world()
main.input("1")                                          # Yes
assert main.world.seed != old_seed and main.st.panel is None and not main.st.paused
assert str(main.world.seed) in main.message.text and main.inventory.used_slots() == 0 and main.stats.level == 1
assert any("backup" in n for n in os.listdir(_tmp)), os.listdir(_tmp)
assert abs(daytime.phase(main.st.world_time) - C.START_TIME) < 1e-6
assert main.world.get_block(int(main.body.x // 1), int(main.body.y - 1.01 + 0.5), int(main.body.z // 1)) == 2, "starts on grass"
print("new world: seed %d -> %d, old game kept as a backup" % (old_seed, main.world.seed))
main.save_now(False)

# A corrupt save must not stop the game from starting.
(Path(_tmp) / "save" / "meta.json").write_text("{broken")
main = importlib.reload(main)
assert "unreadable" in main.message.text
assert main.world.get_block(*placed_cell) != ROCK, "corrupt save must start a fresh world"
assert any("corrupt" in n for n in os.listdir(_tmp)), "corrupt save should be set aside, not deleted"
print("corrupt save handled; message:", repr(main.message.text))
print("SMOKE OK")
