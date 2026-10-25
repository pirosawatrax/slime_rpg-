"""All player-facing text lives here (English). Add other languages later by swapping this module."""

GAME_TITLE = "Slime RPG - Stage 1"

INVENTORY_FULL = "Inventory full"
LOST_FMT = "Lost: {name} x{count}"
HUD_INVENTORY = "Inventory {used}/{total}"
HUD_POSITION = "XYZ {x:.0f} {y:.0f} {z:.0f}   Depth {depth}"
EMPTY_SLOT = "(empty)"
HELP_TEXT = "WASD move | Space jump | Hold LMB dig | RMB place | E eat | Wheel/1-0 select | Q discard 1 | Esc menu"

BLOCK_NAMES = {
    "soil": "Soil",
    "grass": "Grass",
    "rock": "Rock",
    "wood": "Wood",
    "leaf": "Leaf",
    "water": "Water",
}

SAVED = "Game saved"
SAVE_FAILED = "Save failed: {reason}"
LOADED = "Save loaded"
SAVE_CORRUPT = "Save file was unreadable and was set aside.\nStarting a new world."
SAVE_TOO_NEW = "This save was made by a newer version of the game (format {found}, this build reads up to {supported})."
WORLDGEN_CHANGED = "Terrain generation changed since this save was made.\nOld edits may look out of place."

MENU_TITLE = "Paused"
MENU_RESUME = "Resume"
MENU_SAVE = "Save"
MENU_LOAD = "Load last save"
MENU_END = "Save and quit"
MENU_LOAD_HINT = "Load discards everything since your last save."
NO_SAVE = "No save to load"
LOAD_FAILED = "Could not read the save file"

MINERAL_NAME = "Mineral ({r},{g},{b})"
HUD_HP = "Lv {level}   XP {xp}/{need}\nHP {hp}/{max_hp}\nATK {atk}  DEF {df}  SPD {spd}"
HUD_COLOR = "Color {r:.0f},{g:.0f},{b:.0f}\nHue {h:.0f}  Sat {s:.0f}%"
HUD_YOU = "You"
HUD_HELD = "Held"
EAT_HEAL = "Ate mineral: HP +{n}"
EAT_HURT = "Ate mineral: HP -{n}"
EAT_NOTHING = "Ate mineral: no effect"
EAT_NOT_MINERAL = "Select a mineral to eat (E)"

# battle (terminal style: "> " = an action, two spaces = its result, "* " = a notice)
BATTLE_TITLE = "SLIME BATTLE"
BATTLE_HEADER_ENEMY = "ENEMY  Slime  Lv {level}\nHP {hp}/{max_hp}   RGB {r:.0f},{g:.0f},{b:.0f}"
BATTLE_HEADER_YOU = "YOU  Lv {level}\nHP {hp}/{max_hp}   RGB {r:.0f},{g:.0f},{b:.0f}"
BATTLE_APPEARED = "* A slime appears!"
BTN_TACKLE = "[A] Tackle"
BTN_THROW = "[T] Throw"
BTN_EAT = "[E] Eat"
BTN_FLEE = "[F] Flee"
BTN_CONTINUE = "[Enter] Continue"
PROMPT_CHOOSE = "> choose an action"
PROMPT_WAIT = "> ...   (Enter: skip)"
PROMPT_CONTINUE = "> press Enter to continue"
BATTLE_HELD = "held: {name}   throw x{throw:.2f}   tackle x{tackle:.2f}"
BATTLE_HELD_NONE = "held: -   (mouse wheel / 1-0 to pick a mineral)   tackle x{tackle:.2f}"
ACT_TACKLE = "> You tackle!"
ACT_ENEMY_TACKLE = "> {who} tackles!"
ACT_THROW = "> You throw {name}!"
ACT_EAT = "> You eat {name}."
ACT_FLEE = "> You try to run away..."
RES_ENEMY_DAMAGE = "  {who} takes {n} damage{tag}."
RES_YOU_DAMAGE = "  You take {n} damage{tag}."
RES_ENEMY_HEAL = "  {who} recovers {n} HP!"
RES_NO_EFFECT = "  No effect."
RES_EAT = "  HP {delta:+d}."
RES_FLEE_OK = "  You got away!"
RES_FLEE_FAIL = "  Blocked! You could not get away."
NOTE_NEED_MINERAL = "* Select a mineral first (mouse wheel or 1-0)."
NOTE_WIN = "* {who} is beaten!"
NOTE_XP = "* +{xp} XP"
NOTE_LEVEL_UP = "* LEVEL UP! Lv {level}  ({gains})"
NOTE_LOSE = "* You were defeated..."
TAG_STRONG = " (strong colour!)"
TAG_WEAK = " (weak colour)"
DEATH_NOTICE = "You died. Everything you carried is lost."
ENCOUNTER_NOTICE = "A slime blocks your way!"

