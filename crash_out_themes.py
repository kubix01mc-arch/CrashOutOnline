#!/usr/bin/env python3
"""Theme presets and random theme generation for the window UI."""

from __future__ import annotations

import ctypes
import json
import os
import random
import struct
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

CardStyle = Literal[
    "pixel",
    "neon",
    "stone",
    "ice",
    "lava",
    "arcade",
    "gold",
    "circuit",
    "shadow",
    "crimson",
    "ocean",
    "sakura",
    "jazz",
    "toxic",
    "solar",
    "aurora",
    "ruins",
    "void",
    "candy",
    "village",
]

CARD_STYLES: tuple[CardStyle, ...] = (
    "pixel",
    "neon",
    "stone",
    "ice",
    "lava",
    "arcade",
    "gold",
    "circuit",
    "shadow",
    "crimson",
    "ocean",
    "sakura",
    "jazz",
    "toxic",
    "solar",
    "aurora",
    "ruins",
    "void",
    "candy",
    "village",
)

FR_PRIVATE = 0x10
HWND_BROADCAST = 0xFFFF
WM_FONTCHANGE = 0x001D

PROJECT_ROOT = Path(__file__).resolve().parent
if sys.platform == "win32":
    CONFIG_DIR = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    CONFIG_DIR /= "Crash Out"
elif sys.platform == "darwin":
    CONFIG_DIR = Path.home() / "Library" / "Application Support" / "Crash Out"
else:
    CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    CONFIG_DIR /= "crash-out"
PREFS_PATH = CONFIG_DIR / "user_prefs.json"
LEGACY_PREFS_PATH = PROJECT_ROOT / "user_prefs.json"
DEFAULT_FONT_PATH = (
    PROJECT_ROOT / "Minecraft-20230518T220806Z-001 (1)" / "Minecraft" / "arial.ttf"
)
FONT_DIR = PROJECT_ROOT / "Minecraft-20230518T220806Z-001 (1)" / "Minecraft"


# Default poison palette (deep purple fill / violet accent / lilac text)
DEFAULT_POISON_ART: tuple[str, str, str] = ("#2a1540", "#a855f7", "#f3e8ff")


@dataclass(frozen=True)
class CardArt:
    """Pixel-card fill / accent / text colors."""

    normal: tuple[str, str, str]
    heal: tuple[str, str, str]
    heavy_hit: tuple[str, str, str]
    steal: tuple[str, str, str]
    disabled: tuple[str, str, str]
    selected: tuple[str, str, str]
    poison: tuple[str, str, str] = DEFAULT_POISON_ART


@dataclass(frozen=True)
class GameTheme:
    name: str
    font_path: Path | None
    font_family: str
    screen_bg: str
    win_bg: str
    lose_bg: str
    title_fg: str
    body_fg: str
    log_bg: str
    log_fg: str
    overlay_bg: str
    panel_bg: str
    panel_border: str
    target_bg: str
    hud_active: tuple[str, str, str]
    hud_idle: tuple[str, str, str]
    hud_dead: tuple[str, str, str]
    target_self: tuple[str, str, str]
    target_other: tuple[str, str, str]
    scale_trough: str
    scale_fill: str
    scale_border: str
    scale_light: str
    scale_dark: str
    cards: CardArt = field(repr=False)
    card_style: CardStyle = "pixel"


def _register_font_file(font_path: Path) -> None:
    if not font_path.exists() or not hasattr(ctypes, "windll"):
        return
    add_ex = getattr(ctypes.windll.gdi32, "AddFontResourceExW", None)
    if add_ex is None:
        return
    try:
        add_ex(str(font_path), FR_PRIVATE, None)
        # Notify, don't wait — HWND_BROADCAST + SendMessageW can hang for minutes.
        ctypes.windll.user32.SendNotifyMessageW(HWND_BROADCAST, WM_FONTCHANGE, 0, 0)
    except Exception:
        pass


def _read_font_family(font_path: Path) -> str:
    """Best-effort TTF/OTF family name (no external deps)."""
    try:
        data = font_path.read_bytes()
        if len(data) < 12:
            return font_path.stem
        num_tables = struct.unpack(">H", data[4:6])[0]
        name_offset = None
        off = 12
        for _ in range(num_tables):
            tag, _csum, start, length = struct.unpack(">4sIII", data[off : off + 16])
            off += 16
            if tag == b"name":
                name_offset = start
                break
        if name_offset is None:
            return font_path.stem
        count, string_offset = struct.unpack(">HH", data[name_offset + 2 : name_offset + 6])
        for i in range(count):
            rec = name_offset + 6 + i * 12
            plat, enc, lang, name_id, slen, soff = struct.unpack(
                ">HHHHHH", data[rec : rec + 12]
            )
            if name_id != 1:
                continue
            raw = data[name_offset + string_offset + soff : name_offset + string_offset + soff + slen]
            if plat == 3:
                return raw.decode("utf-16-be", errors="replace").strip() or font_path.stem
            if plat == 1:
                return raw.decode("latin-1", errors="replace").strip() or font_path.stem
    except Exception:
        pass
    return font_path.stem


def _clamp(v: float) -> float:
    return max(0.0, min(1.0, v))


def _hsl_to_hex(h: float, s: float, l: float) -> str:
    h, s, l = h % 1.0, _clamp(s), _clamp(l)
    if s == 0:
        val = int(l * 255)
        return f"#{val:02x}{val:02x}{val:02x}"

    def hue_to_rgb(p: float, q: float, t: float) -> float:
        if t < 0:
            t += 1
        if t > 1:
            t -= 1
        if t < 1 / 6:
            return p + (q - p) * 6 * t
        if t < 1 / 2:
            return q
        if t < 2 / 3:
            return p + (q - p) * (2 / 3 - t) * 6
        return p

    q = l * (1 + s) if l < 0.5 else l + s - l * s
    p = 2 * l - q
    r = int(hue_to_rgb(p, q, h + 1 / 3) * 255)
    g = int(hue_to_rgb(p, q, h) * 255)
    b = int(hue_to_rgb(p, q, h - 1 / 3) * 255)
    return f"#{r:02x}{g:02x}{b:02x}"


def _shift_hex(color: str, delta: int) -> str:
    raw = color.lstrip("#")
    rgb = [max(0, min(255, int(raw[i : i + 2], 16) + delta)) for i in (0, 2, 4)]
    return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"


