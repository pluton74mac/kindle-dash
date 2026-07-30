# MCP Server Design — Kindle the agent Dashboard

> Condensed from the full architecture grill (D03, 2026-07-24). See project DECISIONS.md for the full decision record.

## Architecture

```
Sports Coach Agent    Life Coach Agent    System Agent
(cron 7am)           (cron 8am)          (cron every 5min)
     │                     │                   │
     │ update_view()       │ update_view()     │ update_view()
     │ push_home_card()    │ push_home_card()  │ push_home_card()
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
│    • Disk store: PNGs + view metadata           │
└──────────────────────┬───────────────────────────┘
                         │ HTTP (fetch on interaction)
                  ┌──────┴──────┐
                  │   Kindle     │  (dumb display: shell + C touch)
                  └─────────────┘
```

## Tool Surface

### `update_view(path, data)`
Push structured data → MCP renders PNG → saves to disk.
- `path`: namespaced by agent (`sports/readiness`, `life/habits`)
- `data`: `{type: "<view_type>", ...fields}`
- Returns: `{success, path, image_url, rendered_at}`

### `push_home_card(agent_id, title, summary, nav_target)`
Update the agent's designated card on the home grid.
- Each agent_id maps to a fixed slot position. No ordering.
- Triggers home view re-render (combines all current cards).

### `get_status()` / `list_views()`
Debugging/monitoring tools.

## View Types (Phase 1 — 5 generic types)

| Type | Use case | Key fields |
|------|----------|------------|
| `status_grid` | Home view (grid of agent cards) | `cards: [{agent_id, title, summary[], nav_target}]` |
| `metric_dashboard` | Readiness, scores (hero + factors) | `hero: {value, unit, label}`, `factors: [{name, percent, status}]`, `safety_gate` |
| `text_list` | Cron list, calendar, sessions | `header`, `rows: [{left, right, status}]` |
| `chart_view` | HRV trend, weight trend | `hero: {value, unit}`, `sparkline: {values[], baseline}`, `caption` |
| `progress_view` | Nutrition, macros | `bars: [{label, value, max}]`, `stacked_bar`, `items[]` |

Phase 2: agent-domain types (habit_tracker, mood_journal, etc.) added as agent data patterns are understood.

## Data Flow

1. Agent cron fires → agent fetches data → calls `update_view(path, {type, ...})`
2. MCP looks up renderer for type → calls Pillow → saves PNG to disk
3. Agent calls `push_home_card()` → MCP updates home grid
4. Agent disconnects (cron done)
5. User picks up Kindle → taps card → shell fetches `GET /view?path=sports/readiness`
6. MCP HTTP thread reads PNG from disk → serves JSON + PNG
7. Kindle displays via `eips -f -g`

**Key insight:** The PNG lives on disk. It doesn't matter if the agent is connected or the MCP subprocess is alive. The HTTP server serves whatever's on disk. Agents write to disk, Kindle reads from disk, HTTP server is the bridge.

## Lifecycle

- Stdio MCP server: the agent-managed subprocess, `idle_timeout_seconds: 0`
- HTTP server: background thread inside MCP process
- Disk persistence: PNGs + metadata survive process restarts
- Kindle offline cache: covers the agent restart gaps (shows last PNG, retries on next tap)
- Subprocess respawns on next tool call (cron push), so HTTP server is up when new data exists

## Design Decisions (with rationale)

| Decision | Why | Rejected alternative |
|----------|-----|----------------------|
| Typed view types | Agents are data pushers, not UI designers | Freeform text (can't do bars/charts), Layout DSL (over-engineered) |
| No polling | E-ink holds image; fetch on interaction is sufficient | Push signals (requires Kindle listener, breaks "dumb display") |
| Stdio MCP (not daemon) | Simpler, no launchd; disk persistence + Kindle cache cover gaps | Standalone HTTP daemon (more setup, unnecessary) |
| Builtin types only | Cronjobs are deterministic — no surprise data shapes | Custom renderers (violates agent/MCP boundary) |
| Fixed agent slots | No ordering conflicts, no priority system | Auto-generated home (less control), orchestrator agent (single point of failure) |

## the agent Config

```yaml
mcp_servers:
  kindle-dash:
    command: "python3"
    args: ["/path/to/server.py"]
    idle_timeout_seconds: 0
    tools:
      include: [update_view, push_home_card, get_status, list_views]
```

## Related
- `references/viewer-implementation-c-vs-shell.md` — Kindle viewer architecture (D01)
- `templates/view_server.py` — Spike server (single-agent, hardcoded views)
- Project docs: `ideas/kindle-the agent-dashboard/DECISIONS.md` (D02, D03), `llm_wiki/mcp-server-design.md` (full spec)
