# Kindle Power Button Sleep/Wake Lifecycle (v4 final — WORKING)

Implementation details for the sleep/wake toggle. The dashboard sleeps when the power button is pressed (Kindle native screensaver) and wakes back to the dashboard when pressed again. This file documents the final working architecture after 5 iterations of debugging.

## Architecture: Separate Channels + Flag Files

**Do NOT use a shared FIFO for touch + power events.** Two processes writing to the same FIFO causes line interleaving/corruption: `goingToScreenSaver 2` splits into `r 2`, which the main loop misinterprets as a tap coordinate → navigates to a random page.

```
touch_tap (C binary)   → writes "x y\n" to TOUCH_FIFO (fd3)     ← touch taps only
power watcher (subsh)  → creates flag files on LIPC events       ← power events only
                         .sleep_flag  (goingToScreenSaver)
                         .wake_flag   (outOfScreenSaver)
main loop              → reads TOUCH_FIFO via `read -r -t 1 <&3`
                       → polls `.sleep_flag` existence each iteration
```

The power watcher runs `lipc-wait-event` piped through `while read` — but writes flag files via `touch`, NOT `echo` to the FIFO. The `echo`-to-FIFO approach fails in busybox piped subshells.

## The 5 Bugs That Were Iterated Through

### Bug 1: `preventScreenSaver 1` blocks ALL screensaver entry

`lipc-set-prop com.lab126.powerd preventScreenSaver 1` prevents the power button from triggering `goingToScreenSaver`. The LIPC event never fired, so the power watcher sat idle and the sleep/wake toggle did nothing.

**Fix:** Don't set `preventScreenSaver` at all. Let the Kindle sleep naturally (timeout or power button). Trade-off: auto-sleeps after ~10 min inactivity — acceptable, user wakes with power button.

### Bug 2: `lipc-wait-event` events must be comma-separated

```sh
# CORRECT — comma-separated:
lipc-wait-event -m com.lab126.powerd goingToScreenSaver,outOfScreenSaver

# WRONG — space-separated prints usage and exits:
lipc-wait-event -m com.lab126.powerd goingToScreenSaver outOfScreenSaver
```

The space-separated form silently prints usage text and exits with rc=0. The `while true` wrapper keeps restarting it in a tight loop. The log fills with usage messages.

**Diagnostic:** If the viewer log shows `Power watcher raw: lipc-wait-event [options]...` or `Power watcher raw: Usage:`, the events are space-separated.

### Bug 3: `echo` in piped subshell doesn't reach FIFO

```sh
# WRONG — echo stdout doesn't reach the FIFO through the pipe in busybox:
lipc-wait-event -m com.lab126.powerd goingToScreenSaver,outOfScreenSaver | while read -r line; do
    echo "POWER:SLEEP"  # THIS ECHO GOES NOWHERE
done
```

The LIPC events ARE received (visible in logs as `Power watcher raw: goingToScreenSaver 2`), but `handle_sleep()` is never called because the `echo` output never reaches the FIFO.

**Fix:** Use flag files instead of echoing to the FIFO. The power watcher does `touch "$SLEEP_FLAG"` on `goingToScreenSaver` and `touch "$WAKE_FLAG"` on `outOfScreenSaver`. The main loop polls for file existence.

### Bug 4: Shared FIFO corrupts lines (dual-writer)

Even with `lipc-wait-event` writing directly to the FIFO (no `echo`), two processes writing to the same FIFO causes line interleaving. `goingToScreenSaver 2` gets split mid-line:

```
Unknown FIFO line: r 2              ← fragment of "goingToScreenSaver 2"
Tap: (52,)                          ← fragment misinterpreted as tap
Unknown FIFO line: ScreenSaver 1    ← fragment of "outOfScreenSaver 1"
```

These phantom "taps" navigate to random pages.

**Fix:** Separate channels. Touch taps via FIFO (fd3), power events via flag files. No FIFO sharing.

### Bug 5: Killing touch_tap on sleep breaks swipe-to-unlock

Killing `touch_tap` on sleep and restarting it on wake causes the restarted process to re-grab `EVIOCGRAB` before the user finishes the swipe-to-unlock gesture. The swipe stops responding.

