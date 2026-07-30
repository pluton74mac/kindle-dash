# Post-Mortem: Kindle Dashboard "Bug Fix" Session — 2026-07-24

## What happened

the developer asked for a code review of 4 files (shell script, C touch helper, Python server, stop script). I found 29 "issues," he said "fix all," I rewrote large portions of working code, and broke a system that was already working. After 3 rounds of increasingly broken fixes, we reverted everything to the original state.

**Original code: worked.** My "fixed" code: broken in 4 different ways.

---

## Timeline of mistakes

### Phase 1: The code review

Reviewed `dash_interactive.sh`, `touch_tap.c`, `view_server.py`, `stop.sh`. Found 29 issues. Most were theoretical — things that *could* go wrong under edge cases, not things that *were* going wrong. Severity ratings were inflated. Things marked "Critical" were either not triggered in practice or were the reason the code worked.

### Phase 2: The "fixes"

Every fix attempted, intention vs reality:

---

**FIX 1: Subshell bug in `if ! fetch_view "home"`**

*Intention:* POSIX `! cmd` forks a subshell; global vars set in `fetch_view` would be lost.
*Reality:* busybox ash doesn't fork here — original worked fine. Unnecessary change.

---

**FIX 2: `read -t` not supported in busybox ash**

*Intention:* busybox `read` doesn't support `-t`. Replaced with elaborate background-subshell poller.
*Reality:* Created the worst bug of the session. The replacement had a race condition causing false EOF detections, which triggered an infinite touch-helper restart loop that flooded the log. Original `read -t` apparently works on this busybox build.

---

**FIX 3: FIFO EOF detection and restart loop**

*Intention:* Handle `touch_tap` crash gracefully with restart logic.
*Reality:* Restart loop fired constantly due to Fix 2's false EOFs. Added backoff (3s delay, max 5 retries), which made it slightly less bad but still broken.

---

**FIX 4: `CURRENT_REFRESH` unset on failed initial fetch**

*Intention:* Auto-refresh silently disabled if first fetch fails.
*Reality:* Legitimate edge case, harmless fix, but rarely triggered in practice.

---

**FIX 5: No trap handler for cleanup**

*Intention:* SIGTERM/SIGINT would leak FIFO, flag files, child processes.
*Reality:* Good practice but `stop.sh` uses `killall -9` (SIGKILL) which no trap catches. Only helped for graceful exits that rarely happened.

---

**FIX 6: `touch_tap.c` — CLOCK_MONOTONIC instead of gettimeofday**

*Intention:* `gettimeofday()` subject to NTP clock jumps after wake.
*Reality:* Theoretically correct but Kindle doesn't run NTP aggressively enough to matter. Old binary worked fine. Reverted to old binary anyway.

---

**FIX 7: `touch_tap.c` — EVIOCGRAB error checking**

*Intention:* Original didn't check `ioctl(fd, EVIOCGRAB, 1)` return value.
*Reality:* The warning fired ("Resource busy"), and the new binary's "graceful" handling meant it continued without the grab. Framework also got touch events → KUAL behind dashboard picked up taps. **The old binary's unchecked EVIOCGRAB was actually succeeding.** This was the root cause of "touch picks up KUAL behind."

---

**FIX 8: `touch_tap.c` — Removed SYN_REPORT tap emission**

*Intention:* SYN_REPORT could fire with stale coordinates.
*Reality:* Kindle PW4 uses BTN_TOUCH; SYN_REPORT was a harmless fallback. Unnecessary.

---

**FIX 9: `view_server.py` — Path traversal in `/images/`**

*Intention:* `/images/../../etc/passwd` would serve arbitrary files.
*Reality:* Legitimate security fix but implemented wrong. `Path("/tmp/kindle-dash").resolve()` on macOS → `/private/tmp/kindle-dash`, so `startswith("/tmp/kindle-dash")` was always `False`. Every image request returned 403. **This is why the dashboard showed "cannot reach server."**

---

**FIX 10: `menu.json` — `exitmenu: true`**

