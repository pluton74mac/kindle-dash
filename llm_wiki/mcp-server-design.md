# MCP Server Design — Kindle the agent Dashboard

> **Status:** Design spec (grilled + crystallized 2026-07-24). Based on D03 in [DECISIONS.md](../DECISIONS.md). Implements the architecture from [IDEA.md](../IDEA.md) and extends the [view protocol spec](view-protocol-spec.md).

## Summary

The Kindle Dashboard MCP Server is a stdio MCP server that acts as the bridge between the agent agents and the Kindle e-ink display. Agents push structured data via MCP tools; the server renders PNGs using builtin view type renderers (Pillow), serves them over HTTP to the Kindle, and manages the view tree. The dashboard operates as an "agent newspaper" — each agent has a designated section.

## Architecture

```
Sports Coach Agent    Life Coach Agent    System Agent
(cron 7am)           (cron 8am)          (cron every 5min)
     │                     │                   │
     │ push_home_card()    │ push_home_card()  │ push_home_card()
     │ update_view()       │ update_view()     │ update_view()
     ▼                     ▼                   ▼
┌──────────────────────────────────────────────────┐
│           Kindle Dashboard MCP Server             │
│  (stdio subprocess, managed by the agent)           │
│                                                   │
│  MCP Tools (stdin/stdout):                       │
│    • update_view(path, data)                     │
│    • push_home_card(agent_id, ...)               │
│    • get_status()                                │
│    • list_views()                                │
│                                                   │
│  Internal:                                        │
│    • View type renderers (Pillow)                │
│    • HTTP server (background thread, :8888)     │
│    • View registry (in-memory + disk)           │
│    • Disk store: PNGs + view metadata           │
└──────────────────────┬───────────────────────────┘
                         │ HTTP (fetch on interaction)
                  ┌──────┴──────┐
                  │   Kindle     │  (dumb display: shell + C touch)
                  └─────────────┘
```

## Tool Surface

### 1. `update_view(path, data)`

Push structured data to a view path. The MCP renders a PNG using the builtin renderer for the view type, saves it to disk, and stores view metadata.

**Parameters:**

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `path` | string | Yes | View path, namespaced by agent: `sports/readiness`, `life/habits`, `system/cron` |
| `data` | object | Yes | View data including `type` field + type-specific fields (see View Types) |

**Returns:**

```json
{
  "success": true,
  "path": "sports/readiness",
  "image_url": "/images/sports_readiness.png",
  "rendered_at": "2026-07-24T07:00:00Z"
}
```

**Behavior:**
- First push to a path: creates the view, renders PNG, saves to disk
- Subsequent pushes: overwrites the PNG and metadata on disk
- The Kindle fetches this PNG on next interaction (tap, refresh, wake)
- If the MCP subprocess has died, the tool call respawns it (the agent stdio behavior)

### 2. `push_home_card(agent_id, title, summary, nav_target)`

Update the agent's designated card on the home view. The home view is a fixed grid of agent slots, rendered as a `status_grid`.

**Parameters:**

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `agent_id` | string | Yes | Agent namespace: `sports`, `life`, `system`, etc. Determines card slot. |
| `title` | string | Yes | Card title (e.g. "Training Readiness") |
| `summary` | string[] | Yes | 1-3 lines of summary text for the card |
| `nav_target` | string | Yes | View path to navigate to when card is tapped (e.g. `sports/readiness`) |

**Returns:**

```json
{
  "success": true,
  "agent_id": "sports",
  "home_rendered": true
}
```

**Behavior:**
- Each agent_id maps to a fixed slot position on the home grid
- If an agent hasn't pushed a card, its slot shows "No data" or is omitted
- Pushing a card triggers a home view re-render (combines all current cards)

### 3. `get_status()`

Return dashboard server status — useful for debugging and monitoring.

**Returns:**

```json
{
  "port": 8888,
  "kindle_last_seen": "2026-07-24T10:15:00Z",
  "views_count": 8,
  "agents": [
    {"id": "sports", "last_push": "2026-07-24T07:00:00Z", "views": 6},
    {"id": "system", "last_push": "2026-07-24T10:10:00Z", "views": 2}
  ],
  "uptime_sec": 14523
}
```

### 4. `list_views()`

List all registered views with metadata.

**Returns:**

```json
[
  {
    "path": "sports/readiness",
    "type": "metric_dashboard",
    "title": "Training Readiness",
    "agent_id": "sports",
    "updated_at": "2026-07-24T07:00:00Z"
  },
  {
    "path": "system/cron",
    "type": "text_list",
    "title": "Cron Jobs",
    "agent_id": "system",
    "updated_at": "2026-07-24T10:10:00Z"
  }
]
```

