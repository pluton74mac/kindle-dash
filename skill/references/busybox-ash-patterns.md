# Busybox Ash Shell Patterns for Kindle

> **IMPORTANT (POSTMORTEM-2026-07-24):** Several patterns in this file were
> derived from theoretical concerns that turned out to be WRONG on this Kindle's
> busybox build. The `nb_read_tap` function below was the **worst bug of the
> postmortem session** — replacing working `read -t` with this background-reader
> subshell introduced race conditions → false EOF detections → infinite touch
> helper restart loop. **`read -t` WORKS on the PW4. Use it. Do NOT use
> `nb_read_tap`.** This file is kept for reference only — the v4 final code uses
> simple `read -r -t 1 tap_line <&3` with no workarounds.

## `read -t` — WORKS on PW4 busybox ash

```sh
# This is the v4 final working pattern. Use it.
if read -r -t 1 tap_line <&3 2>/dev/null; then
    # process tap_line
    ...
fi
```

`read -t` was assumed unsupported in busybox, but the PW4's busybox build
supports it. POSTMORTEM-2026-07-24 Fix 2 documents the failed replacement
attempt. Do NOT replace this pattern.

---

## Historical: nb_read_tap (DO NOT USE — kept for reference only)

```sh
TAP_RESULT_FILE="${CACHE_DIR}/.tap_result"

nb_read_tap() {
    rm -f "$TAP_RESULT_FILE"
    (
        if read -r line <&3 2>/dev/null; then
            echo "$line" > "$TAP_RESULT_FILE"
        fi
    ) &
    reader_pid=$!
    waited=0
    while [ $waited -lt 10 ]; do          # 10 x 100ms = 1s timeout
        # Check result file FIRST — reader may have written data and exited
        # before we check kill -0. If we check kill -0 first, we'd falsely
        # report EOF when the reader actually delivered data.
        if [ -f "$TAP_RESULT_FILE" ]; then
            kill $reader_pid 2>/dev/null
            wait $reader_pid 2>/dev/null
            return 0                      # Data available
        fi
        # Only report EOF if reader died AND no result file appeared
        if ! kill -0 $reader_pid 2>/dev/null; then
            wait $reader_pid 2>/dev/null
            # One more check for the file — reader may have written it
            # just before dying
            if [ -f "$TAP_RESULT_FILE" ]; then
                return 0
            fi
            return 2                      # EOF — writer disconnected
        fi
        sleep 0.1 2>/dev/null || sleep 1  # busybox sleep supports decimals
        waited=$((waited + 1))
    done
    kill $reader_pid 2>/dev/null
    wait $reader_pid 2>/dev/null
    return 1                              # Timeout
}
```

Usage:
```sh
tap_line=""
nb_read_tap
nb_result=$?
if [ $nb_result -eq 2 ]; then
    # EOF — restart touch helper
    restart_touch_helper
    continue
elif [ $nb_result -eq 0 ]; then
    tap_line=$(cat "$TAP_RESULT_FILE" 2>/dev/null)
    rm -f "$TAP_RESULT_FILE"
fi
```

## FIFO Write-Before-Read (SIGPIPE)

> **NOTE:** The v4 final working code starts `touch_tap` BEFORE opening fd3, and it works. `touch_tap` blocks on `open()` (FIFO with no reader) until `exec 3<` opens the read end. The ordering below was identified as a bug during the postmortem session, but the POSTMORTEM (POSTMORTEM-2026-07-24.md, Fix 14) revealed that Fix 14 was actually fixing a bug *introduced* by the reviewer's own reordering in v4.1 — the original v4 had the correct ordering all along. **Test on hardware before changing FIFO ordering.**

```sh
# CORRECT order:
mkfifo "$TOUCH_FIFO"
exec 3< "$TOUCH_FIFO"          # open read end FIRST
start_touch_helper              # then start writer

# WRONG order — writer gets SIGPIPE and dies:
start_touch_helper              # writer starts, writes, SIGPIPE
exec 3< "$TOUCH_FIFO"          # too late — writer already dead
```

This bug manifests as: touch helper starts, appears in process list briefly, then dies. EOF detection fires, restart loop begins. The log shows "Touch helper started" followed immediately by "Touch helper disconnected (EOF on FIFO)" with no taps in between.

## FIFO EOF Race Condition in nb_read_tap

The background reader subshell can write data AND exit before the main loop's `kill -0` check runs. If `kill -0` is checked first, it fails (process already exited), and the function returns 2 (EOF) even though data was delivered. This causes spurious "Touch helper disconnected" restarts.

**Fix:** Always check the result file BEFORE checking if the reader died (see the `nb_read_tap` code above for the corrected pattern).

## FIFO Recreation Invalidates fd3

When `restart_touch_helper` recreates the FIFO (`rm -f` + `mkfifo`), the old fd3 (opened on the deleted inode) is stale. Must close and re-open:

```sh
restart_touch_helper() {
    # ... kill old helper ...
    rm -f "$TOUCH_FIFO"
    mkfifo "$TOUCH_FIFO" 2>/dev/null
    exec 3<&- 2>/dev/null       # close stale fd3
    exec 3< "$TOUCH_FIFO"       # re-open on new inode
    start_touch_helper
}
```

