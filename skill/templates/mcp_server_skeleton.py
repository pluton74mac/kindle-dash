#!/usr/bin/env python3
"""
Kindle Dashboard MCP Server — skeleton template.
Demonstrates the stdio MCP + HTTP thread + Pillow renderer pattern.

This is NOT production code. It's a starting point showing:
1. How to run MCP stdio handler + HTTP server in the same process
2. How update_view() renders a PNG via a type-dispatched renderer
3. How push_home_card() updates the home grid
4. Disk persistence layout

Copy this to your project, fill in the renderers, register in config.yaml.

Dependencies: mcp (pip install mcp), Pillow
"""
import json
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

# ── Config ──
HTTP_PORT = 8888
WIDTH, HEIGHT = 1072, 1448
DATA_DIR = Path("/tmp/kindle-dash")
DATA_DIR.mkdir(exist_ok=True)

# ── State (in-memory, backed by disk) ──
view_registry = {}  # path → {type, title, updated_at, agent_id}
home_cards = {}      # agent_id → {title, summary, nav_target}

# ── Font helper ──
def find_font(size):
    for path in ["/System/Library/Fonts/Helvetica.ttc", "/System/Library/Fonts/Menlo.ttc"]:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()

# ── Renderers (one per view type) ──
# Each renderer takes (data) and returns (img, taps, back, refresh_sec)

def render_status_grid(data):
    """Home view: grid of agent cards."""
    img = Image.new("L", (WIDTH, HEIGHT), 255)
    draw = ImageDraw.Draw(img)
    # ... draw cards from data["cards"] ...
    taps = []
    # ... build tap regions for each card ...
    return img, taps, None, 0

def render_metric_dashboard(data):
    """Hero number + factor bars + optional safety gate."""
    img = Image.new("L", (WIDTH, HEIGHT), 255)
    draw = ImageDraw.Draw(img)
    # ... draw hero, factors, gate ...
    return img, [], "home", 0

def render_text_list(data):
    """Title + rows with status indicators."""
    img = Image.new("L", (WIDTH, HEIGHT), 255)
    draw = ImageDraw.Draw(img)
    # ... draw header, rows ...
    return img, [], "home", 0

def render_chart_view(data):
    """Hero value + sparkline + baseline."""
    img = Image.new("L", (WIDTH, HEIGHT), 255)
    draw = ImageDraw.Draw(img)
    # ... draw hero, sparkline, caption ...
    return img, [], "home", 0

def render_progress_view(data):
    """Progress bars + stacked bar + items."""
    img = Image.new("L", (WIDTH, HEIGHT), 255)
    draw = ImageDraw.Draw(img)
    # ... draw bars, items ...
    return img, [], "home", 0

RENDERERS = {
    "status_grid": render_status_grid,
    "metric_dashboard": render_metric_dashboard,
    "text_list": render_text_list,
    "chart_view": render_chart_view,
    "progress_view": render_progress_view,
}

# ── Core: render + persist a view ──
def render_and_save(path, data):
    view_type = data.get("type")
    renderer = RENDERERS.get(view_type)
    if not renderer:
        return False, f"Unknown view type: {view_type}"

    img, taps, back, refresh_sec = renderer(data)
    
    # Save PNG to disk
    img_name = path.replace("/", "_")
    img_path = DATA_DIR / f"{img_name}.png"
    img.save(str(img_path), format="PNG")

    # Save view metadata
    meta = {
        "version": 1,
        "title": data.get("title", path),
        "image": f"/images/{img_name}.png",
        "taps": taps,
        "back": back,
        "refresh_sec": refresh_sec,
        "error": None,
        "cache": {"key": path, "ttl_sec": 0},
    }
    meta_path = DATA_DIR / f"{img_name}.json"
    meta_path.write_text(json.dumps(meta, indent=2))

    # Update registry
    view_registry[path] = {
        "type": view_type,
        "title": data.get("title", path),
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    
    return True, None

def render_home():
    """Compose home view from registered cards."""
    cards = []
    for agent_id, card in home_cards.items():
        cards.append({"agent_id": agent_id, **card})
    render_and_save("home", {"type": "status_grid", "title": "Dashboard", "cards": cards})

# ── HTTP Server (background thread) ──
class ViewHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = self.path.split("?")[0]
        query = {}
        if "?" in self.path:
            from urllib.parse import parse_qs
            query = {k: v[0] for k, v in parse_qs(self.path.split("?")[1]).items()}

        if parsed == "/view":
            path = query.get("path", "home")
            img_name = path.replace("/", "_")
            meta_path = DATA_DIR / f"{img_name}.json"
            if meta_path.exists():
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(meta_path.read_bytes())
            else:
                self.send_error(404, f"View not found: {path}")

        elif parsed.startswith("/images/"):
            img_name = parsed.replace("/images/", "")
            img_path = DATA_DIR / img_name
            if img_path.exists():
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.end_headers()
                self.wfile.write(img_path.read_bytes())
            else:
                self.send_error(404, "Image not found")

        elif parsed == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True, "port": HTTP_PORT}).encode())

    def log_message(self, fmt, *args):
        pass  # Suppress logs (or print to stderr)

def start_http_server():
    server = HTTPServer(("0.0.0.0", HTTP_PORT), ViewHandler)
    server.serve_forever()

# ── MCP Tool Handlers (stdio) ──
# These are called by the agent agents via the MCP protocol.
# In production, use the `mcp` Python SDK to register these as MCP tools.

def handle_update_view(path: str, data: dict) -> dict:
    success, error = render_and_save(path, data)
    return {
        "success": success,
        "path": path,
        "image_url": f"/images/{path.replace('/', '_')}.png" if success else None,
        "rendered_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "error": error,
    }

def handle_push_home_card(agent_id: str, title: str, summary: list, nav_target: str) -> dict:
    home_cards[agent_id] = {"title": title, "summary": summary, "nav_target": nav_target}
    render_home()
    return {"success": True, "agent_id": agent_id, "home_rendered": True}

def handle_get_status() -> dict:
    return {
        "port": HTTP_PORT,
        "views_count": len(view_registry),
        "agents": list(home_cards.keys()),
    }

def handle_list_views() -> list:
    return [{"path": p, **v} for p, v in view_registry.items()]

# ── Main ──
if __name__ == "__main__":
    # Start HTTP server in background thread
    http_thread = threading.Thread(target=start_http_server, daemon=True)
    http_thread.start()
    print(f"HTTP server on :{HTTP_PORT}", flush=True)

    # TODO: Start MCP stdio handler here
    # from mcp.server import Server
    # server = Server("kindle-dash")
    # ... register tools: update_view, push_home_card, get_status, list_views ...
    # server.run()
    
    # For now, just keep alive
    print("MCP handler not yet implemented. HTTP server running.", flush=True)
    while True:
        time.sleep(1)
