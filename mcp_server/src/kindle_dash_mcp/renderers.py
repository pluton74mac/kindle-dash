"""Pillow renderers for the 5 Phase-1 view types (DECISIONS.md D03).

Every renderer has the signature `render_X(data: dict) -> (Image, taps, back, refresh_sec)`.
Agents never touch Pillow, e-ink, or tap-map geometry — they pick a `type` and pass
matching structured data to `update_view()`; the MCP server does the rest.

Grayscale-only palette note: e-ink has no color, so "status" (good/warning/bad) is
communicated with fill darkness and text labels, not hue.
"""
from __future__ import annotations

import time
from functools import lru_cache
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from . import config

W, H = config.SCREEN_WIDTH, config.SCREEN_HEIGHT

_FONT_CANDIDATES = [
    "/System/Library/Fonts/Helvetica.ttc",
    "/System/Library/Fonts/Menlo.ttc",
    "/System/Library/Fonts/Monaco.ttf",
    "/Library/Fonts/Arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
]

STATUS_FILL = {
    "good": 210, "ok": 210, "normal": 210, "cleared": 210,
    "warning": 140, "warn": 140, "caution": 140,
    "bad": 40, "low": 40, "critical": 0, "error": 0, "blocked": 0,
}
DEFAULT_STATUS_FILL = 180