## Touch Helper Restart Loop Prevention

When EVIOCGRAB fails ("Resource busy" — the Kindle framework already holds the grab), `touch_tap` exits immediately. The EOF detection fires, restart fires, `touch_tap` exits again. Infinite loop at ~1/sec flooding the log.

**Fix: max-retry counter with delay:**

```sh
RESTART_COUNT=0
MAX_RESTARTS=5

restart_touch_helper() {
    RESTART_COUNT=$((RESTART_COUNT + 1))
    if [ $RESTART_COUNT -gt $MAX_RESTARTS ]; then
        log "ERROR: Touch helper failed $MAX_RESTARTS times — giving up"
        log "Dashboard will display but touch will not work"
        TOUCH_PID=""
        return 1
    fi
    log "Restarting touch helper (attempt $RESTART_COUNT/$MAX_RESTARTS)..."
    [ -n "$TOUCH_PID" ] && kill "$TOUCH_PID" 2>/dev/null
    sleep 3                              # longer delay between retries
    rm -f "$TOUCH_FIFO"
    mkfifo "$TOUCH_FIFO" 2>/dev/null
    exec 3<&- 2>/dev/null               # close stale fd3
    exec 3< "$TOUCH_FIFO"               # re-open on new inode
    start_touch_helper
    log "Touch helper restarted"
    return 0
}
```

In the main loop, after calling `restart_touch_helper`, check the return value. If it failed (max retries), add `sleep 5` before continuing — otherwise the EOF read returns instantly and the loop spins at 100% CPU.

## FIFO EOF Detection

When the FIFO writer (touch_tap) dies, `read` returns EOF (exit 0, empty string). Without detection, the main loop spins at 100% CPU processing empty strings.

Detection: `kill -0 $reader_pid` checks if the background reader is still alive. If it died instantly, the FIFO has no writer → EOF.

Recovery: see FIFO Recreation above for the restart pattern.

## Subshell Global Variable Loss — DOES NOT APPLY on PW4 busybox

> **POSTMORTEM-2026-07-24 Fix 1:** The claim that `if ! fetch_view` forks a
> subshell and loses globals was **wrong for this Kindle's busybox**. The v4
> working code uses `if ! fetch_view "home"` and globals (CURRENT_PNG,
> CURRENT_JSON, etc.) propagate correctly. Do NOT rewrite this pattern.

The `$(fetch_view)` (command substitution) pattern DOES fork a subshell and
would lose globals — but `if ! fetch_view` does not on this device.

## No `local` Keyword

> **Note:** This was flagged as a theoretical concern. The v4 code doesn't use
> `local`, so it wasn't tested. If you need local variables, test on hardware
> first. busybox ash in some builds supports `local`, in others it doesn't.

The v4 working code avoids `local` entirely — variables are function-scoped in
ash by default when not exported. This is safe and matches the working code.

```sh
# BAD
my_func() {
    local result="hello"
}

# GOOD
my_func() {
    result="hello"
}
```

## Trap Handler for Cleanup

Without a trap, SIGTERM orphans children, file descriptors, and temp files:

```sh
cleanup() {
    exec 3<&- 2>/dev/null
    # Kill touch helper with SIGTERM first (allows EVIOCGRAB release), then SIGKILL
    if [ -n "$TOUCH_PID" ]; then
        kill "$TOUCH_PID" 2>/dev/null
        sleep 1
        kill -9 "$TOUCH_PID" 2>/dev/null
    fi
    [ -n "$POWER_WATCHER_PID" ] && kill "$POWER_WATCHER_PID" 2>/dev/null
    # Also kill by name as fallback — ensures EVIOCGRAB is released
    killall touch_tap 2>/dev/null
    rm -f "$TOUCH_FIFO" "$SLEEP_FLAG" "$WAKE_FLAG" "$PID_FILE" "$TAP_RESULT_FILE"
    exit 0
}
trap cleanup INT TERM
```

Note: `killall -9` (SIGKILL) cannot be trapped — this only helps for graceful SIGTERM.

**EVIOCGRAB release on exit:** The touch helper holds EVIOCGRAB on the touch device. Killing with SIGTERM allows the process to close its file descriptors (releasing the grab). SIGKILL may not release it immediately — the kernel cleans up on process death, but there can be a delay. Always try SIGTERM first, then SIGKILL, then `killall` as a final fallback. Without this, the Kindle framework never gets touch events back after the dashboard exits.

## PID File for Reliable Process Management

`killall` matches against `/proc/<pid>/comm` which may not match the script name on busybox:

```sh
# In main script:
echo $$ > "${CACHE_DIR}/viewer.pid"

# In stop.sh:
if [ -f "${CACHE_DIR}/viewer.pid" ]; then
    kill -9 "$(cat "${CACHE_DIR}/viewer.pid")" 2>/dev/null
    rm -f "${CACHE_DIR}/viewer.pid"
fi
```

## Targeted curl Kill

`killall -9 curl` kills every curl on the system. Be more selective:

```sh
for pid in $(pidof curl 2>/dev/null); do
    if [ -n "$pid" ] && grep -q "8888" "/proc/$pid/cmdline" 2>/dev/null; then
        kill -9 "$pid" 2>/dev/null
    fi
done
```