## HTTP Endpoints (Kindle-Facing)

These are internal HTTP endpoints served by the background thread, not MCP tools. The Kindle viewer (shell script) fetches from these.

### `GET /view?path=<path>`

Returns the view protocol JSON (see [view-protocol-spec.md](view-protocol-spec.md)). Contains the image reference, tap map, back path, and metadata.

**Response:** Same schema as the spike — `{version, title, image, taps, back, refresh_sec, error, cache}`

### `GET /images/<name>.png`

Returns PNG bytes. The Kindle fetches this after getting the image path from the `/view` response.

### `GET /health`

Returns `{"ok": true, "port": 8888}`. Used for health checks.

## View Types (Phase 1 — Generic)

Each view type has a builtin renderer. Agents pick a type and pass matching structured data.

### 1. `status_grid` — Home view

Grid of N×M cards, each with a title + summary lines + nav tap to a sub-view.

```json
{
  "type": "status_grid",
  "title": "the agent Dashboard",
  "cards": [
    {
      "agent_id": "sports",
      "title": "Training Readiness",
      "summary": ["Readiness: 74/100", "HRV: 92ms (declining)", "⚠️ Body Battery: 18"],
      "nav_target": "sports/readiness"
    },
    {
      "agent_id": "system",
      "title": "Cron Jobs",
      "summary": ["11 OK · 1 FAILED", "⚠️ data-sync failed"],
      "nav_target": "system/cron"
    }
  ]
}
```

**Note:** The home view is auto-generated from `push_home_card` calls. Agents don't call `update_view("home", ...)` directly — the MCP composes it from registered cards.

### 2. `metric_dashboard` — Readiness, scores

Hero number + optional factor bars + optional status gate icon.

```json
{
  "type": "metric_dashboard",
  "title": "Training Readiness",
  "hero": {
    "value": 74,
    "unit": "/100",
    "label": "Moderate"
  },
  "factors": [
    {"name": "Sleep", "percent": 80, "status": "good"},
    {"name": "HRV", "percent": 90, "status": "good"},
    {"name": "Stress", "percent": 67, "status": "caution"},
    {"name": "Load", "percent": 100, "status": "good"}
  ],
  "safety_gate": "yellow",
  "footer": "Light/recovery or rest. HRV declining."
}
```

### 3. `text_list` — Cron list, session history, calendar

Title + header + list of rows (left text, right text, optional status indicator).

```json
{
  "type": "text_list",
  "title": "Cron Jobs",
  "header": "12 jobs · 11 OK · 1 FAILED",
  "rows": [
    {"left": "morning-brief", "right": "08:00 daily", "status": "ok"},
    {"left": "data-sync", "right": "every 5min", "status": "failed"},
    {"left": "weekly-plan", "right": "Sun 09:00", "status": "pending"}
  ]
}
```

**Status values:** `ok`, `failed`, `running`, `pending` — rendered as grayscale symbols (■ for ok, ✕ for failed, ◐ for running, ○ for pending).

### 4. `chart_view` — HRV trend, weight trend, training load

Title + hero value + sparkline + optional baseline marker + caption.

```json
{
  "type": "chart_view",
  "title": "HRV Trend",
  "hero": {
    "value": 92,
    "unit": "ms",
    "label": "Balanced"
  },
  "sparkline": {
    "values": [45, 48, 42, 50, 47, 52, 49, 92],
    "baseline": 55,
    "label": "7-day"
  },
  "caption": "⚠️ Declining (-53.8% from baseline)"
}
```

### 5. `progress_view` — Nutrition, macros

Title + progress bars + optional stacked bar + optional itemized list.

```json
{
  "type": "progress_view",
  "title": "Nutrition",
  "bars": [
    {"label": "Calories", "value": 1450, "max": 2000, "unit": "kcal"},
    {"label": "Protein", "value": 85, "max": 140, "unit": "g"}
  ],
  "stacked_bar": {
    "label": "Macros",
    "segments": [
      {"label": "Carbs", "value": 180, "unit": "g"},
      {"label": "Protein", "value": 85, "unit": "g"},
      {"label": "Fat", "value": 55, "unit": "g"}
    ]
  },
  "items": [
    {"name": "Breakfast", "value": "420 kcal"},
    {"name": "Lunch", "value": "680 kcal"}
  ]
}
```

## View Types (Phase 2 — Agent-Domain)

