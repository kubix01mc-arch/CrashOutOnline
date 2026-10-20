#!/usr/bin/env python3
"""Theme-aware SFX for Crash Out (custom assets + procedural fallback)."""

from __future__ import annotations

import math
import subprocess
import struct
import sys
import tempfile
import threading
import wave
from io import BytesIO
from pathlib import Path
from typing import Callable

PROJECT_ROOT = Path(__file__).resolve().parent
ASSETS_DIR = PROJECT_ROOT / "assets"

# User-provided WAV overrides (looked up in assets/, then project root).
CUSTOM_SFX_FILES: dict[str, str] = {
    "damage": "hurt_crashout.wav",
    "heal": "heal_crashout.wav",
    "steal": "steal_crashout.wav",
    "crash_out": "die_crashout.wav",
    "card_pick": "cardpick_crashout.wav",
}

# ---------------------------------------------------------------------------
# Public event names (match suggested placements)
# ---------------------------------------------------------------------------
SFX_DAMAGE = "damage"
SFX_CRASH_OUT = "crash_out"
SFX_HEAL = "heal"
SFX_STEAL = "steal"
SFX_STEAL_FAIL = "steal_fail"
SFX_HEAVY_HIT = "heavy_hit"
SFX_SHIELD = "shield"
SFX_SHIELD_BLOCK = "shield_block"
SFX_POISON = "poison"
SFX_BORROW_RETURN = "borrow_return"
SFX_CARD_PLAY = "card_play"
SFX_CARD_PLAY_MERCY = "card_play_mercy"
SFX_CARD_PLAY_STEAL = "card_play_steal"
SFX_CARD_PLAY_HEAVY = "card_play_heavy"
SFX_CARD_PLAY_SHIELD = "card_play_shield"
SFX_CARD_PLAY_POISON = "card_play_poison"
SFX_CARD_PICK = "card_pick"
SFX_TURN_START = "turn_start"
SFX_TURN_SKIP = "turn_skip"
SFX_MATCH_START = "match_start"
SFX_DEAL = "deal"
SFX_WIN = "win"
SFX_LOSE = "lose"
SFX_CRAFT = "craft"
SFX_MERCY_ADD = "mercy_add"
SFX_DENY = "deny"
SFX_UI_CLICK = "ui_click"
SFX_THEME_CHANGE = "theme_change"
SFX_HH_READY = "hh_ready"
SFX_RELIEF_END = "relief_end"

SAMPLE_RATE = 22050

_lock = threading.Lock()
_style: str = "pixel"
_seed: int = 0
_cache: dict[tuple[str, str, int], bytes] = {}
_enabled: bool = True
_muted: bool = False


def set_sfx_theme(card_style: str, theme_name: str = "") -> None:
    """Rebuild SFX palette when the visual theme changes."""
    global _style, _seed, _cache
    with _lock:
        _style = (card_style or "pixel").lower()
        _seed = sum(ord(c) for c in theme_name) & 0xFFFF
        _cache.clear()
    # Swap BGM loop to match the new theme if music is already playing.
    if _bgm_wanted:
        start_bgm(force_rebuild=True)


def set_sfx_enabled(enabled: bool) -> None:
    global _enabled
    _enabled = enabled


def set_sfx_muted(muted: bool) -> None:
    global _muted
    _muted = muted


def play_sfx(name: str, delay_ms: int = 0) -> None:
    """Play a named cue for the active theme (async, non-blocking)."""
    if not _enabled or _muted:
        return

    def _run() -> None:
        try:
            custom = _custom_sfx_path(name)
            if custom is not None:
                _play_wav_file(custom)
                return
            data = _get_wav(name)
            _play_wav_bytes(data)
        except Exception:
            pass

    if delay_ms > 0:
        threading.Timer(delay_ms / 1000.0, _run).start()
    else:
        threading.Thread(target=_run, daemon=True).start()


def play_card_play_sfx(card) -> None:
    """Card-type play sting (Mercy / Steal / Heavy Hit / Shield / normal)."""
    if getattr(card, "heal_any", False):
        play_sfx(SFX_CARD_PLAY_MERCY)
    elif getattr(card, "steals", False):
        play_sfx(SFX_CARD_PLAY_STEAL)
    elif getattr(card, "heavy_hit", False):
        play_sfx(SFX_CARD_PLAY_HEAVY)
    elif getattr(card, "shields", False):
        play_sfx(SFX_CARD_PLAY_SHIELD)
    elif getattr(card, "poisons", False):
        play_sfx(SFX_CARD_PLAY_POISON)
    else:
        play_sfx(SFX_CARD_PLAY)