def _card_triplet(h: float, s: float, l_fill: float, l_accent: float, l_text: float) -> tuple[str, str, str]:
    return (
        _hsl_to_hex(h, s, l_fill),
        _hsl_to_hex(h, min(1.0, s + 0.15), l_accent),
        _hsl_to_hex(h, max(0.0, s - 0.2), l_text),
    )


def _build_theme(
    *,
    name: str,
    font_path: Path | None,
    font_family: str,
    screen_bg: str,
    win_bg: str,
    lose_bg: str,
    title_fg: str,
    body_fg: str,
    log_bg: str,
    log_fg: str,
    overlay_bg: str,
    panel_bg: str,
    panel_border: str,
    target_bg: str,
    cards: CardArt,
    scale_hue: float,
    hud_active: tuple[str, str, str] | None = None,
    hud_idle: tuple[str, str, str] | None = None,
    hud_dead: tuple[str, str, str] | None = None,
    target_self: tuple[str, str, str] | None = None,
    target_other: tuple[str, str, str] | None = None,
    card_style: CardStyle = "pixel",
) -> GameTheme:
    return GameTheme(
        name=name,
        font_path=font_path,
        font_family=font_family,
        screen_bg=screen_bg,
        win_bg=win_bg,
        lose_bg=lose_bg,
        title_fg=title_fg,
        body_fg=body_fg,
        log_bg=log_bg,
        log_fg=log_fg,
        overlay_bg=overlay_bg,
        panel_bg=panel_bg,
        panel_border=panel_border,
        target_bg=target_bg,
        hud_active=hud_active or ("#3d5a45", "#f0c674", "#fff6d8"),
        hud_idle=hud_idle or (_shift_hex(screen_bg, 18), "#8a948c", "#c4b59a"),
        hud_dead=hud_dead or cards.disabled,
        target_self=target_self or ("#3d5a45", "#f0c674", "#f7f0e0"),
        target_other=target_other or (_shift_hex(screen_bg, 12), "#c4b59a", "#f2e9d8"),
        scale_trough=_hsl_to_hex(scale_hue, 0.25, 0.18),
        scale_fill=_hsl_to_hex(scale_hue, 0.45, 0.55),
        scale_border=_hsl_to_hex(scale_hue, 0.35, 0.42),
        scale_light=_hsl_to_hex(scale_hue, 0.45, 0.65),
        scale_dark=_hsl_to_hex(scale_hue, 0.35, 0.32),
        card_style=card_style,
        cards=cards,
    )


def _theme_font(filename: str, fallback: str = "Minecraft") -> tuple[Path | None, str]:
    path = FONT_DIR / filename
    if path.exists():
        _register_font_file(path)
        return path, _read_font_family(path)
    if DEFAULT_FONT_PATH.exists():
        _register_font_file(DEFAULT_FONT_PATH)
        return DEFAULT_FONT_PATH, fallback
    return None, fallback


def default_theme() -> GameTheme:
    cards = CardArt(
        normal=("#3a3228", "#d4b483", "#f7edd8"),
        heal=("#1e3d2a", "#6ecf8a", "#d8ffe6"),
        heavy_hit=("#4a241c", "#e07a5f", "#ffe4d8"),
        steal=("#2e2240", "#c9a0dc", "#f3e6ff"),
        disabled=("#2a302c", "#6a736c", "#8a948c"),
        selected=("#3d5a45", "#f0c674", "#fff6d8"),
        poison=("#2a1540", "#a855f7", "#f3e8ff"),
    )
    return _build_theme(
        name="Default",
        font_path=DEFAULT_FONT_PATH if DEFAULT_FONT_PATH.exists() else None,
        font_family="Minecraft",
        screen_bg="#1a1f1c",
        win_bg="#1f5a32",
        lose_bg="#6b1f1f",
        title_fg="#f2e9d8",
        body_fg="#d7d2c4",
        log_bg="#121612",
        log_fg="#c8e6c0",
        overlay_bg="#1a1f1c",
        panel_bg="#222824",
        panel_border="#c4b59a",
        target_bg="#222824",
        cards=cards,
        scale_hue=130 / 360,
        card_style="pixel",
    )


