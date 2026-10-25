"""The music director with a fake sound system: switching, silence recovery and fresh tunes."""
import tempfile
import unittest
from pathlib import Path

import numpy as np

import config as C
from audio import director as D, music as M


class FakePlayer:
    log = []

    def __init__(self, stem):
        self.stem, self.playing, self.destroyed, self.starts = stem, False, False, 0
        FakePlayer.log.append(("make", stem))

    def start(self):
        self.playing = True
        self.starts += 1
        FakePlayer.log.append(("start", self.stem))

    def stop(self):
        self.playing = False
        FakePlayer.log.append(("stop", self.stem))

    def is_playing(self):
        return self.playing

    def destroy(self):
        self.destroyed = True
        FakePlayer.log.append(("destroy", self.stem))


def make_director(tmp, threaded=False):
    FakePlayer.log = []
    seeds = iter(range(100, 10 ** 6))
    msgs = []
    d = D.MusicDirector(tmp, FakePlayer, seed_fn=lambda: next(seeds), threaded=threaded, log=msgs.append)
    d.messages = msgs
    return d


def files(tmp):
    return {p.stem for p in Path(tmp).glob("bgm_*")}


class TestMusicDirector(unittest.TestCase):
    def setUp(self):                                                   # switching logic needs files, not real music: keep it quick
        self._render = M.render
        M.render = lambda piece, seed=0: np.zeros(2000, dtype=np.int16)

    def tearDown(self):
        M.render = self._render

    def test_both_tracks_exist_after_start_and_only_one_plays(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = make_director(tmp)
            d.start()
            self.assertEqual(set(d.current), {"field", "battle"})
            self.assertEqual(files(tmp), {d.current["field"][0], d.current["battle"][0]})
            d.set_track("field")
            self.assertTrue(d.current["field"][1].playing)
            self.assertFalse(d.current["battle"][1].playing)
            d.set_track("battle")
            self.assertTrue(d.current["battle"][1].playing)
            self.assertFalse(d.current["field"][1].playing)
            d.set_track("field")
            self.assertTrue(d.current["field"][1].playing and not d.current["battle"][1].playing)

    def test_a_silent_track_is_restarted_within_a_couple_of_seconds(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = make_director(tmp)
            d.start()
            d.set_track("field")
            player = d.current["field"][1]
            for _ in range(200):                                       # healthy: never restarted
                d.update(0.05)
            self.assertEqual(d.restarts, 0)
            player.playing = False                                     # the sound system lets it fall silent
            for _ in range(int(D.CHECK_EVERY / 0.05) + 2):
                d.update(0.05)
            self.assertTrue(player.playing)
            self.assertEqual(d.restarts, 1)
            self.assertTrue(any("had stopped" in m for m in d.messages))
            d.current["battle"][1].playing = False                     # a track that should NOT play is left alone
            for _ in range(100):
                d.update(0.05)
            self.assertFalse(d.current["battle"][1].playing)

    def test_nothing_is_restarted_before_a_track_is_chosen(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = make_director(tmp)
            d.start()
            for _ in range(100):
                d.update(0.05)
            self.assertEqual(d.restarts, 0)
            self.assertFalse(any(p[0] == "start" for p in FakePlayer.log))

    def test_every_battle_and_every_return_to_the_field_brings_a_new_tune(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = make_director(tmp)
            d.start()
            d.set_track("field")
            battles, fields = [d.current["battle"][0]], [d.current["field"][0]]
            for _ in range(3):
                d.set_track("battle"); d.wait()
                battles.append(d.current["battle"][0])
                d.set_track("field"); d.wait()
                fields.append(d.current["field"][0])
            self.assertEqual(battles[0], battles[1], "the first fight uses the tune made at start-up")
            heard = battles[1:]                                        # the tunes actually played in fights
            self.assertEqual(len(set(heard)), len(heard), heard)
            self.assertEqual(len(set(fields)), len(fields), fields)
            d.set_track("battle"); d.wait()
            self.assertLessEqual(len(files(tmp)), 4, "old tunes must be deleted: " + str(files(tmp)))
            self.assertTrue(files(tmp) >= {d.current["field"][0], d.current["battle"][0]})
            self.assertTrue(any(p[0] == "destroy" for p in FakePlayer.log))

    def test_the_first_tune_of_a_launch_is_different_each_time(self):
        with tempfile.TemporaryDirectory() as tmp1, tempfile.TemporaryDirectory() as tmp2:
            stems = []
            for tmp in (tmp1, tmp2):
                FakePlayer.log = []
                d = D.MusicDirector(tmp, FakePlayer, threaded=False)   # the real, random seeds
                d.start()
                stems.append((d.current["field"][0], d.current["battle"][0]))
            self.assertNotEqual(stems[0][0], stems[1][0])
            self.assertNotEqual(stems[0][1], stems[1][1])

    def test_a_failed_tune_changes_nothing_and_the_game_keeps_its_music(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = make_director(tmp)
            d.start()
            d.set_track("field")
            original = M.write_track
            M.write_track = lambda *a, **k: (_ for _ in ()).throw(OSError("disk full"))
            try:
                d.set_track("battle"); d.wait()
                self.assertTrue(d.current["battle"][1].playing)
                self.assertTrue(any("could not make" in m for m in d.messages))
                d.set_track("field"); d.wait()
                self.assertTrue(d.current["field"][1].playing)
            finally:
                M.write_track = original

    def test_background_thread_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = make_director(tmp, threaded=True)
            d.start()
            d.set_track("field")
            first = d.current["battle"][0]
            d.set_track("battle")
            self.assertEqual(d.current["battle"][0], first, "the first fight uses the tune made at start-up")
            d.set_track("field")
            d.wait()
            d.set_track("battle")
            self.assertNotEqual(d.current["battle"][0], first, "the next fight has a new tune")
            d.wait()


class TestEveryTuneIsMusical(unittest.TestCase):
    def test_random_seeds_all_stay_in_key_and_phrase_correctly(self):
        for seed in (1, 2, 3, 7, 42, 1234, 99999, 2 ** 30):
            field, battle = M.compose_field(seed), M.compose_battle(seed)
            for piece, scale in ((field, M.MAJOR_PENTATONIC), (battle, M.MINOR_PENTATONIC)):
                allowed = {(piece.root + i) % 12 for i in scale}
                pcs = {n.midi % 12 for n in piece.notes if n.voice in ("lead", "pad", "bass", "arp")}
                self.assertTrue(pcs <= allowed, (seed, piece.name, pcs - allowed))
                lead = [n for n in piece.notes if n.voice == "lead"]
                self.assertGreater(len(lead), 40)
            tonic = {field.root % 12, (field.root + 7) % 12}
            for phrase in range(field.beats // 16):
                inside = [n for n in field.notes if n.voice == "lead" and phrase * 16 <= n.start < (phrase + 1) * 16]
                self.assertIn(inside[-1].midi % 12, tonic, (seed, phrase))

    def test_different_seeds_really_are_different_tunes(self):
        melodies = {tuple((n.start, n.midi) for n in M.compose_field(s).notes if n.voice == "lead") for s in range(1, 9)}
        self.assertEqual(len(melodies), 8)
        riffs = {tuple((n.start, n.midi) for n in M.compose_battle(s).notes if n.voice == "lead") for s in range(1, 9)}
        self.assertEqual(len(riffs), 8)

    def test_written_tune_is_a_whole_valid_wav(self):
        import wave
        with tempfile.TemporaryDirectory() as tmp:
            stem = M.write_track("battle", 77, tmp)
            with wave.open(str(Path(tmp) / f"{stem}.wav")) as f:
                self.assertEqual((f.getnchannels(), f.getframerate()), (1, M.RATE))
                self.assertEqual(f.getnframes(), int(round(M.compose_battle(77).seconds * M.RATE)))
            self.assertEqual(list(Path(tmp).glob("*.tmp")), [])
            M.cleanup(tmp, keep=set())
            self.assertEqual(list(Path(tmp).glob("bgm_*")), [])


if __name__ == "__main__":
    unittest.main()