@lru_cache(maxsize=None)
def _font(size: int) -> ImageFont.FreeTypeFont:
    for path in _FONT_CANDIDATES:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _text_size(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> tuple[int, int]:
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def _centered_text(draw, box, text, font, fill=0):
    x0, y0, x1, y1 = box
    tw, th = _text_size(draw, text, font)
    draw.text((x0 + (x1 - x0 - tw) // 2, y0 + (y1 - y0 - th) // 2), text, fill=fill, font=font)


def _new_canvas() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("L", (W, H), 255)
    return img, ImageDraw.Draw(img)


def _status_fill(status: str | None) -> int:
    if not status:
        return DEFAULT_STATUS_FILL
    return STATUS_FILL.get(status.lower(), DEFAULT_STATUS_FILL)


def _draw_header(draw: ImageDraw.ImageDraw, title: str) -> int:
    """Black title bar. Returns the y-coordinate content should start below."""
    bar_h = 80
    draw.rectangle([0, 0, W, bar_h], fill=0)
    draw.text((30, 15), title, fill=255, font=_font(48))
    now = time.strftime("%H:%M")
    tw, _ = _text_size(draw, now, _font(28))
    draw.text((W - tw - 24, 25), now, fill=255, font=_font(28))
    return bar_h + 20


def _draw_nav_buttons(draw: ImageDraw.ImageDraw, back: str | None) -> list[dict]:
    """Back (if any) + Exit buttons along the bottom. Returns their tap regions."""
    taps: list[dict] = []
    exit_w, exit_h = 180, 90
    margin = 20

    if back is not None:
        back_w = W - exit_w - margin * 3
        back_x, back_y = margin, H - exit_h - margin
        draw.rectangle([back_x, back_y, back_x + back_w, back_y + exit_h], outline=0, width=4)
        _centered_text(draw, (back_x, back_y, back_x + back_w, back_y + exit_h), "< BACK", _font(38))
        taps.append({"x": back_x, "y": back_y, "w": back_w, "h": exit_h,
                      "action": "navigate", "target": back, "label": "Back"})
        exit_x = back_x + back_w + margin
    else:
        exit_x = W - exit_w - margin

    exit_y = H - exit_h - margin
    draw.rectangle([exit_x, exit_y, exit_x + exit_w, exit_y + exit_h], outline=0, width=4)
    _centered_text(draw, (exit_x, exit_y, exit_x + exit_w, exit_y + exit_h), "EXIT", _font(38))
    taps.append({"x": exit_x, "y": exit_y, "w": exit_w, "h": exit_h,
                 "action": "exit", "target": "", "label": "Exit"})
    return taps


# ── status_grid: home view / any grid of navigable cards ──

def render_status_grid(data: dict) -> tuple[Image.Image, list[dict], str | None, int]:
    img, draw = _new_canvas()
    title = data.get("title", "Dashboard")
    content_y = _draw_header(draw, title)
    is_home = data.get("_home", False)

    cards: list[dict] = data.get("cards", [])
    taps: list[dict] = []

    nav_reserved = 0 if is_home else 130  # non-home grids also get a back button strip
    grid_bottom = H - nav_reserved - 20
    cols = 2
    margin = 20
    gap = 20
    card_w = (W - margin * 2 - gap * (cols - 1)) // cols

    if not cards:
        draw.text((margin, content_y + 20), "No agents connected yet.", fill=0, font=_font(34))
    else:
        rows = (len(cards) + cols - 1) // cols
        card_h = min(320, (grid_bottom - content_y - gap * (rows - 1)) // max(rows, 1))
        card_h = max(card_h, 140)

        for i, card in enumerate(cards):
            col, row = i % cols, i // cols
            x = margin + col * (card_w + gap)
            y = content_y + row * (card_h + gap)
            if y + card_h > grid_bottom:
                break  # caller is responsible for capping card count before this point
            draw.rectangle([x, y, x + card_w, y + card_h], outline=0, width=3)
            draw.text((x + 16, y + 12), card.get("title", "")[:28], fill=0, font=_font(32))
            for j, line in enumerate(card.get("summary", [])[:4]):
                draw.text((x + 16, y + 58 + j * 32), str(line)[:32], fill=0, font=_font(24))
            taps.append({"x": x, "y": y, "w": card_w, "h": card_h,
                         "action": "navigate", "target": card.get("nav_target", ""),
                         "label": card.get("title", "")})

    taps.extend(_draw_nav_buttons(draw, None if is_home else data.get("back", "home")))
    if is_home:
        draw.text((30, H - 40), "Tap a card to open it", fill=128, font=_font(24))
    return img, taps, None if is_home else data.get("back", "home"), data.get("refresh_sec", 0)


# ── metric_dashboard: hero number + factor bars + optional safety gate ──

def render_metric_dashboard(data: dict) -> tuple[Image.Image, list[dict], str | None, int]:
    img, draw = _new_canvas()
    title = data.get("title", "Metrics")
    y = _draw_header(draw, title)
    back = data.get("back", "home")

    gate = data.get("safety_gate")
    if gate and not gate.get("ok", True):
        band_h = 90
        draw.rectangle([0, y, W, y + band_h], fill=0)
        _centered_text(draw, (20, y, W - 20, y + band_h), str(gate.get("message", "BLOCKED")), _font(34), fill=255)
        y += band_h + 20
    elif gate and gate.get("message"):
        draw.text((30, y), str(gate["message"]), fill=100, font=_font(26))
        y += 40

    hero = data.get("hero") or {}
    if hero:
        value = str(hero.get("value", ""))
        unit = str(hero.get("unit", ""))
        label = str(hero.get("label", ""))
        draw.text((30, y), value, fill=0, font=_font(110))
        vw, _ = _text_size(draw, value, _font(110))
        if unit:
            draw.text((30 + vw + 14, y + 55), unit, fill=0, font=_font(34))
        if label:
            draw.text((30, y + 130), label, fill=90, font=_font(30))
        y += 180

    y += 20
    bar_x0, bar_x1 = 30, W - 30
    for factor in data.get("factors", []):
        name = str(factor.get("name", ""))
        percent = max(0, min(100, int(factor.get("percent", 0))))
        status = factor.get("status")

        draw.text((bar_x0, y), name, fill=0, font=_font(28))
        chip = f"{percent}%  {status.upper() if status else ''}".strip()
        cw, _ = _text_size(draw, chip, _font(24))
        draw.text((bar_x1 - cw, y + 4), chip, fill=0, font=_font(24))

        bar_y = y + 40
        bar_h = 26
        draw.rectangle([bar_x0, bar_y, bar_x1, bar_y + bar_h], outline=0, width=2)
        fill_w = int((bar_x1 - bar_x0 - 4) * percent / 100)
        if fill_w > 0:
            draw.rectangle([bar_x0 + 2, bar_y + 2, bar_x0 + 2 + fill_w, bar_y + bar_h - 2],
                            fill=_status_fill(status))
        y = bar_y + bar_h + 26

    taps = _draw_nav_buttons(draw, back)
    return img, taps, back, data.get("refresh_sec", 0)


# ── text_list: header + rows with left/right columns and a status marker ──

def render_text_list(data: dict) -> tuple[Image.Image, list[dict], str | None, int]:
    img, draw = _new_canvas()
    title = data.get("title", "List")
    y = _draw_header(draw, title)
    back = data.get("back", "home")

    header = data.get("header")
    if header:
        draw.text((30, y), str(header), fill=0, font=_font(32))
        y += 50

    row_h = 46
    for row in data.get("rows", []):
        if y + row_h > H - 140:
            draw.text((30, y), "...", fill=128, font=_font(28))
            break
        status = row.get("status")
        if status:
            draw.rectangle([30, y + 6, 46, y + 22], fill=_status_fill(status))
        left = str(row.get("left", ""))
        right = str(row.get("right", ""))
        draw.text((60, y), left, fill=0, font=_font(28))
        if right:
            rw, _ = _text_size(draw, right, _font(28))
            draw.text((W - 30 - rw, y), right, fill=0, font=_font(28))
        y += row_h

    taps = _draw_nav_buttons(draw, back)
    return img, taps, back, data.get("refresh_sec", 0)


# ── chart_view: hero value + sparkline + baseline + caption ──

def render_chart_view(data: dict) -> tuple[Image.Image, list[dict], str | None, int]:
    img, draw = _new_canvas()
    title = data.get("title", "Chart")
    y = _draw_header(draw, title)
    back = data.get("back", "home")

    hero = data.get("hero") or {}
    if hero:
        value = str(hero.get("value", ""))
        unit = str(hero.get("unit", ""))
        draw.text((30, y), value, fill=0, font=_font(90))
        vw, _ = _text_size(draw, value, _font(90))
        if unit:
            draw.text((30 + vw + 14, y + 45), unit, fill=0, font=_font(32))
        y += 130

    spark = data.get("sparkline") or {}
    values = [float(v) for v in spark.get("values", [])]
    chart_x0, chart_x1 = 40, W - 40
    chart_y0, chart_y1 = y + 20, y + 320

    if len(values) >= 2:
        baseline = spark.get("baseline")
        all_vals = values + ([float(baseline)] if baseline is not None else [])
        lo, hi = min(all_vals), max(all_vals)
        pad = (hi - lo) * 0.1 or 1.0
        lo, hi = lo - pad, hi + pad

        def sx(i):
            return chart_x0 + (chart_x1 - chart_x0) * i / (len(values) - 1)

        def sy(v):
            return chart_y1 - (chart_y1 - chart_y0) * (v - lo) / (hi - lo)

        draw.rectangle([chart_x0, chart_y0, chart_x1, chart_y1], outline=180, width=2)
        if baseline is not None:
            by = sy(float(baseline))
            for dx in range(int(chart_x0), int(chart_x1), 14):
                draw.line([(dx, by), (dx + 7, by)], fill=140, width=2)

        points = [(sx(i), sy(v)) for i, v in enumerate(values)]
        draw.line(points, fill=0, width=4, joint="curve")
        for px, py in points:
            draw.ellipse([px - 4, py - 4, px + 4, py + 4], fill=0)
        y = chart_y1 + 30
    else:
        draw.text((chart_x0, chart_y0 + 40), "Not enough data for a chart.", fill=128, font=_font(28))
        y = chart_y1 + 30

    caption = data.get("caption")
    if caption:
        draw.text((30, y), str(caption), fill=90, font=_font(26))

    taps = _draw_nav_buttons(draw, back)
    return img, taps, back, data.get("refresh_sec", 0)


# ── progress_view: individual bars + optional stacked bar + item list ──

def render_progress_view(data: dict) -> tuple[Image.Image, list[dict], str | None, int]:
    img, draw = _new_canvas()
    title = data.get("title", "Progress")
    y = _draw_header(draw, title)
    back = data.get("back", "home")

    bar_x0, bar_x1 = 30, W - 30
    for bar in data.get("bars", []):
        label = str(bar.get("label", ""))
        value = float(bar.get("value", 0))
        vmax = float(bar.get("max", 1)) or 1.0
        frac = max(0.0, min(1.0, value / vmax))

        draw.text((bar_x0, y), label, fill=0, font=_font(28))
        readout = f"{value:g}/{vmax:g}"
        rw, _ = _text_size(draw, readout, _font(24))
        draw.text((bar_x1 - rw, y + 4), readout, fill=0, font=_font(24))

        bar_y = y + 38
        bar_h = 24
        draw.rectangle([bar_x0, bar_y, bar_x1, bar_y + bar_h], outline=0, width=2)
        fill_w = int((bar_x1 - bar_x0 - 4) * frac)
        if fill_w > 0:
            draw.rectangle([bar_x0 + 2, bar_y + 2, bar_x0 + 2 + fill_w, bar_y + bar_h - 2], fill=60)
        y = bar_y + bar_h + 22

    stacked = data.get("stacked_bar")
    if stacked and stacked.get("segments"):
        y += 10
        segments = stacked["segments"]
        smax = float(stacked.get("max") or sum(s.get("value", 0) for s in segments) or 1.0)
        bar_y, bar_h = y, 40
        x = bar_x0
        palette = [40, 100, 160, 210]
        for i, seg in enumerate(segments):
            seg_w = int((bar_x1 - bar_x0) * float(seg.get("value", 0)) / smax)
            fill = palette[i % len(palette)]
            draw.rectangle([x, bar_y, x + seg_w, bar_y + bar_h], fill=fill, outline=0)
            x += seg_w
        draw.rectangle([bar_x0, bar_y, bar_x1, bar_y + bar_h], outline=0, width=2)
        y = bar_y + bar_h + 16
        for i, seg in enumerate(segments):
            fill = palette[i % len(palette)]
            sw_x = bar_x0 + (i % 3) * 340
            sw_y = y + (i // 3) * 34
            draw.rectangle([sw_x, sw_y + 4, sw_x + 20, sw_y + 24], fill=fill, outline=0)
            draw.text((sw_x + 30, sw_y), f"{seg.get('label', '')} ({seg.get('value', 0):g})",
                       fill=0, font=_font(22))
        y += ((len(segments) + 2) // 3) * 34 + 16

    items = data.get("items", [])
    if items:
        y += 10
        for item in items:
            if y > H - 160:
                draw.text((bar_x0, y), "...", fill=128, font=_font(26))
                break
            draw.text((bar_x0, y), f"• {item}", fill=0, font=_font(26))
            y += 34

    taps = _draw_nav_buttons(draw, back)
    return img, taps, back, data.get("refresh_sec", 0)


RENDERERS = {
    "status_grid": render_status_grid,
    "metric_dashboard": render_metric_dashboard,
    "text_list": render_text_list,
    "chart_view": render_chart_view,
    "progress_view": render_progress_view,
}


def render(view_type: str, data: dict[str, Any]):
    renderer = RENDERERS.get(view_type)
    if renderer is None:
        raise ValueError(f"Unknown view type: {view_type!r}. Known types: {sorted(RENDERERS)}")
    return renderer(data)
