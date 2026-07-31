---
name: kindle-eink-dashboard
description: Build server-driven e-ink dashboards on a jailbroken Kindle. An MCP server (or a minimal Python HTTP server) renders PNG + JSON tap maps, a Kindle shell viewer displays via eips, a C touch helper reads evdev. Proven on Kindle Paperwhite 4.
version: 2.0.0
author: Pluton Mac & Claude
metadata:
  hermes:
    tags: [kindle, e-ink, dashboard, mcp, cross-compile, arm]
---

# Kindle E-Ink Dashboard

Build a server-driven e-ink dashboard on a jailbroken Kindle. The Kindle is a dumb display — a server generates PNG images + JSON tap maps, the Kindle fetches and displays them. A tiny C touch helper reads evdev input for tap navigation. See the repo's top-level `README.md` for the full setup path (jailbreak → deploy the KUAL extension → run the MCP server → connect an agent) and `mcp_server/README.md` for the server's own tool/config reference — this file is operational knowledge: hard-won pitfalls and protocol details worth knowing before you touch the Kindle-side code.

## Code Review and Bug Fixing Workflow

**Do not fix working shell/C code on this Kindle without testing on hardware first.** A code review once found 20+ "bugs" in the shell script — busybox `read -t`, `!` subshell semantics, `local` keyword — that were theoretical: they existed in the code but the runtime paths never hit them, so the dashboard worked despite them. "Fixing" all of them in one batch introduced real bugs (a race condition causing an infinite touch-helper restart loop, a path-traversal fix that broke every image request because of a macOS `/tmp` → `/private/tmp` resolution mismatch, and a KUAL config change that broke the launch path entirely) and required a full revert to recover.

**The pattern that kills:** review finds theoretical bugs → "fix all" → batch of N fixes → deploy → something breaks → can't tell which fix caused it → patch on top of patch → system is now worse than before any fixes.

**Rules for Kindle shell/C changes:**
1. **Test every change on hardware** — `sh -n` syntax checking is not enough. Busybox ash, FIFO behavior, and LIPC event timing can only be verified on-device.
2. **One fix at a time** — deploy, test, confirm working, then the next fix. Never batch multiple fixes into one deploy.
3. **Keep the working version** — copy the working file to `.bak` before editing; there's no git on the Kindle itself.
4. **Theoretical bugs < working code** — a bug that exists in code but doesn't manifest in the current execution path is lower priority than anything that actively breaks the user experience.
5. **Don't fix what you can't test on hardware.**
6. **If asked to "fix all" issues from a review of working code, push back** — name the 2-3 that actually matter and confirm before batching the rest.
7. **If 3+ fixes in a row make things worse, stop and revert everything**, then re-approach one fix at a time.
8. **Never recompile a working `touch_tap` binary** without a specific, demonstrated bug in the binary itself — "improvements" (EVIOCGRAB error handling, a different clock source) have broken working touch behavior before.

## Architecture

```
Server (MCP or plain HTTP)   Kindle (shell + C)
┌──────────────┐            ┌──────────────────┐
│ View render   │  HTTP LAN  │ dash_interactive.sh│
│ (Pillow PNG)  │───────────▶│ • curl fetch PNG   │
│ + tap map JSON│            │ • eips -f -g display│
└──────────────┘            │ • awk parse taps    │
                            │ • hit test → navigate│
                            └──────┬─────────────┘
                                   │ FIFO pipe: "x y\n"
                            ┌──────┴─────────────┐
                            │ touch_tap (C, ~50ln)│
                            │ • EVIOCGRAB         │
                            │ • evdev /dev/input  │
                            │ • prints tap coords │
                            └────────────────────┘
```

## Target Hardware

**Proven on:** Kindle Paperwhite 4 (10th Gen, 2018) — 1072×1448, 300 PPI, 8-bit grayscale, capacitive touch, WiFi (2.4GHz only), jailbroken with WinterBreak + KUAL.

