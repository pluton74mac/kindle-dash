#!/usr/bin/env python3
"""
Minimal view server for Kindle the agent Dashboard spike.
Serves a PNG image + JSON tap map over HTTP.
Designed for Kindle Paperwhite 4 (1072×1448, portrait).
"""
import json
import re
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

PORT = 8888
WIDTH = 1072
HEIGHT = 1448
IMG_DIR = Path("/tmp/kindle-dash").resolve()
SAFE_NAME = re.compile(r"^[a-zA-Z0-9_\-.]+$")

# Shared state for tap feedback
last_tap = None


def find_font(size):
    """Find a usable font on macOS."""
    candidates = [
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/Menlo.ttc",
        "/System/Library/Fonts/Monaco.ttf",
        "/Library/Fonts/Arial.ttf",
    ]
    for c in candidates:
        if Path(c).exists():
            try:
                return ImageFont.truetype(c, size)
            except Exception:
                continue
    return ImageFont.load_default()


def render_home():
    """Render the home view: daily briefing + 4 nav buttons."""
    img = Image.new("L", (WIDTH, HEIGHT), 255)  # white, 8-bit grayscale
    draw = ImageDraw.Draw(img)

    font_title = find_font(52)
    font_body = find_font(36)
    font_small = find_font(28)
    font_button = find_font(42)

    # ── Header ──
    draw.rectangle([0, 0, WIDTH, 80], fill=0)  # black bar
    draw.text((30, 15), "E-INK DASHBOARD", fill=255, font=font_title)

    now = time.strftime("%a %b %d, %H:%M")
    draw.text((WIDTH - 320, 25), now, fill=255, font=font_small)

    # ── Daily Briefing Card (top half) ──
    briefing_y = 100
    briefing_h = 500
    draw.rectangle([20, briefing_y, WIDTH - 20, briefing_y + briefing_h], outline=0, width=3)

    draw.text((40, briefing_y + 20), "DAILY BRIEFING", fill=0, font=font_title)

    briefing_lines = [
        "✅ Readiness: 74/100 — Moderate",
        "✅ HRV: 92ms (balanced, declining trend)",
        "⚠️  Body Battery: 18/100 — low",
        "✅ RHR: 51 bpm — stable",
        "✅ VO2 Max: 54.0 — flat 31 days",
        "",
        "Today: light/recovery or rest.",
        "HRV decline suggests backing off.",
        "Keep it Z1–Z2 if you train.",
    ]
    for i, line in enumerate(briefing_lines):
        draw.text((40, briefing_y + 100 + i * 38), line, fill=0, font=font_body)

    # ── 4 Navigation Buttons (bottom half) ──
    btn_y = 650
    btn_w = (WIDTH - 60) // 2  # 2 columns, 20px margins + 20px gap
    btn_h = 320
    gap = 20

    buttons = [
        {"label": "📅 CALENDAR", "action": "calendar/today", "col": 0, "row": 0},
        {"label": "⏰ CRON JOBS", "action": "cron/list", "col": 1, "row": 0},
        {"label": "🏃 COACHING", "action": "coaching/readiness", "col": 0, "row": 1},
        {"label": "⚙️  WORKFLOWS", "action": "workflows/active", "col": 1, "row": 1},
    ]

    taps = []
    for btn in buttons:
        x = 20 + btn["col"] * (btn_w + gap)
        y = btn_y + btn["row"] * (btn_h + gap)
        # Draw button box
        draw.rectangle([x, y, x + btn_w, y + btn_h], outline=0, width=4)
        # Center the label
        bbox = draw.textbbox((0, 0), btn["label"], font=font_button)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        tx = x + (btn_w - tw) // 2
        ty = y + (btn_h - th) // 2
        draw.text((tx, ty), btn["label"], fill=0, font=font_button)
        # Register tap region
        taps.append({
            "x": x, "y": y, "w": btn_w, "h": btn_h,
            "action": "navigate", "target": btn["action"],
            "label": btn["label"]
        })

    # ── Footer ──
    draw.text((30, HEIGHT - 50), "Tap a button to navigate • Auto-refresh 60min", fill=128, font=font_small)

    # ── Exit button (bottom-right corner) ──
    exit_w = 180
    exit_h = 50
    exit_x = WIDTH - exit_w - 20
    exit_y = HEIGHT - exit_h - 20
    draw.rectangle([exit_x, exit_y, exit_x + exit_w, exit_y + exit_h], outline=0, width=3)
    bbox = draw.textbbox((0, 0), "✕ EXIT", font=font_small)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    draw.text((exit_x + (exit_w - tw) // 2, exit_y + (exit_h - th) // 2), "✕ EXIT", fill=0, font=font_small)
    taps.append({
        "x": exit_x, "y": exit_y, "w": exit_w, "h": exit_h,
        "action": "exit", "target": "", "label": "Exit"
    })

    # If there was a tap, show it
    if last_tap:
        draw.text((WIDTH - 300, HEIGHT - 50), f"Last tap: {last_tap}", fill=128, font=font_small)

    return img, taps


def render_subview(title, lines):
    """Render a simple sub-view with a title, text lines, and a back button."""
    img = Image.new("L", (WIDTH, HEIGHT), 255)
    draw = ImageDraw.Draw(img)

    font_title = find_font(52)
    font_body = find_font(36)
    font_small = find_font(28)
    font_button = find_font(42)

    # Header
    draw.rectangle([0, 0, WIDTH, 80], fill=0)
    draw.text((30, 15), title, fill=255, font=font_title)

    # Content
    for i, line in enumerate(lines):
        draw.text((40, 120 + i * 42), line, fill=0, font=font_body)

    # Back + Exit buttons at bottom
    back_y = HEIGHT - 150
    back_w = 400
    exit_w = 180
    exit_h = 100
    gap = 20
    total_w = back_w + gap + exit_w
    start_x = (WIDTH - total_w) // 2

    # Back button
    back_x = start_x
    draw.rectangle([back_x, back_y, back_x + back_w, back_y + 100], outline=0, width=4)
    bbox = draw.textbbox((0, 0), "← BACK", font=font_button)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    draw.text((back_x + (back_w - tw) // 2, back_y + (100 - th) // 2), "← BACK", fill=0, font=font_button)

    # Exit button
    exit_x = back_x + back_w + gap
    draw.rectangle([exit_x, back_y, exit_x + exit_w, back_y + exit_h], outline=0, width=4)
    bbox = draw.textbbox((0, 0), "✕ EXIT", font=font_button)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    draw.text((exit_x + (exit_w - tw) // 2, back_y + (exit_h - th) // 2), "✕ EXIT", fill=0, font=font_button)

    taps = [
        {
            "x": back_x, "y": back_y, "w": back_w, "h": 100,
            "action": "navigate", "target": "home", "label": "Back"
        },
        {
            "x": exit_x, "y": back_y, "w": exit_w, "h": exit_h,
            "action": "exit", "target": "", "label": "Exit"
        }
    ]

    # Footer
    draw.text((30, HEIGHT - 40), f"View: {title}", fill=128, font=font_small)

    return img, taps


def render_lock_screen():
    """Render a minimal lock screen: time, date, battery, next event."""
    img = Image.new("L", (WIDTH, HEIGHT), 0)  # black background
    draw = ImageDraw.Draw(img)

    font_clock = find_font(120)
    font_date = find_font(48)
    font_small = find_font(28)
    font_battery = find_font(36)

    # ── Clock (centered, upper third) ──
    now = time.time()
    time_str = time.strftime("%H:%M")
    date_str = time.strftime("%A, %B %d")

    bbox = draw.textbbox((0, 0), time_str, font=font_clock)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    cx = (WIDTH - tw) // 2
    cy = 300
    draw.text((cx, cy), time_str, fill=255, font=font_clock)

    # ── Date (below clock) ──
    bbox = draw.textbbox((0, 0), date_str, font=font_date)
    dw = bbox[2] - bbox[0]
    draw.text(((WIDTH - dw) // 2, cy + th + 30), date_str, fill=200, font=font_date)

    # ── Battery level (bottom-right) ──
    draw.text((WIDTH - 180, HEIGHT - 80), "🔋 87%", fill=200, font=font_battery)

    # ── Next event (bottom-left) ──
    draw.text((40, HEIGHT - 80), "Next: 17:00 Z2 Run", fill=200, font=font_small)

    # ── "Kindle the agent" label (top, faint) ──
    label = "KINDLE DASH"
    bbox = draw.textbbox((0, 0), label, font=font_small)
    lw = bbox[2] - bbox[0]
    draw.text(((WIDTH - lw) // 2, 60), label, fill=120, font=font_small)

    return img, []  # no taps — lock screen is not interactive


def render_view(path):
    """Route a view path to the appropriate renderer."""
    global last_tap

    if path == "lock_screen":
        img, taps = render_lock_screen()
        return img, taps, None, 0

    if path == "home" or path == "/" or path == "":
        img, taps = render_home()
        return img, taps, None, 3600

    elif path == "calendar/today":
        lines = [
            "📅 Today's Calendar",
            "",
            "09:00 — Daily Briefing (cron)",
            "12:30 — Lunch",
            "17:00 — Z2 Run (planned)",
            "18:30 — Dinner",
            "21:00 — Kindle dashboard refresh",
            "",
            "No more events today.",
        ]
        img, taps = render_subview("CALENDAR", lines)
        return img, taps, "home", 1800

    elif path == "cron/list":
        lines = [
            "⏰ Cron Jobs",
            "",
            "✅ morning-brief    7am daily    last: ok",
            "✅ kindle-refresh  every 60min  last: ok",
            "⏳ data-sync       every 5min   running...",
            "❌ backup-check     3am daily    last: FAILED",
            "",
            "4 jobs total, 3 healthy, 1 failing",
        ]
        img, taps = render_subview("CRON JOBS", lines)
        return img, taps, "home", 300

    elif path == "coaching/readiness":
        lines = [
            "🏃 Training Readiness",
            "",
            "Score:        74/100 (Moderate)",
            "Recovery:     7.7h remaining (87%)",
            "Load:         100% — Very Good",
            "HRV:          90% — Good",
            "Stress:       67% — Moderate",
            "Sleep hist:   68% — Moderate",
            "",
            "HRV 7-day:    ⚠️ Declining (-53.8%)",
            "Body Battery: 18/100 — LOW",
            "RHR:          51 bpm — stable",
            "",
            "Verdict: Light/recovery or rest.",
        ]
        img, taps = render_subview("COACHING", lines)
        return img, taps, "home", 1800

    elif path == "workflows/active":
        lines = [
            "⚙️  Active Workflows",
            "",
            "None currently running.",
            "",
            "Recent completed:",
            "  • research-pass (3 agents) — done",
            "  • morning-briefing — done",
            "",
            "Tap to trigger:",
            "  (not implemented in spike)",
        ]
        img, taps = render_subview("WORKFLOWS", lines)
        return img, taps, "home", 0

    else:
        # Unknown view — render error
        img = Image.new("L", (WIDTH, HEIGHT), 255)
        draw = ImageDraw.Draw(img)
        font = find_font(42)
        draw.text((100, 200), f"404: View not found", fill=0, font=font)
        draw.text((100, 260), f"Path: {path}", fill=0, font=find_font(36))
        taps = [{
            "x": 100, "y": 400, "w": WIDTH - 200, "h": 100,
            "action": "navigate", "target": "home", "label": "Back to home"
        }]
        return img, taps, "home", 0


class ViewHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global last_tap

        parsed_path = self.path.split("?")[0]
        query = {}
        if "?" in self.path:
            from urllib.parse import parse_qs
            query = {k: v[0] for k, v in parse_qs(self.path.split("?")[1]).items()}

        if parsed_path == "/view":
            view_path = query.get("path", "home")
            img, taps, back, refresh = render_view(view_path)

            # Save PNG
            IMG_DIR.mkdir(exist_ok=True)
            img_path = IMG_DIR / f"{view_path.replace('/', '_')}.png"
            img.save(str(img_path), format="PNG")

            response = {
                "version": 1,
                "title": view_path,
                "image": f"/images/{view_path.replace('/', '_')}.png",
                "taps": taps,
                "back": back,
                "refresh_sec": refresh,
                "error": None,
                "cache": {"key": view_path, "ttl_sec": refresh or 3600}
            }

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(response, indent=2).encode())

        elif parsed_path.startswith("/images/"):
            img_name = parsed_path[len("/images/"):]
            if not SAFE_NAME.match(img_name):
                self.send_error(403, "Invalid image name")
                return
            img_path = (IMG_DIR / img_name).resolve()
            if img_path.parent != IMG_DIR or not img_path.exists():
                self.send_error(404, "Image not found")
                return
            body = img_path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)

        elif parsed_path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True, "port": PORT}).encode())

        else:
            self.send_error(404, f"Unknown path: {parsed_path}")

    def do_POST(self):
        global last_tap
        if self.path.startswith("/tap"):
            content_len = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_len)
            data = json.loads(body)
            last_tap = data.get("label", str(data.get("x", "?")))
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True, "received": data}).encode())
        else:
            self.send_error(404)

    def log_message(self, format, *args):
        print(f"[{time.strftime('%H:%M:%S')}] {args[0]}")


if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", PORT), ViewHandler)
    print(f"🔍 Kindle Dashboard View Server")
    print(f"   Listening on 0.0.0.0:{PORT}")
    print(f"   Kindle should fetch: http://YOUR_SERVER_IP:{PORT}/view?path=home")
    print(f"   Test: http://localhost:{PORT}/view?path=home")
    print(f"   Ctrl+C to stop")
    print()
    server.serve_forever()
