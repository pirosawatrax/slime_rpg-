"""MOD loader: names, types, limits, warnings, the copy-me template, and how MOD slimes appear in battle."""
import json
import random
import shutil
import tempfile
import unittest
from pathlib import Path

import config as C
from game.battle import Battle, make_enemy
from game.inventory import Inventory
from game.stats import PlayerStats
from mods import loader
from mods.loader import load_mods

ROOT = Path(__file__).resolve().parents[1]


def write_mod(root, folder, meta=None, slimes=None, raw_slimes=None):
    d = Path(root) / folder
    d.mkdir(parents=True, exist_ok=True)
    m = {"id": folder.strip("_.").replace("-", "_") or "x", "name": "Test", "api_version": 1}
    m.update(meta or {})
    (d / "mod.json").write_text(json.dumps(m), encoding="utf-8")
    if raw_slimes is not None:
        (d / "slimes.json").write_text(raw_slimes, encoding="utf-8")
    else:
        (d / "slimes.json").write_text(json.dumps(slimes if slimes is not None else [{"id": "s1", "name": "Okay"}]), encoding="utf-8")
    return d


class TestNames(unittest.TestCase):
    def check(self, name):
        with tempfile.TemporaryDirectory() as t:
            write_mod(t, "m", slimes=[{"id": "s", "name": name}])
            return load_mods(t)

    def test_names_must_be_one_short_printable_line(self):
        for bad in ("Line\nBreak", "Tab\tHere", "Bell\x07", "W" * (loader.SLIME_NAME_MAX + 1), "", "   ", 5, None, ["a"]):
            r = self.check(bad)
            self.assertEqual(r.slimes, [], repr(bad))
            self.assertEqual(len(r.errors), 1, repr(bad))
        ok = self.check("W" * loader.SLIME_NAME_MAX)
        self.assertEqual(len(ok.slimes), 1)
        self.assertEqual(self.check("  Padded  ").slimes[0]["name"], "Padded")
        self.assertEqual(len(self.check("Braces {x} %s").slimes), 1, "format characters are harmless")

    def test_mod_name_has_its_own_limit(self):
        with tempfile.TemporaryDirectory() as t:
            write_mod(t, "m", meta={"name": "N" * (loader.MOD_NAME_MAX + 1)})
            self.assertEqual(len(load_mods(t).errors), 1)


class TestTypesAndLimits(unittest.TestCase):
    def test_enabled_must_be_a_real_boolean_and_the_error_says_so(self):
        for bad in ("true", "false", "yes", 1, 0, None):
            with tempfile.TemporaryDirectory() as t:
                write_mod(t, "m", meta={"enabled": bad})
                r = load_mods(t)
                self.assertEqual(r.loaded, [], repr(bad))
                self.assertEqual(len(r.errors), 1, repr(bad))
                self.assertIn("enabled", r.errors[0])
        with tempfile.TemporaryDirectory() as t:
            write_mod(t, "off", meta={"enabled": False})
            r = load_mods(t)
            self.assertEqual((r.loaded, r.errors), ([], []))

    def test_unknown_keys_warn_but_do_not_break_the_mod(self):
        with tempfile.TemporaryDirectory() as t:
            write_mod(t, "m", meta={"autor": "me"}, slimes=[{"id": "s", "name": "Okay", "wieght": 5}])
            r = load_mods(t)
            self.assertEqual(len(r.slimes), 1)
            self.assertEqual(r.slimes[0]["weight"], 1, "the misspelt key is ignored")
            self.assertEqual(r.errors, [])
            text = " ".join(r.warnings)
            self.assertIn("autor", text)
            self.assertIn("wieght", text)
            self.assertEqual(len(r.warnings), 2)

    def test_a_clean_mod_has_no_warnings(self):
        with tempfile.TemporaryDirectory() as t:
            write_mod(t, "m", meta={"author": "me", "description": "d", "version": "1"},
                      slimes=[{"id": "s", "name": "Okay", "weight": 2, "stat_multiplier": 1.2,
                               "color_min": [60, 60, 60], "color_max": [90, 90, 90]}])
            r = load_mods(t)
            self.assertEqual((r.errors, r.warnings), ([], []))

    def test_file_size_and_count_limits(self):
        with tempfile.TemporaryDirectory() as t:
            big = "[" + ",".join('{"id":"s%d","name":"n"}' % i for i in range(20000)) + "]"
            write_mod(t, "big", raw_slimes=big)
            r = load_mods(t)
            self.assertEqual(r.loaded, [])
            self.assertIn("too large", r.errors[0])
        with tempfile.TemporaryDirectory() as t:
            many = [{"id": f"s{i}", "name": "n"} for i in range(loader.MAX_SLIMES_PER_MOD + 1)]
            write_mod(t, "many", slimes=many)
            self.assertIn("too many slimes", load_mods(t).errors[0])
            write_mod(t, "exact", meta={"id": "exact"}, slimes=[{"id": f"e{i}", "name": "n"} for i in range(loader.MAX_SLIMES_PER_MOD)])
            r = load_mods(t)
            self.assertEqual([m["id"] for m in r.loaded], ["exact"])
        with tempfile.TemporaryDirectory() as t:
            for i in range(loader.MAX_MODS + 1):
                write_mod(t, f"mod{i:03d}", meta={"id": f"mod{i:03d}"}, slimes=[{"id": f"slime{i:03d}", "name": "n"}])
            r = load_mods(t)
            self.assertEqual(len(r.loaded), loader.MAX_MODS)
            self.assertEqual(len(r.errors), 1)

    def test_underscore_and_dot_folders_are_ignored_even_if_broken(self):
        with tempfile.TemporaryDirectory() as t:
            for name in ("_draft", ".hidden"):
                (Path(t) / name).mkdir()
                (Path(t) / name / "mod.json").write_text("not json")
            write_mod(t, "real")
            r = load_mods(t)
            self.assertEqual(([m["id"] for m in r.loaded], r.errors), (["real"], []))

    def test_duplicates_and_version_mismatches_skip_only_the_offender(self):
        with tempfile.TemporaryDirectory() as t:
            write_mod(t, "a_first", meta={"id": "first"}, slimes=[{"id": "same", "name": "A"}])
            write_mod(t, "b_second", meta={"id": "second"}, slimes=[{"id": "same", "name": "B"}])       # slime id clash
            write_mod(t, "c_third", meta={"id": "first"})                                                 # mod id clash
            write_mod(t, "d_old", meta={"id": "old", "api_version": 99})
            write_mod(t, "e_good", meta={"id": "good"}, slimes=[{"id": "fine", "name": "F"}])
            r = load_mods(t)
            self.assertEqual([m["id"] for m in r.loaded], ["first", "good"])
            self.assertEqual(len(r.errors), 3)
            self.assertEqual({s["id"] for s in r.slimes}, {"same", "fine"})
            self.assertEqual([s["name"] for s in r.slimes if s["id"] == "same"], ["A"])


