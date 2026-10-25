"""On-disk save format (JSON). Engine-free.

    <dir>/meta.json                 version, seed, player, inventory, spawn
    <dir>/chunks/c_<cx>_<cz>.json   only the blocks the player changed in that chunk (a diff over generated terrain)

Chunks are stored separately, so saving writes only the chunks that changed and the world can grow without
one giant file. Every write goes to a temp file first and is then renamed into place."""
import json
import os
import time
from pathlib import Path

import config as C
import items
from blocks import AIR, BLOCKS

S = C.CHUNK_SIZE
H = C.WORLD_HEIGHT


class SaveError(Exception):
    """kind: 'corrupt' (unreadable) or 'too_new' (written by a newer game version)."""

    def __init__(self, kind, detail=""):
        super().__init__(f"{kind}: {detail}")
        self.kind = kind
        self.detail = detail


def _atomic_write(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


class SaveStore:
    def __init__(self, directory):
        self.dir = Path(directory)
        self.warnings = []                    # non-fatal problems found while loading (skipped chunk files...)

    # ---- whole save ---------------------------------------------------
    def exists(self):
        return (self.dir / "meta.json").is_file()

    def archive(self, tag="old"):
        """Move the whole save aside (never deletes it). Returns the new path."""
        if not self.dir.exists():
            return None
        target = self.dir.with_name(f"{self.dir.name}.{tag}-{time.strftime('%Y%m%d-%H%M%S')}")
        n = 1
        while target.exists():
            n += 1
            target = self.dir.with_name(f"{self.dir.name}.{tag}-{time.strftime('%Y%m%d-%H%M%S')}-{n}")
        os.replace(self.dir, target)
        return target

    # ---- meta ---------------------------------------------------------
    def save_meta(self, meta):
        _atomic_write(self.dir / "meta.json", json.dumps(meta, indent=1))

    def load_meta(self):
        try:
            with open(self.dir / "meta.json", encoding="utf-8") as f:
                meta = json.load(f)
        except (OSError, ValueError) as exc:
            raise SaveError("corrupt", str(exc))
        if not isinstance(meta, dict) or not isinstance(meta.get("save_version"), int):
            raise SaveError("corrupt", "missing save_version")
        if meta["save_version"] > C.SAVE_VERSION:
            raise SaveError("too_new", f"{meta['save_version']}")
        meta = _migrate(meta)
        if not isinstance(meta.get("seed"), int):
            raise SaveError("corrupt", "missing seed")
        return meta

    # ---- chunk diffs --------------------------------------------------
    def _chunk_path(self, cx, cz):
        return self.dir / "chunks" / f"c_{cx}_{cz}.json"

    def save_chunk_edits(self, cx, cz, edits):
        """edits: {(lx, y, lz): block}. An empty diff removes the file (the chunk is back to generated terrain)."""
        path = self._chunk_path(cx, cz)
        if not edits:
            try:
                path.unlink()
            except FileNotFoundError:
                pass
            return
        rows = [[lx, y, lz, int(b)] for (lx, y, lz), b in sorted(edits.items())]
        _atomic_write(path, json.dumps({"v": 1, "edits": rows}, separators=(",", ":")))

    def load_chunk_edits(self, cx, cz):
        path = self._chunk_path(cx, cz)
        if not path.is_file():
            return {}
        try:
            with open(path, encoding="utf-8") as f:
                rows = json.load(f)["edits"]
            if not isinstance(rows, list):
                raise ValueError("edits is not a list")
        except (OSError, ValueError, KeyError, TypeError) as exc:
            self.warnings.append(f"chunk ({cx}, {cz}) unreadable, skipped: {exc}")
            try:
                os.replace(path, path.with_name(path.name + ".corrupt"))
            except OSError:
                pass
            return {}
        edits = {}
        for row in rows:
            try:
                lx, y, lz, b = row
                if (isinstance(lx, int) and isinstance(y, int) and isinstance(lz, int) and isinstance(b, int)
                        and 0 <= lx < S and 0 <= lz < S and 0 <= y < H and (b == AIR or b in BLOCKS)):
                    edits[(lx, y, lz)] = b
            except (TypeError, ValueError):
                continue
        return edits


def _migrate(meta):
    """Upgrade older save formats to the current one.
    1 -> 2: mineral colours went from 8 to 10 levels per channel, so mineral item ids in the inventory change."""
    if meta.get("save_version") == 1:
        rows = meta.get("inventory")
        if isinstance(rows, list):
            for i, row in enumerate(rows):
                try:
                    if isinstance(row[0], int) and items.is_mineral(row[0]) and row[0] < items.MINERAL_BASE + 512:
                        rows[i] = [items.old_item_to_current(row[0]), row[1]]
                except (TypeError, IndexError):
                    pass
        meta["save_version"] = 2
    return meta
