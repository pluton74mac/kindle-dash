# kindle-dash-mcp

An MCP server that turns a jailbroken Kindle into a shared e-ink dashboard for AI
agents. Point any number of MCP-capable agents at it — each one pushes structured
data (`update_view`) and gets a designated card on the home screen
(`push_home_card`); the server renders everything to PNG + tap maps with Pillow.
The Kindle itself stays a dumb display (see the parent repo's
[`spike/`](../spike/) for the shell + C viewer this serves).

This implements the design in the parent project's `DECISIONS.md` (D02, D03) —
read that first if you want the "why," this README is the "how."

## Install

Requires Python 3.11+. Uses [uv](https://docs.astral.sh/uv/) for dependency
management.

```sh
cd mcp_server
uv sync
```

## Configuration

Everything is an environment variable, all optional:

| Variable | Default | Meaning |
|---|---|---|
| `KINDLE_DASH_WIDTH` | `1072` | Screen width in px (default matches Kindle Paperwhite 4) |
| `KINDLE_DASH_HEIGHT` | `1448` | Screen height in px |
| `KINDLE_DASH_PORT` | `8888` | HTTP port the Kindle's viewer fetches from |
| `KINDLE_DASH_HOST` | `0.0.0.0` | HTTP bind address |
| `KINDLE_DASH_DATA_DIR` | `~/.kindle-dash/data` | Where rendered PNGs + view metadata are persisted |
| `KINDLE_DASH_HOME_MAX_CARDS` | `8` | Cards shown directly on the home grid before collapsing extras into a "+N more" tile |

If your Kindle isn't a Paperwhite 4, set `KINDLE_DASH_WIDTH`/`HEIGHT` to its panel
resolution — nothing else in the server assumes PW4 hardware.

## Running

```sh
uv run kindle-dash-mcp
```

This starts the HTTP server (background thread) and the MCP stdio server
(foreground, blocks). In practice you won't run it directly — your agent
framework spawns it as a subprocess when it needs a tool call served. Point your
Kindle's KUAL extension (`spike/kindle-dash/menu.json` in the parent repo) at
`http://<this-machine>:8888`.

### Connecting an agent

Any MCP client that can spawn a stdio server works. Generic config shape:

```json
{
  "mcpServers": {
    "kindle-dash": {
      "command": "uv",
      "args": ["run", "--directory", "/absolute/path/to/mcp_server", "kindle-dash-mcp"]
    }
  }
}
```

Set `KINDLE_DASH_DATA_DIR` (and the other env vars above) in that config's `env`
block if you're not using the defaults — every agent pointed at the same data dir
+ port shares one dashboard.

## Tool surface

| Tool | Purpose |
|---|---|
| `update_view(path, data)` | Push data to a view. `path` is namespaced by your agent (e.g. `sports/readiness`, `garden/moisture`) — first call creates it, later calls overwrite. `data` must include `type` (one of the 5 below) plus that type's fields. |
| `push_home_card(agent_id, title, summary, nav_target)` | Give your agent a card on the home grid. Each `agent_id` keeps a stable slot, assigned in first-registration order. |
| `get_status()` | Port, screen size, data dir, view/agent counts, uptime. |
| `list_views()` | Every registered view: path, type, title, owning agent, last updated. |

`home` and the `system/` path prefix are reserved — `home` is built only from
`push_home_card()` calls, and `system/agents` is auto-generated (an overview of
every connected agent, linked from home's overflow tile once you have more than
`KINDLE_DASH_HOME_MAX_CARDS` agents).

## View types

Grayscale only — e-ink has no color, so "status" fields (`good`/`warning`/`bad`,
etc.) are drawn as fill darkness + text labels, not hue.

**`status_grid`** — a grid of navigable cards.
```json
{"type": "status_grid", "title": "...", "cards": [
  {"title": "...", "summary": ["line 1", "line 2"], "nav_target": "agent/some/path"}
]}
```

**`metric_dashboard`** — hero number + factor bars + optional safety gate.
```json
{"type": "metric_dashboard", "title": "Readiness",
 "hero": {"value": "74", "unit": "/100", "label": "Readiness"},
 "factors": [{"name": "HRV", "percent": 90, "status": "good"}],
 "safety_gate": {"ok": false, "message": "Do not train — HRV crashed"}}
```

**`text_list`** — header + rows with a left/right column and a status marker.
```json
{"type": "text_list", "title": "Cron Jobs", "header": "4 jobs",
 "rows": [{"left": "backup-check 3am", "right": "FAILED", "status": "bad"}]}
```

**`chart_view`** — hero value + sparkline + optional baseline + caption.
```json
{"type": "chart_view", "title": "HRV Trend", "hero": {"value": "92", "unit": "ms"},
 "sparkline": {"values": [88, 95, 101, 97, 90], "baseline": 95},
 "caption": "7-day trend, declining from baseline"}
```

**`progress_view`** — bars + optional stacked bar + a bullet list.
```json
{"type": "progress_view", "title": "Nutrition",
 "bars": [{"label": "Protein", "value": 120, "max": 160}],
 "stacked_bar": {"segments": [{"label": "Protein", "value": 480}, {"label": "Carbs", "value": 900}], "max": 2400},
 "items": ["Logged: breakfast, lunch", "Missing: dinner"]}
```

`status` values across all types map to fill darkness: `good`/`ok`/`normal` ->
light, `warning`/`caution` -> mid gray, `bad`/`low`/`critical`/`error` -> dark/black.
Every non-home view auto-gets a Back button (target: whatever `data["back"]`
says, default `"home"`) and an Exit button — you don't draw those yourself.

There is no custom-renderer escape hatch (DECISIONS.md D03) — if you need a 6th
view type, add a renderer function to `renderers.py` and register it in
`RENDERERS`, the same way the built-in 5 are defined.

## Why these design choices

See the parent repo's `DECISIONS.md` D02/D03 for the full rationale (rejected
alternatives included). Short version: no polling (the Kindle fetches only on
tap/wake, e-ink holds the image when idle), disk is the source of truth (the
HTTP server just serves whatever's on disk, so it doesn't matter whether an
agent or even the MCP subprocess is currently running), and typed view types
instead of a layout DSL (agents pick a type and hand over data, they never touch
Pillow or tap-map geometry).
