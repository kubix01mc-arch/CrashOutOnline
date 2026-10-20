#!/usr/bin/env python3
"""Procedural pixel-art wallpapers tinted to the active theme."""

from __future__ import annotations

import io
import math
import random
import tkinter as tk
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from crash_out_themes import GameTheme

try:
    from PIL import Image, ImageTk

    HAS_PIL = True
except ImportError:
    HAS_PIL = False


def _hex_to_rgb(color: str) -> tuple[int, int, int]:
    raw = color.lstrip("#")
    return int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16)


def _rgb_to_hex(r: int, g: int, b: int) -> str:
    return f"#{max(0, min(255, r)):02x}{max(0, min(255, g)):02x}{max(0, min(255, b)):02x}"


def _shift_rgb(rgb: tuple[int, int, int], delta: int) -> tuple[int, int, int]:
    return tuple(max(0, min(255, c + delta)) for c in rgb)  # type: ignore[return-value]


def _mix(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    return tuple(int(a[i] * (1 - t) + b[i] * t) for i in range(3))  # type: ignore[return-value]


def _palette(theme: GameTheme, tint: str | None = None) -> list[tuple[int, int, int]]:
    base = _hex_to_rgb(tint or theme.screen_bg)
    accent = _hex_to_rgb(theme.cards.normal[1])
    title = _hex_to_rgb(theme.title_fg)
    panel = _hex_to_rgb(theme.panel_bg)
    return [
        base,
        _shift_rgb(base, 18),
        _shift_rgb(base, -14),
        _mix(base, accent, 0.22),
        _mix(base, accent, 0.38),
        _mix(base, title, 0.12),
        _mix(base, panel, 0.35),
        _shift_rgb(_mix(base, accent, 0.5), -20),
    ]


def _cell_size(style: str) -> int:
    return {
        "neon": 10,
        "lava": 12,
        "ice": 10,
        "arcade": 8,
        "gold": 12,
        "circuit": 10,
        "stone": 14,
        "shadow": 12,
        "pixel": 12,
        "crimson": 12,
        "ocean": 10,
        "sakura": 10,
        "jazz": 11,
        "toxic": 10,
        "solar": 11,
        "aurora": 10,
        "ruins": 13,
        "void": 12,
        "candy": 9,
        "village": 8,
    }.get(style, 12)


def _fill_rect(
    set_px,
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    color: tuple[int, int, int],
) -> None:
    for y in range(min(y1, y2), max(y1, y2) + 1):
        for x in range(min(x1, x2), max(x1, x2) + 1):
            set_px(x, y, color)


def _stroke_rect(
    set_px,
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    color: tuple[int, int, int],
) -> None:
    for x in range(min(x1, x2), max(x1, x2) + 1):
        set_px(x, y1, color)
        set_px(x, y2, color)
    for y in range(min(y1, y2), max(y1, y2) + 1):
        set_px(x1, y, color)
        set_px(x2, y, color)


def _paint_village_scene(
    grid: list[list[tuple[int, int, int]]],
    cols: int,
    rows: int,
    set_px,
    rng: random.Random,
    *,
    tint: str | None = None,
) -> None:
    """
    Side-view Minecraft village matching the reference art:
    blue sky, chunky clouds, stone church + annex, well, grass over dirt.
    """
    # Palette from the reference image
    sky = _hex_to_rgb(tint) if tint and tint.lower() not in {"#7ec8f0", "#87ceeb"} else (126, 184, 220)
    if tint:
        # Win/lose tint still shifts sky slightly toward that color
        sky = _mix(sky, _hex_to_rgb(tint), 0.35)
    cloud = (245, 248, 252)
    stone = (168, 172, 178)
    stone_dk = (120, 124, 132)
    outline = (55, 58, 64)
    grass = (110, 178, 78)
    grass_dk = (70, 120, 55)
    dirt = (166, 124, 78)
    pebble = (190, 186, 176)
    wood = (92, 58, 36)
    window = (240, 236, 210)
    candle = (255, 220, 90)

    ground_top = int(rows * 0.62)
    grass_h = max(3, rows // 14)
    dirt_top = ground_top + grass_h

    # Sky fill
    for y in range(rows):
        for x in range(cols):
            grid[y][x] = sky

    # Chunky clouds
    def cloud_blob(cx: int, cy: int, w: int, h: int) -> None:
        _fill_rect(set_px, cx, cy + h // 3, cx + w, cy + h, cloud)
        _fill_rect(set_px, cx + w // 5, cy, cx + 4 * w // 5, cy + 2 * h // 3, cloud)

    cloud_blob(max(1, cols // 20), max(1, rows // 14), max(6, cols // 7), max(3, rows // 12))
    cloud_blob(cols // 3, max(1, rows // 18), max(8, cols // 6), max(3, rows // 11))
    cloud_blob(2 * cols // 3, max(2, rows // 12), max(7, cols // 6), max(3, rows // 12))

    # Dirt + pebbles
    for y in range(dirt_top, rows):
        for x in range(cols):
            grid[y][x] = dirt
            if (x * 5 + y * 3 + rng.randrange(3)) % 11 == 0:
                set_px(x, y, pebble)

    # Grass strip (bright top, darker underside like the reference)
    for y in range(ground_top, dirt_top):
        for x in range(cols):
            if y == ground_top:
                set_px(x, y, grass)
            elif y == dirt_top - 1:
                set_px(x, y, grass_dk)
            else:
                set_px(x, y, _mix(grass, grass_dk, 0.45))
    # Jagged grass tips
    for x in range(cols):
        if (x + rng.randrange(2)) % 4 == 0:
            set_px(x, ground_top - 1, grass)

    # --- Church / tower ---
    # Scale buildings from ground_top upward
    tower_w = max(8, cols // 7)
    tower_h = max(14, int(rows * 0.42))
    tower_x = max(3, cols // 10)
    tower_y2 = ground_top - 1
    tower_y1 = max(2, tower_y2 - tower_h)
    annex_w = max(6, cols // 9)
    annex_h = max(8, int(tower_h * 0.55))
    annex_x = tower_x + tower_w
    annex_y1 = tower_y2 - annex_h

    def stone_building(x1: int, y1: int, x2: int, y2: int) -> None:
        _fill_rect(set_px, x1, y1, x2, y2, stone)
        # Right-side shade
        shade_x = x2 - max(1, (x2 - x1) // 5)
        _fill_rect(set_px, shade_x, y1, x2, y2, stone_dk)
        _stroke_rect(set_px, x1, y1, x2, y2, outline)

    stone_building(tower_x, tower_y1, tower_x + tower_w, tower_y2)
    stone_building(annex_x, annex_y1, annex_x + annex_w, tower_y2)

    # Crenellations on tower
    merlon = max(2, tower_w // 5)
    gap = max(1, merlon // 2)
    x = tower_x
    while x + merlon <= tower_x + tower_w:
        _fill_rect(set_px, x, tower_y1 - max(2, rows // 30), x + merlon - 1, tower_y1, stone)
        _stroke_rect(set_px, x, tower_y1 - max(2, rows // 30), x + merlon - 1, tower_y1, outline)
        x += merlon + gap

    # Windows (diamond-ish slots with candle)
    def window_at(wx: int, wy: int, ww: int, wh: int) -> None:
        # Tall diamond/slot window with white panes + candle glow
        _fill_rect(set_px, wx, wy, wx + ww, wy + wh, outline)
        _fill_rect(set_px, wx + 1, wy + 1, wx + ww - 1, wy + wh - 1, window)
        cx = wx + ww // 2
        cy = wy + wh // 2
        set_px(cx, cy, candle)
        set_px(cx, cy - 1, candle)
        set_px(cx, wy + 1, window)

    ww = max(2, tower_w // 4)
    wh = max(3, tower_h // 7)
    window_at(tower_x + tower_w // 2 - ww // 2, tower_y1 + tower_h // 5, ww, wh)
    window_at(tower_x + tower_w // 2 - ww // 2, tower_y1 + tower_h // 2, ww, wh)

    # Door
    dw = max(2, tower_w // 4)
    dh = max(3, tower_h // 6)
    door_x = tower_x + tower_w // 2 - dw // 2
    door_y = tower_y2 - dh
    _fill_rect(set_px, door_x, door_y, door_x + dw, tower_y2, wood)
    _stroke_rect(set_px, door_x, door_y, door_x + dw, tower_y2, outline)

    # Grass shadow under building
    _fill_rect(
        set_px,
        tower_x,
        ground_top,
        annex_x + annex_w + 1,
        ground_top + max(1, grass_h - 1),
        grass_dk,
    )

    # --- Well ---
    well_w = max(5, cols // 12)
    well_h = max(4, rows // 14)
    well_x = min(cols - well_w - 3, annex_x + annex_w + max(4, cols // 14))
    well_y2 = ground_top - 1
    well_y1 = well_y2 - well_h
    stone_building(well_x, well_y1, well_x + well_w, well_y2)
    # Pillars + roof
    pillar_h = max(3, rows // 16)
    roof_y = well_y1 - pillar_h
    set_px(well_x + 1, roof_y + 1, outline)
    set_px(well_x + well_w - 1, roof_y + 1, outline)
    for py in range(roof_y + 1, well_y1):
        set_px(well_x + 1, py, stone_dk)
        set_px(well_x + well_w - 1, py, stone_dk)
    _fill_rect(set_px, well_x, roof_y, well_x + well_w, roof_y + 1, stone)
    _stroke_rect(set_px, well_x, roof_y, well_x + well_w, roof_y + 1, outline)


def _paint_pixel_grid(
    theme: GameTheme,
    cols: int,
    rows: int,
    tint: str | None = None,
) -> list[list[tuple[int, int, int]]]:
    rng = random.Random(f"{theme.name}:{theme.card_style}:{tint or theme.screen_bg}:{cols}x{rows}")
    colors = _palette(theme, tint)
    base = colors[0]
    style = theme.card_style
    grid = [[base for _ in range(cols)] for _ in range(rows)]

    def set_px(x: int, y: int, color: tuple[int, int, int]) -> None:
        if 0 <= x < cols and 0 <= y < rows:
            grid[y][x] = color

    if style == "neon":
        for y in range(rows):
            for x in range(cols):
                grid[y][x] = colors[1] if (x + y) % 7 == 0 else colors[2 if (x * 3 + y) % 11 == 0 else 0]
        for x in range(0, cols, 6):
            for y in range(rows):
                set_px(x, y, colors[4])
        for y in range(0, rows, 6):
            for x in range(cols):
                set_px(x, y, colors[3])
        for _ in range(max(8, cols * rows // 40)):
            set_px(rng.randrange(cols), rng.randrange(rows), colors[5])

    elif style == "lava":
        for y in range(rows):
            for x in range(cols):
                n = (x * 5 + y * 3 + rng.randrange(3)) % 9
                grid[y][x] = colors[0 if n > 5 else (4 if n > 2 else 7)]
        for _ in range(cols):
            x, y = rng.randrange(cols), rng.randrange(rows)
            for i in range(rng.randint(3, 8)):
                set_px(x, y, colors[4])
                x += rng.choice((-1, 0, 1))
                y += rng.choice((-1, 0, 1))

    elif style == "ice":
        for y in range(rows):
            for x in range(cols):
                band = (x + y) % 8
                grid[y][x] = colors[1 if band < 2 else (5 if band == 4 else 0)]
        for _ in range(max(12, cols // 2)):
            x = rng.randrange(cols)
            for y in range(rows):
                if rng.random() < 0.55:
                    set_px(x, y, colors[5])
                    set_px(x + 1, y, colors[1])

    elif style == "arcade":
        for y in range(rows):
            stripe = colors[3 if (y // 2) % 2 == 0 else 0]
            for x in range(cols):
                grid[y][x] = colors[4] if (x + y) % 5 == 0 else stripe
        for y in range(0, rows, 4):
            for x in range(0, cols, 4):
                set_px(x, y, colors[5])

    elif style == "gold":
        for y in range(rows):
            for x in range(cols):
                grid[y][x] = colors[(x // 3 + y // 3) % 3]
        for y in range(2, rows - 2):
            for x in range(2, cols - 2):
                if x in (2, cols - 3) or y in (2, rows - 3):
                    set_px(x, y, colors[4])
        for _ in range(max(6, cols // 3)):
            set_px(rng.randrange(cols), rng.randrange(rows), colors[5])

    elif style == "circuit":
        for y in range(rows):
            for x in range(cols):
                grid[y][x] = colors[2 if (x % 4 == 0 or y % 4 == 0) else 0]
        for y in range(1, rows, 4):
            for x in range(1, cols, 4):
                set_px(x, y, colors[4])
                if rng.random() < 0.5:
                    set_px(x + 1, y, colors[3])
                if rng.random() < 0.5:
                    set_px(x, y + 1, colors[3])

    elif style == "stone":
        brick_w, brick_h = 4, 2
        for y in range(rows):
            row = y // brick_h
            offset = (brick_w // 2) if row % 2 else 0
            for x in range(cols):
                tone = colors[1 if ((x + offset) // brick_w + row) % 2 == 0 else 2]
                if x % brick_w == offset % brick_w or y % brick_h == 0:
                    tone = colors[7]
                grid[y][x] = tone

    elif style == "shadow":
        for y in range(rows):
            for x in range(cols):
                grid[y][x] = colors[2 if (x * y + x) % 13 == 0 else 0]
        for y in range(rows):
            for x in range(cols):
                if abs((x - cols // 2) * (y - rows // 2)) % 17 == 0:
                    set_px(x, y, colors[3])

    elif style == "crimson":
        # Arena floor: concentric rings + rivet dots
        cx, cy = cols // 2, rows // 2
        for y in range(rows):
            for x in range(cols):
                dist = abs(x - cx) + abs(y - cy)
                grid[y][x] = colors[4 if dist % 8 < 2 else (1 if dist % 5 == 0 else 0)]
        for _ in range(max(10, cols // 2)):
            set_px(rng.randrange(cols), rng.randrange(rows), colors[5])

    elif style == "ocean":
        # Horizontal wave bands
        for y in range(rows):
            band = (y // 2 + (y % 5)) % 4
            tone = colors[band if band < len(colors) else 0]
            for x in range(cols):
                wobble = 1 if ((x + y) % 6) < 3 else 0
                grid[y][x] = colors[(band + wobble) % 5]
        for _ in range(max(8, cols // 3)):
            x = rng.randrange(cols)
            for y in range(rows):
                if rng.random() < 0.2:
                    set_px(x, y, colors[5])

    elif style == "sakura":
        # Soft dither + scattered petal clusters
        for y in range(rows):
            for x in range(cols):
                n = (x * 3 + y * 5) % 11
                grid[y][x] = colors[1 if n < 2 else (2 if n == 5 else 0)]
        for _ in range(max(10, cols * rows // 50)):
            cx, cy = rng.randrange(cols), rng.randrange(rows)
            for dx, dy in ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1)):
                set_px(cx + dx, cy + dy, colors[4 if abs(dx) + abs(dy) == 0 else 3])

    elif style == "jazz":
        # Diagonal velvet stripes
        for y in range(rows):
            for x in range(cols):
                stripe = ((x + y) // 3) % 3
                grid[y][x] = colors[stripe]
        for y in range(0, rows, 7):
            for x in range(cols):
                set_px(x, y, colors[4])
        for _ in range(max(6, cols // 4)):
            set_px(rng.randrange(cols), rng.randrange(rows), colors[5])

    elif style == "toxic":
        # Hazard chevrons / warning bars
        for y in range(rows):
            for x in range(cols):
                chev = ((x + (y % 4) * 2) // 3) % 2
                grid[y][x] = colors[4 if chev else 0]
        for y in range(0, rows, 5):
            for x in range(cols):
                set_px(x, y, colors[7])
        for _ in range(max(8, cols // 3)):
            set_px(rng.randrange(cols), rng.randrange(rows), colors[5])

    elif style == "solar":
        # Radial burst from center
        cx, cy = cols // 2, rows // 2
        for y in range(rows):
            for x in range(cols):
                dx, dy = x - cx, y - cy
                ang = (dx * 5 + dy * 3) % 12
                grid[y][x] = colors[4 if ang < 2 else (1 if ang < 5 else 0)]
        for r in range(2, min(cx, cy), 4):
            for t in range(0, 360, 20):
                set_px(cx + int(math.cos(math.radians(t)) * r), cy + int(math.sin(math.radians(t)) * r), colors[5])

    elif style == "aurora":
        # Vertical ribbons with soft shimmer
        for y in range(rows):
            for x in range(cols):
                ribbon = (x // 3 + y // 8) % 4
                grid[y][x] = colors[ribbon]
        for y in range(rows):
            for x in range(cols):
                if (x + y * 2) % 9 == 0:
                    set_px(x, y, colors[5])

    elif style == "ruins":
        # Broken tile / column grid
        for y in range(rows):
            for x in range(cols):
                tile = ((x // 5) + (y // 4)) % 2
                grid[y][x] = colors[1 if tile else 2]
                if x % 5 == 0 or y % 4 == 0:
                    grid[y][x] = colors[7]
        for _ in range(max(10, cols // 2)):
            x, y = rng.randrange(cols), rng.randrange(rows)
            for i in range(rng.randint(2, 6)):
                set_px(x + i, y, colors[4])
                set_px(x, y + i, colors[3])

    elif style == "void":
        # Sparse stars on deep field + faint rings
        for y in range(rows):
            for x in range(cols):
                grid[y][x] = colors[2]
        cx, cy = cols // 2, rows // 2
        for y in range(rows):
            for x in range(cols):
                dist = abs(x - cx) + abs(y - cy)
                if dist % 10 == 0:
                    set_px(x, y, colors[3])
        for _ in range(max(16, cols * rows // 30)):
            set_px(rng.randrange(cols), rng.randrange(rows), colors[5 if rng.random() < 0.3 else 4])

    elif style == "candy":
        # Polka-dot carnival field
        for y in range(rows):
            stripe = colors[3 if (y // 3) % 2 == 0 else 0]
            for x in range(cols):
                grid[y][x] = stripe
        for y in range(1, rows, 4):
            for x in range(1, cols, 4):
                set_px(x, y, colors[4])
                set_px(x + 1, y, colors[5])
                set_px(x, y + 1, colors[5])

    elif style == "village":
        # Side-view Minecraft village: sky, clouds, stone church, well, grass + dirt
        _paint_village_scene(grid, cols, rows, set_px, rng, tint=tint)

    else:  # pixel / default — chunky dithered noise
        for y in range(rows):
            for x in range(cols):
                n = rng.randrange(100)
                if n < 8:
                    grid[y][x] = colors[4]
                elif n < 20:
                    grid[y][x] = colors[1]
                elif n < 35:
                    grid[y][x] = colors[2]
                else:
                    grid[y][x] = colors[0]
        # sparse accent clusters
        for _ in range(max(4, cols * rows // 80)):
            cx, cy = rng.randrange(cols), rng.randrange(rows)
            for dy in range(-1, 2):
                for dx in range(-1, 2):
                    if rng.random() < 0.6:
                        set_px(cx + dx, cy + dy, colors[3])

    return grid


def _photo_from_grid_pil(
    grid: list[list[tuple[int, int, int]]],
    cell: int,
    width: int,
    height: int,
) -> tk.PhotoImage:
    rows = len(grid)
    cols = len(grid[0]) if rows else 0
    img = Image.new("RGB", (cols, rows))
    pixels = img.load()
    assert pixels is not None
    for y in range(rows):
        for x in range(cols):
            pixels[x, y] = grid[y][x]
    img = img.resize((cols * cell, rows * cell), Image.Resampling.NEAREST)
    if img.size != (width, height):
        # Crop or pad to exact window size while keeping pixel edges crisp.
        canvas = Image.new("RGB", (width, height), grid[0][0] if rows and cols else (0, 0, 0))
        canvas.paste(img, (0, 0))
        img = canvas.crop((0, 0, width, height))
    return ImageTk.PhotoImage(img)


def _photo_from_grid_tk(
    grid: list[list[tuple[int, int, int]]],
    cell: int,
    width: int,
    height: int,
) -> tk.PhotoImage:
    """Fallback without PIL — build a small image and zoom it."""
    rows = len(grid)
    cols = len(grid[0]) if rows else 1
    photo = tk.PhotoImage(width=cols, height=rows)
    # put() accepts row-wise color data
    for y in range(rows):
        row = " ".join(_rgb_to_hex(*grid[y][x]) for x in range(cols))
        photo.put("{" + row + "}", to=(0, y))
    zoomed = photo.zoom(max(1, cell), max(1, cell))
    # If zoomed is larger than needed, leave it — Label will clip.
    # If smaller, the Label centers/stretches poorly; pad by creating full size.
    if zoomed.width() < width or zoomed.height() < height:
        full = tk.PhotoImage(width=width, height=height)
        full.paste(zoomed)
        return full
    return zoomed


def generate_theme_wallpaper(
    theme: GameTheme,
    width: int,
    height: int,
    *,
    tint: str | None = None,
) -> tk.PhotoImage:
    """
    Build a pixel-art wallpaper matching the theme tint and card_style.
    `tint` overrides the base color (e.g. win/lose screens).
    """
    width = max(64, int(width))
    height = max(64, int(height))

    # Village scene: paint at a fixed logical resolution so buildings stay readable,
    # then nearest-neighbor scale to the window.
    if theme.card_style == "village" and HAS_PIL:
        logical_w, logical_h = 160, 90
        grid = _paint_pixel_grid(theme, logical_w, logical_h, tint=tint)
        img = Image.new("RGB", (logical_w, logical_h))
        pixels = img.load()
        assert pixels is not None
        for y in range(logical_h):
            for x in range(logical_w):
                pixels[x, y] = grid[y][x]
        img = img.resize((width, height), Image.Resampling.NEAREST)
        return ImageTk.PhotoImage(img)

    cell = _cell_size(theme.card_style)
    cols = max(8, (width + cell - 1) // cell)
    rows = max(8, (height + cell - 1) // cell)
    grid = _paint_pixel_grid(theme, cols, rows, tint=tint)
    if HAS_PIL:
        return _photo_from_grid_pil(grid, cell, width, height)
    return _photo_from_grid_tk(grid, cell, width, height)


def wallpaper_png_bytes(
    theme: GameTheme,
    width: int,
    height: int,
    *,
    tint: str | None = None,
) -> bytes:
    """Same pixel wallpaper as the window UI, as a PNG (for the browser)."""
    if not HAS_PIL:
        raise RuntimeError("Pillow is required for browser wallpapers.")
    width = max(64, int(width))
    height = max(64, int(height))
    if theme.card_style == "village":
        logical_w, logical_h = 160, 90
        grid = _paint_pixel_grid(theme, logical_w, logical_h, tint=tint)
        img = Image.new("RGB", (logical_w, logical_h))
        pixels = img.load()
        assert pixels is not None
        for y in range(logical_h):
            for x in range(logical_w):
                pixels[x, y] = grid[y][x]
        img = img.resize((width, height), Image.Resampling.NEAREST)
    else:
        cell = _cell_size(theme.card_style)
        cols = max(8, (width + cell - 1) // cell)
        rows = max(8, (height + cell - 1) // cell)
        grid = _paint_pixel_grid(theme, cols, rows, tint=tint)
        rows_n = len(grid)
        cols_n = len(grid[0]) if rows_n else 1
        img = Image.new("RGB", (cols_n, rows_n))
        pixels = img.load()
        assert pixels is not None
        for y in range(rows_n):
            for x in range(cols_n):
                pixels[x, y] = grid[y][x]
        img = img.resize((cols_n * cell, rows_n * cell), Image.Resampling.NEAREST)
        if img.size != (width, height):
            canvas = Image.new(
                "RGB", (width, height), grid[0][0] if rows_n and cols_n else (0, 0, 0)
            )
            canvas.paste(img, (0, 0))
            img = canvas.crop((0, 0, width, height))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