VILLAGE_ENTER = "Village {id}"
HUD_VILLAGE = "Village: {dist:.0f} blocks {dir}"
HUD_VILLAGE_NONE = "Village: none nearby"
HUD_TIME = "Time {clock}  {phase}"
PHASE_DAY = "day"
PHASE_NIGHT = "night"

# ---- village commands (terminal style)
V_TITLE = "VILLAGE {id}"
V_MAIN_LINES = ("A quiet village. What do you need?",)
V_INN = "Inn"
V_STORAGE = "Storage"
V_TRADE = "Trade"
V_GUIDE = "Guide"
V_REQUEST = "Request"
V_SERVICES = "Services"
V_LEAVE = "Leave"
V_BACK = "Back"
V_MORE = "More..."
V_INN_LINES = ("Stay the night: full HP, and this inn becomes your respawn point. At night you sleep until morning.",
               "Fee: {fee} mineral of any colour (the plainest one you carry is used first).")
V_INN_STATUS = "Respawn point: {where}"
V_INN_HERE = "this village"
V_INN_START = "the start point"
V_INN_ELSEWHERE = "another village"
V_STAY = "Stay the night"
V_STAY_OK = "You rest. HP is full and this is now your respawn point."
V_STAY_OK_MORNING = "You sleep until morning. HP is full and this is now your respawn point."
V_STAY_NOTHING = "You are rested already, and this is already your respawn point."
V_NEED_FEE = "You need {fee} mineral to pay the fee. Dig one out of a rock that shows a coloured dot."
V_NEED_FEE_COMMON = "You need {fee} common (muted-colour) mineral for the fee."
V_FEE_WITH = "You would pay with: {name}"
V_FEE_NONE = "You have no mineral to pay with."
V_STORAGE_LINES = ("Slots used: {used}/{cap}.", "Depositing costs {fee} mineral each time (the plainest one you carry). Taking things out is free.",
                   "What you store here survives death.")
V_DEPOSIT = "Deposit"
V_WITHDRAW = "Withdraw"
V_DEPOSIT_LINES = ("Pick a stack of yours to store (the whole stack).", "Fee: {fee} mineral (the plainest one you carry).")
V_WITHDRAW_LINES = ("Pick a stack to take out.",)
V_EMPTY = "(nothing)"
V_STORED = "Stored {name} x{n}."
V_STORAGE_FULL = "The storage is full."
V_STORED_PART = "Stored {name} x{n}; the rest did not fit."
V_TOOK = "Took {name} x{n}."
V_TOOK_PART = "Took {name} x{n}; your inventory is full."
V_NO_ROOM = "Your inventory is full."
V_TRADE_LINES = ("The merchant swaps minerals of the colours she wants for goods.",)
V_TRADE_OFFER = "{qty} {want}  ->  {give}"
V_TRADED = "Traded: you got {give}."
V_TRADE_MISSING = "You do not have {qty} {want}."
V_GUIDE_LINES = ("Ask about:",)
V_G_DANGER = "Dangers"
V_G_COLOURS = "Colours"
V_G_MINERALS = "Minerals"
V_G_BOSS = "The Slime King"
V_G_DANGER_TEXT = ("Enemies grow stronger the deeper you dig: about one level per two blocks below the surface.",
                   "Distance from where you started adds only a little.",
                   "Wood floors, bridges and the Wood tile of a village are safe from encounters.",
                   "At night, slimes find you twice as often on the surface.")