To be designed as agent data patterns are understood. The dashboard = "agent newspaper" — each agent gets purpose-built renderers tailored to its data.

**Potential future types:**
- `habit_tracker` — checkmark grid, streak counters (life coach)
- `mood_journal` — mood scale, journal entries (life coach)
- `training_calendar` — weekly training plan with workout blocks (sports coach)
- `session_browser` — the agent session history with previews (system)

New types are added as code changes to the MCP, not as agent-supplied renderers.

## Data Flow

### Agent pushes data (cron-triggered)

```
1. Agent cron fires (e.g. sports coach at 7am)
2. Agent fetches data from source (Garmin, session DB, etc.)
3. Agent calls update_view("sports/readiness", {type: "metric_dashboard", ...})
4. MCP receives tool call via stdin/stdout
5. MCP looks up renderer for "metric_dashboard"
6. MCP calls Pillow to render 1072×1448 grayscale PNG
7. MCP saves PNG to disk: /tmp/kindle-dash/sports_readiness.png
8. MCP saves view metadata: /tmp/kindle-dash/sports_readiness.json
9. MCP returns {success: true, ...} to agent
10. Agent disconnects (cron job done)
```

### Kindle fetches view (user-triggered)

```
1. User picks up Kindle, wakes it (power button)
2. Kindle viewer fetches: curl http://<mac-ip>:8888/view?path=home
3. MCP HTTP server (background thread) handles request
4. Server reads home view metadata from disk, composes response JSON
5. Kindle receives JSON: {image: "/images/home.png", taps: [...], ...}
6. Kindle fetches PNG: curl http://<mac-ip>:8888/images/home.png
7. Kindle displays: eips -f -g /tmp/dash_cache/home.png
8. User taps a card → fetches that view (repeat from step 2 with new path)
```

### State persistence

```
Disk layout:
/tmp/kindle-dash/
├── home.png                    # Home view PNG (auto-generated from cards)
├── home.json                   # Home view metadata + tap map
├── sports_readiness.png        # Agent view PNGs
├── sports_readiness.json
├── system_cron.png
├── system_cron.json
├── agents.json                 # Agent registry (agent_id → card content + slot)
└── view_index.json             # View index (path → type, title, updated_at)
```

All state is on disk. If the MCP subprocess dies and respawns, it reads from disk to restore state. The HTTP server can serve views immediately after respawn.

## the agent MCP Configuration

```yaml
# ~/.the agent/config.yaml
mcp_servers:
  kindle-dash:
    command: "python3"
    args: ["$HOME/Documents/kindle-dash/server.py"]
    idle_timeout_seconds: 0   # keep alive indefinitely
    tools:
      include: [update_view, push_home_card, get_status, list_views]
```

The server Python script starts both the MCP stdio handler (main thread) and the HTTP server (background thread) on import.

## Cron Integration

Each agent's cron job is a self-contained prompt that:
1. Fetches data from the appropriate source (Garmin MCP, session_search, etc.)
2. Structures the data as a view type
3. Calls `update_view(path, data)` and `push_home_card(agent_id, ...)`

**Example cron job (sports coach daily briefing):**

```yaml
# Cron job config
schedule: "0 7 * * *"
prompt: |
  Fetch today's training readiness from the data source MCP.
  Push a home card with the readiness summary.
  Push a detailed readiness view with hero score, factors, and safety gate.
  Use update_view("sports/readiness", {type: "metric_dashboard", ...}).
  Use push_home_card("sports", "Training Readiness", [...], "sports/readiness").
```

## Kindle Viewer Integration

The Kindle viewer (shell script + C touch helper) is unchanged from the spike. It fetches from the MCP's HTTP server on interaction:

- **Wake** → fetch home view
- **Tap nav button** → fetch target view
- **Tap refresh** → re-fetch current view
- **Idle** → hold last image (e-ink, no polling)

The viewer's offline cache (already in the spike) handles server downtime gracefully — shows last cached PNG, retries on next tap.

## Related Files

- [DECISIONS.md](../DECISIONS.md) — D02 (MCP server decision), D03 (this design)
- [view-protocol-spec.md](view-protocol-spec.md) — JSON protocol between Kindle and view server
- [the agent-data-sources.md](the agent-data-sources.md) — What data feeds into each view
- [png-rendering-pipeline.md](png-rendering-pipeline.md) — How PNGs are rendered with Pillow
- [IDEA.md](../IDEA.md) — Original architecture and hardware specs
- [../spike/view_server.py](../spike/view_server.py) — Working spike (5 hardcoded views)
