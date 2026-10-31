"""Global tunables. Stage 1 values are initial guesses; adjust while playing."""

SEED = 12345

# World layout (cell space: block (x, y, z) occupies [x, x+1) on each axis)
CHUNK_SIZE = 16
WORLD_HEIGHT = 64
SECTION_HEIGHT = 16
SECTIONS_PER_CHUNK = WORLD_HEIGHT // SECTION_HEIGHT
SEA_LEVEL = 30  # top Y of water; land columns have top Y >= SEA_LEVEL

# Terrain shape
TERRAIN_BASE = SEA_LEVEL + 4
TERRAIN_AMP = 14
TERRAIN_SCALES = (40.0, 20.0, 10.0)   # noise feature sizes in blocks: smaller = narrower lakes (stage 5: ~99% of water is < 70 wide)
TREE_CHANCE = 0.012
# Caves (stage 6, Minecraft-like): winding tunnels where two noise fields are both near 0.5, a finer second network, and
# big caverns. About 16% of everything underground is hollow and almost all of it is one connected network.
CAVE_TUNNEL = (0.07, 24.0)           # (half-width in noise units, feature size in blocks)
CAVE_FINE = (0.05, 12.0)
CAVE_CAVERN = (0.80, 30.0)           # (noise level above which a big cavern opens, feature size)
CAVE_Y_SQUASH = 1.8                  # >1 makes tunnels run more horizontally than vertically
CAVE_SKIN = 3                        # caves stay this far below the surface ...
CAVE_ENTRANCE = (0.70, 18.0)         # ... except in "entrance" spots (2D noise above this level), where they can break through

# Streaming (in chunks)
RENDER_RADIUS = 4            # chunks that get meshes
DATA_RADIUS = RENDER_RADIUS + 1   # chunks whose block data exists (needed for face culling)
UNLOAD_RADIUS = RENDER_RADIUS + 2

# Player
PLAYER_WIDTH = 0.6
PLAYER_HEIGHT = 0.9
EYE_HEIGHT = 0.75
MOVE_SPEED = 4.5
GRAVITY = 26.0
JUMP_SPEED = 8.5
TERMINAL_VELOCITY = -40.0
REACH = 5.5
WATER_BARRIER_HEIGHT = 2     # invisible wall above water so it cannot be stood on
MOUSE_SENSITIVITY = 40.0

# Inventory
INVENTORY_SLOTS = 20

# Mining
HIT_INTERVAL = 0.25          # seconds between hit sounds while holding the button
BREAK_COOLDOWN = 0.15
FLOWER_SEED_CHANCE = 0.025      # chance per dug soil/grass block to find a colour-coded flower seed        # pause after a block breaks
MESSAGE_COOLDOWN = 1.0       # throttle for "Inventory full" messages

# Fog (distance in blocks) at the surface and deep underground
FOG_SURFACE = (24.0, 56.0)
FOG_DEEP = (3.0, 22.0)
FOG_COLOR_SURFACE = (0.60, 0.78, 0.95)
FOG_COLOR_DEEP = (0.02, 0.02, 0.04)
FOG_FULL_DARK_DEPTH = 24     # blocks below the surface where fog reaches the deep values

# Saving
SAVE_VERSION = 2             # bump when the save FORMAT changes (add a migration in save/store.py)
WORLDGEN_VERSION = 11         # bump when terrain generation changes: old chunk diffs may no longer fit
AUTOSAVE_SECONDS = 120

# Minerals (stage 3). Colours are 8 levels per channel: 60, 80, ... 200 (512 colours).
MINERAL_BASE_P = 0.012          # chance that a rock cell holds a mineral (underground)
MINERAL_RICH_P = 0.14           # ... inside "rich zones" (clusters)
MINERAL_RICH_THRESHOLD = 0.72   # 3D noise level that marks a rich zone
OUTCROP_CHANCE = 0.004          # surface rock outcrops per land column
OUTCROP_MINERAL_P = 0.10        # mineral chance inside surface outcrops (lower: ore should not pile up on the surface)
OUTCROP_DEPTH = 8               # outcrops count as this deep, so they can hold uncommon colours
MINERAL_DEPTH_BOOST = 0.5       # ore gets this much denser (x1.5) by depth DEPTH_BOOST_FULL, so going deeper pays
DEPTH_BOOST_FULL = 24
TIER_DEPTHS = (8, 20)           # blocks below the surface where uncommon / rare colours start to appear
ORE_GLOW = 0.5                  # 0 = true colour, 1 = fully brightened (ore no longer needs to be visible from afar)
ORE_CELLS = 1                   # of the 9 cells on an ore face, how many show the mineral colour (a single small dot)
ORE_ROCK_CELL_SHADE = 0.85      # brightness of the plain-rock cells between the mineral cells

# Eating (stage 3)
EAT_SAFE_DISTANCE = 110.0       # RGB distance up to which eating heals
EAT_HEAL_MAX = 0.25             # fraction of max HP healed by an identical colour
EAT_HURT_MAX = 0.15             # fraction of max HP lost at the largest possible distance
EAT_COLOR_MIX = 0.20            # how far the slime's colour moves toward the mineral

# Colour matchup (stage 3 function, used by combat in stage 4)
MATCHUP_K = 0.5                 # multiplier range is 1 +- K

# Player
START_COLOR = (130.0, 130.0, 130.0)

