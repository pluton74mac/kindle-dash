#!/usr/bin/env python3
"""
Kindle Dashboard View Server — Template

Serves PNG images + JSON tap maps over HTTP for a jailbroken Kindle.
The Kindle fetches GET /view?path=<name> and receives:
  - A PNG image path (rendered by PIL/Pillow)
  - A tap map (JSON array of {x, y, w, h, action, target} regions)
  - Navigation metadata (back path, refresh interval)

Architecture: Kindle is a dumb display. This server owns all view logic.
New views = new Python functions here. Kindle code never changes.

Requirements:
  - Python 3.9+ with Pillow
  - Mac or any server on the same WiFi as the Kindle

Usage:
  python3 view_server.py              # binds 0.0.0.0 (LAN)
  python3 view_server.py --bind 127.0.0.1  # localhost only
  # Then on Kindle: sh dash_interactive.sh http://SERVER_IP:8888
"""
import json
import re
import sys
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

# ── Config ──
PORT = 8888
WIDTH = 1072    # Kindle Paperwhite 4 (portrait)
HEIGHT = 1448

# ── Font helper ──
def find_font(size):
    """Find a usable font. Works on macOS and Linux."""
    candidates = [
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/Menlo.ttc",
        "/System/Library/Fonts/Monaco.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    for c in candidates:
        if Path(c).exists():
            try:
                return ImageFont.truetype(c, size)
            except Exception:
                continue
    return ImageFont.load_default()


# ── View renderers ──
# Each renderer returns (PIL.Image, list_of_tap_regions, back_path, refresh_sec)

def render_home():
    """Home view: briefing card + 4 navigation buttons."""
    img = Image.new("L", (WIDTH, HEIGHT), 255)
    draw = ImageDraw.Draw(img)

    font_title = find_font(52)
    font_body = find_font(36)
    font_button = find_font(42)

    # Header bar
    draw.rectangle([0, 0, WIDTH, 80], fill=0)
    draw.text((30, 15), "E-INK DASHBOARD", fill=255, font=font_title)

    # Briefing card
    briefing_y = 100
    draw.rectangle([20, briefing_y, WIDTH-20, briefing_y+500], outline=0, width=3)
    draw.text((40, briefing_y+20), "DAILY BRIEFING", fill=0, font=font_title)
    # ... add your briefing lines here ...

    # 4 nav buttons (2x2 grid)
    btn_y = 650
    btn_w = (WIDTH - 60) // 2
    btn_h = 320
    buttons = [
        {"label": "CALENDAR", "action": "calendar/today", "col": 0, "row": 0},
        {"label": "CRON JOBS", "action": "cron/list", "col": 1, "row": 0},
        {"label": "COACHING",  "action": "coaching/readiness", "col": 0, "row": 1},
        {"label": "WORKFLOWS", "action": "workflows/active", "col": 1, "row": 1},
    ]
    taps = []
    for btn in buttons:
        x = 20 + btn["col"] * (btn_w + 20)
        y = btn_y + btn["row"] * (btn_h + 20)
        draw.rectangle([x, y, x+btn_w, y+btn_h], outline=0, width=4)
        # Center label
        bbox = draw.textbbox((0,0), btn["label"], font=font_button)
        tw, th = bbox[2]-bbox[0], bbox[3]-bbox[1]
        draw.text((x + (btn_w-tw)//2, y + (btn_h-th)//2), btn["label"], fill=0, font=font_button)
        taps.append({"x": x, "y": y, "w": btn_w, "h": btn_h,
                      "action": "navigate", "target": btn["action"], "label": btn["label"]})

    return img, taps, None, 3600


def render_subview(title, lines):
    """Generic sub-view: title, text lines, back button."""
    img = Image.new("L", (WIDTH, HEIGHT), 255)
    draw = ImageDraw.Draw(img)
    font_title = find_font(52)
    font_body = find_font(36)
    font_button = find_font(42)

    draw.rectangle([0, 0, WIDTH, 80], fill=0)
    draw.text((30, 15), title, fill=255, font=font_title)
    for i, line in enumerate(lines):
        draw.text((40, 120 + i*42), line, fill=0, font=font_body)

    # Back button
    back_y = HEIGHT - 150
    back_x = (WIDTH - 400) // 2
    draw.rectangle([back_x, back_y, back_x+400, back_y+100], outline=0, width=4)
    bbox = draw.textbbox((0,0), "< BACK", font=font_button)
    tw, th = bbox[2]-bbox[0], bbox[3]-bbox[1]
    draw.text((back_x + (400-tw)//2, back_y + (100-th)//2), "< BACK", fill=0, font=font_button)

    taps = [{"x": back_x, "y": back_y, "w": 400, "h": 100,
             "action": "navigate", "target": "home", "label": "Back"}]
    return img, taps, "home", 1800


# ── View router ──
def render_view(path):
    """Route path to renderer. Returns (img, taps, back, refresh_sec)."""
    if path in ("home", "/", ""):
        return render_home()
    # Add your views here:
    # elif path == "calendar/today":
    #     return render_subview("CALENDAR", [...])
    else:
        # 404
        img = Image.new("L", (WIDTH, HEIGHT), 255)
        draw = ImageDraw.Draw(img)
        draw.text((100, 200), "404: View not found", fill=0, font=find_font(42))
        draw.text((100, 260), f"Path: {path}", fill=0, font=find_font(36))
        taps = [{"x": 100, "y": 400, "w": WIDTH-200, "h": 100,
                 "action": "navigate", "target": "home", "label": "Back"}]
        return img, taps, "home", 0


# ── HTTP server ──
class ViewHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = self.path.split("?")[0]
        query = {}
        if "?" in self.path:
            from urllib.parse import parse_qs
            query = {k: v[0] for k, v in parse_qs(self.path.split("?")[1]).items()}

        if parsed == "/view":
            view_path = query.get("path", "home")
            img, taps, back, refresh = render_view(view_path)

            # Save PNG
            img_dir = Path("/tmp/kindle-dash")
            img_dir.mkdir(exist_ok=True)
            img_name = view_path.replace("/", "_")
            img_path = img_dir / f"{img_name}.png"
            img.save(str(img_path), format="PNG")

            response = {
                "version": 1,
                "title": view_path,
                "image": f"/images/{img_name}.png",
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

        elif parsed.startswith("/images/"):
            img_name = parsed.replace("/images/", "")
            # Sanitize: only allow alphanumeric, underscore, hyphen, dot
            if not re.match(r'^[a-zA-Z0-9_\-.]+$', img_name):
                self.send_error(403, "Invalid image name")
                return
            img_path = Path("/tmp/kindle-dash") / img_name
            # Ensure resolved path stays under /tmp/kindle-dash (path traversal guard)
            if not str(img_path.resolve()).startswith("/tmp/kindle-dash"):
                self.send_error(403, "Path traversal detected")
                return
            if img_path.exists():
                img_bytes = img_path.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(img_bytes)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(img_bytes)
            else:
                self.send_error(404)

        elif parsed == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True, "port": PORT}).encode())
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path.startswith("/tap"):
            content_len = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_len)
            try:
                data = json.loads(body)
            except (json.JSONDecodeError, ValueError) as e:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"ok": False, "error": str(e)}).encode())
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True, "received": data}).encode())
        else:
            self.send_error(404)

    def log_message(self, fmt, *args):
        print(f"[{time.strftime('%H:%M:%S')}] {args[0]}")


if __name__ == "__main__":
    bind_addr = "0.0.0.0"
    for i, arg in enumerate(sys.argv):
        if arg == "--bind" and i + 1 < len(sys.argv):
            bind_addr = sys.argv[i + 1]
    server = HTTPServer((bind_addr, PORT), ViewHandler)
    print(f"Kindle Dashboard View Server")
    print(f"  Listening on {bind_addr}:{PORT}")
    print(f"  Kindle fetches: http://<this-ip>:{PORT}/view?path=home")
    print(f"  Test: http://localhost:{PORT}/view?path=home")
    print(f"  Use --bind 127.0.0.1 for local-only access")
    print(f"  Ctrl+C to stop")
    server.serve_forever()
