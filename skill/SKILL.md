---
name: kindle-eink-dashboard
description: Build server-driven e-ink dashboards on a jailbroken Kindle. Python view server renders PNG + JSON tap map, Kindle shell viewer displays via eips, C touch helper reads evdev. Proven on Kindle Paperwhite 4.
version: 1.0.0
author: the agent + the developer
metadata:
  the agent:
    tags: [kindle, e-ink, dashboard, cross-compile, arm, zig]
---

# Kindle E-Ink Dashboard

Build a server-driven e-ink dashboard on a jailbroken Kindle. The Kindle is a dumb display — a server (Mac/Python) generates PNG images + JSON tap maps, the Kindle fetches and displays them. A tiny C touch helper reads evdev input for tap navigation.

## Code Review and Bug Fixing Workflow

**Do NOT fix working code without testing on hardware first.** This is the hardest-won lesson from this project. Two sessions now have proven it:

1. **v4→v4.1 code review:** identified 20+ "bugs" in the shell script. Many were theoretical (busybox `read -t`, `!` subshell, `local` keyword) — they existed in code but the script still worked because the runtime paths didn't hit them. Fixing them introduced NEW bugs that broke the working dashboard.
2. **v4.1→v4.3 fix session (2026-07-24):** "fix all" on a code review of a WORKING dashboard. 3 rounds of increasingly broken patches. Every fix created new problems. Ended with a full revert to the original code. The dashboard worked perfectly again. Full report: `POSTMORTEM-2026-07-24.md` in the idea folder.

**The pattern that kills:** review finds theoretical bugs → "fix all" → batch of 20 fixes → deploy → something breaks → can't tell which fix caused it → patch on top of patch → system is now worse than before any fixes.

**Rules for Kindle shell script changes:**
1. **Test every change on hardware** — `sh -n` syntax check is not enough. The Kindle's busybox ash, FIFO behavior, and LIPC event timing can only be verified on-device.
2. **One fix at a time** — deploy, test, confirm working, then next fix. Never batch 20 fixes into one deploy.
3. **Keep the original** — always preserve the last-working version. No git on the spike directory means no undo. Copy the working file to `.bak` before editing.
4. **Theoretical bugs < working code** — a bug that exists in code but doesn't manifest in the current execution path is lower priority than a bug that actively breaks the user experience. If the dashboard works, don't fix it.
5. **Don't fix what you can't test** — if you can't verify the fix on hardware, don't apply it.
6. **When the user says "fix all" on a working spike, push back** — say "here are the 2-3 that actually matter, want me to fix just those?" Batching fixes on working code is how you break it.
7. **If 3+ fixes in a row make things worse, STOP and revert everything** — you're in a debugging spiral. Revert to the last known working state, then re-approach with one fix at a time.
8. **Never recompile a working binary** — the `touch_tap` binary worked. Recompiling with "improvements" (EVIOCGRAB error handling, CLOCK_MONOTONIC) changed its behavior and broke touch. Only recompile when you have a specific, demonstrated bug in the binary itself.

## Architecture

```
Mac (Python server)          Kindle (shell + C)
┌──────────────┐            ┌──────────────────┐
│ View Server   │  HTTP LAN  │ dash_interactive.sh│
│ (Pillow PNG)  │───────────▶│ • curl fetch PNG   │
│ + tap map JSON│            │ • eips -f -g display│
└──────────────┘            │ • awk parse taps    │
                            │ • hit test → navigate│
                            └──────┬─────────────┘
                                   │ FIFO pipe: "x y\n"
                            ┌──────┴─────────────┐
                            │ touch_tap (C, 50ln) │
                            │ • EVIOCGRAB         │
                            │ • evdev /dev/input  │
                            │ • prints tap coords │
                            └────────────────────┘
```

## Target Hardware

- Kindle Paperwhite 4 (10th Gen, 2018)
- Screen: 1072×1448, 300 PPI, 8-bit grayscale
- Capacitive touch, WiFi (2.4GHz only)
- Jailbroken with WinterBreak + KUAL

## Cross-Compiling C for Kindle

Install Zig, cross-compile static ARM binary:

```sh
# Install Zig
curl -sL https://ziglang.org/download/0.16.0/zig-aarch64-macos-0.16.0.tar.xz -o /tmp/zig.tar.xz
cd /tmp && tar xf zig.tar.xz

# Cross-compile
/tmp/zig-aarch64-macos-0.16.0/zig cc -target arm-linux-musleabi -O2 -static -o touch_tap touch_tap.c

# Verify
file touch_tap  # Should show: ELF 32-bit LSB executable, ARM, EABI5, statically linked
```

## KUAL Extension Structure

```
/mnt/us/extensions/kindle-dash/
├── config.xml    ← Must use <information> + <menus> tags (NOT <about>/<mainmenu>)
├── menu.json     ← KUAL menu items
└── bin/
    ├── dash_interactive.sh
    ├── touch_tap              ← ARM static binary
    ├── show_static.sh         ← Display pre-copied PNG
    └── stop.sh
```

### config.xml (correct format — modeled after koreader)