def creative_theme_presets() -> list[GameTheme]:
    """Hand-crafted themes with distinct card frame art styles."""
    presets: list[GameTheme] = []

    neon_font = _theme_font("PressStart2P-Regular.ttf", "Minecraft")
    presets.append(
        _build_theme(
            name="Neon City",
            font_path=neon_font[0],
            font_family=neon_font[1],
            screen_bg="#0a0618",
            win_bg="#0d3d2a",
            lose_bg="#4a0828",
            title_fg="#ff71ce",
            body_fg="#05d9e8",
            log_bg="#12082a",
            log_fg="#01ff70",
            overlay_bg="#0a0618",
            panel_bg="#160c32",
            panel_border="#05d9e8",
            target_bg="#160c32",
            cards=CardArt(
                normal=("#12082a", "#ff71ce", "#fff0fa"),
                heal=("#0a1828", "#01ff70", "#d8ffe8"),
                heavy_hit=("#281008", "#fffb96", "#fffde0"),
                steal=("#180828", "#bd93f9", "#f3e6ff"),
                disabled=("#181028", "#5a5080", "#9088a8"),
                selected=("#1a0838", "#05d9e8", "#e0ffff"),
            ),
            scale_hue=300 / 360,
            card_style="neon",
            hud_active=("#1a0838", "#05d9e8", "#e0ffff"),
            hud_idle=("#12082a", "#bd93f9", "#d8c8f0"),
        )
    )

    presets.append(
        _build_theme(
            name="Volcanic Forge",
            font_path=DEFAULT_FONT_PATH if DEFAULT_FONT_PATH.exists() else None,
            font_family="Minecraft",
            screen_bg="#140808",
            win_bg="#2a5018",
            lose_bg="#6b1010",
            title_fg="#ffd080",
            body_fg="#ffb090",
            log_bg="#0c0404",
            log_fg="#ff9040",
            overlay_bg="#140808",
            panel_bg="#281010",
            panel_border="#ff6020",
            target_bg="#281010",
            cards=CardArt(
                normal=("#281008", "#ff6020", "#ffe0c8"),
                heal=("#102018", "#60c060", "#d0ffd0"),
                heavy_hit=("#381008", "#ff4020", "#ffe0d0"),
                steal=("#201028", "#c060ff", "#ecd0ff"),
                disabled=("#201818", "#705050", "#988880"),
                selected=("#401808", "#ffb040", "#fff0d0"),
            ),
            scale_hue=20 / 360,
            card_style="lava",
            hud_active=("#401808", "#ffb040", "#fff0d0"),
        )
    )

    presets.append(
        _build_theme(
            name="Frozen Tundra",
            font_path=DEFAULT_FONT_PATH if DEFAULT_FONT_PATH.exists() else None,
            font_family="Minecraft",
            screen_bg="#0c1828",
            win_bg="#1a4838",
            lose_bg="#482838",
            title_fg="#e8f8ff",
            body_fg="#b8d8f0",
            log_bg="#081420",
            log_fg="#a0e0ff",
            overlay_bg="#0c1828",
            panel_bg="#142838",
            panel_border="#80d0ff",
            target_bg="#142838",
            cards=CardArt(
                normal=("#183048", "#80d0ff", "#f0f8ff"),
                heal=("#103828", "#60e0a0", "#e0fff0"),
                heavy_hit=("#283848", "#a0e0ff", "#f0ffff"),
                steal=("#202848", "#a0b0ff", "#e8e8ff"),
                disabled=("#182028", "#607080", "#90a0b0"),
                selected=("#204058", "#c0f0ff", "#ffffff"),
            ),
            scale_hue=200 / 360,
            card_style="ice",
            hud_active=("#204058", "#c0f0ff", "#ffffff"),
        )
    )

    presets.append(
        _build_theme(
            name="Enchanted Grove",
            font_path=DEFAULT_FONT_PATH if DEFAULT_FONT_PATH.exists() else None,
            font_family="Minecraft",
            screen_bg="#101a12",
            win_bg="#1f5a32",
            lose_bg="#5a2818",
            title_fg="#e8ffe0",
            body_fg="#c8e8b8",
            log_bg="#0a120a",
            log_fg="#90e878",
            overlay_bg="#101a12",
            panel_bg="#1a2820",
            panel_border="#78c860",
            target_bg="#1a2820",
            cards=CardArt(
                normal=("#243820", "#a0d878", "#f0ffe8"),
                heal=("#1a3828", "#60e090", "#e0ffe8"),
                heavy_hit=("#382818", "#e09060", "#ffe8d8"),
                steal=("#282038", "#b090e0", "#f0e8ff"),
                disabled=("#202820", "#688068", "#90a890"),
                selected=("#2a4828", "#f0d060", "#fffae0"),
            ),
            scale_hue=120 / 360,
            card_style="pixel",
        )
    )

    shadow_font = _theme_font("Creepster-Regular.ttf", "Minecraft")
    presets.append(
        _build_theme(
            name="Shadow Realm",
            font_path=shadow_font[0],
            font_family=shadow_font[1],
            screen_bg="#060608",
            win_bg="#1a3020",
            lose_bg="#401018",
            title_fg="#c8b0e0",
            body_fg="#9080a8",
            log_bg="#040406",
            log_fg="#8060b0",
            overlay_bg="#060608",
            panel_bg="#100c18",
            panel_border="#6040a0",
            target_bg="#100c18",
            cards=CardArt(
                normal=("#100c14", "#8060b0", "#e0d0f0"),
                heal=("#0c1410", "#508060", "#c0e0c8"),
                heavy_hit=("#180c10", "#b05080", "#f0d0e0"),
                steal=("#140c20", "#9060c0", "#e8d8ff"),
                disabled=("#0c0c10", "#484058", "#686070"),
                selected=("#201030", "#a080d0", "#f0e8ff"),
            ),
            scale_hue=270 / 360,
            card_style="shadow",
            hud_active=("#201030", "#a080d0", "#f0e8ff"),
        )
    )

    arcade_font = _theme_font("PressStart2P-Regular.ttf", "Minecraft")
    presets.append(
        _build_theme(
            name="Arcade Cabinet",
            font_path=arcade_font[0],
            font_family=arcade_font[1],
            screen_bg="#101028",
            win_bg="#006040",
            lose_bg="#880018",
            title_fg="#ffff00",
            body_fg="#00ffff",
            log_bg="#080818",
            log_fg="#ff00ff",
            overlay_bg="#101028",
            panel_bg="#181840",
            panel_border="#ffff00",
            target_bg="#181840",
            cards=CardArt(
                normal=("#202050", "#ffff00", "#ffffe0"),
                heal=("#104030", "#00ff80", "#d0ffe8"),
                heavy_hit=("#502020", "#ff4040", "#ffe0e0"),
                steal=("#301050", "#ff80ff", "#ffe8ff"),
                disabled=("#202030", "#606080", "#9090a8"),
                selected=("#303070", "#00ffff", "#e0ffff"),
            ),
            scale_hue=60 / 360,
            card_style="arcade",
            hud_active=("#303070", "#00ffff", "#e0ffff"),
        )
    )

    presets.append(
        _build_theme(
            name="Royal Treasure",
            font_path=DEFAULT_FONT_PATH if DEFAULT_FONT_PATH.exists() else None,
            font_family="Minecraft",
            screen_bg="#181008",
            win_bg="#284018",
            lose_bg="#601818",
            title_fg="#ffe8a0",
            body_fg="#d8c090",
            log_bg="#100c04",
            log_fg="#f0c860",
            overlay_bg="#181008",
            panel_bg="#282010",
            panel_border="#e8b840",
            target_bg="#282010",
            cards=CardArt(
                normal=("#382818", "#e8b840", "#fff8e0"),
                heal=("#283820", "#80c060", "#e8ffe0"),
                heavy_hit=("#482018", "#e87840", "#ffe8d0"),
                steal=("#302040", "#c090e0", "#f0e8ff"),
                disabled=("#282018", "#706050", "#988878"),
                selected=("#483820", "#ffe060", "#fffff0"),
            ),
            scale_hue=45 / 360,
            card_style="gold",
            hud_active=("#483820", "#ffe060", "#fffff0"),
        )
    )

    circuit_font = _theme_font("RobotoMono-Regular.ttf", "Minecraft")
    presets.append(
        _build_theme(
            name="Cyber Grid",
            font_path=circuit_font[0],
            font_family=circuit_font[1],
            screen_bg="#041018",
            win_bg="#083828",
            lose_bg="#381018",
            title_fg="#40ffb0",
            body_fg="#80c0d0",
            log_bg="#020810",
            log_fg="#20e890",
            overlay_bg="#041018",
            panel_bg="#081820",
            panel_border="#20e890",
            target_bg="#081820",
            cards=CardArt(
                normal=("#0a2030", "#20e890", "#d0ffe8"),
                heal=("#082820", "#40ff90", "#d8ffe0"),
                heavy_hit=("#281808", "#ff8040", "#ffe8d0"),
                steal=("#180828", "#8040ff", "#ecd0ff"),
                disabled=("#101820", "#406060", "#608080"),
                selected=("#103028", "#60ffb0", "#e0fff0"),
            ),
            scale_hue=160 / 360,
            card_style="circuit",
            hud_active=("#103028", "#60ffb0", "#e0fff0"),
        )
    )

    presets.append(
        _build_theme(
            name="Stone Stronghold",
            font_path=DEFAULT_FONT_PATH if DEFAULT_FONT_PATH.exists() else None,
            font_family="Minecraft",
            screen_bg="#141412",
            win_bg="#283820",
            lose_bg="#502018",
            title_fg="#e0d8c8",
            body_fg="#b8b0a0",
            log_bg="#0c0c0a",
            log_fg="#c0b8a8",
            overlay_bg="#141412",
            panel_bg="#242220",
            panel_border="#908878",
            target_bg="#242220",
            cards=CardArt(
                normal=("#383430", "#a89878", "#f0ece0"),
                heal=("#283830", "#78a878", "#e0f0e0"),
                heavy_hit=("#483028", "#c08060", "#ffe8d8"),
                steal=("#383040", "#9888b0", "#ece8f0"),
                disabled=("#282824", "#686860", "#888880"),
                selected=("#484038", "#d0b870", "#fff8e0"),
            ),
            scale_hue=40 / 360,
            card_style="stone",
        )
    )

    presets.append(
        _build_theme(
            name="Crimson Colosseum",
            font_path=DEFAULT_FONT_PATH if DEFAULT_FONT_PATH.exists() else None,
            font_family="Minecraft",
            screen_bg="#180808",
            win_bg="#284818",
            lose_bg="#701010",
            title_fg="#ffb0a0",
            body_fg="#e89080",
            log_bg="#100404",
            log_fg="#ff7060",
            overlay_bg="#180808",
            panel_bg="#301010",
            panel_border="#ff5040",
            target_bg="#301010",
            cards=CardArt(
                normal=("#401818", "#ff6040", "#ffe8e0"),
                heal=("#183020", "#60c870", "#d8ffe0"),
                heavy_hit=("#501010", "#ff3020", "#ffd8d0"),
                steal=("#281830", "#c070e0", "#f0e0ff"),
                disabled=("#281818", "#705050", "#988080"),
                selected=("#502018", "#ffb060", "#fff0d8"),
            ),
            scale_hue=10 / 360,
            card_style="crimson",
            hud_active=("#502018", "#ffb060", "#fff0d8"),
        )
    )

    presets.append(
        _build_theme(
            name="Deep Ocean",
            font_path=DEFAULT_FONT_PATH if DEFAULT_FONT_PATH.exists() else None,
            font_family="Minecraft",
            screen_bg="#041018",
            win_bg="#0a3848",
            lose_bg="#381828",
            title_fg="#a0e8ff",
            body_fg="#70b8d8",
            log_bg="#020810",
            log_fg="#60c8f0",
            overlay_bg="#041018",
            panel_bg="#0a1828",
            panel_border="#4090c0",
            target_bg="#0a1828",
            cards=CardArt(
                normal=("#102838", "#4090c0", "#e0f4ff"),
                heal=("#082830", "#40c0a0", "#d8fff0"),
                heavy_hit=("#182838", "#60b0e0", "#e8f8ff"),
                steal=("#101838", "#7080e0", "#e8ecff"),
                disabled=("#101820", "#506070", "#7890a0"),
                selected=("#183848", "#80d8ff", "#f0fcff"),
            ),
            scale_hue=210 / 360,
            card_style="ocean",
            hud_active=("#183848", "#80d8ff", "#f0fcff"),
        )
    )

    presets.append(
        _build_theme(
            name="Sakura Garden",
            font_path=DEFAULT_FONT_PATH if DEFAULT_FONT_PATH.exists() else None,
            font_family="Minecraft",
            screen_bg="#181018",
            win_bg="#304830",
            lose_bg="#582838",
            title_fg="#ffd0e8",
            body_fg="#e8b0c8",
            log_bg="#100810",
            log_fg="#f090b8",
            overlay_bg="#181018",
            panel_bg="#281820",
            panel_border="#f080a8",
            target_bg="#281820",
            cards=CardArt(
                normal=("#382028", "#f080a8", "#fff0f4"),
                heal=("#203028", "#80d890", "#e8ffe8"),
                heavy_hit=("#402028", "#e07090", "#ffe8ec"),
                steal=("#282038", "#c090d8", "#f4ecff"),
                disabled=("#282028", "#806878", "#a89098"),
                selected=("#483030", "#ffb8d0", "#fff8fa"),
            ),
            scale_hue=330 / 360,
            card_style="sakura",
            hud_active=("#483030", "#ffb8d0", "#fff8fa"),
        )
    )

    presets.append(
        _build_theme(
            name="Midnight Jazz",
            font_path=DEFAULT_FONT_PATH if DEFAULT_FONT_PATH.exists() else None,
            font_family="Minecraft",
            screen_bg="#0c0818",
            win_bg="#1a3830",
            lose_bg="#481828",
            title_fg="#e0c878",
            body_fg="#b0a0c0",
            log_bg="#080410",
            log_fg="#c0a860",
            overlay_bg="#0c0818",
            panel_bg="#181028",
            panel_border="#c0a060",
            target_bg="#181028",
            cards=CardArt(
                normal=("#201830", "#c0a060", "#fff8e8"),
                heal=("#182820", "#70b880", "#e0f0e0"),
                heavy_hit=("#301820", "#d08070", "#ffe8e0"),
                steal=("#201830", "#a080d0", "#f0e8ff"),
                disabled=("#181820", "#605870", "#888898"),
                selected=("#302040", "#e8c870", "#fffae8"),
            ),
            scale_hue=270 / 360,
            card_style="jazz",
            hud_active=("#302040", "#e8c870", "#fffae8"),
        )
    )

    toxic_font = _theme_font("RobotoMono-Regular.ttf", "Minecraft")
    presets.append(
        _build_theme(
            name="Toxic Wasteland",
            font_path=toxic_font[0],
            font_family=toxic_font[1],
            screen_bg="#081008",
            win_bg="#183820",
            lose_bg="#402010",
            title_fg="#a0ff60",
            body_fg="#80c870",
            log_bg="#040804",
            log_fg="#80e840",
            overlay_bg="#081008",
            panel_bg="#101810",
            panel_border="#70d040",
            target_bg="#101810",
            cards=CardArt(
                normal=("#182018", "#70d040", "#e8ffd0"),
                heal=("#102818", "#50e060", "#d8ffe0"),
                heavy_hit=("#281808", "#e08030", "#ffe8c8"),
                steal=("#181820", "#9080e0", "#ece8ff"),
                disabled=("#141814", "#506050", "#708870"),
                selected=("#203018", "#a0ff70", "#f0ffe8"),
            ),
            scale_hue=100 / 360,
            card_style="toxic",
            hud_active=("#203018", "#a0ff70", "#f0ffe8"),
        )
    )

    presets.append(
        _build_theme(
            name="Solar Flare",
            font_path=DEFAULT_FONT_PATH if DEFAULT_FONT_PATH.exists() else None,
            font_family="Minecraft",
            screen_bg="#180c04",
            win_bg="#304818",
            lose_bg="#681810",
            title_fg="#ffe060",
            body_fg="#f0c080",
            log_bg="#100804",
            log_fg="#ffb040",
            overlay_bg="#180c04",
            panel_bg="#281808",
            panel_border="#ffa020",
            target_bg="#281808",
            cards=CardArt(
                normal=("#402010", "#ffa020", "#fff8d8"),
                heal=("#203018", "#70c060", "#e0ffe0"),
                heavy_hit=("#502008", "#ff6020", "#ffe8c0"),
                steal=("#301828", "#d080ff", "#f4e8ff"),
                disabled=("#281810", "#806050", "#a89078"),
                selected=("#503018", "#ffd040", "#ffffe8"),
            ),
            scale_hue=35 / 360,
            card_style="solar",
            hud_active=("#503018", "#ffd040", "#ffffe8"),
        )
    )

    presets.append(
        _build_theme(
            name="Arctic Aurora",
            font_path=DEFAULT_FONT_PATH if DEFAULT_FONT_PATH.exists() else None,
            font_family="Minecraft",
            screen_bg="#060818",
            win_bg="#103838",
            lose_bg="#382048",
            title_fg="#80ffe8",
            body_fg="#a0d8f0",
            log_bg="#040410",
            log_fg="#60f0d0",
            overlay_bg="#060818",
            panel_bg="#0c1020",
            panel_border="#40e8c8",
            target_bg="#0c1020",
            cards=CardArt(
                normal=("#101830", "#40e8c8", "#e8fffc"),
                heal=("#082820", "#60e890", "#e0ffe8"),
                heavy_hit=("#182030", "#80c0ff", "#f0f8ff"),
                steal=("#141830", "#a080ff", "#f0ecff"),
                disabled=("#101418", "#506870", "#789098"),
                selected=("#183040", "#80ffe8", "#f0ffff"),
            ),
            scale_hue=175 / 360,
            card_style="aurora",
            hud_active=("#183040", "#80ffe8", "#f0ffff"),
        )
    )

    presets.append(
        _build_theme(
            name="Ancient Ruins",
            font_path=DEFAULT_FONT_PATH if DEFAULT_FONT_PATH.exists() else None,
            font_family="Minecraft",
            screen_bg="#161410",
            win_bg="#303820",
            lose_bg="#502818",
            title_fg="#d8c8a8",
            body_fg="#b0a890",
            log_bg="#0c0a08",
            log_fg="#c0b090",
            overlay_bg="#161410",
            panel_bg="#242018",
            panel_border="#a89870",
            target_bg="#242018",
            cards=CardArt(
                normal=("#383028", "#a89870", "#f4f0e0"),
                heal=("#283028", "#789868", "#e4f0dc"),
                heavy_hit=("#483020", "#c08858", "#ffe8d0"),
                steal=("#302830", "#9888a8", "#f0ecf4"),
                disabled=("#242018", "#686058", "#888078"),
                selected=("#484030", "#e0c878", "#fffae8"),
            ),
            scale_hue=38 / 360,
            card_style="ruins",
            hud_active=("#484030", "#e0c878", "#fffae8"),
        )
    )

    void_font = _theme_font("Creepster-Regular.ttf", "Minecraft")
    presets.append(
        _build_theme(
            name="Digital Void",
            font_path=void_font[0],
            font_family=void_font[1],
            screen_bg="#020204",
            win_bg="#102820",
            lose_bg="#300818",
            title_fg="#8080ff",
            body_fg="#6060a0",
            log_bg="#010102",
            log_fg="#6060e0",
            overlay_bg="#020204",
            panel_bg="#080810",
            panel_border="#5050c0",
            target_bg="#080810",
            cards=CardArt(
                normal=("#0c0c18", "#5050c0", "#e8e8ff"),
                heal=("#081810", "#408060", "#d8f0e0"),
                heavy_hit=("#180810", "#c05080", "#ffe8f0"),
                steal=("#100818", "#8060c0", "#f0e8ff"),
                disabled=("#080810", "#404058", "#606070"),
                selected=("#181028", "#7070e0", "#f0f0ff"),
            ),
            scale_hue=240 / 360,
            card_style="void",
            hud_active=("#181028", "#7070e0", "#f0f0ff"),
        )
    )

    carnival_font = _theme_font("PressStart2P-Regular.ttf", "Minecraft")
    presets.append(
        _build_theme(
            name="Candy Carnival",
            font_path=carnival_font[0],
            font_family=carnival_font[1],
            screen_bg="#201018",
            win_bg="#386830",
            lose_bg="#883048",
            title_fg="#ff90c0",
            body_fg="#ffb0d0",
            log_bg="#180810",
            log_fg="#ff80b0",
            overlay_bg="#201018",
            panel_bg="#301828",
            panel_border="#ff70a8",
            target_bg="#301828",
            cards=CardArt(
                normal=("#402030", "#ff70a8", "#fff0f6"),
                heal=("#204030", "#70e890", "#e8ffe8"),
                heavy_hit=("#502028", "#ff5080", "#ffe8ee"),
                steal=("#302040", "#c080ff", "#f4ecff"),
                disabled=("#282028", "#806878", "#a89098"),
                selected=("#503040", "#ffa0c8", "#fff8fa"),
            ),
            scale_hue=320 / 360,
            card_style="candy",
            hud_active=("#503040", "#ffa0c8", "#fff8fa"),
        )
    )

    presets.append(
        _build_theme(
            name="Minecraft Village",
            font_path=DEFAULT_FONT_PATH if DEFAULT_FONT_PATH.exists() else None,
            font_family="Minecraft",
            # Daylight sky matching the village reference art
            screen_bg="#7eb8dc",
            win_bg="#3d8c3a",
            lose_bg="#8b3a2a",
            title_fg="#2f5d2c",
            body_fg="#3a4a30",
            log_bg="#5a9cc0",
            log_fg="#1e3a18",
            overlay_bg="#7eb8dc",
            panel_bg="#9ad070",
            panel_border="#6b4f2a",
            target_bg="#a8d878",
            cards=CardArt(
                # Classic grass-block greens + dirt browns
                normal=("#5aaf3a", "#8b6b3d", "#f4ffe8"),
                heal=("#3d9c48", "#6ecf6a", "#e8ffe8"),
                heavy_hit=("#7a4a28", "#c07040", "#fff0d8"),
                steal=("#4a8c38", "#9a7850", "#f8ffe8"),
                disabled=("#6a7a58", "#8a9078", "#c8d0b8"),
                selected=("#6ecf4a", "#c4a060", "#fffff0"),
            ),
            scale_hue=110 / 360,
            card_style="village",
            hud_active=("#4a8c38", "#e8c060", "#fffff0"),
            hud_idle=("#9ad070", "#6b4f2a", "#2f5d2c"),
            target_self=("#4a8c38", "#e8c060", "#fffff0"),
            target_other=("#a8d878", "#6b4f2a", "#2f5d2c"),
        )
    )

    presets.append(
        _build_theme(
            name="Desert Mirage",
            font_path=DEFAULT_FONT_PATH if DEFAULT_FONT_PATH.exists() else None,
            font_family="Minecraft",
            screen_bg="#20140a",
            win_bg="#405020",
            lose_bg="#682818",
            title_fg="#ffe0a0",
            body_fg="#d8b878",
            log_bg="#140c06",
            log_fg="#f0c878",
            overlay_bg="#20140a",
            panel_bg="#302010",
            panel_border="#d89840",
            target_bg="#302010",
            cards=CardArt(
                normal=("#403018", "#d89840", "#fff0d0"),
                heal=("#283820", "#88b858", "#e8ffd8"),
                heavy_hit=("#502018", "#e06030", "#ffe0c8"),
                steal=("#302038", "#b080c0", "#f4e8ff"),
                disabled=("#282018", "#786850", "#a89878"),
                selected=("#584020", "#ffc858", "#fff8e0"),
            ),
            scale_hue=35 / 360,
            card_style="ruins",
            hud_active=("#584020", "#ffc858", "#fff8e0"),
        )
    )

    presets.append(
        _build_theme(
            name="Moonlit Library",
            font_path=DEFAULT_FONT_PATH if DEFAULT_FONT_PATH.exists() else None,
            font_family="Minecraft",
            screen_bg="#0c1020",
            win_bg="#183840",
            lose_bg="#482038",
            title_fg="#d8d0ff",
            body_fg="#a8b0d8",
            log_bg="#080c18",
            log_fg="#b0c8ff",
            overlay_bg="#0c1020",
            panel_bg="#181830",
            panel_border="#8880c8",
            target_bg="#181830",
            cards=CardArt(
                normal=("#202040", "#8880c8", "#f0ecff"),
                heal=("#183830", "#60c8a0", "#e0fff0"),
                heavy_hit=("#382038", "#e078a0", "#ffe8f0"),
                steal=("#282040", "#a890e0", "#f0e8ff"),
                disabled=("#181820", "#606078", "#9090a8"),
                selected=("#303050", "#c0b0ff", "#fffaff"),
            ),
            scale_hue=255 / 360,
            card_style="shadow",
            hud_active=("#303050", "#c0b0ff", "#fffaff"),
        )
    )

    presets.append(
        _build_theme(
            name="Coral Reef",
            font_path=DEFAULT_FONT_PATH if DEFAULT_FONT_PATH.exists() else None,
            font_family="Minecraft",
            screen_bg="#062028",
            win_bg="#105040",
            lose_bg="#582830",
            title_fg="#90fff0",
            body_fg="#90d8d0",
            log_bg="#041820",
            log_fg="#70f0d8",
            overlay_bg="#062028",
            panel_bg="#0c3038",
            panel_border="#40d8c0",
            target_bg="#0c3038",
            cards=CardArt(
                normal=("#104048", "#40d8c0", "#e0fff8"),
                heal=("#104030", "#60e890", "#e0fff0"),
                heavy_hit=("#482028", "#ff8068", "#fff0e8"),
                steal=("#182848", "#80a8f0", "#ecf4ff"),
                disabled=("#142428", "#507078", "#90a8a8"),
                selected=("#185058", "#70fff0", "#f0fffc"),
            ),
            scale_hue=175 / 360,
            card_style="ocean",
            hud_active=("#185058", "#70fff0", "#f0fffc"),
        )
    )

    presets.append(
        _build_theme(
            name="Bubblegum Arcade",
            font_path=arcade_font[0],
            font_family=arcade_font[1],
            screen_bg="#180c28",
            win_bg="#205038",
            lose_bg="#702050",
            title_fg="#ffb8f0",
            body_fg="#d8a8f0",
            log_bg="#100820",
            log_fg="#ff80d8",
            overlay_bg="#180c28",
            panel_bg="#281438",
            panel_border="#ff70c8",
            target_bg="#281438",
            cards=CardArt(
                normal=("#381840", "#ff70c8", "#fff0fc"),
                heal=("#183830", "#60e8a0", "#e0fff0"),
                heavy_hit=("#481828", "#ff5880", "#ffe8f0"),
                steal=("#281848", "#b880ff", "#f4eaff"),
                disabled=("#241828", "#786080", "#a890a8"),
                selected=("#482050", "#ffc0f0", "#fffaff"),
            ),
            scale_hue=315 / 360,
            card_style="candy",
            hud_active=("#482050", "#ffc0f0", "#fffaff"),
        )
    )

    return presets