**Fix:** Don't kill `touch_tap` during sleep. A frozen process can't read events, so `EVIOCGRAB` on a frozen process is effectively released — the Kindle framework handles swipe-to-unlock naturally. This is the same behavior that worked in v3 (before sleep/wake was added).

### Bug 6: Phantom tap on wake navigates to random page

`touch_tap` freezes during sleep, resumes with the device, and reads **buffered evdev events from the swipe-to-unlock gesture**. It reports the release point (~466,1201 — always the coaching/readiness button area) as a tap. Without draining, this phantom tap navigates immediately after wake.

**Fix:** After displaying home on wake, drain the FIFO for 2 seconds before accepting real input:

```sh
drain_until=$(($(date +%s) + 2))
while [ "$(date +%s)" -lt "$drain_until" ]; do
    if read -r -t 1 drain_line <&3 2>/dev/null; then
        log "Drained: $drain_line"
    fi
done
```

## Final Working Implementation

### Power Watcher (flag files, NOT FIFO)

```sh
start_power_watcher() {
    rm -f "$SLEEP_FLAG" "$WAKE_FLAG"
    (
        while true; do
            log "Power watcher: launching lipc-wait-event"
            lipc-wait-event -m com.lab126.powerd goingToScreenSaver,outOfScreenSaver 2>>"$LOG_FILE" | while read -r line; do
                log "Power event: $line"
                case "$line" in
                    *goingToScreenSaver*) touch "$SLEEP_FLAG" 2>/dev/null ;;
                    *outOfScreenSaver*)   touch "$WAKE_FLAG" 2>/dev/null ;;
                esac
            done
            log "Power watcher: lipc-wait-event exited, restarting in 1s"
            sleep 1
        done
    ) &
    POWER_WATCHER_PID=$!
}
```

Note: the `while read` pipe works here because we're using `touch` (file creation) not `echo` (stdout to FIFO). The pipe's stdout doesn't need to go anywhere.

### Sleep Sequence (does NOT kill touch_tap)

```sh
handle_sleep() {
    log "=== SLEEP: entering sleep mode ==="
    rm -f "$SLEEP_FLAG"

    # Clear screen to prevent ghosting through screensaver
    eips -c 2>/dev/null

    # Wait for wake — flag file or time-gap detection
    while true; do
        if [ -f "$WAKE_FLAG" ]; then
            rm -f "$WAKE_FLAG"
            log "Wake flag detected (outOfScreenSaver)"
            break
        fi
        before=$(date +%s)
        sleep 2
        after=$(date +%s)
        gap=$((after - before))
        if [ "$gap" -gt 10 ]; then
            log "Time gap ${gap}s >> 2s — woke from deep sleep"
            rm -f "$WAKE_FLAG" 2>/dev/null
            break
        fi
    done

    # WAKE: wait for WiFi, fetch home, display, drain phantom taps
    log "=== WAKE: Resuming dashboard ==="
    sleep 3  # WiFi reconnection

    if fetch_view "home"; then
        CURRENT_PATH="home"
        display_view
        last_refresh=$(date +%s)
    else
        display_view  # cached
    fi

    # Drain phantom taps from swipe-to-unlock gesture
    drain_until=$(($(date +%s) + 2))
    while [ "$(date +%s)" -lt "$drain_until" ]; do
        if read -r -t 1 drain_line <&3 2>/dev/null; then
            log "Drained: $drain_line"
        fi
    done
}
```

### Main Loop (polls flag file + reads FIFO)

```sh
while true; do
    # Check for sleep flag (power button pressed)
    if [ -f "$SLEEP_FLAG" ]; then
        handle_sleep
        continue
    fi

    # Read touch taps (1-second timeout for auto-refresh tick)
    tap_line=""
    if read -r -t 1 tap_line <&3 2>/dev/null; then
        case "$tap_line" in
            [0-9]*)  # Touch tap — parse coordinates
                tx=$(echo "$tap_line" | awk '{print $1}')
                ty=$(echo "$tap_line" | awk '{print $2}')
                # ... hit test, navigate, etc.
                ;;
            *)  # Non-touch line — log and ignore
                log "Ignoring non-touch line: $tap_line"
                ;;
        esac
    fi

    # Auto-refresh check...
done
```

## LIPC Event Reference

