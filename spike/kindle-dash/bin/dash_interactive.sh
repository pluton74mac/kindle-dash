#!/bin/sh
# Kindle the agent Dashboard — Interactive Viewer v4
# Power button sleep/wake lifecycle via LIPC events.
# Uses awk for JSON parsing (no jq or python dependency).
#
# Architecture:
#   - Touch helper writes taps to TOUCH_FIFO (fd3)
#   - Power watcher creates flag files (SLEEP_FLAG / WAKE_FLAG)
#   - Main loop polls flag files + reads touch FIFO
#   - Touch helper is NEVER killed during sleep — it freezes and resumes
#     naturally. EVIOCGRAB on a frozen process doesn't block the Kindle
#     framework from handling swipe-to-unlock.
#
# Usage: dash_interactive.sh [SERVER_URL]

SERVER="${1:-http://YOUR_SERVER_IP:8888}"
SCRIPT_DIR="/mnt/us/extensions/kindle-dash/bin"
CACHE_DIR="/mnt/us/documents/kindle-dash"
LOG_FILE="/mnt/us/documents/kindle-dash/viewer.log"
TOUCH_HELPER="${SCRIPT_DIR}/touch_tap"
SCREEN_W=1072
SCREEN_H=1448
SLEEP_FLAG="${CACHE_DIR}/.sleep_flag"
WAKE_FLAG="${CACHE_DIR}/.wake_flag"
TAILSCALED_BIN="/mnt/us/extensions/tailscale/bin/tailscaled"
TAILSCALED_STATEDIR="/mnt/us/extensions/tailscale/bin/"
TAILSCALE_PROXY="localhost:1055"
CURL_PROXY_ARGS=""

mkdir -p "$CACHE_DIR"

log() {
    echo "[$(date '+%H:%M:%S')] $1" >> "$LOG_FILE" 2>&1
}

# Parse a JSON string field using grep/sed
json_str() {
    grep -o "\"$2\"[[:space:]]*:[[:space:]]*\"[^\"]*\"" "$1" 2>/dev/null | head -1 | sed "s/.*\"$2\"[[:space:]]*:[[:space:]]*\"//;s/\"$//"
}

# Parse a JSON number field using grep/sed
json_num() {
    grep -o "\"$2\"[[:space:]]*:[[:space:]]*[0-9]*" "$1" 2>/dev/null | head -1 | sed "s/.*:[[:space:]]*//"
}

# ── Tailscale (optional) ──
# If a Tailscale extension is installed (SOCKS5/HTTP proxy mode), start it and
# route curl through the local proxy. This lets SERVER be a Tailscale IP
# (100.x.x.x) that works both on the home LAN and away from it — Tailscale
# picks a direct path when possible, falling back to its DERP relay otherwise.
# Kernel TUN networking is NOT used here: confirmed unavailable on this
# PW4/FW5.16.7 build ("tailscaled failed — kernel TUN may not be supported"),
# so userspace-networking + an explicit proxy is the only path that works.
# If the Tailscale extension isn't installed, this is skipped entirely and
# curl falls back to plain LAN-only requests — Tailscale is purely additive.
ensure_tailscale_proxy() {
    if [ ! -x "$TAILSCALED_BIN" ]; then
        log "Tailscale not installed — LAN-only mode"
        return 1
    fi

    # If a tailscaled proxy is already up and can reach the server, don't
    # bounce it. Restarting kills any active Tailscale SSH session (the SSH
    # server runs inside tailscaled itself) and costs a real reconnect delay
    # for no benefit — an already-healthy proxy is already what we need.
    if curl -fsS --connect-timeout 2 --max-time 3 --proxy "http://${TAILSCALE_PROXY}" "${SERVER}/health" >/dev/null 2>&1; then
        CURL_PROXY_ARGS="--proxy http://${TAILSCALE_PROXY}"
        log "Tailscale proxy already up at ${TAILSCALE_PROXY}"
        return 0
    fi

    log "Starting tailscaled (proxy mode) for Tailscale connectivity..."
    pkill tailscaled 2>/dev/null
    sleep 2
    rm -f /var/run/tailscale/tailscaled.sock

    nohup "$TAILSCALED_BIN" --statedir="$TAILSCALED_STATEDIR" -tun userspace-networking \
        --socks5-server="$TAILSCALE_PROXY" \
        --outbound-http-proxy-listen="$TAILSCALE_PROXY" >> "$LOG_FILE" 2>&1 &

    sleep 3
    CURL_PROXY_ARGS="--proxy http://${TAILSCALE_PROXY}"

    # tailscaled needs real time to reach the control plane and connect to a
    # DERP relay before the proxy can actually route anywhere — observed ~20s
    # from cold start. Give it a bounded head start rather than either
    # guessing with a fixed sleep (too short = first fetch fails) or waiting
    # for full readiness (too long = touch_tap holds its EVIOCGRAB grab with
    # nothing yet watching SLEEP_FLAG, so a screen-timeout mid-wait leaves
    # swipe-to-unlock broken — hit on hardware 2026-07-31, see LOG.md). The
    # normal fetch fallback (cached image) plus the next tap's retry already
    # cover a still-cold tailnet, so this only needs to catch the common case.
    log "Waiting for Tailscale to connect..."
    start_ts=$(date +%s)
    waited=0
    while [ $waited -lt 6 ]; do
        if curl -fsS --connect-timeout 2 --max-time 3 $CURL_PROXY_ARGS "${SERVER}/health" >/dev/null 2>&1; then
            log "Tailscale proxy ready at ${TAILSCALE_PROXY} (connected after $(($(date +%s) - start_ts))s)"
            return 0
        fi
        sleep 2
        waited=$((waited + 2))
    done
    log "Tailscale proxy started but server not reachable after ${waited}s — continuing anyway (cached view / next tap will retry)"
}

