"""Safe, data-only MOD loader for Slime RPG. MODs are JSON, never imported Python code.

A MOD is a folder inside the mods directory:

    mods/<any_folder_name>/mod.json       who the MOD is (id, name, api_version, ...)
    mods/<any_folder_name>/slimes.json    a list of enemy slime types it adds

Folders whose name starts with "_" or "." are ignored (mods/_template/ is a copy-me starting point).
A broken MOD is skipped and reported in `errors`; the other MODs still load. Mistakes that do not break a MOD, such as
a misspelled key, are reported in `warnings` (the key is ignored)."""
from dataclasses import dataclass, field
import json
import math
from pathlib import Path
import re

API_VERSION = 1
ID_RE = re.compile(r"^[a-z0-9_]{1,48}$")

MAX_FILE_BYTES = 256 * 1024          # one JSON file of a MOD
MAX_MODS = 64
MAX_SLIMES_PER_MOD = 50
MAX_BLOCKS_PER_MOD = 64
MAX_TOTAL_BLOCKS = 249
BLOCK_KEYS = {"id", "name", "hardness", "stack_limit", "sound", "color", "top", "side", "bottom", "placeable"}
BLOCK_SOUNDS = {"soft", "rock", "wood", "leaf"}
MOD_NAME_MAX = 48
SLIME_NAME_MAX = 24                  # it must fit the battle screen: "ENEMY  <name>  Lv 99"

MOD_KEYS = {"id", "name", "version", "api_version", "enabled", "author", "description"}
SLIME_KEYS = {"id", "name", "weight", "stat_multiplier", "color_min", "color_max"}


@dataclass
class ModLoadResult:
    slimes: list = field(default_factory=list)
    blocks: list = field(default_factory=list)
    loaded: list = field(default_factory=list)
    errors: list = field(default_factory=list)       # MODs that were skipped, and why
    warnings: list = field(default_factory=list)     # things that were ignored but did not break the MOD