```xml
<?xml version="1.0" encoding="UTF-8"?>
<extension>
    <information>
        <name>Kindle Dashboard</name>
        <version>0.1.0</version>
        <author>Your Name</author>
        <id>kindle-dash</id>
    </information>
    <menus>
        <menu type="json" dynamic="true">menu.json</menu>
    </menus>
</extension>
```

### menu.json

```json
{
    "items": [{
        "name": "Kindle Dashboard",
        "priority": 0,
        "items": [{
            "name": "Start Dashboard",
            "priority": 1,
            "action": "/mnt/us/extensions/kindle-dash/bin/dash_interactive.sh",
            "params": "http://YOUR_SERVER_IP:8888",
            "exitmenu": false
        }]
    }]
}
```

## Deploying to Kindle

```sh
# Copy files via USB
cp dash_interactive.sh /Volumes/Kindle/extensions/kindle-dash/bin/
cp touch_tap /Volumes/Kindle/extensions/kindle-dash/bin/
chmod +x /Volumes/Kindle/extensions/kindle-dash/bin/*

# CRITICAL: Clean macOS resource fork files — they break KUAL
find /Volumes/Kindle/extensions/kindle-dash -name '._*' -delete
```

## Touch Helper (touch_tap.c)

Key implementation details:

1. **Scan `/dev/input/event0..15`** — don't hardcode event number (changes between boot modes)
2. **Use `EVIOCGABS(ABS_X)` and `EVIOCGABS(ABS_MT_POSITION_X)`** to detect touch devices
3. **Handle 0-0 range:** PW4 reports `x:0-0 y:0-0` via EVIOCGABS — the driver outputs raw pixel coordinates directly. Scale function must clamp, not divide by zero.
4. **`EVIOCGRAB` for exclusive access** — prevents Kindle framework from also receiving touches
5. **700ms debounce** — e-ink refresh is slow, rapid taps cause confusion
6. **Output: `printf("%d %d\n", x, y)` on tap release** — line-buffered stdout
7. **32-bit ARM struct size:** `struct input_event` is 16 bytes (not 24 as on 64-bit). timeval is 4+4=8 bytes on ARM EABI5.
8. **Use `clock_gettime(CLOCK_MONOTONIC)` for debounce** — `gettimeofday` breaks when NTP syncs after wake (clock jumps forward/backward). Monotonic clock is immune.
9. **No SYN_REPORT tap emission** — SYN_REPORT can fire with stale coordinates if the touch sequence doesn't use BTN_TOUCH. Only emit taps on BTN_TOUCH release or ABS_MT_TRACKING_ID=-1.

## Shell Viewer (dash_interactive.sh)

Key patterns:

1. **No `jq` on Kindle** — use `awk` for JSON parsing. The awk parser extracts x/y/w/h/action/target from each tap block.
2. **No usable `python3` on Kindle** — the PW4 has a python3 binary but it fails on JSON. Use awk, not python.
3. **FIFO pipe for touch input:** `mkfifo`, start touch helper writing to FIFO, then open fd3 for reading (`exec 3< "$TOUCH_FIFO"`). The v4 working code starts the helper first (it blocks on open() until a reader attaches), then opens fd3. This ordering works on this Kindle. If touch_tap dies silently on startup, check whether fd3 was opened — but don't preemptively reorder without testing on hardware.
4. **`read -t` WORKS on PW4 busybox ash** — despite theoretical concerns, `read -r -t 1 tap_line <&3` works correctly on this Kindle's busybox build. The v4 final code uses it in the main loop. **Do NOT replace it with a background-reader-subshell workaround** — that was attempted in the postmortem session (POSTMORTEM-2026-07-24.md, Fix 2) and created the worst bug of the session: race conditions → false EOF detections → infinite touch-helper restart loop. If `read -t` works, leave it alone.
5. **Atomic downloads:** curl to `.tmp`, then `mv` to final name.
6. **`if ! fetch_view` works on busybox ash** — the v4 code uses `if ! fetch_view "home"` and it works. An earlier skill version claimed POSIX `!` forks a subshell and loses globals. **That was wrong for this Kindle's busybox.** The postmortem (POSTMORTEM-2026-07-24.md, Fix 1) confirmed busybox ash does NOT fork here. Do NOT rewrite this pattern.
7. **Trap handler for cleanup:** `trap cleanup INT TERM` with a `cleanup()` that kills children, closes fd3, removes FIFO/flags/PID file. Without it, SIGTERM orphans everything.
8. **PID file for stop.sh:** `echo $$ > "$PID_FILE"` at startup. `killall` may not match the process comm reliably on busybox.
6. **Exit action (v4 final):** Kill touch helper and power watcher, remove FIFO/flags, relaunch Kindle home. The v4 code does NOT set/restore `preventScreenSaver` (it was removed entirely):
   ```sh
   exec 3<&-
   kill $TOUCH_PID 2>/dev/null
   kill $POWER_WATCHER_PID 2>/dev/null
   rm -f "$TOUCH_FIFO" "$SLEEP_FLAG" "$WAKE_FLAG"
   lipc-set-prop com.lab126.appmgrd start app://com.lab126.booklet.home 2>/dev/null
   ```

