#!/usr/bin/env python3
"""Crash Out — window (tkinter) UI."""

from __future__ import annotations

import json
import math
import os
import random
import re
import socket
import subprocess
import sys
import tkinter as tk
import time
import webbrowser
from collections.abc import Callable
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from urllib.parse import urlencode, urlsplit
from urllib.request import urlopen

PROJECT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = (
    PROJECT_DIR.parent / "Crash out"
    if PROJECT_DIR.name.casefold() == "pbl"
    else PROJECT_DIR
)
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from PIL import Image, ImageTk

    HAS_PIL = True
except ImportError:
    HAS_PIL = False

from CrashOut_Resources import (
    BOT_NAME,
    DEFAULT_POWER_POINTS,
    DEFAULT_STARTING_HP,
    DECK_SIZE,
    DECK_SIZE_MAX,
    DECK_SIZE_MIN,
    FIFTH_CARD_HEAL,
    HP_MAX,
    HP_MIN,
    MatchSettings,
    MAX_UNIQUE_CARDS_IN_DECK,
    PLAYER_COUNT_MAX,
    PP_MAX,
    PP_MIN,
    STEAL_PP_COST,
    TURN_DELAY_MS,
    ActiveBorrow,
    Card,
    Player,
    allows_duplicate_archetypes,
    archetype_taken,
    bot_choose_play,
    build_deck_export,
    card_archetype,
    can_add_heavy_hit_card,
    can_add_poison_card,
    can_add_shield_card,
    can_add_steal_card,
    can_add_vampire_card,
    can_craft_steal,
    card_is_cooling,
    check_winner,
    clamp_deck_size,
    craft_card,
    deck_has_heavy_hit,
    deck_has_poison,
    deck_has_shield,
    deck_has_steal,
    deck_has_vampire,
    default_decks_dir,
    describe_target,
    load_deck_file,
    make_bot_deck,
    make_mercy_card,
    make_players_from_mixed_decks,
    make_solo_players,
    mark_card_played,
    name_for_split,
    next_alive_index,
    resolve_card,
    resolve_steal,
    return_expired_borrows,
    save_deck_file,
    stat_budget,
    tick_poisons_on_turn_start,
    tick_reaper_marks,
    tick_turn_cooldowns,
    unique_card_total,
    validate_deck_export,
)
from crash_out_themes import (
    active_theme,
    apply_theme_by_name,
    randomize_theme,
    reset_theme,
    restore_theme_preference,
    save_theme_preference,
    theme_names,
)
from crash_out_pixel_bg import generate_theme_wallpaper
from crash_out_party import (
    BOARD_HEIGHT,
    BOARD_WIDTH,
    TETROMINOES,
    apply_placement,
    clear_completed_rows,
    conflict_groups,
    legal_positions,
    place_piece,
    rank_points,
    rotations,
    starting_tiles,
)
from crash_out_sfx import (
    SFX_CARD_PICK,
    SFX_CRAFT,
    SFX_DEAL,
    SFX_DENY,
    SFX_LOSE,
    SFX_MATCH_START,
    SFX_MERCY_ADD,
    SFX_THEME_CHANGE,
    SFX_TURN_START,
    SFX_UI_CLICK,
    SFX_WIN,
    get_bgm_volume,
    play_card_play_sfx,
    play_sfx,
    set_bgm_volume,
    set_sfx_muted,
    shutdown_audio,
    start_bgm,
    stop_bgm,
)

# Playing-card style buttons: width:height = 5:7
CARD_ASPECT = 7 / 5
CARD_MIN_W = 48
CARD_MAX_W = 200
CARD_GAP_MIN = 6
TARGET_MIN = 100
TARGET_MAX = 200
LOG_CLOSE_SIZE = 40
PREVIEW_CARD_W = 168
DECK_MINI_W = 78
UNIQUE_PICK_W = 120
UNIQUE_PICK_H = 168
BOT_ICON_PATH = PROJECT_ROOT / "assets" / "bot_icon.png"

UPDATE_HISTORY = (
    (
        "Update 1",
        (
            "Removed Joker and Cloak cards.",
            "Freeze lasts 3 turns, does not stack, and no longer skips the frozen player's turn.",
            "While frozen, a player can use cards; damage dealt or received and healing are halved.",
            "Freeze cannot be used while the player has a lava-marked card.",
            "Shield does not activate or block damage while its owner is frozen.",
            "Shield cards no longer heal.",
        ),
    ),
)


def format_elapsed_time(elapsed_seconds: float) -> str:
    """Format a match duration as mm:ss or hh:mm:ss."""
    total_seconds = max(0, int(elapsed_seconds))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


def _theme():
    return active_theme()


def _font_family() -> str:
    return _theme().font_family


