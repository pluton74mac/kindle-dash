# Kindle Viewer Implementation: C vs Shell (curl+eips)

> **Status:** Decision analysis. Synthesized from all wiki research files. Informs the AGENTS.md technical decision.

## Context

The Kindle viewer is the write-once component that lives on the device. It must:
1. Fetch a PNG image + JSON tap map from the Mac view server
2. Display the PNG on the e-ink screen
3. Listen for touch events and route taps to navigation actions
4. Handle sleep/wake lifecycle (detect wake, auto-refresh, idle timeout)
5. Cache last-good view for offline fallback
6. Survive reboots, WiFi drops, and server outages gracefully

Two approaches compete: **C binary** (like kdashboard) and **Shell script** (curl + eips + shell-native touch reading).

---

## Comparison Matrix

| Dimension | C Binary | Shell (curl + eips) |
|---|---|---|
| **Reliability** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| **Ease of implementation** | ⭐⭐ | ⭐⭐⭐⭐⭐ |
| **Rendering speed** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| **Touch handling** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ |
| **Expandability** | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| **Power efficiency** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| **Debuggability** | ⭐⭐ | ⭐⭐⭐⭐⭐ |
| **Maintenance burden** | ⭐⭐ | ⭐⭐⭐⭐⭐ |
| **Binary distribution** | ⭐⭐ (cross-compile) | ⭐⭐⭐⭐⭐ (text file) |
| **Sleep/wake handling** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| **Offline cache** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ |

---

## 1. Reliability

### C Binary

**Strengths:**
- Single process, no shell quoting bugs, no subprocess failures
- Direct mmap to `/dev/fb0` — no dependency on `eips` behavior across firmware versions
- kdashboard proves the pattern works in production (error recovery, SSE reconnection, atomic cache writes)
- Memory management is explicit — can handle edge cases (partial downloads, corrupt JSON, malloc failures)
- Touch events via `EVIOCGRAB` — exclusive access, no race with Kindle framework
- Can implement atomic file operations, retry logic, and progressive backoff in-process

**Weaknesses:**
- Memory leaks or segfaults kill the dashboard silently — no shell error output
- Binary incompatibility with future firmware updates (ABI changes)
- If the binary crashes, KUAL doesn't auto-restart unless wrapped in a shell loop

### Shell (curl + eips)

**Strengths:**
- Every command's exit code is checkable — `curl` failing, `eips` failing, `jq` failing all produce detectable errors
- Shell scripts are inherently self-documenting — `set -e` + `set -x` for debugging
- No segfaults possible — worst case is a command fails and the script catches it
- Can use `jq` for JSON parsing (if available) or fall back to `grep`/`sed` patterns
- homecircuits.eu project proves shell-based image-push with full error recovery works in production:
  - `while true` loop with progressive ping backoff
  - Atomic downloads (`.tmp` → rename)
  - Error counter → auto-reboot after 10 consecutive failures
  - Battery level check → low-battery image
  - Gateway route restoration after sleep

**Weaknesses:**
- Shell quoting is fragile — URL parameters, JSON values, file paths with spaces can break
- Subprocess overhead: each `curl`, `eips`, `cat`, `jq` is a fork+exec
- No exclusive touch grab — Kindle framework may also receive touch events, causing unexpected UI responses
- Signal handling is limited — `trap` works but is less precise than C signal handlers
- Race conditions possible if multiple refresh cycles overlap (though `flock` can prevent this)

### Verdict: **C wins on robustness, Shell wins on recoverability.** A crashed C binary is worse than a failed shell command. But a well-structured shell script with proper error handling (like homecircuits.eu) is production-grade. The gap closes significantly if the C binary is wrapped in a shell `while true` restart loop.

---

## 2. Ease of Implementation

### C Binary

