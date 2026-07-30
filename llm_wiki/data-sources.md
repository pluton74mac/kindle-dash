# the agent Data Sources for Dashboard Views

> **Status:** Research + proposed mapping. Tool descriptions are from the the agent tool inventory (data source MCP, session_search, etc.). Data structuring is proposed design.

## Summary

Maps the the agent data sources available for Kindle dashboard views. Each source is documented with: what tool to call, what data it returns, and how to structure it for a dashboard view. The view server calls these tools and renders the results into PNG images via the [PNG rendering pipeline](png-rendering-pipeline.md).

## Data Source Overview

| Source | Tool / MCP | Key Tools | Refresh Frequency | View Paths |
|---|---|---|---|---|
| Data Source MCP | integrated tools | `get_daily_briefing`, `get_training_readiness`, `get_sleep_summary`, `get_hrv_data`, `get_body_composition`, `get_nutrition_daily_food_log` | 15-60 min | `coaching/*` |
| Cron Jobs | the agent `cronjob` | `action=list`, `action=status` | 5 min | `cron/*` |
| Session History | `session_search` | query, browse | 10 min | `sessions/*` |
| Workflow Status | `delegate_task` | workflow status, completion | 5 min | `workflows/*` |
| Google Workspace | Google Workspace skill | calendar events | 30 min | `calendar/*` |

---

## 1. Data Source MCP (Garmin Connect)