CREATIVE_THEMES: list[GameTheme] = creative_theme_presets()


def _discover_fonts() -> list[Path]:
    if not FONT_DIR.exists():
        return [DEFAULT_FONT_PATH] if DEFAULT_FONT_PATH.exists() else []
    fonts = sorted(
        p
        for p in FONT_DIR.iterdir()
        if p.suffix.lower() in {".ttf", ".otf"} and p.name.lower() != "desktop.ini"
    )
    if DEFAULT_FONT_PATH.exists() and DEFAULT_FONT_PATH not in fonts:
        fonts.insert(0, DEFAULT_FONT_PATH)
    return fonts or ([DEFAULT_FONT_PATH] if DEFAULT_FONT_PATH.exists() else [])


def generate_random_theme(rng: random.Random | None = None) -> GameTheme:
    rng = rng or random.Random()
    fonts = _discover_fonts()
    font_path = rng.choice(fonts) if fonts else None
    if font_path and font_path.exists():
        _register_font_file(font_path)
        font_family = _read_font_family(font_path)
    else:
        font_family = "Minecraft"

    hue = rng.random()
    accent_hue = (hue + rng.uniform(0.12, 0.35)) % 1.0
    heal_hue = (hue + 0.33) % 1.0
    steal_hue = (hue + 0.62) % 1.0
    heavy_hue = (hue + 0.08) % 1.0
    poison_hue = 0.78  # purple/violet band

    screen_bg = _hsl_to_hex(hue, rng.uniform(0.18, 0.35), rng.uniform(0.08, 0.16))
    title_fg = _hsl_to_hex(hue, rng.uniform(0.15, 0.35), rng.uniform(0.82, 0.92))
    body_fg = _hsl_to_hex(hue, rng.uniform(0.12, 0.28), rng.uniform(0.68, 0.78))
    log_bg = _hsl_to_hex(hue, rng.uniform(0.2, 0.4), rng.uniform(0.05, 0.12))
    log_fg = _hsl_to_hex(accent_hue, rng.uniform(0.35, 0.55), rng.uniform(0.72, 0.85))
    panel_bg = _shift_hex(screen_bg, 14)
    panel_border = _hsl_to_hex(accent_hue, rng.uniform(0.25, 0.45), rng.uniform(0.62, 0.72))

    cards = CardArt(
        normal=_card_triplet(accent_hue, rng.uniform(0.28, 0.5), 0.22, 0.58, 0.88),
        heal=_card_triplet(heal_hue, rng.uniform(0.35, 0.55), 0.18, 0.52, 0.9),
        heavy_hit=_card_triplet(heavy_hue, rng.uniform(0.4, 0.6), 0.2, 0.55, 0.9),
        steal=_card_triplet(steal_hue, rng.uniform(0.3, 0.5), 0.18, 0.52, 0.9),
        disabled=_card_triplet(hue, 0.12, 0.16, 0.38, 0.52),
        selected=_card_triplet(accent_hue, rng.uniform(0.35, 0.55), 0.28, 0.62, 0.92),
        poison=_card_triplet(poison_hue, rng.uniform(0.45, 0.65), 0.16, 0.58, 0.92),
    )
    hud_active = _card_triplet(accent_hue, rng.uniform(0.35, 0.55), 0.28, 0.62, 0.92)
    hud_idle = (
        _shift_hex(screen_bg, 18),
        _hsl_to_hex(hue, 0.12, 0.55),
        _hsl_to_hex(hue, 0.12, 0.72),
    )

    style = rng.choice(CARD_STYLES)

    return _build_theme(
        name=f"Random ({style})",
        font_path=font_path,
        font_family=font_family,
        screen_bg=screen_bg,
        win_bg=_hsl_to_hex(0.33, rng.uniform(0.35, 0.55), rng.uniform(0.22, 0.32)),
        lose_bg=_hsl_to_hex(0.02, rng.uniform(0.45, 0.65), rng.uniform(0.24, 0.34)),
        title_fg=title_fg,
        body_fg=body_fg,
        log_bg=log_bg,
        log_fg=log_fg,
        overlay_bg=screen_bg,
        panel_bg=panel_bg,
        panel_border=panel_border,
        target_bg=panel_bg,
        cards=cards,
        scale_hue=heal_hue,
        hud_active=hud_active,
        hud_idle=hud_idle,
        hud_dead=cards.disabled,
        target_self=hud_active,
        target_other=(
            _shift_hex(screen_bg, 12),
            panel_border,
            title_fg,
        ),
        card_style=style,
    )