def card_size_for_area(
    area_w: int,
    area_h: int,
    num_cards: int,
    *,
    pad_x: int = 12,
    pad_y: int = 12,
    columns: int | None = None,
    rows: int = 1,
) -> tuple[int, int]:
    """Fit cards in area while keeping 5:7 aspect ratio (optional grid)."""
    if num_cards <= 0 or area_w < CARD_MIN_W or area_h < CARD_MIN_W:
        return CARD_MIN_W, int(CARD_MIN_W * CARD_ASPECT)

    cols = max(1, columns if columns is not None else num_cards)
    rows = max(1, rows)
    gap = max(CARD_GAP_MIN, area_w // 80)
    vgap = gap
    avail_w = max(CARD_MIN_W, area_w - pad_x * 2 - gap * max(0, cols - 1))
    avail_h = max(CARD_MIN_W, area_h - pad_y * 2 - vgap * max(0, rows - 1))

    card_w = min(CARD_MAX_W, avail_w // cols)
    card_h = int(card_w * CARD_ASPECT)
    max_h = avail_h // rows
    if card_h > max_h:
        card_h = max_h
        card_w = int(card_h / CARD_ASPECT)

    card_w = max(CARD_MIN_W, min(CARD_MAX_W, card_w))
    card_h = int(card_w * CARD_ASPECT)
    if card_h > max_h:
        card_h = max(int(CARD_MIN_W * CARD_ASPECT), max_h)
        card_w = int(card_h / CARD_ASPECT)
    return card_w, card_h


def target_size_for_area(area_w: int, area_h: int, num_targets: int) -> tuple[int, int]:
    """Square target buttons that fit in the overlay panel."""
    if num_targets <= 0:
        return TARGET_MIN, CARD_GAP_MIN
    gap = max(CARD_GAP_MIN, area_w // 60)
    avail_w = max(TARGET_MIN, area_w - 48 - gap * max(0, num_targets - 1))
    avail_h = max(TARGET_MIN, area_h - 80)
    size = min(TARGET_MAX, avail_w // num_targets, avail_h)
    return max(TARGET_MIN, size), gap


def _shift_hex(color: str, delta: int) -> str:
    raw = color.lstrip("#")
    rgb = [max(0, min(255, int(raw[i : i + 2], 16) + delta)) for i in (0, 2, 4)]
    return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"


def _pixel_scale(size: int) -> int:
    return max(2, size // 28)


def _mc_font_size(size: int) -> int:
    """Minecraft bitmap fonts stay crisp on an 8px grid."""
    return max(8, int(round(size / 8) * 8))


def _px_rect(canvas: tk.Canvas, x1: int, y1: int, x2: int, y2: int, color: str) -> None:
    """Filled axis-aligned block — the only fill primitive for card art."""
    if x2 <= x1 or y2 <= y1:
        return
    canvas.create_rectangle(x1, y1, x2, y2, fill=color, outline="", width=0)


def _px_frame(canvas: tk.Canvas, x1: int, y1: int, x2: int, y2: int, color: str, s: int) -> None:
    """1-block-thick rectangular border made of four rects (no outline antialiasing)."""
    s = max(1, s)
    _px_rect(canvas, x1, y1, x2, y1 + s, color)
    _px_rect(canvas, x1, y2 - s, x2, y2, color)
    _px_rect(canvas, x1, y1, x1 + s, y2, color)
    _px_rect(canvas, x2 - s, y1, x2, y2, color)


def _px_block(canvas: tk.Canvas, x: int, y: int, s: int, color: str) -> None:
    _px_rect(canvas, x, y, x + s, y + s, color)


def _px_line(
    canvas: tk.Canvas, x0: int, y0: int, x1: int, y1: int, s: int, color: str
) -> None:
    """Bresenham line as s×s pixel blocks (snapped to the scale grid)."""
    s = max(1, s)
    x0, y0 = (x0 // s) * s, (y0 // s) * s
    x1, y1 = (x1 // s) * s, (y1 // s) * s
    dx = abs(x1 - x0)
    dy = abs(y1 - y0)
    sx = s if x0 < x1 else -s
    sy = s if y0 < y1 else -s
    err = dx - dy
    x, y = x0, y0
    for _ in range((dx + dy) // s + 3):
        _px_block(canvas, x, y, s, color)
        if x == x1 and y == y1:
            break
        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            x += sx
        if e2 < dx:
            err += dx
            y += sy


def _px_disk(canvas: tk.Canvas, cx: int, cy: int, r: int, s: int, color: str) -> None:
    """Filled circle approximated on an s-pixel grid."""
    s = max(1, s)
    r = max(s, (r // s) * s)
    rr = r * r
    y = -r
    while y <= r:
        x = -r
        while x <= r:
            if x * x + y * y <= rr:
                _px_block(canvas, cx + x, cy + y, s, color)
            x += s
        y += s


def _px_ring(canvas: tk.Canvas, cx: int, cy: int, r: int, s: int, color: str) -> None:
    """1-block-thick circle outline on an s-pixel grid."""
    s = max(1, s)
    r = max(s, (r // s) * s)
    outer = r * r
    inner = max(0, r - s) ** 2
    y = -r
    while y <= r:
        x = -r
        while x <= r:
            d = x * x + y * y
            if inner < d <= outer:
                _px_block(canvas, cx + x, cy + y, s, color)
            x += s
        y += s


def _px_diamond(
    canvas: tk.Canvas, cx: int, cy: int, mark: int, s: int, fill: str, outline: str
) -> None:
    """Stepped diamond (card-back mark) built from blocks."""
    s = max(1, s)
    mark = max(s, (mark // s) * s)
    y = -mark
    while y <= mark:
        half = mark - abs(y)
        _px_rect(canvas, cx - half, cy + y, cx + half + s, cy + y + s, fill)
        y += s
    # Outline edge
    for t in range(0, mark + s, s):
        _px_block(canvas, cx - mark + t, cy - t, s, outline)
        _px_block(canvas, cx + mark - t, cy - t, s, outline)
        _px_block(canvas, cx - mark + t, cy + t, s, outline)
        _px_block(canvas, cx + mark - t, cy + t, s, outline)


def _px_arc_top(
    canvas: tk.Canvas, x1: int, y_base: int, width: int, height: int, s: int, color: str
) -> None:
    """Pixel semicircle arch (top half) for colosseum-style frames."""
    s = max(1, s)
    cx = x1 + width // 2
    cy = y_base
    rx = max(s, (width // 2 // s) * s)
    ry = max(s, (height // s) * s)
    x = -rx
    while x <= rx:
        # Ellipse: (x/rx)^2 + (y/ry)^2 <= 1, take top edge only
        xn = x / max(1, rx)
        y_off = int(ry * math.sqrt(max(0.0, 1.0 - xn * xn)))
        y_off = (y_off // s) * s
        _px_block(canvas, cx + x, cy - y_off, s, color)
        x += s


def _draw_pixel_panel(
    canvas: tk.Canvas,
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    fill: str,
    accent: str,
    scale: int,
) -> None:
    """Minecraft-style beveled panel with 1-pixel corner cuts."""
    s = scale
    highlight = _shift_hex(fill, 38)
    shadow = _shift_hex(fill, -40)
    outline = _shift_hex(accent, -50)

    _px_rect(canvas, x1 + s, y1, x2 - s, y2, fill)
    _px_rect(canvas, x1, y1 + s, x2, y2 - s, fill)

    _px_rect(canvas, x1 + s, y1, x2 - s, y1 + s, outline)
    _px_rect(canvas, x1 + s, y2 - s, x2 - s, y2, outline)
    _px_rect(canvas, x1, y1 + s, x1 + s, y2 - s, outline)
    _px_rect(canvas, x2 - s, y1 + s, x2, y2 - s, outline)

    _px_rect(canvas, x1 + s, y1 + s, x2 - s, y1 + 2 * s, highlight)
    _px_rect(canvas, x1 + s, y1 + s, x1 + 2 * s, y2 - s, highlight)
    _px_rect(canvas, x1 + s, y2 - 2 * s, x2 - s, y2 - s, shadow)
    _px_rect(canvas, x2 - 2 * s, y1 + s, x2 - s, y2 - s, shadow)

    inner = 3 * s
    ix1, iy1, ix2, iy2 = x1 + inner, y1 + inner, x2 - inner, y2 - inner
    if ix2 - ix1 > 4 * s and iy2 - iy1 > 4 * s:
        _px_rect(canvas, ix1 + s, iy1, ix2 - s, iy1 + s, accent)
        _px_rect(canvas, ix1 + s, iy2 - s, ix2 - s, iy2, accent)
        _px_rect(canvas, ix1, iy1 + s, ix1 + s, iy2 - s, accent)
        _px_rect(canvas, ix2 - s, iy1 + s, ix2, iy2 - s, accent)


def _draw_neon_card(
    canvas: tk.Canvas, x1: int, y1: int, x2: int, y2: int, fill: str, accent: str, scale: int
) -> None:
    s = max(2, scale)
    _px_rect(canvas, x1, y1, x2, y2, fill)
    for inset, color in ((0, accent), (s, _shift_hex(accent, 40)), (2 * s, _shift_hex(accent, -35))):
        _px_frame(canvas, x1 + inset, y1 + inset, x2 - inset, y2 - inset, color, s)
    arm = 5 * s
    for px, py, dx, dy in (
        (x1 + s, y1 + s, 1, 1),
        (x2 - 2 * s, y1 + s, -1, 1),
        (x1 + s, y2 - 2 * s, 1, -1),
        (x2 - 2 * s, y2 - 2 * s, -1, -1),
    ):
        if dx > 0:
            _px_rect(canvas, px, py, px + arm, py + s, accent)
        else:
            _px_rect(canvas, px - arm + s, py, px + s, py + s, accent)
        if dy > 0:
            _px_rect(canvas, px, py, px + s, py + arm, accent)
        else:
            _px_rect(canvas, px, py - arm + s, px + s, py + s, accent)


def _draw_stone_card(
    canvas: tk.Canvas, x1: int, y1: int, x2: int, y2: int, fill: str, accent: str, scale: int
) -> None:
    s = max(2, scale)
    mortar = _shift_hex(accent, -55)
    _px_rect(canvas, x1, y1, x2, y2, mortar)
    _px_frame(canvas, x1, y1, x2, y2, _shift_hex(accent, -40), s)
    row_h = max(3, 3 * s)
    row = 0
    y = y1 + s
    while y < y2 - s:
        offset = (row % 2) * (4 * s)
        x = x1 + s + offset
        while x < x2 - s:
            bw = min(7 * s, x2 - s - x)
            bh = min(row_h - s, y2 - s - y)
            brick = _shift_hex(fill, 10 if row % 2 else -10)
            _px_rect(canvas, x, y, x + bw, y + bh, brick)
            x += 8 * s
        y += row_h
        row += 1


def _draw_ice_card(
    canvas: tk.Canvas, x1: int, y1: int, x2: int, y2: int, fill: str, accent: str, scale: int
) -> None:
    s = max(2, scale)
    _px_rect(canvas, x1, y1, x2, y2, fill)
    _px_frame(canvas, x1, y1, x2, y2, accent, s)
    frost = _shift_hex(accent, 50)
    step = max(2, 3 * s)
    d = y2 - y1
    i = x1 - d
    while i < x2 + d:
        _px_line(canvas, i, y1 + s, i + d, y2 - s, s, frost)
        i += step
    _px_rect(canvas, x1 + s, y1 + s, x2 - s, y1 + 2 * s, "#ffffff")


def _draw_lava_card(
    canvas: tk.Canvas, x1: int, y1: int, x2: int, y2: int, fill: str, accent: str, scale: int
) -> None:
    s = max(2, scale)
    _px_rect(canvas, x1, y1, x2, y2, fill)
    _px_frame(canvas, x1, y1, x2, y2, _shift_hex(accent, -30), s)
    w, h = x2 - x1, y2 - y1
    cracks = (
        (x1 + 3 * s, y1 + 4 * s, x1 + w // 2, y1 + h // 3),
        (x1 + w // 2, y1 + h // 3, x2 - 4 * s, y2 - 5 * s),
        (x1 + 5 * s, y2 - 6 * s, x2 - 6 * s, y1 + h // 2),
        (x1 + w // 3, y1 + 6 * s, x1 + 2 * w // 3, y2 - 4 * s),
    )
    for x_a, y_a, x_b, y_b in cracks:
        _px_line(canvas, x_a, y_a, x_b, y_b, s, accent)
        _px_line(canvas, x_a + s, y_a, x_b + s, y_b, s, _shift_hex(accent, 35))


def _draw_arcade_card(
    canvas: tk.Canvas, x1: int, y1: int, x2: int, y2: int, fill: str, accent: str, scale: int
) -> None:
    s = max(2, scale)
    stripe = 2 * s
    row = 0
    y = y1
    while y < y2:
        color = _shift_hex(fill, 14 if row % 2 else -14)
        _px_rect(canvas, x1, y, x2, min(y + stripe, y2), color)
        y += stripe
        row += 1
    _px_frame(canvas, x1, y1, x2, y2, accent, 2 * s)
    dot = 2 * s
    for px, py in ((x1 + dot, y1 + dot), (x2 - dot, y1 + dot), (x1 + dot, y2 - dot), (x2 - dot, y2 - dot)):
        _px_rect(canvas, px - dot, py - dot, px + dot, py + dot, accent)


def _draw_gold_card(
    canvas: tk.Canvas, x1: int, y1: int, x2: int, y2: int, fill: str, accent: str, scale: int
) -> None:
    s = max(2, scale)
    _px_rect(canvas, x1, y1, x2, y2, fill)
    _px_frame(canvas, x1, y1, x2, y2, accent, 2 * s)
    inset = 2 * s
    _px_frame(
        canvas, x1 + inset, y1 + inset, x2 - inset, y2 - inset, _shift_hex(accent, 25), s
    )
    gem = 2 * s
    for px, py in ((x1 + 3 * s, y1 + 3 * s), (x2 - 3 * s, y1 + 3 * s), (x1 + 3 * s, y2 - 3 * s), (x2 - 3 * s, y2 - 3 * s)):
        _px_rect(canvas, px - gem, py - gem, px + gem, py + gem, accent)
        _px_frame(canvas, px - gem, py - gem, px + gem, py + gem, _shift_hex(accent, 40), s)


def _draw_circuit_card(
    canvas: tk.Canvas, x1: int, y1: int, x2: int, y2: int, fill: str, accent: str, scale: int
) -> None:
    s = max(2, scale)
    _px_rect(canvas, x1, y1, x2, y2, fill)
    _px_frame(canvas, x1, y1, x2, y2, accent, s)
    step = max(3, 4 * s)
    dot = max(1, s)
    gx = x1 + 2 * s
    while gx < x2 - 2 * s:
        gy = y1 + 2 * s
        while gy < y2 - 2 * s:
            _px_rect(canvas, gx, gy, gx + dot, gy + dot, _shift_hex(accent, -15))
            gy += step
        gx += step
    mid = (y1 + y2) // 2
    _px_rect(canvas, x1 + 4 * s, mid, x2 - 4 * s, mid + s, accent)
    _px_rect(canvas, (x1 + x2) // 2, y1 + 4 * s, (x1 + x2) // 2 + s, y2 - 4 * s, accent)


def _draw_shadow_card(
    canvas: tk.Canvas, x1: int, y1: int, x2: int, y2: int, fill: str, accent: str, scale: int
) -> None:
    s = max(2, scale)
    _px_rect(canvas, x1, y1, x2, y2, fill)
    inset = 2 * s
    _px_frame(canvas, x1 + inset, y1 + inset, x2 - inset, y2 - inset, accent, s)
    _px_rect(
        canvas,
        x1 + inset,
        y1 + inset + 3 * s,
        x2 - inset,
        y1 + inset + 3 * s + s,
        _shift_hex(accent, -35),
    )


def _draw_crimson_card(
    canvas: tk.Canvas, x1: int, y1: int, x2: int, y2: int, fill: str, accent: str, scale: int
) -> None:
    """Colosseum arches + rivets (pixel arches, no arcs/ovals)."""
    s = max(2, scale)
    _px_rect(canvas, x1, y1, x2, y2, fill)
    _px_frame(canvas, x1, y1, x2, y2, _shift_hex(accent, -40), 2 * s)
    arch_y = y1 + (y2 - y1) // 3
    step = max(6 * s, (x2 - x1) // 4)
    x = x1 + 3 * s
    while x + step < x2 - 2 * s:
        _px_arc_top(canvas, x, arch_y, step, 4 * s, s, accent)
        x += step + s
    rivet = max(s, s)
    for px, py in (
        (x1 + 3 * s, y1 + 3 * s),
        (x2 - 3 * s, y1 + 3 * s),
        (x1 + 3 * s, y2 - 3 * s),
        (x2 - 3 * s, y2 - 3 * s),
    ):
        _px_disk(canvas, px, py, rivet, max(1, s // 2) if s >= 2 else s, accent)


def _draw_ocean_card(
    canvas: tk.Canvas, x1: int, y1: int, x2: int, y2: int, fill: str, accent: str, scale: int
) -> None:
    """Layered stepped wave bands (no polygons)."""
    s = max(2, scale)
    _px_rect(canvas, x1, y1, x2, y2, fill)
    _px_frame(canvas, x1, y1, x2, y2, accent, s)
    band = max(3, 3 * s)
    y = y1 + 2 * s
    row = 0
    while y < y2 - 2 * s:
        color = _shift_hex(accent, 20 if row % 2 == 0 else -25)
        amp = 2 * s if row % 2 == 0 else s
        x = x1 + 2 * s
        while x < x2 - 2 * s:
            crest = amp if ((x // s) % 4 < 2) else 0
            _px_rect(canvas, x, y + crest, min(x + 2 * s, x2 - 2 * s), y + band + crest, color)
            x += 2 * s
        y += band + s
        row += 1
    _px_rect(canvas, x1 + s, y1 + s, x2 - s, y1 + 2 * s, _shift_hex(accent, 40))


def _draw_sakura_card(
    canvas: tk.Canvas, x1: int, y1: int, x2: int, y2: int, fill: str, accent: str, scale: int
) -> None:
    """Pixel-rounded frame with petal dots (no ovals)."""
    s = max(2, scale)
    cut = 3 * s
    _px_rect(canvas, x1 + cut, y1, x2 - cut, y2, fill)
    _px_rect(canvas, x1, y1 + cut, x2, y2 - cut, fill)
    # Stepped corner fills (2-block chamfer + disk quarter feel)
    for cx, cy in (
        (x1 + cut, y1 + cut),
        (x2 - cut, y1 + cut),
        (x1 + cut, y2 - cut),
        (x2 - cut, y2 - cut),
    ):
        _px_disk(canvas, cx, cy, cut, s, fill)
    _px_frame(canvas, x1 + s, y1 + s, x2 - s, y2 - s, accent, s)
    petal = max(2 * s, 2 * s)
    for px, py in (
        (x1 + 4 * s, y1 + 5 * s),
        (x2 - 4 * s, y1 + 5 * s),
        (x1 + 4 * s, y2 - 5 * s),
        (x2 - 4 * s, y2 - 5 * s),
        ((x1 + x2) // 2, y1 + 4 * s),
    ):
        _px_disk(canvas, px, py, petal, s, accent)


def _draw_jazz_card(
    canvas: tk.Canvas, x1: int, y1: int, x2: int, y2: int, fill: str, accent: str, scale: int
) -> None:
    """Diagonal velvet stripes + gold corners (block diagonals)."""
    s = max(2, scale)
    _px_rect(canvas, x1, y1, x2, y2, fill)
    _px_frame(canvas, x1, y1, x2, y2, accent, 2 * s)
    step = max(3, 3 * s)
    d = y2 - y1
    i = x1 - d
    stripe = _shift_hex(fill, 18)
    while i < x2 + d:
        _px_line(canvas, i, y1 + s, i + d, y2 - s, s, stripe)
        i += step
    corner = 4 * s
    for px, py, dx, dy in (
        (x1 + 2 * s, y1 + 2 * s, 1, 1),
        (x2 - 2 * s - s, y1 + 2 * s, -1, 1),
        (x1 + 2 * s, y2 - 2 * s - s, 1, -1),
        (x2 - 2 * s - s, y2 - 2 * s - s, -1, -1),
    ):
        if dx > 0:
            _px_rect(canvas, px, py, px + corner, py + s, accent)
        else:
            _px_rect(canvas, px - corner + s, py, px + s, py + s, accent)
        if dy > 0:
            _px_rect(canvas, px, py, px + s, py + corner, accent)
        else:
            _px_rect(canvas, px, py - corner + s, px + s, py + s, accent)


def _draw_toxic_card(
    canvas: tk.Canvas, x1: int, y1: int, x2: int, y2: int, fill: str, accent: str, scale: int
) -> None:
    """Hazard chevron bars as stepped pixel triangles."""
    s = max(2, scale)
    _px_rect(canvas, x1, y1, x2, y2, fill)
    _px_frame(canvas, x1, y1, x2, y2, accent, s)
    band = max(3, 3 * s)
    for side_y in (y1 + 2 * s, y2 - 2 * s - band):
        x = x1 + 2 * s
        flip = 0
        while x < x2 - 2 * s:
            color = accent if flip % 2 == 0 else _shift_hex(fill, -20)
            # Build chevron from horizontal slices (peak at top)
            for step_i in range(0, band, s):
                t = step_i // s
                half = t * s
                mid = x + band
                _px_rect(
                    canvas,
                    mid - half,
                    side_y + band - step_i - s,
                    mid + half + s,
                    side_y + band - step_i,
                    color,
                )
            x += band
            flip += 1
    mid = (y1 + y2) // 2
    _px_rect(canvas, x1 + 3 * s, mid - s, x2 - 3 * s, mid + s, accent)


def _draw_solar_card(
    canvas: tk.Canvas, x1: int, y1: int, x2: int, y2: int, fill: str, accent: str, scale: int
) -> None:
    """Sunburst rays from center (pixel lines + disk core)."""
    s = max(2, scale)
    _px_rect(canvas, x1, y1, x2, y2, fill)
    _px_frame(canvas, x1, y1, x2, y2, accent, 2 * s)
    cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
    radius = min(x2 - x1, y2 - y1) // 2 - 2 * s
    for i in range(12):
        ang = i * math.pi / 6
        x_b = cx + int(math.cos(ang) * radius)
        y_b = cy + int(math.sin(ang) * radius)
        _px_line(canvas, cx, cy, x_b, y_b, s, _shift_hex(accent, -20 if i % 2 else 20))
    core = 3 * s
    _px_disk(canvas, cx, cy, core, s, accent)
    _px_ring(canvas, cx, cy, core + s, s, _shift_hex(accent, 40))


def _draw_aurora_card(
    canvas: tk.Canvas, x1: int, y1: int, x2: int, y2: int, fill: str, accent: str, scale: int
) -> None:
    """Stepped ribbon bands (no smooth curves)."""
    s = max(2, scale)
    _px_rect(canvas, x1, y1, x2, y2, fill)
    _px_frame(canvas, x1, y1, x2, y2, accent, s)
    ribbons = (
        (_shift_hex(accent, 30), y1 + (y2 - y1) // 4),
        (accent, y1 + (y2 - y1) // 2),
        (_shift_hex(accent, -30), y1 + 3 * (y2 - y1) // 4),
    )
    for color, base_y in ribbons:
        x = x1 + 2 * s
        phase = 0
        while x <= x2 - 2 * s:
            y = base_y + (2 * s if phase % 2 == 0 else -2 * s)
            _px_rect(canvas, x, y, min(x + 3 * s, x2 - 2 * s), y + s, color)
            x += 3 * s
            phase += 1
    _px_frame(canvas, x1 + 2 * s, y1 + 2 * s, x2 - 2 * s, y2 - 2 * s, _shift_hex(accent, 25), s)


def _draw_ruins_card(
    canvas: tk.Canvas, x1: int, y1: int, x2: int, y2: int, fill: str, accent: str, scale: int
) -> None:
    """Weathered pillars + cracked lintel (pixel cracks)."""
    s = max(2, scale)
    _px_rect(canvas, x1, y1, x2, y2, fill)
    _px_frame(canvas, x1, y1, x2, y2, _shift_hex(accent, -30), s)
    _px_rect(canvas, x1 + 2 * s, y1 + 2 * s, x2 - 2 * s, y1 + 5 * s, _shift_hex(fill, 15))
    _px_frame(canvas, x1 + 2 * s, y1 + 2 * s, x2 - 2 * s, y1 + 5 * s, accent, s)
    pillar_w = max(3, 3 * s)
    gap = max(4, (x2 - x1 - 4 * s - 3 * pillar_w) // 2)
    px = x1 + 3 * s
    for _ in range(3):
        _px_rect(canvas, px, y1 + 5 * s, px + pillar_w, y2 - 3 * s, _shift_hex(fill, -12))
        _px_frame(canvas, px, y1 + 5 * s, px + pillar_w, y2 - 3 * s, accent, s)
        px += pillar_w + gap
    _px_line(canvas, x1 + 4 * s, y2 - 5 * s, x2 - 6 * s, y2 - 4 * s, s, accent)
    _px_line(canvas, x1 + 6 * s, y1 + 8 * s, x1 + 10 * s, y1 + 12 * s, s, _shift_hex(accent, -20))


def _draw_void_card(
    canvas: tk.Canvas, x1: int, y1: int, x2: int, y2: int, fill: str, accent: str, scale: int
) -> None:
    """Concentric pixel rings + star dots."""
    s = max(2, scale)
    _px_rect(canvas, x1, y1, x2, y2, fill)
    cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
    for ring in (8 * s, 5 * s, 3 * s):
        _px_ring(canvas, cx, cy, ring, s, accent)
    star = max(1, s)
    for px, py in (
        (x1 + 3 * s, y1 + 3 * s),
        (x2 - 3 * s, y1 + 4 * s),
        (x1 + 4 * s, y2 - 4 * s),
        (x2 - 4 * s, y2 - 3 * s),
        (x1 + 6 * s, (y1 + y2) // 2),
        (x2 - 6 * s, (y1 + y2) // 2),
    ):
        _px_rect(canvas, px - star, py - star, px + star, py + star, _shift_hex(accent, 30))


def _draw_candy_card(
    canvas: tk.Canvas, x1: int, y1: int, x2: int, y2: int, fill: str, accent: str, scale: int
) -> None:
    """Scalloped border + polka dots (pixel disks only)."""
    s = max(2, scale)
    _px_rect(canvas, x1 + s, y1 + s, x2 - s, y2 - s, fill)
    r = 2 * s
    x = x1 + s
    while x < x2 - s:
        _px_disk(canvas, x + r, y1 + r, r, s, accent)
        _px_disk(canvas, x + r, y2 - r, r, s, accent)
        x += 2 * r
    y = y1 + s
    while y < y2 - s:
        _px_disk(canvas, x1 + r, y + r, r, s, accent)
        _px_disk(canvas, x2 - r, y + r, r, s, accent)
        y += 2 * r
    _px_rect(canvas, x1 + 2 * s, y1 + 2 * s, x2 - 2 * s, y2 - 2 * s, fill)
    _px_frame(canvas, x1 + 2 * s, y1 + 2 * s, x2 - 2 * s, y2 - 2 * s, _shift_hex(accent, 20), s)
    dot = max(2, 2 * s)
    for px, py in (
        (x1 + 6 * s, y1 + 7 * s),
        (x2 - 6 * s, y1 + 9 * s),
        (x1 + 7 * s, y2 - 8 * s),
        (x2 - 7 * s, y2 - 7 * s),
        ((x1 + x2) // 2, (y1 + y2) // 2),
    ):
        _px_disk(canvas, px, py, dot, s, _shift_hex(accent, -15))


def _draw_village_card(
    canvas: tk.Canvas, x1: int, y1: int, x2: int, y2: int, fill: str, accent: str, scale: int
) -> None:
    """Side-view Minecraft grass block: jagged green top + speckled dirt body."""
    s = max(2, scale)
    # Classic grass-block palette (tinted toward theme fill/accent)
    grass_hi = _shift_hex(fill, 40) if fill else "#7cfc00"
    grass_mid = fill if fill else "#4caf50"
    grass_lo = _shift_hex(fill, -25) if fill else "#2e7d32"
    dirt_hi = _shift_hex(accent, 28) if accent else "#c4a484"
    dirt_mid = accent if accent else "#8d6e4c"
    dirt_lo = _shift_hex(accent, -30) if accent else "#5d4037"
    dirt_red = _shift_hex(accent, -10) if accent else "#6d4c3d"
    stone = "#8a8a8a"
    outline = _shift_hex(dirt_lo, -20)

    w = max(1, x2 - x1)
    h = max(1, y2 - y1)
    # ~16px logical columns like a Minecraft block face
    cols = 16
    rows = 16
    cell_w = max(1, w // cols)
    cell_h = max(1, h // rows)

    def cell(cx: int, cy: int, color: str) -> None:
        px = x1 + cx * cell_w
        py = y1 + cy * cell_h
        # Stretch last row/col to cover rounding leftover
        pw = (x2 - px) if cx == cols - 1 else cell_w
        ph = (y2 - py) if cy == rows - 1 else cell_h
        canvas.create_rectangle(px, py, px + pw, py + ph, fill=color, outline="", width=0)

    # Jagged grass fringe pattern (row depths) — like the reference block
    grass_depth = [3, 4, 3, 2, 4, 3, 4, 3, 2, 4, 3, 4, 2, 3, 4, 3]
    dirt_noise = (
        0, 1, 2, 0, 3, 1, 0, 2, 1, 0, 3, 2, 0, 1, 2, 0,
        1, 0, 3, 2, 0, 1, 2, 0, 3, 1, 0, 2, 1, 0, 3, 2,
        2, 3, 0, 1, 2, 0, 3, 1, 0, 2, 1, 3, 0, 2, 1, 0,
        0, 2, 1, 3, 0, 2, 1, 0, 2, 0, 3, 1, 2, 0, 1, 3,
        1, 0, 2, 0, 3, 1, 0, 2, 3, 1, 0, 2, 0, 1, 2, 0,
        3, 1, 0, 2, 1, 0, 2, 3, 0, 1, 2, 0, 1, 3, 0, 2,
        0, 2, 3, 1, 0, 2, 1, 0, 2, 0, 1, 3, 2, 0, 1, 0,
        2, 0, 1, 0, 2, 3, 0, 1, 0, 2, 1, 0, 3, 2, 0, 1,
        1, 3, 0, 2, 1, 0, 2, 0, 1, 3, 0, 2, 1, 0, 2, 0,
        0, 1, 2, 0, 3, 1, 0, 2, 0, 1, 2, 3, 0, 1, 0, 2,
        2, 0, 1, 3, 0, 2, 1, 0, 2, 0, 1, 0, 2, 3, 1, 0,
        0, 2, 0, 1, 2, 0, 3, 1, 0, 2, 3, 0, 1, 2, 0, 1,
        1, 0, 2, 0, 1, 3, 0, 2, 1, 0, 2, 1, 0, 2, 3, 0,
    )
    dirt_tones = (dirt_mid, dirt_hi, dirt_lo, dirt_red)
    # Sparse pebble positions (col, row) in dirt area
    pebbles = {(2, 7), (5, 9), (9, 6), (12, 11), (4, 13), (14, 8), (7, 12), (11, 14)}

    for cy in range(rows):
        for cx in range(cols):
            depth = grass_depth[cx % len(grass_depth)]
            if cy < depth:
                # Grass: lighter on top row, mid/dark toward fringe
                if cy == 0:
                    color = grass_hi
                elif cy == depth - 1:
                    color = grass_lo
                else:
                    color = grass_mid if (cx + cy) % 2 == 0 else grass_hi
            else:
                if (cx, cy) in pebbles:
                    color = stone
                else:
                    idx = dirt_noise[((cy * cols) + cx) % len(dirt_noise)]
                    color = dirt_tones[idx]
            cell(cx, cy, color)

    # Soft block outline
    _px_frame(canvas, x1, y1, x2, y2, outline, max(1, s))


_CARD_FRAME_DRAWERS = {
    "pixel": _draw_pixel_panel,
    "neon": _draw_neon_card,
    "stone": _draw_stone_card,
    "ice": _draw_ice_card,
    "lava": _draw_lava_card,
    "arcade": _draw_arcade_card,
    "gold": _draw_gold_card,
    "circuit": _draw_circuit_card,
    "shadow": _draw_shadow_card,
    "crimson": _draw_crimson_card,
    "ocean": _draw_ocean_card,
    "sakura": _draw_sakura_card,
    "jazz": _draw_jazz_card,
    "toxic": _draw_toxic_card,
    "solar": _draw_solar_card,
    "aurora": _draw_aurora_card,
    "ruins": _draw_ruins_card,
    "void": _draw_void_card,
    "candy": _draw_candy_card,
    "village": _draw_village_card,
}


def _draw_card_frame(
    canvas: tk.Canvas,
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    fill: str,
    accent: str,
    scale: int,
) -> None:
    style = _theme().card_style
    drawer = _CARD_FRAME_DRAWERS.get(style, _draw_pixel_panel)
    drawer(canvas, x1, y1, x2, y2, fill, accent, scale)


def _draw_bloom(
    canvas: tk.Canvas,
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    accent: str,
    scale: int,
) -> None:
    """Layered pixel halos that suggest bloom without alpha compositing."""
    for distance, shade in ((3, -42), (2, -24), (1, -8)):
        inset = distance * scale
        canvas.create_rectangle(
            x1 - inset,
            y1 - inset,
            x2 + inset,
            y2 + inset,
            outline=_shift_hex(accent, shade),
            width=max(1, scale),
        )


class RoundedCardButton(tk.Canvas):
    """Clickable pixel-art card face (5:7 aspect ratio)."""

    FLIP_STEPS = 10
    FLIP_FRAME_MS = 16

    def __init__(
        self,
        parent: tk.Misc,
        card: Card,
        *,
        command=None,
        disabled: bool = False,
        selected: bool = False,
        width: int = CARD_MIN_W,
        height: int | None = None,
        flip_on_hover: bool = False,
    ) -> None:
        height = height or int(width * CARD_ASPECT)
        super().__init__(
            parent,
            width=width,
            height=height,
            bg=_theme().screen_bg,
            highlightthickness=0,
            bd=0,
            cursor="arrow" if disabled or command is None else "hand2",
        )
        self.card = card
        self.command = command
        self.disabled = disabled
        self.selected = selected
        self.flip_on_hover = self._is_unique_card(card)
        self._hover = False
        self._detail_popup: tk.Toplevel | None = None
        self._width = width
        self._height = height
        # 0.0 = face-down back, 1.0 = face-up front
        self._flip_t = 1.0
        self._flip_job: str | None = None
        self._flip_target = self._flip_t
        self._draw()
        # Hover always for flip mode; clicks only when playable
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Motion>", self._on_motion)
        if not disabled and command is not None:
            self.bind("<Button-1>", self._on_click)

    @staticmethod
    def _is_unique_card(card: Card) -> bool:
        return any(
            getattr(card, field, False)
            for field in (
                "steals",
                "heavy_hit",
                "shields",
                "poisons",
                "lava",
                "reaper",
                "vampire",
                "cure",
                "freeze",
                "gamble",
            )
        )

    def set_size(self, width: int, height: int) -> None:
        width = max(CARD_MIN_W, width)
        height = max(int(CARD_MIN_W * CARD_ASPECT), height)
        if width == self._width and height == self._height:
            return
        self._width = width
        self._height = height
        self.configure(width=width, height=height)
        self._draw()

    def set_card(self, card: Card, *, disabled: bool | None = None) -> None:
        self.card = card
        self.flip_on_hover = self._is_unique_card(card)
        self._flip_t = 1.0
        if disabled is not None:
            self.disabled = disabled
            self.configure(cursor="arrow" if self.disabled or self.command is None else "hand2")
        self._draw()

    def _font(self, ratio: float, minimum: int = 8) -> tuple[str, int, str]:
        size = _mc_font_size(max(minimum, int(min(self._width, self._height) * ratio)))
        return (_font_family(), size, "bold")

    def _font_regular(self, ratio: float, minimum: int = 8) -> tuple[str, int]:
        size = _mc_font_size(max(minimum, int(min(self._width, self._height) * ratio)))
        return (_font_family(), size)

    def _fill_colors(self) -> tuple[str, str, str]:
        art = _theme().cards
        if self.disabled:
            return art.disabled
        if self.selected:
            return art.selected
        if self.card.heal_any:
            return art.heal
        if self.card.heavy_hit:
            return art.heavy_hit
        if self.card.steals:
            return art.steal
        if self.card.shields:
            return art.selected
        if self.card.poisons:
            return art.poison
        if self.card.reaper:
            return ("#2b0f1a", "#ff5b7a", "#fbe7ef")
        if self.card.vampire:
            return ("#260d16", "#d9345b", "#fff0f3")
        if self.card.cure:
            return ("#0d2d1f", "#7cf2b7", "#e8fff5")
        if self.card.freeze:
            return ("#143547", "#70d9ff", "#e8faff")
        if self.card.gamble:
            return ("#3a2208", "#ffc14a", "#fff4d6")
        return art.normal

    def _cancel_flip(self) -> None:
        if self._flip_job is not None:
            try:
                self.after_cancel(self._flip_job)
            except tk.TclError:
                pass
            self._flip_job = None

    def _animate_flip_to(self, target: float) -> None:
        self._flip_target = 1.0 if target >= 0.5 else 0.0
        self._cancel_flip()
        if not self.flip_on_hover:
            self._flip_t = self._flip_target
            self._draw()
            return

        def step() -> None:
            self._flip_job = None
            diff = self._flip_target - self._flip_t
            if abs(diff) < 0.04:
                self._flip_t = self._flip_target
                self._draw()
                return
            self._flip_t += diff / max(2, self.FLIP_STEPS // 2)
            self._draw()
            self._flip_job = self.after(self.FLIP_FRAME_MS, step)

        step()

    def _draw_card_back(self, x1: int, y1: int, x2: int, y2: int, scale: int) -> None:
        """Theme-tinted card back (hidden face)."""
        theme = _theme()
        fill = theme.panel_bg
        accent = theme.panel_border
        _draw_card_frame(self, x1, y1, x2, y2, fill, accent, scale)
        cx = (x1 + x2) // 2
        cy = (y1 + y2) // 2
        # Inner diamond / pattern
        inset = 4 * scale
        _px_frame(
            self,
            x1 + inset,
            y1 + inset,
            x2 - inset,
            y2 - inset,
            accent,
            max(1, scale),
        )
        mark = max(3 * scale, (x2 - x1) // 5)
        _px_diamond(
            self,
            cx,
            cy,
            mark,
            max(1, scale),
            _shift_hex(fill, 18),
            accent,
        )
        self.create_text(
            cx,
            cy,
            text="CO",
            fill=theme.title_fg,
            font=self._font(0.14, 10),
        )

    def _draw_card_front(self, x1: int, y1: int, x2: int, y2: int, scale: int, *, hover: bool) -> None:
        fill, accent, text_color = self._fill_colors()
        if hover and not self.disabled:
            _draw_bloom(self, x1, y1, x2, y2, accent, scale)
            fill = _shift_hex(fill, 22)
        _draw_card_frame(self, x1, y1, x2, y2, fill, accent, scale)

        cx = (x1 + x2) // 2
        title_y = y1 + 7 * scale
        stats_y = int(self._height * 0.54)
        detail_y = y2 - 6 * scale
        style = _theme().card_style
        div_x1 = x1 + 5 * scale
        div_x2 = x2 - 5 * scale
        if style not in ("shadow", "circuit", "village"):
            divider_y1 = int(self._height * 0.30)
            divider_y2 = int(self._height * 0.76)
            self.create_rectangle(
                div_x1, divider_y1, div_x2, divider_y1 + scale, fill=accent, outline="", width=0
            )
            self.create_rectangle(
                div_x1, divider_y2, div_x2, divider_y2 + scale, fill=accent, outline="", width=0
            )
        elif style == "circuit":
            self.create_rectangle(
                div_x1, y1 + 5 * scale, div_x2, y1 + 5 * scale + max(1, scale // 2),
                fill=accent, outline="", width=0,
            )

        self.create_text(
            cx,
            title_y,
            text=self.card.name.upper(),
            fill=text_color,
            font=self._font(0.10, 8),
            width=max(20, (x2 - x1) - 10 * scale),
            justify="center",
        )
        stats, detail = self.card.face_stats()
        if self.disabled:
            detail = "cooling down"
        elif self.card.is_borrowed:
            detail = "borrowed"

        stats_color = "#ffffff"
        self.create_text(
            cx,
            stats_y,
            text=stats,
            fill=stats_color,
            font=self._font(0.13, 8),
            justify="center",
        )
        self.create_text(
            cx,
            detail_y,
            text=detail,
            fill=text_color,
            font=self._font_regular(0.08, 8),
            width=max(20, (x2 - x1) - 8 * scale),
            justify="center",
        )

        if self.card.lava_marked:
            lava_fill = "#ff8a1a"
            self.create_rectangle(
                x1 + 3 * scale,
                y1 + 3 * scale,
                x1 + 14 * scale,
                y1 + 14 * scale,
                fill=lava_fill,
                outline="#ffd1a6",
                width=max(1, scale),
            )
            self.create_text(
                x1 + 8 * scale,
                y1 + 8 * scale,
                text="LAVA",
                fill="#fff8ee",
                font=self._font_regular(0.055, 7),
                justify="center",
            )

    def _draw(self, hover: bool | None = None) -> None:
        if hover is None:
            hover = self._hover
        self.delete("all")
        scale = _pixel_scale(self._width)
        pad = scale
        # Horizontal squash for flip illusion (1 at faces, 0 at edge-on)
        squash = abs(1.0 - 2.0 * self._flip_t)
        squash = max(0.06, squash)
        full_w = self._width - 2 * pad
        draw_w = max(2, int(full_w * squash))
        cx = self._width // 2
        x1 = cx - draw_w // 2
        x2 = cx + draw_w // 2
        y1, y2 = pad, self._height - pad

        show_front = self._flip_t >= 0.5
        if show_front:
            self._draw_card_front(x1, y1, x2, y2, scale, hover=hover)
        else:
            self._draw_card_back(x1, y1, x2, y2, scale)

    def _on_click(self, _event=None) -> None:
        if not self.disabled and self.command:
            # Ensure face is up when selecting
            if self.flip_on_hover and self._flip_t < 0.5:
                self._flip_t = 1.0
                self._draw()
            self.command()

    def _on_enter(self, _event=None) -> None:
        self._hover = True
        if self.flip_on_hover:
            self._animate_flip_to(0.0)
        else:
            self._draw(hover=True)
        self._show_detail_popup()

    def _on_leave(self, _event=None) -> None:
        self._hover = False
        self._hide_detail_popup()
        if self.flip_on_hover:
            self._animate_flip_to(1.0)
        else:
            self._draw(hover=False)

    def _on_motion(self, _event=None) -> None:
        if self._hover:
            self._position_detail_popup()

    def _show_detail_popup(self) -> None:
        self._hide_detail_popup()
        popup = tk.Toplevel(self)
        popup.overrideredirect(True)
        popup.attributes("-topmost", True)
        popup.configure(bg=_theme().panel_border)
        text = tk.Label(
            popup,
            text=f"{self.card.name}\n\n{self.card.effect}",
            justify="left",
            anchor="w",
            wraplength=560,
            padx=20,
            pady=16,
            bg=_theme().panel_bg,
            fg=_theme().body_fg,
            font=(_font_family(), _mc_font_size(20)),
        )
        text.pack(padx=4, pady=4)
        popup.update_idletasks()
        self._detail_popup = popup
        self._position_detail_popup()

    def _position_detail_popup(self) -> None:
        popup = self._detail_popup
        if popup is None:
            return
        try:
            if not popup.winfo_exists():
                self._detail_popup = None
                return
            pointer_x = self.winfo_pointerx()
            pointer_y = self.winfo_pointery()
        except tk.TclError:
            self._detail_popup = None
            return
        x = pointer_x + 16
        y = pointer_y + 16
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        popup_w = popup.winfo_width()
        popup_h = popup.winfo_height()
        if x + popup_w > screen_w:
            x = max(0, pointer_x - popup_w - 16)
        if y + popup_h > screen_h:
            y = max(0, pointer_y - popup_h - 16)
        popup.geometry(f"+{x}+{y}")

    def _hide_detail_popup(self) -> None:
        if self._detail_popup is None:
            return
        try:
            self._detail_popup.destroy()
        except tk.TclError:
            pass
        self._detail_popup = None


class RoundedTargetButton(tk.Canvas):
    """Rounded-square button for choosing a target player."""

    def __init__(
        self,
        parent: tk.Misc,
        player: Player,
        subtitle: str,
        *,
        command,
        is_self: bool = False,
        bot_photo_getter=None,
        width: int = TARGET_MIN,
        height: int | None = None,
    ) -> None:
        height = height or width
        super().__init__(
            parent,
            width=width,
            height=height,
            bg=_theme().target_bg,
            highlightthickness=0,
            bd=0,
            cursor="hand2",
        )
        self.player = player
        self.subtitle = subtitle
        self.command = command
        self.is_self = is_self
        self._bot_photo_getter = bot_photo_getter
        self._hover = False
        self._size = width
        self._bot_photo = None
        self._draw()
        self.bind("<Button-1>", self._on_click)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)

    @staticmethod
    def _player_number(player: Player) -> str:
        if player.name.startswith("player-"):
            return player.name.split("-", 1)[1]
        letters = "".join(character for character in player.name if character.isalpha())
        return letters[:2].upper() or player.name

    def set_size(self, size: int) -> None:
        size = max(TARGET_MIN, size)
        if size == self._size:
            return
        self._size = size
        self.configure(width=size, height=size)
        self._draw(self._hover)

    def _colors(self, hover: bool) -> tuple[str, str, str]:
        theme = _theme()
        if self.is_self:
            fill, accent, text = theme.target_self
        else:
            fill, accent, text = theme.target_other
        if hover:
            fill = _shift_hex(fill, 22)
        return fill, accent, text

    def _draw_badge(self, cx: int, cy: int, accent: str, text_color: str) -> None:
        if self.player.is_bot and self._bot_photo_getter is not None:
            icon_size = max(32, int(self._size * 0.42))
            icon_size = (icon_size // 8) * 8
            photo = self._bot_photo_getter(icon_size)
            if photo is not None:
                self._bot_photo = photo
                self.create_image(cx, cy, image=photo)
                return
        number = self._player_number(self.player)
        self.create_text(
            cx,
            cy,
            text=number,
            fill=accent,
            font=(_font_family(), _mc_font_size(max(10, self._size // 6)), "bold"),
            justify="center",
        )

    def _draw(self, hover: bool = False) -> None:
        self.delete("all")
        fill, accent, text_color = self._colors(hover)
        s = self._size
        scale = _pixel_scale(s)
        pad = scale
        if hover:
            _draw_bloom(self, pad, pad, s - pad, s - pad, accent, scale)
        _draw_card_frame(self, pad, pad, s - pad, s - pad, fill, accent, scale)
        cx = s // 2
        self._draw_badge(cx, int(s * 0.34), accent, text_color)
        target_hp = "∞" if self.player.cheats_enabled else f"{self.player.hp}/{self.player.max_hp}"
        self.create_text(
            cx,
            int(s * 0.62),
            text=target_hp,
            fill=accent,
            font=(_font_family(), _mc_font_size(max(8, s // 9)), "bold"),
            justify="center",
        )
        self.create_text(
            cx,
            int(s * 0.82),
            text=self.subtitle,
            fill=text_color,
            font=(_font_family(), _mc_font_size(max(8, s // 14))),
            width=s - pad * 6,
            justify="center",
        )

    def _on_click(self, _event=None) -> None:
        if self.command:
            self.command()

    def _on_enter(self, _event=None) -> None:
        self._hover = True
        self._draw(hover=True)

    def _on_leave(self, _event=None) -> None:
        self._hover = False
        self._draw(hover=False)


HUD_CHIP_W = 220
HUD_CHIP_H = 112
ART_BTN_W = 200
ART_BTN_H = 52


def _hud_chip_size(player: Player) -> tuple[int, int]:
    """Scale top HUD chips so larger HP pools get roomier chips."""
    ref = max(int(getattr(player, "max_hp", 1) or 1), 1)
    # log curve: ~100 HP ≈ base, 500 ≈ +18%, 1000 ≈ +30%, 5000 ≈ +50%
    factor = 0.78 + 0.20 * math.log10(ref + 20)
    factor = max(0.82, min(1.70, factor))
    hp_text = (
        "∞ HP"
        if player.alive and player.cheats_enabled
        else f"{player.hp}/{player.max_hp} HP"
        if player.alive
        else "OUT"
    )
    char_w = max(8, int(round(9.5 * factor)))
    width = max(int(round(HUD_CHIP_W * factor)), len(hp_text) * char_w + 28)
    height = max(int(round(HUD_CHIP_H * factor)), int(round(64 * factor)))
    if player.alive and (
        player.shield_charges > 0
        or player.poisoned
        or player.freeze_skip_turns > 0
    ):
        height = max(height, int(round(80 * factor)))
    # Keep pixel-ish even sizes
    return width - (width % 2), height - (height % 2)


class PixelCloseButton(tk.Canvas):
    """Small pixel-art X button for closing overlays."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        command=None,
        size: int = LOG_CLOSE_SIZE,
        bg: str | None = None,
    ) -> None:
        super().__init__(
            parent,
            width=size,
            height=size,
            bg=bg if bg is not None else _theme().log_bg,
            highlightthickness=0,
            bd=0,
            cursor="hand2",
        )
        self.command = command
        self._hover = False
        self._size = size
        self._draw()
        self.bind("<Button-1>", self._on_click)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)

    def _draw(self, hover: bool = False) -> None:
        self.delete("all")
        art = _theme().cards
        fill, accent, _text = art.heavy_hit
        if hover:
            fill = _shift_hex(fill, 28)
            accent = _shift_hex(accent, 20)
        s = max(2, self._size // 14)
        pad = s
        _draw_card_frame(self, pad, pad, self._size - pad, self._size - pad, fill, accent, s)
        # Pixel X made of thick diagonal bars
        m = self._size // 2
        arm = self._size // 2 - 3 * s
        thickness = max(s, ((s + 1) // s) * s)
        for dx in range(-(thickness // s), thickness // s + 1):
            ox = dx * s
            _px_line(self, m - arm + ox, m - arm, m + arm + ox, m + arm, s, accent)
            _px_line(self, m + arm + ox, m - arm, m - arm + ox, m + arm, s, accent)

    def _on_click(self, _event=None) -> None:
        if self.command:
            self.command()

    def _on_enter(self, _event=None) -> None:
        self._hover = True
        self._draw(hover=True)

    def _on_leave(self, _event=None) -> None:
        self._hover = False
        self._draw(hover=False)


class ThemedArtButton(tk.Canvas):
    """Action button drawn with the active theme's card-frame art."""

    def __init__(
        self,
        parent: tk.Misc,
        text: str,
        *,
        command=None,
        width: int = ART_BTN_W,
        height: int = ART_BTN_H,
        palette: str = "normal",
        bg: str | None = None,
        text_scale: float = 1.0,
    ) -> None:
        super().__init__(
            parent,
            width=width,
            height=height,
            bg=bg if bg is not None else _theme().screen_bg,
            highlightthickness=0,
            bd=0,
            cursor="hand2",
        )
        self._label = text
        self.command = command
        self._palette = palette
        self._disabled = False
        self._hover = False
        self._width = width
        self._height = height
        self._text_scale = text_scale
        self._draw()
        self.bind("<Button-1>", self._on_click)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)

    def _colors(self, hover: bool) -> tuple[str, str, str]:
        art = _theme().cards
        mapping = {
            "normal": art.normal,
            "heal": art.heal,
            "heavy_hit": art.heavy_hit,
            "steal": art.steal,
            "poison": art.poison,
            "selected": art.selected,
            "disabled": art.disabled,
        }
        fill, accent, text = mapping.get(
            "disabled" if self._disabled else self._palette,
            art.normal,
        )
        if hover and not self._disabled:
            fill = _shift_hex(fill, 22)
        return fill, accent, text

    def state(self, states: list[str] | tuple[str, ...]) -> None:
        if "disabled" in states:
            self._disabled = True
        if "!disabled" in states:
            self._disabled = False
        self.configure(cursor="arrow" if self._disabled else "hand2")
        self._draw()

    def set_text(self, text: str) -> None:
        self._label = text
        self._draw(hover=self._hover)

    def _draw(self, hover: bool = False) -> None:
        self.delete("all")
        fill, accent, text_color = self._colors(hover)
        scale = _pixel_scale(min(self._width, self._height * 2))
        pad = scale
        x1, y1 = pad, pad
        x2, y2 = self._width - pad, self._height - pad
        _draw_pixel_panel(self, x1, y1, x2, y2, fill, accent, scale)
        self.create_text(
            self._width // 2,
            self._height // 2,
            text=self._label.upper(),
            fill=text_color,
            font=(
                _font_family(),
                _mc_font_size(max(10, int(self._height // 3 * self._text_scale))),
                "bold",
            ),
            justify="center",
        )

    def _on_click(self, _event=None) -> None:
        if not self._disabled and self.command:
            self.command()

    def _on_enter(self, _event=None) -> None:
        self._hover = True
        self._draw(hover=True)

    def _on_leave(self, _event=None) -> None:
        self._hover = False
        self._draw(hover=False)


class UniquePickCard(tk.Canvas):
    """Big card-framed toggle for Steal / Heavy Hit / Shield (label only)."""

    def __init__(
        self,
        parent: tk.Misc,
        label: str,
        *,
        variable: tk.BooleanVar,
        command=None,
        palette: str = "normal",
        bg: str | None = None,
        width: int = UNIQUE_PICK_W,
        height: int = UNIQUE_PICK_H,
        locked: bool = False,
    ) -> None:
        super().__init__(
            parent,
            width=width,
            height=height,
            bg=bg if bg is not None else _theme().screen_bg,
            highlightthickness=0,
            bd=0,
            cursor="arrow" if locked else "hand2",
        )
        self._label = label
        self.variable = variable
        self.command = command
        self._palette = palette
        self._locked = locked
        self._hover = False
        self._width = width
        self._height = height
        self._draw()
        self.bind("<Button-1>", self._on_click)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        if not locked:
            try:
                self.variable.trace_add("write", lambda *_: self._draw(self._hover))
            except tk.TclError:
                pass

    def _colors(self, hover: bool) -> tuple[str, str, str]:
        art = _theme().cards
        selected = bool(self.variable.get())
        if self._locked:
            fill, accent, text = art.disabled
        elif selected:
            fill, accent, text = art.selected
        else:
            mapping = {
                "normal": art.normal,
                "heal": art.heal,
                "heavy_hit": art.heavy_hit,
                "steal": art.steal,
                "poison": art.poison,
                "selected": art.selected,
                "disabled": art.disabled,
            }
            fill, accent, text = mapping.get(self._palette, art.normal)
        if hover and not selected and not self._locked:
            fill = _shift_hex(fill, 22)
        return fill, accent, text

    def _draw(self, hover: bool = False) -> None:
        self.delete("all")
        fill, accent, text_color = self._colors(hover)
        scale = _pixel_scale(min(self._width, self._height))
        pad = scale
        x1, y1 = pad, pad
        x2, y2 = self._width - pad, self._height - pad
        _draw_card_frame(self, x1, y1, x2, y2, fill, accent, scale)
        selected = bool(self.variable.get())
        title_size = _mc_font_size(max(12, self._height // 7))
        self.create_text(
            self._width // 2,
            self._height // 2 - (12 if selected or self._locked else 0),
            text=self._label.upper(),
            fill=text_color,
            font=(_font_family(), title_size, "bold"),
            justify="center",
            width=self._width - 4 * scale,
        )
        footer = None
        if self._locked:
            footer = "USED"
        elif selected:
            footer = "EQUIPPED"
        if footer:
            mark_size = _mc_font_size(max(9, self._height // 10))
            self.create_text(
                self._width // 2,
                self._height - 5 * scale,
                text=footer,
                fill=accent,
                font=(_font_family(), mark_size, "bold"),
                justify="center",
            )

    def _on_click(self, _event=None) -> None:
        if self._locked:
            return
        self.variable.set(not bool(self.variable.get()))
        if self.command:
            self.command()
        self._draw(self._hover)

    def _on_enter(self, _event=None) -> None:
        if self._locked:
            return
        self._hover = True
        self._draw(hover=True)

    def _on_leave(self, _event=None) -> None:
        self._hover = False
        self._draw(hover=False)


class PixelHudChip(tk.Canvas):
    """Pixel-art HP chip; the active player's panel is the turn indicator."""

    def __init__(
        self,
        parent: tk.Misc,
        player: Player,
        *,
        is_active: bool,
    ) -> None:
        w, h = _hud_chip_size(player)
        super().__init__(
            parent,
            width=w,
            height=h,
            bg=_theme().screen_bg,
            highlightthickness=0,
            bd=0,
        )
        self.player = player
        self.is_active = is_active
        self._width = w
        self._height = h
        self._draw()

    def _draw(self) -> None:
        self.delete("all")
        w, h = _hud_chip_size(self.player)
        if w != self._width or h != self._height:
            self._width, self._height = w, h
            self.configure(width=w, height=h)
        theme = _theme()
        if not self.player.alive:
            fill, accent, text_color = theme.hud_dead
        elif self.is_active:
            fill, accent, text_color = theme.hud_active
        else:
            fill, accent, text_color = theme.hud_idle
        scale = max(2, min(w, h) // 24)
        _draw_pixel_panel(self, 0, 0, w, h, fill, accent, scale)
        cx = w // 2
        name = self.player.name.upper()
        name_size = _mc_font_size(max(14, h // 7))
        hp_size = _mc_font_size(max(10, h // 7))
        status_size = _mc_font_size(max(9, h // 10))
        name_y = int(h * 0.28)
        hp_y = int(h * 0.58)
        status_y = int(h * 0.78)
        self.create_text(
            cx,
            name_y,
            text=name,
            fill=accent if self.is_active else text_color,
            font=(_font_family(), name_size, "bold" if self.is_active else "normal"),
            justify="center",
        )
        hp_text = (
            "∞ HP"
            if self.player.alive and self.player.cheats_enabled
            else f"{self.player.hp}/{self.player.max_hp} HP"
            if self.player.alive
            else "OUT"
        )
        self.create_text(
            cx,
            hp_y,
            text=hp_text,
            fill=accent if self.player.alive else text_color,
            font=(_font_family(), hp_size, "bold"),
            justify="center",
        )
        if self.player.alive and self.player.freeze_skip_turns > 0:
            self.create_text(
                cx,
                status_y,
                text=f"FROZEN ({self.player.freeze_skip_turns})",
                fill=accent,
                font=(_font_family(), status_size, "bold"),
                justify="center",
            )
        elif self.player.alive and self.player.shield_charges > 0:
            self.create_text(
                cx,
                status_y,
                text="SHIELD",
                fill=accent,
                font=(_font_family(), status_size, "bold"),
                justify="center",
            )
        elif self.player.alive and any(card.lava_marked for card in self.player.hand):
            lava_accent = _theme().cards.poison[1]
            self.create_text(
                cx,
                status_y,
                text="LAVA",
                fill=lava_accent,
                font=(_font_family(), status_size, "bold"),
                justify="center",
            )
        elif self.player.alive and self.player.poisoned:
            poison_accent = _theme().cards.poison[1]
            self.create_text(
                cx,
                status_y,
                text="POISON",
                fill=poison_accent,
                font=(_font_family(), status_size, "bold"),
                justify="center",
            )

class CrashOutApp(tk.Tk):
    def __init__(self) -> None:
        restore_theme_preference()
        super().__init__()
        self.title("Crash Out")
        self.geometry("920x700")
        self.minsize(480, 400)
        self._screen = "main_menu"
        self._play_banner = ""
        self._game_over_winner: str | None = None
        self._death_causes: dict[int, str] = {}
        self._fullscreen = False
        self._lan_servers: list[subprocess.Popen] = []
        self.bind("<F11>", self._toggle_fullscreen)

        self.settings: MatchSettings | None = None
        self.players: list[Player] = []
        self.game_mode = "Standard"
        self.crafted: list[Card] = []
        self.all_player_decks: list[list[Card]] = []
        self.player_names: list[str] = []
        self.crafting_player = 1
        self.craft_slot = 1
        self.active = 0
        self.pending_card: Card | None = None
        self.pending_target_idx: int | None = None
        self.starting_hp = DEFAULT_STARTING_HP
        self._busy = False
        self._borrows: list[ActiveBorrow] = []
        self._game_log: list[str] = []
        self._log_cheat_buffer: list[str] = []
        self.log: tk.Text | None = None
        self._card_faces: list[RoundedCardButton] = []
        self._hand_outer: tk.Frame | None = None
        self._overlay_host = tk.Frame(self, bg=_theme().screen_bg)
        self._target_overlay: tk.Canvas | None = None
        self._log_overlay: tk.Canvas | None = None
        self._log_panel: tk.Misc | None = None
        self._log_inner_id: int | None = None
        self._craft_scale: ttk.Scale | None = None
        self._target_row: tk.Frame | None = None
        self._target_buttons: list[RoundedTargetButton] = []
        self._bot_photo_cache: dict[int, tk.PhotoImage] = {}
        self.preview: RoundedCardButton | None = None
        self.preview_status: ttk.Label | None = None
        self._theme_label: tk.Canvas | None = None
        self._setup_rules_label: tk.Canvas | None = None
        self._music_volume_label: tk.Label | None = None
        self._main_menu_volume_var: tk.DoubleVar | None = None
        self._match_started_at: float | None = None
        self._match_timer_label: tk.Label | None = None
        self._match_timer_job: str | None = None
        self._hud_chips: list[PixelHudChip] = []
        self._hud_bar: tk.Frame | None = None
        self._bg_photo: tk.PhotoImage | None = None
        self._bg_tint: str | None = None
        self._widget_bg_photos: dict[int, tk.PhotoImage] = {}
        self._party_board: dict[tuple[int, int], int] = {}
        self._party_racers: list[Player] = []
        self._party_claims: list[int] = []
        self._party_progress: list[int] = []
        self._party_finish_round: list[int | None] = []
        self._party_blocked: set[int] = set()
        self._party_round = 0
        self._party_placements: dict[int, set[tuple[int, int]]] = {}
        self._party_conflicts: list[tuple[tuple[int, ...], set[tuple[int, int]]]] = []
        self._party_conflict_players: list[int] = []
        self._party_conflict_cells: set[tuple[int, int]] = set()
        self._party_duel_players: list[Player] = []
        self._party_duel_global_indices: list[int] = []
        self._party_duel_winner: int | None = None
        self._party_duel_active = False
        self._party_duel_turn = 0
        self._party_duel_turns = 0
        self._party_canvas: tk.Canvas | None = None
        self._party_preview: set[tuple[int, int]] = set()
        self._ui_fill = False
        self._ui_front_wallpaper = False
        self._last_container_size = (0, 0)
        self._bg_resize_job: str | None = None
        self.bind("<Escape>", self._on_escape_overlay)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self.style = ttk.Style(self)
        try:
            self.style.theme_use("clam")
        except tk.TclError:
            pass
        self._apply_theme_styles()

        # Single wallpaper layer lives on the container canvas. Root uses a solid
        # tint so the outer pad doesn't stack a second patterned background.
        self.container = tk.Canvas(self, highlightthickness=0, bd=0, bg=_theme().screen_bg)
        self.container.pack(fill="both", expand=True, padx=16, pady=16)
        self._ui = tk.Frame(self.container, bg=_theme().screen_bg)
        self._ui_win = self.container.create_window(0, 0, anchor="nw", window=self._ui)
        self.container.bind("<Configure>", self._on_container_configure)
        self._refresh_wallpapers()
        self.show_main_menu()

    def _apply_theme_styles(self) -> None:
        theme = _theme()
        self.configure(bg=theme.screen_bg)
        if hasattr(self, "container"):
            self.container.configure(bg=theme.screen_bg)
        if hasattr(self, "_ui"):
            self._ui.configure(bg=theme.screen_bg)
        if hasattr(self, "_overlay_host"):
            self._overlay_host.configure(bg=theme.screen_bg)
        if hasattr(self, "container"):
            self._refresh_wallpapers()
        self.style.configure(
            "Title.TLabel",
            font=(_font_family(), 22, "bold"),
            foreground=theme.title_fg,
            background=theme.screen_bg,
        )
        self.style.configure(
            "Body.TLabel",
            font=(_font_family(), 11),
            foreground=theme.body_fg,
            background=theme.screen_bg,
        )
        self.style.configure(
            "Log.TLabel",
            font=(_font_family(), 10),
            foreground=theme.log_fg,
            background=theme.log_bg,
        )
        self.style.configure("Accent.TButton", font=(_font_family(), 11, "bold"))
        self.style.configure(
            "SetupTitle.TLabel",
            font=(_font_family(), 32, "bold"),
            foreground=theme.title_fg,
            background=theme.screen_bg,
        )
        self.style.configure(
            "SetupBody.TLabel",
            font=(_font_family(), 16),
            foreground=theme.body_fg,
            background=theme.screen_bg,
        )
        self.style.configure(
            "Setup.TButton",
            font=(_font_family(), 16, "bold"),
            padding=(16, 8),
        )
        self.style.configure(
            "Setup.TCombobox",
            font=(_font_family(), 16),
        )
        self.style.configure(
            "Setup.TEntry",
            font=(_font_family(), 16),
        )
        self.style.configure(
            "Lab.TCheckbutton",
            font=(_font_family(), 16),
            background=theme.screen_bg,
            foreground=theme.body_fg,
        )
        self.style.configure(
            "Green.Horizontal.TScale",
            troughcolor=theme.scale_trough,
            background=theme.scale_fill,
            bordercolor=theme.scale_border,
            lightcolor=theme.scale_light,
            darkcolor=theme.scale_dark,
        )
        self.style.map(
            "Green.Horizontal.TScale",
            background=[("active", theme.scale_light), ("!disabled", theme.scale_fill)],
        )

    def _refresh_current_screen(self) -> None:
        if self._screen == "main_menu":
            self.show_main_menu()
        elif self._screen == "updates":
            self.show_updates()
        elif self._screen == "setup":
            self.show_setup()
        elif self._screen == "craft":
            self.show_craft()
        elif self._screen == "play":
            self.show_play(self._play_banner)
        elif self._screen == "game_over":
            self.show_game_over(self._game_over_winner)

    def _on_random_theme(self) -> None:
        theme = randomize_theme()
        self._apply_theme_styles()
        self._refresh_current_screen()
        self._sync_theme_picker(theme)
        play_sfx(SFX_THEME_CHANGE)

    def _on_reset_theme(self) -> None:
        theme = reset_theme()
        self._apply_theme_styles()
        self._refresh_current_screen()
        self._sync_theme_picker(theme)
        play_sfx(SFX_THEME_CHANGE)

    def _sync_theme_picker(self, theme) -> None:
        if self._theme_label is not None and self._theme_label.winfo_exists():
            self._set_menu_text(
                self._theme_label,
                f"Theme: {theme.name} ({theme.card_style}) — {theme.font_family}",
            )
        if getattr(self, "theme_var", None) is not None:
            try:
                self.theme_var.set(theme.name)
            except tk.TclError:
                pass

    def _on_pick_theme(self, _event: tk.Event | None = None) -> None:
        name = self.theme_var.get().strip() if getattr(self, "theme_var", None) else ""
        if not name:
            return
        theme = apply_theme_by_name(name)
        if theme is None:
            return
        self._apply_theme_styles()
        self._refresh_current_screen()
        self._sync_theme_picker(theme)
        play_sfx(SFX_THEME_CHANGE)

    def _reset_game(self) -> None:
        """Clear match progress and return to setup; keep the active theme."""
        play_sfx(SFX_UI_CLICK)
        self._busy = False
        self.settings = None
        self.players = []
        self.game_mode = "Standard"
        self.crafted = []
        self.all_player_decks = []
        self.player_names = []
        self.crafting_player = 1
        self.craft_slot = 1
        self.active = 0
        self.pending_card = None
        self.pending_target_idx = None
        self.starting_hp = DEFAULT_STARTING_HP
        self._borrows = []
        self._game_log = []
        self._death_causes = {}
        self._death_causes = {}
        self._play_banner = ""
        self._game_over_winner = None
        self._match_started_at = None
        self._stop_match_timer()
        self._party_board = {}
        self._party_racers = []
        self._party_claims = []
        self._party_progress = []
        self._party_finish_round = []
        self._party_blocked = set()
        self._party_round = 0
        self._party_placements = {}
        self._party_conflicts = []
        self._party_conflict_players = []
        self._party_conflict_cells = set()
        self._party_duel_players = []
        self._party_duel_global_indices = []
        self._party_duel_winner = None
        self._party_duel_active = False
        self._party_duel_turn = 0
        self._party_duel_turns = 0
        self._party_canvas = None
        self._party_preview = set()
        stop_bgm()
        self.show_main_menu()

    def _on_close(self) -> None:
        for server in self._lan_servers:
            if server.poll() is None:
                server.terminate()
                try:
                    server.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait()
        self._lan_servers.clear()
        save_theme_preference()
        shutdown_audio()
        self.destroy()

    def _on_bgm_volume(self, value: str) -> None:
        try:
            set_bgm_volume(float(value) / 100.0)
        except ValueError:
            pass
        if self._music_volume_label is not None and self._music_volume_label.winfo_exists():
            self._music_volume_label.configure(
                text=f"Music  {int(round(get_bgm_volume() * 100))}%"
            )

    def _toggle_fullscreen(self, _event: tk.Event | None = None) -> str:
        self._fullscreen = not self._fullscreen
        self.attributes("-fullscreen", self._fullscreen)
        return "break"

    def _raise_overlay_layer(self) -> None:
        self._overlay_host.place(relx=0, rely=0, relwidth=1, relheight=1)
        try:
            self.container.lower(self._overlay_host)
        except tk.TclError:
            pass
        tk.Misc.tkraise(self._overlay_host)

    def _set_screen_bg(self, color: str) -> None:
        tint_changed = color != self._bg_tint
        self._bg_tint = color
        self.configure(bg=color)
        if hasattr(self, "container"):
            self.container.configure(bg=color)
        if hasattr(self, "_ui"):
            self._ui.configure(bg=color)
        if hasattr(self, "_overlay_host"):
            self._overlay_host.configure(bg=color)
        # Avoid regenerating the container wallpaper on every clear()/turn.
        if tint_changed:
            self._refresh_wallpapers(tint=color)

    def _on_container_configure(self, event: tk.Event) -> None:
        if event.widget is not self.container:
            return
        if event.width < 40 or event.height < 40:
            return
        size = (event.width, event.height)
        if size == self._last_container_size:
            self._layout_ui_window(event.width, event.height)
            return
        self._last_container_size = size
        if self._bg_resize_job is not None:
            try:
                self.after_cancel(self._bg_resize_job)
            except tk.TclError:
                pass
        self._bg_resize_job = self.after(
            40, lambda w=event.width, h=event.height: self._finish_container_resize(w, h)
        )

    def _finish_container_resize(self, width: int, height: int) -> None:
        self._bg_resize_job = None
        self._refresh_container_wallpaper(width, height)
        self._layout_ui_window(width, height)

    def _refresh_wallpapers(self, tint: str | None = None) -> None:
        if tint is not None:
            self._bg_tint = tint
        self.update_idletasks()
        if hasattr(self, "container"):
            cw = max(self.container.winfo_width(), 200)
            ch = max(self.container.winfo_height(), 200)
            self._refresh_container_wallpaper(cw, ch)
            self._layout_ui_window(cw, ch)

    def _refresh_container_wallpaper(self, width: int, height: int) -> None:
        theme = _theme()
        tint = self._bg_tint or theme.screen_bg
        size = (max(1, width), max(1, height))
        if (
            size == getattr(self, "_last_wallpaper_size", None)
            and tint == getattr(self, "_last_wallpaper_tint", None)
            and self._bg_photo is not None
        ):
            self.container.configure(bg=tint)
            self.container.tag_lower("wallpaper")
            return
        photo = generate_theme_wallpaper(theme, size[0], size[1], tint=tint)
        self._bg_photo = photo
        self._last_wallpaper_size = size
        self._last_wallpaper_tint = tint
        self.container.delete("wallpaper")
        self.container.create_image(
            0, 0, anchor="nw", image=photo, tags="wallpaper"
        )
        self.container.tag_lower("wallpaper")
        self.container.configure(bg=tint)

    def _layout_ui_window(self, width: int, height: int) -> None:
        if not hasattr(self, "_ui_win"):
            return
        if self._ui_fill:
            pad = 0 if self._ui_front_wallpaper else 22
            self.container.coords(self._ui_win, pad, pad)
            self.container.itemconfigure(
                self._ui_win,
                anchor="nw",
                width=max(40, width - 2 * pad),
                height=max(40, height - 2 * pad),
            )
        else:
            self._ui.update_idletasks()
            rw = max(self._ui.winfo_reqwidth(), 80)
            rh = max(self._ui.winfo_reqheight(), 80)
            self.container.coords(self._ui_win, width // 2, height // 2)
            self.container.itemconfigure(
                self._ui_win,
                anchor="center",
                width=rw,
                height=rh,
            )
        self.container.itemconfigure(
            "wallpaper",
            state="hidden" if self._ui_front_wallpaper else "normal",
        )
        self.container.tag_raise(self._ui_win)

    def _stop_match_timer(self) -> None:
        if self._match_timer_job is not None:
            try:
                self.after_cancel(self._match_timer_job)
            except tk.TclError:
                pass
            self._match_timer_job = None
        self._match_timer_label = None

    def _update_match_timer(self) -> None:
        if self._match_started_at is None:
            return
        if self._match_timer_label is None or not self._match_timer_label.winfo_exists():
            self._match_timer_job = None
            return
        elapsed = max(0.0, time.monotonic() - self._match_started_at)
        self._match_timer_label.configure(text=f"Time: {format_elapsed_time(elapsed)}")
        self._match_timer_job = self.after(250, self._update_match_timer)

    def clear(self) -> None:
        self._stop_match_timer()
        self._hide_log_overlay()
        self._hide_target_overlay()
        self._remove_widget_wallpaper(self._ui)
        self._card_faces = []
        self._hand_outer = None
        self._party_canvas = None
        self._music_volume_label = None
        self.preview = None
        self.preview_status = None
        self._ui_fill = False
        self._ui_front_wallpaper = False
        self._set_screen_bg(_theme().screen_bg)
        for w in self._ui.winfo_children():
            w.destroy()

    def _remove_widget_wallpaper(self, widget: tk.Misc) -> None:
        key = id(widget)
        label = getattr(widget, "_pixel_bg_label", None)
        if label is not None:
            try:
                label.destroy()
            except tk.TclError:
                pass
        self._widget_bg_photos.pop(key, None)
        for attribute in (
            "_pixel_bg_label",
            "_pixel_bg_size",
            "_pixel_bg_tint",
            "_pixel_bg_tint_wanted",
            "_pixel_bg_ready",
            "_pixel_bg_bound",
        ):
            if hasattr(widget, attribute):
                delattr(widget, attribute)

    def _relayout_ui(self) -> None:
        if not hasattr(self, "container"):
            return
        cw = max(self.container.winfo_width(), 200)
        ch = max(self.container.winfo_height(), 200)
        self._layout_ui_window(cw, ch)

    def _install_widget_wallpaper(self, widget: tk.Misc, tint: str | None = None) -> None:
        """Place a single theme wallpaper behind a widget's children (idempotent)."""
        color = tint or self._bg_tint or _theme().screen_bg
        widget._pixel_bg_tint_wanted = color  # type: ignore[attr-defined]

        def _paint(_event: tk.Event | None = None) -> None:
            if getattr(widget, "_pixel_bg_painting", False):
                return
            try:
                if not widget.winfo_exists():
                    return
            except tk.TclError:
                return
            w = max(widget.winfo_width(), 2)
            h = max(widget.winfo_height(), 2)
            if w < 2 or h < 2:
                return
            paint_tint = (
                getattr(widget, "_pixel_bg_tint_wanted", None)
                or self._bg_tint
                or _theme().screen_bg
            )
            size = (w, h)
            if (
                size == getattr(widget, "_pixel_bg_size", None)
                and paint_tint == getattr(widget, "_pixel_bg_tint", None)
                and getattr(widget, "_pixel_bg_ready", False)
            ):
                return

            widget._pixel_bg_painting = True  # type: ignore[attr-defined]
            try:
                photo = generate_theme_wallpaper(_theme(), w, h, tint=paint_tint)
                self._widget_bg_photos[id(widget)] = photo
                if isinstance(widget, tk.Canvas):
                    widget.delete("wallpaper")
                    widget.create_image(
                        0, 0, anchor="nw", image=photo, tags="wallpaper"
                    )
                    widget.tag_lower("wallpaper")
                    if widget.find_withtag("label"):
                        widget.tag_raise("label")
                    widget.configure(bg=paint_tint)
                else:
                    existing = getattr(widget, "_pixel_bg_label", None)
                    if existing is not None:
                        try:
                            if existing.winfo_exists():
                                existing.configure(image=photo, bg=paint_tint)
                                existing.lower()
                                widget._pixel_bg_size = size  # type: ignore[attr-defined]
                                widget._pixel_bg_tint = paint_tint  # type: ignore[attr-defined]
                                widget._pixel_bg_ready = True  # type: ignore[attr-defined]
                                return
                        except tk.TclError:
                            pass
                    label = tk.Label(
                        widget, image=photo, bd=0, highlightthickness=0, bg=paint_tint
                    )
                    # Assign before place() so re-entrant Configure won't spawn another label.
                    widget._pixel_bg_label = label  # type: ignore[attr-defined]
                    label.place(x=0, y=0, relwidth=1, relheight=1)
                    label.lower()
                widget._pixel_bg_size = size  # type: ignore[attr-defined]
                widget._pixel_bg_tint = paint_tint  # type: ignore[attr-defined]
                widget._pixel_bg_ready = True  # type: ignore[attr-defined]
            finally:
                widget._pixel_bg_painting = False  # type: ignore[attr-defined]

        if not getattr(widget, "_pixel_bg_bound", False):
            widget.bind("<Configure>", _paint, add="+")
            widget._pixel_bg_bound = True  # type: ignore[attr-defined]
        self.after_idle(_paint)

    def _wallpaper_frame(self, parent: tk.Misc, tint: str, *, wallpaper: bool = False) -> tk.Frame:
        """Plain frame by default; set wallpaper=True for a single background layer."""
        frame = tk.Frame(parent, bg=tint)
        if wallpaper:
            self._install_widget_wallpaper(frame, tint)
        return frame

    def _menu_text(
        self,
        parent: tk.Misc,
        text: str,
        tint: str,
        *,
        fg: str,
        size: int,
        bold: bool = False,
        wraplength: int = 0,
        pady: int | tuple[int, int] = 0,
    ) -> tk.Canvas:
        """Title/body text — no per-label wallpaper (avoids tiled re-renders)."""
        family = _font_family()
        font: tuple = (family, size, "bold") if bold else (family, size)
        cv = tk.Canvas(parent, highlightthickness=0, bd=0, bg=tint, borderwidth=0)
        cv.create_text(
            0,
            0,
            text=text,
            fill=fg,
            font=font,
            width=wraplength if wraplength > 0 else 0,
            justify=tk.CENTER,
            anchor="nw",
            tags="label",
        )
        bbox = cv.bbox("label")
        if bbox is not None:
            cv.configure(width=max(1, bbox[2] - bbox[0]), height=max(1, bbox[3] - bbox[1]))
        cv.pack(pady=pady)
        return cv

    def _set_menu_text(
        self,
        canvas: tk.Canvas | None,
        text: str,
        *,
        wraplength: int = 0,
    ) -> None:
        if canvas is None:
            return
        try:
            if not canvas.winfo_exists():
                return
        except tk.TclError:
            return
        canvas.itemconfigure("label", text=text, width=wraplength if wraplength > 0 else 0)
        bbox = canvas.bbox("label")
        if bbox is not None:
            canvas.configure(
                width=max(1, bbox[2] - bbox[0]),
                height=max(1, bbox[3] - bbox[1]),
            )
        canvas.tag_raise("label")

    def _open_menu_panel(self, tint: str) -> tk.Frame:
        """
        One full-window animated wallpaper behind the centered menu content.
        """
        self._ui_fill = True
        self._ui_front_wallpaper = True
        self.after_idle(self._relayout_ui)
        self._ui.configure(bg=tint)
        panel = self._wallpaper_frame(self._ui, tint, wallpaper=True)
        panel.pack(fill="both", expand=True)
        panel.grid_rowconfigure(0, weight=1)
        panel.grid_rowconfigure(2, weight=1)
        panel.grid_columnconfigure(0, weight=1)
        # Plain host so text/rows don't each spawn a wallpaper. Panel art shows
        # through the empty grid rows above and below the content.
        host = self._wallpaper_frame(panel, tint, wallpaper=False)
        host.grid(row=1, column=0)
        return host

    def _release_overlay_host(self) -> None:
        if self._target_overlay is None and self._log_overlay is None:
            self._overlay_host.place_forget()

    def _on_escape_overlay(self, _event: tk.Event | None = None) -> str:
        if self._log_overlay is not None:
            self._hide_log_overlay()
            return "break"
        if self._target_overlay is not None:
            self._hide_target_overlay()
            self.pending_card = None
            return "break"
        return "break"

    def _get_bot_photo(self, size: int) -> tk.PhotoImage | None:
        if not BOT_ICON_PATH.exists():
            return None
        size = max(24, size)
        if size in self._bot_photo_cache:
            return self._bot_photo_cache[size]
        if HAS_PIL:
            img = Image.open(BOT_ICON_PATH).convert("RGBA")
            img = img.resize((size, size), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(img)
        else:
            photo = tk.PhotoImage(file=str(BOT_ICON_PATH))
            if photo.width() > size:
                factor = max(1, photo.width() // size)
                photo = photo.subsample(factor, factor)
        self._bot_photo_cache[size] = photo
        return photo

    def _draw_target_dim(self, _event: tk.Event | None = None) -> None:
        if self._target_overlay is None:
            return
        w = self._target_overlay.winfo_width()
        h = self._target_overlay.winfo_height()
        if w < 2 or h < 2:
            return
        self._target_overlay.delete("dim")
        # Dark dim — not solid black; game still faintly visible behind
        self._target_overlay.create_rectangle(
            0,
            0,
            w,
            h,
            fill="#0a0c0b",
            stipple="gray50",
            outline="",
            tags="dim",
        )

    def _hide_target_overlay(self) -> None:
        for child in list(self._overlay_host.winfo_children()):
            if child is self._log_overlay or child is self._log_panel:
                continue
            child.destroy()
        self._target_overlay = None
        self._target_row = None
        self._target_buttons = []
        self._release_overlay_host()

    def _draw_log_dim(self, _event: tk.Event | None = None) -> None:
        """Unused for fullscreen log; kept for resize hook compatibility."""
        return

    def _layout_log_panel(self, _event: tk.Event | None = None) -> None:
        if self._log_panel is None:
            return
        try:
            w = self._log_panel.winfo_width()
            h = self._log_panel.winfo_height()
        except tk.TclError:
            return
        if w < 40 or h < 40:
            return
        theme = _theme()
        fill, accent, _text = theme.cards.normal
        scale = max(2, min(w, h) // 80)
        self._log_panel.delete("frame")
        # Draw frame under content via temporary tag, then lower
        # Use a helper canvas layer: redraw by creating tagged shapes
        items_before = set(self._log_panel.find_all())
        _draw_card_frame(self._log_panel, scale, scale, w - scale, h - scale, fill, accent, scale)
        for item in self._log_panel.find_all():
            if item not in items_before:
                self._log_panel.itemconfigure(item, tags=("frame",))
        self._log_panel.tag_lower("frame")
        if self._log_inner_id is not None:
            inset = 6 * scale
            self._log_panel.coords(self._log_inner_id, w // 2, h // 2)
            self._log_panel.itemconfigure(
                self._log_inner_id,
                width=max(40, w - 2 * inset),
                height=max(40, h - 2 * inset),
            )

    def _hide_log_overlay(self) -> None:
        shells = []
        for w in (self._log_panel, self._log_overlay):
            if w is not None and w not in shells:
                shells.append(w)
        for w in shells:
            try:
                w.destroy()
            except tk.TclError:
                pass
        self._log_panel = None
        self._log_overlay = None
        self._log_inner_id = None
        self.log = None
        self._release_overlay_host()

    def _show_log_overlay(self) -> None:
        play_sfx(SFX_UI_CLICK)
        self._hide_target_overlay()
        self._hide_log_overlay()
        self._raise_overlay_layer()
        theme = _theme()
        fill, accent, _text_color = theme.cards.normal

        # Fullscreen shell — no separate dim layer
        shell = tk.Canvas(
            self._overlay_host,
            highlightthickness=0,
            bd=0,
            bg=theme.log_bg,
        )
        shell.place(relx=0, rely=0, relwidth=1, relheight=1)
        self._log_overlay = shell
        self._log_panel = shell

        inner = tk.Frame(shell, bg=theme.log_bg)
        self._log_inner_id = shell.create_window(0, 0, window=inner, anchor="center")

        header = tk.Frame(inner, bg=theme.log_bg)
        header.pack(fill="x", padx=16, pady=(14, 8))
        tk.Label(
            header,
            text="GAME LOG",
            fg=accent,
            bg=theme.log_bg,
            font=(_font_family(), 20, "bold"),
        ).pack(side="left")
        PixelCloseButton(
            header,
            command=self._hide_log_overlay,
            size=LOG_CLOSE_SIZE,
            bg=theme.log_bg,
        ).pack(side="right")

        log_frame = tk.Frame(inner, bg=theme.log_bg)
        log_frame.pack(fill="both", expand=True, padx=16, pady=(0, 8))

        scrollbar = tk.Scrollbar(
            log_frame, bg=theme.scale_trough, troughcolor=theme.log_bg
        )
        scrollbar.pack(side="right", fill="y")

        self.log = tk.Text(
            log_frame,
            bg=theme.log_bg,
            fg=theme.log_fg,
            insertbackground=theme.log_fg,
            font=(_font_family(), 12),
            relief="flat",
            wrap="word",
            state="disabled",
            yscrollcommand=scrollbar.set,
            padx=12,
            pady=12,
        )
        self.log.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=self.log.yview)
        shell.bind("<KeyPress>", self._on_log_keypress)
        shell.focus_set()
        self._render_game_log()

        # Music volume — bottom of log menu
        vol_row = tk.Frame(inner, bg=theme.log_bg)
        vol_row.pack(fill="x", padx=16, pady=(0, 14))
        pct = int(round(get_bgm_volume() * 100))
        self._music_volume_label = tk.Label(
            vol_row,
            text=f"Music  {pct}%",
            fg=theme.log_fg,
            bg=theme.log_bg,
            font=(_font_family(), 12),
            anchor="w",
        )
        self._music_volume_label.pack(fill="x", pady=(0, 4))
        vol_var = tk.DoubleVar(value=float(pct))
        ttk.Scale(
            vol_row,
            from_=0,
            to=100,
            orient="horizontal",
            variable=vol_var,
            command=self._on_bgm_volume,
        ).pack(fill="x")

        shell.bind("<Configure>", self._layout_log_panel)
        self.after_idle(self._layout_log_panel)
        self._raise_overlay_layer()

    def _target_subtitle(self, card: Card, target_idx: int) -> str:
        if card.heal_any:
            return "heal target"
        if target_idx == self.active:
            return "heal you"
        return "attack"

    def _card_target_indices(self, card: Card) -> list[int]:
        """Return valid targets, keeping self-only cards out of the chooser."""
        if card.heal_any:
            return [i for i, player in enumerate(self.players) if player.alive]
        if not (
            card.heal_any
            or card.damage > 0
            or card.steals
            or card.heavy_hit
            or card.poisons
            or card.lava
            or card.reaper
            or card.freeze
            or card.gamble
        ):
            return [self.active]
        opponents = [
            i for i, player in enumerate(self.players)
            if i != self.active and player.alive
        ]
        return opponents or [self.active]

    def _layout_target_buttons(self, _event: tk.Event | None = None) -> None:
        if not self._target_buttons or self._target_row is None:
            return
        fw = self._target_row.winfo_width()
        fh = self._target_row.winfo_height()
        if fw < TARGET_MIN or fh < TARGET_MIN:
            return
        n = len(self._target_buttons)
        size, gap = target_size_for_area(fw, fh, n)
        total_w = n * size + gap * max(0, n - 1)
        start_x = max(0, (fw - total_w) // 2)
        y = max(0, (fh - size) // 2)
        for i, btn in enumerate(self._target_buttons):
            btn.set_size(size)
            btn.place(x=start_x + i * (size + gap), y=y, width=size, height=size)

    def _show_target_overlay(self, card: Card) -> None:
        self._hide_log_overlay()
        self._hide_target_overlay()
        self._raise_overlay_layer()
        self._target_overlay = tk.Canvas(
            self._overlay_host,
            highlightthickness=0,
            bd=0,
            bg=_theme().overlay_bg,
        )
        self._target_overlay.place(relx=0, rely=0, relwidth=1, relheight=1)
        self._target_overlay.bind("<Configure>", self._draw_target_dim)
        self.after_idle(self._draw_target_dim)

        panel = tk.Frame(
            self._overlay_host,
            bg=_theme().panel_bg,
            highlightbackground=_theme().panel_border,
            highlightthickness=2,
            padx=20,
            pady=16,
        )
        panel.place(relx=0.5, rely=0.5, anchor="center")

        tk.Label(
            panel,
            text=f"Choose target for {card.name}",
            fg=_theme().title_fg,
            bg=_theme().panel_bg,
            font=(_font_family(), 14, "bold"),
        ).pack(pady=(0, 12))

        self._target_row = tk.Frame(panel, bg=_theme().panel_bg, width=560, height=220)
        self._target_row.pack()
        self._target_row.pack_propagate(False)
        self._target_buttons = []

        for i in self._card_target_indices(card):
            p = self.players[i]
            btn = RoundedTargetButton(
                self._target_row,
                p,
                self._target_subtitle(card, i),
                is_self=(i == self.active),
                bot_photo_getter=self._get_bot_photo,
                command=(lambda idx=i: self.confirm_play(idx)),
            )
            self._target_buttons.append(btn)

        self._target_row.bind("<Configure>", self._layout_target_buttons)
        self.after_idle(self._layout_target_buttons)
        self._raise_overlay_layer()

    def _snapshot_hp(self) -> list[int]:
        return [p.hp for p in self.players]

    def _record_new_deaths(self, before_hp: list[int], cause: str) -> None:
        for index, player in enumerate(self.players):
            if before_hp[index] > 0 and not player.alive:
                self._death_causes.setdefault(index, cause)

    def _mix_hex(self, a: str, b: str, t: float) -> str:
        t = max(0.0, min(1.0, t))
        ar = a.lstrip("#")
        br = b.lstrip("#")
        rgb = [
            int(int(ar[i : i + 2], 16) * (1 - t) + int(br[i : i + 2], 16) * t)
            for i in (0, 2, 4)
        ]
        return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"

    def _show_hp_floaters(self, before_hp: list[int]) -> bool:
        """Spawn floating +/- HP numbers over HUD chips. Returns True if any spawned."""
        if not self._hud_chips or not self._hud_bar:
            return False
        tint = self._bg_tint or _theme().screen_bg
        self._hud_bar.update_idletasks()
        spawned = False
        for i, chip in enumerate(self._hud_chips):
            if i >= len(self.players) or i >= len(before_hp):
                break
            try:
                chip._draw()
            except tk.TclError:
                continue
            delta = self.players[i].hp - before_hp[i]
            if delta == 0:
                continue
            spawned = True
            amount = abs(delta)
            is_heal = delta > 0
            text = f"+{amount}" if is_heal else f"-{amount}"
            color = "#2ecc71" if is_heal else "#e74c3c"
            try:
                x = chip.winfo_x() + chip.winfo_width() // 2
                y = chip.winfo_y() + 8
            except tk.TclError:
                continue
            lbl = tk.Label(
                self._hud_bar,
                text=text,
                fg=color,
                bg=tint,
                font=(_font_family(), 22, "bold"),
            )
            lbl.place(x=x, y=y, anchor="s")
            self._animate_floater(lbl, y, color, tint)
        return spawned

    def _animate_floater(
        self,
        label: tk.Label,
        start_y: int,
        color: str,
        tint: str,
        *,
        steps: int = 24,
        step_ms: int = 30,
    ) -> None:
        def tick(step: int = 0) -> None:
            try:
                if not label.winfo_exists():
                    return
            except tk.TclError:
                return
            if step >= steps:
                try:
                    label.destroy()
                except tk.TclError:
                    pass
                return
            t = step / max(1, steps - 1)
            # Rise and fade toward background tint
            label.place_configure(y=start_y - int(step * 2.4))
            label.configure(fg=self._mix_hex(color, tint, t * 0.85))
            self.after(step_ms, lambda: tick(step + 1))

        tick(0)

    def _complete_play(self, *, resolve_delay_ms: int | None = None) -> None:
        self.pending_card = None
        self.pending_target_idx = None
        self._busy = True
        self._borrows, return_logs = return_expired_borrows(
            self.players, self.active, self._borrows
        )
        for line in return_logs:
            self.append_log("  " + line)
        for line in tick_turn_cooldowns(self.players, self.active):
            self.append_log("  " + line)
        delay = TURN_DELAY_MS if resolve_delay_ms is None else resolve_delay_ms
        self.after(delay, self.after_resolve)

    def _layout_hand_cards(self, _event: tk.Event | None = None) -> None:
        if not self._card_faces or self._hand_outer is None:
            return
        fw = self._hand_outer.winfo_width()
        fh = self._hand_outer.winfo_height()
        if fw < CARD_MIN_W or fh < CARD_MIN_W:
            return

        n = len(self._card_faces)
        # At most half the hand per row (2-row grid when 2+ cards).
        cols = max(1, (n + 1) // 2)
        rows = 1 if n <= 1 else 2
        gap = max(CARD_GAP_MIN, fw // 80)
        card_w, card_h = card_size_for_area(fw, fh, n, columns=cols, rows=rows)

        row_counts = [min(cols, n)]
        if rows > 1:
            row_counts.append(n - row_counts[0])

        total_h = rows * card_h + gap * max(0, rows - 1)
        start_y = max(0, (fh - total_h) // 2)
        idx = 0
        for r, count in enumerate(row_counts):
            if count <= 0:
                continue
            total_w = count * card_w + gap * max(0, count - 1)
            start_x = max(0, (fw - total_w) // 2)
            y = start_y + r * (card_h + gap)
            for c in range(count):
                face = self._card_faces[idx]
                face.set_size(card_w, card_h)
                face.place(
                    x=start_x + c * (card_w + gap),
                    y=y,
                    width=card_w,
                    height=card_h,
                )
                idx += 1

    def show_main_menu(self) -> None:
        self._screen = "main_menu"
        self.clear()
        theme = _theme()
        tint = theme.screen_bg
        center = self._open_menu_panel(tint)

        self._menu_text(
            center,
            "CRASH OUT",
            tint,
            fg=theme.title_fg,
            size=36,
            bold=True,
        )
        self._menu_text(
            center,
            "Choose Play to set up your next game.",
            tint,
            fg=theme.body_fg,
            size=16,
            pady=(10, 22),
        )
        ThemedArtButton(
            center,
            text="Play",
            width=260,
            height=58,
            palette="selected",
            text_scale=0.65,
            command=self.show_setup,
        ).pack(pady=8)
        ThemedArtButton(
            center,
            text="Updates",
            width=240,
            height=48,
            palette="normal",
            text_scale=0.55,
            command=self.show_updates,
        ).pack(pady=8)

        volume_row = self._wallpaper_frame(center, tint)
        volume_row.pack(fill="x", padx=34, pady=(18, 8))
        pct = int(round(get_bgm_volume() * 100))
        self._music_volume_label = tk.Label(
            volume_row,
            text=f"Music volume  {pct}%",
            fg=theme.body_fg,
            bg=tint,
            font=(_font_family(), 13, "bold"),
        )
        self._music_volume_label.pack(pady=(0, 4))
        self._main_menu_volume_var = tk.DoubleVar(value=float(pct))
        ttk.Scale(
            volume_row,
            from_=0,
            to=100,
            orient="horizontal",
            variable=self._main_menu_volume_var,
            command=self._on_bgm_volume,
            style="Green.Horizontal.TScale",
            length=300,
        ).pack(fill="x", padx=14)

    def show_updates(self) -> None:
        self._screen = "updates"
        self.clear()
        theme = _theme()
        tint = theme.screen_bg
        center = self._open_menu_panel(tint)

        self._menu_text(
            center,
            "UPDATE HISTORY",
            tint,
            fg=theme.title_fg,
            size=28,
            bold=True,
            pady=(0, 14),
        )
        history_frame = self._wallpaper_frame(center, tint)
        history_frame.pack(fill="both", expand=True, padx=24, pady=(0, 12))
        history = tk.Text(
            history_frame,
            width=72,
            height=16,
            wrap="word",
            bg=theme.panel_bg,
            fg=theme.body_fg,
            insertbackground=theme.body_fg,
            relief="flat",
            padx=14,
            pady=10,
            font=(_font_family(), 12),
        )
        scrollbar = ttk.Scrollbar(
            history_frame, orient="vertical", command=history.yview
        )
        history.configure(yscrollcommand=scrollbar.set)
        history.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        history.tag_configure(
            "version",
            foreground=theme.title_fg,
            font=(_font_family(), 16, "bold"),
            spacing3=8,
        )
        history.tag_configure("note", lmargin1=12, lmargin2=24, spacing3=4)
        for version, notes in UPDATE_HISTORY:
            history.insert("end", version + "\n", "version")
            for note in notes:
                history.insert("end", f"- {note}\n", "note")
            history.insert("end", "\n")
        history.configure(state="disabled")
        ThemedArtButton(
            center,
            text="Back to Main Menu",
            width=240,
            height=48,
            palette="selected",
            text_scale=0.5,
            command=self.show_main_menu,
        ).pack(pady=(4, 0))

    def show_setup(self) -> None:
        self._screen = "setup"
        self.clear()
        theme = _theme()
        tint = theme.screen_bg
        center = self._open_menu_panel(tint)

        self._menu_text(
            center,
            "GAME SETTINGS",
            tint,
            fg=theme.title_fg,
            size=32,
            bold=True,
        )
        self._menu_text(
            center,
            (
                "Choose Standard to craft and play cards, or Party to race across a "
                "shared Tetris board with 2–4 local players."
            ),
            tint,
            fg=theme.body_fg,
            size=16,
            wraplength=720,
            pady=(12, 28),
        )

        form = self._wallpaper_frame(center, tint)
        form.pack()

        self.game_mode_var = tk.StringVar(value="Standard")
        ttk.Label(form, text="Game mode", style="SetupBody.TLabel").grid(
            row=0, column=0, sticky="e", pady=8, padx=8
        )
        game_mode = ttk.Combobox(
            form,
            textvariable=self.game_mode_var,
            values=["Standard", "Party"],
            state="readonly",
            width=18,
            font=(_font_family(), 16),
            style="Setup.TCombobox",
        )
        game_mode.grid(row=0, column=1, sticky="w", padx=8)
        game_mode.bind("<<ComboboxSelected>>", self._on_game_mode_changed)

        self.mode_var = tk.StringVar(value="1")
        ttk.Label(form, text="Match size", style="SetupBody.TLabel").grid(
            row=1, column=0, sticky="e", pady=8, padx=8
        )
        modes = ttk.Combobox(
            form,
            textvariable=self.mode_var,
            values=["1 — vs bot"] + [
                f"{count} players" for count in range(2, PLAYER_COUNT_MAX + 1)
            ],
            state="readonly",
            width=18,
            font=(_font_family(), 16),
            style="Setup.TCombobox",
        )
        modes.current(0)
        modes.grid(row=1, column=1, sticky="w", padx=8)
        self._player_count_picker = modes

        self.hp_var = tk.StringVar(value=str(DEFAULT_STARTING_HP))
        hp_label = ttk.Label(form, text="Starting HP", style="SetupBody.TLabel")
        hp_label.grid(row=2, column=0, sticky="e", pady=8, padx=8)
        hp_entry = ttk.Entry(
            form,
            textvariable=self.hp_var,
            width=12,
            font=(_font_family(), 16),
            style="Setup.TEntry",
        )
        hp_entry.grid(row=2, column=1, sticky="w", padx=8)

        self.pp_var = tk.StringVar(value=str(DEFAULT_POWER_POINTS))
        pp_label = ttk.Label(form, text="Power points / card", style="SetupBody.TLabel")
        pp_label.grid(row=3, column=0, sticky="e", pady=8, padx=8)
        pp_entry = ttk.Entry(
            form,
            textvariable=self.pp_var,
            width=12,
            font=(_font_family(), 16),
            style="Setup.TEntry",
        )
        pp_entry.grid(row=3, column=1, sticky="w", padx=8)

        self.deck_size_var = tk.IntVar(value=DECK_SIZE)
        deck_size_label = ttk.Label(form, text="Max cards / deck", style="SetupBody.TLabel")
        deck_size_label.grid(row=4, column=0, sticky="e", pady=8, padx=8)
        deck_row = self._wallpaper_frame(form, tint)
        deck_row.grid(row=4, column=1, sticky="w", padx=8)
        ThemedArtButton(
            deck_row,
            text="-",
            width=42,
            height=38,
            palette="normal",
            command=self._deck_size_down,
        ).pack(side="left")
        self._deck_size_label = ttk.Label(
            deck_row,
            textvariable=self.deck_size_var,
            style="SetupBody.TLabel",
            width=4,
            anchor="center",
        )
        self._deck_size_label.pack(side="left", padx=8)
        ThemedArtButton(
            deck_row,
            text="+",
            width=42,
            height=38,
            palette="normal",
            command=self._deck_size_up,
        ).pack(side="left")

        self._setup_rules_label = self._menu_text(
            center,
            self._setup_rules_text(DECK_SIZE),
            tint,
            fg=theme.body_fg,
            size=16,
            wraplength=720,
            pady=(24, 12),
        )
        self._party_setup_widgets = [
            hp_label,
            hp_entry,
            pp_label,
            pp_entry,
            deck_size_label,
            deck_row,
        ]

        self._setup_start_button = ThemedArtButton(
            center,
            text="Start Game",
            width=260,
            height=52,
            palette="selected",
            text_scale=0.5,
            command=self.begin_card_lab,
        )
        self._setup_start_button.pack(pady=8)

        online_row = tk.Frame(center, bg=tint)
        online_row.pack(pady=(6, 8))
        ThemedArtButton(
            online_row,
            text="Host Online",
            width=200,
            height=48,
            palette="steal",
            text_scale=0.55,
            command=self._host_online_game,
        ).pack(side="left", padx=6)
        ThemedArtButton(
            online_row,
            text="Host on LAN",
            width=200,
            height=48,
            palette="heavy_hit",
            text_scale=0.55,
            command=self._host_lan_game,
        ).pack(side="left", padx=6)
        join_row = tk.Frame(center, bg=tint)
        join_row.pack(pady=(0, 8))
        ThemedArtButton(
            join_row,
            text="Join Online by Code",
            width=220,
            height=48,
            palette="normal",
            text_scale=0.5,
            command=self._join_online_game,
        ).pack(side="left", padx=6)
        ThemedArtButton(
            join_row,
            text="Join LAN by Code",
            width=220,
            height=48,
            palette="selected",
            text_scale=0.5,
            command=self._join_lan_game,
        ).pack(side="left", padx=6)

        theme_row = self._wallpaper_frame(center, tint)
        theme_row.pack(pady=(16, 4))
        ttk.Label(theme_row, text="Theme", style="SetupBody.TLabel").pack(
            side="left", padx=(0, 8)
        )
        names = theme_names()
        current = theme.name if theme.name in names else names[0]
        self.theme_var = tk.StringVar(value=current)
        theme_pick = ttk.Combobox(
            theme_row,
            textvariable=self.theme_var,
            values=names,
            state="readonly",
            width=22,
            font=(_font_family(), 14),
            style="Setup.TCombobox",
        )
        theme_pick.pack(side="left", padx=4)
        theme_pick.bind("<<ComboboxSelected>>", self._on_pick_theme)
        ThemedArtButton(
            theme_row,
            text="Random",
            width=120,
            height=42,
            palette="normal",
            text_scale=0.5,
            command=self._on_random_theme,
        ).pack(side="left", padx=6)
        self._theme_label = self._menu_text(
            center,
            f"Theme: {theme.name} ({theme.card_style}) — {theme.font_family}",
            tint,
            fg=theme.body_fg,
            size=16,
            pady=(8, 0),
        )
        ThemedArtButton(
            center,
            text="Back to Main Menu",
            width=240,
            height=46,
            palette="normal",
            text_scale=0.5,
            command=self.show_main_menu,
        ).pack(pady=(8, 0))

    def _normalize_online_url(
        self,
        value: str,
        *,
        default_scheme: str,
    ) -> str | None:
        url = value.strip().rstrip("/")
        if "://" not in url:
            url = f"{default_scheme}://{url}"
        parsed = urlsplit(url)
        if (
            parsed.scheme not in ("http", "https")
            or not parsed.netloc
            or parsed.path not in ("", "/")
            or parsed.query
            or parsed.fragment
        ):
            messagebox.showerror(
                "Invalid Server URL",
                "Enter a server base address, such as http://192.168.1.20:54321.",
                parent=self,
            )
            return None
        return url

    def _online_server_url(self) -> str | None:
        config_path = Path.home() / ".crash_out_online_url"
        url = os.environ.get("CRASH_OUT_ONLINE_URL", "").strip()
        if not url:
            try:
                url = config_path.read_text(encoding="utf-8").strip()
            except OSError:
                pass
        if not url:
            url = simpledialog.askstring(
                "Online Multiplayer",
                "Enter the public Crash Out server URL (from the server deployment):",
                parent=self,
            )
            if not url:
                return None
        url = self._normalize_online_url(url, default_scheme="https")
        if not url:
            return None
        try:
            config_path.write_text(url, encoding="utf-8")
        except OSError:
            pass
        return url

    def _launch_online_window(self, url: str) -> None:
        if sys.platform == "darwin":
            if not webbrowser.open(url, new=1):
                messagebox.showerror(
                    "Online Multiplayer",
                    "Could not open the online game in your default browser.",
                    parent=self,
                )
            return
        try:
            import webview
        except ImportError:
            messagebox.showerror(
                "Online Multiplayer",
                "Install the windowed online dependencies with:\n"
                "python -m pip install -r requirements-windowed-online.txt",
                parent=self,
            )
            return
        self.withdraw()
        try:
            webview.create_window(
                "Crash Out Online",
                url,
                width=1100,
                height=820,
                min_size=(640, 520),
            )
            webview.start()
        except Exception as exc:
            messagebox.showerror("Online Multiplayer", str(exc), parent=self)
        finally:
            self.deiconify()

    def _host_online_game(self) -> None:
        server_url = self._online_server_url()
        if server_url:
            self._launch_online_window(server_url)

    def _host_lan_game(self) -> None:
        project_root = PROJECT_ROOT
        with socket.socket() as probe:
            probe.bind(("0.0.0.0", 0))
            port = probe.getsockname()[1]
        command = [
            sys.executable,
            "-m",
            "uvicorn",
            "server.app:app",
            "--host",
            "0.0.0.0",
            "--port",
            str(port),
        ]
        try:
            server = subprocess.Popen(
                command,
                cwd=project_root,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except OSError as exc:
            messagebox.showerror("LAN Host", str(exc), parent=self)
            return

        local_url = f"http://127.0.0.1:{port}"
        for _ in range(50):
            if server.poll() is not None:
                messagebox.showerror(
                    "LAN Host",
                    "The local game server stopped while starting. Install the "
                    "windowed online dependencies and try again.",
                    parent=self,
                )
                return
            try:
                with urlopen(f"{local_url}/api/host-info", timeout=0.3):
                    break
            except Exception:
                time.sleep(0.1)
        else:
            server.terminate()
            messagebox.showerror(
                "LAN Host",
                "The local game server did not become ready.",
                parent=self,
            )
            return

        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
                probe.connect(("8.8.8.8", 80))
                lan_ip = probe.getsockname()[0]
        except OSError:
            lan_ip = "127.0.0.1"
        messagebox.showinfo(
            "LAN Host",
            f"Friends on the same Wi-Fi connect to http://{lan_ip}:{port}, "
            "then enter the six-digit room code shown in the lobby.",
            parent=self,
        )
        if sys.platform == "darwin":
            self._lan_servers.append(server)
            self._launch_online_window(local_url)
            return
        try:
            self._launch_online_window(local_url)
        finally:
            if server.poll() is None:
                server.terminate()
                try:
                    server.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait()

    def _join_online_game(self) -> None:
        server_url = self._online_server_url()
        if server_url:
            self._join_game_at_server(server_url, "Join Online Game")

    def _join_lan_game(self) -> None:
        address = simpledialog.askstring(
            "Join LAN Game",
            "Enter the host's LAN address (shown when they host):",
            parent=self,
        )
        if not address:
            return
        server_url = self._normalize_online_url(address, default_scheme="http")
        if server_url:
            self._join_game_at_server(server_url, "Join LAN Game")

    def _join_game_at_server(self, server_url: str, title: str) -> None:
        code = simpledialog.askstring(
            title,
            "Enter the six-digit room code:",
            parent=self,
        )
        if code is None:
            return
        code = code.strip()
        if not re.fullmatch(r"[0-9]{6}", code):
            messagebox.showerror(
                "Invalid Room Code",
                "Room codes contain exactly six digits.",
                parent=self,
            )
            return
        name = simpledialog.askstring(
            title,
            "Enter your player name:",
            initialvalue="Player",
            parent=self,
        )
        if name is None:
            return
        query = urlencode({"join": code, "name": name.strip() or "Player"})
        self._launch_online_window(f"{server_url}/?{query}")

    def _setup_rules_text(self, deck_size: int) -> str:
        last = deck_size
        lines = [
            f"Max HP = 2x starting. Last card ({last}) = Mercy "
            f"({FIFTH_CARD_HEAL} heal any target).",
            f"Deck size {DECK_SIZE_MIN}-{DECK_SIZE_MAX}.",
        ]
        if allows_duplicate_archetypes(deck_size):
            lines.append(
                "12+ cards: duplicate types allowed "
                "(Steal / Heavy Hit / Shield / Poison still one each)."
            )
        else:
            lines.append(
                "Under 12 cards: each type is unique "
                "(duplicates unlock at 12+). Names change every 10% damage."
            )
        return "\n".join(lines)

    def _refresh_setup_rules(self) -> None:
        if getattr(self, "_setup_rules_label", None) is None:
            return
        try:
            if not self._setup_rules_label.winfo_exists():
                return
        except tk.TclError:
            return
        self._set_menu_text(
            self._setup_rules_label,
            self._setup_rules_text(int(self.deck_size_var.get())),
            wraplength=720,
        )

    def _deck_size_up(self) -> None:
        value = clamp_deck_size(int(self.deck_size_var.get()) + 1)
        self.deck_size_var.set(value)
        self._refresh_setup_rules()

    def _deck_size_down(self) -> None:
        value = clamp_deck_size(int(self.deck_size_var.get()) - 1)
        self.deck_size_var.set(value)
        self._refresh_setup_rules()

    def _on_game_mode_changed(self, _event: tk.Event | None = None) -> None:
        self.game_mode = self.game_mode_var.get()
        party = self.game_mode == "Party"
        player_counts = (
            [f"{count} players" for count in range(2, 5)]
            if party
            else ["1 — vs bot"] + [
                f"{count} players" for count in range(2, PLAYER_COUNT_MAX + 1)
            ]
        )
        self._player_count_picker.configure(values=player_counts)
        if self.mode_var.get() not in player_counts:
            self.mode_var.set(player_counts[0])
        for widget in self._party_setup_widgets:
            if party:
                widget.grid_remove()
            else:
                widget.grid()
        self._set_menu_text(
            self._setup_rules_label,
            (
                "Party: choose a piece, rotation, and legal column; each piece drops "
                "onto the shared 6×30 board. Players lock placements privately, then "
                "reveal together. Duels settle overlaps. Race and claim ranks award "
                "5 / 3 / 2 / 0 points."
                if party
                else self._setup_rules_text(int(self.deck_size_var.get()))
            ),
            wraplength=720,
        )
        self._setup_start_button.set_text(
            "Start Party" if party else "Continue to Card Lab"
        )

    def begin_card_lab(self) -> None:
        if self.game_mode_var.get() == "Party":
            count = int(self.mode_var.get().split()[0])
            play_sfx(SFX_UI_CLICK)
            self.game_mode = "Party"
            self.settings = MatchSettings(
                count, DEFAULT_STARTING_HP, DEFAULT_POWER_POINTS, DECK_SIZE
            )
            self.starting_hp = DEFAULT_STARTING_HP
            self.crafted = []
            self.all_player_decks = []
            self.player_names = []
            self.crafting_player = 1
            self.craft_slot = 1
            self._collect_party_name(1)
            return

        try:
            hp = int(self.hp_var.get().strip())
            pp = int(self.pp_var.get().strip())
            deck_size = int(self.deck_size_var.get())
        except ValueError:
            play_sfx(SFX_DENY)
            messagebox.showerror(
                "Invalid input", "HP, power points, and max cards must be numbers."
            )
            return
        if not (HP_MIN <= hp <= HP_MAX):
            play_sfx(SFX_DENY)
            messagebox.showerror("Invalid HP", f"Starting HP must be {HP_MIN}-{HP_MAX}.")
            return
        if not (PP_MIN <= pp <= PP_MAX):
            play_sfx(SFX_DENY)
            messagebox.showerror(
                "Invalid PP", f"Power points must be {PP_MIN}-{PP_MAX}."
            )
            return
        if not (DECK_SIZE_MIN <= deck_size <= DECK_SIZE_MAX):
            play_sfx(SFX_DENY)
            messagebox.showerror(
                "Invalid deck size",
                f"Max cards must be {DECK_SIZE_MIN}-{DECK_SIZE_MAX}.",
            )
            return

        play_sfx(SFX_UI_CLICK)
        mode = self.mode_var.get()
        count = int(mode.split()[0])
        self.settings = MatchSettings(count, hp, pp, deck_size)
        self.game_mode = "Standard"
        self.starting_hp = hp
        self.crafted = []
        self.all_player_decks = []
        self.player_names = []
        self.crafting_player = 1
        self.craft_slot = 1
        self.show_craft()

    def show_craft(self) -> None:
        self._screen = "craft"
        assert self.settings is not None
        self.clear()
        deck_size = self.settings.deck_size
        if self.craft_slot >= deck_size:
            self.crafted.append(make_mercy_card(deck_size, self.crafted))
            play_sfx(SFX_MERCY_ADD)
            if self.settings.vs_bot:
                self._ask_player_name(1, self.start_match)
            else:
                self._finish_player_craft()
            return

        pp = self.settings.power_points
        craftable_size = max(1, deck_size - 1)
        if self.settings.vs_bot:
            lab_title = f"Card Lab — Card {self.craft_slot}/{craftable_size}"
            lab_hint = (
                f"Spend exactly {pp} power points (damage + heal)."
            )
        else:
            lab_title = (
                f"Card Lab — player-{self.crafting_player} "
                f"— Card {self.craft_slot}/{craftable_size}"
            )
            lab_hint = (
                f"player-{self.crafting_player}, spend exactly {pp} power points "
                f"(damage + heal). Craftable cards are shuffled and re-dealt when "
                f"everyone is done. Mercy and unique-effect cards stay with their owner."
            )
        theme = _theme()
        tint = theme.screen_bg
        lab = self._open_menu_panel(tint)
        self._menu_text(
            lab,
            lab_title,
            tint,
            fg=theme.title_fg,
            size=32,
            bold=True,
        )
        ThemedArtButton(
            lab,
            "Reset Game",
            command=self._reset_game,
            width=180,
            height=44,
            palette="heavy_hit",
        ).pack(pady=(8, 4))
        deck_io = self._wallpaper_frame(lab, tint)
        deck_io.pack(pady=(0, 6))
        ThemedArtButton(
            deck_io,
            "Export Deck",
            command=self._export_deck,
            width=160,
            height=40,
            palette="selected",
        ).pack(side="left", padx=6)
        ThemedArtButton(
            deck_io,
            "Import Deck",
            command=self._import_deck,
            width=160,
            height=40,
            palette="normal",
        ).pack(side="left", padx=6)
        ThemedArtButton(
            deck_io,
            "Random 6-Unique Deck",
            command=self._randomize_crafted_deck,
            width=220,
            height=40,
            palette="heavy_hit",
            text_scale=0.8,
        ).pack(side="left", padx=6)
        type_hint = (
            f"Duplicate types allowed (deck 12+); "
            f"uniques still one each; max {MAX_UNIQUE_CARDS_IN_DECK} unique cards in a 10-card deck."
            if self.settings.allow_duplicate_archetypes
            else f"No duplicate types (names change every 10% damage); max {MAX_UNIQUE_CARDS_IN_DECK} unique cards in a 10-card deck."
        )
        self._menu_text(
            lab,
            f"{lab_hint} {type_hint}",
            tint,
            fg=theme.body_fg,
            size=16,
            wraplength=800,
            pady=(8, 12),
        )

        if self.crafted:
            self._menu_text(
                lab,
                "Deck so far — click a card to remove it:",
                tint,
                fg=theme.body_fg,
                size=16,
                pady=(0, 4),
            )
            deck_row = self._wallpaper_frame(lab, tint)
            deck_width = max(320, min(880, self.container.winfo_width() - 64))
            deck_row.configure(width=deck_width)
            deck_row.pack(pady=(0, 8))
            deck_row.grid_propagate(False)
            columns = max(1, min(8, (deck_width + 12) // (DECK_MINI_W + 12)))
            rows = (len(self.crafted) + columns - 1) // columns
            deck_row.configure(
                height=rows * int(DECK_MINI_W * CARD_ASPECT) + rows * 8
            )
            for column in range(columns):
                deck_row.grid_columnconfigure(column, weight=1)
            for index, card in enumerate(self.crafted):
                face = RoundedCardButton(
                    deck_row,
                    card,
                    command=lambda card_index=index: self._remove_crafted_card(
                        card_index
                    ),
                    width=DECK_MINI_W,
                )
                face.grid(
                    row=index // columns,
                    column=index % columns,
                    padx=6,
                    pady=4,
                )

        self.steal_var = tk.BooleanVar(value=False)
        self.heavy_hit_var = tk.BooleanVar(value=False)
        self.shield_var = tk.BooleanVar(value=False)
        self.poison_var = tk.BooleanVar(value=False)
        self.lava_var = tk.BooleanVar(value=False)
        self.reaper_var = tk.BooleanVar(value=False)
        self.vampire_var = tk.BooleanVar(value=False)
        self.cure_var = tk.BooleanVar(value=False)
        self.freeze_var = tk.BooleanVar(value=False)
        self.gamble_var = tk.BooleanVar(value=False)
        self._shield_pick = None

        unique_row = self._wallpaper_frame(lab, tint)
        unique_row.pack(pady=(0, 10))
        any_unique = False

        if can_add_steal_card(self.crafted, pp) and not self.settings.vs_bot:
            UniquePickCard(
                unique_row,
                "Steal",
                variable=self.steal_var,
                command=self._on_steal_toggle,
                palette="steal",
                bg=tint,
            ).pack(side="left", padx=8)
            any_unique = True
        elif deck_has_steal(self.crafted):
            UniquePickCard(
                unique_row,
                "Steal",
                variable=tk.BooleanVar(value=True),
                palette="disabled",
                bg=tint,
                locked=True,
            ).pack(side="left", padx=8)
            any_unique = True

        if can_add_heavy_hit_card(self.crafted):
            UniquePickCard(
                unique_row,
                "Heavy Hit",
                variable=self.heavy_hit_var,
                command=self._on_heavy_hit_toggle,
                palette="heavy_hit",
                bg=tint,
            ).pack(side="left", padx=8)
            any_unique = True
        elif deck_has_heavy_hit(self.crafted):
            UniquePickCard(
                unique_row,
                "Heavy Hit",
                variable=tk.BooleanVar(value=True),
                palette="disabled",
                bg=tint,
                locked=True,
            ).pack(side="left", padx=8)
            any_unique = True

        if can_add_shield_card(self.crafted, pp):
            self._shield_pick = UniquePickCard(
                unique_row,
                "Shield",
                variable=self.shield_var,
                command=self._on_shield_toggle,
                palette="selected",
                bg=tint,
            )
            self._shield_pick.pack(side="left", padx=8)
            any_unique = True
        elif deck_has_shield(self.crafted):
            self._shield_pick = None
            UniquePickCard(
                unique_row,
                "Shield",
                variable=tk.BooleanVar(value=True),
                palette="disabled",
                bg=tint,
                locked=True,
            ).pack(side="left", padx=8)
            any_unique = True
        else:
            self._shield_pick = None

        if can_add_poison_card(self.crafted):
            UniquePickCard(
                unique_row,
                "Poison",
                variable=self.poison_var,
                command=self._on_poison_toggle,
                palette="poison",
                bg=tint,
            ).pack(side="left", padx=8)
            any_unique = True
        elif deck_has_poison(self.crafted):
            UniquePickCard(
                unique_row,
                "Poison",
                variable=tk.BooleanVar(value=True),
                palette="disabled",
                bg=tint,
                locked=True,
            ).pack(side="left", padx=8)
            any_unique = True

        if can_add_vampire_card(self.crafted):
            UniquePickCard(
                unique_row,
                "Vampire",
                variable=self.vampire_var,
                command=self._on_vampire_toggle,
                palette="poison",
                bg=tint,
            ).pack(side="left", padx=8)
            any_unique = True
        else:
            UniquePickCard(
                unique_row,
                "Vampire",
                variable=tk.BooleanVar(value=True),
                palette="disabled",
                bg=tint,
                locked=True,
            ).pack(side="left", padx=8)
            any_unique = True
        UniquePickCard(
            unique_row,
            "Floor is Lava",
            variable=self.lava_var,
            command=self._on_lava_toggle,
            palette="selected",
            bg=tint,
        ).pack(side="left", padx=8)
        any_unique = True
        UniquePickCard(
            unique_row,
            "Reaper",
            variable=self.reaper_var,
            command=self._on_reaper_toggle,
            palette="selected",
            bg=tint,
        ).pack(side="left", padx=8)
        any_unique = True
        UniquePickCard(
            unique_row,
            "Cure",
            variable=self.cure_var,
            command=self._on_cure_toggle,
            palette="selected",
            bg=tint,
        ).pack(side="left", padx=8)
        any_unique = True
        UniquePickCard(
            unique_row,
            "Freeze",
            variable=self.freeze_var,
            command=self._on_freeze_toggle,
            palette="selected",
            bg=tint,
        ).pack(side="left", padx=8)
        any_unique = True
        UniquePickCard(
            unique_row,
            "Gamble",
            variable=self.gamble_var,
            command=self._on_gamble_toggle,
            palette="selected",
            bg=tint,
        ).pack(side="left", padx=8)
        any_unique = True

        if not any_unique:
            unique_row.pack_forget()

        budget = stat_budget(
            pp, self.steal_var.get(), shields=self.shield_var.get()
        )
        self.damage_var = tk.IntVar(value=budget // 2 if budget else 0)
        row = self._wallpaper_frame(lab, tint)
        row.pack(pady=8)
        ttk.Label(row, text="Damage points", style="SetupBody.TLabel").pack(side="left")
        self._craft_scale = ttk.Scale(
            row,
            from_=0,
            to=max(0, budget),
            orient="horizontal",
            length=480,
            style="Green.Horizontal.TScale",
            command=self._on_damage_slide,
        )
        self._craft_scale.pack(side="left", padx=12)

        preview_row = self._wallpaper_frame(lab, tint)
        preview_row.pack(pady=12)
        placeholder = Card(self.craft_slot, "Allrounder", 0, 0)
        self.preview = RoundedCardButton(
            preview_row,
            placeholder,
            command=self.save_crafted_card,
            width=PREVIEW_CARD_W,
        )
        self.preview.pack()
        self.preview_status = ttk.Label(
            lab, text="Click the card to save it.", style="SetupBody.TLabel"
        )
        self.preview_status.pack(pady=(8, 0))

        if budget:
            self._craft_scale.set(budget // 2)
        else:
            self._on_damage_slide("0")

    def _remove_crafted_card(self, card_index: int) -> None:
        if not 0 <= card_index < len(self.crafted):
            return
        self.crafted.pop(card_index)
        for slot, card in enumerate(self.crafted, start=1):
            card.id = slot
        self.craft_slot = len(self.crafted) + 1
        self._craft_scale = None
        play_sfx(SFX_UI_CLICK)
        self.show_craft()

    def _craft_budget(self) -> int:
        assert self.settings is not None
        if (
            self.lava_var.get()
            or self.reaper_var.get()
            or self.cure_var.get()
            or self.freeze_var.get()
            or self.gamble_var.get()
        ):
            return 0
        return stat_budget(
            self.settings.power_points,
            self.steal_var.get(),
            shields=self.shield_var.get(),
        )

    def _on_steal_toggle(self) -> None:
        if self.steal_var.get():
            self.heavy_hit_var.set(False)
            self.shield_var.set(False)
            self.poison_var.set(False)
            self.lava_var.set(False)
            self.reaper_var.set(False)
            self.vampire_var.set(False)
            self.cure_var.set(False)
        self._refresh_craft_slider()

    def _on_heavy_hit_toggle(self) -> None:
        if self.heavy_hit_var.get():
            self.steal_var.set(False)
            self.shield_var.set(False)
            self.poison_var.set(False)
            self.lava_var.set(False)
            self.reaper_var.set(False)
            self.vampire_var.set(False)
            self.cure_var.set(False)
        self._refresh_craft_slider()

    def _on_shield_toggle(self) -> None:
        if self.shield_var.get():
            self.steal_var.set(False)
            self.heavy_hit_var.set(False)
            self.poison_var.set(False)
            self.lava_var.set(False)
            self.reaper_var.set(False)
            self.vampire_var.set(False)
            self.cure_var.set(False)
            # Shield cards have no damage or healing stats.
            self.damage_var.set(0)
            if self._craft_scale is not None:
                self._craft_scale.set(0)
        self._refresh_craft_slider()

    def _on_poison_toggle(self) -> None:
        if self.poison_var.get():
            self.steal_var.set(False)
            self.heavy_hit_var.set(False)
            self.shield_var.set(False)
            self.lava_var.set(False)
            self.reaper_var.set(False)
            self.vampire_var.set(False)
            self.cure_var.set(False)
            # Poison is damage-only — snap to full damage.
            budget = self._craft_budget()
            self.damage_var.set(budget)
            if self._craft_scale is not None:
                self._craft_scale.set(budget)
        self._refresh_craft_slider()

    def _on_lava_toggle(self) -> None:
        if self.lava_var.get():
            self.steal_var.set(False)
            self.heavy_hit_var.set(False)
            self.shield_var.set(False)
            self.poison_var.set(False)
            self.reaper_var.set(False)
            self.vampire_var.set(False)
            self.cure_var.set(False)
        self._refresh_craft_slider()

    def _on_reaper_toggle(self) -> None:
        if self.reaper_var.get():
            self.steal_var.set(False)
            self.heavy_hit_var.set(False)
            self.shield_var.set(False)
            self.poison_var.set(False)
            self.lava_var.set(False)
            self.vampire_var.set(False)
            self.cure_var.set(False)
        self._refresh_craft_slider()

    def _on_cure_toggle(self) -> None:
        if self.cure_var.get():
            self.steal_var.set(False)
            self.heavy_hit_var.set(False)
            self.shield_var.set(False)
            self.poison_var.set(False)
            self.lava_var.set(False)
            self.reaper_var.set(False)
            self.vampire_var.set(False)
        self._refresh_craft_slider()

    def _on_freeze_toggle(self) -> None:
        if self.freeze_var.get():
            for variable in (
                self.steal_var,
                self.heavy_hit_var,
                self.shield_var,
                self.poison_var,
                self.lava_var,
                self.reaper_var,
                self.vampire_var,
                self.cure_var,
                self.gamble_var,
            ):
                variable.set(False)
        self._refresh_craft_slider()

    def _on_gamble_toggle(self) -> None:
        if self.gamble_var.get():
            for variable in (
                self.steal_var,
                self.heavy_hit_var,
                self.shield_var,
                self.poison_var,
                self.lava_var,
                self.reaper_var,
                self.vampire_var,
                self.cure_var,
                self.freeze_var,
            ):
                variable.set(False)
        self._refresh_craft_slider()

    def _on_vampire_toggle(self) -> None:
        if self.vampire_var.get():
            self.steal_var.set(False)
            self.heavy_hit_var.set(False)
            self.shield_var.set(False)
            self.poison_var.set(False)
            self.lava_var.set(False)
            self.reaper_var.set(False)
            self.cure_var.set(False)
        self._refresh_craft_slider()

    def _refresh_craft_slider(self) -> None:
        if self._craft_scale is None:
            return
        if any(
            variable.get()
            for variable in (
                self.steal_var,
                self.heavy_hit_var,
                self.shield_var,
                self.poison_var,
                self.lava_var,
                self.reaper_var,
                self.vampire_var,
                self.cure_var,
            )
        ):
            self.freeze_var.set(False)
            self.gamble_var.set(False)
        budget = self._craft_budget()
        self._craft_scale.configure(to=max(0, budget))
        damage = min(self.damage_var.get(), budget)
        if self.shield_var.get():
            damage = 0
        elif self.poison_var.get():
            damage = budget
        elif self.lava_var.get():
            damage = 0
        elif (
            self.reaper_var.get()
            or self.cure_var.get()
            or self.freeze_var.get()
            or self.gamble_var.get()
        ):
            damage = 0
        self.damage_var.set(damage)
        if budget:
            self._craft_scale.set(damage)
        self._on_damage_slide(str(damage))

    def _on_damage_slide(self, value: str) -> None:
        assert self.settings is not None
        preview_ok = self.preview is not None and self.preview.winfo_exists()
        status_ok = (
            self.preview_status is not None and self.preview_status.winfo_exists()
        )
        if not preview_ok or not status_ok:
            return
        budget = self._craft_budget()
        damage = int(float(value))
        damage = max(0, min(budget, damage))
        if self.shield_var.get() and damage > 0:
            self.shield_var.set(False)
        if self.poison_var.get() and damage < budget:
            self.poison_var.set(False)
        lava = self.lava_var.get()
        reaper = self.reaper_var.get()
        vampire = self.vampire_var.get()
        cure = self.cure_var.get()
        freeze = self.freeze_var.get()
        gamble = self.gamble_var.get()
        shields = self.shield_var.get()
        heal = 0 if shields else budget - damage
        self.damage_var.set(damage)
        archetype = name_for_split(damage, heal, budget if budget else 1)
        heavy_hit = self.heavy_hit_var.get()
        steals = self.steal_var.get()
        poisons = self.poison_var.get()
        if heavy_hit:
            name = "Heavy Hit"
        elif shields:
            name = "Shield"
        elif poisons:
            name = "Poison"
        elif lava:
            name = "Floor is Lava"
        elif reaper:
            name = "Reaper"
        elif vampire:
            name = "Vampire"
        elif cure:
            name = "Cure"
        elif freeze:
            name = "Freeze"
        elif gamble:
            name = "Gamble"
        else:
            name = archetype
        card = Card(
            id=self.craft_slot,
            name=name,
            damage=damage,
            heal=heal,
            steals=steals,
            heavy_hit=heavy_hit,
            shields=shields,
            poisons=poisons,
            lava=lava,
            reaper=reaper,
            vampire=vampire,
            cure=cure,
            freeze=freeze,
            gamble=gamble,
        )
        taken = archetype_taken(name, self.crafted)
        block_dupe = taken and not self.settings.allow_duplicate_archetypes
        if heavy_hit and deck_has_heavy_hit(self.crafted):
            block_dupe = True
        if steals and deck_has_steal(self.crafted):
            block_dupe = True
        if shields and deck_has_shield(self.crafted):
            block_dupe = True
        if poisons and deck_has_poison(self.crafted):
            block_dupe = True
        if lava and any(c.lava for c in self.crafted):
            block_dupe = True
        if reaper and any(c.reaper for c in self.crafted):
            block_dupe = True
        if vampire and deck_has_vampire(self.crafted):
            block_dupe = True
        if cure and any(c.cure for c in self.crafted):
            block_dupe = True
        if freeze and any(c.freeze for c in self.crafted):
            block_dupe = True
        if gamble and any(c.gamble for c in self.crafted):
            block_dupe = True
        if (
            self.settings.deck_size == DECK_SIZE
            and any(
                (
                    steals,
                    heavy_hit,
                    shields,
                    poisons,
                    lava,
                    reaper,
                    vampire,
                    cure,
                    freeze,
                    gamble,
                )
            )
            and unique_card_total(self.crafted) >= MAX_UNIQUE_CARDS_IN_DECK
        ):
            block_dupe = True
        if shields and damage > 0:
            block_dupe = True
        if poisons and heal > 0:
            block_dupe = True
        self.preview.set_card(card, disabled=block_dupe)
        if block_dupe:
            if heavy_hit and deck_has_heavy_hit(self.crafted):
                msg = "Heavy Hit already in deck (attribute — one only)."
            elif steals and deck_has_steal(self.crafted):
                msg = "Steal already in deck (attribute — one only)."
            elif shields and deck_has_shield(self.crafted):
                msg = "Shield already in deck (attribute — one only)."
            elif poisons and deck_has_poison(self.crafted):
                msg = "Poison already in deck (attribute — one only)."
            elif lava and any(c.lava for c in self.crafted):
                msg = "Floor is Lava already in deck (one only)."
            elif reaper and any(c.reaper for c in self.crafted):
                msg = "Reaper already in deck (one only)."
            elif vampire and deck_has_vampire(self.crafted):
                msg = "Vampire already in deck (one only)."
            elif cure and any(c.cure for c in self.crafted):
                msg = "Cure already in deck (one only)."
            elif freeze and any(c.freeze for c in self.crafted):
                msg = "Freeze already in deck (one only)."
            elif gamble and any(c.gamble for c in self.crafted):
                msg = "Gamble already in deck (one only)."
            elif (
                self.settings.deck_size == DECK_SIZE
                and any(
                    (
                        steals,
                        heavy_hit,
                        shields,
                        poisons,
                        lava,
                        reaper,
                        vampire,
                        cure,
                        freeze,
                        gamble,
                    )
                )
                and unique_card_total(self.crafted) >= MAX_UNIQUE_CARDS_IN_DECK
            ):
                msg = f"A {DECK_SIZE}-card deck allows only {MAX_UNIQUE_CARDS_IN_DECK} unique cards."
            elif shields and damage > 0:
                msg = "Shield requires 0 damage (heal only)."
            elif poisons and heal > 0:
                msg = "Poison requires 0 heal (damage only)."
            else:
                msg = "Already in deck — pick another split."
            self.preview_status.configure(text=msg)
            self.preview.set_card(card, disabled=True)
        else:
            if taken and self.settings.allow_duplicate_archetypes:
                self.preview_status.configure(
                    text="Duplicate type allowed (deck above 7). Click the card to save it."
                )
            else:
                self.preview_status.configure(text="Click the card to save it.")
            self.preview.set_card(card, disabled=False)

    def _export_deck(self) -> None:
        assert self.settings is not None
        if not self.crafted and self.craft_slot <= 1:
            messagebox.showinfo(
                "Export Deck",
                "Craft at least one card before exporting a deck.",
            )
            return
        decks_dir = default_decks_dir(PROJECT_ROOT)
        decks_dir.mkdir(parents=True, exist_ok=True)
        path = filedialog.asksaveasfilename(
            title="Export deck",
            initialdir=str(decks_dir),
            defaultextension=".json",
            filetypes=[("Crash Out deck", "*.json"), ("All files", "*.*")],
            initialfile="my_deck.json",
        )
        if not path:
            return
        name = Path(path).stem.replace("_", " ").strip() or "Saved Deck"
        payload = build_deck_export(
            self.crafted,
            power_points=self.settings.power_points,
            deck_size=self.settings.deck_size,
            name=name,
        )
        try:
            saved = save_deck_file(path, payload)
        except OSError as exc:
            messagebox.showerror("Export failed", str(exc))
            return
        play_sfx(SFX_CRAFT)
        messagebox.showinfo(
            "Deck exported",
            f"Saved {payload['deck_size']} cards to:\n{saved}",
        )

    def _import_deck(self) -> None:
        assert self.settings is not None
        decks_dir = default_decks_dir(PROJECT_ROOT)
        decks_dir.mkdir(parents=True, exist_ok=True)
        path = filedialog.askopenfilename(
            title="Import deck",
            initialdir=str(decks_dir),
            filetypes=[("Crash Out deck", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            data = load_deck_file(path)
            cards, power_points, deck_name = validate_deck_export(data)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            messagebox.showerror("Import failed", str(exc))
            return

        # Keep match deck size; load craftables and continue Card Lab after them.
        target_size = self.settings.deck_size
        craft_slots = max(0, target_size - 1)
        craftables = [c for c in cards if not c.heal_any]
        notes: list[str] = []
        if power_points != self.settings.power_points:
            notes.append(
                f"Power points will change from {self.settings.power_points} to {power_points}."
            )
        if len(craftables) > craft_slots:
            notes.append(
                f"Only the first {craft_slots} craftable cards fit this match "
                f"(max cards {target_size}, including Mercy)."
            )
            craftables = craftables[:craft_slots]
        remaining = craft_slots - len(craftables)
        if remaining > 0:
            notes.append(
                f"You can keep crafting {remaining} more card(s) after the import."
            )
        else:
            notes.append("Deck is full — Mercy will be added and crafting will finish.")
        if self.crafted:
            notes.append("Your current unfinished cards will be replaced.")
        prompt = (
            f"Import '{deck_name}' ({len(craftables)} craftable card(s), "
            f"{power_points} PP) into a {target_size}-card deck?"
        )
        if notes:
            prompt += "\n\n" + "\n".join(notes)
        if not messagebox.askyesno("Import Deck", prompt):
            return

        self.settings.power_points = power_points
        for i, card in enumerate(craftables, start=1):
            card.id = i
            card.borrowed_from = None
            card.cooldown_remaining = 0
        self.crafted = list(craftables)
        self.craft_slot = len(self.crafted) + 1
        play_sfx(SFX_CRAFT)
        self.show_craft()

    def _randomize_crafted_deck(self) -> None:
        assert self.settings is not None
        craftable_slots = self.settings.deck_size - 1
        if craftable_slots < MAX_UNIQUE_CARDS_IN_DECK:
            play_sfx(SFX_DENY)
            messagebox.showwarning(
                "Deck too small",
                f"A random deck needs at least {MAX_UNIQUE_CARDS_IN_DECK + 1} cards "
                "to include six unique cards plus Mercy.",
            )
            return
        if self.crafted and not messagebox.askyesno(
            "Randomize deck",
            "Replace your current unfinished cards with a random six-unique deck?",
        ):
            return

        pp = self.settings.power_points
        cards = self._make_random_crafted_deck(
            pp,
            vs_bot=self.settings.vs_bot,
            deck_size=self.settings.deck_size,
        )
        self.crafted = cards
        self.craft_slot = self.settings.deck_size
        self._craft_scale = None
        self._show_random_deck_roll(cards)

    def _make_random_crafted_deck(
        self,
        power_points: int,
        *,
        vs_bot: bool,
        deck_size: int,
    ) -> list[Card]:
        pp = power_points
        craftable_slots = deck_size - 1
        special_flags = [
            "heavy_hit",
            "shields",
            "poisons",
            "lava",
            "reaper",
            "vampire",
            "cure",
            "freeze",
            "gamble",
        ]
        if not vs_bot and pp > STEAL_PP_COST:
            special_flags.append("steals")
        chosen_specials = random.sample(special_flags, MAX_UNIQUE_CARDS_IN_DECK)
        cards: list[Card] = []

        for slot, flag in enumerate(chosen_specials, start=1):
            damage = 0
            if flag == "steals":
                damage = random.randint(0, stat_budget(pp, True))
            elif flag == "heavy_hit":
                damage = random.randint(0, pp)
            elif flag == "poisons":
                damage = pp
            elif flag == "vampire":
                damage = random.randint(1, pp)
            card = craft_card(
                slot,
                damage,
                pp,
                cards,
                **{flag: True},
                deck_size=deck_size,
            )
            cards.append(card)

        for slot in range(len(cards) + 1, craftable_slots + 1):
            used_archetypes = {card_archetype(card) for card in cards}
            buckets = list(range(11))
            if not allows_duplicate_archetypes(deck_size):
                buckets = [
                    bucket
                    for bucket in buckets
                    if name_for_split(
                        round(pp * bucket / 10),
                        pp - round(pp * bucket / 10),
                        pp,
                    )
                    not in used_archetypes
                ]
            bucket = random.choice(buckets or list(range(11)))
            damage = round(pp * bucket / 10)
            card = craft_card(
                slot,
                damage,
                pp,
                cards,
                deck_size=deck_size,
            )
            cards.append(card)
        return cards

    def _show_random_deck_roll(
        self,
        cards: list[Card],
        *,
        title: str = "RANDOM DECK",
        final_status: str = "DECK LOCKED",
        on_complete: Callable[[], None] | None = None,
        finish_sfx: str = SFX_CRAFT,
    ) -> None:
        self.clear()
        theme = _theme()
        panel = tk.Frame(
            self._ui,
            bg=theme.panel_bg,
            highlightbackground=theme.panel_border,
            highlightthickness=3,
            padx=30,
            pady=24,
        )
        panel.pack(expand=True)
        tk.Label(
            panel,
            text=title,
            bg=theme.panel_bg,
            fg=theme.title_fg,
            font=(_font_family(), 22, "bold"),
        ).pack(pady=(0, 8))
        tk.Label(
            panel,
            text="Rolling your cards...",
            bg=theme.panel_bg,
            fg=theme.body_fg,
            font=(_font_family(), 13),
        ).pack(pady=(0, 14))

        reels = tk.Frame(panel, bg=theme.panel_bg)
        reels.pack()
        reel_faces: list[RoundedCardButton] = []
        for index in range(3):
            face = RoundedCardButton(
                reels,
                cards[(index + 1) % len(cards)],
                width=128,
                command=None,
            )
            face.pack(side="left", padx=10)
            reel_faces.append(face)

        status = tk.Label(
            panel,
            text="",
            bg=theme.panel_bg,
            fg=theme.title_fg,
            font=(_font_family(), 15, "bold"),
        )
        status.pack(pady=(12, 0))
        stop_steps = (8, 11, 14)

        def roll(step: int = 0) -> None:
            for index, face in enumerate(reel_faces):
                if step < stop_steps[index]:
                    face.set_card(cards[(step * 3 + index) % len(cards)])
                elif step == stop_steps[index]:
                    face.set_card(cards[index % len(cards)])

            if step < max(stop_steps):
                self.after(45 + step * 5, lambda: roll(step + 1))
                return

            status.configure(text=final_status)

            def finish_roll() -> None:
                play_sfx(finish_sfx)
                if on_complete is not None:
                    on_complete()
                else:
                    self.show_craft()

            self.after(500, finish_roll)

        roll()

    def save_crafted_card(self) -> None:
        assert self.settings is not None
        damage = self.damage_var.get()
        steals = self.steal_var.get()
        heavy_hit = self.heavy_hit_var.get()
        shields = self.shield_var.get()
        poisons = self.poison_var.get()
        lava = self.lava_var.get()
        reaper = self.reaper_var.get()
        vampire = self.vampire_var.get()
        cure = self.cure_var.get()
        freeze = self.freeze_var.get()
        gamble = self.gamble_var.get()
        try:
            card = craft_card(
                self.craft_slot,
                damage,
                self.settings.power_points,
                self.crafted,
                steals=steals,
                heavy_hit=heavy_hit,
                shields=shields,
                poisons=poisons,
                lava=lava,
                reaper=reaper,
                vampire=vampire,
                cure=cure,
                freeze=freeze,
                gamble=gamble,
                deck_size=self.settings.deck_size,
            )
        except ValueError as exc:
            play_sfx(SFX_DENY)
            messagebox.showwarning("Invalid card", str(exc))
            return
        play_sfx(SFX_CRAFT)
        self.crafted.append(card)
        self.craft_slot += 1
        self._craft_scale = None
        self.show_craft()

    def _finish_player_craft(self) -> None:
        assert self.settings is not None
        self._ask_player_name(self.crafting_player, self._complete_player_craft)

    def _complete_player_craft(self) -> None:
        assert self.settings is not None
        self.all_player_decks.append(list(self.crafted))
        self.crafted = []
        self.craft_slot = 1
        if self.crafting_player < self.settings.player_count:
            self.crafting_player += 1
            self.show_craft()
        else:
            self.start_match()

    def start_match(self) -> None:
        assert self.settings is not None
        if self.settings.vs_bot:
            bot_deck = make_bot_deck(
                self.settings.power_points, self.settings.deck_size
            )
            self.players = make_solo_players(
                self.crafted, bot_deck, self.settings.starting_hp
            )
        else:
            self.players = make_players_from_mixed_decks(
                self.all_player_decks, self.settings.starting_hp
            )
        for i, name in enumerate(self.player_names):
            if i < len(self.players):
                self.players[i].name = name
        starting_player = random.choice(self.players)
        self.active = self.players.index(starting_player)
        self.pending_card = None
        self.pending_target_idx = None
        self._borrows = []
        self._game_log = []
        self._match_started_at = time.monotonic()
        self._stop_match_timer()
        if self.settings.vs_bot:
            play_sfx(SFX_MATCH_START)
        else:
            play_sfx(SFX_DEAL)
            play_sfx(SFX_MATCH_START, delay_ms=220)
        start_bgm()
        self._start_player_roll(self.active)

    def _ask_player_name(
        self, player_number: int, on_submit: Callable[[], None]
    ) -> None:
        self._screen = "name"
        self.clear()
        default_name = f"player-{player_number}"
        theme = _theme()
        panel = tk.Frame(
            self._ui,
            bg=theme.panel_bg,
            highlightbackground=theme.panel_border,
            highlightthickness=3,
            padx=34,
            pady=28,
        )
        panel.pack(expand=True)
        tk.Label(
            panel,
            text=f"PLAYER {player_number} NAME",
            bg=theme.panel_bg,
            fg=theme.title_fg,
            font=(_font_family(), 20, "bold"),
        ).pack(pady=(0, 10))
        tk.Label(
            panel,
            text=f"Enter your name, or leave blank to use {default_name}.",
            bg=theme.panel_bg,
            fg=theme.body_fg,
            font=(_font_family(), 12),
        ).pack(pady=(0, 12))

        name_var = tk.StringVar()
        name_entry = ttk.Entry(
            panel,
            textvariable=name_var,
            width=24,
            font=(_font_family(), 16),
            style="Setup.TEntry",
        )
        name_entry.pack(pady=(0, 14))

        def submit(event: tk.Event | None = None) -> str | None:
            self.player_names.append(name_var.get().strip() or default_name)
            on_submit()
            return "break" if event is not None else None

        name_entry.bind("<Return>", submit)
        ThemedArtButton(
            panel,
            "Continue",
            command=submit,
            width=180,
            height=48,
            palette="selected",
        ).pack()
        self.after_idle(name_entry.focus_set)

    def _collect_party_name(self, player_number: int) -> None:
        self._ask_player_name(
            player_number,
            lambda: self._continue_party_names(player_number),
        )

    def _continue_party_names(self, player_number: int) -> None:
        assert self.settings is not None
        next_player = player_number + 1
        if next_player <= self.settings.player_count:
            self._collect_party_name(next_player)
            return
        self._start_party_game()

    def _start_party_game(self) -> None:
        assert self.settings is not None
        self.players = [
            Player(
                name=name,
                hp=self.starting_hp,
                max_hp=self.starting_hp * 2,
            )
            for name in self.player_names
        ]
        self._party_racers = self.players
        self._party_board = starting_tiles(len(self._party_racers))
        self._party_claims = [0] * len(self._party_racers)
        self._party_progress = [0] * len(self._party_racers)
        self._party_finish_round = [None] * len(self._party_racers)
        self._party_blocked = set()
        self._party_round = 1
        self._party_placements = {}
        self._party_conflicts = []
        self._party_conflict_index = 0
        self._party_duel_active = False
        self._party_canvas = None
        self._party_preview = set()
        play_sfx(SFX_MATCH_START)
        self._prepare_party_round()

    def _prepare_party_round(self) -> None:
        self._party_placements = {}
        self._party_placement_order = [
            idx
            for idx in range(len(self._party_racers))
            if self._party_finish_round[idx] is None and idx not in self._party_blocked
        ]
        self._party_place_cursor = 0
        if not self._party_placement_order:
            self._finish_party_race()
            return
        self._show_party_placement()

    def _party_piece_shape(self) -> tuple[tuple[int, int], ...]:
        piece = self._party_piece_var.get()
        orientations = rotations(piece)
        rotation_idx = int(self._party_rotation_var.get().rstrip("°")) // 90
        return orientations[rotation_idx]

    def _party_legal_rotations(
        self, player_idx: int, piece: str
    ) -> list[tuple[int, tuple[tuple[int, int], ...]]]:
        return [
            (rotation_idx, shape)
            for rotation_idx, shape in enumerate(rotations(piece))
            if legal_positions(
                shape, owners=self._party_board, player_idx=player_idx
            )
        ]

    def _party_refresh_controls(self, _event: tk.Event | None = None) -> None:
        if self._screen != "party_place":
            return
        player_idx = self._party_placement_order[self._party_place_cursor]
        try:
            shape = self._party_piece_shape()
        except (KeyError, ValueError, tk.TclError):
            return
        positions = legal_positions(
            shape,
            owners=self._party_board,
            player_idx=player_idx,
        )
        columns = sorted({column for column, _ in positions})
        rows = sorted({row for _, row in positions})
        values = [str(column + 1) for column in columns]
        row_values = [str(row + 1) for row in rows]
        self._party_column_picker.configure(values=values)
        self._party_row_picker.configure(values=row_values)
        if self._party_column_var.get() not in values:
            self._party_column_var.set(values[0] if values else "")
        if self._party_row_var.get() not in row_values:
            self._party_row_var.set(row_values[0] if row_values else "")
        selected_position = None
        if values and row_values:
            selected_position = (
                int(self._party_column_var.get()) - 1,
                int(self._party_row_var.get()) - 1,
            )
        if positions and selected_position not in positions:
            if _event is not None and _event.widget is self._party_row_picker:
                matching = [
                    position
                    for position in positions
                    if position[1] == selected_position[1]
                ]
            else:
                matching = [
                    position
                    for position in positions
                    if position[0] == selected_position[0]
                ]
            selected_position = matching[0] if matching else positions[0]
            self._party_column_var.set(str(selected_position[0] + 1))
            self._party_row_var.set(str(selected_position[1] + 1))
        self._party_preview = set()
        if selected_position is not None:
            try:
                self._party_preview = place_piece(
                    shape,
                    selected_position[0],
                    selected_position[1],
                    owners=self._party_board,
                    player_idx=player_idx,
                )
            except ValueError:
                self._party_preview = set()
        self._party_place_button.state(
            ("!disabled",) if self._party_preview else ("disabled",)
        )
        self._draw_party_board()

    def _show_party_placement(self) -> None:
        self._screen = "party_place"
        self.clear()
        if self._party_place_cursor >= len(self._party_placement_order):
            self._reveal_party_placements()
            return
        player_idx = self._party_placement_order[self._party_place_cursor]
        available_pieces = [
            (piece, self._party_legal_rotations(player_idx, piece))
            for piece in TETROMINOES
        ]
        available_pieces = [
            (piece, legal_rotations)
            for piece, legal_rotations in available_pieces
            if legal_rotations
        ]
        if not available_pieces:
            self._party_blocked.add(player_idx)
            self.after_idle(self._advance_party_placement)
            return
        piece, legal_rotations = random.choice(available_pieces)
        self._party_piece_var = tk.StringVar(value=piece)
        self._party_rotation_var = tk.StringVar(
            value=f"{90 * legal_rotations[0][0]}°"
        )

        theme = _theme()
        self._ui_fill = True
        self._ui_front_wallpaper = True
        self.after_idle(self._relayout_ui)
        panel = tk.Frame(
            self._ui,
            bg=theme.panel_bg,
            highlightbackground=theme.panel_border,
            highlightthickness=3,
            padx=16,
            pady=12,
        )
        panel.pack(fill="both", expand=True)
        self._install_widget_wallpaper(panel, theme.screen_bg)
        tk.Label(
            panel,
            text=f"PARTY RACE — ROUND {self._party_round}",
            bg=theme.panel_bg,
            fg=theme.title_fg,
            font=(_font_family(), 20, "bold"),
        ).pack(pady=(0, 4))
        tk.Label(
            panel,
            text=(
                f"Pass to {self._party_racers[player_idx].name}. "
                "Your random piece is locked; choose its rotation, row, and column."
            ),
            bg=theme.panel_bg,
            fg=theme.body_fg,
            font=(_font_family(), 11),
        ).pack(pady=(0, 8))
        self._party_score_label = tk.Label(
            panel,
            text=self._party_score_text(),
            bg=theme.panel_bg,
            fg=theme.body_fg,
            font=(_font_family(), 10),
            justify="center",
            wraplength=820,
        )
        self._party_score_label.pack(pady=(0, 8))

        self._party_canvas = tk.Canvas(
            panel,
            height=250,
            bg=theme.screen_bg,
            highlightbackground=theme.panel_border,
            highlightthickness=1,
        )
        self._party_canvas.pack(fill="x", expand=True, pady=(0, 8))
        self._party_canvas.bind("<Configure>", self._draw_party_board)
        self._show_party_legend(panel)

        controls = tk.Frame(panel, bg=theme.panel_bg)
        controls.pack(pady=(0, 8))
        tk.Label(
            controls,
            text=f"Random piece: {piece}",
            bg=theme.panel_bg,
            fg=theme.body_fg,
            font=(_font_family(), 11, "bold"),
        ).grid(row=0, column=0, rowspan=2, padx=8)

        tk.Label(
            controls,
            text="Rotation",
            bg=theme.panel_bg,
            fg=theme.body_fg,
            font=(_font_family(), 11, "bold"),
        ).grid(row=0, column=1, padx=4)
        self._party_rotation_picker = ttk.Combobox(
            controls,
            textvariable=self._party_rotation_var,
            values=[f"{90 * index}°" for index, _ in legal_rotations],
            width=7,
            state="readonly",
        )
        self._party_rotation_picker.grid(row=1, column=1, padx=4)
        self._party_rotation_picker.bind(
            "<<ComboboxSelected>>", self._party_refresh_controls
        )

        tk.Label(
            controls,
            text="Column",
            bg=theme.panel_bg,
            fg=theme.body_fg,
            font=(_font_family(), 11, "bold"),
        ).grid(row=0, column=2, padx=4)
        self._party_column_var = tk.StringVar()
        self._party_column_picker = ttk.Combobox(
            controls,
            textvariable=self._party_column_var,
            width=6,
            state="readonly",
        )
        self._party_column_picker.grid(row=1, column=2, padx=4)
        self._party_column_picker.bind(
            "<<ComboboxSelected>>", self._party_refresh_controls
        )

        tk.Label(
            controls,
            text="Row",
            bg=theme.panel_bg,
            fg=theme.body_fg,
            font=(_font_family(), 11, "bold"),
        ).grid(row=0, column=3, padx=4)
        self._party_row_var = tk.StringVar()
        self._party_row_picker = ttk.Combobox(
            controls,
            textvariable=self._party_row_var,
            width=6,
            state="readonly",
        )
        self._party_row_picker.grid(row=1, column=3, padx=4)
        self._party_row_picker.bind(
            "<<ComboboxSelected>>", self._party_refresh_controls
        )

        self._party_place_button = ThemedArtButton(
            controls,
            "Lock Piece",
            command=self._lock_party_placement,
            width=160,
            height=40,
            palette="selected",
        )
        self._party_place_button.grid(row=1, column=4, padx=8)
        ThemedArtButton(
            panel,
            "Reset Game",
            command=self._reset_game,
            width=140,
            height=36,
            palette="heavy_hit",
        ).pack()
        self._party_refresh_controls()
        self.after_idle(self._draw_party_board)

    def _party_score_text(self) -> str:
        details = []
        for idx, player in enumerate(self._party_racers):
            status = (
                f"FINISHED R{self._party_finish_round[idx]}"
                if self._party_finish_round[idx] is not None
                else f"{self._party_progress[idx] + 1}/{BOARD_WIDTH}"
            )
            if idx in self._party_blocked:
                status = f"BLOCKED at {self._party_progress[idx] + 1}/{BOARD_WIDTH}"
            details.append(
                f"{player.name}: {status}  |  claimed {self._party_claims[idx]}"
            )
        return "     ".join(details)

    def _party_player_colors(self) -> list[tuple[str, str, str]]:
        art = _theme().cards
        return [
            art.normal,
            art.heavy_hit,
            art.steal,
            art.poison,
            art.selected,
            art.heal,
        ]

    def _show_party_legend(self, parent: tk.Misc) -> None:
        theme = _theme()
        legend = tk.Frame(parent, bg=theme.panel_bg)
        legend.pack(pady=(0, 8))
        colors = self._party_player_colors()
        for idx, player in enumerate(self._party_racers):
            color = colors[idx % len(colors)]
            entry = tk.Frame(legend, bg=theme.panel_bg)
            entry.pack(side="left", padx=8)
            tk.Label(
                entry,
                text=str(idx + 1),
                bg=color[0],
                fg=color[2],
                font=(_font_family(), 10, "bold"),
                width=2,
                relief="solid",
                borderwidth=2,
                highlightbackground=color[1],
                highlightthickness=2,
            ).pack(side="left", padx=(0, 4))
            tk.Label(
                entry,
                text=player.name,
                bg=theme.panel_bg,
                fg=theme.body_fg,
                font=(_font_family(), 10, "bold"),
            ).pack(side="left")

    def _draw_party_board(self, _event: tk.Event | None = None) -> None:
        canvas = self._party_canvas
        if canvas is None:
            return
        try:
            if not canvas.winfo_exists():
                return
        except tk.TclError:
            return
        width = canvas.winfo_width()
        height = canvas.winfo_height()
        if width < 20 or height < 20:
            return
        cell = max(4, min((width - 16) // BOARD_WIDTH, (height - 16) // BOARD_HEIGHT))
        left = (width - cell * BOARD_WIDTH) // 2 + 12
        top = (height - cell * BOARD_HEIGHT) // 2
        theme = _theme()
        colors = self._party_player_colors()
        canvas.delete("all")
        for y in range(BOARD_HEIGHT):
            for x in range(BOARD_WIDTH):
                x1, y1 = left + x * cell, top + y * cell
                x2, y2 = x1 + cell, y1 + cell
                owner = self._party_board.get((x, y))
                fill = colors[owner % len(colors)][0] if owner is not None else theme.panel_bg
                outline = _shift_hex(theme.panel_border, 18)
                line_width = 1
                if (x, y) in self._party_conflict_cells and self._screen == "party_reveal":
                    fill = theme.cards.heavy_hit[1]
                    outline = theme.cards.heavy_hit[2]
                    line_width = 2
                elif (x, y) in self._party_preview and self._screen == "party_place":
                    fill = colors[self._party_placement_order[self._party_place_cursor] % len(colors)][1]
                    outline = colors[self._party_placement_order[self._party_place_cursor] % len(colors)][2]
                    line_width = 2
                elif owner is not None:
                    outline = colors[owner % len(colors)][1]
                    line_width = 2
                canvas.create_rectangle(
                    x1,
                    y1,
                    x2,
                    y2,
                    fill=fill,
                    outline=outline,
                    width=line_width,
                )
                if owner is not None and cell >= 12:
                    canvas.create_text(
                        (x1 + x2) / 2,
                        (y1 + y2) / 2,
                        text=str(owner + 1),
                        fill=colors[owner % len(colors)][2],
                        font=(_font_family(), max(8, min(11, cell // 2)), "bold"),
                    )
                elif (
                    (x, y) in self._party_preview
                    and self._screen == "party_place"
                    and cell >= 12
                ):
                    canvas.create_text(
                        (x1 + x2) / 2,
                        (y1 + y2) / 2,
                        text="+",
                        fill=colors[
                            self._party_placement_order[self._party_place_cursor]
                            % len(colors)
                        ][2],
                        font=(_font_family(), max(8, min(11, cell // 2)), "bold"),
                    )
        for y in range(BOARD_HEIGHT):
            canvas.create_text(
                left - 8,
                top + y * cell + cell // 2,
                text=str(y + 1),
                fill=theme.body_fg,
                font=(_font_family(), 8, "bold"),
                anchor="e",
            )
        for x in (0, BOARD_WIDTH - 1):
            canvas.create_text(
                left + x * cell + cell // 2,
                top - 4,
                text=str(x + 1),
                fill=theme.body_fg,
                font=(_font_family(), 8, "bold"),
                anchor="s",
            )

    def _lock_party_placement(self) -> None:
        if self._screen != "party_place":
            return
        player_idx = self._party_placement_order[self._party_place_cursor]
        try:
            column = int(self._party_column_var.get()) - 1
            row = int(self._party_row_var.get()) - 1
            cells = place_piece(
                self._party_piece_shape(),
                column,
                row,
                owners=self._party_board,
                player_idx=player_idx,
            )
        except (ValueError, KeyError):
            play_sfx(SFX_DENY)
            return
        self._party_placements[player_idx] = cells
        self._party_progress[player_idx] = max(
            self._party_progress[player_idx],
            max(x for x, _ in cells),
        )
        play_sfx(SFX_CARD_PICK)
        self._advance_party_placement()

    def _advance_party_placement(self) -> None:
        self._party_place_cursor += 1
        self._show_party_placement()

    def _reveal_party_placements(self) -> None:
        self._screen = "party_reveal"
        for player_idx, cells in self._party_placements.items():
            apply_placement(self._party_board, cells, player_idx)
        for idx, progress in enumerate(self._party_progress):
            if progress >= BOARD_WIDTH - 1 and self._party_finish_round[idx] is None:
                self._party_finish_round[idx] = self._party_round

        groups = conflict_groups(self._party_placements)
        self._party_conflicts = [
            (tuple(sorted(contenders)), cells)
            for contenders, cells in sorted(
                groups.items(),
                key=lambda item: (
                    min((y, x) for x, y in item[1]),
                    tuple(sorted(item[0])),
                ),
            )
        ]
        self._party_conflict_index = 0
        self._party_conflict_cells = {
            cell for _, cells in self._party_conflicts for cell in cells
        }
        self._show_party_reveal()

    def _show_party_reveal(self) -> None:
        self._screen = "party_reveal"
        self.clear()
        theme = _theme()
        self._ui_fill = True
        self._ui_front_wallpaper = True
        self.after_idle(self._relayout_ui)
        panel = tk.Frame(
            self._ui,
            bg=theme.panel_bg,
            highlightbackground=theme.panel_border,
            highlightthickness=3,
            padx=16,
            pady=12,
        )
        panel.pack(fill="both", expand=True)
        self._install_widget_wallpaper(panel, theme.screen_bg)
        clashes = sum(len(cells) for _, cells in self._party_conflicts)
        title = f"ROUND {self._party_round} REVEALED"
        explanation = (
            f"{clashes} contested tile(s) — each clash is settled by a card duel."
            if clashes
            else "No intersections this round. The race continues."
        )
        tk.Label(
            panel,
            text=title,
            bg=theme.panel_bg,
            fg=theme.title_fg,
            font=(_font_family(), 20, "bold"),
        ).pack(pady=(0, 4))
        tk.Label(
            panel,
            text=explanation,
            bg=theme.panel_bg,
            fg=theme.body_fg,
            font=(_font_family(), 12),
        ).pack(pady=(0, 8))
        self._party_score_label = tk.Label(
            panel,
            text=self._party_score_text(),
            bg=theme.panel_bg,
            fg=theme.body_fg,
            font=(_font_family(), 10),
            justify="center",
            wraplength=820,
        )
        self._party_score_label.pack(pady=(0, 8))
        self._party_canvas = tk.Canvas(
            panel,
            height=250,
            bg=theme.screen_bg,
            highlightbackground=theme.panel_border,
            highlightthickness=1,
        )
        self._party_canvas.pack(fill="x", expand=True, pady=(0, 8))
        self._party_canvas.bind("<Configure>", self._draw_party_board)
        self._show_party_legend(panel)
        ThemedArtButton(
            panel,
            "Resolve Clashes" if clashes else "Continue Race",
            command=(
                self._start_next_party_conflict
                if clashes
                else self._complete_party_round
            ),
            width=210,
            height=44,
            palette="selected",
        ).pack()
        ThemedArtButton(
            panel,
            "Reset Game",
            command=self._reset_game,
            width=140,
            height=36,
            palette="heavy_hit",
        ).pack(pady=(6, 0))
        self.after_idle(self._draw_party_board)

    def _start_next_party_conflict(self) -> None:
        if self._party_conflict_index >= len(self._party_conflicts):
            self._complete_party_round()
            return
        contenders, cells = self._party_conflicts[self._party_conflict_index]
        self._party_conflict_players = list(contenders)
        self._party_conflict_cells = set(cells)
        self._party_tournament_champion = self._party_conflict_players[0]
        self._party_tournament_next = 1
        self._start_party_duel(
            self._party_tournament_champion,
            self._party_conflict_players[self._party_tournament_next],
        )

    def _start_party_duel(self, first_idx: int, second_idx: int) -> None:
        assert self.settings is not None
        self._party_duel_global_indices = [first_idx, second_idx]
        decks: list[list[Card]] = []
        for _ in range(2):
            deck = self._make_random_crafted_deck(
                self.settings.power_points,
                vs_bot=False,
                deck_size=DECK_SIZE,
            )
            deck.append(make_mercy_card(DECK_SIZE, deck))
            decks.append(deck)
        self._party_duel_players = make_players_from_mixed_decks(
            decks,
            self.settings.starting_hp,
        )
        for duel_idx, racer_idx in enumerate(self._party_duel_global_indices):
            self._party_duel_players[duel_idx].name = self._party_racers[
                racer_idx
            ].name
        self._party_duel_winner = None
        self._show_random_deck_roll(
            [
                card
                for player in self._party_duel_players
                for card in player.hand
            ],
            title="BATTLE CARDS",
            final_status="10-CARD DECKS READY",
            on_complete=self._begin_party_crashout_match,
            finish_sfx=SFX_DEAL,
        )

    def _begin_party_crashout_match(self) -> None:
        self.players = self._party_duel_players
        self._party_duel_active = True
        self._party_duel_turn = random.randrange(len(self.players))
        self._party_duel_turns = 0
        self.active = self._party_duel_turn
        self.pending_card = None
        self.pending_target_idx = None
        self._borrows = []
        self._game_log = []
        self._death_causes = {}
        self._busy = False
        play_sfx(SFX_MATCH_START)
        start_bgm()
        self.show_play(
            "Tile clash — standard Crash Out rules with fresh 10-card decks."
        )

    def _show_party_duel_result(self, message: str) -> None:
        self.clear()
        theme = _theme()
        panel = tk.Frame(
            self._ui,
            bg=theme.panel_bg,
            highlightbackground=theme.panel_border,
            highlightthickness=3,
            padx=28,
            pady=20,
        )
        panel.pack(expand=True)
        assert self._party_duel_winner is not None
        winner = self._party_racers[self._party_duel_winner]
        cells = len(self._party_conflict_cells)
        tk.Label(
            panel,
            text=f"{winner.name} wins the clash!",
            bg=theme.panel_bg,
            fg=theme.title_fg,
            font=(_font_family(), 20, "bold"),
        ).pack(pady=(0, 8))
        tk.Label(
            panel,
            text=f"Claimed {cells} tile(s)  •  {message}",
            bg=theme.panel_bg,
            fg=theme.body_fg,
            font=(_font_family(), 11),
            wraplength=620,
        ).pack(pady=(0, 12))
        ThemedArtButton(
            panel,
            "Continue",
            command=self._advance_party_tournament,
            width=160,
            height=42,
            palette="selected",
        ).pack()

    def _advance_party_tournament(self) -> None:
        assert self._party_duel_winner is not None
        self._party_tournament_champion = self._party_duel_winner
        self._party_tournament_next += 1
        if self._party_tournament_next < len(self._party_conflict_players):
            self._start_party_duel(
                self._party_tournament_champion,
                self._party_conflict_players[self._party_tournament_next],
            )
            return
        winner = self._party_tournament_champion
        apply_placement(
            self._party_board,
            self._party_conflict_cells,
            winner,
        )
        self._party_claims[winner] += len(self._party_conflict_cells)
        self._party_conflict_index += 1
        self._start_next_party_conflict()

    def _complete_party_round(self) -> None:
        self._party_board = clear_completed_rows(self._party_board)
        if all(
            self._party_finish_round[idx] is not None or idx in self._party_blocked
            for idx in range(len(self._party_racers))
        ):
            self._finish_party_race()
            return
        self._party_round += 1
        self._prepare_party_round()

    def _finish_party_race(self) -> None:
        race_keys = [
            (1, -finish_round)
            if finish_round is not None
            else (0, self._party_progress[idx])
            for idx, finish_round in enumerate(self._party_finish_round)
        ]
        race_points = rank_points(race_keys)
        claim_points = rank_points([(count,) for count in self._party_claims])
        total_points = [
            race_points[idx] + claim_points[idx]
            for idx in range(len(self._party_racers))
        ]
        self._screen = "party_results"
        self.clear()
        theme = _theme()
        center = self._open_menu_panel(theme.screen_bg)
        self._menu_text(
            center,
            "PARTY RESULTS",
            theme.screen_bg,
            fg=theme.title_fg,
            size=32,
            bold=True,
            pady=(0, 12),
        )
        highest = max(total_points, default=0)
        winners = [
            self._party_racers[idx].name
            for idx, points in enumerate(total_points)
            if points == highest
        ]
        self._menu_text(
            center,
            f"Winner: {', '.join(winners)} — {highest} points",
            theme.screen_bg,
            fg=theme.title_fg,
            size=18,
            bold=True,
            pady=(0, 10),
        )
        ranking = sorted(
            range(len(self._party_racers)),
            key=lambda idx: (
                -total_points[idx],
                self._party_finish_round[idx] or self._party_round + 1,
                -self._party_claims[idx],
            ),
        )
        for rank, idx in enumerate(ranking, start=1):
            finish = (
                f"finished in round {self._party_finish_round[idx]}"
                if self._party_finish_round[idx] is not None
                else f"reached tile {self._party_progress[idx] + 1}/{BOARD_WIDTH}"
            )
            self._menu_text(
                center,
                (
                    f"{rank}. {self._party_racers[idx].name} — {total_points[idx]} pts "
                    f"(race {race_points[idx]}, claims {claim_points[idx]}; "
                    f"{self._party_claims[idx]} tile(s) claimed; {finish})"
                ),
                theme.screen_bg,
                fg=theme.body_fg,
                size=14,
                pady=3,
            )
        ThemedArtButton(
            center,
            "Reset Game",
            command=self._reset_game,
            width=200,
            height=48,
            palette="heavy_hit",
        ).pack(pady=(16, 0))

    def _start_player_roll(self, final_idx: int) -> None:
        self.clear()
        theme = _theme()
        panel = tk.Frame(
            self._ui,
            bg=theme.panel_bg,
            highlightbackground=theme.panel_border,
            highlightthickness=3,
            padx=34,
            pady=26,
        )
        panel.pack(expand=True)
        tk.Label(
            panel,
            text="STARTING PLAYER",
            bg=theme.panel_bg,
            fg=theme.title_fg,
            font=(_font_family(), 18, "bold"),
        ).pack(pady=(0, 12))
        slot = tk.Canvas(
            panel,
            width=150,
            height=150,
            bg=theme.screen_bg,
            highlightbackground=theme.panel_border,
            highlightthickness=2,
        )
        slot.pack()
        number = tk.Label(
            slot,
            text="1",
            bg=theme.screen_bg,
            fg=theme.title_fg,
            font=(_font_family(), 72, "bold"),
        )
        number.place(relx=0.5, rely=0.5, anchor="center")

        total_steps = max(12, len(self.players) * 5)

        def roll_label(player_idx: int) -> str:
            player = self.players[player_idx]
            default_name = f"player-{player_idx + 1}"
            if player.name == default_name:
                return str(player_idx + 1)
            letters = "".join(character for character in player.name if character.isalpha())
            return letters[:2].upper() or str(player_idx + 1)

        def roll(step: int = 0) -> None:
            if step < total_steps:
                shown_idx = (step * 3 + final_idx) % len(self.players)
                number.configure(text=roll_label(shown_idx))
                self.after(70 + step * 5, lambda: roll(step + 1))
                return
            number.configure(text=roll_label(final_idx))
            play_sfx(SFX_TURN_START)
            def begin_match() -> None:
                start_msg = (
                    "Craftable cards shuffled and dealt! "
                    if not self.settings.vs_bot
                    else "Match started. "
                )
                self.show_play(
                    start_msg + f"{self.players[final_idx].name}'s turn."
                )

            self.after(2000, begin_match)

        roll()

    def _log_turn_banner(self, banner_msg: str) -> None:
        if not banner_msg:
            return
        entry = f"--- {banner_msg} ---"
        if not self._game_log or self._game_log[-1] != entry:
            self.append_log(entry)

    def _render_game_log(self) -> None:
        if self.log is None:
            return
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        for line in self._game_log:
            self.log.insert("end", line + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _trigger_log_debug_cheat(self) -> None:
        if not self.players:
            return
        player = self.players[self.active]
        player.cheats_enabled = not player.cheats_enabled
        if player.cheats_enabled:
            player.cooldown_clear_turns = 0
            for card in player.hand:
                card.cooldown_remaining = 0
            self.append_log(
                f"DEBUG: {player.name}'s cheats enabled — no cooldowns and damage immunity active."
            )
        else:
            self.append_log(f"DEBUG: {player.name}'s cheats disabled.")
        for chip in self._hud_chips:
            chip._draw()
        self._render_game_log()

    def _on_log_keypress(self, event: tk.Event) -> None:
        key = (event.char or event.keysym or "").lower()
        if not key or not key.isalpha():
            self._log_cheat_buffer.clear()
            return
        target = "cmnd"
        if not self._log_cheat_buffer:
            if key == target[0]:
                self._log_cheat_buffer = [key]
            else:
                self._log_cheat_buffer.clear()
            return
        if key == target[len(self._log_cheat_buffer)]:
            self._log_cheat_buffer.append(key)
        elif key == target[0]:
            self._log_cheat_buffer = [key]
        else:
            self._log_cheat_buffer.clear()
        if len(self._log_cheat_buffer) == len(target):
            self._log_cheat_buffer.clear()
            self._trigger_log_debug_cheat()

    def show_play(self, banner_msg: str = "") -> None:
        self._screen = "play"
        self._play_banner = banner_msg
        self.clear()
        self._busy = False
        self.log = None
        player = self.players[self.active]
        if not self._game_log:
            self._game_log.append("Play a card, then choose a target.")
        self._log_turn_banner(banner_msg or f"Turn — {player.name}")

        self._ui_fill = True
        self.after_idle(self._relayout_ui)
        theme = _theme()
        tint = self._bg_tint or theme.screen_bg

        self._ui_front_wallpaper = True
        play_area = tk.Frame(self._ui, bg=tint)
        play_area.pack(fill="both", expand=True)
        self._install_widget_wallpaper(play_area, tint)

        hud_outer = tk.Frame(play_area, bg=tint)
        hud_outer.pack(fill="x", pady=(0, 10))
        health_bar = tk.Frame(hud_outer, bg=tint)
        health_bar.pack(anchor="center")
        self._hud_bar = health_bar
        self._hud_chips = []
        for i, p in enumerate(self.players):
            chip = PixelHudChip(health_bar, p, is_active=(i == self.active))
            chip.pack(side="left", padx=6)
            self._hud_chips.append(chip)

        ttk.Label(play_area, text="CRASH OUT", style="Title.TLabel").pack()
        ttk.Label(
            play_area,
            text=banner_msg or f"Turn — {player.name}",
            style="Body.TLabel",
        ).pack(pady=(4, 0))
        self._match_timer_label = ttk.Label(
            play_area,
            text="Time: 00:00",
            style="Body.TLabel",
        )
        self._match_timer_label.pack(pady=(2, 6))
        self._update_match_timer()

        btn_row = tk.Frame(play_area, bg=_theme().screen_bg)
        btn_row.pack(pady=(0, 10))
        ThemedArtButton(
            btn_row,
            "Log",
            command=self._show_log_overlay,
            width=140,
            height=44,
            palette="selected",
        ).pack(side="left", padx=6)
        ThemedArtButton(
            btn_row,
            "Reset Game",
            command=self._reset_game,
            width=180,
            height=44,
            palette="heavy_hit",
        ).pack(side="left", padx=6)

        action = tk.Frame(play_area, bg=_theme().screen_bg)
        action.pack(fill="both", expand=True)

        if not player.alive:
            self.after(TURN_DELAY_MS, self.advance_turn)
            return

        if player.is_bot:
            ttk.Label(
                action, text="Bot is thinking...", style="Body.TLabel"
            ).pack()
            self.after(TURN_DELAY_MS, self.run_bot_turn)
            return

        ttk.Label(
            action,
            text="Your hand — hover a unique card to inspect it",
            style="Body.TLabel",
        ).pack()
        self._hand_outer = tk.Frame(action, bg=_theme().screen_bg)
        self._hand_outer.pack(fill="both", expand=True, pady=8)
        self._card_faces = []
        for card in player.hand:
            cooling = card_is_cooling(player, card)
            face = RoundedCardButton(
                self._hand_outer,
                card,
                disabled=cooling,
                command=(None if cooling else (lambda c=card: self.pick_card(c))),
                flip_on_hover=True,
            )
            self._card_faces.append(face)
        self._hand_outer.bind("<Configure>", self._layout_hand_cards)
        self.after_idle(self._layout_hand_cards)

    def append_log(self, text: str) -> None:
        self._game_log.append(text)
        if self.log is None:
            return
        try:
            self.log.configure(state="normal")
            self.log.insert("end", text + "\n")
            self.log.see("end")
            self.log.configure(state="disabled")
        except tk.TclError:
            pass

    def pick_card(self, card: Card) -> None:
        if self._busy:
            return
        player = self.players[self.active]
        if card_is_cooling(player, card):
            play_sfx(SFX_DENY)
            return
        self.pending_card = card
        play_sfx(SFX_CARD_PICK)
        targets = self._card_target_indices(card)
        if len(targets) == 1 and not card.heal_any:
            self.confirm_play(targets[0])
            return
        self._show_target_overlay(card)

    def confirm_play(self, target_idx: int) -> None:
        if self._busy or self.pending_card is None:
            return
        self._hide_target_overlay()
        card = self.pending_card
        player = self.players[self.active]
        mark_card_played(player, card)
        play_card_play_sfx(card)
        self.append_log(f"{player.name} plays {card.name}")
        self.append_log(
            f"Target: {describe_target(card, self.players, self.active, target_idx)}"
        )
        before_hp = self._snapshot_hp()
        for line in resolve_card(
            card, self.players, self.active, target_idx, self._borrows
        ):
            self.append_log("  " + line)
        for line in resolve_steal(
            card, self.players, self.active, target_idx, self._borrows
        ):
            self.append_log("  " + line)
        self._record_new_deaths(before_hp, card.name)
        floated = self._show_hp_floaters(before_hp)
        self._complete_play(resolve_delay_ms=900 if floated else TURN_DELAY_MS)

    def run_bot_turn(self) -> None:
        set_sfx_muted(True)
        try:
            player = self.players[self.active]
            choice = bot_choose_play(self.players, self.active, self.starting_hp)
            if choice is None:
                player.last_card_id = None
                self.append_log("Bot has no playable cards — skipped.")
                self._borrows, return_logs = return_expired_borrows(
                    self.players, self.active, self._borrows
                )
                for line in return_logs:
                    self.append_log("  " + line)
                for line in tick_turn_cooldowns(self.players, self.active):
                    self.append_log("  " + line)
                self.after(TURN_DELAY_MS, self.after_resolve)
                return
            card, target_idx, reason = choice
            mark_card_played(player, card)
            self.append_log(f"Bot plan: {reason}")
            self.append_log(f"Bot plays {card.name}")
            self.append_log(
                f"Target: {describe_target(card, self.players, self.active, target_idx)}"
            )
            before_hp = self._snapshot_hp()
            for line in resolve_card(
                card, self.players, self.active, target_idx, self._borrows
            ):
                self.append_log("  " + line)
            self._record_new_deaths(before_hp, card.name)
            floated = self._show_hp_floaters(before_hp)
            self._borrows, return_logs = return_expired_borrows(
                self.players, self.active, self._borrows
            )
            for line in return_logs:
                self.append_log("  " + line)
            for line in tick_turn_cooldowns(self.players, self.active):
                self.append_log("  " + line)
            self.after(900 if floated else TURN_DELAY_MS, self.after_resolve)
        finally:
            set_sfx_muted(False)

    def after_resolve(self) -> None:
        winner = check_winner(self.players)
        if self._party_duel_active:
            if winner is not None:
                self._finish_party_duel(winner)
                return
            self.advance_turn()
            return
        if winner is not None:
            self.show_game_over(winner.name)
            return
        self.advance_turn()

    def _finish_party_duel(self, winner: Player | None) -> None:
        if not self._party_duel_active:
            return
        if winner is None:
            duel_winner_idx = random.randrange(len(self._party_duel_global_indices))
            outcome = "Both players were knocked out; the clash was awarded by tiebreak."
        else:
            duel_winner_idx = self.players.index(winner)
            outcome = f"{winner.name} wins with {winner.hp} HP remaining."
        self._party_duel_winner = self._party_duel_global_indices[duel_winner_idx]
        self._party_duel_active = False
        self._party_duel_players = []
        self.players = self._party_racers
        self.pending_card = None
        self.pending_target_idx = None
        self._busy = False
        stop_bgm()
        play_sfx(SFX_WIN)
        self._screen = "party_duel_result"
        self._show_party_duel_result(
            f"Standard Crash Out match — {outcome}"
        )

    def advance_turn(self) -> None:
        while True:
            nxt = next_alive_index(self.players, self.active)
            if nxt is None:
                if self._party_duel_active:
                    self._finish_party_duel(None)
                else:
                    self.show_game_over(None)
                return
            self.active = nxt
            before_hp = self._snapshot_hp()
            for line in tick_reaper_marks(self.players):
                self.append_log("  " + line)
            self._record_new_deaths(before_hp, "Reaper")
            if not self.players[self.active].alive:
                winner = check_winner(self.players)
                if winner is not None:
                    if self._party_duel_active:
                        self._finish_party_duel(winner)
                    else:
                        self.show_game_over(winner.name)
                    return
                continue
            before_hp = self._snapshot_hp()
            for line in tick_poisons_on_turn_start(
                self.players[self.active], self.players
            ):
                self.append_log("  " + line)
            self._record_new_deaths(before_hp, "Poison")
            if not self.players[self.active].alive:
                winner = check_winner(self.players)
                if winner is not None:
                    if self._party_duel_active:
                        self._finish_party_duel(winner)
                    else:
                        self.show_game_over(winner.name)
                    return
                continue
            break
        if not self.players[self.active].is_bot:
            play_sfx(SFX_TURN_START)
        self.show_play(f"Turn — {self.players[self.active].name}")

    def show_game_over(self, winner: str | None) -> None:
        self._screen = "game_over"
        self._game_over_winner = winner
        self._stop_match_timer()
        stop_bgm()
        self.clear()
        theme = _theme()
        vs_bot = self.settings is not None and self.settings.vs_bot
        human_won = vs_bot and winner is not None and winner != BOT_NAME
        if vs_bot:
            bg = theme.win_bg if human_won else theme.lose_bg
            fg = "#e8f8ee" if human_won else "#ffe8e0"
            play_sfx(SFX_WIN if human_won else SFX_LOSE)
        else:
            bg = theme.screen_bg
            fg = theme.title_fg
            play_sfx(SFX_WIN if winner is not None else SFX_LOSE)
        self._set_screen_bg(bg)
        center = self._open_menu_panel(bg)
        title = "-=You Win=-" if human_won else "-=Game Over=-"
        self._menu_text(
            center,
            title,
            bg,
            fg=fg,
            size=64,
            bold=True,
            pady=(0, 20),
        )
        elapsed = 0.0
        if self._match_started_at is not None:
            elapsed = max(0.0, time.monotonic() - self._match_started_at)
        self._menu_text(
            center,
            f"Match time: {format_elapsed_time(elapsed)}",
            bg,
            fg=fg,
            size=22,
            pady=(0, 6),
        )
        if not human_won:
            msg = f"{winner} wins!" if winner else "No one left standing."
            self._menu_text(
                center,
                msg,
                bg,
                fg=fg,
                size=24,
                pady=20,
            )
        for index, p in enumerate(self.players):
            if p.alive:
                status = "∞ HP" if p.cheats_enabled else f"{p.hp}/{p.max_hp} HP"
            else:
                cause = self._death_causes.get(index, "unknown cause")
                status = f"OUT — {cause}"
            self._menu_text(
                center,
                f"{p.name}: {status}",
                bg,
                fg=fg,
                size=24,
                pady=4,
            )
        btn_row = self._wallpaper_frame(center, bg)
        btn_row.pack(pady=(24, 0))
        ThemedArtButton(
            btn_row,
            "Reset Game",
            command=self._reset_game,
            width=200,
            height=52,
            palette="heavy_hit",
            bg=bg,
        ).pack(side="left", padx=8)
        ThemedArtButton(
            btn_row,
            "Quit",
            command=self.destroy,
            width=140,
            height=52,
            palette="normal",
            bg=bg,
        ).pack(side="left", padx=8)


def main() -> None:
    app = CrashOutApp()
    app.mainloop()


if __name__ == "__main__":
    main()