## View Protocol

```
GET /view?path=home → JSON:
{
  "version": 1,
  "title": "Home",
  "image": "/images/home.png",
  "taps": [
    {"x": 20, "y": 650, "w": 506, "h": 320, "action": "navigate", "target": "calendar/today", "label": "Calendar"},
    {"x": 872, "y": 1378, "w": 180, "h": 50, "action": "exit", "target": "", "label": "Exit"}
  ],
  "back": null,
  "refresh_sec": 3600
}

GET /images/home.png → PNG bytes (1072×1448, 8-bit grayscale)
```

Action types: `navigate`, `refresh`, `toggle`, `custom`, `exit`.

## View Server (Python, Mac)

- Use Pillow to render PNG: `Image.new("L", (1072, 1448), 255)` — mode "L" is 8-bit grayscale
- Save PNGs to a served directory, return relative path in JSON
- `http.server.BaseHTTPRequestHandler` is sufficient — no Flask needed
- Include an exit button on every view
- **Sanitize image paths** — reject anything that isn't `[a-zA-Z0-9_\-.]` and verify resolved path stays under the served directory. Without this, `/images/../../etc/passwd` reads arbitrary files.
- **Add Content-Length header** on image responses — more robust than relying on HTTP/1.0 connection close.

## MCP Server Architecture (D03 — multi-agent dashboard)

When the dashboard evolves from a single server to a multi-agent MCP server, the architecture changes. The "agent newspaper" model: each agent has a designated card slot on the home view, and a namespaced view tree (`sports/readiness`, `life/habits`, `system/cron`). Agents are data pushers — they call `update_view(path, {type: "metric_dashboard", ...})` and the MCP renders via builtin Pillow renderers per view type. Cronjobs are the trigger — agents don't sit in loops.

**Key design decisions (see `references/mcp-server-design.md` for full spec):**
- **Typed view types (not freeform text or widget DSL):** 5 generic types in Phase 1 (status_grid, metric_dashboard, text_list, chart_view, progress_view). Agents pick a type and pass matching structured data. Phase 2 adds agent-domain types.
- **No polling:** Kindle fetches on interaction only (tap, refresh, wake). E-ink holds the image when idle. The auto-refresh timer from the spike was unnecessary.
- **Stdio MCP (not standalone daemon):** the agent-managed subprocess. HTTP server runs as background thread inside the MCP. PNGs persisted to disk survive process restarts. Kindle offline cache covers the agent restart gaps.
- **No custom renderers:** Builtin types only. New types = MCP code change. Safe because cronjobs are deterministic — no surprise data shapes.
- **Home view = fixed grid of agent slots:** `push_home_card(agent_id, title, summary, nav_target)`. No ordering, no priority.

**the agent config entry:**
```yaml
mcp_servers:
  kindle-dash:
    command: "python3"
    args: ["/path/to/server.py"]
    idle_timeout_seconds: 0   # keep alive indefinitely
    tools:
      include: [update_view, push_home_card, get_status, list_views]
```

See `references/mcp-server-design.md` for the full design spec (tools, params, view type schemas, data flow, lifecycle). See `templates/mcp_server_skeleton.py` for a starting-point server showing the stdio + HTTP thread + renderer pattern.

## Power Button Sleep/Wake Lifecycle (v4 final — WORKING)

The dashboard sleeps when the power button is pressed (Kindle native screensaver → deep sleep) and wakes back to the dashboard when pressed again. The shell process survives deep sleep — it freezes and resumes on wake without restarting.

### Critical: `preventScreenSaver` — DO NOT USE for interactive viewers

**Interactive viewer (dash_interactive.sh):** Do NOT set `preventScreenSaver 1`. It blocks the power button's `goingToScreenSaver` LIPC event — the sleep detection never fires and the sleep/wake lifecycle breaks entirely. The v4 final working code does NOT use `preventScreenSaver` anywhere. The Kindle sleeps naturally on power button press or timeout.

An earlier version of this skill said to set it. **That was wrong.** The LOG and POSTMORTEM both confirm: `preventScreenSaver 1` blocked ALL screensaver entry including power button, `goingToScreenSaver` never fired. Fix was removing it entirely.

**Static viewer (dash_viewer.sh):** A simple fetch-display loop with no sleep/wake handling may use `preventScreenSaver 1` to avoid timeout sleep — but this is a different use case from the interactive dashboard.

### Architecture: Separate channels (NOT shared FIFO)

**Do NOT use a shared FIFO for touch + power events.** Two processes writing to the same FIFO causes line interleaving/corruption: `goingToScreenSaver 2` splits into `r 2`, which the main loop misinterprets as a tap coordinate → navigates to a random page.

The working v4 architecture uses **separate channels**:

```
touch_tap (C binary)   → writes "x y\n" to TOUCH_FIFO (fd3)     ← touch taps only
power watcher (subsh)  → creates flag files on LIPC events       ← power events only
                         .sleep_flag  (goingToScreenSaver)
                         .wake_flag   (outOfScreenSaver)
main loop              → reads TOUCH_FIFO via `read -r -t 1 <&3`
                       → polls `.sleep_flag` existence each iteration
```

