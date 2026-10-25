"""Procedural sound effects: written once to assets/sfx/*.wav with numpy, so no sound files need to be sourced.
Each block family (soft / rock / wood / leaf) gets its own hit and break sound."""
import wave
from pathlib import Path

import numpy as np

RATE = 22050
SFX_DIR = Path(__file__).resolve().parent.parent / "assets" / "sfx"
FAMILIES = ("soft", "rock", "wood", "leaf")
# family -> (noise smoothing 0..1 (higher = brighter), tone Hz, tone mix, length s, decay s, gain)
_RECIPES = {
    "soft": (0.10, 110.0, 0.8, 0.12, 0.035, 0.9),
    "rock": (0.65, 1400.0, 0.35, 0.09, 0.020, 0.8),
    "wood": (0.25, 320.0, 0.9, 0.11, 0.030, 0.9),
    "leaf": (0.95, 0.0, 0.0, 0.14, 0.050, 0.5),
}


def _smooth_noise(rng, n, bright):
    """One-pole low-pass of white noise; bright near 1 keeps the highs (rock/leaf), near 0 is dull (soil)."""
    white = rng.uniform(-1, 1, n)
    out = np.empty(n)
    acc = 0.0
    for i in range(n):
        acc += (white[i] - acc) * bright
        out[i] = acc
    return out / max(1e-9, np.abs(out).max())


def _hit(family, scale=1.0, seed=1):
    bright, hz, tone_mix, length, decay, gain = _RECIPES[family]
    rng = np.random.default_rng(seed)
    n = int(RATE * length * scale)
    t = np.arange(n) / RATE
    env = np.exp(-t / (decay * scale))
    wave_ = _smooth_noise(rng, n, bright) * (1 - tone_mix * 0.5)
    if hz:
        wave_ += np.sin(2 * np.pi * hz * t) * tone_mix * 0.6
    return wave_ * env * gain * (1.0 if scale == 1.0 else 1.15)


def _beeps():
    out = []
    for hz in (440.0, 330.0):
        n = int(RATE * 0.12)
        t = np.arange(n) / RATE
        out.append(np.sign(np.sin(2 * np.pi * hz * t)) * 0.25 * np.exp(-t / 0.15))
    return np.concatenate(out)


def _whoosh(seed=9):
    """Short rising noise sweep: the 'attack' sound that starts a battle action."""
    rng = np.random.default_rng(seed)
    n = int(RATE * 0.16)
    t = np.arange(n) / RATE
    out = _smooth_noise(rng, n, 0.55) * np.sin(np.pi * t / 0.16) ** 1.5
    return out * 0.55


def _jingle(freqs, note=0.11):
    out = []
    for hz in freqs:
        n = int(RATE * note)
        t = np.arange(n) / RATE
        out.append(np.sin(2 * np.pi * hz * t) * 0.35 * np.exp(-t / 0.12))
    return np.concatenate(out)


def render_all():
    """name -> int16 numpy array."""
    sounds = {}
    for fam in FAMILIES:
        sounds[f"hit_{fam}"] = _hit(fam)
        sounds[f"break_{fam}"] = _hit(fam, scale=2.2, seed=2)
    sounds["place"] = _hit("soft", scale=0.7, seed=3) * 0.9
    sounds["full"] = _beeps()
    sounds["whoosh"] = _whoosh()
    sounds["impact"] = _hit("soft", scale=1.4, seed=7) * 1.25
    sounds["heal"] = _jingle((440.0, 587.0), note=0.10)
    sounds["win"] = _jingle((392.0, 494.0, 587.0), note=0.12)
    sounds["levelup"] = _jingle((523.0, 659.0, 784.0, 1047.0))
    sounds["lose"] = _jingle((392.0, 330.0, 262.0, 196.0), note=0.16)
    sounds["eat"] = _hit("leaf", scale=1.6, seed=5) * 1.2
    return {k: (np.clip(v, -1, 1) * 32000).astype(np.int16) for k, v in sounds.items()}


def write_all(directory=SFX_DIR):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    for name, data in render_all().items():
        with wave.open(str(directory / f"{name}.wav"), "wb") as f:
            f.setnchannels(1)
            f.setsampwidth(2)
            f.setframerate(RATE)
            f.writeframes(data.tobytes())
    return directory