**Cost to build:**
- Cross-compilation toolchain setup (Zig or `arm-linux-gnueabi-g++`)
- ~500-1000 lines of C to implement: HTTP fetch (via curl subprocess or libcurl), JSON parsing (hand-rolled like kdashboard or cJSON), framebuffer mmap, touch evdev reading, tap region matching, sleep/wake detection (via lipc subprocess), cache file management
- kdashboard is ~3000 lines of C++ — we'd need a meaningful subset
- Debugging requires SSH to Kindle, `strace`, `gdb` (limited on Kindle)
- Every change requires: edit → cross-compile → scp to Kindle → test → repeat

**Time estimate:** 3-5 sessions to get a working viewer with touch + navigation.

### Shell (curl + eips)

**Cost to build:**
- ~200-300 lines of shell script
- `curl` fetches PNG + JSON → `jq` parses tap map → `eips -f -g` displays
- Touch reading: either a tiny C helper (50 lines: read `/dev/input/event*`, print "x y" on tap) or Python `struct.unpack` approach from the wiki
- Sleep/wake: `lipc-wait-event` in a background subprocess
- No cross-compilation, no binary builds
- Debugging: `set -x`, read the log, fix the script, `scp` and re-run

**Time estimate:** 1-2 sessions to get a working viewer with touch + navigation.

### Verdict: **Shell wins decisively.** The iteration loop is 10x faster — edit a text file, scp, run. No compiler, no toolchain, no ABI concerns. The only C code needed is a ~50-line touch event reader (or Python alternative).

---

## 3. Rendering Speed

### C Binary

- Direct framebuffer write: `mmap` → memcpy canvas pixels → `msync` → `eips ''` to refresh
- Full-screen 1072×1448 (1.5MB) write: **~50-100ms** (memory bandwidth limited)
- Plus `eips ''` refresh call: **~300-500ms** (e-ink waveform execution)
- Total: **~400-600ms** from render to visible

### Shell (curl + eips)

- `curl` downloads PNG: **~50-200ms** on LAN (1.5MB at 10+ Mbps)
- `eips -f -g image.png` handles PNG decode + dithering + framebuffer write + refresh internally
- `eips` internally does: open PNG → decode to framebuffer format → mmap → write pixels → ioctl refresh
- Total: **~500-800ms** from fetch to visible (PNG decode adds ~100-200ms over raw fb write)

### Verdict: **C is ~200ms faster.** But for a dashboard you glance at, 600ms vs 800ms is imperceptible. E-ink refresh itself takes 300-500ms regardless — that's the floor. The difference only matters if you're doing rapid partial updates (which we're not — full refresh per view).

---

## 4. Touch Handling

### C Binary