The power watcher runs `lipc-wait-event` piped through `while read` — but writes flag files via `touch`, NOT `echo` to the FIFO. The `echo`-to-FIFO approach fails in busybox piped subshells.

### Critical: Do NOT kill touch_tap during sleep

Killing `touch_tap` on sleep and restarting it on wake **breaks swipe-to-unlock**. The restarted process re-grabs `EVIOCGRAB` before the user finishes swiping.

Instead: **leave `touch_tap` running.** A frozen process can't read events, so `EVIOCGRAB` on a frozen process is effectively released — the Kindle framework handles swipe-to-unlock naturally. This is the behavior that worked in v3 (before sleep/wake was added).

### Critical: Drain phantom taps after wake

`touch_tap` freezes during sleep, resumes with the device, and reads **buffered evdev events from the swipe-to-unlock gesture**. It reports the release point (~466,1201 — the coaching button area) as a tap. Without draining, this phantom tap navigates to a random page immediately after wake.

**Fix:** after displaying home on wake, drain the FIFO for 2 seconds before accepting real input:

```sh
drain_until=$(($(date +%s) + 2))
while [ "$(date +%s)" -lt "$drain_until" ]; do
    read -r -t 1 drain_line <&3 2>/dev/null && log "Drained: $drain_line"
done
```

### Three LIPC pitfalls

1. **Event names MUST be comma-separated**: `goingToScreenSaver,outOfScreenSaver` (NOT space-separated — prints usage and exits)
2. **No `echo` to FIFO in a piped subshell**: `lipc-wait-event | while read ... echo "POWER:SLEEP"` doesn't work in busybox. Use flag files (`touch $SLEEP_FLAG`) instead.
3. **Don't share the FIFO with lipc-wait-event**: even direct-write (no echo) causes line corruption. Use separate channels.

See `references/power-lifecycle.md` for full implementation details, the final working code, and the debugging guide (including all 5 bugs that were iterated through). See `references/busybox-ash-patterns.md` for the non-blocking read workaround and other busybox ash shell patterns. See `references/code-review-2026-07.md` for the full bug list from the v4→v4.1 code review.

## Custom Lock Screen / Screensaver (sleep display)

Two approaches exist. **Use native replacement (Approach B)** unless you need dynamic content that changes per sleep cycle.

### Approach A: Overlay (DO NOT USE — causes flash)

Display a custom PNG via `eips -f -g` after the Kindle paints its native screensaver. **This causes a visible flash** — the native screensaver appears briefly, then gets overwritten. The user sees the default Kindle screensaver flash before the custom image.

The overlay approach also requires: pre-caching the PNG on Kindle, re-caching after wake (stale time), and a `sleep 1` delay before `eips`. It's fragile and adds complexity for no benefit over Approach B.

### Approach B: Native screensaver replacement via linkss (BEST for static images — but unsupported on FW 5.16+)

Replace the native Kindle screensaver image itself. The Kindle framework shows your custom image directly on sleep — no overlay, no flash, no `eips` calls in `handle_sleep()`. Best for static designs that don't change per sleep cycle.

**⚠️ CRITICAL — linkss 0.25.N is UNSUPPORTED on FW 5.16.x and later.** NiLuJe (the original author) confirmed on MobileRead t=195474 post #2989 (Dec 2023): *"No, it isn't supported on FW version with native custom screensaver support (and that was, like 5.12 or even earlier?)"*. The installer doesn't refuse to install (no FW version check), so it "succeeds" but the bind-mount mechanism conflicts with the native screensaver system Amazon introduced in ~FW 5.12. On FW 5.16.7, symptoms include: default screensavers still showing, custom image appearing once then reverting, cycling modes not working, and framework restart freezes. **For FW 5.16+, use Approach C (FBInk) or KOReader Sleep Screen instead — see `references/screensaver-troubleshooting-5.16.md`.**

**For older FW (pre-5.12) or if you want to try linkss anyway:**

**CRITICAL — the blanket directory is tmpfs, NOT a regular folder.** `/usr/share/blanket/screensaver/` is a RAM-backed tmpfs (`mount` shows `type tmpfs (rw,relatime,size=4096k)`). The framework regenerates stock images into it on every boot. Direct `cp` to this path (as earlier versions of this skill recommended) is volatile — the image works for the current session but is lost on reboot. Use the **linkss hack** instead, which bind-mounts a persistent directory over the tmpfs path via an upstart job that runs before the framework starts.