def _read_json(path):
    size = path.stat().st_size
    if size > MAX_FILE_BYTES:
        raise ValueError(f"{path.name} is too large ({size // 1024} KB; the limit is {MAX_FILE_BYTES // 1024} KB)")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _clean_name(value, what, max_len):
    """A display name: 1..max_len printable characters on one line (it is drawn on the battle screen)."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{what} must be text")
    value = value.strip()
    if len(value) > max_len:
        raise ValueError(f"{what} is too long ({len(value)} characters; the limit is {max_len})")
    if not value.isprintable():
        raise ValueError(f"{what} must not contain line breaks or control characters")
    return value


def _valid_rgb_range(value, field_name):
    if not isinstance(value, list) or len(value) != 3:
        raise ValueError(f"{field_name} must be a three-number list")
    if any(not isinstance(n, (int, float)) or isinstance(n, bool) or not 40 <= n <= 220 for n in value):
        raise ValueError(f"{field_name} channels must be between 40 and 220")
    return tuple(float(n) for n in value)


def _unknown_keys(obj, allowed, where, warnings):
    for key in sorted(set(obj) - allowed):
        warnings.append(f"{where}: unknown key \"{key}\" is ignored (check the spelling)")


def load_mods(mods_dir):
    """Load enabled JSON mods. A bad mod is skipped and reported; other mods still load."""
    result = ModLoadResult()
    mods_dir = Path(mods_dir)
    if not mods_dir.exists():
        return result
    if not mods_dir.is_dir():
        result.errors.append(f"MOD path is not a directory: {mods_dir}")
        return result

    seen_mod_ids = set()
    seen_slime_ids = set()
    seen_block_ids = set()
    for folder in sorted(mods_dir.iterdir(), key=lambda p: p.name.lower()):
        if not folder.is_dir() or folder.name.startswith((".", "_")):
            continue
        if len(result.loaded) >= MAX_MODS:
            result.errors.append(f"{folder.name}: too many MODs (the limit is {MAX_MODS})")
            continue
        try:
            meta_path = folder / "mod.json"
            if not meta_path.is_file():
                raise ValueError("mod.json is missing")
            meta = _read_json(meta_path)
            if not isinstance(meta, dict):
                raise ValueError("mod.json must contain an object")
            mod_id = meta.get("id")
            if not isinstance(mod_id, str) or not ID_RE.fullmatch(mod_id):
                raise ValueError("id must use lowercase letters, numbers and underscores")
            if mod_id in seen_mod_ids:
                raise ValueError(f"duplicate MOD id: {mod_id}")
            if meta.get("api_version") != API_VERSION:
                raise ValueError(f"unsupported api_version (expected {API_VERSION})")
            enabled = meta.get("enabled", True)
            if not isinstance(enabled, bool):
                raise ValueError('"enabled" must be true or false (without quotes)')
            _unknown_keys(meta, MOD_KEYS, f"{folder.name}/mod.json", result.warnings)
            if not enabled:
                continue
            name = _clean_name(meta.get("name"), "name", MOD_NAME_MAX)
            slime_path = folder / "slimes.json"
            raw_slimes = _read_json(slime_path) if slime_path.is_file() else []
            if not isinstance(raw_slimes, list):
                raise ValueError("slimes.json must contain a list")
            if len(raw_slimes) > MAX_SLIMES_PER_MOD:
                raise ValueError(f"too many slimes ({len(raw_slimes)}; the limit is {MAX_SLIMES_PER_MOD} per MOD)")
            parsed = []
            local_ids = set()
            local_warnings = []
            for row in raw_slimes:
                if not isinstance(row, dict):
                    raise ValueError("each slime must be an object")
                sid = row.get("id")
                if not isinstance(sid, str) or not ID_RE.fullmatch(sid):
                    raise ValueError("slime id must use lowercase letters, numbers and underscores")
                if sid in local_ids or sid in seen_slime_ids:
                    raise ValueError(f"duplicate slime id: {sid}")
                sname = _clean_name(row.get("name"), f"{sid}: name", SLIME_NAME_MAX)
                weight = row.get("weight", 1)
                multiplier = row.get("stat_multiplier", 1.0)
                if not isinstance(weight, int) or isinstance(weight, bool) or not 1 <= weight <= 100:
                    raise ValueError(f"{sid}: weight must be an integer from 1 to 100")
                if not isinstance(multiplier, (int, float)) or isinstance(multiplier, bool) or not 0.25 <= multiplier <= 4:
                    raise ValueError(f"{sid}: stat_multiplier must be between 0.25 and 4")
                color_min = _valid_rgb_range(row.get("color_min", [60, 60, 60]), f"{sid}.color_min")
                color_max = _valid_rgb_range(row.get("color_max", [200, 200, 200]), f"{sid}.color_max")
                if any(lo > hi for lo, hi in zip(color_min, color_max)):
                    raise ValueError(f"{sid}: color_min cannot exceed color_max")
                _unknown_keys(row, SLIME_KEYS, f"{folder.name}/slimes.json ({sid})", local_warnings)
                parsed.append({
                    "id": sid, "name": sname, "weight": weight,
                    "stat_multiplier": float(multiplier),
                    "color_min": color_min, "color_max": color_max,
                    "mod_id": mod_id, "mod_name": name,
                })
                local_ids.add(sid)
            # Blocks are optional. A MOD can contain only blocks, only slimes, or both.
            raw_blocks = _read_json(folder / "blocks.json") if (folder / "blocks.json").is_file() else []
            if not isinstance(raw_blocks, list):
                raise ValueError("blocks.json must contain a list")
            if len(raw_blocks) > MAX_BLOCKS_PER_MOD:
                raise ValueError(f"too many blocks ({len(raw_blocks)}; the limit is {MAX_BLOCKS_PER_MOD} per MOD)")
            parsed_blocks = []
            local_block_ids = set()
            for row in raw_blocks:
                if not isinstance(row, dict):
                    raise ValueError("each block must be an object")
                bid = row.get("id")
                if not isinstance(bid, str) or not ID_RE.fullmatch(bid):
                    raise ValueError("block id must use lowercase letters, numbers and underscores")
                if bid in local_block_ids or bid in seen_block_ids:
                    raise ValueError(f"duplicate block id: {bid}")
                bname = _clean_name(row.get("name"), f"{bid}: name", 48)
                hardness = row.get("hardness", 1.0)
                stack = row.get("stack_limit", 64)
                sound = row.get("sound", "rock")
                placeable = row.get("placeable", True)
                if not isinstance(hardness, (int, float)) or isinstance(hardness, bool) or not math.isfinite(hardness) or not 0.05 <= hardness <= 60:
                    raise ValueError(f"{bid}: hardness must be between 0.05 and 60")
                if not isinstance(stack, int) or isinstance(stack, bool) or not 1 <= stack <= 64:
                    raise ValueError(f"{bid}: stack_limit must be an integer from 1 to 64")
                if sound not in BLOCK_SOUNDS:
                    raise ValueError(f"{bid}: sound must be one of {sorted(BLOCK_SOUNDS)}")
                if not isinstance(placeable, bool):
                    raise ValueError(f"{bid}: placeable must be true or false")
                color = row.get("color", [128, 128, 128])
                top, side, bottom = row.get("top", color), row.get("side", color), row.get("bottom", color)
                colors = []
                for label, rgb in (("top", top), ("side", side), ("bottom", bottom)):
                    if (not isinstance(rgb, list) or len(rgb) != 3 or
                            any(not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v) or not 0 <= v <= 255 for v in rgb)):
                        raise ValueError(f"{bid}: {label} color must be three numbers from 0 to 255")
                    colors.append(tuple(float(v) / 255.0 for v in rgb))
                _unknown_keys(row, BLOCK_KEYS, f"{folder.name}/blocks.json ({bid})", local_warnings)
                parsed_blocks.append({"id": bid, "name": bname, "hardness": float(hardness),
                                      "stack_limit": stack, "sound": sound, "top": colors[0],
                                      "side": colors[1], "bottom": colors[2], "placeable": placeable,
                                      "mod_id": mod_id, "mod_name": name})
                local_block_ids.add(bid)
            if len(result.blocks) + len(parsed_blocks) > MAX_TOTAL_BLOCKS:
                raise ValueError(f"too many custom blocks (maximum {MAX_TOTAL_BLOCKS})")
            seen_mod_ids.add(mod_id)
            seen_slime_ids.update(local_ids)
            seen_block_ids.update(local_block_ids)
            result.slimes.extend(parsed)
            result.blocks.extend(parsed_blocks)
            result.warnings.extend(local_warnings)
            result.loaded.append({"id": mod_id, "name": name, "slime_count": len(parsed), "block_count": len(parsed_blocks)})
        except (OSError, json.JSONDecodeError, ValueError, TypeError) as exc:
            result.errors.append(f"{folder.name}: {exc}")
    return result
