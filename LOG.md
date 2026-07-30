# Chronicle — Kindle the agent Dashboard

## 2026-07-16 — Session: Idea crystallization + folder creation

- **Discussed:** Kindle e-ink dashboard as access point for the agent. Explored kdashboard repo (thecodedose/kdashboard). Grilled the experience: what to see, how to interact, where it lives, refresh cadence, data sources, navigation model.
- **Decisions:**
  - Architecture: the agent generates PNG + JSON tap map, Kindle runs a write-once viewer (C or Python). Kindle is a dumb display — all view logic server-side.
  - Interaction: Tap to navigate tree of views. Read-only + minimal input. No other device needed.
  - Lifecycle: Kindle sleeps naturally (screensaver). Power button wakes → immediate fetch + render. Auto-refresh every 60 min while awake. Goes back to sleep after idle.
  - Home screen: Daily briefing card + 4 nav buttons (Calendar, Cron Jobs, Coaching Dashboard, Workflows). Each leads to a tree of sub-screens.
  - Specific per-view designs deferred — build the structure first, fill in screens later.
- **Findings:** kdashboard repo analyzed in depth:
  - C++ renderer hardcoded to specific views (planner lists, health, recipes, meal plan)
  - SSE change detection (hash visible state → version string → push version only)
  - Touch via tap coordinates → registered rectangles → actions
  - Stay-awake mode via `lipc-set-prop com.lab126.powerd preventScreenSaver 1`
  - Framebuffer write via mmap to `/dev/fb0`
  - KUAL extension packaging with `config.sh` for user config
- **Next steps:**
  - Research Kindle dev community for: wake-on-power-button detection via lipc, touch event reading in Python vs C, eips vs framebuffer rendering tradeoffs
  - Spike: minimal Python view server serving a static PNG + tap map + Kindle shell script fetching and displaying it
  - Design the view tree structure (JSON schema for view definitions)
  - Research Kindle model variations (which Kindle does the developer have? screen resolution, touch capability)
## 2026-07-16 — Research: Wiki populated (3 subagents, 12 files, ~148KB)

- **Findings:** 3 parallel subagents completed a full research pass:
  - **Kindle platform** (4 files): PW4 specs confirmed (1448×1072, 300 PPI, capacitive touch), framebuffer rendering via `/dev/fb0` mmap + `eips`, KUAL extension structure, power management (lipc preventScreenSaver, wake detection, RTC alarms)
  - **Touch + networking** (4 files): evdev touch events from `/dev/input/event*`, coordinate scaling, Python availability on Kindle (limited — KUAL Python extension, no PIL), curl + LAN access confirmed, WiFi power management
  - **Server + protocol** (4 files): View protocol spec (GET /view → PNG + tap map JSON), the agent data source mapping (data source MCP, cron, sessions, calendar), PNG rendering pipeline (PIL/Pillow on Mac), similar project survey
- **Key insights:**
  - Kindle Python is limited (no PIL/Pillow) — viewer should be C or minimal Python + eips
  - `eips -f` does full refresh (anti-ghosting), `eips -g` does partial (faster but ghosting)
  - Touch via evdev: `struct input_event` from `/dev/input/event*`, coordinates need scaling
  - Wake detection: `lipc-wait-event com.lab126.powerd outOfScreenSaver` or RTC alarm
  - Daemon processes survive screensaver — can detect wake and re-render
  - Protocol spec defined: GET /view?path=X → {image, taps[], back, refresh_sec, title}
## 2026-07-16 — Spike: End-to-end proof of concept WORKING

- **Discussed:** N/A (build session)
- **Decisions:**
  - Exit action implemented: `lipc-set-prop com.lab126.appmgrd start app://com.lab126.booklet.home` returns to Kindle home cleanly (no white screen)
  - Exit button added to home view (bottom-right corner) and all sub-views (next to back button)
  - `action: "exit"` is a first-class action type in the view protocol — viewer cleans up touch helper, restores screensaver, relaunches Kindle home