# ---------------------------------------------------------------------------
# Playback
# ---------------------------------------------------------------------------

_play_lock = threading.Lock()


def _custom_sfx_path(name: str) -> Path | None:
    filename = CUSTOM_SFX_FILES.get(name)
    if not filename:
        return None
    for base in (ASSETS_DIR, PROJECT_ROOT):
        path = base / filename
        if path.is_file():
            return path
    return None


def _play_wav_file(path: Path) -> None:
    if sys.platform == "darwin":
        with _play_lock:
            subprocess.run(
                ["/usr/bin/afplay", str(path)],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        return
    try:
        import winsound
    except ImportError:
        return
    with _play_lock:
        try:
            winsound.PlaySound(str(path), winsound.SND_FILENAME)
        except Exception:
            pass


def _play_wav_bytes(data: bytes) -> None:
    if sys.platform == "darwin":
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as sound_file:
            sound_file.write(data)
            path = Path(sound_file.name)
        try:
            _play_wav_file(path)
        finally:
            path.unlink(missing_ok=True)
        return
    # Windows winsound cannot combine SND_MEMORY with SND_ASYNC.
    # Play synchronously inside our worker thread so the UI stays responsive.
    try:
        import winsound
    except ImportError:
        return
    with _play_lock:
        try:
            winsound.PlaySound(data, winsound.SND_MEMORY)
        except Exception:
            pass


def _get_wav(name: str) -> bytes:
    key = (_style, name, _seed)
    with _lock:
        cached = _cache.get(key)
        if cached is not None:
            return cached
    samples = _synthesize(name, _style, _seed)
    data = _pcm_to_wav(samples)
    with _lock:
        _cache[key] = data
    return data


def _pcm_to_wav(samples: list[float]) -> bytes:
    buf = BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        frames = bytearray()
        for s in samples:
            v = max(-1.0, min(1.0, s))
            frames += struct.pack("<h", int(v * 32767))
        wf.writeframes(frames)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Style profiles — pitch / wave / noise character per card_style
# ---------------------------------------------------------------------------

def _style_profile(style: str, seed: int) -> dict:
    """Return synthesis knobs for a visual card style."""
    # Seed nudges pitch so random themes of the same style still differ a bit.
    nudge = 0.92 + ((seed % 17) / 100.0)

    profiles = {
        "pixel": {
            "wave": "square",
            "noise": 0.08,
            "bright": 0.85,
            "decay": 2.8,
            "base": 220.0 * nudge,
            "harmonics": 0.2,
        },
        "neon": {
            "wave": "sine",
            "noise": 0.04,
            "bright": 1.25,
            "decay": 2.2,
            "base": 330.0 * nudge,
            "harmonics": 0.55,
            "vibrato": 7.0,
        },
        "stone": {
            "wave": "triangle",
            "noise": 0.35,
            "bright": 0.55,
            "decay": 3.4,
            "base": 110.0 * nudge,
            "harmonics": 0.1,
        },
        "ice": {
            "wave": "sine",
            "noise": 0.12,
            "bright": 1.4,
            "decay": 1.8,
            "base": 520.0 * nudge,
            "harmonics": 0.7,
        },
        "lava": {
            "wave": "saw",
            "noise": 0.28,
            "bright": 0.9,
            "decay": 2.6,
            "base": 140.0 * nudge,
            "harmonics": 0.35,
        },
        "arcade": {
            "wave": "square",
            "noise": 0.05,
            "bright": 1.1,
            "decay": 3.0,
            "base": 260.0 * nudge,
            "harmonics": 0.15,
        },
        "gold": {
            "wave": "triangle",
            "noise": 0.03,
            "bright": 1.15,
            "decay": 1.6,
            "base": 392.0 * nudge,
            "harmonics": 0.6,
        },
        "circuit": {
            "wave": "pwm",
            "noise": 0.1,
            "bright": 1.05,
            "decay": 2.4,
            "base": 300.0 * nudge,
            "harmonics": 0.25,
        },
        "shadow": {
            "wave": "sine",
            "noise": 0.4,
            "bright": 0.45,
            "decay": 3.8,
            "base": 90.0 * nudge,
            "harmonics": 0.15,
        },
        "crimson": {
            "wave": "saw",
            "noise": 0.22,
            "bright": 0.95,
            "decay": 2.5,
            "base": 160.0 * nudge,
            "harmonics": 0.3,
        },
        "ocean": {
            "wave": "sine",
            "noise": 0.1,
            "bright": 1.15,
            "decay": 2.0,
            "base": 280.0 * nudge,
            "harmonics": 0.5,
            "vibrato": 4.0,
        },
        "sakura": {
            "wave": "triangle",
            "noise": 0.06,
            "bright": 1.2,
            "decay": 1.9,
            "base": 440.0 * nudge,
            "harmonics": 0.45,
        },
        "jazz": {
            "wave": "triangle",
            "noise": 0.12,
            "bright": 0.8,
            "decay": 2.8,
            "base": 180.0 * nudge,
            "harmonics": 0.35,
        },
        "toxic": {
            "wave": "pwm",
            "noise": 0.2,
            "bright": 1.1,
            "decay": 2.3,
            "base": 240.0 * nudge,
            "harmonics": 0.25,
        },
        "solar": {
            "wave": "saw",
            "noise": 0.08,
            "bright": 1.3,
            "decay": 2.1,
            "base": 360.0 * nudge,
            "harmonics": 0.4,
        },
        "aurora": {
            "wave": "sine",
            "noise": 0.05,
            "bright": 1.35,
            "decay": 1.7,
            "base": 480.0 * nudge,
            "harmonics": 0.65,
            "vibrato": 5.5,
        },
        "ruins": {
            "wave": "triangle",
            "noise": 0.3,
            "bright": 0.6,
            "decay": 3.2,
            "base": 130.0 * nudge,
            "harmonics": 0.12,
        },
        "void": {
            "wave": "sine",
            "noise": 0.45,
            "bright": 0.4,
            "decay": 4.0,
            "base": 75.0 * nudge,
            "harmonics": 0.2,
        },
        "candy": {
            "wave": "square",
            "noise": 0.04,
            "bright": 1.2,
            "decay": 2.6,
            "base": 310.0 * nudge,
            "harmonics": 0.2,
        },
        "village": {
            "wave": "square",
            "noise": 0.1,
            "bright": 0.9,
            "decay": 2.7,
            "base": 200.0 * nudge,
            "harmonics": 0.18,
        },
    }
    return profiles.get(style, profiles["pixel"])


def _osc(kind: str, phase: float, duty: float = 0.5) -> float:
    p = phase % 1.0
    if kind == "sine":
        return math.sin(2 * math.pi * p)
    if kind == "square":
        return 1.0 if p < 0.5 else -1.0
    if kind == "saw":
        return 2.0 * p - 1.0
    if kind == "triangle":
        return 1.0 - 4.0 * abs(p - 0.5)
    if kind == "pwm":
        return 1.0 if p < duty else -1.0
    return math.sin(2 * math.pi * p)


def _noise(i: int, seed: int) -> float:
    # Deterministic cheap noise (no random module dependency in hot path)
    x = (i * 1103515245 + seed * 12345) & 0x7FFFFFFF
    return (x / 0x7FFFFFFF) * 2.0 - 1.0


def _tone(
    freq: float,
    ms: float,
    *,
    volume: float,
    profile: dict,
    seed: int,
    slide: float = 0.0,
    duty: float = 0.5,
) -> list[float]:
    n = max(1, int(SAMPLE_RATE * ms / 1000.0))
    out: list[float] = []
    kind = profile["wave"]
    decay = profile["decay"]
    noise_amt = profile["noise"]
    harm = profile["harmonics"]
    vibrato = profile.get("vibrato", 0.0)
    phase = 0.0
    phase2 = 0.0
    for i in range(n):
        t = i / SAMPLE_RATE
        env = math.exp(-decay * t) * (1.0 - 0.15 * (i / n))
        f = freq * (1.0 + slide * (i / n))
        if vibrato:
            f *= 1.0 + 0.012 * math.sin(2 * math.pi * vibrato * t)
        phase += f / SAMPLE_RATE
        sample = _osc(kind, phase, duty)
        if harm > 0:
            phase2 += (f * 2.01) / SAMPLE_RATE
            sample += harm * 0.45 * _osc(kind, phase2, duty)
        sample += noise_amt * 0.55 * _noise(i + int(freq), seed)
        out.append(sample * volume * env * profile["bright"] * 0.85)
    return out


def _chord(freqs: list[float], ms: float, volume: float, profile: dict, seed: int) -> list[float]:
    layers = [
        _tone(f, ms, volume=volume / max(1, len(freqs)), profile=profile, seed=seed + i)
        for i, f in enumerate(freqs)
    ]
    n = max(len(x) for x in layers)
    out = [0.0] * n
    for layer in layers:
        for i, s in enumerate(layer):
            out[i] += s
    return out


def _seq(parts: list[list[float]], gap_ms: float = 0.0) -> list[float]:
    gap = [0.0] * int(SAMPLE_RATE * gap_ms / 1000.0)
    out: list[float] = []
    for i, part in enumerate(parts):
        out.extend(part)
        if i < len(parts) - 1 and gap:
            out.extend(gap)
    return out


# ---------------------------------------------------------------------------
# Event → synthesis recipes
# ---------------------------------------------------------------------------

def _synthesize(name: str, style: str, seed: int) -> list[float]:
    p = _style_profile(style, seed)
    b = p["base"]

    recipes: dict[str, Callable[[], list[float]]] = {
        SFX_DAMAGE: lambda: _tone(b * 1.4, 90, volume=0.9, profile=p, seed=seed, slide=-0.35),
        SFX_CRASH_OUT: lambda: _seq(
            [
                _tone(b * 2.2, 70, volume=1.0, profile=p, seed=seed, slide=-0.2),
                _tone(b * 0.7, 220, volume=1.0, profile=p, seed=seed + 3, slide=-0.55),
            ],
            gap_ms=20,
        ),
        SFX_HEAL: lambda: _chord([b * 1.5, b * 2.0, b * 2.5], 140, 0.7, p, seed),
        SFX_STEAL: lambda: _tone(b * 2.4, 120, volume=0.75, profile=p, seed=seed, slide=0.55),
        SFX_STEAL_FAIL: lambda: _tone(b * 0.9, 100, volume=0.45, profile=p, seed=seed, slide=-0.2),
        SFX_HEAVY_HIT: lambda: _seq(
            [
                _tone(b * 0.55, 80, volume=1.0, profile=p, seed=seed),
                _tone(b * 1.8, 100, volume=0.95, profile=p, seed=seed + 1, slide=0.25),
            ],
            gap_ms=10,
        ),
        SFX_SHIELD: lambda: _chord([b * 1.1, b * 1.65, b * 2.2], 130, 0.65, p, seed),
        SFX_SHIELD_BLOCK: lambda: _tone(b * 1.9, 90, volume=0.7, profile=p, seed=seed, slide=-0.15),
        SFX_POISON: lambda: _tone(b * 1.35, 140, volume=0.6, profile=p, seed=seed, slide=-0.35),
        SFX_BORROW_RETURN: lambda: _tone(b * 1.7, 90, volume=0.55, profile=p, seed=seed, slide=-0.4),
        SFX_CARD_PLAY: lambda: _tone(b * 1.2, 70, volume=0.55, profile=p, seed=seed),
        SFX_CARD_PLAY_MERCY: lambda: _chord([b * 1.6, b * 2.4], 110, 0.6, p, seed),
        SFX_CARD_PLAY_STEAL: lambda: _tone(b * 2.0, 85, volume=0.65, profile=p, seed=seed, slide=0.4),
        SFX_CARD_PLAY_HEAVY: lambda: _tone(b * 0.8, 100, volume=0.85, profile=p, seed=seed, slide=-0.15),
        SFX_CARD_PLAY_SHIELD: lambda: _chord([b * 1.3, b * 2.0], 95, 0.6, p, seed),
        SFX_CARD_PLAY_POISON: lambda: _tone(b * 0.95, 100, volume=0.6, profile=p, seed=seed, slide=0.2),
        SFX_TURN_START: lambda: _tone(b * 1.1, 80, volume=0.4, profile=p, seed=seed, slide=0.2),
        SFX_TURN_SKIP: lambda: _tone(b * 0.75, 60, volume=0.35, profile=p, seed=seed),
        SFX_MATCH_START: lambda: _seq(
            [
                _tone(b, 70, volume=0.55, profile=p, seed=seed),
                _tone(b * 1.5, 70, volume=0.6, profile=p, seed=seed + 1),
                _tone(b * 2.0, 110, volume=0.7, profile=p, seed=seed + 2),
            ],
            gap_ms=35,
        ),
        SFX_DEAL: lambda: _seq(
            [
                _tone(b * 1.3, 40, volume=0.4, profile=p, seed=seed + i)
                for i in range(4)
            ],
            gap_ms=25,
        ),
        SFX_WIN: lambda: _seq(
            [
                _chord([b * 1.0, b * 1.25, b * 1.5], 160, 0.7, p, seed),
                _chord([b * 1.25, b * 1.5, b * 2.0], 220, 0.75, p, seed + 2),
            ],
            gap_ms=40,
        ),
        SFX_LOSE: lambda: _seq(
            [
                _tone(b * 1.4, 120, volume=0.55, profile=p, seed=seed, slide=-0.25),
                _tone(b * 0.7, 280, volume=0.5, profile=p, seed=seed + 1, slide=-0.4),
            ],
            gap_ms=30,
        ),
        SFX_CRAFT: lambda: _tone(b * 1.8, 60, volume=0.5, profile=p, seed=seed),
        SFX_MERCY_ADD: lambda: _chord([b * 1.5, b * 2.25], 130, 0.55, p, seed),
        SFX_DENY: lambda: _tone(b * 0.6, 70, volume=0.4, profile=p, seed=seed, slide=-0.1),
        SFX_UI_CLICK: lambda: _tone(b * 2.2, 35, volume=0.3, profile=p, seed=seed),
        SFX_THEME_CHANGE: lambda: _seq(
            [
                _tone(b * 1.0, 50, volume=0.45, profile=p, seed=seed),
                _tone(b * 1.6, 70, volume=0.5, profile=p, seed=seed + 1),
            ],
            gap_ms=20,
        ),
        SFX_HH_READY: lambda: _tone(b * 2.6, 90, volume=0.55, profile=p, seed=seed, slide=0.15),
        SFX_RELIEF_END: lambda: _tone(b * 1.0, 80, volume=0.4, profile=p, seed=seed, slide=-0.2),
    }

    builder = recipes.get(name)
    if builder is None:
        return _tone(b, 50, volume=0.3, profile=p, seed=seed)
    samples = builder()
    # Soft clip
    peak = max((abs(s) for s in samples), default=1.0) or 1.0
    if peak > 1.0:
        samples = [s / peak for s in samples]
    return samples


# ---------------------------------------------------------------------------
# Background music (pygame) — looping soft bed, volume controllable
# ---------------------------------------------------------------------------

DEFAULT_BGM_VOLUME = 0.40
_CUSTOM_BGM_NAMES = ("bgm_crashout.wav", "music_crashout.wav")

_bgm_volume: float = DEFAULT_BGM_VOLUME
_bgm_wanted: bool = False
_bgm_channel = None
_bgm_sound = None
_bgm_mixer_ready: bool = False
_bgm_key: tuple[str, int] | None = None


def get_bgm_volume() -> float:
    return _bgm_volume


def set_bgm_volume(volume: float) -> None:
    """Set BGM volume in 0.0–1.0 (also applies immediately if playing)."""
    global _bgm_volume
    _bgm_volume = max(0.0, min(1.0, float(volume)))
    if _bgm_channel is not None:
        try:
            _bgm_channel.set_volume(_bgm_volume)
        except Exception:
            pass


def _ensure_mixer() -> bool:
    global _bgm_mixer_ready
    if _bgm_mixer_ready:
        return True
    try:
        import pygame

        if not pygame.mixer.get_init():
            pygame.mixer.init(frequency=SAMPLE_RATE, size=-16, channels=2, buffer=1024)
        _bgm_mixer_ready = True
        return True
    except Exception:
        return False


def _custom_bgm_path() -> Path | None:
    for name in _CUSTOM_BGM_NAMES:
        for base in (ASSETS_DIR, PROJECT_ROOT):
            path = base / name
            if path.is_file():
                return path
    return None


def _bgm_note(
    freq: float,
    ms: float,
    *,
    volume: float,
    wave_kind: str,
    seed: int,
) -> list[float]:
    n = max(1, int(SAMPLE_RATE * ms / 1000.0))
    out: list[float] = []
    phase = 0.0
    attack = max(1, int(0.02 * SAMPLE_RATE))
    release = max(1, int(0.08 * SAMPLE_RATE))
    for i in range(n):
        t = i / SAMPLE_RATE
        env = 1.0
        if i < attack:
            env = i / attack
        elif i > n - release:
            env = max(0.0, (n - i) / release)
        env *= math.exp(-1.2 * t)
        phase += freq / SAMPLE_RATE
        sample = _osc(wave_kind, phase)
        # Soft pad harmonic
        sample += 0.25 * _osc("sine", phase * 2.01)
        sample += 0.03 * _noise(i, seed)
        out.append(sample * volume * env * 0.22)
    return out


def _synthesize_bgm(style: str, seed: int) -> list[float]:
    """Build a short seamless-ish soft loop (~12s) for the active style."""
    profile = _style_profile(style, seed)
    root = profile["base"] * 0.5
    # Major-ish pentatonic degrees for a calm game bed
    degrees = [1.0, 9 / 8, 5 / 4, 3 / 2, 5 / 3, 2.0]
    pattern = [
        0, 2, 4, 2, 3, 1, 4, 2,
        0, 3, 4, 5, 4, 2, 1, 0,
        2, 4, 3, 1, 0, 2, 4, 3,
        5, 4, 2, 0, 1, 3, 2, 0,
    ]
    wave_kind = "sine" if profile["wave"] in ("sine", "triangle") else "triangle"
    note_ms = 375
    parts: list[list[float]] = []
    for i, deg_i in enumerate(pattern):
        freq = root * degrees[deg_i % len(degrees)]
        # Alternate octave lightly for variety
        if i % 7 == 0:
            freq *= 0.5
        parts.append(
            _bgm_note(
                freq,
                note_ms,
                volume=0.55 if i % 4 else 0.4,
                wave_kind=wave_kind,
                seed=seed + i,
            )
        )
    samples = _seq(parts, gap_ms=0)
    # Soft fade edges so loop restart is less clicky
    fade = min(len(samples) // 20, int(0.15 * SAMPLE_RATE))
    for i in range(fade):
        samples[i] *= i / fade
        samples[-(i + 1)] *= i / fade
    peak = max((abs(s) for s in samples), default=1.0) or 1.0
    if peak > 0.9:
        samples = [s * 0.9 / peak for s in samples]
    return samples


def start_bgm(*, force_rebuild: bool = False) -> None:
    """Start (or keep) looping background music for the match."""
    global _bgm_wanted, _bgm_channel, _bgm_sound, _bgm_key
    _bgm_wanted = True
    if not _ensure_mixer():
        return
    key = (_style, _seed)
    if (
        not force_rebuild
        and _bgm_channel is not None
        and _bgm_channel.get_busy()
        and _bgm_key == key
    ):
        _bgm_channel.set_volume(_bgm_volume)
        return
    try:
        import pygame

        custom = _custom_bgm_path()
        if custom is not None:
            sound = pygame.mixer.Sound(str(custom))
            _bgm_key = ("custom", 0)
        else:
            wav = _pcm_to_wav(_synthesize_bgm(_style, _seed))
            sound = pygame.mixer.Sound(file=BytesIO(wav))
            _bgm_key = key
        if _bgm_channel is not None:
            _bgm_channel.stop()
        # Reserve channel 0 for BGM so SFX paths stay independent.
        channel = pygame.mixer.Channel(0)
        channel.set_volume(_bgm_volume)
        channel.play(sound, loops=-1, fade_ms=400)
        _bgm_sound = sound
        _bgm_channel = channel
    except Exception:
        _bgm_channel = None
        _bgm_sound = None


def stop_bgm() -> None:
    """Stop background music (leaving setup / closing app)."""
    global _bgm_wanted, _bgm_channel, _bgm_sound
    _bgm_wanted = False
    if _bgm_channel is not None:
        try:
            _bgm_channel.fadeout(350)
        except Exception:
            try:
                _bgm_channel.stop()
            except Exception:
                pass
    _bgm_channel = None
    _bgm_sound = None


def shutdown_audio() -> None:
    """Full teardown on app exit."""
    stop_bgm()
    global _bgm_mixer_ready
    try:
        import pygame

        if pygame.mixer.get_init():
            pygame.mixer.quit()
    except Exception:
        pass
    _bgm_mixer_ready = False