**How linkss works (verified from NiLuJe's linkss v0.25.N source):**

1. Install linkss via MRPI (one-time): copy `Update_linkss_0.25.N_install_pw2_kt2_kv_pw3_koa_kt3_koa2_pw4_kt4.bin` to `/mnt/us/mrpackages/`, then `KUAL → Helper → Install MR Packages`
2. Enable at boot: `KUAL → Screen Savers → Enable hack at boot` (creates `/mnt/us/linkss/auto`)
3. Drop your PNG into `/mnt/us/linkss/screensavers/` — linkss renames it to `bg_ss00.png` and bind-mounts the result over `/usr/share/blanket/screensaver/`
4. Restart the framework after changing images: `KUAL → Screen Savers → Restart framework now` (or `stop framework && sync && start framework`)

For the dashboard's single static image, the script can copy the PNG to `/mnt/us/linkss/screensavers/bg_ss00.png` on startup (replacing any previous image), then trigger a framework restart if the image changed. Alternatively, install the image once and leave it — linkss persists it across reboots automatically.

**Image requirements (verified):** PNG, 1072×1448, 8-bit grayscale 256-color (`magick identify` shows `8-bit Gray 256c`). PIL `mode='L'` matches. The framework auto-renames processed images to `bg_ss00.png`, `bg_ss01.png`, etc. (zero-indexed, zero-padded).

**`handle_sleep()` with native replacement — no eips needed:**
```sh
handle_sleep() {
    log "=== SLEEP: entering sleep mode ==="
    rm -f "$SLEEP_FLAG"
    # Kindle shows the native screensaver (now our custom image) automatically.
    # No overlay, no eips calls — just wait for wake.
    log "Kindle will sleep naturally (screensaver → deep sleep)"
    # ... wait for wake as before ...
}
```

### Approach C: Direct FBInk image display (RECOMMENDED for FW 5.16+ — no screensaver hack needed)

For firmware where linkss is unsupported (5.16.x+), use `fbink` directly to push images to the e-ink panel. This is what production Kindle dashboard projects (HASS Lovelace, weather displays) actually use:

```bash
# Via SSH or KUAL terminal:
/mnt/us/koreader/fbink -i /mnt/us/your_image.png -g
```

This bypasses the entire screensaver system — you draw an image to the framebuffer directly. The image stays until you draw another one or the device sleeps and the framework overwrites it.

**For a dashboard that updates periodically:**
- Disable sleep entirely: `lipc-set-prop -i com.lab126.powerd powerd 0`
- Run a cron/script that calls `fbink -i new_image.png` on a schedule
- No linkss, no bind-mount, no framework restart needed

### Approach D: KOReader Sleep Screen (RECOMMENDED for static custom images on FW 5.16+)

KOReader has its own screensaver system that works independently of the Kindle framework. It draws directly to the framebuffer using FBInk.

1. In KOReader: Settings (gear) → Screen → Sleep screen
2. Set "Sleep screen" to: **Image file** or **Random image from folder**
3. Set the folder to `/mnt/us/linkss/screensavers/` or any custom path
4. Set "Sleep screen message" to OFF (removes the "Sleeping..." text)
5. KOReader draws the image to the e-ink panel directly — **no framework restart needed, no bind-mount, no conflict with native FW**

**Caveat:** KOReader's sleep screen only activates when KOReader is the active app. If you're on the Kindle home screen, the native framework screensaver takes over. For a dedicated dashboard, keep KOReader running in the foreground.

See `references/screensaver-troubleshooting-5.16.md` for the full troubleshooting guide covering linkss on FW 5.16.7, bind-mount verification, framework restart freeze causes, the "Display Cover" setting conflict, and alternative approaches. See `references/screensaver-replacement.md` for the original linkss installation procedure (pre-5.16 FW), manual bind-mount alternative, image format verification, and source citations from MobileRead forums and linkss source code. See `references/firmware-downgrade.md` for the procedure to downgrade PW4 from 5.16.x to 5.16.2.1.1 (where linkss works natively). See `templates/fix_linker.sh` for a ready-to-deploy KUAL script that fixes the `xzdec: not found` error on FW 5.16+.

## Pitfalls Discovered

| Pitfall | Fix |
|---|---|
| `preventScreenSaver 1` blocks power button sleep | **Do NOT use it for interactive viewers.** It blocks the power button's `goingToScreenSaver` event entirely — sleep detection never fires. The v4 final working code does NOT use `preventScreenSaver` anywhere. Kindle sleeps naturally. |
| `lipc-wait-event` events space-separated | MUST be comma-separated: `goingToScreenSaver,outOfScreenSaver`. Space-separated prints usage and exits. |
| `echo` in piped subshell doesn't reach FIFO | Don't pipe `lipc-wait-event \| while read ... echo`. Use flag files (`touch $SLEEP_FLAG`) instead — the main loop polls for file existence. |
| Shared FIFO corrupts lines (touch + power) | Two processes writing to the same FIFO causes interleaving: `goingToScreenSaver 2` splits into `r 2` (misinterpreted as tap → random navigation). Use separate channels: touch taps via FIFO, power events via flag files. |
| Killing touch_tap on sleep breaks swipe-to-unlock | Don't kill it. A frozen `touch_tap` can't read events, so EVIOCGRAB on a frozen process is effectively released. Kindle framework handles swipe-to-unlock naturally. |
| Phantom tap on wake (navigates to random page) | `touch_tap` resumes with buffered swipe-to-unlock events, reports release point as tap. Drain FIFO for 2 seconds after displaying home on wake. |
| Screen ghosts through screensaver on repeated sleep cycles | `eips -c` (clear to white) before sleep |
| Wake returns to wrong page | Always fetch `home` on wake, not `CURRENT_PATH` |
| KUAL doesn't show extension | Use `<information>`/`<menus>` in config.xml, not `<about>`/`<mainmenu>` |
| `._` files break KUAL | `find ... -name '._*' -delete` after every copy |
| `jq` not on Kindle | Use `awk` for JSON parsing |
| `python3` fails silently on Kindle | Don't use python3 on Kindle at all — pure awk |
| Touch EVIOCGABS returns 0-0 range | PW4 reports raw pixel coords — clamp, don't scale |
| `eips -c` on exit leaves white screen | Use `lipc-set-prop com.lab126.appmgrd start app://com.lab126.booklet.home` instead |
| White screen after exit | Don't clear framebuffer — let Kindle home repaint |
| 2.4GHz WiFi only | Ensure AP broadcasts 2.4GHz SSID |
| `stop.sh` doesn't kill power watcher | Kill `lipc-wait-event` and `dash_interactive.sh` too, not just `dash_viewer.sh` |
| `read -t` works on PW4 busybox | **Use `read -r -t 1 tap_line <&3`.** It works on this Kindle. Do NOT replace with background-reader-subshell workarounds — that was the worst bug of the postmortem session (race condition → infinite restart loop). |
| `if ! fetch_view` works on PW4 busybox | Globals propagate correctly. Do NOT rewrite as `fetch_view; if [ $? -ne 0 ]` — the `!` pattern works on this Kindle's busybox. |
| FIFO EOF spins CPU at 100% | When touch_tap dies, `read` returns EOF (empty string) in a tight loop. Detect EOF and restart the helper |
| No cleanup on SIGTERM | Orphaned children, fd3, FIFO, flag files. Add `trap cleanup INT TERM` |
| `killall` unreliable on busybox | Process comm may not match script name. Use PID file: `echo $$ > file.pid` |
| `gettimeofday` debounce breaks on NTP | Clock jumps after wake. Use `clock_gettime(CLOCK_MONOTONIC)` |
| View server path traversal | `/images/../../etc/passwd` reads arbitrary files. Sanitize filename against `[a-zA-Z0-9_\-.]+` **and** resolve the target path against a base dir resolved once at startup (not per-request) — compare resolved parent, not `startswith` on the literal string. |
| Taps on empty space trigger a button anyway (confirmed on hardware, 2026-07-31) | `hit_test()`'s "try rotated/mirrored coordinates" fallback (for hardware where touch axes don't match screen axes) fires on ANY miss, and an empty-space tap can mirror straight into a real button's rectangle. On PW4 touch and screen axes always match — every direct hit test in the logs is correct. **Removed the fallback entirely.** Only add coordinate-rotation logic back if you have a specific Kindle model that demonstrably reports rotated coordinates — don't carry it as defensive code. |
| Unstripped `touch_tap` leaks build path | Compiling without `-s` embeds the absolute source path (incl. local username) in `debug_info`, recoverable via `strings touch_tap`. Always cross-compile with `-s`. macOS `strip` cannot fix this after the fact — it doesn't handle foreign ARM/Linux ELF binaries, silently no-ops ("can't process non-object and non-archive file"). Must rebuild from source with `-s`. |
| `killall -9 curl` kills unrelated curls | Check `/proc/$pid/cmdline` for server port before killing |
| **WiFi not ready after USB eject** | `sleep 3` is not enough — the Kindle needs 5-15s to reconnect WiFi after USB eject. Use `wait_for_network()` that pings 1.1.1.1 up to 30s before fetching. |
| **No exit path when fetch fails + no cached view** | Dashboard shows error and user is stuck. Always auto-exit after a timeout if there's no cached view to fall back to. |
| **macOS `/tmp` resolves to `/private/tmp`** | Python `Path("/tmp/x").resolve()` returns `/private/tmp/x`. Any path-containment check (`startswith`) must compare against the *resolved* base path, not the literal string. |
| **the agent venv PYTHONPATH leaks into system Python** | `/usr/bin/python3` (Python 3.9) picks up the the agent venv's PIL (compiled for 3.11) via `PYTHONPATH` → `ImportError: _imaging`. Not a broken PIL — version mismatch. Run servers with the venv's Python directly. |
| **KUAL `exitmenu: true` closes KUAL before script runs** | `exitmenu: true` causes KUAL to exit to the Kindle home screen BEFORE the dashboard script starts. User sees: home screen flash → blank → "cannot reach server". The script needs KUAL's process context to launch correctly. Keep `exitmenu: false` — KUAL stays open behind the dashboard. |
| **KUAL behind dashboard picks up touch (touch-through)** | When `exitmenu: false`, KUAL stays open behind the dashboard image. The Kindle framework reads touch from the same evdev device and passes events to KUAL's UI. Taps on the dashboard image ALSO hit invisible KUAL menu items underneath. This is NOT an EVIOCGRAB problem — it's the framework's input pipeline. The old `touch_tap` binary with EVIOCGRAB prevents the framework from receiving events — the grab must succeed. If EVIOCGRAB fails ("Resource busy"), something else holds the grab — kill the previous `touch_tap` first (`killall touch_tap; sleep 1`). Do NOT change `exitmenu` to `true` to fix this — it breaks the launch entirely. |
| **Touch helper restart loop** | EVIOCGRAB fails with "Resource busy" (framework holds the grab), touch_tap exits, EOF detected, restart fires immediately → infinite loop at ~1/sec flooding log. Add max-retry counter (5 attempts with 3s delay), then give up gracefully and display-only. |
| **Stale Kindle cache between sessions** | Old `.png`/`.json` files from a previous session persist in `/mnt/us/documents/kindle-dash/`. The dashboard fetches but displays stale content if the fetch partially fails. Clear cache on every deploy: `rm -f *.png *.json *.tmp touch_fifo viewer.pid` |
| FIFO write-before-read (SIGPIPE) | The v4 working code starts touch_tap before opening fd3. `touch_tap` blocks on `open()` until the reader attaches. This ordering works — do not change it without testing on hardware. |
| `nb_read_tap` EOF false positive — DO NOT USE | The `nb_read_tap` background-reader workaround was the worst bug of the postmortem session. `read -t` works on this Kindle — use it directly. The workaround's race conditions caused infinite touch helper restart loops. |
| **FIFO recreation invalidates fd3** | `restart_touch_helper` does `rm -f` + `mkfifo` but old fd3 is on the deleted inode. Reads on stale fd3 fail or return EOF. Fix: `exec 3<&-` then `exec 3<` after recreating the FIFO. |
| **EVIOCGRAB not released on exit** | `cleanup()` kills touch_tap with SIGTERM but doesn't wait. Kernel may delay grab release. Kindle framework never gets touch back after dashboard exits. Fix: SIGTERM → wait 1s → SIGKILL → `killall touch_tap` as fallback. |
| **Direct `cp` to blanket screensaver dir is volatile** | `/usr/share/blanket/screensaver/` is a **tmpfs** (RAM-backed, 4MB) — the framework regenerates stock images on every boot. A direct `cp` works for the current session but is lost on reboot. **Fix: use the linkss hack** — it bind-mounts a persistent directory (`/mnt/us/linkss/screensavers/`) over the tmpfs path via an upstart job that runs before the framework starts. Install linkss via MRPI, drop your PNG into `/mnt/us/linkss/screensavers/`, restart the framework. |
| **linkss install fails: `xzdec: not found`** | On FW 5.16+ (not just 5.17+ as forum posts suggest — confirmed on PW4 5.16.7), the linkss `.bin`'s `xzdec` binary can't find `/lib/ld-linux.so.3`. MRPI log shows `./xzdec: not found` + `tar: short read`. **Fix:** create the symlink via a KUAL script (`mntroot rw && ln -s /lib/ld-linux-armhf.so.3 /lib/ld-linux.so.3 && mntroot ro`), then re-run `KUAL → Helper → Install MR Packages`. Check MRPI log at `/mnt/us/extensions/MRInstaller/log/mrinstaller.log` (via USB: `/Volumes/Kindle/extensions/MRInstaller/log/mrinstaller.log`). |
| **linkss runtime binaries also need the linker symlink** | ALL linkss runtime binaries (`convert`, `identify`, `fbink`, `mobitool`) are dynamically linked with `interpreter /lib/ld-linux.so.3`. If the symlink is missing, these silently fail. Symptoms: framework restart hangs at the load screen (user must hard-reboot), "No new images to process" even though images exist, default screensavers still showing after restart. Verify the symlink exists before any linkss operation — it's permanent once created. |
| **Stale lock screen time after wake (overlay approach only)** | The lock screen PNG was rendered before sleep, so the clock is wrong when the Kindle sleeps again later. **Only relevant for overlay approach.** Native replacement uses a static image — no stale time issue. |
| **Don't create scripts for simple file copies** | the developer prefers the simplest approach. When asked "is that script needed? or you can just push the image to the kindle with no script?" — the answer was no script needed. Just `cp bg_ss0.png /Volumes/Kindle/linkss/screensavers/bg_ss00.png` via USB. The only action that needs a KUAL button is the framework restart (which linkss already provides). Don't write install scripts for one-shot file operations. |
| **Don't reinvent what works for others** | When a proven community hack exists (linkss for screensavers), use it rather than building a custom alternative (manual bind-mount + upstart job). The community solution handles edge cases you'll only discover the hard way. the developer explicitly pushed back on a custom bind-mount approach: "lets not try to reinvent what works for others. there must be a way to do it the way you found online." |
| **Recognize when a feature isn't worth pursuing** | After multiple failed attempts at custom screensavers (overlay flash, direct tmpfs copy, linkss unsupported on 5.16.7, manual bind-mount), the developer said "custom screensaver is not a need for the project. does not matter." Don't sunk-cost a feature — if it's not a requirement and the path forward is risky (firmware downgrade), abandon it. The dashboard works fine without custom screensavers. |
| **linkss 0.25.N is UNSUPPORTED on FW 5.16.x+** | NiLuJe (original author) confirmed on MobileRead t=195474 #2989: linkss is "not supported on FW version with native custom screensaver support (and that was, like 5.12 or even earlier)." The installer lacks a FW version check so it "succeeds" but the bind-mount conflicts with Amazon's native screensaver system introduced ~FW 5.12. Symptoms on 5.16.7: default screensavers still showing, custom image appearing once then reverting, cycling modes broken, framework restart freezes. **Use direct FBInk or KOReader Sleep Screen instead.** |
| **"Display Cover" / "Show covers on lock screen" setting overrides linkss** | On FW 5.16+, the Kindle has a native "Display Cover" setting (Settings → Device Options → Display Cover). When enabled, the framework actively writes book covers to the screensaver dir — **overriding any bind-mounted content**. This is the ONLY mode where linkss's bind-mount could theoretically work: "Image Cycle" / stock images / OFF. Even then, the framework may re-mount tmpfs after linkss's upstart job. The jcs.org Kindle Scribe guide confirms: "Make sure the 'Show covers on lock screen' option is disabled." |
| **KUAL "Restart framework now" freezes on FW 5.16+** | Known, widely-reported issue on FW 5.16+/5.17+. KUAL's stop/start framework command leaves the device half-initialized — frontlight stuck on, no PIN dialog, power button unresponsive. **Workaround:** never use KUAL's restart — use the Kindle's own Menu → Settings → Menu → Restart, or do a full device reboot (hold power 15s → release → press to boot). The upstart job runs cleanly on full boot. (MobileRead t=195474 #3037) |
| **linkss `staging/` vs `screensavers/` directory** | linkss has a `/mnt/us/linkss/staging/` directory for processing new images. "Process staging images" in KUAL only processes files in `staging/`, not `screensavers/`. If your image is already correctly named (`bg_ss00.png`) in `screensavers/`, the staging processor will say "no new images to process" — this is expected. The file in `screensavers/` should work IF the bind-mount is active. |
| **linkss `mounted_ss` sentinel ≠ active bind-mount** | The `/mnt/us/linkss/mounted_ss` file (0 bytes) is a sentinel linkss creates when it *believes* the mount succeeded — but its existence does NOT guarantee the mount is actually active. Verify via `cat /proc/mounts \| grep blanket` (should show bind mount, not tmpfs) and compare inodes: `stat -c '%i' /mnt/us/linkss/screensavers/bg_ss00.png` vs `stat -c '%i' /usr/share/blanket/screensaver/bg_ss00.png` (should match if bind-mount is active). |
| **linkss `autoreboot` flag causes framework restart hangs** | After linkss install, the `autoreboot` flag (`/mnt/us/linkss/autoreboot`) is set by default. When you do `KUAL → Screen Savers → Restart framework now`, the framework hangs at the load screen — user must hard-reboot (hold power 15s). **Fix:** remove the flag before restarting: `rm /mnt/us/linkss/autoreboot` (via USB at `/Volumes/Kindle/linkss/autoreboot`). Then use a **full Kindle reboot** (Settings → Menu → Restart) instead of framework restart — the upstart job runs cleanly on full boot and the bind-mount succeeds. |
| **Full Kindle reboot recovers from framework restart hang** | When `KUAL → Screen Savers → Restart framework now` hangs at the load screen, don't hold power to force-off and retry the same restart — it'll hang again. Instead, do a **full reboot** (Settings → Menu → Restart, or if already frozen, hold power 15s to force-off, then press power to boot). The linkss upstart job (`start on starting framework`) runs during a full boot and the bind-mount succeeds. Framework restart skips the upstart job's `start on starting framework` trigger. |
| **Don't create scripts for simple file copies** | the developer prefers the simplest approach. When asked "is that script needed? or you can just push the image to the kindle with no script?" — the answer was no script needed. Just `cp bg_ss0.png /Volumes/Kindle/linkss/screensavers/bg_ss00.png` via USB. The only action that needs a KUAL button is the framework restart (which linkss already provides). Don't write install scripts for one-shot file operations. |

