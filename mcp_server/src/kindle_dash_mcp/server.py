"""MCP tool surface (DECISIONS.md D03): update_view, push_home_card, get_status, list_views.

Agents are data pushers, not UI designers — this module is the only place that
turns their calls into rendered PNGs on disk. `home` and the `system/` namespace
are reserved: home is built exclusively from `push_home_card()` calls, and
`system/agents` is an auto-generated overview so a dashboard with more agents than
fit on the home grid stays fully browsable.
"""
import io
import time

from mcp.server.fastmcp import FastMCP
from PIL import Image

from . import config, renderers, store

mcp = FastMCP("kindle-dash")

RESERVED_PATHS = {"home"}
RESERVED_NAMESPACES = {"system"}

_START_TIME = time.time()


def _save_render(path: str, view_type: str, data: dict, image: Image.Image,
                  taps: list, back: str | None, refresh_sec: int) -> dict:
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    meta = {
        "version": 1,
        "title": data.get("title", path),
        "image": f"/images/{store.path_to_name(path)}.png",
        "taps": taps,
        "back": back,
        "refresh_sec": refresh_sec,
        "error": None,
        "cache": {"key": path, "ttl_sec": refresh_sec},
        "_view_type": view_type,
    }
    store.save_view(path, meta, buf.getvalue())
    return meta


def render_and_save(path: str, data: dict) -> dict:
    view_type = data.get("type")
    if not view_type:
        raise ValueError(f"data.type is required (one of: {sorted(renderers.RENDERERS)})")
    image, taps, back, refresh_sec = renderers.render(view_type, data)
    return _save_render(path, view_type, data, image, taps, back, refresh_sec)


def build_home_view() -> dict:
    """Compose the home grid from all registered agents' cards. Reserved path."""
    cards_by_agent = store.get_home_cards()
    ordered = sorted(cards_by_agent.items(), key=lambda kv: kv[1]["slot"])
    overflow = len(ordered) > config.HOME_MAX_CARDS
    shown = ordered[: config.HOME_MAX_CARDS - 1] if overflow else ordered

    cards = [
        {"agent_id": agent_id, "title": c["title"], "summary": c["summary"], "nav_target": c["nav_target"]}
        for agent_id, c in shown
    ]
    if overflow:
        cards.append({
            "agent_id": "_more",
            "title": f"+{len(ordered) - len(shown)} more",
            "summary": ["Tap to see all connected agents"],
            "nav_target": "system/agents",
        })

    data = {"type": "status_grid", "title": "Dashboard", "cards": cards, "_home": True}
    image, taps, back, refresh_sec = renderers.render("status_grid", data)
    return _save_render("home", "status_grid", data, image, taps, back, refresh_sec)


def build_agents_overview() -> dict:
    """Full list of every registered agent — reachable from home's overflow tile,
    and useful on its own once you have more than a handful of agents."""
    cards_by_agent = store.get_home_cards()
    ordered = sorted(cards_by_agent.items(), key=lambda kv: kv[1]["slot"])
    rows = [
        {"left": agent_id, "right": c["updated_at"], "status": None}
        for agent_id, c in ordered
    ]
    data = {
        "type": "text_list", "title": "Agents", "back": "home",
        "header": f"{len(ordered)} agent(s) connected",
        "rows": rows,
    }
    image, taps, back, refresh_sec = renderers.render("text_list", data)
    return _save_render("system/agents", "text_list", data, image, taps, back, refresh_sec)


@mcp.tool()
def update_view(path: str, data: dict) -> dict:
    """Push structured data to a view path; the server renders it to PNG for the Kindle.

    `path` is namespaced by your agent, e.g. "sports/readiness" or "life/habits" —
    first push creates the view, later pushes overwrite it. `data` must include a
    `type` field naming one of the built-in view types (status_grid, metric_dashboard,
    text_list, chart_view, progress_view) plus that type's fields. `home` and the
    `system/` namespace are reserved — use push_home_card() to appear on the home grid.
    """
    path = path.strip("/")
    if not path:
        return {"success": False, "path": path, "image_url": None, "rendered_at": None,
                "error": "path must not be empty"}
    if path in RESERVED_PATHS or path.split("/")[0] in RESERVED_NAMESPACES:
        return {"success": False, "path": path, "image_url": None, "rendered_at": None,
                "error": f"'{path}' is reserved. Use push_home_card() for the home grid."}
    try:
        meta = render_and_save(path, data)
    except ValueError as exc:
        return {"success": False, "path": path, "image_url": None, "rendered_at": None, "error": str(exc)}
    return {"success": True, "path": path, "image_url": meta["image"],
            "rendered_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "error": None}


@mcp.tool()
def push_home_card(agent_id: str, title: str, summary: list[str], nav_target: str) -> dict:
    """Update your agent's card on the home grid (creates it on first call).

    Each `agent_id` gets one fixed slot, assigned in first-registration order and
    kept stable across restarts. `nav_target` is the view path opened when the card
    is tapped — normally a path you've already pushed via update_view().
    """
    card = store.upsert_home_card(agent_id.strip(), title, summary, nav_target)
    build_home_view()
    build_agents_overview()
    return {"success": True, "agent_id": agent_id, "slot": card["slot"], "home_rendered": True}


@mcp.tool()
def get_status() -> dict:
    """Server health: port, screen geometry, data dir, view/agent counts, uptime."""
    cards = store.get_home_cards()
    return {
        "port": config.HTTP_PORT,
        "data_dir": str(config.DATA_DIR),
        "screen": {"width": config.SCREEN_WIDTH, "height": config.SCREEN_HEIGHT},
        "views_count": store.registry_count(),
        "agents": sorted(cards.keys()),
        "home_max_cards": config.HOME_MAX_CARDS,
        "uptime_sec": round(time.time() - _START_TIME, 1),
    }


@mcp.tool()
def list_views() -> list:
    """All registered views with their type, title, owning agent, and last-updated time."""
    return store.list_views()