V_G_COLOURS_TEXT = ("Colours beat each other in a cycle: green beats red, blue beats green, red beats blue.",
                    "The same colour is a shield: a good colour also takes less damage from that slime.",
                    "Grey colours have no edge either way. The battle screen shows the multiplier before you throw.")
V_G_MINERALS_TEXT = ("Muted colours lie near the surface. Vivid ones start below 8 blocks, the vividest below 20.",
                     "Eating a mineral heals you if its colour is close to yours and hurts if it is far, and your colour drifts toward it.",
                     "A mineral thrown at a slime hits hard if its colour beats the slime's, and heals the slime if it is weak.")
V_G_BOSS_TEXT = ("The Slime King lives in a room at the very bottom of the world, {dist:.0f} blocks {dir} of here.",
                 "Dig straight down at x {x}, z {z} until you break into the lair, then step on the Wood tile.",
                 "He is level {level}. He changes colour every turn, and you can see the next colour coming.",
                 "No single hit can take more than a fifth of his health, and there is no running away.")
V_G_BOSS_DONE = ("The Slime King is gone. Stranger colours now seep up from the deep, and the slimes above grow without limit.",
                 "The villages offer new services for the new colours.")
V_REQUEST_LINES = ("A villager asks: bring {qty} {want}.", "Reward: {reward}.")
V_REQUEST_REWARD = "{n} more storage slots here"
V_REQUEST_DONE = "Thank you! You helped this village."
V_REQUEST_DONE_LINES = ("The request is done. Thank you!",)
V_HAND_OVER = "Hand them over"
V_SERVICES_LINES = ("New services, paid in the new colours:",)
V_S_EXPAND = "Expand storage (+{n} slots): {qty} {want}"
V_S_TONIC = "Vitality tonic (+{n} max HP): {qty} {want}"
V_S_BOUGHT = "Already bought here."
V_S_EXPANDED = "The storage has {n} more slots."
V_S_TONIC_OK = "You feel sturdier: max HP +{n}."
V_LEFT = "Safe travels."
V_NOTE = "> {text}"

# ---- boss
BOSS_NAME = "Slime King"
BOSS_ASK_LINES = ("A huge slime stirs on the Wood tile...", "Slime King  Lv {level}. He changes colour every turn. No escape.")
BOSS_FIGHT = "Fight"
BOSS_LEAVE = "Not yet"
BOSS_GONE = "Only an empty room. The Slime King is gone."
BATTLE_HEADER_BOSS = "BOSS  Slime King  Lv {level}\nHP {hp}/{max_hp}   RGB {r:.0f},{g:.0f},{b:.0f}\nNEXT  RGB {nr:.0f},{ng:.0f},{nb:.0f}"
NOTE_BOSS_SHIFT = "* The Slime King shifts to RGB {r:.0f},{g:.0f},{b:.0f}."
NOTE_NO_ESCAPE = "* There is no escape from the Slime King!"
NOTE_BOSS_FALLS = "* The ground rumbles. New colours stir in the deep!"
HUD_BOSS = "Slime King: {dist:.0f} blocks {dir}"
RESPAWN_INN = "You wake up at the inn."

MENU_NEW = "New world"
MENU_SEED = "World seed: {seed}"
NEW_WORLD = "A new world! Seed {seed}.\nYour old game is kept in a backup folder."
NEW_WORLD_TITLE = "NEW WORLD"
NEW_WORLD_LINES = ("Start a new game on a new, random map?", "Your current game is saved first and kept in a backup folder.",
                   "(You can also start with a chosen map: python main.py --seed 12345)")
NEW_WORLD_YES = "Yes, start a new world"
NEW_WORLD_NO = "No, keep playing"
