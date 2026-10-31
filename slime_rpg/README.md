# Slime RPG - Stage 6

Chunked voxel world with fog, hold-to-break mining, bridges, a 20-slot inventory, save/load, minerals you can dig,
carry and eat, terminal-style slime battles, levels, death, villages with commands, a day/night cycle and the Slime King.
Design document: `slime_rpg_design_v3.md` (stages 1-6 of section 13; day/night, the terminal battle screen and the
one-tile villages were decided after that document was written).

## Run

    pip install -r requirements.txt
    python main.py          # continues the saved world if there is one (otherwise a new random map)
    python main.py --new    # a new game on a new random map; the old save is moved aside, never deleted
    python main.py --seed N # a new game on map N

On Linux, `main.py` sets `XMODIFIERS=@im=none` itself (before Ursina loads) so fcitx5/ibus cannot swallow
key-release events (symptom: keys keep "holding" and Space does nothing). `SLIME_KEEP_IME=1 python main.py` opts out.

## MODs

The game supports **data-only MODs**: folders of JSON files in `mods/` (or in the folder named by `SLIME_MODS_DIR`). The game never
runs code from a MOD. A MOD can add **new enemy slime types** and **custom cube blocks** with individual colours, hardness, sounds,
and inventory drops.

Included examples: `mods/crystal_slime` adds a Crystal Slime; `mods/sandstone_colors` adds four sandstone colours;
`mods/tree_species` adds birch, pine and darkwood logs and leaves; `mods/common_rocks` adds granite, basalt, limestone and red rock. Dry regions naturally generate sandstone layers, small, scattered geological patches naturally generate the four ordinary rock varieties underground, with rare matching outcrops also appearing on the surface, and climate-based forests naturally grow the tree species. The four common rock varieties do not contain minerals; mineral deposits remain exclusive to the original gray ROCK blocks. Custom wood logs can also be placed on water as bridges.

**To add a MOD:** copy `mods/_template`, rename the copy, and edit `mod.json` plus `slimes.json` and/or `blocks.json`. Restart the game.
The full format, limits and troubleshooting guide are in **[MODDING.md](MODDING.md)**.

**Feedback while you work:** a MOD that cannot load is skipped (the others still load) and the game tells you at the start, in the
terminal and on screen; the pause menu (Esc) lists the loaded MODs and counts problems. A misspelt key is ignored and reported as a
warning, so it never fails silently. A MOD has hard limits (file size, slimes per MOD, number of MODs) so that a mistake cannot break
the game. Saves do not depend on MODs, so removing a MOD never damages a save.

Not supported yet: custom minerals, village trades, music, textures, translations, custom shapes and scripts. Python-script MODs are
intentionally not enabled, because they could run arbitrary code on the player's computer.

## Snowy regions

Cold-climate areas appear naturally within the ordinary world; no separate map or new game mode is needed. The temperature field is shared with the tree-species climate: colder patches become snow-covered, exposed lake water becomes walkable ice while the water remains underneath, and the existing pine-tree preference makes snowy forests feel distinct. Snow replaces only the surface grass block, so terrain height, caves, underground minerals and the surrounding map layout stay unchanged. Village plots are kept clear.

## Flower cultivation

Digging Soil or Grass has a 2.5% chance to uncover a colour-coded flower seed. Select the seed and right-click a Grass/Soil block beside water to plant it in the empty cell above. The seedling appears on a thin brown tile with a small green sprout; after one full in-game day (600 seconds), the tile shows a coloured flower. The tile is decorative and does not behave like a full-height solid block. Breaking an immature seedling returns its seed; breaking a mature flower yields the mineral with the same colour code. Plant colour and planting time are saved with the chunk, so growth continues correctly after reloading.

## Controls

| Input | Action |
|---|---|
| WASD / Space | Move / jump |
| Hold left mouse | Dig (hold time depends on the block) |
| Right mouse | Place the selected block (water accepts Wood only: bridges) |
| Mouse wheel, 1-0 | Select inventory slot |
| E | Eat the selected mineral |
| In a battle: A / T / E / F | Tackle / Throw / Eat / Flee (or click the buttons) |
| In a battle: Enter or Space | Skip the typing, then continue after the fight |
| Q | Discard one item from the selected slot |
| Esc | Open / close the pause menu (Resume, Save, Load last save, Save and quit) |

## Villages, the Slime King and the post-boss world (stage 6)

**Village commands** (a terminal-style screen; pick with the number keys 1-9 and 0, or click; Esc leaves). The world
stands still while it is open. Everything a village offers is decided by the seed and the village, so nothing is stored
except what you change.