def pick_creative_theme(rng: random.Random | None = None) -> GameTheme:
    rng = rng or random.Random()
    return rng.choice(CREATIVE_THEMES)


def all_selectable_themes() -> list[GameTheme]:
    """Default + every hand-crafted creative theme (stable order for the picker)."""
    return [default_theme(), *CREATIVE_THEMES]


def theme_names() -> list[str]:
    return [t.name for t in all_selectable_themes()]


def find_theme_by_name(name: str) -> GameTheme | None:
    needle = name.strip().lower()
    for theme in all_selectable_themes():
        if theme.name.lower() == needle:
            return theme
    return None


def apply_theme_by_name(name: str) -> GameTheme | None:
    theme = find_theme_by_name(name)
    if theme is None:
        return None
    set_active_theme(theme)
    return theme


_ACTIVE: GameTheme = default_theme()


def _triplet_to_list(rgb: tuple[str, str, str]) -> list[str]:
    return [rgb[0], rgb[1], rgb[2]]


def _triplet_from_list(raw: Any, fallback: tuple[str, str, str]) -> tuple[str, str, str]:
    if not isinstance(raw, (list, tuple)) or len(raw) != 3:
        return fallback
    return (str(raw[0]), str(raw[1]), str(raw[2]))


def theme_to_dict(theme: GameTheme) -> dict[str, Any]:
    return {
        "name": theme.name,
        "font_path": str(theme.font_path) if theme.font_path else None,
        "font_family": theme.font_family,
        "screen_bg": theme.screen_bg,
        "win_bg": theme.win_bg,
        "lose_bg": theme.lose_bg,
        "title_fg": theme.title_fg,
        "body_fg": theme.body_fg,
        "log_bg": theme.log_bg,
        "log_fg": theme.log_fg,
        "overlay_bg": theme.overlay_bg,
        "panel_bg": theme.panel_bg,
        "panel_border": theme.panel_border,
        "target_bg": theme.target_bg,
        "hud_active": _triplet_to_list(theme.hud_active),
        "hud_idle": _triplet_to_list(theme.hud_idle),
        "hud_dead": _triplet_to_list(theme.hud_dead),
        "target_self": _triplet_to_list(theme.target_self),
        "target_other": _triplet_to_list(theme.target_other),
        "scale_trough": theme.scale_trough,
        "scale_fill": theme.scale_fill,
        "scale_border": theme.scale_border,
        "scale_light": theme.scale_light,
        "scale_dark": theme.scale_dark,
        "card_style": theme.card_style,
        "cards": {
            "normal": _triplet_to_list(theme.cards.normal),
            "heal": _triplet_to_list(theme.cards.heal),
            "heavy_hit": _triplet_to_list(theme.cards.heavy_hit),
            "steal": _triplet_to_list(theme.cards.steal),
            "disabled": _triplet_to_list(theme.cards.disabled),
            "selected": _triplet_to_list(theme.cards.selected),
            "poison": _triplet_to_list(theme.cards.poison),
        },
    }


