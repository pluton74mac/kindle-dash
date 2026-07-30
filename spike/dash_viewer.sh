#!/bin/sh
# Kindle the agent Dashboard — Shell Viewer (spike)
# Fetches PNG + tap map from Mac view server, displays via eips.
# No touch helper yet — this is display-only for the spike.
#
# Usage: sh dash_viewer.sh [SERVER_URL]
# Example: sh dash_viewer.sh http://YOUR_SERVER_IP:8888

SERVER="${1:-http://YOUR_SERVER_IP:8888}"
VIEW_PATH="home"
CACHE_DIR="/mnt/us/documents/kindle-dash"
LOG_FILE="/mnt/us/documents/kindle-dash/viewer.log"

mkdir -p "$CACHE_DIR"

log() {
    echo "[$(date '+%H:%M:%S')] $1" >> "$LOG_FILE"
    echo "[$(date '+%H:%M:%S')] $1"
}

# Fetch a view: downloads PNG + JSON tap map
# Sets: CURRENT_PNG, CURRENT_TAPS, CURRENT_BACK, CURRENT_REFRESH
fetch_view() {
    path="$1"
    url="${SERVER}/view?path=${path}"
    json_tmp="${CACHE_DIR}/view.json.tmp"
    png_tmp="${CACHE_DIR}/view.png.tmp"
    json_file="${CACHE_DIR}/view.json"
    png_file="${CACHE_DIR}/$(echo "$path" | tr '/' '_').png"

    log "Fetching: $url"

    # Fetch JSON tap map
    curl -fsSL --connect-timeout 10 --max-time 30 "$url" -o "$json_tmp" 2>>"$LOG_FILE"
    if [ $? -ne 0 ]; then
        log "ERROR: Failed to fetch JSON from $url"
        return 1
    fi

    # Parse JSON (using jq if available, fallback to grep/sed)
    image_path=$(jq -r '.image' "$json_tmp" 2>/dev/null || grep -o '"image"[[:space:]]*:[[:space:]]*"[^"]*"' "$json_tmp" | sed 's/.*"image"[[:space:]]*:[[:space:]]*"//;s/"//')
    back_path=$(jq -r '.back // empty' "$json_tmp" 2>/dev/null || echo "")
    refresh_sec=$(jq -r '.refresh_sec // 0' "$json_tmp" 2>/dev/null || echo "0")

    if [ -z "$image_path" ]; then
        log "ERROR: No image path in JSON"
        cat "$json_tmp" >> "$LOG_FILE"
        return 1
    fi

    # Fetch the PNG image
    img_url="${SERVER}${image_path}"
    log "Fetching image: $img_url"
    curl -fsSL --connect-timeout 10 --max-time 30 "$img_url" -o "$png_tmp" 2>>"$LOG_FILE"
    if [ $? -ne 0 ]; then
        log "ERROR: Failed to fetch PNG from $img_url"
        return 1
    fi

    # Atomic move
    mv "$json_tmp" "$json_file"
    mv "$png_tmp" "$png_file"

    CURRENT_PNG="$png_file"
    CURRENT_TAPS="$json_file"
    CURRENT_BACK="$back_path"
    CURRENT_REFRESH="$refresh_sec"

    log "OK: view=$path png=$png_file refresh=${refresh_sec}s"
    return 0
}

# Display the current PNG on the e-ink screen
display_view() {
    if [ -z "$CURRENT_PNG" ] || [ ! -f "$CURRENT_PNG" ]; then
        log "ERROR: No PNG to display"
        return 1
    fi

    log "Displaying: $CURRENT_PNG"
    eips -f -g "$CURRENT_PNG"
    return $?
}

# Show error screen
show_error() {
    msg="$1"
    log "ERROR SCREEN: $msg"
    # Use eips text mode as fallback
    eips -c
    eips 1 2 "E-INK DASHBOARD"
    eips 1 4 "Error: $msg"
    eips 1 6 "Check server at ${SERVER}"
    eips 1 8 "Tap power to retry"
}

# ── Main loop ──

log "=== Kindle the agent Dashboard Viewer (spike) ==="
log "Server: $SERVER"

# Prevent screensaver during active session
lipc-set-prop com.lab126.powerd preventScreenSaver 1 2>/dev/null
log "Screensaver prevented"

# Initial fetch
if fetch_view "$VIEW_PATH"; then
    display_view
else
    show_error "Cannot reach server"
    # Try cached view
    if [ -f "${CACHE_DIR}/home.png" ]; then
        log "Using cached home.png"
        eips -f -g "${CACHE_DIR}/home.png"
    fi
fi

# Auto-refresh loop (60 minutes)
while true; do
    # Sleep for the refresh interval (or 3600 default)
    sleep_secs="${CURRENT_REFRESH:-3600}"
    if [ "$sleep_secs" = "0" ]; then
        sleep_secs=3600
    fi
    log "Sleeping ${sleep_secs}s before next refresh..."

    sleep "$sleep_secs" 2>/dev/null || break

    # Re-fetch and display current view
    if fetch_view "$VIEW_PATH"; then
        display_view
    else
        log "Refresh failed, keeping current screen"
    fi
done

# Cleanup on exit
lipc-set-prop com.lab126.powerd preventScreenSaver 0 2>/dev/null
log "Viewer stopped, screensaver restored"