**Other Kindle models:** the MCP server (`mcp_server/`) is hardware-agnostic — screen dimensions are an env var, not a constant. The Kindle-side viewer is not yet proven portable: `touch_tap` is a precompiled 32-bit ARM binary tuned around this specific device's driver behavior (see Touch Helper section below), and `dash_interactive.sh`'s busybox-ash and LIPC-event assumptions were verified empirically on this exact firmware. Porting to a different model means re-verifying those assumptions on your own hardware, not just recompiling.

## Cross-Compiling C for Kindle

Install Zig, cross-compile a static ARM binary:

```sh
curl -sL https://ziglang.org/download/0.13.0/zig-macos-aarch64-0.13.0.tar.xz -o /tmp/zig.tar.xz
cd /tmp && tar xf zig.tar.xz

# -s strips debug symbols — always use it, an unstripped binary embeds your
# local build path (incl. username) recoverable via `strings touch_tap`
/tmp/zig-macos-aarch64-0.13.0/zig cc -target arm-linux-musleabi -O2 -static -s -o touch_tap touch_tap.c

file touch_tap  # ELF 32-bit LSB executable, ARM, EABI5, statically linked, stripped
```

## KUAL Extension Structure

```
/mnt/us/extensions/kindle-dash/
├── config.xml    ← Must use <information> + <menus> tags (NOT <about>/<mainmenu>)
├── menu.json     ← KUAL menu items
└── bin/
    ├── dash_interactive.sh
    ├── touch_tap              ← ARM static binary
    ├── show_static.sh         ← Display a pre-cached PNG
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

`exitmenu: false` is required — `true` closes KUAL before the script starts, which breaks the launch (the script needs KUAL's process context).

## Deploying to Kindle

```sh
cp -r kindle/ /Volumes/Kindle/extensions/kindle-dash/
chmod +x /Volumes/Kindle/extensions/kindle-dash/bin/*

# CRITICAL: clean macOS resource fork files — they break KUAL
find /Volumes/Kindle/extensions/kindle-dash -name '._*' -delete
```

## Touch Helper (touch_tap.c)

Key implementation details:

1. **Scan `/dev/input/event0..15`** — don't hardcode the event number, it changes between boot modes.
2. **Use `EVIOCGABS(ABS_X)` and `EVIOCGABS(ABS_MT_POSITION_X)`** to detect touch devices.
3. **Handle a 0-0 EVIOCGABS range:** this Kindle reports `x:0-0 y:0-0` — the driver outputs raw pixel coordinates directly. The scale function must clamp, not divide by zero. A different device's driver may report a real range and need actual scaling — verify on your hardware.
4. **`EVIOCGRAB` for exclusive access** — prevents the Kindle framework from also receiving touches (without it, taps on the dashboard image can also hit invisible KUAL menu items underneath).
5. **700ms debounce** — e-ink refresh is slow; rapid taps cause confusion.
6. **Output: `printf("%d %d\n", x, y)` on tap release** — line-buffered stdout.
7. **32-bit ARM struct size:** `struct input_event` is 16 bytes (not 24, as on 64-bit). `timeval` is 4+4=8 bytes on ARM EABI5.
8. **Use `clock_gettime(CLOCK_MONOTONIC)` for debounce** — `gettimeofday` breaks when NTP syncs after wake (the clock jumps). Monotonic is immune.
9. **No SYN_REPORT tap emission** — `SYN_REPORT` can fire with stale coordinates if the touch sequence doesn't use `BTN_TOUCH`. Only emit taps on `BTN_TOUCH` release or `ABS_MT_TRACKING_ID=-1`.

## Shell Viewer (dash_interactive.sh)

Key patterns, all verified on-device — don't "fix" these without hardware testing (see Code Review workflow above):

1. **No `jq` on Kindle** — use `awk` for JSON parsing. The awk parser extracts x/y/w/h/action/target from each tap block, scanning line by line.
2. **No usable `python3` on Kindle** — a `python3` binary may exist but fail on JSON. Use awk.
3. **FIFO pipe for touch input:** `mkfifo`, start the touch helper (it blocks on `open()` until a reader attaches), then open fd3 for reading (`exec 3< "$TOUCH_FIFO"`). This ordering matters — don't reorder without testing on hardware.
4. **`read -t` works on this Kindle's busybox ash** — `read -r -t 1 tap_line <&3` works correctly despite looking unsupported in some busybox builds. Do not replace it with a background-reader-subshell workaround — that pattern caused the worst bug encountered on this project: a race condition producing false EOF detections and an infinite touch-helper restart loop.
5. **`if ! fetch_view` works on this busybox** — globals propagate correctly; `!` does not fork a subshell here. Don't rewrite as `fetch_view; if [ $? -ne 0 ]`.
6. **Atomic downloads:** curl to `.tmp`, then `mv` to the final name.
7. **Trap handler for cleanup:** `trap cleanup INT TERM` with a `cleanup()` that kills children, closes fd3, removes the FIFO/flag files/PID file. Without it, SIGTERM orphans everything.
8. **PID file for stop.sh:** `echo $$ > "$PID_FILE"` at startup — `killall` may not match the process comm reliably on busybox.
9. **Exit action:** kill the touch helper and power watcher, remove FIFO/flags, relaunch the Kindle home screen. No `preventScreenSaver` set/restore needed (see Power Lifecycle below — it's never used):
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

**Load-bearing formatting detail:** the shell's awk parser scans this JSON *line-by-line* and expects each field and each tap object's closing `}` on its own line. A server must pretty-print (`indent=2` in Python) — compact single-line JSON parses without error but silently breaks every tap (they just never hit). `mcp_server/src/kindle_dash_mcp/http_server.py`'s `_json()` method has this as a load-bearing comment for exactly this reason.

## Serving the protocol

`mcp_server/` (see its own `README.md`) is the reference server: an MCP server that any number of MCP-capable agents push data to, which renders this protocol via Pillow and serves it over HTTP. If you just want a minimal standalone server without MCP, the same protocol applies — the requirements are: `Image.new("L", (width, height), 255)` for 8-bit grayscale PNGs, a Content-Length header on image responses, filename sanitization on `/images/<name>` against `[a-zA-Z0-9_\-.]+` plus a resolved-path containment check (reject `../` traversal), and `json.dumps(..., indent=2)` per the note above.

## MCP Server (multi-agent dashboard)

`mcp_server/` is a generalized MCP server — not tied to any one agent framework, usable by anyone with a Kindle and an MCP-capable agent. The "agent newspaper" model: each agent gets a designated card slot on the home view (stable, first-registration order, persisted to disk) and a namespaced view tree (`sports/readiness`, `life/habits`, ...). Agents are data pushers — they call `update_view(path, {type: "metric_dashboard", ...})` and the server renders via builtin Pillow renderers per view type.

**Key design decisions:**
- **Typed view types (not freeform text or a widget DSL):** 5 built-in types in `mcp_server/src/kindle_dash_mcp/renderers.py` — `status_grid`, `metric_dashboard`, `text_list`, `chart_view`, `progress_view`. Agents pick a type and pass matching structured data; they never touch Pillow.
- **No polling:** the Kindle fetches on interaction only (tap, refresh, wake). E-ink holds the image when idle.
- **Stdio MCP, HTTP as a background thread:** agent-managed subprocess. PNGs + view/registry metadata persist to disk (`store.py`) and survive process restarts — the Kindle's offline cache covers the gap while no agent is connected.
- **No custom renderers:** built-in types only. A new type is a code change to `renderers.py`'s `RENDERERS` dict.
- **Home view = dynamic grid of agent slots:** `push_home_card(agent_id, title, summary, nav_target)`. Slot assignment is stable (first-registration order, persisted) — any number of agents can register. Beyond `KINDLE_DASH_HOME_MAX_CARDS` (default 8), extras collapse into a "+N more" tile linking to an auto-generated `system/agents` overview.
- **Env-driven, not hardcoded to one Kindle:** screen dimensions, HTTP port, and data dir are all env vars (`KINDLE_DASH_WIDTH`/`HEIGHT`/`PORT`/`DATA_DIR`) — defaults match the Paperwhite 4, but nothing assumes it.

See `mcp_server/README.md` for install/config/tool docs (including Hermes Agent setup) and `mcp_server/src/kindle_dash_mcp/` for the implementation.

## Power Button Sleep/Wake Lifecycle

The dashboard sleeps when the power button is pressed (Kindle native screensaver → deep sleep) and wakes back to the dashboard when pressed again. The shell process survives deep sleep — it freezes and resumes on wake without restarting.

### Critical: `preventScreenSaver` — do not use for interactive viewers

Do NOT set `preventScreenSaver 1` in the interactive viewer. It blocks the power button's `goingToScreenSaver` LIPC event entirely — sleep detection never fires and the lifecycle breaks. The working code doesn't use `preventScreenSaver` anywhere; the Kindle sleeps naturally on power-button press or timeout.

A simple display-only loop with no sleep/wake handling *may* use `preventScreenSaver 1` to avoid timeout sleep — that's a different use case from the interactive dashboard.

### Architecture: separate channels, not a shared FIFO

Two processes writing to the same FIFO causes line interleaving/corruption — e.g. `goingToScreenSaver 2` can split into `r 2`, misread as a tap coordinate that navigates to a random page. Use separate channels:

```
touch_tap (C binary)   → writes "x y\n" to TOUCH_FIFO (fd3)     ← touch taps only
power watcher (subsh)  → creates flag files on LIPC events       ← power events only
                         .sleep_flag  (goingToScreenSaver)
                         .wake_flag   (outOfScreenSaver)
main loop              → reads TOUCH_FIFO via `read -r -t 1 <&3`
                       → polls `.sleep_flag` existence each iteration
```

The power watcher runs `lipc-wait-event` and writes flag files via `touch`, NOT `echo` to the FIFO — `echo` inside a piped subshell doesn't reach the FIFO reliably in busybox.

### Critical: do not kill touch_tap during sleep

Killing `touch_tap` on sleep and restarting it on wake breaks swipe-to-unlock — the restarted process re-grabs `EVIOCGRAB` before the user finishes swiping. Instead, leave it running: a frozen process can't read events, so `EVIOCGRAB` on a frozen process is effectively released, and the Kindle framework handles swipe-to-unlock naturally.

### Critical: drain phantom taps after wake

`touch_tap` freezes during sleep, resumes with the device, and reads buffered evdev events from the swipe-to-unlock gesture — it reports the release point as a tap, which (without draining) navigates to a random page immediately after wake:

```sh
drain_until=$(($(date +%s) + 2))
while [ "$(date +%s)" -lt "$drain_until" ]; do
    read -r -t 1 drain_line <&3 2>/dev/null && log "Drained: $drain_line"
done
```

### Three LIPC pitfalls

1. **Event names must be comma-separated**: `goingToScreenSaver,outOfScreenSaver` — space-separated prints usage and exits.
2. **No `echo` to FIFO in a piped subshell**: use flag files (`touch $SLEEP_FLAG`) instead.
3. **Don't share the FIFO with `lipc-wait-event`**: even direct-write (no echo) causes corruption — separate channels.

## Pitfalls Discovered

| Pitfall | Fix |
|---|---|
| `preventScreenSaver 1` blocks power button sleep | Do NOT use it for interactive viewers — it blocks the power button's `goingToScreenSaver` event entirely, so sleep detection never fires. |
| `lipc-wait-event` events space-separated | Must be comma-separated: `goingToScreenSaver,outOfScreenSaver`. |
| `echo` in piped subshell doesn't reach FIFO | Use flag files (`touch $SLEEP_FLAG`) instead — the main loop polls for file existence. |
| Shared FIFO corrupts lines (touch + power) | Use separate channels: touch taps via FIFO, power events via flag files. |
| Killing touch_tap on sleep breaks swipe-to-unlock | Leave it running — EVIOCGRAB on a frozen process is effectively released. |
| Phantom tap on wake (navigates to random page) | Drain the FIFO for 2 seconds after displaying home on wake. |
| Screen ghosts through screensaver on repeated sleep cycles | `eips -c` (clear to white) before sleep. |
| Wake returns to wrong page | Always fetch `home` on wake, not the last-viewed path. |
| KUAL doesn't show the extension | Use `<information>`/`<menus>` in config.xml, not `<about>`/`<mainmenu>`. |
| `._` files break KUAL | `find ... -name '._*' -delete` after every copy. |
| `jq` not on Kindle | Use `awk` for JSON parsing. |
| `python3` fails silently on Kindle | Don't use python3 on Kindle — pure awk. |
| Touch EVIOCGABS returns 0-0 range | This Kindle reports raw pixel coords — clamp, don't scale. Verify on other hardware before assuming. |
| `eips -c` on exit leaves white screen | Use `lipc-set-prop com.lab126.appmgrd start app://com.lab126.booklet.home` instead. |
| 2.4GHz WiFi only | Ensure the AP broadcasts a 2.4GHz SSID. |
| `stop.sh` doesn't kill power watcher | Kill `lipc-wait-event` and `dash_interactive.sh` too, not just the display loop. |
| `read -t` works on this Kindle's busybox | Use `read -r -t 1 tap_line <&3` directly — see Shell Viewer section above. |
| `if ! fetch_view` works on this busybox | Don't rewrite as `fetch_view; if [ $? -ne 0 ]` — see Shell Viewer section above. |
| FIFO EOF spins CPU at 100% | When touch_tap dies, `read` returns EOF in a tight loop — detect EOF and restart the helper (with a retry cap). |
| No cleanup on SIGTERM | Orphaned children, fd3, FIFO, flag files — add `trap cleanup INT TERM`. |
| `killall` unreliable on busybox | Process comm may not match the script name — use a PID file (`echo $$ > file.pid`). |
| `gettimeofday` debounce breaks on NTP | Clock jumps after wake — use `clock_gettime(CLOCK_MONOTONIC)`. |
| View server path traversal | `/images/../../etc/passwd` reads arbitrary files. Sanitize the filename against `[a-zA-Z0-9_\-.]+` **and** resolve the target path against a base dir resolved once at startup — compare the resolved parent, not `startswith` on the literal string. |
| Taps on empty space trigger a button anyway | A coordinate-mirroring fallback (meant for hardware where touch/screen axes don't match) can fire on any miss and mirror an empty-space tap straight into a real button's rectangle. On hardware where axes always match, remove the fallback entirely — don't carry it as defensive code unless you've demonstrated a device that needs it. |
| Unstripped `touch_tap` leaks the build path | Compiling without `-s` embeds the absolute source path (incl. local username) in debug info, recoverable via `strings touch_tap`. macOS `strip` cannot fix this after the fact for a foreign ARM/Linux ELF binary — rebuild from source with `-s`. |
| Kernel TUN networking may not work on your firmware | Verify empirically via SSH before assuming — on this Kindle's firmware, `tailscaled` in kernel-TUN mode failed to start against an existing `/dev/net/tun` node. Userspace-networking + an explicit SOCKS5/HTTP proxy is the fallback that works everywhere; route `curl` through `--proxy http://localhost:<port>`. |
| Killing `tailscaled` drops your own Tailscale SSH session | `tailscale up --ssh` runs the SSH server *inside* `tailscaled` — restarting the daemon (including your own script's proxy bring-up) severs the SSH connection you're using to run it. Make daemon bring-up idempotent (skip the restart if already healthy). |
| USB mass-storage mode kills all Kindle background processes | Confirmed empirically — connecting via USB suspends `tailscaled`, the dashboard script, and `touch_tap`, and none resume on their own after eject. Everything needs restarting via KUAL after any USB session. |
| Touch grab held during a slow startup can break swipe-to-unlock | `touch_tap` grabs the touchscreen early in startup, before sleep/wake handling is running. If the screen times out during any blocking pre-main-loop work (e.g. a network wait), the framework never gets touch back. Recovery: kill the orphaned `touch_tap` (the grab releases automatically). Mitigation: keep any blocking startup work bounded and short — rely on cache fallbacks rather than blocking for full readiness. |
| `killall -9 curl` kills unrelated curls | Check `/proc/$pid/cmdline` for the server port before killing. |
| WiFi not ready immediately after USB eject | A fixed few-second sleep isn't enough — reconnection can take 5-15s. Poll a reachability check (e.g. ping) with a real timeout before fetching. |
| No exit path when fetch fails and there's no cached view | The dashboard would get stuck showing an error. Always auto-exit after a timeout if there's no cached view to fall back to. |
| macOS `/tmp` resolves to `/private/tmp` | Any path-containment check must compare against the *resolved* base path, not the literal string, or it silently always fails. |
| A venv's PYTHONPATH can leak into an unrelated system Python | If `PYTHONPATH` points at one Python's site-packages (e.g. a venv's Pillow build), invoking a *different* Python version picks it up and fails with a binary-incompatible import error. Not a broken install — a version mismatch. Invoke the correct interpreter explicitly rather than relying on a bare `python3`. |
| KUAL `exitmenu: true` closes KUAL before the script runs | The script needs KUAL's process context to launch correctly — keep `exitmenu: false`. |
| KUAL behind the dashboard picks up touch (touch-through) | With `exitmenu: false`, taps on the dashboard image can also hit invisible KUAL menu items underneath, via the framework's shared input pipeline (not an EVIOCGRAB problem). The touch helper's EVIOCGRAB prevents this — if it fails ("Resource busy"), something else holds the grab; kill any previous `touch_tap` first. |
| Touch helper restart loop | EVIOCGRAB failing with "Resource busy" can trigger EOF → restart → EOF → restart at ~1/sec. Add a max-retry counter with backoff, then give up gracefully to display-only. |
| Stale Kindle cache between sessions | Old `.png`/`.json` files from a previous session can persist and get served if a later fetch partially fails. Clear the cache on every deploy. |
| FIFO write-before-read (SIGPIPE) | Start the touch helper before opening fd3 for reading — it blocks on `open()` until the reader attaches. Don't reorder without testing on hardware. |
| FIFO recreation invalidates fd3 | Recreating the FIFO (`rm` + `mkfifo`) leaves an existing fd3 pointed at the deleted inode. Close and reopen fd3 (`exec 3<&-` then `exec 3<`) after recreating it. |
| EVIOCGRAB not released promptly on exit | `SIGTERM` alone may not release the grab immediately — send it, wait briefly, then `SIGKILL` as a fallback so the Kindle framework reliably gets touch back. |

## Zig Installation

Zig is the easiest cross-compiler for Kindle ARM. Install to `/tmp`:

```sh
# Zig 0.13.0 (proven working for touch_tap.c)
curl -sL https://ziglang.org/download/0.13.0/zig-macos-aarch64-0.13.0.tar.xz -o /tmp/zig.tar.xz
cd /tmp && tar xf zig.tar.xz
# Binary at: /tmp/zig-macos-aarch64-0.13.0/zig

# Cross-compile
/tmp/zig-macos-aarch64-0.13.0/zig cc -target arm-linux-musleabi -O2 -static -s -o touch_tap touch_tap.c
```

Note: the Zig download URL pattern varies by version — check https://ziglang.org/download/ for the current format.