- **Findings:**
  - **Display pipeline PROVEN:** Python server renders PNG (Pillow, 1072×1448 grayscale) → curl fetches over WiFi → `eips -f -g` displays on e-ink. Full round-trip ~1-2s.
  - **Touch pipeline PROVEN:** 50-line C touch helper (`touch_tap.c`) cross-compiled with Zig (`arm-linux-musleabi`, static) → EVIOCGRAB exclusive touch → reads evdev `/dev/input/event2` → prints "x y\n" on tap → shell script reads via FIFO → awk parses JSON tap map → hit test → navigate. Works.
  - **PW4 touch reports x:0-0 y:0-0 via EVIOCGABS** — the driver reports raw pixel coordinates directly (not a hardware range like 0-4095). Fixed scale() to clamp raw values to screen bounds when min=max=0.
  - **No `jq` on Kindle** — had to rewrite JSON parsing to use `awk` instead of `jq`. Awk parser tested and working correctly against the actual JSON tap map.
  - **No `python3` usable on Kindle for JSON** — the PW4 has a `python3` binary but it fails silently on JSON parsing. v2 script tried python3 first and failed. v3 script uses pure awk, no python dependency.
  - **KUAL config.xml format:** Must use `<information>` + `<menus>` tags (not `<about>` + `<mainmenu>`). Modeled after koreader's config.xml.
  - **macOS `._` resource fork files** must be cleaned from the Kindle extension directory — they can confuse KUAL.
  - **WiFi works** — Kindle connects to home network (2.4GHz), reaches Mac at YOUR_SERVER_IP:8888. ~1s fetch time for PNG + JSON.
  - **`preventScreenSaver 1`** works as expected — keeps Kindle awake during dashboard session. Restored to 0 on exit.
- **Spike artifacts:**
  - `spike/view_server.py` — Python HTTP server, 5 views (home, calendar, cron, coaching, workflows), renders PNG + JSON tap map
  - `spike/dash_interactive.sh` — Shell viewer (v3), curl + awk + eips, touch via FIFO, exit action
  - `spike/touch_tap.c` — 50-line C touch helper, cross-compiled with Zig 0.16.0 for `arm-linux-musleabi` (static, 1.2MB)
  - KUAL extension installed at `/mnt/us/extensions/kindle-dash/` on Kindle
## 2026-07-16 — Decision: Kindle Dashboard as MCP Server