```sh
# Watch for power events (blocks until event, prints to stdout)
lipc-wait-event -m com.lab126.powerd goingToScreenSaver,outOfScreenSaver

# Output format:
# goingToScreenSaver 2     # Sleep (power button pressed or timeout)
# outOfScreenSaver 1       # Wake (power button pressed)
```

| Event | Meaning |
|---|---|
| `goingToScreenSaver` | Device entering screensaver (power button or timeout) |
| `outOfScreenSaver` | Device waking from screensaver (power button) |
| `charging` | Charger connected |
| `battLevelChanged` | Battery level changed (value = percentage) |

## WiFi Events (for wake reconnection)

```sh
lipc-wait-event -m com.lab126.wifid cmConnected
```

The script uses a simpler `sleep 3` instead of waiting for the LIPC event. The Kindle only supports 2.4GHz WiFi, which takes 3-5 seconds to reconnect after wake.

## Key Kindle Quirks (learned through debugging)

1. **`preventScreenSaver 1` blocks the power button's `goingToScreenSaver` event** — don't use it if you want power button sleep
2. **`lipc-wait-event` event names are comma-separated**, not space-separated
3. **A frozen `touch_tap` process doesn't block the Kindle framework from handling swipe-to-unlock** — EVIOCGRAB on a frozen process is effectively released
4. **`touch_tap` resumes with buffered evdev events from the swipe-to-unlock gesture** — must drain FIFO for 2s after wake
5. **Two processes writing to the same FIFO causes line corruption** — use separate channels (FIFO for touch, flag files for power)
6. **`echo` in a piped subshell (`cmd | while read ... echo`) doesn't reach a redirected stdout** in busybox — use file operations (`touch`) instead

## Debugging

A working session looks like:

```
[17:58:17] Power watcher: launching lipc-wait-event
[17:58:29] Power event: goingToScreenSaver 2
[17:58:29] === SLEEP: entering sleep mode ===
[17:58:29] Kindle will sleep naturally (screensaver → deep sleep)
[17:58:29] Waiting for wake (flag file or time-gap detection)...
[17:58:35] Power event: outOfScreenSaver 1
[17:58:35] Wake flag detected (outOfScreenSaver)
[17:58:35] === WAKE: Resuming dashboard ===
[17:58:35] Waiting for WiFi to reconnect...
[17:58:38] Fetching home view after wake...
[17:58:40] Home view displayed after wake
[17:58:40] Draining phantom taps (swipe-to-unlock residue)...
[17:58:41] Drain complete — accepting touch input
```

### Common failure modes

| Symptom | Cause | Fix |
|---|---|---|
| Log shows `Power watcher raw: lipc-wait-event [options]...` | Events space-separated | Change to comma-separated: `goingToScreenSaver,outOfScreenSaver` |
| Power events logged but `handle_sleep()` never called | `echo` in piped subshell doesn't reach FIFO | Use flag files (`touch $SLEEP_FLAG`) instead of `echo` to FIFO |
| `Unknown FIFO line: r 2` or `Tap: (52,)` in log | Shared FIFO — two writers corrupting lines | Separate channels: FIFO for touch, flag files for power |
| Swipe-to-unlock stops responding after 2nd sleep | Killing touch_tap on sleep, restarting on wake | Don't kill touch_tap — let it freeze/resume naturally |
| Wake navigates to random page (always coaching/readiness) | Phantom tap from buffered swipe-to-unlock events | Drain FIFO for 2 seconds after displaying home on wake |
| No power events at all | `preventScreenSaver 1` is set | Don't set it — blocks all screensaver entry including power button |
| Screen ghosts through screensaver on 2nd+ sleep | No `eips -c` before sleep | Add `eips -c` at start of `handle_sleep()` |
| Wake returns to wrong page | Fetching `CURRENT_PATH` instead of `home` | Always `fetch_view "home"` on wake |

## stop.sh

The stop script must kill all dashboard-related processes:

```sh
killall -9 dash_interactive.sh 2>/dev/null
killall -9 dash_viewer.sh 2>/dev/null
killall -9 touch_tap 2>/dev/null
killall -9 lipc-wait-event 2>/dev/null
killall -9 curl 2>/dev/null
```

Without killing `lipc-wait-event`, the power watcher subshell survives dashboard exit.