# Fetch a view from the server
fetch_view() {
    path="$1"
    url="${SERVER}/view?path=${path}"
    img_name=$(echo "$path" | tr '/' '_')
    json_tmp="${CACHE_DIR}/${img_name}.json.tmp"
    png_tmp="${CACHE_DIR}/${img_name}.png.tmp"
    json_file="${CACHE_DIR}/${img_name}.json"
    png_file="${CACHE_DIR}/${img_name}.png"

    log "Fetching: $url"

    curl -fsSL --connect-timeout 10 --max-time 30 $CURL_PROXY_ARGS "$url" -o "$json_tmp" 2>>"$LOG_FILE"
    if [ $? -ne 0 ]; then
        log "ERROR: Failed to fetch JSON"
        return 1
    fi

    image_path=$(json_str "$json_tmp" "image")
    refresh_sec=$(json_num "$json_tmp" "refresh_sec")
    back_path=$(json_str "$json_tmp" "back")

    if [ -z "$image_path" ]; then
        log "ERROR: No image path in JSON"
        return 1
    fi

    img_url="${SERVER}${image_path}"
    log "Fetching image: $img_url"
    curl -fsSL --connect-timeout 10 --max-time 30 $CURL_PROXY_ARGS "$img_url" -o "$png_tmp" 2>>"$LOG_FILE"
    if [ $? -ne 0 ]; then
        log "ERROR: Failed to fetch PNG"
        return 1
    fi

    mv "$json_tmp" "$json_file"
    mv "$png_tmp" "$png_file"

    CURRENT_PNG="$png_file"
    CURRENT_JSON="$json_file"
    CURRENT_PATH="$path"
    CURRENT_BACK="${back_path:-home}"
    CURRENT_REFRESH="${refresh_sec:-3600}"

    log "OK: view=$path png=$png_file refresh=${refresh_sec}s"
    return 0
}

# Display current PNG
display_view() {
    if [ -z "$CURRENT_PNG" ] || [ ! -f "$CURRENT_PNG" ]; then
        log "ERROR: No PNG to display"
        return 1
    fi
    eips -f -g "$CURRENT_PNG" 2>>"$LOG_FILE"
    log "Displayed: $CURRENT_PNG"
}

# Hit test: check if (x,y) matches any tap region
# Output: "action target" on stdout if hit, empty if no hit
hit_test() {
    tx=$1
    ty=$2

    if [ -z "$CURRENT_JSON" ] || [ ! -f "$CURRENT_JSON" ]; then
        return 1
    fi

    # First try direct coordinates
    result=$(awk -v tx="$tx" -v ty="$ty" '
    BEGIN { x=y=w=h=act=tgt="" }
    /"x"/ { gsub(/.*"x"[[:space:]]*:[[:space:]]*/, ""); gsub(/[^0-9-].*/, ""); x=$0 }
    /"y"/ { gsub(/.*"y"[[:space:]]*:[[:space:]]*/, ""); gsub(/[^0-9-].*/, ""); y=$0 }
    /"w"/ { gsub(/.*"w"[[:space:]]*:[[:space:]]*/, ""); gsub(/[^0-9-].*/, ""); w=$0 }
    /"h"/ { gsub(/.*"h"[[:space:]]*:[[:space:]]*/, ""); gsub(/[^0-9-].*/, ""); h=$0 }
    /"action"/ { gsub(/.*"action"[[:space:]]*:[[:space:]]*"/, ""); gsub(/".*/, ""); act=$0 }
    /"target"/ { gsub(/.*"target"[[:space:]]*:[[:space:]]*"/, ""); gsub(/".*/, ""); tgt=$0 }
    /}/ && x != "" {
        if (tx+0 >= x+0 && tx+0 < x+0+w+0 && ty+0 >= y+0 && ty+0 < y+0+h+0) {
            print act " " tgt
            exit 0
        }
        x=y=w=h=act=tgt=""
    }
    ' "$CURRENT_JSON" 2>/dev/null)

    if [ -n "$result" ]; then
        echo "$result"
        return 0
    fi

    return 1
}