class TestTemplateAndSample(unittest.TestCase):
    def test_the_template_is_skipped_in_place_but_works_when_copied(self):
        self.assertTrue((ROOT / "mods" / "_template" / "mod.json").is_file())
        self.assertNotIn("my_first_mod", [m["id"] for m in load_mods(ROOT / "mods").loaded])
        with tempfile.TemporaryDirectory() as t:
            shutil.copytree(ROOT / "mods" / "_template", Path(t) / "my_first_mod")
            r = load_mods(t)
            self.assertEqual((r.errors, r.warnings), ([], []), "the template must always be a valid MOD")
            self.assertEqual([m["id"] for m in r.loaded], ["my_first_mod"])
            self.assertEqual(r.slimes[0]["name"], "My Slime")

    def test_the_sample_mod_loads_cleanly(self):
        r = load_mods(ROOT / "mods")
        self.assertEqual((r.errors, r.warnings), ([], []))
        self.assertIn("Crystal Slime", [s["name"] for s in r.slimes])


class TestModSlimesInBattle(unittest.TestCase):
    SLIMES = [{"id": "gem", "name": "Gem Slime", "weight": 30, "stat_multiplier": 1.5, "mod_id": "m", "mod_name": "M",
               "color_min": (100.0, 100.0, 100.0), "color_max": (110.0, 110.0, 110.0)}]

    def test_how_often_a_mod_slime_appears_follows_its_weight(self):
        r = random.Random(1)
        hits = sum(make_enemy(5, r, mod_slimes=self.SLIMES).name == "Gem Slime" for _ in range(4000)) / 4000
        self.assertAlmostEqual(hits, 30 / (10 + 30), delta=0.04)
        self.assertEqual(sum(make_enemy(5, r).name != "Slime" for _ in range(500)), 0, "no MODs: only plain slimes")

    def test_the_battle_names_the_mod_slime_but_keeps_the_plain_intro_for_plain_ones(self):
        r = random.Random(1)
        gem = make_enemy(5, r)
        while gem.name != "Gem Slime":
            gem = make_enemy(5, r, mod_slimes=self.SLIMES)
        b = Battle(PlayerStats(), gem, Inventory(), r, str)
        self.assertEqual(b.log[0], "* Gem Slime appears!")
        plain = Battle(PlayerStats(), make_enemy(5, r), Inventory(), r, str)
        self.assertEqual(plain.log[0], "* A slime appears!")
        b.take_events()
        b.act("tackle")
        text = " ".join(b.log)
        self.assertIn("Gem Slime takes", text)
        self.assertIn("> Gem Slime tackles!", text)
        self.assertTrue(all(100 <= c <= 110 for c in gem.color))

    def test_the_boss_is_never_a_mod_slime(self):
        from game.battle import make_boss
        self.assertEqual(getattr(make_boss(random.Random(1)), "name", "Slime"), "Slime")
        boss = Battle(PlayerStats(), make_boss(random.Random(1)), Inventory(), random.Random(1), str, boss=True)
        self.assertEqual(boss.log[0], "* A slime appears!")


if __name__ == "__main__":
    unittest.main()
