# IDEA — Kindle the agent Dashboard

## Problem

the agent runs headless. Its outputs — daily briefings, cron job status, training readiness, workflow results — live in chat logs, terminal output, or cron job delivery messages. There's no passive, always-visible surface for glancing at what matters today.

the developer has a jailbroken Kindle. E-ink holds an image with zero power, is readable in any lighting, and the Kindle has WiFi + a touchscreen. It's the perfect low-power, zero-glare, always-on access point for the agent — if we can connect them.

## Audience

Single-user (the developer). This is a personal dashboard, not a product. But the architecture — a server-driven e-ink viewer that renders PNG + tap maps from any backend — is generalizable to anyone with a jailbroken Kindle and a data source.

## Revenue Angle

Not a product. However, the write-once Kindle viewer + the agent view server could be packaged as an open-source "Kindle dashboard kit" (similar to kdashboard but generic). Potential as a GitHub project / blog content.

## Architecture Hypothesis

### Core Principle: Kindle is a dumb display. the agent owns everything.

The Kindle runs a **shell script viewer** (curl + eips + jq) with a **tiny C touch helper** (50 lines, compiled once). Together they:
1. Fetches a PNG image + JSON tap map from a local HTTP server
2. Renders the PNG to the e-ink framebuffer (`/dev/fb0` or `eips -f`)
3. Listens for touch events
4. On tap → matches coordinates to a tap region → fetches the corresponding view
5. Auto-refreshes every 60 min while awake
6. Detects wake (power button) → immediate refresh
7. Sleeps naturally (Kindle screensaver) when idle

The **view server** runs on the Mac (Python, local HTTP):
- Aggregates data from the agent sources (daily briefing, cron jobs, data source MCP, calendar, workflows, session history)
- Renders views as PNG images using PIL/Pillow
- Returns JSON tap maps (regions → view paths) for navigation
- View tree is server-side — Kindle never needs code changes for new views

### Kindle Viewer Architecture (Decided: Hybrid Shell + C Touch Helper)

```
┌─────────────────────────────────────────┐
│          SHELL SCRIPT (main)             │
│  • curl fetches PNG + JSON tap map      │
│  • jq parses tap regions                 │
│  • eips -f -g displays PNG               │
│  • lipc-wait-event handles sleep/wake    │
│  • Auto-refresh every 60 min             │
│  • Error recovery (homecircuits pattern) │
│  • Offline cache (atomic .tmp → rename)  │
└──────────────┬──────────────────────────┘
               │ pipe: "x y\n" on tap
┌──────────────┴──────────────────────────┐
│     TOUCH HELPER (C, ~50 lines)         │
│  • EVIOCGRAB exclusive touch access      │
│  • Reads evdev /dev/input/event*         │
│  • Scales coords via EVIOCGABS           │
│  • 700ms debounce                        │
│  • Prints "x y\n" on tap release         │
└─────────────────────────────────────────┘
```

**Why hybrid (not full C):** Cross-compilation for every change kills iteration speed. Shell is instantly editable. The 50-line C helper is the only compiled code — it's so simple it never changes. Full analysis at `llm_wiki/viewer-implementation-c-vs-shell.md`.

### Protocol

```
GET /view?path=home
→ {
    "image": "/tmp/dash_home.png",
    "taps": [
      { "x": 0, "y": 400, "w": 400, "h": 200, "action": "calendar" },
      { "x": 400, "y": 400, "w": 400, "h": 200, "action": "cron" },
      ...
    ],
    "back": null,
    "refresh_sec": 3600
  }
```

### Data Sources (to be connected)

| Source | the agent Tool / MCP | What it provides |
|---|---|---|
| Daily Briefing | `get_daily_briefing` (data source MCP) or custom cron | Day summary, key metrics, bullet points |
| Cron Jobs | `cronjob action=list` | Job names, schedules, next run, last status |
| Coaching Dashboard | Data Source MCP (integrated tools) | Readiness, sleep, HRV, training plan, body composition |
| Calendar | Google Workspace skill or system calendar | Today's events, upcoming |
| Workflows | the agent delegate_task / session_search | Running tasks, triggered workflows, status |
| Session History | `session_search` | Recent sessions, what was worked on |

### View Tree (initial)

```
home (daily briefing + 4 nav buttons)
├── calendar/
│   ├── today
│   ├── week
│   └── month
├── cron/
│   ├── list (all jobs + status)
│   └── detail/<job_id>
├── coaching/
│   ├── readiness (HRV, sleep, body battery, RHR)
│   ├── training (today's plan, week summary)
│   ├── health (body composition, weight trend)
│   └── nutrition (daily log, macros)
└── workflows/
    ├── active (running tasks)
    ├── history (recent completed)
    └── trigger/<workflow_name>
```

### Kindle Lifecycle

```
SLEEP ──(power button)──▶ WAKE → fetch + render home
  ▲                           │
  │                           ├── tap → navigate (fetch new view)
  │                           ├── 60 min timer → auto-refresh current view
  │                           └── idle N min → SLEEP (screensaver)
  │
  └──(idle timeout)───────────┘
```

## Target Hardware

**Kindle Paperwhite 4 (10th Gen, 2018)**
- Screen: 6" Carta E-Ink, 300 PPI, **1448×1072 pixels**
- Touch: capacitive touchscreen
- WiFi: yes
- Jailbreak + KUAL: supported

## Why Us

- the developer already has a jailbroken Kindle with KUAL
- the agent has all the data sources (data source MCP, cron, sessions, workflows)
- The kdashboard repo proves the Kindle-side patterns work (framebuffer, touch, KUAL, lipc)
- We need to build the generic view server + write-once viewer — the hard Kindle work is already solved

## Key Insight from kdashboard

kdashboard hardcodes every view in C++. We invert this: the Kindle viewer is generic (PNG + tap map), and all view logic lives server-side. New screens = new Python functions, not new C++ compilations.
