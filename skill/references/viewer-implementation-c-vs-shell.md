# Kindle Viewer Implementation: C vs Shell (curl+eips)

> Condensed from a 10-dimension comparison analysis. Decision: hybrid shell + C touch helper.

## Decision Matrix

| Dimension | C Binary | Shell (curl + eips) | Winner |
|---|---|---|---|
| **Reliability** | Single process, no shell quoting bugs, direct mmap | Every command exit-code checkable, `set -e` + `set -x` | C wins robustness, Shell wins recoverability |
| **Ease of implementation** | 3-5 sessions, cross-compile toolchain, ~1000 lines C | 1-2 sessions, ~200-300 lines shell, no compilation | **Shell 10x** |
| **Rendering speed** | ~400-600ms (direct fb write + eips refresh) | ~500-800ms (curl + eips PNG decode + refresh) | C ~200ms faster — imperceptible on e-ink |
| **Touch handling** | Full: EVIOCGRAB, scaling, debounce, rotation, visual feedback | Needs 50-line C helper for EVIOCGRAB. Python alternative has 2-3s startup, no grab | C wins, but gap closed by tiny helper |
| **Expandability** | Recompile for every change. New JSON fields = re-parse | Edit text file, scp, run. `jq '.new_field'`. Instant | **Shell 10x** |
| **Power efficiency** | ~2-5MB RSS, minimal CPU idle | Shell + transient curl/eips processes. Negligible difference — e-ink panel is the power draw | Tie |
| **Debuggability** | gdb limited on Kindle, segfaults = mystery, no valgrind | `set -x` = readable logs, ssh in and run manually | **Shell decisively** |
| **Maintenance burden** | Cross-compiler, ABI concerns, binary distribution | Text file, scp, done | **Shell decisively** |
| **Binary distribution** | Requires Zig or arm-linux-gnueabi-g++. Static link. Copy to /var/tmp (noexec) | curl + eips built-in. jq may need install. One 50-line binary | **Shell decisively** |
| **Sleep/wake** | lipc via popen, time-gap detection, deferSuspend, RTC alarm | Same lipc commands via shell. Same RTC sysfs. Identical capability | Tie |

## The Hybrid Sweet Spot

```
SHELL SCRIPT (main)
  • curl fetches PNG + JSON tap map
  • jq parses tap regions
  • eips -f -g displays PNG
  • lipc-wait-event handles sleep/wake
  • Auto-refresh loop
  • Error recovery (homecircuits pattern)
  • Offline cache (atomic .tmp → rename)
      │ pipe: "x y\n" on tap
      ▼
C TOUCH HELPER (50 lines, compiled once)
  • EVIOCGRAB exclusive touch access
  • Reads evdev /dev/input/event*
  • Scales coordinates via EVIOCGABS
  • 700ms debounce
  • Prints "x y\n" on tap release
```

## Key Arguments

**Against full C:**
- Cross-compilation for every change kills iteration speed
- 3000 lines of C++ (kdashboard size) to debug with no valgrind, limited gdb on Kindle
- Segfaults at 2am = mystery. Shell errors = readable logs
- ~200ms rendering speed difference is invisible — e-ink panel refresh is 300-500ms regardless

**Against pure shell (no C):**
- No EVIOCGRAB → Kindle framework receives touches too, causes unwanted UI responses
- Python touch reader: 2-3s startup, no exclusive grab, fragile ctypes FFI for ioctl

**For the hybrid:**
- Only C code is a tiny touch reader — compiled once, never changed
- Everything else is shell — instantly editable, no compilation
- EVIOCGRAB is in the C helper — Kindle framework won't interfere
- Shell handles all orchestration, networking, display, lifecycle
- homecircuits.eu proves shell-based image-push with full error recovery works in production

## When Full C Would Be Justified

Real-time partial updates (sub-second region redraws, animations, rapid touch response). We don't do this — we do full-screen view swaps on tap. Shell is the right tool.

## Production Reliability Patterns (from homecircuits.eu)

- `while true` loop with full error recovery at every step
- Atomic downloads (download to `.tmp`, rename only on success)
- Progressive ping backoff (up to 10 attempts with increasing delays)
- Gateway route restoration after deep sleep (`route add default gw ...`)
- Battery protection (below 5%, show low-battery image, sleep 1h)
- Error counter — after 10 consecutive errors, auto-reboot
- Upstart job for auto-start after boot
- Log rotation (trim to last 300 lines)

## Sources

- kdashboard GitHub repo — C++ patterns for touch, framebuffer, KUAL
- homecircuits.eu — production shell-based image-push with error recovery
- 4dcu.be — Python + SVG + rsvg-convert + fbink dashboard on Kindle
- pascalw/kindle-dash — minimal shell + eips + RTC wake pattern
- Full wiki at: ideas/kindle-the agent-dashboard/llm_wiki/viewer-implementation-c-vs-shell.md
