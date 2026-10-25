"""Background music, composed and synthesised in code (numpy only; no sound files needed).

  field  : slow (72 BPM), C MAJOR pentatonic (C D E G A): a gentle bell-like melody over soft pads, a slow bass and a
           quiet harp arpeggio.
  battle : fast (156 BPM), A MINOR pentatonic (A C D E G): a driving riff, pulsing bass, 16th-note arpeggio and drums.

compose_*() returns plain note lists (so the rules are testable); render() turns them into a loop that joins seamlessly
(the ends of notes and of the reverb wrap around to the start)."""
import random
import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np

import config as C

RATE = 22050
MUSIC_VERSION = 1                      # bump when the composition or the sound changes: stale files are re-made
MUSIC_DIR = Path(__file__).resolve().parent.parent / "assets" / "music"

MAJOR_PENTATONIC = (0, 2, 4, 7, 9)
MINOR_PENTATONIC = (0, 3, 5, 7, 10)


@dataclass(frozen=True)
class Note:
    start: float            # in beats from the start of the loop
    length: float           # in beats
    midi: int               # MIDI note number; for drums an id (kick / snare / hat)
    voice: str              # lead | pad | bass | arp | kick | snare | hat
    velocity: float = 0.8


@dataclass(frozen=True)
class Piece:
    name: str
    tempo: float            # beats per minute
    beats: int              # length of the loop in beats
    root: int               # MIDI root of the key
    scale: tuple            # semitone offsets of the pentatonic scale
    notes: tuple

    @property
    def seconds(self):
        return self.beats * 60.0 / self.tempo


def midi_hz(m):
    return 440.0 * 2.0 ** ((m - 69) / 12.0)


def scale_notes(root, intervals, low, high):
    """All MIDI notes between low and high that belong to the scale built on `root`."""
    return [m for m in range(low, high + 1) if (m - root) % 12 in intervals]


# --------------------------------------------------------------------------------------------------- composing
# Rhythms of one 4-beat bar as lists of (length in beats, rest?); each sums to 4.
_FIELD_RHYTHMS = [((2, 0), (1, 0), (1, 0)), ((1, 0), (1, 0), (2, 0)), ((1.5, 0), (0.5, 0), (1, 0), (1, 0)),
                  ((3, 0), (1, 1)), ((1, 0), (1, 0), (1, 0), (1, 0)), ((2, 0), (2, 0)), ((1, 1), (1, 0), (2, 0)),
                  ((0.5, 0), (0.5, 0), (1, 0), (2, 0))]
_BATTLE_RHYTHMS = [((0.5, 0),) * 8, ((0.5, 0), (0.5, 0), (1, 0), (0.5, 0), (0.5, 0), (1, 0)),
                   ((1, 0), (0.5, 0), (0.5, 0), (1, 0), (1, 0)), ((0.5, 0), (0.5, 0), (0.5, 0), (0.5, 0), (1, 0), (1, 0)),
                   ((0.75, 0), (0.75, 0), (0.5, 0), (1, 0), (1, 0)), ((0.5, 0),) * 4 + ((1, 0), (1, 0))]