**Full control:**
- `EVIOCGRAB` — exclusive grab prevents Kindle framework from also receiving touch events
- Non-blocking `read()` on `/dev/input/event*` in a dedicated thread
- 700ms debounce (kdashboard pattern)
- Coordinate scaling via `EVIOCGABS` min/max ranges
- Rotation handling (try all 8 orientations on miss)
- Can flash the touch region on framebuffer for visual feedback (kdashboard's `flashTouchRectOnFramebuffer`)
- Sub-millisecond response time

### Shell

**Two options:**

**Option A: Tiny C helper (50 lines)**
```c
// touch_tap.c — reads /dev/input/event*, prints "x y\n" on tap release
// Cross-compile once, reuse forever. No changes needed for new views.
```
- Shell script reads stdout of this helper via a pipe
- All the C advantages (EVIOCGRAB, scaling, debounce) in a 50-line program
- This is the **sweet spot** — minimal C, maximal shell flexibility

**Option B: Python struct.unpack**
- Read `/dev/input/event*` with `struct.unpack('iiHHi', data)` (16 bytes per event on 32-bit ARM)
- No compilation needed but Python startup is ~2-3 seconds on Kindle
- No EVIOCGRAB (would need ctypes FFI, which is fragile)
- Kindle framework may interfere with touches

### Verdict: **C wins on capability, but the gap is closed by a 50-line C helper.** The touch helper is the only piece of C we'd ever need to write. It's so simple it'll never change. Everything else — navigation, rendering, networking — stays in shell.

---

## 5. Expandability

### C Binary

**Adding a new feature requires:**
1. Write C code
2. Cross-compile
3. SCP to Kindle
4. Restart viewer
5. Test on device (or via SSH)

**What's hard in C:**
- New JSON fields (re-parse, re-struct)
- New action types (switch statement grows, new code paths)
- New rendering tricks (anti-aliasing, dithering, custom fonts)
- Dynamic layouts (everything is compiled in)
- A/B testing different approaches

### Shell

**Adding a new feature requires:**
1. Edit the script
2. SCP to Kindle (or even edit via SSH)
3. Restart viewer

**What's easy in shell:**
- New JSON fields (`jq '.new_field'`)
- New action types (case statement, call any command)
- New rendering tricks (pipe through ImageMagick, add dithering, resize)
- Dynamic layouts (server controls everything, shell just routes)
- A/B testing (swap scripts, compare)
- Add new Kindle-side utilities (curl, jq, grep, sed — all available)

**What's hard in shell:**
- Complex string manipulation (quoting hell)
- Math beyond basic arithmetic (no floating point without `bc` or `awk`)
- Concurrency (background processes + wait, but no real threading)

### Verdict: **Shell wins decisively.** The entire design philosophy is "Kindle is dumb, server is smart." The shell script is a thin router. New features almost always live on the server side. When a Kindle-side change is needed, shell iteration is 10x faster.

---

## 6. Power Efficiency

### C Binary

- Process uses ~2-5MB RSS, minimal CPU when idle (sleeping in `select()` or `usleep()`)
- No subprocess overhead
- Can precisely control WiFi power (`wmiconfig` only when needed)
- Can implement RTC wake alarms with minimal code

### Shell

- Shell process + `curl` + `eips` + `jq` = more processes, but they're short-lived
- Between refreshes, only the shell `sleep` and `lipc-wait-event` are running (~1MB RSS)
- `curl` spawns and exits per fetch (~2MB transient)
- Net power difference: negligible. The dominant power draw is the e-ink refresh itself (~500ms at ~200mA), not the CPU

### Verdict: **Tie.** Both approaches achieve the same battery life (weeks). The e-ink panel and WiFi are the power consumers, not the viewer process.

---

## 7. Debuggability

### C Binary

- `gdb` available on Kindle but limited (no symbols if stripped, ARM remote debugging is painful)
- `strace` works — can trace syscalls
- Log to file via `fprintf(stderr, ...)` — kdashboard does this
- Segfaults produce no useful output unless core dumps are enabled
- Memory leaks are invisible without `valgrind` (not available on Kindle)
- Can add `--dump-pgm` flag to save rendered frame for inspection (kdashboard does this)

### Shell

- `set -x` — every command printed to log, immediately debuggable
- Every command's exit code visible
- Can `ssh` in and run the script manually, watch output in real-time
- Can `echo` variables at any point
- Can test individual commands (`curl URL`, `eips -f -g test.png`, `jq '.taps' file.json`)
- No segfaults, no memory leaks, no ABI issues
- Logs are human-readable by default

### Verdict: **Shell wins decisively.** This is the biggest practical advantage. When something breaks at 2am, a shell script log is readable. A C binary's segfault is a mystery.

---

## 8. Sleep/Wake Lifecycle

### C Binary

- `lipc-wait-event` called via `popen()` or `system()` — reads `outOfScreenSaver` event
- Time-gap detection: `gettimeofday()` before/after `sleep()` — if gap >> sleep, device was suspended
- Can use `deferSuspend` during critical operations (fetching, rendering)
- Process survives screensaver, freezes during deep sleep, resumes on wake
- Can set RTC wake alarm via `echo "+3600" > /sys/class/rtc/rtc1/wakealarm` (via system call)
- Full control over the lifecycle state machine

### Shell

- `lipc-wait-event com.lab126.powerd outOfScreenSaver` — blocks until wake, returns, script continues
- Same RTC alarm: `echo "+3600" > /sys/class/rtc/rtc1/wakealarm`
- Time-gap detection: `date +%s` before/after `sleep` — if gap >> sleep, device was suspended
- `~ds` command to disable deep sleep entirely (simplest for always-on mode)
- All the same patterns, just via shell commands

### Verdict: **Tie.** Both approaches have access to the same lipc/RTC/sysfs interfaces. The C version is slightly more precise (no subprocess for lipc), but the shell version is equally functional.

### Our planned lifecycle (from IDEA.md):

```
SLEEP ←─(idle timeout)─← WAKE → fetch + render home
  ↑                        │
  │                        ├── tap → navigate
  │                        ├── 60 min → auto-refresh
  │                        └── idle N min → SLEEP
  │
  └──(power button)─────────┘
```

Both approaches handle this identically. The shell version:
```sh
# Wait for wake
lipc-wait-event com.lab126.powerd outOfScreenSaver
# WiFi reconnect
wait_for_wifi
# Fetch + render
refresh_view "home"
# Enter interactive loop
interactive_loop
# On idle timeout, allow sleep
lipc-set-prop com.lab126.powerd preventScreenSaver 0
```

---

## 9. Binary Distribution & Cross-Compilation

### C Binary

**Requirements:**
- Zig compiler (easiest cross-compilation: `zig c++ -target arm-linux-musleabi`)
- OR `arm-linux-gnueabi-g++` (GNU cross-toolchain)
- OR Kindle's native GCC (if available via KUAL extension — rare)
- Must produce a **statically linked** binary (no shared library dependencies on Kindle)
- Binary must be copied to `/var/tmp/` (not `/mnt/us/` which is `noexec`)
- kdashboard's Makefile handles this with Zig or GNU cross-compiler

**Ongoing burden:**
- Every code change requires recompilation
- If Kindle firmware updates change ABI (rare but possible), binary may break
- Distributing to others requires them to install a cross-compiler or trust a pre-built binary

### Shell

**Requirements:**
- `curl` — already on Kindle at `/usr/bin/curl`
- `eips` — already on Kindle at `/usr/sbin/eips`
- `jq` — may need to be installed (copy a static ARM binary to `/var/tmp/`)
- `lipc-wait-event` — already on Kindle
- Touch helper: one 50-line C program, compiled once, never touched again

**Ongoing burden:**
- Edit text file, SCP, done
- No compilation for feature changes
- `jq` binary is the only external dependency — can fall back to `grep`/`sed`/`awk` if unavailable

### Verdict: **Shell wins decisively.** The cross-compilation burden is the single biggest argument against C. Even kdashboard requires Zig or a GNU cross-toolchain — this is friction for development and for anyone else who wants to use the project.

---

## 10. Offline Cache

### C Binary

- kdashboard pattern: fetch to `.tmp` → validate → rename to cache file
- On fetch failure: load cache file, parse JSON, render from cached data
- Full control over cache invalidation, TTL, and partial cache (e.g., cache taps but re-fetch image)
- Can implement LRU cache, cache size limits, etc.

### Shell

```sh
# Fetch to tmp
curl -fsSL "$url" -o "$cache.tmp" && mv "$cache.tmp" "$cache.json"
# Fetch image to tmp
curl -fsSL "$img_url" -o "$img.tmp" && mv "$img.tmp" "$img.png"
# On failure, use cache
if [ ! -f "$cache.json" ]; then
    cache_json=$(cat "$cache.json")
    img_path="$cache_png"
fi
```

- Same atomic download pattern
- Simpler — no JSON struct parsing needed, just serve the cached PNG directly
- `jq` can parse cached JSON for tap regions

### Verdict: **Shell is sufficient.** The cache strategy is simple: save PNG + JSON on success, serve from cache on failure. No need for complex cache management.

---

## The Hybrid Sweet Spot

The research reveals a clear optimal architecture:

```
┌─────────────────────────────────────────┐
│          SHELL SCRIPT (main)             │
│  • Fetch PNG + JSON via curl            │
│  • Parse tap map via jq                  │
│  • Display via eips -f -g               │
│  • Sleep/wake via lipc-wait-event       │
│  • Auto-refresh loop                    │
│  • Error recovery (homecircuits pattern)│
│  • Offline cache (atomic .tmp → rename) │
└──────────────┬──────────────────────────┘
               │ pipe: "x y\n" on tap
┌──────────────┴──────────────────────────┐
│     TOUCH HELPER (C, 50 lines)           │
│  • Scan /dev/input/event* for ABS device │
│  • EVIOCGRAB (exclusive touch)           │
│  • Read struct input_event               │
│  • Scale coordinates via EVIOCGABS       │
│  • Debounce 700ms                        │
│  • Print "x y\n" on tap release          │
│  • Try rotation variants on miss         │
└─────────────────────────────────────────┘
```

**Why this is optimal:**
- The only C code is a tiny touch reader — compiled once, never changed
- Everything else is shell — instantly editable, no compilation
- `EVIOCGRAB` is in the C helper — Kindle framework won't interfere with touches
- Shell handles all the orchestration, networking, display, lifecycle
- If the touch helper breaks, it's 50 lines of C to debug, not 3000
- The touch helper's interface is dead simple: stdout pipe printing "x y\n"

**Alternative if even 50 lines of C is too much:**
- Python `struct.unpack` touch reader (no compilation, but ~2-3s startup, no EVIOCGRAB)
- Use `evtest` if available on Kindle (may need installation)

---

## Decision Recommendation

**Use the hybrid: shell script + 50-line C touch helper.**

| Criterion | Weight | C Binary | Hybrid (shell + touch C) |
|---|---|---|---|
| Time to first working version | High | 3-5 sessions | 1-2 sessions |
| Iteration speed for new views | High | Slow (recompile) | Instant (edit text) |
| Touch quality | Medium | Excellent | Excellent (same C code) |
| Rendering speed | Low | ~200ms faster | Sufficient (e-ink is the bottleneck) |
| Debuggability | High | Hard (segfaults, no symbols) | Easy (`set -x`, readable logs) |
| Distribution | Medium | Cross-compiler required | Text file + 1 tiny binary |
| Power efficiency | Low | Marginally better | Same in practice |
| Production reliability | High | Good (if wrapped in restart loop) | Good (homecircuits pattern proven) |
| Expandability | High | Recompile for changes | Edit script |

The hybrid approach:
- Gets us to a working dashboard 3x faster
- Makes debugging 10x easier
- Sacrifices nothing on touch quality (the C helper handles it)
- The ~200ms rendering speed difference is invisible on e-ink
- Matches the "Kindle is dumb, server is smart" design philosophy — the shell is a thin router

**The one scenario where full C would be justified:** if we needed real-time partial updates (sub-second region redraws, animations, rapid touch response). We don't. We're doing full-screen view swaps on tap. Shell is the right tool.

---

## Related Files

- [kindle-framebuffer-rendering.md](kindle-framebuffer-rendering.md) — eips vs framebuffer technical details
- [kindle-touch-input.md](kindle-touch-input.md) — evdev touch reading, C and Python approaches
- [kindle-wake-detection.md](kindle-wake-detection.md) — lipc wake events, RTC alarms
- [kindle-networking.md](kindle-networking.md) — curl, LAN access, WiFi power management
- [kindle-python-availability.md](kindle-python-availability.md) — Python as alternative to shell
- [similar-projects.md](similar-projects.md) — homecircuits.eu production shell patterns
- [view-protocol-spec.md](view-protocol-spec.md) — The protocol the shell script implements