| Command | What it does |
|---|---|
| Inn | Stay the night for **1 mineral of any colour** (the plainest one you carry is used first; the screen shows which one): full HP, and this inn becomes your **respawn point**. **Staying at night skips to the next morning (07:12)**; by day the clock is left alone. When you die you wake up at the last inn you slept at (the start point if you never did). |
| Storage | 20 slots **per village** (not shared). Depositing a stack costs 1 mineral (any colour, plainest first); taking things out is free. Survives death. |
| Trade | The merchant swaps minerals of the colours *she* wants for goods: Wood x24, Rock x32, or one rare mineral. Every village wants different colours, which is what gives colours a value. |
| Guide | Tips about dangers, colours and minerals, and **where the Slime King lives** (coordinates, direction, distance). Telling you puts a line in the HUD. |
| Request | Bring 2 minerals of the villager's rare colour: +5 storage slots in this village (once). |
| Services | **Only after the boss.** Paid in the new colours, once per village: +10 storage slots, or a Vitality Tonic (+10 max HP, permanent). |

**The Slime King:** his lair is a 17x17 room at the very bottom of the world (Y 1-8), a few hundred blocks from the origin.
You dig down to it (the guide gives x and z) and step onto the Wood tile in the middle; a screen asks if you want to fight.
- A level-30 slime with fixed stats (no variation). Low attack, high defence on purpose, so a plain tackle is weak and
  **well-chosen colours (throwing a mineral that beats his current colour) are what win**.
- **He changes colour every round, and the next colour is shown in the header** (with a swatch), so you can eat a
  mineral to move your own colour before it matters. A colour change is always at least 90 apart.
- **No single hit takes more than 20% of his HP** (so over-levelling cannot skip the fight: at least 5 hits), and there
  is **no fleeing**. Winning gives triple XP.
- Simulated balance (`BOSS_STAT_MULT`): tackling only wins at level 25/30/35 about 0/36/90% of the time; a player who
  throws well-matched minerals and eats to heal wins about 69/92/96%.

**After the boss falls:** (saved at once)
1. Enemy levels are no longer capped at 90% of the boss's level.
2. **New colours** appear: channels now run 40..220 (10 levels, 1000 colours) instead of 60..200 (512). About a third
   of the ore in newly generated chunks turns into the new colours; chunks you have not changed are regenerated at once.
   Enemies and the Slime King's own colours use the wider range too.
3. Villages offer the Services above, paid in the new colours.

**Ore** is a single small dot on a rock face (1 of 9 cells, `ORE_CELLS`), no longer meant to be seen from far away.
Underground ore is about twice as common as before (3.2% of rock near the surface, 4.1% below 20 blocks: the deeper, the
richer) while surface boulders hold little, so ore no longer piles up on the surface.

**Caves** are Minecraft-like: winding tunnels (two noise fields both near 0.5), a finer second network and big caverns,
about 13% of the underground, and almost all of it one connected network. A scatter of **entrances** (about 3% of land
columns) lets caves break through to the surface; trees and boulders keep clear of them. Lake beds and the bottom three
layers stay sealed. Tune in `config.py` (`CAVE_*`).

**Music** is composed in code (`audio/music.py`, `audio/director.py`) and written to `assets/music/` (about a second at start-up):
slow (72 BPM) C-major-pentatonic bell melody over pads, bass and a soft arpeggio while you explore; a fast (156 BPM)
A-minor-pentatonic riff with driving bass, arpeggio and drums in battles.
- **A different tune every time:** every launch composes new tunes (random seed), and every time a tune is used a new one of that
  kind is composed in a background thread, so the next fight and the next stretch of exploring sound different. (The first fight of a
  launch uses the tune made at start-up.)
- **Silence and hiss:** Panda3D streams sound files over 1 MB from disk, and a slow frame then makes the stream stutter, go silent or
  hiss. `main.py` now tells Panda to load the tunes whole (`audio-preload-threshold`), and a watchdog checks every 1.5 s that the
  active tune is really playing and restarts it if not (a line "music: ... had stopped; restarting it" appears in the console).
- `SLIME_NO_MUSIC=1 python main.py` turns the music off. Volume: `MUSIC_VOLUME`.

**Maps:** a new game gets a **random map** (`world/seeds.py`); a saved game keeps its own map (its villages, caves and your edits
belong to it). The pause menu has **New world** (asks first; the old game is kept in a backup folder next to the save) and shows the
current seed. `python main.py --seed 12345` starts a new game on a chosen map (any existing save is kept as a backup).
The start point is the nearest open patch of grass to the origin, never inside a tree or a hole (`world/spawn.py`).

**Battle and village screens** hide the everyday overlay (inventory, status, key help, crosshair). The pixel slimes have two
black dot eyes (no whites, no mouth).

