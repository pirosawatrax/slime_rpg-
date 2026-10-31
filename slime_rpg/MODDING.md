# Making MODs for Slime RPG

A MOD is a folder of **JSON files**. The game never runs code from a MOD, so a MOD cannot harm your computer or your saves.
A MOD can add **new enemy slime types and custom cube blocks**. The game never executes Python code from a MOD.

## Quick start

1. Copy the folder `mods/_template` and rename the copy, for example `mods/my_slimes`.
   (Folders whose names start with `_` or `.` are ignored, which is why the template does nothing by itself.)
2. Open `mod.json` and change `"id"` and `"name"`. Open `slimes.json` and edit or add slimes.
3. Start the game: `python main.py`. At the start of the game you see a short notice if something was wrong, and the pause menu
   (Esc) shows a line such as `MODs: My First MOD (1)`. The terminal you started the game from has the full details.

To use a MODs folder somewhere else: `SLIME_MODS_DIR=/path/to/mods python main.py`.

## Folder layout

```
mods/
  my_slimes/            <- any folder name (not starting with _ or .)
    mod.json            <- who the MOD is
    slimes.json         <- the enemy slimes it adds
    blocks.json         <- optional custom cube blocks
```

## mod.json

| Key | Required | Meaning |
|---|---|---|
| `id` | yes | Unique id: lowercase letters, digits and `_`, 1-48 characters. Two MODs with the same id cannot both load. |
| `name` | yes | Shown in the pause menu. 1-48 characters, one line. |
| `api_version` | yes | Must be `1`. A MOD for a different API version is skipped, so old MODs never half-work. |
| `enabled` | no | `true` (default) or `false` to switch the MOD off without deleting it. It must be a real boolean: `false`, not `"false"`. |
| `version`, `author`, `description` | no | For humans. |

## slimes.json

A list of slimes. Every slime is an object:

| Key | Required | Default | Meaning |
|---|---|---|---|
| `id` | yes | | Unique across all MODs: lowercase letters, digits and `_`. |
| `name` | yes | | Shown in battle (`ENEMY  <name>  Lv 7`). 1-24 printable characters on one line. |
| `weight` | no | `1` | How often it appears, integer 1-100. Plain slimes have weight **10**. The chance of a MOD slime is `weight / (10 + sum of all MOD weights)`: with one slime of weight 2, about 1 fight in 6. |
| `stat_multiplier` | no | `1.0` | 0.25-4. Multiplies the slime's HP, ATK, DEF and SPD (on top of the normal stats for its level, which depend on how deep you are). |
| `color_min`, `color_max` | no | `[60,60,60]`, `[200,200,200]` | Three numbers each, 40-220. The slime's colour is picked at random between them, channel by channel. Colour decides the matchups (see the guide in a village), so a narrow range makes a slime that is reliably weak or strong against certain colours. |

Example: a slime that is always bluish, tougher than normal, and fairly common:

```json
[
  {
    "id": "deep_blue",
    "name": "Deep Blue Slime",
    "weight": 5,
    "stat_multiplier": 1.3,
    "color_min": [60, 60, 150],
    "color_max": [110, 110, 220]
  }
]
```

A MOD slime fights exactly like a plain slime (a tackle, throws and so on), levels with depth like any other enemy and is drawn
with the same pixel slime in its own colour. The Slime King is never replaced.

## Limits (so a mistake cannot break the game)

- A JSON file may be at most 256 KB, a MOD may have at most 50 slimes, and at most 64 MODs are loaded.
- Slime ids must be unique over all MODs. If two collide, the MOD that comes later (alphabetical folder order) is skipped.

## When something is wrong

A MOD with a **mistake that breaks it** is skipped completely (the others still load) and the game says so at the start:
`1 MOD(s) were skipped: <folder>: <what is wrong>`. A **misspelt key** does not break the MOD: it is ignored and reported as a
warning (for example `unknown key "wieght" is ignored (check the spelling)`), which is why a slime that seems to ignore a
setting is worth a look at the terminal output.