def theme_from_dict(data: dict[str, Any]) -> GameTheme | None:
    try:
        style = str(data.get("card_style") or "pixel")
        if style not in CARD_STYLES:
            style = "pixel"
        cards_raw = data.get("cards") or {}
        if not isinstance(cards_raw, dict):
            return None
        blank = ("#333333", "#666666", "#ffffff")
        cards = CardArt(
            normal=_triplet_from_list(cards_raw.get("normal"), blank),
            heal=_triplet_from_list(cards_raw.get("heal"), blank),
            heavy_hit=_triplet_from_list(cards_raw.get("heavy_hit"), blank),
            steal=_triplet_from_list(cards_raw.get("steal"), blank),
            disabled=_triplet_from_list(cards_raw.get("disabled"), blank),
            selected=_triplet_from_list(cards_raw.get("selected"), blank),
            poison=_triplet_from_list(cards_raw.get("poison"), DEFAULT_POISON_ART),
        )
        font_raw = data.get("font_path")
        font_path = Path(str(font_raw)) if font_raw else None
        if font_path is not None and not font_path.exists():
            font_path = DEFAULT_FONT_PATH if DEFAULT_FONT_PATH.exists() else None
        return GameTheme(
            name=str(data.get("name") or "Saved Theme"),
            font_path=font_path,
            font_family=str(data.get("font_family") or "Minecraft"),
            screen_bg=str(data.get("screen_bg") or "#1a1a1a"),
            win_bg=str(data.get("win_bg") or "#1a3a24"),
            lose_bg=str(data.get("lose_bg") or "#3a1a1a"),
            title_fg=str(data.get("title_fg") or "#f0f0f0"),
            body_fg=str(data.get("body_fg") or "#c8c8c8"),
            log_bg=str(data.get("log_bg") or "#101010"),
            log_fg=str(data.get("log_fg") or "#d0d0d0"),
            overlay_bg=str(data.get("overlay_bg") or "#000000"),
            panel_bg=str(data.get("panel_bg") or "#222222"),
            panel_border=str(data.get("panel_border") or "#888888"),
            target_bg=str(data.get("target_bg") or "#1a1a1a"),
            hud_active=_triplet_from_list(data.get("hud_active"), blank),
            hud_idle=_triplet_from_list(data.get("hud_idle"), blank),
            hud_dead=_triplet_from_list(data.get("hud_dead"), blank),
            target_self=_triplet_from_list(data.get("target_self"), blank),
            target_other=_triplet_from_list(data.get("target_other"), blank),
            scale_trough=str(data.get("scale_trough") or "#333333"),
            scale_fill=str(data.get("scale_fill") or "#66aa66"),
            scale_border=str(data.get("scale_border") or "#444444"),
            scale_light=str(data.get("scale_light") or "#88cc88"),
            scale_dark=str(data.get("scale_dark") or "#226622"),
            cards=cards,
            card_style=style,  # type: ignore[arg-type]
        )
    except (TypeError, ValueError, KeyError):
        return None