## World, villages, day and night (stage 5)

- **Water:** terrain features are smaller now (`TERRAIN_SCALES`), so lakes and rivers are narrower: 90% of water
  crossings are under about 40 blocks, 99% under about 70 (2-3 stacks of Wood for a bridge). Wide seas still exist but
  are rare. No slope is too steep to jump up.
- **Villages:** the world is cut into 128-block regions; each region hashes to "no village" (about 40%) or one village
  on gentle dry land, so a village is the same in every chunk and every save without storing anything. A village has
  **no buildings**: a small levelled patch with ONE Wood tile in the middle and a signpost (post + crossbar + tip) beside it
  made of **Water blocks**: blue, so it cannot be mistaken for a tree, and water cannot be dug out, so it cannot be destroyed.
  **Step onto the Wood tile and the village commands open** (see below). The HUD shows the nearest village and its
  compass direction. The tile is Wood, so it is safe from encounters.
- **Day and night:** one day lasts 10 minutes (`DAY_LENGTH`); a new game starts in the morning. **Only the sky changes**
  (light blue by day, orange at sunrise/sunset, dark blue at night); the distant fog shares the sky colour so the
  horizon blends, and everything near you stays as bright as by day. (`NIGHT_WORLD_TINT` can darken the whole world
  at night if you ever want that; it is off by default.) Underground nothing changes. **At night the encounter chance
  goes up to 2x** (surface only). The time of day is saved.
- Old saves: terrain generation changed (`WORLDGEN_VERSION` 6), so older saves show a warning; use `--new`. Old saves
  still load (format 2 converts the minerals of format-1 saves), but the world may look different around old edits.

## Battles (stage 4, terminal style since stage 5)

- **Screen:** a black screen with green text. Every round is played back one line at a time with a typewriter effect:
  `> You tackle!` (whoosh) then `  Slime takes 12 damage.` (impact), then the same for the enemy; level-ups and
  results are `*` lines. The HP numbers change only when the line that caused them appears. HP is shown as numbers
  only (no bars), plus each side's RGB colour. Both slimes are the same 32x32 pixel-art slime tinted with their colour
  (`game/sprites.py`). Press Enter to skip the typing.

- **Encounters:** walking on the ground counts steps (blocks walked). After 12 safe steps each step has a 3.5% chance
  of a battle (about 40 blocks on average). Walking on a **Wood** floor or bridge never counts and never triggers one.
  Digging and standing still do not count. Nothing is saved about enemies: they are made when the fight starts.
- **Enemy level:** mostly depth below the surface (0.5 level per block), plus a small saturating bonus for distance
  from the start point (at most +6). Until the final boss exists (stage 6) no ordinary enemy exceeds 90% of the boss
  level (27). Enemy colour is random in 60..200; its stats are 85% of the average for its level, +-10%.
- **Round:** you pick an action, then the faster side acts first (ties: you). Actions:
  - **Tackle:** damage = a share of the target's max HP (so fights last ~5 rounds at any level) x ATK/(ATK+DEF) x
    colour matchup x luck. Enemies tackle with the same rule, so *your* colour matters when they hit you too.
  - **Throw (selected mineral):** costs the mineral. Colour matchup of the mineral vs the enemy: strong = big damage,
    weak = it heals the enemy. The screen shows the multiplier for the held mineral before you commit.
  - **Eat (selected mineral):** same effect as eating outside battle, but it costs your turn.
  - **Flee:** 50% at equal speed, +3% per point of speed advantage (15%..95%). A failed attempt costs a hit.
  - Change the held slot with the mouse wheel or 1-0 during a fight.
- **Levels:** XP = 6 x enemy level x clamp(enemy level / yours, 0.25..2). Level L to L+1 costs 8 x L^2 XP. Each level
  hands out 4-6 random growth points to HP / ATK / DEF / SPD (HP is likeliest; one point = +4 HP or +1 stat), so growth
  slows because levels cost more. There is no level cap.
- **Death:** when HP reaches 0 you lose **everything you carry**, wake at the start point with full HP, and the game
  is saved at once. Level, XP, colour, the world and (later) storage are kept. Respawning at an inn comes with villages.
  Eating can never kill you (HP stays at 1 or more).
- Esc does nothing during a battle; closing the window mid-battle saves the current (damaged) state.

## Minerals (stage 3)

- **Colours:** 8 levels per channel (60, 80, ... 200) = 512 colours. Your slime starts grey (130,130,130).
- **Where:** about 1.7% of rock holds a mineral, more in "rich zones", plus small rock outcrops on the surface
  (30% ore) so you can spot colour without digging first. Only rock holds ore.
