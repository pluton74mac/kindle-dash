# Code Review Session 2026-07-24 — Bug Fixes Applied

> Session-specific detail from the full code review of dash_interactive.sh, touch_tap.c, view_server.py, and stop.sh. All bugs were fixed and deployed to the Kindle.

## Bugs Found and Fixed

### dash_interactive.sh (v4 → v4.1)

| # | Severity | Bug | Fix |
|---|----------|-----|-----|
| 1 | Critical | `if ! fetch_view "home"` — POSIX `!` forks subshell, globals (CURRENT_PNG etc.) lost | `fetch_view "home"; fetch_result=$?; if [ $fetch_result -ne 0 ]` |
| 2 | Critical | `read -r -t 1` — busybox ash silently ignores `-t`, blocks forever | `nb_read_tap()` — background reader subshell + flag file with 100ms poll loop |
| 3 | Critical | FIFO EOF → `read` returns empty string in tight loop → 100% CPU spin | `nb_read_tap` returns 2 on EOF (detected via `kill -0 $reader_pid`) → restart helper |
| 4 | Moderate | `CURRENT_REFRESH` unset on failed initial fetch → auto-refresh silently disabled | Set `CURRENT_REFRESH=3600` before initial fetch |
| 5 | Moderate | No trap handler → SIGTERM orphans children, fd3, FIFO, flag files | `trap cleanup INT TERM` with cleanup() that kills children, closes fd3, removes files |
| 6 | Minor | `kill $TOUCH_PID` when TOUCH_PID="" → "kill: illegal pid" | Guard: `[ -n "$TOUCH_PID" ] && kill "$TOUCH_PID"` |
| 7 | Minor | `local` keyword used — not supported in all busybox ash versions | Removed all `local` keywords |
| 8 | Moderate | Touch helper restart loop — EVIOCGRAB "Resource busy" → touch_tap exits → EOF → restart → exit → loop | Max 5 restarts with 3s delay, then give up gracefully |

### touch_tap.c

| # | Severity | Bug | Fix |
|---|----------|-----|-----|
| 1 | Moderate | `gettimeofday()` debounce breaks when NTP syncs after wake (clock jumps) | `clock_gettime(CLOCK_MONOTONIC)` — immune to wall-clock changes |
| 2 | Minor | `ioctl(fd, EVIOCGRAB, 1)` return value not checked | Check return, log warning with `strerror(errno)` on failure |
| 3 | Moderate | SYN_REPORT emitted taps with stale coordinates when BTN_TOUCH never sent | Removed SYN_REPORT tap emission. Added MT TRACKING_ID=-1 handling |

### view_server.py

| # | Severity | Bug | Fix |
|---|----------|-----|-----|
| 1 | Critical | Path traversal: `/images/../../etc/passwd` reads arbitrary files | `re.match(r'^[a-zA-Z0-9_\-.]+$', img_name)` + `resolve().startswith()` check |
| 2 | Minor | `json.loads(body)` crashes on malformed POST | `try/except (json.JSONDecodeError, ValueError)` → 400 error response |
| 3 | Minor | No Content-Length header on image responses | Added `Content-Length` header |
| 4 | Minor | Binds to 0.0.0.0 with no auth | Added `--bind` CLI flag (default 0.0.0.0, use `--bind 127.0.0.1` for local-only) |

### stop.sh

| # | Severity | Bug | Fix |
|---|----------|-----|-----|
| 1 | Moderate | `killall -9 curl` kills ALL curl processes system-wide | Check `/proc/$pid/cmdline` for "8888" before killing |
| 2 | Minor | `killall` may not match process comm on busybox | PID file: `echo $$ > viewer.pid` in main script, stop.sh reads it |
| 3 | Minor | No cleanup of FIFO/flag files | Added `rm -f touch_fifo .sleep_flag .wake_flag .tap_result` |

## KUAL menu.json Fix

`"exitmenu": false` on the interactive dashboard launcher is correct. `exitmenu: true` was tried and broke the launch — KUAL exits to the Kindle home screen before the dashboard script starts, leaving the user stuck.

## Post-Review Deployment Bugs (v4.1 → v4.2)

Bugs found after the code review fixes were deployed and tested on real hardware:

| # | Severity | Bug | Fix |
|---|----------|-----|-----|
| 1 | Critical | WiFi not ready after USB eject — `sleep 3` insufficient | `wait_for_network()` — ping 1.1.1.1 up to 30s before first fetch |
| 2 | Critical | No exit path when fetch fails AND no cached view | Auto-exit after 10s timeout with error message |
| 3 | Critical | KUAL `exitmenu: true` closes KUAL before script runs | Reverted to `exitmenu: false` |
| 4 | Moderate | Touch helper infinite restart loop (EVIOCGRAB "Resource busy") | Max 5 restarts with 3s delay, then give up gracefully |
| 5 | Moderate | macOS `/tmp` resolves to `/private/tmp` — path containment check fails | Compare against `Path(base).resolve()`, not literal string |
| 6 | Moderate | the agent venv PYTHONPATH leaks into system Python | Run server with venv Python directly |

## Post-Review Deployment Bugs (v4.2 → v4.3)

Bugs found in the second round of real-hardware testing:

| # | Severity | Bug | Fix |
|---|----------|-----|-----|
| 1 | Critical | FIFO write-before-read — `start_touch_helper` writes to FIFO before `exec 3<` opens read end → SIGPIPE → touch_tap dies | Open fd3 BEFORE starting touch helper: `exec 3< "$TOUCH_FIFO"` before `start_touch_helper` |
| 2 | Critical | nb_read_tap EOF false positive — reader subshell writes data and exits before `kill -0` check → returns 2 (EOF) instead of 0 (data) | Check result file BEFORE `kill -0` in nb_read_tap loop |
| 3 | Moderate | FIFO recreation invalidates fd3 — `rm -f` + `mkfifo` in restart_touch_helper but old fd3 on deleted inode | `exec 3<&-` then `exec 3<` after recreating FIFO |
| 4 | Moderate | EVIOCGRAB not released on exit — cleanup kills touch_tap with SIGTERM but doesn't wait, framework never gets touch back | SIGTERM → wait 1s → SIGKILL → `killall touch_tap` as fallback |

## Deployment Lesson

Stale `.png`/`.json` cache files from a previous session persisted in `/mnt/us/documents/kindle-dash/`. The dashboard fetched fresh data but displayed the old cached image when the fetch partially failed. Always clear cache on deploy.

## the agent venv PYTHONPATH Leak

Running `python3 view_server.py` picked up the the agent venv's PIL (compiled for Python 3.11) via the global PYTHONPATH, but `/usr/bin/python3` is Python 3.9 → `ImportError: _imaging`. Fix: use the venv's Python explicitly (`$HOME/.the agent/the agent-agent/venv/bin/python3`).
