"""Kindle-facing HTTP server: the 3 endpoints the shell viewer polls.

Runs as a background thread inside the MCP process (DECISIONS.md D03 — stdio MCP,
HTTP as a thread, not a separate daemon). Pure read path over what `store.py` has
persisted to disk; it doesn't know or care whether an agent is currently connected.
"""
from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlsplit

from . import config, store


class ViewHandler(BaseHTTPRequestHandler):
    server_version = "KindleDashMCP/1.0"

    def do_GET(self):
        parsed = urlsplit(self.path)
        query = {k: v[0] for k, v in parse_qs(parsed.query).items()}

        if parsed.path == "/view":
            self._handle_view(query.get("path", "home"))
        elif parsed.path.startswith("/images/"):
            self._handle_image(parsed.path[len("/images/"):])
        elif parsed.path == "/health":
            self._json(200, {"ok": True, "port": config.HTTP_PORT, "views": store.registry_count()})
        else:
            self.send_error(404, f"Unknown path: {parsed.path}")

    def _handle_view(self, path: str):
        meta = store.get_view_meta(path)
        if meta is None:
            self.send_error(404, f"View not found: {path}")
            return
        self._json(200, meta)

    def _handle_image(self, name: str):
        img_path = store.get_image_path(name)
        if img_path is None:
            self.send_error(404, "Image not found")
            return
        body = img_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, payload: dict):
        # indent=2 is load-bearing, not cosmetic: the Kindle's awk tap parser
        # (dash_interactive.sh) scans line-by-line and expects each field and each
        # tap object's closing "}" on its own line. Compact single-line JSON breaks it.
        body = json.dumps(payload, indent=2).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        print(f"[http {time.strftime('%H:%M:%S')}] {self.address_string()} {fmt % args}", flush=True)


def start() -> HTTPServer:
    server = HTTPServer((config.HTTP_HOST, config.HTTP_PORT), ViewHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True, name="kindle-dash-http")
    thread.start()
    print(f"[kindle-dash-mcp] HTTP server listening on {config.HTTP_HOST}:{config.HTTP_PORT}", flush=True)
    return server