# ---- Stage 4: growth, enemies, battle, encounters -------------------------------------------------------------
START_STATS = {"hp": 50, "atk": 10, "def": 6, "spd": 8}
GROWTH_POINTS = (4, 6)                                   # random points handed out at each level-up
GROWTH_WEIGHTS = {"hp": 3.0, "atk": 1.5, "def": 1.5, "spd": 1.0}      # how likely each stat gets a point
GROWTH_PER_POINT = {"hp": 4, "atk": 1, "def": 1, "spd": 1}           # stat gained per point
XP_NEED = 8                      # xp to go from level L to L+1 is XP_NEED * L^2 (growth slows down)
XP_BASE = 6                      # reward = XP_BASE * enemy level * clamp(enemy level / your level)
XP_RATIO_RANGE = (0.25, 2.0)

BOSS_LEVEL = 30                  # the final boss (stage 6) has a fixed level
ENEMY_CAP_FRACTION = 0.9         # before the boss falls, no ordinary enemy exceeds this share of the boss level
LEVEL_PER_DEPTH = 0.5            # enemy level gained per block below the surface (depth is the main driver)
DISTANCE_LEVEL_MAX = 6.0         # levels that distance from the start can add at most (slow, saturating)
DISTANCE_SCALE = 600.0           # blocks; larger = the distance bonus grows more slowly
ENEMY_STAT_VARIATION = 0.10      # each enemy stat is +-10% of the average for its level

TACKLE_FRACTION = 0.40           # share of the target's max HP a tackle takes at equal ATK/DEF and neutral colours is half of this
THROW_FRACTION = 0.60            # a thrown mineral hits harder than a tackle, but costs the mineral
ENEMY_STRENGTH = 0.85            # ordinary enemies have this share of the average stats for their level
THROW_NEUTRAL = 0.75             # a thrown mineral does nothing at this matchup; weaker heals the enemy, stronger hurts
THROW_SLOPE = 4.0
DAMAGE_RANDOM = 0.10
FLEE_BASE = 0.5
FLEE_PER_SPD = 0.03
FLEE_LIMITS = (0.15, 0.95)

ENCOUNTER_SAFE_STEPS = 12        # steps after a battle (or load) with no encounters
ENCOUNTER_CHANCE = 0.035         # per step after that; walking on Wood never triggers one

# ---- Stage 5: villages, day and night ------------------------------------------------------------------------
VILLAGE_REGION = 128             # the world is cut into square regions; each may hold one village
VILLAGE_CHANCE = 0.7
VILLAGE_HALF = 2                 # the village is a levelled (2*HALF+1)-square patch with ONE Wood tile in the middle
VILLAGE_TREE_MARGIN = 4          # no trees or boulders this close to the patch

DAY_LENGTH = 600.0               # seconds for a full day and night
START_TIME = 0.30                # fraction of the day when a NEW game starts (0 = midnight, 0.5 = noon)
NIGHT_ENCOUNTER_MULT = 2.0       # encounter chance multiplier in full darkness, on the surface only
NIGHT_UNDERGROUND_DEPTH = 3      # deeper than this, day and night make no difference
SKY_DAY = (0.60, 0.78, 0.95)
SKY_NIGHT = (0.03, 0.04, 0.12)
SKY_DUSK = (0.95, 0.55, 0.35)
NIGHT_WORLD_TINT = (1.0, 1.0, 1.0)        # optional darkening of the whole world at night; (1,1,1) = only the sky changes

# ---- Stage 6: colours after the boss, the boss, village services ---------------------------------------------
BASE_COLOR_RANGE = (60.0, 200.0)         # colours of enemies and minerals before the boss falls
EXTENDED_COLOR_RANGE = (40.0, 220.0)     # ... and after
NEW_COLOR_SHARE = 0.35                   # share of ore cells that hold a post-boss colour once the boss has fallen

STORAGE_SLOTS = 20               # slots in a village storage (each village has its own)
STORAGE_REQUEST_BONUS = 5        # extra slots for finishing the village request
STORAGE_EXPAND_BONUS = 10        # extra slots from the post-boss service
TONIC_HP = 10                    # permanent max HP from the post-boss tonic
INN_FEE = 1                      # minerals for a night at the inn
STORAGE_FEE = 1                  # minerals for each deposit
FEE_ANY_MINERAL = True           # True: a fee can be paid with any mineral (the plainest one you carry is used first).
                                 # False: only common (muted) colours are accepted

BOSS_DISTANCE = (220, 320)       # the boss lair lies this far from the world origin
# The boss is the average BOSS_LEVEL slime times these (fixed, no variation). Low attack and high defence on purpose:
# a plain tackle falls short of the damage cap, so well-chosen colours (throws) are what make the fight shorter and safer.
# (simulated: tackle-only wins at level 25/30/35 = 0/36/90%, a player using colours wins 69/92/96%)
BOSS_STAT_MULT = {"hp": 1.0, "atk": 0.45, "def": 2.4, "spd": 1.0}
BOSS_DAMAGE_CAP = 0.20           # one hit never takes more than this share of the boss's max HP
BOSS_XP_MULT = 3.0
BOSS_COLOR_MIN_DISTANCE = 90.0   # a colour change is at least this far from the current colour
ARENA_HALF = 8                   # the lair is a (2*HALF+1)-square room ...
ARENA_HEIGHT = 8                 # ... from the world floor up to this Y

# ---- Background music (generated in code, see audio/music.py) -------------------------------------------------
MUSIC_VOLUME = 0.30
MUSIC_SEED = 2026