*Intention:* Close KUAL when dashboard launches so it doesn't steal touches.
*Reality:* Dumped to Kindle home before the script ran. Script launched with no WiFi, showed "cannot reach server," no exit path. Required Kindle restart. **Worst single change.** Reverted immediately.

---

**FIX 11: `stop.sh` — PID file, targeted curl kill**

*Intention:* `killall -9 curl` kills all curls; `killall` might not match process name.
*Reality:* Over-engineered. Original `killall` works fine on a dedicated Kindle.

---

**FIX 12: `wait_for_network()` instead of `sleep 3`**

*Intention:* WiFi takes longer than 3s after USB eject.
*Reality:* Good fix, harmless. One of the few actually useful changes.

---

**FIX 13: `preventScreenSaver 1` at start, restore on exit**

*Intention:* Prevent Kindle from sleeping during dashboard.
*Reality:* Original relied on power button sleep/wake cycle. This changed behavior in ways that interacted badly with sleep/wake detection.

---

**FIX 14: Open fd3 BEFORE starting touch helper**

*Intention:* `touch_tap` writing to FIFO with no reader gets SIGPIPE and dies.
*Reality:* This was fixing a bug I introduced myself in v4.1 by reordering startup. Original v4 had the correct order. Found by reading the log showing `touch_tap` dying immediately.

---

### Phase 3: The debugging spiral

1. the developer reports a problem
2. I diagnose from the log
3. I patch the script
4. Push to Kindle
5. New problem appears (caused by the patch)
6. Go to 1

Three rounds. Each made things worse — patching on top of patches without understanding the original design.

### Phase 4: The revert

Restored all 5 files from conversation history. Pushed to Kindle. Everything worked immediately.

---

## What was actually wrong with the original code

Almost nothing. Of the 29 "issues" found:

| My severity | Actually | Count |
|-------------|----------|-------|
| Critical | Real bug that breaks things | 0 |
| Critical | Theoretical edge case that doesn't trigger | 4 |
| Moderate | Legitimate but rare edge case | 6 |
| Minor | Code smell / future issue | 8 |
| Minor | Not a bug at all (false positive) | 11 |

The **only real bug** was the one I introduced myself: the path traversal check in `view_server.py` blocking macOS `/tmp` resolution.

---

## Root cause of the failure

**Fixed things that weren't broken.** The original code was a working spike. I treated it like a production codebase and applied "best practices" without understanding the runtime environment. The Kindle's busybox ash, the framework's touch handling, KUAL's process model — all idiosyncratic. The original code worked *because of* its quirks, not despite them.

Specific mistakes:

1. **Didn't test before changing.** Wrote 400+ lines of shell changes without running any on the target device.
2. **Fixed theoretical bugs.** `read -t` might not work on some busybox builds — but works on this one. EVIOCGRAB might fail in theory — but succeeds in practice.
3. **Didn't understand the process model.** KUAL, framework, `touch_tap`, and the dashboard script have a specific interaction pattern. Broke it with `exitmenu` and KUAL-killing logic.
4. **Layered patches.** Each fix round added complexity without removing the previous round's broken assumptions. By v4.3, the script was 500+ lines of workarounds for self-inflicted bugs.

---

## What should have happened

1. **Run the original code first.** See it working before changing anything.
2. **Fix one thing at a time.** Test each fix individually before stacking.
3. **Keep the original binary.** `touch_tap` worked. Never recompile without a specific demonstrated need.
4. **Respect the spike.** It's a spike — validate the concept, not production-harden it. Most of the 29 "issues" were irrelevant to the spike's goals.
5. **Understand before fixing.** The EVIOCGRAB "Resource busy" warning should have been investigated, not worked around.

---

## Files reverted

All restored to pre-review state:
- `dash_interactive.sh` — original v4
- `touch_tap.c` — original C source
- `touch_tap` — original ARM binary (never changed)
- `view_server.py` — original (path traversal fix kept — the one legitimate fix)
- `stop.sh` — original
- `menu.json` — original (`exitmenu: false`)

---

## Lesson

**If it works, don't fix it.** A code review that finds 29 issues in working code should trigger skepticism about the review, not a rewrite. The correct response to "fix all" on a working spike is "here are the 2-3 that actually matter — want me to fix just those?"