show_error() {
    msg="$1"
    log "ERROR: $msg"
    eips -c 2>/dev/null
    eips 1 2 "E-INK DASHBOARD" 2>/dev/null
    eips 1 4 "Error: $msg" 2>/dev/null
    eips 1 6 "Server: $SERVER" 2>/dev/null
}

# ── Power lifecycle ──

# Start touch helper — writes "x y" taps to the touch FIFO
start_touch_helper() {
    if [ -x "$TOUCH_HELPER" ]; then
        "$TOUCH_HELPER" > "$TOUCH_FIFO" 2>>"$LOG_FILE" &
        TOUCH_PID=$!
        log "Touch helper started (PID=$TOUCH_PID)"
    else
        log "ERROR: touch_tap not found at $TOUCH_HELPER"
        TOUCH_PID=""
    fi
}

# Start power event watcher — creates flag files on sleep/wake events.
# Uses lipc-wait-event with -m (multievent, don't exit after first event).
# Event names MUST be comma-separated.
# The watcher creates SLEEP_FLAG or WAKE_FLAG files — the main loop polls these.
# This avoids any FIFO sharing/corruption issues.
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
    log "Power watcher started (PID=$POWER_WATCHER_PID)"
}


# Handle sleep — called when SLEEP_FLAG is detected by the main loop.
# Clears the screen, waits for wake, then fetches home and displays.
# Does NOT kill the touch helper — it freezes and resumes with the device.
# A frozen touch_tap can't read events, so the Kindle framework handles
# swipe-to-unlock naturally. This is the behavior that worked before.
handle_sleep() {
    log "=== SLEEP: entering sleep mode ==="
    rm -f "$SLEEP_FLAG"

    # Clear the screen so the dashboard image doesn't ghost through the screensaver.
    eips -c 2>/dev/null

    log "Kindle will sleep naturally (screensaver → deep sleep)"
    log "Waiting for wake (flag file or time-gap detection)..."

    # Wait for wake.
    # Two detection mechanisms:
    #   a) WAKE_FLAG file created by power watcher (outOfScreenSaver event)
    #   b) Time-gap: sleep 2 takes much longer than 2s → device was suspended
    #
    # During deep sleep, the shell process freezes mid-sleep.
    # When it resumes, the time gap tells us we slept.
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
            # Clean up any wake flag that might have been set
            rm -f "$WAKE_FLAG" 2>/dev/null
            break
        fi
    done

    # ── WAKE ──
    log "=== WAKE: Resuming dashboard ==="

    # Wait for WiFi to reconnect (Kindle only supports 2.4GHz, takes 3-5s)
    log "Waiting for WiFi to reconnect..."
    sleep 3

    # 6. Fetch fresh view from server — always return to home on wake
    log "Fetching home view after wake..."
    if fetch_view "home"; then
        CURRENT_PATH="home"
        display_view
        last_refresh=$(date +%s)
        log "Home view displayed after wake"
    else
        log "Fetch failed after wake — showing cached view"
        display_view
    fi

    # 7. Drain phantom taps from the swipe-to-unlock gesture.
    #    touch_tap was frozen during sleep — it resumes with the device and
    #    reads buffered swipe-to-unlock events, reporting the final release
    #    point as a tap. Flush these for 2 seconds before accepting real input.
    log "Draining phantom taps (swipe-to-unlock residue)..."
    drain_until=$(($(date +%s) + 2))
    while [ "$(date +%s)" -lt "$drain_until" ]; do
        if read -r -t 1 drain_line <&3 2>/dev/null; then
            log "Drained: $drain_line"
        fi
    done
    log "Drain complete — accepting touch input"
}

# ── Main ──

