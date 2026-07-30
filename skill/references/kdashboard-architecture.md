# kdashboard Architecture Reference

Deep breakdown of `thecodedose/kdashboard` (github.com/thecodedose/kdashboard) — the best open-source reference for a native Kindle e-ink dashboard. Extracted from session research on 2026-07-16.

## Overview

- **Stars:** 107 | **Forks:** 11 | **Commits:** 3
- **Languages:** C++ 49.9%, TypeScript 28.8%, Swift 7.4%, JavaScript 6.1%, Shell 5.5%, Makefile 2.3%
- **Backend:** InsForge (open-source BaaS — Postgres + edge functions + auth + storage)
- **Inputs:** Telegram bot + iOS HealthKit companion app
- **Last updated:** July 2026

## Architecture Diagram

```
Kindle (e-ink)  ←── HTTP GET + SSE ──  InsForge Backend  ←── Telegram bot
  C++ renderer                              Postgres           iOS HealthKit
  /dev/fb0                                  Edge functions
  Touch regions
```

## Backend Spine

InsForge edge functions (TypeScript/Deno):

| Function | Purpose |
|---|---|
| `kindle-dashboard-data.ts` | Builds compact JSON payload, hashes visible state into version |
| `kindle-dashboard-events.ts` | SSE stream — polls DB every 2s, emits version changes |
| `kindle-dashboard-toggle.ts` | POST — toggle planner items done/undone |
| `telegram-webhook.ts` | Parse Telegram messages → DB writes (AI or deterministic parser) |
| `health-sync.ts` | iOS HealthKit daily aggregates upload |

Postgres tables: `planner_items`, `health_daily_summaries`, `health_targets`, `challenge_daily_logs`, `recipes`, `recipe_ingredients`, `meal_plan_entries`.

## Change Detection Pattern

1. Backend computes a hash of the visible dashboard state (FNV-1a hash)
2. Same data = same version hash. Changed data = new hash.
3. SSE endpoint polls DB every 2 seconds, compares version
4. If version changed → emits SSE event with just the version string (not the payload)
5. Kindle sees new version → re-fetches full JSON payload

```typescript
const version = hashText(JSON.stringify({
  health: payload.health,
  challenge: payload.challenge,
  lists: payload.lists,
  meal_plan: payload.meal_plan,
  recipes: payload.recipes
}));
```

This is elegant — the SSE channel is tiny (just a hash), and the Kindle only does a full fetch when something actually changed.

## Native C++ Renderer

File: `kindle/native/src/kindle_dashboard.cpp` (~125K chars)

### Key constants
- `kScreenColumns = 40`, `kMaxRows = 28`
- `kMaxLists = 4`, `kMaxItems = 16`, `kMaxRecipes = 12`
- `kBitmapFallbackWidth = 760`, `kBitmapFallbackHeight = 1024`
- `kKindleStatusBarHeight = 66`
- `kMaxDashboardPayloadBytes = 512 * 1024`

### Data flow
1. Fetch JSON from backend → save to cache file (`/mnt/us/documents/kindle-dashboard-data.json`)
2. Parse JSON with hand-rolled parser (no JSON library — `findKeyInRange`, `extractString`, `extractInt`, `extractBool`, `matchingClose` for nested objects/arrays)
3. Parse into `Dashboard` struct (fixed arrays, fixed field sizes)
4. Render to canvas (text, boxes, progress bars, PGM images)
5. Write canvas to `/dev/fb0` via mmap, or fallback to `eips`

### Framebuffer write
```cpp
int fd = open("/dev/fb0", O_RDWR);
unsigned char* fb = static_cast<unsigned char*>(
  mmap(0, screensize, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0)
);
```

### Touch system
- No button framework. Touch is manual: tap coordinates → rectangle → action.
- Each tappable area is a `TouchRegion` struct with rect + action type + indices.
- Max 32 touch regions (`kMaxTouchRegions`).
- Touch actions: exit, back, open list, toggle item, open meal planner, open recipe, open recipes, home, open challenge, next/previous day, today.
- Touch input read from input device, watcher runs in separate thread.

### Views
- Home: health stats + planner lists + challenge progress
- Meal planner: today's meals with recipe details
- Recipe library: browse saved recipes
- Recipe detail: ingredients, instructions, macros
- Challenge: 75-day challenge tracker

### Offline cache
- Always renders from local cache file
- Fetch updates the cache
- Network down = still renders from last good cache
- Optimistic updates: toggle item locally in cache, then POST to backend

### Sleep control
- `DASHBOARD_KEEP_AWAKE=1` → `lipc-set-prop com.lab126.powerd preventScreenSaver 1`
- Optional sleep window: `DASHBOARD_SLEEP_WINDOW="23:00-07:00"` (render "quiet hours" screen)
- Manual refresh via KUAL menu

## KUAL Packaging

```
kindle/kual/kindle-dashboard/
├── config.sh.example    # URLs, tokens, interval, sleep window, invert
├── bin/dashboard.sh     # Launcher script
├── assets/              # PGM images (covers, placeholders, recipe photos)
└── ...
```

Config (`config.sh`):
```sh
DASHBOARD_DATA_URL="https://your-project.insforge.app/functions/kindle-dashboard-data"
DASHBOARD_EVENTS_URL="https://your-project.function2.insforge.app/kindle-dashboard-events"
DASHBOARD_TOGGLE_URL="https://your-project.insforge.app/functions/kindle-dashboard-toggle"
DASHBOARD_READ_TOKEN="..."
DASHBOARD_TOGGLE_TOKEN="..."
INTERVAL="3600"
DASHBOARD_KEEP_AWAKE="1"
DASHBOARD_SLEEP_WINDOW="off"
INVERT_IMAGES="0"
```

Build:
- `make -C kindle/native extension-zig ZIG=/path/to/zig` (soft-float ARM)
- `make -C kindle/native extension` (with `arm-linux-gnueabi-g++`)
- Output: `kindle/native/build/kindle-dashboard-kual.tar.gz`

Install:
```sh
tar -C /mnt/us/extensions -xzf kindle-dashboard-kual.tar.gz
cd /mnt/us/extensions/kindle-dashboard
cp config.sh.example config.sh  # then edit
```

## Auth Model

- `DASHBOARD_READ_TOKEN` — for GET (data + events endpoints)
- `DASHBOARD_TOGGLE_TOKEN` — for POST (toggle items)
- Token sent via `X-Dashboard-Read-Token` header, Bearer auth, or `?read_token=` query param
- Kindle never stores the InsForge admin API key
- Single-owner by design (no multi-user scoping)

## Why It Doesn't Fit Our Use Case Directly

The C++ renderer is **hardcoded** to specific views (planner lists, health, challenge, recipes, meal planner). Every new view requires:
1. New C++ struct fields
2. New JSON parsing code
3. New canvas rendering code
4. New touch regions
5. Cross-compilation for ARM
6. Repackaging the KUAL extension
7. Reinstalling on Kindle

For a the agent dashboard with evolving views (daily briefing, cron jobs, coaching, workflows, calendar), this iteration loop is too slow. The "dumb display" architecture (server generates PNG + tap map, Kindle is a generic viewer) is the better fit.