def save_theme_preference(theme: GameTheme | None = None) -> None:
    """Persist the active theme so it restores on next launch."""
    theme = theme or _ACTIVE
    payload = {
        "theme_name": theme.name,
        "theme": theme_to_dict(theme),
    }
    try:
        PREFS_PATH.parent.mkdir(parents=True, exist_ok=True)
        PREFS_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except OSError:
        pass


def restore_theme_preference() -> GameTheme:
    """Load the last saved theme, or fall back to Default."""
    try:
        try:
            raw = PREFS_PATH.read_text(encoding="utf-8")
        except OSError:
            raw = LEGACY_PREFS_PATH.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        theme = default_theme()
        set_active_theme(theme)
        return theme

    if not isinstance(data, dict):
        theme = default_theme()
        set_active_theme(theme)
        return theme

    name = str(data.get("theme_name") or "").strip()
    named = find_theme_by_name(name) if name else None
    # Named presets reload from code so palette tweaks still apply.
    if named is not None and not name.lower().startswith("random"):
        set_active_theme(named)
        return named

    snap = data.get("theme")
    if isinstance(snap, dict):
        theme = theme_from_dict(snap)
        if theme is not None:
            set_active_theme(theme)
            return theme

    if named is not None:
        set_active_theme(named)
        return named

    theme = default_theme()
    set_active_theme(theme)
    return theme


def active_theme() -> GameTheme:
    return _ACTIVE


def set_active_theme(theme: GameTheme, *, persist: bool = True) -> None:
    global _ACTIVE
    if theme.font_path and theme.font_path.exists():
        _register_font_file(theme.font_path)
    _ACTIVE = theme
    try:
        from crash_out_sfx import set_sfx_theme

        set_sfx_theme(theme.card_style, theme.name)
    except Exception:
        pass
    if persist:
        save_theme_preference(theme)


def reset_theme() -> GameTheme:
    theme = default_theme()
    set_active_theme(theme)
    return theme


def randomize_theme(rng: random.Random | None = None) -> GameTheme:
    rng = rng or random.Random()
    theme = pick_creative_theme(rng) if rng.random() < 0.85 else generate_random_theme(rng)
    set_active_theme(theme)
    return theme
