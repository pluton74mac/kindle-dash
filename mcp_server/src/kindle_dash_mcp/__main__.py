"""Entrypoint: start the HTTP thread, ensure a home view exists, then run the MCP
stdio server. This blocks on stdio — an agent framework manages this as a subprocess
so nothing here needs its own daemonization.
"""
from __future__ import annotations

from . import http_server, store
from .server import build_home_view, mcp


def main() -> None:
    http_server.start()
    if store.get_view_meta("home") is None:
        build_home_view()
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