**Source:** `taxuspt/garmin_mcp` fork — [GitHub](https://github.com/taxuspt/garmin_mcp) (790 stars, 232 forks). Exposes 171 MCP tools connecting to Garmin Connect. This is the richest data source for the dashboard.

### Key Tools for Dashboard

#### Daily Briefing — `get_daily_briefing(date)`

**Returns:** Aggregated morning coaching brief: sleep, recovery (body battery, HRV, RHR), training readiness, today's scheduled workout, and alerts. Single call replaces 5+ individual tool calls.

**Dashboard structure:**
- Home view: 2-3 line summary (readiness score, sleep quality, today's workout)
- Coaching/readiness: full breakdown with sub-sections

**Sample call:** `get_daily_briefing(date="2026-07-16")`

> Note: In testing, this tool returned an error (`'list' object has no attribute 'get'`). This may require authentication or a valid Garmin session. The view server should handle this gracefully and show cached/partial data.

#### Training Readiness — `get_training_readiness(date)`

**Returns:** Training readiness score and contributing factors (sleep, recovery time, acute load, HRV status, sleep history, stress history).

**Dashboard structure:** Large readiness score (0-100), factor breakdown as a mini bar chart or bullet list, color-coded zones (green/yellow/red → grayscale: dark/medium/light).

**Composite version:** `get_training_readiness_composite(date)` — aggregates 6-factor readiness into a composite score with breakdown. Better for compact display.

#### Sleep — `get_sleep_summary(date)`

**Returns:** Compact sleep summary (~350 bytes): total sleep, deep/light/REM durations, sleep score, wake time.

**Dashboard structure:** Sleep score as a large number, sleep stages as a horizontal bar, bedtime/wake time as text.

#### HRV — `get_hrv_data(date)` / `get_hrv_trend(start_date, end_date)`

**Returns:** `get_hrv_data` — single-day HRV with optional 5-minute timeseries. `get_hrv_trend` — daily HRV values and weekly rolling averages over a range.

**Dashboard structure:** Current HRV (ms) as a big number, 7-day trend as a sparkline, baseline comparison indicator (above/below baseline).

#### Body Composition — `get_body_composition(start_date, end_date)`

**Returns:** Weight, body fat %, muscle mass, bone mass, BMI, hydration %, visceral fat, metabolic age, physique rating.

**Dashboard structure:** Weight as the hero number, body fat % and muscle mass as secondary, 7-day weight trend sparkline.

#### Nutrition — `get_nutrition_daily_food_log(date)` / `get_nutrition_daily_settings(date)`

**Returns:** Food items logged throughout the day with calories, macros, and meal associations. Settings: daily calorie/macro targets.

**Dashboard structure:** Calories consumed vs. target as a progress bar, macro breakdown (carbs/protein/fat) as a stacked bar, meal list with per-meal calorie counts.

#### Athlete Status Snapshot — `get_athlete_status_snapshot()`

**Returns:** Current HRV, body battery, RHR, readiness, and sleep metrics with baseline deviations. Includes a `safety_gate` field (green/yellow/red) that gates coaching recommendations.

**Dashboard structure:** Home view summary card — safety gate as a traffic-light icon (grayscale), key metrics in a compact 2-column layout.

#### Additional Data Source MCP Tools

| Category | Tools | Dashboard Use |
|---|---|---|
| Activities | `get_activities(limit)`, `get_activity(activity_id)`, `get_activities_by_date(start, end)` | Recent workouts list, weekly volume |
| Training Load | `get_training_load_trend(start, end)` | CTL/ATL/TSB chart, form indicator |
| Cycling Analytics | `get_activity_fit_data(activity_id)`, `get_power_duration_curve()` | Power zones, FTP estimate |
| Gear | `get_gear()` | Shoe/bike mileage, replacement alerts |
| Safety | `run_safety_check()`, `check_overtraining_risk()` | Safety gate indicator on home view |
| Recovery | `get_recovery_trend(days)`, `get_weekly_health_summary(end_date)` | Recovery trajectory, weekly averages |
| VO2 Max | `get_vo2max_trend(start, end)` | Fitness trend sparkline |
| Respiration | `get_respiration_summary(date)`, `get_respiration_trend(start, end)` | Overnight respiration, trend |
| Stress | `get_stress_summary(date)` | Daily stress average, peak stress time |
| Steps | `get_stats(date)`, `get_daily_steps(start, end)` | Step count, daily activity |

### Dashboard View Paths (Coaching)

```
coaching/
├── readiness    — readiness score, 6-factor breakdown, safety gate
├── sleep        — sleep summary, stages bar, score
├── hrv          — current HRV, 7-day trend, baseline deviation
├── training     — today's workout, weekly plan, CTL/ATL/TSB
├── health       — body composition, weight trend, metabolic age
└── nutrition    — calorie progress, macro breakdown, meal log
```

---

## 2. Cron Jobs

**Source:** the agent built-in cronjob management. The `cronjob` tool is available via the agent CLI.

### Tools

#### `cronjob action=list`

**Returns:** List of all configured cron jobs with: name, schedule (cron expression), next run time, last run time, last status (success/failure/running), and delivery method.

**Dashboard structure:**
```
┌─────────────────────────────────────────┐
│  Cron Jobs                    12 jobs   │
├─────────────────────────────────────────┤
│  ✅ morning-brief       08:00  OK       │
│  ✅ daily-report        18:00  OK       │
│  ⚠️  data-sync          02:00  FAILED    │
│  🔄 idea-lab-check     */30   RUNNING   │
│  ⏰ weekly-plan        Sun 09  PENDING  │
│  ...                                    │
├─────────────────────────────────────────┤
│  11 OK  ·  1 FAILED  ·  1 RUNNING       │
└─────────────────────────────────────────┘
```

In grayscale: use filled rectangles (■) for OK, hollow (□) for failed, crosshatch for running, dash for pending.

#### `cronjob action=status`

**Returns:** Current status of all jobs — which are running, last execution results, error messages.

### Dashboard View Paths

```
cron/
├── list          — all jobs with status indicators, tap to drill in
└── detail/<name> — full detail: schedule, last 5 runs, error logs, next run
```

---

## 3. Session History

**Source:** `session_search` — FTS5-backed retrieval over the local SQLite session database.

### Tools

#### `session_search()` (no args — browse shape)

**Returns:** Recent sessions chronologically: session_id, title, preview, timestamp.

**Dashboard structure:** List of recent 5-8 sessions with title and timestamp. Tap to expand (shows bookend summary).

#### `session_search(query="<keyword>")` (discovery shape)

**Returns:** Matching sessions with FTS5-highlighted snippets, bookend summaries, and message windows around matches.

**Dashboard structure:** Search results list — less useful for a passive dashboard but could show "recently worked on" topics.

### Dashboard View Paths

```
sessions/
├── recent        — last 8 sessions, title + timestamp + preview
└── detail/<id>   — session summary (bookend_start + bookend_end, key decisions)
```

**Note:** Session search is read-only against the the agent session DB. The view server should call this and format the response into a compact list. No PII filtering needed (single-user personal dashboard).

---

## 4. Workflow Status

**Source:** `delegate_task` / the agent workflow system. Autonomous AI agents can be spawned and their status tracked.

### Tools

The delegate_task tool spawns autonomous coding agents (Claude Code, Codex, OpenCode). The status of running and recently completed tasks can be queried.

#### Workflow Status Query

**Returns (expected):** List of active and recently completed delegated tasks with:
- Task name / description
- Status: running / completed / failed
- Start time, estimated completion
- Agent type (claude-code, codex, opencode)
- Result summary

### Dashboard View Paths

```
workflows/
├── active        — running tasks with live status, elapsed time
├── history       — last 10 completed tasks with results
└── trigger/<name> — trigger a new workflow (POST /toggle or /action)
```

**Dashboard structure:**
```
┌─────────────────────────────────────────┐
│  Active Workflows                       │
├─────────────────────────────────────────┤
│  🔄 PR #234 review   (claude-code)      │
│     12 min elapsed · in progress        │
│  🔄 Deploy staging   (codex)            │
│     3 min elapsed · in progress         │
├─────────────────────────────────────────┤
│  Recent Completions                     │
│  ✅ Test suite        15 min ago         │
│  ✅ Doc generation   1 hr ago           │
│  ❌ Migration script  2 hr ago (FAILED)  │
└─────────────────────────────────────────┘
```

---

## 5. Google Workspace (Calendar)

**Source:** Google Workspace skill in the agent. Provides Gmail, Calendar, Drive, Docs, Sheets via `gws` CLI or Python.

### Tools

#### Calendar Events

**Returns:** Today's events, upcoming events this week. Each event has: title, start time, end time, location, attendees.

**Dashboard structure:**
```
┌─────────────────────────────────────────┐
│  Wednesday, Jul 16                      │
├─────────────────────────────────────────┤
│  09:00  Team standup          30 min   │
│  11:00  1:1 with Sarah        45 min   │
│  14:00  Architecture review    1 hr    │
│  16:30  Dentist                30 min  │
├─────────────────────────────────────────┤
│  Tomorrow                               │
│  10:00  Sprint planning        1.5 hr   │
│  15:00  Demo prep              1 hr    │
└─────────────────────────────────────────┘
```

### Dashboard View Paths

```
calendar/
├── today   — today's schedule, timeline view
├── week    — 7-day agenda
└── month   — month grid with event density indicators
```

---

## Data Aggregation Patterns

### Home View (Composite)

The home view aggregates from multiple sources in a single render:

```
┌─────────────────────────────────────────┐
│  Wed Jul 16  ·  08:12                   │
├──────────────────────┬──────────────────┤
│  READINESS           │  CALENDAR        │
│  72  ●●●○○           │  4 events today  │
│  Sleep 7h12m  Good   │  Next: 11:00 1:1 │
├──────────────────────┼──────────────────┤
│  CRON                │  WORKFLOWS       │
│  11 OK · 1 FAIL      │  2 active        │
│  ⚠ data-sync failed  │  ✅ Test suite   │
├──────────────────────┴──────────────────┤
│  "Small steps every day..."            │
├─────────────────────────────────────────┤
│  Last sync 08:12  ·  Batt 85%          │
└─────────────────────────────────────────┘
```

### Render Flow

```python
def render_home_view():
    # Fetch from multiple sources (parallel where possible)
    status = get_athlete_status_snapshot()  # or get_daily_briefing
    cron = cronjob_list()
    calendar = gws_calendar_today()
    workflows = get_active_workflows()

    # Render to PNG
    image = render_dashboard_png(
        title=f"{date_str} · {time_str}",
        sections=[
            ("readiness", status, navigate_to="coaching/readiness"),
            ("calendar", calendar, navigate_to="calendar/today"),
            ("cron", cron, navigate_to="cron/list"),
            ("workflows", workflows, navigate_to="workflows/active"),
        ]
    )

    # Build tap map
    taps = [
        TapRegion(x=0, y=120, w=536, h=340, action="navigate", target="coaching/readiness"),
        TapRegion(x=536, y=120, w=536, h=340, action="navigate", target="calendar/today"),
        # ...
    ]

    return ViewResponse(image=image, taps=taps, refresh_sec=3600)
```

### Error Handling

Each data source should be fetched independently with try/except. If one source fails, the view renders with that section showing "unavailable" and the `error` field set to a non-fatal warning. See [view-protocol-spec.md](view-protocol-spec.md) for the error response schema.

---

## Related Files

- [view-protocol-spec.md](view-protocol-spec.md) — How the viewer fetches and renders views
- [png-rendering-pipeline.md](png-rendering-pipeline.md) — How data is rendered to PNG
- [IDEA.md](../IDEA.md) — Original architecture and data source plan