log "=== Kindle Dashboard Interactive Viewer v4 ==="
log "Server: $SERVER"

# Kill any leftover processes from previous sessions
killall touch_tap 2>/dev/null
killall lipc-wait-event 2>/dev/null

# Create touch FIFO (ONLY touch helper writes to it — no power watcher)
TOUCH_FIFO="${CACHE_DIR}/touch_fifo"
rm -f "$TOUCH_FIFO"
mkfifo "$TOUCH_FIFO" 2>/dev/null

# Start touch helper and power watcher
start_touch_helper
start_power_watcher
ensure_tailscale_proxy

log "Waiting 3s for WiFi..."
sleep 3

# Initial fetch
CURRENT_PATH="home"
CURRENT_JSON=""
CURRENT_PNG=""
if ! fetch_view "home"; then
    show_error "Cannot reach server"
    if [ -f "${CACHE_DIR}/home.png" ]; then
        eips -f -g "${CACHE_DIR}/home.png" 2>/dev/null
        log "Using cached home.png"
        CURRENT_PNG="${CACHE_DIR}/home.png"
        CURRENT_JSON="${CACHE_DIR}/home.json"
    fi
fi
display_view

# Main interaction loop
# fd3 reads from the touch FIFO (touch taps only — no power events mixed in).
# Power events are detected via flag file polling.
log "Entering interaction loop"
exec 3< "$TOUCH_FIFO"
last_refresh=$(date +%s)

while true; do
    # Check for sleep flag (power button pressed)
    if [ -f "$SLEEP_FLAG" ]; then
        handle_sleep
        continue
    fi

    # Read from touch FIFO (1 second timeout for auto-refresh tick)
    tap_line=""
    if read -r -t 1 tap_line <&3 2>/dev/null; then
        # Only process lines that look like touch coordinates (start with digit)
        case "$tap_line" in
            [0-9]*)
                if [ -n "$tap_line" ]; then
                    tx=$(echo "$tap_line" | awk '{print $1}')
                    ty=$(echo "$tap_line" | awk '{print $2}')
                    log "Tap: ($tx,$ty)"

                    # Hit test
                    hit_result=$(hit_test "$tx" "$ty")
                    if [ -n "$hit_result" ]; then
                        tap_action=$(echo "$hit_result" | awk '{print $1}')
                        tap_target=$(echo "$hit_result" | awk '{print $2}')
                        log "HIT: $tap_action -> $tap_target"

                        if [ "$tap_action" = "navigate" ] && [ -n "$tap_target" ]; then
                            if fetch_view "$tap_target"; then
                                display_view
                                last_refresh=$(date +%s)
                            else
                                log "Failed to fetch $tap_target"
                            fi
                        elif [ "$tap_action" = "refresh" ]; then
                            if fetch_view "$CURRENT_PATH"; then
                                display_view
                                last_refresh=$(date +%s)
                            fi
                        elif [ "$tap_action" = "exit" ]; then
                            log "Exit requested — cleaning up and stopping"
                            exec 3<&-
                            kill $TOUCH_PID 2>/dev/null
                            kill $POWER_WATCHER_PID 2>/dev/null
                            rm -f "$TOUCH_FIFO" "$SLEEP_FLAG" "$WAKE_FLAG"
                            # Return to Kindle home screen
                            lipc-set-prop com.lab126.appmgrd start app://com.lab126.booklet.home 2>/dev/null
                            log "Viewer exited cleanly"
                            exit 0
                        fi
                    else
                        log "No hit at ($tx,$ty)"
                    fi
                fi
                ;;
            *)
                # Not a touch coordinate — log and ignore
                log "Ignoring non-touch line: $tap_line"
                ;;
        esac
    fi

    # Auto-refresh
    now=$(date +%s)
    elapsed=$((now - last_refresh))
    if [ -n "$CURRENT_REFRESH" ] && [ "$CURRENT_REFRESH" -gt 0 ] && [ "$elapsed" -ge "$CURRENT_REFRESH" ]; then
        log "Auto-refresh (${elapsed}s >= ${CURRENT_REFRESH}s)"
        if fetch_view "$CURRENT_PATH"; then
            display_view
        fi
        last_refresh=$(date +%s)
    fi
done

# Cleanup (unreachable — loop is infinite, exit via tap action)
exec 3<&-
kill $TOUCH_PID 2>/dev/null
kill $POWER_WATCHER_PID 2>/dev/null
rm -f "$TOUCH_FIFO" "$SLEEP_FLAG" "$WAKE_FLAG"
log "Viewer stopped"