## Starting the Server (Mac)

```sh
# Start view server — use the correct Python!
# If the agent venv PYTHONPATH is set, bare `python3` picks up the venv's PIL
# which is compiled for a different Python version → ImportError: _imaging
# Use the venv's Python explicitly:
$HOME/.the agent/the agent-agent/venv/bin/python3 view_server.py

# Or clear PYTHONPATH if using system Python:
# PYTHONPATH="" /usr/bin/python3 view_server.py  (but system Python may lack PIL)

# Verify
curl http://localhost:8888/health
curl http://localhost:8888/view?path=home
```

## Zig Installation

Zig is the easiest cross-compiler for Kindle ARM. Install to `/tmp`:

```sh
# Zig 0.13.0 (proven working for touch_tap.c)
curl -sL https://ziglang.org/download/0.13.0/zig-macos-aarch64-0.13.0.tar.xz -o /tmp/zig.tar.xz
cd /tmp && tar xf zig.tar.xz
# Binary at: /tmp/zig-macos-aarch64-0.13.0/zig

# Cross-compile
/tmp/zig-macos-aarch64-0.13.0/zig cc -target arm-linux-musleabi -O2 -static -o touch_tap touch_tap.c
```

Note: Zig download URL pattern varies by version. Check https://ziglang.org/download/ for the current URL format.