- **Discussed:** How to package the Kindle dashboard interface for use by multiple agents (sports coach, life coach, future agents). Evaluated three options: Skill, MCP Server, Standalone HTTP Service.
- **Decision:** Build the Kindle Dashboard as an **MCP Server**.
- **Rationale:**
  - The Kindle dashboard is shared infrastructure, not an agent capability. Multiple agents push data TO it independently.
  - Agents shouldn't know about Pillow, eips, tap maps, or Kindle internals — they just push data via `update_view(path, data)`.
  - MCP gives every connected agent a first-class tool interface (discoverable, type-safe).
  - Unlike a skill (each agent would run its own server, fight over port 8888, only one agent's views visible at a time), MCP centralizes rendering, view tree, and HTTP serving.
  - Unlike a standalone service (agents would use execute_code/terminal to POST — no clean tool interface), MCP provides proper tools.
- **Architecture:**
  ```
  Sports Coach Agent    Life Coach Agent    Future Agent
       │                     │                   │
       │ update_view(        │ update_view(      │ register_view(
       │   "coaching/...")    │   "life/...")     │   "habits/...")
       ▼                     ▼                   ▼
  ┌──────────────────────────────────────────────────┐
  │           Kindle Dashboard MCP Server             │
  │  • register_view(path, title, refresh_sec)       │
  │  • update_view(path, data) → renders PNG + taps  │
  │  • get_status() → Kindle online? current view?  │
  │  • list_views() → what's registered?             │
  │  • push_notification(text) → alert on home       │
  │  Internal: Pillow rendering, HTTP server, tree   │
  └──────────────────────┬───────────────────────────┘
                         │ HTTP
                  ┌──────┴──────┐
                  │   Kindle     │
                  └─────────────┘
  ```
- **Next steps:**
  - New session: grill the MCP design (tools, templates, view registration, data schemas, how agents declare views)
  - Design the view tree schema (unified navigation from multiple agents)
  - Build the MCP server with rendering templates per view type
  - Connect to real the agent data sources
- **Files touched:** LOG.md

## 2026-07-24 — Session: MCP Server Design Grill (7 dimensions resolved)

- **Discussed:** Full architecture grill of the MCP server design. 7 design dimensions explored through 8 clarify() questions. the developer's key insight: the dashboard is an "agent newspaper" — each agent has its own section with a visual style tailored to its data. Another key insight: cronjobs are the trigger mechanism — agents don't sit in loops, they wake on schedule, fetch data, push to dashboard.
- **Decisions (D03):**
  1. **Rendering model:** Typed view types (Model B). Agents push `{type: "<view_type>", ...fields}`. MCP has builtin Pillow renderers per type. Phase 1: 5 generic types (status_grid, metric_dashboard, text_list, chart_view, progress_view). Phase 2: agent-domain types added as data patterns understood.
  2. **Home view:** Fixed grid of agent slots. `push_home_card(agent_id, title, summary, nav_target)`. No ordering — each agent has a designated position.
  3. **View tree:** Namespaced by agent (sports/, life/, system/). No registration step — update_view creates on first push, overwrites after. Implicit registration.
  4. **Freshness:** No polling. Kindle fetches on interaction only (tap, refresh, wake). E-ink holds image when idle. Dropped 60-min auto-refresh timer — unnecessary for a personal dashboard.
  5. **Process lifecycle:** Stdio MCP (Option A). the agent-managed subprocess. HTTP server as background thread. Disk persistence for PNGs + metadata. Kindle offline cache covers the agent restart gaps. Subprocess respawns on cron push.
  6. **Extensibility:** Builtin view types only. No custom renderers, no raw_image escape hatch. New types = MCP code change. Safe because cronjobs are deterministic.
  7. **Tool surface:** 4 MCP tools (update_view, push_home_card, get_status, list_views) + 3 HTTP endpoints (/view, /images, /health).
- **Findings:** Researched the agent MCP lifecycle via official docs. Stdio servers are subprocesses that persist while the agent runs (idle_timeout_seconds: 0). They respawn on next tool call after death. HTTP MCP servers are remote endpoints. Chose stdio for simplicity — no launchd management, Kindle cache covers gaps.
- **Next steps:**
  - Build the MCP server: stdio handler + HTTP thread + Pillow renderers for 5 view types
  - Design agent-domain types (Phase 2) by studying what data each agent provides
  - Set up cronjobs: sports coach morning push, system agent status push
  - Configure in the agent config.yaml
  - Test end-to-end: agent cron → update_view → Kindle fetch
- **Files touched:** DECISIONS.md (D03), llm_wiki/mcp-server-design.md (new), LOG.md

## 2026-07-24 — Session: Power button sleep/wake lifecycle (v4)

- **Discussed:** Implement power button sleep/wake toggle for the dashboard. Kindle should sleep (native screensaver) when power button is pressed, wake back to dashboard when pressed again.
- **Decisions:**
  - **Single multiplexed FIFO** for both touch taps and power events. Power watcher (`lipc-wait-event` wrapper) writes `POWER:SLEEP`/`POWER:WAKE` to the same FIFO that `touch_tap` writes `x y` coordinates to. Main loop distinguishes by prefix. Chosen over dual-FIFO approach for simplicity — one fd to read, one `read -t 1` loop.
  - **Belt-and-suspenders wake detection**: LIPC event (primary) + time-gap detection (fallback). If `read -t 5` takes >10s, device was suspended. Handles case where `lipc-wait-event` misses the `outOfScreenSaver` event during restart.
  - **Touch helper killed on sleep, restarted on wake.** EVIOCGRAB must be released before sleep so Kindle can handle its own input during screensaver. Touch helper is restarted on wake to re-grab exclusively.
  - `preventScreenSaver` cleared on sleep (set to 0), re-set on wake (set to 1). Lets Kindle show native screensaver and proceed to deep sleep naturally.
- **Implementation:**
  - `handle_sleep()` function: kills touch helper → clears preventScreenSaver → blocks on FIFO read waiting for wake → on wake: re-sets preventScreenSaver → restarts touch helper → waits 3s for WiFi → fetches fresh view → displays
  - `start_power_watcher()`: background subshell running `lipc-wait-event -m com.lab126.powerd goingToScreenSaver outOfScreenSaver` in a loop, piping `POWER:SLEEP`/`POWER:WAKE` to the FIFO
  - `start_touch_helper()`: extracted from inline code, reused on wake
  - Main loop `case` statement: routes `POWER:SLEEP` to `handle_sleep()`, ignores stale `POWER:WAKE`, processes touch taps as before
  - Exit action updated: also kills power watcher PID
  - `stop.sh` updated: kills `dash_interactive.sh`, `touch_tap`, `lipc-wait-event`, `curl`
- **Next steps:**
  - Deploy to Kindle (done — script copied, resource forks cleaned)
  - Test: launch via KUAL, press power button to sleep, press again to wake, verify dashboard returns
  - Check viewer.log on Kindle for sleep/wake event flow
- **Files touched:** spike/dash_interactive.sh (v4), stop.sh, LOG.md

## 2026-07-24 — Session: Power button sleep/wake — WORKING (v4 final)

- **Discussed:** Implement power button sleep/wake toggle. Kindle shows native screensaver on sleep, returns to dashboard on wake.
- **Bugs found and fixed (5 iterations):**
  1. **`preventScreenSaver 1` blocked ALL screensaver entry** — including power button. `goingToScreenSaver` LIPC event never fired. Fix: removed `preventScreenSaver` entirely. Kindle sleeps naturally.
  2. **`lipc-wait-event` syntax** — event names must be comma-separated (`goingToScreenSaver,outOfScreenSaver`), not space-separated. Space-separated just printed usage message.
  3. **Dual-writer FIFO corruption** — `touch_tap` and `lipc-wait-event` both writing to same FIFO caused interleaved lines: `goingToScreenSaver 2` split into `r 2` (misinterpreted as tap → navigated to random pages). Fix: separated channels — touch taps via FIFO (fd3), power events via flag files (`.sleep_flag` / `.wake_flag`) polled by main loop.
  4. **Killing touch helper on sleep broke swipe-to-unlock** — restarting `touch_tap` on wake re-grabbed EVIOCGRAB before user finished swiping. Fix: don't kill touch helper during sleep. Frozen `touch_tap` can't read events, so Kindle framework handles swipe-to-unlock naturally.
  5. **Phantom tap on wake** — `touch_tap` froze during sleep, resumed with device, read buffered swipe-to-unlock events, reported release point as a tap at ~(466,1201) → always hit coaching/readiness button. Fix: drain FIFO for 2 seconds after displaying home view on wake to flush phantom swipe residue.
- **Final architecture:**
  - Touch helper (`touch_tap`) runs continuously — never killed during sleep. Writes `x y` taps to TOUCH_FIFO.
  - Power watcher (background subshell) runs `lipc-wait-event -m com.lab126.powerd goingToScreenSaver,outOfScreenSaver`. On event, creates flag file (`.sleep_flag` / `.wake_flag`).
  - Main loop: polls `.sleep_flag` → `handle_sleep()` → clears screen (`eips -c`) → waits for `.wake_flag` or time-gap detection → waits 3s for WiFi → fetches home → displays → drains phantom taps for 2s.
  - No `preventScreenSaver` used anywhere — Kindle sleeps naturally on timeout or power button.
- **Key Kindle quirks discovered:**
  - `preventScreenSaver 1` blocks the power button's `goingToScreenSaver` event — don't use it if you want power button sleep
  - `lipc-wait-event` event names are comma-separated, not space-separated
  - A frozen `touch_tap` process doesn't block the Kindle framework from handling swipe-to-unlock — EVIOCGRAB on a frozen process is effectively released
  - `touch_tap` resumes with buffered evdev events from the swipe-to-unlock gesture — must drain FIFO after wake
- **Files touched:** spike/dash_interactive.sh (v4 final), LOG.md

## 2026-07-24 — Session: Code review disaster + revert

- **Discussed:** Ran a "smart model" code review on all dashboard scripts. It found 29 "issues" and attempted to fix all of them. Broke the working system in 4 different ways across 3 rounds of increasingly broken patches. Reverted everything to original v4 state.
- **What went wrong:**
  1. `read -t` assumed unsupported in ash → replaced with elaborate background-subshell poller → race condition → infinite touch-helper restart loop. Original `read -t` works fine on this Kindle.
  2. EVIOCGRAB error checking → "Resource busy" warning → graceful fallback skipped the grab → KUAL stole touches. Original unchecked EVIOCGRAB succeeds.
  3. Path traversal fix in `view_server.py` → macOS `/tmp` resolves to `/private/tmp` → `startswith` check always False → every image request 403. The one legitimate bug, implemented wrong.
  4. `menu.json` `exitmenu: true` → dumped to Kindle home before script ran. Worst single change.
- **Postmortem written:** `POSTMORTEM-2026-07-24.md` — full timeline, root cause analysis, lessons.
- **Key lesson:** "If it works, don't fix it." A code review that finds 29 issues in working code should trigger skepticism about the review, not a rewrite. Fix one thing at a time, test on device between each.
- **State after revert:** All files restored to pre-review v4 working state. Only `view_server.py` path traversal fix was kept (needs correct implementation — normalize paths before comparing).
- **Files touched:** POSTMORTEM-2026-07-24.md (new), all files reverted, LOG.md

## 2026-07-24 — Post-mortem: Failed bug-fix session, full revert
- **What happened:** the developer requested code review of spike files. Review found 29 "issues." "Fix all" led to 3 rounds of increasingly broken patches. All fixes reverted to original v4 state.
- **Key lesson:** Original spike code worked. The review found theoretical edge cases, not real bugs. Fixing them introduced actual bugs (restart loops, 403 errors, KUAL touch interference, broken exit paths).
- **Worst mistakes:**
  - Replaced working `read -t` with broken background-subshell poller → infinite restart loop
  - Added path traversal check to view_server.py → macOS `/tmp`→`/private/tmp` resolution broke all image fetches (403)
  - Set `exitmenu: true` in menu.json → dumped to Kindle home before script ran, no exit path
  - Recompiled `touch_tap` with "graceful" EVIOCGRAB handling → framework also got touches, KUAL picked up taps
- **What survived:** view_server.py path traversal fix (legitimate security fix). wait_for_network() concept (useful improvement for future).
- **Resolution:** All files restored to original v4 state. Dashboard works perfectly.
- **Files touched:** POSTMORTEM-2026-07-24.md (full report), all spike files reverted to originals

## 2026-07-24 — Feature: Custom lock screen

- **Implemented:** Custom lock screen displayed when Kindle goes to sleep, replacing the `eips -c` white screen.
- **Server changes** (`view_server.py`):
  - Added `render_lock_screen()` — renders 1072×1448 grayscale PNG with black background, large clock, date, battery level, next event, "KINDLE DASH" label
  - Added `lock_screen` route in `render_view()` — returns PNG with empty tap map (not interactive)
  - Tested: endpoint returns valid JSON + 12.5KB PNG, 200 OK
- **Shell changes** (`dash_interactive.sh`) — 3 surgical changes, nothing else touched:
  - Added `LOCK_PNG` variable (`${CACHE_DIR}/lock_screen.png`)
  - Added `cache_lock_screen()` function — fetches lock screen from server, stores locally on Kindle. Skips if already cached.
  - Modified `handle_sleep()`: if `LOCK_PNG` exists, `sleep 1` (let native screensaver paint) then `eips -f -g "$LOCK_PNG"`. Falls back to `eips -c` if no cached image.
  - Called `cache_lock_screen` after initial home display (pre-cache for first sleep)
  - Called `cache_lock_screen` after wake (re-cache with fresh time — old one had stale time from before sleep)
- **Design decisions:**
  - Lock screen PNG is pre-cached — no network fetch during the 5s "Ready to Suspend" window
  - `sleep 1` before `eips -f -g` lets Kindle framework paint its native screensaver first, then we overwrite
  - Re-cache after wake ensures the clock/time is fresh for next sleep
  - Lock screen is non-interactive (empty tap map) — it's a display-only screen
- **Files touched:** spike/view_server.py, spike/dash_interactive.sh, LOG.md

## 2026-07-25 — Feature: Custom lock screen (ABANDONED)

- **Attempted:** Custom screensaver via 3 approaches: (1) eips overlay, (2) direct /usr/share/blanket/screensaver/ replacement, (3) linkss hack bind-mount.
- **Result:** All failed on FW 5.16.7. linkss officially unsupported — Amazon switched to hard-float ABI at 5.16.3, all linkss binaries segfault.
- **Decision:** Abandoned. Not a project requirement. handle_sleep() reverted to original v4 (eips -c).
- **Would work:** FW downgrade to 5.16.2.1.1 + linkss. Not worth the risk for non-essential feature.
- **Research:** 3 wiki files written: kindle-screensaver-replacement.md, kindle-screensaver-firmware-5.16.md, kindle-firmware-downgrade.md
- **Files touched:** spike/dash_interactive.sh (reverted), spike/view_server.py (lock_screen code kept but unused), spike/bg_ss0.png, spike/install_screensaver.sh, spike/fix_linker.sh, spike/menu.json, LOG.md

## 2026-07-31 — Session: Verified working on hardware end-to-end, bug fix, public repo prep

- **Discussed:** Get the dashboard actually running again with the physical Kindle connected, confirm it against fresh logs (not just prior claims), then split off a sanitized public repo.
- **Found:** The repo was missing `config.xml` entirely (README's Quick Start referenced a nonexistent `spike/kual/` folder), and `skill/templates/kual-extension/` contained the *buggy* v4.1 `dash_interactive.sh` (the race-condition/restart-loop version from POSTMORTEM-2026-07-24.md) plus a `config.xml` using the wrong `<about>`/`<mainmenu>` tags — exactly the format the project's own docs call broken.
- **Built:** `spike/kindle-dash/` — a ready-to-copy KUAL bundle assembled only from proven-good pieces: `spike/dash_interactive.sh` (v4 final, byte-identical), the pre-compiled `touch_tap`, `spike/stop.sh`, a corrected `config.xml`, and `menu.json` (placeholder IP in the repo; real LAN IP only on the deployed device copy).
- **Fixed `skill/templates/kual-extension/`** to match — replaced the buggy `dash_interactive.sh`/`stop.sh` and wrong-tag `config.xml` with the known-good versions, so the skill template doesn't keep reproducing the postmortem bug for future builds.
- **Deployed to the real Kindle (USB mass-storage mount) and verified via `viewer.log` on-device** — not just visual inspection: every button tap logged a correct `HIT: navigate -> ...`, back/home worked, a full power-button sleep → `goingToScreenSaver`/`outOfScreenSaver` → wake cycle redisplayed home cleanly with phantom-tap draining, and exit returned cleanly to the Kindle home screen.
- **Real bug found and fixed (user-reported, reproduced twice, not theoretical):** `hit_test()` in `dash_interactive.sh` had a fallback that retried tap coordinates mirrored horizontally/vertically/both, meant for hardware where touch axes don't match screen axes. On this Kindle they always have (confirmed by every successful direct hit in the logs), so the fallback only ever produced false positives — tapping empty space (e.g. the header) could mirror into a button's rectangle and fire it. **Fix: deleted the fallback block entirely**, keeping only the direct-coordinate check. Deployed and confirmed on-device: empty-space taps now do nothing, real buttons still work.
- **Security fix (view_server.py):** the path-traversal check mentioned in POSTMORTEM-2026-07-24.md as "the one legitimate fix, needs correct implementation" had actually been fully reverted — `/images/` had zero sanitization. Added filename allowlisting (`[a-zA-Z0-9_\-.]+`) plus a resolved-path containment check (avoiding the earlier `/tmp` vs `/private/tmp` mistake by resolving the base dir once, not per-request), and a `Content-Length` header. Tested via curl: traversal attempts now 403/404, legitimate image fetches still 200.
- **Privacy fix:** the shipped `touch_tap` binary was compiled without `-s` and embedded the absolute build path in `debug_info` — recoverable via `strings`, leaking the local username and the private project's old codename. Rebuilt from the **unmodified** `touch_tap.c` with `-s` added (zig 0.13.0, same target flags) — no logic change, debug symbols only. Verified `strings` is clean, then re-deployed and re-tested on hardware to confirm identical touch behavior before trusting it.
- **Next steps:** create a separate public repo (`kindle-dash`) from this sanitized state, push.
- **Files touched:** spike/view_server.py, spike/dash_interactive.sh, spike/touch_tap (rebuilt+stripped), spike/kindle-dash/ (new), skill/templates/kual-extension/{config.xml,bin/dash_interactive.sh,bin/stop.sh}, README.md, LOG.md