- **Rarity** follows how vivid the colour is: muted = common (stack 32, ~2.3 s to dig), vivid = rare (stack 16, ~3.8 s).
  Uncommon colours start 8 blocks below the surface, rare ones at 20. Digging ore gives the mineral and the rock;
  if the inventory is short of space the rock is lost first.
- **Looking at ore:** each ore face shows 6 of 9 cells in the mineral colour (brightened by `ORE_GLOW`, so it reads
  at range). The HUD shows your colour/hue/saturation, and a "Held" swatch shows the true colour of the selected mineral.
- **Eating (E):** within `EAT_SAFE_DISTANCE` (RGB distance) of your colour it heals up to 25% of max HP; beyond it you
  lose up to 15%. Either way your colour moves 20% toward the mineral. HP cannot drop below 1 until death arrives in stage 5.
- **Matchup** (`game/colors.py`, used by combat in stage 4): `1 + 0.5 * sin(hue difference) * saturation factor`.
  One-way three-cycle, grey = neutral, mirrored when attacker and defender swap.

## Saving

- Location: `saves/default/` next to `main.py` (override with the `SLIME_SAVE_DIR` environment variable).
- Saved: world seed, player position/view, inventory, selected slot, spawn point, and every block you changed.
- Save from the Esc menu. Autosave every `AUTOSAVE_SECONDS` (120 s), on "Save and quit", and when the window is closed.
- "Load last save" rolls the world back to the last save; everything since then is discarded.
- No function keys are used, so nothing can clash with Ursina's own hotkeys.
- Format: `meta.json` plus one `chunks/c_<cx>_<cz>.json` per edited chunk (a diff over generated terrain,
  so only changed chunks are written). Writes go to a temp file and are renamed into place.
- `config.SAVE_VERSION` is the file format; a save from a newer build is refused untouched. A corrupt save is moved
  to `default.corrupt-<time>` and a new world starts. `config.WORLDGEN_VERSION` flags terrain changes: bump it
  whenever you change terrain generation, since old diffs may no longer fit.

## Tests (no Ursina needed)

    python -m unittest discover -s tests -t .     # 240 engine-free tests
    python tests/smoke_stub.py                    # runs main.py's loop against a fake ursina module

## Layout

    main.py            Ursina glue only: window, camera, HUD, chunk entities, input
    config.py          every tunable number
    strings.py         every player-facing string (English)
    blocks.py          built-in block types; MOD blocks add their own hardness, drops and colours
    world/             noise, worldgen, villages (tile + signpost), boss_arena (the lair), seeds, spawn, world, mesher, manager
    save/              store (files, atomic writes, validation), game_save (live objects <-> files)
    items.py           item ids; minerals = 1000 + colour code (rarity tiers, stack limits, dig times)
    game/              raycast, physics, inventory, mining, building, fog, colors, eating, stats,
                       progression (levels, xp, enemy level), battle (events), presenter (typewriter),
                       sprites (pixel slime), encounter, death, daytime,
                       village (command screens as a state machine), village_data (what each village offers)
    audio/sfx.py       procedural sound effects -> assets/sfx/*.wav (written on first run)
    audio/music.py     composes and renders the background tunes; audio/director.py keeps them playing and makes new ones

## Tuning

- Dig times: `blocks.py` (`hardness`). Hit-sound rate: `config.HIT_INTERVAL`.
- Terrain / lakes / caves / trees: `config.py` (`TERRAIN_*`, `CAVE_THRESHOLD`, `TREE_CHANCE`).
- View distance: `config.RENDER_RADIUS` (chunks).

## Known limits of this build

- The battle screen uses Ursina `Button`s, `Entity(origin=...)` bars and `Entity.scale_x`; if the bars or buttons look
  wrong on first run, that is where to look (`main.py`, "battle screen"). The sprites rely on texture transparency:
  transparent pixels are black, so on the black battle screen they are invisible even if transparency is off.
- Night darkening uses `scene.setColorScale`; if the world does not darken at night, look at `apply_fog()`.
- Written and tested without a real Ursina install. Engine-free logic is covered by tests; the
  Ursina calls in `main.py` are not. If something looks wrong on first run, check these first:
  1. Fog not fading distant terrain: `on_mesh()` sets `e.shader = None` so scene fog applies.
  2. Terrain colours missing: vertex colours on `Mesh(colors=...)`.
  3. No sounds: `Audio(name)` looks the wav up under the project folder.
  4. Crack overlay invisible: `make_crack_textures()` (needs Pillow; falls back to a dark overlay).
- Saved: level, XP, the four stats, HP, colour, inventory, time of day, village storage and progress, the inn respawn
  point, whether the boss has fallen and whether the guide has told you where he lives.
- Block meshes are opaque, including water and leaves.