def _melody(rng, bars, scale, rhythms, lead_range, tonic_pcs, start_beat=0.0, motif=None):
    """A random walk along the scale (mostly steps, sometimes a leap); each 4-bar phrase ends on the tonic or the fifth."""
    notes = []
    idx = rng.randrange(len(scale) // 2, len(scale) // 2 + 2)
    for bar in range(bars):
        t = start_beat + bar * 4.0
        phrase_end = bar % 4 == 3
        rhythm = rng.choice(rhythms)
        last = max(i for i, (_, rest) in enumerate(rhythm) if not rest)       # the last note that actually sounds
        for i, (length, rest) in enumerate(rhythm):
            if not rest:
                step = rng.choices([-2, -1, 0, 1, 2], weights=[1, 4, 1, 4, 1])[0]
                idx = max(0, min(len(scale) - 1, idx + step))
                if phrase_end and i == last:
                    goals = [j for j, m in enumerate(scale) if m % 12 in tonic_pcs]
                    idx = min(goals, key=lambda j: abs(j - idx))
                notes.append((t, length, scale[idx]))
            t += length
    return notes


def compose_field(seed=C.MUSIC_SEED):
    """Slow C-major-pentatonic piece, 24 bars (80 s at 72 BPM)."""
    rng = random.Random(seed)
    root, bars = 60, 24
    lead_scale = scale_notes(root, MAJOR_PENTATONIC, 72, 93)
    notes = []
    # chords, two bars each; every note of every chord belongs to the scale
    chords = [(0, 4, 7), (9, 12, 16), (7, 12, 14), (0, 4, 7), (4, 7, 12), (9, 12, 16), (7, 12, 14), (0, 7, 16)]
    for bar in range(0, bars, 2):
        ch = chords[(bar // 2) % len(chords)]
        t = bar * 4.0
        for off in ch:
            notes.append(Note(t, 8.0, root + off, "pad", 0.22))
        notes.append(Note(t, 4.0, root - 12 + ch[0], "bass", 0.55))
        notes.append(Note(t + 4.0, 4.0, root - 12 + ch[0] + (7 if bar % 4 == 2 else 0), "bass", 0.45))
        for k in range(16):                                      # a quiet harp arpeggio, one note every half beat
            notes.append(Note(t + k * 0.5, 1.0, root + 12 + ch[k % 3] % 12 + (12 if k % 6 == 5 else 0), "arp", 0.16))
    mel = _melody(rng, bars, lead_scale, _FIELD_RHYTHMS, (72, 93), (root % 12, (root + 7) % 12))
    for t, length, m in mel:
        notes.append(Note(t, length, m, "lead", 0.7))
    return Piece("field", 72.0, bars * 4, root, MAJOR_PENTATONIC, tuple(sorted(notes, key=lambda n: n.start)))


def compose_battle(seed=C.MUSIC_SEED):
    """Fast A-minor-pentatonic piece, 32 bars (about 49 s at 156 BPM)."""
    rng = random.Random(seed + 1)
    root, bars = 57, 32
    lead_scale = scale_notes(root, MINOR_PENTATONIC, 69, 91)
    notes = []
    chords = [(0, 3, 7), (3, 7, 10), (7, 10, 17), (0, 7, 10)]            # A-C-E, C-E-G, E-G-D, A-E-G: all pentatonic tones
    for bar in range(bars):
        ch = chords[(bar // 2) % len(chords)]
        t = bar * 4.0
        for k in range(8):                                               # driving eighth-note bass
            notes.append(Note(t + k * 0.5, 0.45, root - 12 + (ch[0] if k % 4 != 3 else ch[2] % 12), "bass", 0.62))
        for k in range(16):                                              # 16th-note arpeggio
            notes.append(Note(t + k * 0.25, 0.4, root + 12 + ch[k % 3] % 12 + (12 if k % 8 >= 6 else 0), "arp", 0.2))
        for b in range(4):                                               # drums: kick every beat, snare on 2 and 4, hats on the offbeats
            notes.append(Note(t + b, 0.3, 36, "kick", 0.8))
            if b % 2 == 1:
                notes.append(Note(t + b, 0.3, 38, "snare", 0.55))
            notes.append(Note(t + b + 0.5, 0.15, 42, "hat", 0.28))
    # the riff: one 4-bar phrase repeated with small changes, so it sounds like a theme rather than noise
    riff = _melody(rng, 4, lead_scale, _BATTLE_RHYTHMS, (69, 91), (root % 12, (root + 7) % 12))
    for rep in range(bars // 4):
        shift = 0 if rep % 4 != 2 else 1
        for t, length, m in riff:
            j = lead_scale.index(m)
            m2 = lead_scale[min(len(lead_scale) - 1, j + shift)] if t % 4 >= 2 and rep % 2 else m
            notes.append(Note(t + rep * 16.0, length, m2, "lead", 0.72))
    return Piece("battle", 156.0, bars * 4, root, MINOR_PENTATONIC, tuple(sorted(notes, key=lambda n: n.start)))


# --------------------------------------------------------------------------------------------------- synthesis
def _env_pluck(n, attack, decay):
    t = np.arange(n) / RATE
    return np.minimum(1.0, t / max(attack, 1e-4)) * np.exp(-t / decay)


def _tone(freq, n, harmonics):
    t = np.arange(n) / RATE
    out = np.zeros(n)
    for k, amp in harmonics:
        if freq * k < RATE / 2.2:
            out += amp * np.sin(2 * np.pi * freq * k * t)
    return out


def _voice(note, piece, rng):
    spb = 60.0 / piece.tempo
    dur = note.length * spb
    v = note.voice
    if v == "kick":
        n = int(RATE * 0.22)
        t = np.arange(n) / RATE
        return np.sin(2 * np.pi * (45 * t + 75 * (1 - np.exp(-t * 28)) / 28)) * np.exp(-t / 0.07) * 1.1
    if v == "snare":
        n = int(RATE * 0.18)
        t = np.arange(n) / RATE
        return (rng.uniform(-1, 1, n) * 0.8 + np.sin(2 * np.pi * 190 * t) * 0.5) * np.exp(-t / 0.045)
    if v == "hat":
        n = int(RATE * 0.06)
        t = np.arange(n) / RATE
        noise = rng.uniform(-1, 1, n)
        return (noise - np.concatenate([[0], noise[:-1]])) * np.exp(-t / 0.014) * 0.6      # differentiated noise = bright
    freq = midi_hz(note.midi)
    if v == "pad":
        n = int((dur + 0.9) * RATE)
        t = np.arange(n) / RATE
        env = np.minimum(1.0, t / 0.5) * np.minimum(1.0, np.maximum(0.0, (dur + 0.9 - t) / 0.9))
        return (np.sin(2 * np.pi * freq * t) + 0.6 * np.sin(2 * np.pi * freq * 1.004 * t) + 0.25 * np.sin(2 * np.pi * freq * 2 * t)) * env * 0.5
    if v == "bass":
        n = int((dur + 0.3) * RATE)
        return _tone(freq, n, ((1, 1.0), (2, 0.35), (3, 0.1))) * _env_pluck(n, 0.01, dur * (0.9 if piece.name == "field" else 0.5))
    if v == "arp":
        n = int((dur + 0.8) * RATE)
        return _tone(freq, n, ((1, 1.0), (2, 0.4), (3, 0.15))) * _env_pluck(n, 0.004, 0.35 if piece.name == "field" else 0.12)
    # lead
    n = int((dur + (1.4 if piece.name == "field" else 0.3)) * RATE)
    if piece.name == "field":                                     # bell / marimba-like: a few inharmonic-ish partials, long decay
        wave_ = _tone(freq, n, ((1, 1.0), (2, 0.5), (3, 0.25), (4.01, 0.08)))
        return wave_ * _env_pluck(n, 0.006, 0.9)
    wave_ = _tone(freq, n, tuple((k, 1.0 / k) for k in range(1, 9)))      # bright, saw-like for the battle riff
    return wave_ * _env_pluck(n, 0.004, max(0.12, dur * 0.8))


_GAIN = {"lead": 0.5, "pad": 0.3, "bass": 0.55, "arp": 0.35, "kick": 0.7, "snare": 0.45, "hat": 0.3}


def _add_wrapped(buf, start, wave_):
    """Mix a note into the loop buffer; whatever runs past the end wraps around to the start (a seamless loop)."""
    n = len(buf)
    start %= n
    first = min(len(wave_), n - start)
    buf[start:start + first] += wave_[:first]
    rest = len(wave_) - first
    while rest > 0:
        chunk = min(rest, n)
        buf[:chunk] += wave_[len(wave_) - rest:len(wave_) - rest + chunk]
        rest -= chunk


def render(piece, seed=C.MUSIC_SEED):
    """Piece -> int16 mono samples; its length is exactly the loop length."""
    rng = np.random.default_rng(seed)
    n = int(round(piece.seconds * RATE))
    buf = np.zeros(n)
    spb = 60.0 / piece.tempo
    for note in piece.notes:
        w = _voice(note, piece, rng) * note.velocity * _GAIN[note.voice]
        _add_wrapped(buf, int(round(note.start * spb * RATE)), w)
    # a little circular reverb: delayed copies that wrap around, so the loop point stays seamless
    wet = np.zeros(n)
    for delay, gain in ((0.173, 0.30), (0.289, 0.22), (0.411, 0.15)):
        wet += np.roll(buf, int(delay * RATE)) * gain
    buf = buf + wet * (1.0 if piece.name == "field" else 0.5)
    peak = np.abs(buf).max()
    return (buf / max(peak, 1e-9) * 0.82 * 32767).astype(np.int16)


def new_seed():
    """A fresh composition seed: every launch, and every battle after the first, gets a different tune."""
    return random.SystemRandom().randrange(1, 2 ** 31 - 2)


def compose(name, seed):
    return compose_field(seed) if name == "field" else compose_battle(seed)


def write_track(name, seed, directory=MUSIC_DIR):
    """Compose, render and write one loop. Returns its file stem (the file is <stem>.wav in `directory`)."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    stem = f"bgm_{name}_v{MUSIC_VERSION}_{seed}"
    data = render(compose(name, seed), seed)
    tmp = directory / f"{stem}.tmp"
    with wave.open(str(tmp), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(RATE)
        f.writeframes(data.tobytes())
    tmp.replace(directory / f"{stem}.wav")              # appears whole or not at all
    return stem


def cleanup(directory, keep):
    """Delete every bgm file in `directory` whose stem is not in `keep` (older tunes, half-written files)."""
    for f in Path(directory).glob("bgm_*"):
        if f.stem not in keep:
            try:
                f.unlink()
            except OSError:
                pass