| Message | Fix |
|---|---|
| `mod.json is missing` | The folder needs a `mod.json` directly inside it. |
| `unsupported api_version` | Set `"api_version": 1`. |
| `"enabled" must be true or false (without quotes)` | Write `true`/`false`, not `"true"`/`"false"`. |
| `name is too long` / `must not contain line breaks` | Slime names: at most 24 characters, one line. |
| `weight must be an integer from 1 to 100` | No decimals, no quotes. |
| `color_min cannot exceed color_max` | Every channel of `color_min` must be at most the same channel of `color_max`. |
| `duplicate slime id` / `duplicate MOD id` | Ids must be unique over all MODs. |
| `file is too large` / `too many slimes` | See the limits above. |

Changes to a MOD take effect the next time the game starts.

## What MODs cannot do yet

Custom minerals and colours, village trades and requests, music and sounds, custom textures, text translations, custom shapes,
transparent/liquid blocks, and scripts (Python or otherwise) are not supported. Removing a MOD does not damage the save: data
that depends on the missing MOD is safely skipped when loaded.

## Adding custom blocks (API version 1)

A MOD may add blocks with an optional `blocks.json`. `slimes.json` is also optional, so a block-only MOD needs just `mod.json` and `blocks.json`. The included `snow_biome` pack demonstrates two surface materials used by the world generator: snow and ice.

Example folder:

```
mods/
  my_stones/
    mod.json
    blocks.json
```

`blocks.json` is a list of block definitions:

| Key | Required | Default | Meaning |
|---|---|---|---|
| `id` | yes | | Unique lowercase id, digits and `_` allowed. |
| `name` | yes | | Display name, up to 48 printable characters. |
| `hardness` | no | `1.0` | Seconds to mine, from 0.05 to 60. |
| `stack_limit` | no | `64` | Inventory stack size, from 1 to 64. |
| `sound` | no | `rock` | One of `soft`, `rock`, `wood`, `leaf`. |
| `color` | no | `[128,128,128]` | Default RGB color for all faces, each channel 0-255. |
| `top`, `side`, `bottom` | no | `color` | Optional per-face RGB colors, each channel 0-255. |
| `placeable` | no | `true` | Whether the mined block can be placed from the inventory. |

Example:

```json
[
  {
    "id": "red_sandstone",
    "name": "Red Sandstone",
    "hardness": 1.8,
    "stack_limit": 64,
    "sound": "rock",
    "top": [190, 105, 70],
    "side": [165, 80, 55],
    "bottom": [135, 65, 48],
    "placeable": true
  }
]
```

The game assigns each custom block a runtime block ID in the available `uint8` range (7-255). Runtime block IDs are compact and may change when the installed MOD set changes. Saves therefore store custom blocks by their namespaced key (`mod_id:block_id`) in both chunk edits and inventory, then resolve that key at load time. If the MOD is missing, only those unavailable custom blocks/items are skipped rather than being mistaken for a different block. Existing built-in block IDs and existing saves are unchanged.

Limits: up to 64 custom blocks per MOD, 249 custom blocks total, and 256 KB per JSON file. A broken block definition skips its entire MOD; other MODs still load. MOD code is never executed.

The included `_example_stones` folder is an inactive example. Copy it to a new folder whose name does not start with `_` or `.`, then edit `mod.json` and `blocks.json`.

Custom blocks currently support cube geometry and solid-block collision. Custom shapes, transparency, liquid behavior, special mining effects, and custom textures are not supported yet.


## Included example block MODs

The game includes three enabled sample packs:

- `mods/sandstone_colors/`: yellow, red, white and gray sandstone.
- `mods/tree_species/`: birch, pine and darkwood logs and foliage.
- `mods/common_rocks/`: granite, basalt, limestone and red rock. These are ordinary mineral-free geological rocks.

These blocks can be mined, collected, saved and placed like other custom blocks. Log blocks use the `wood` sound family and can also be placed on water as bridges. Leaf blocks use the `leaf` sound family. With the packs enabled, dry climate regions naturally generate shallow sandstone layers, small, scattered geological patches generate the four common rock varieties underground, and rare matching boulders expose them on the surface so they can be found without digging. Climate-based forest regions naturally generate birch, pine and darkwood trees. Their positions and types are deterministic for a world seed and independent of chunk load order. The common rock varieties do not hold minerals; mineral deposits remain exclusive to the original ROCK block. Their generation is deliberately sparse so ordinary ROCK remains the dominant mineral-bearing material.
