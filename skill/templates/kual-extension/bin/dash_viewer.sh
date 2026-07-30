#!/bin/sh
# Kindle the agent Dashboard — Shell Viewer
# Fetches PNG + tap map from Mac view server, displays via eips.
#
# Usage: sh dash_viewer.sh [SERVER_URL] [once]
# Example: sh dash_viewer.sh http://192.168.1.100:8888
#          sh dash_viewer.sh http://192.168.1.100:8888 once

SERVER="${1:-http://192.168.1.100:8888}"
MODE="${2:-loop}"
VIEW_PATH="home"
CACHE_DIR="/mnt/us/documents/kindle-dash"
LOG_FILE="/mnt/us/documents/kindle-dash/viewer.log"

mkdir -p "$CACHE_DIR"

log() {
    echo "[$(date '+%H:%M:%S')] $1" >> "$LOG_FILE" 2>&1
    echo "[$(date '+%H:%M:%S')] $1"
}

# Fetch a view: downloads PNG + JSON tap map
fetch_view() {
    path="$1"
    url="${SERVER}/view?path=${path}"
    json_tmp="${CACHE_DIR}/view.json.tmp"
    png_tmp="${CACHE_DIR}/view.png.tmp"
    json_file="${CACHE_DIR}/view.json"
    img_name=$(echo "$path" | tr '/' '_')
    png_file="${CACHE_DIR}/${img_name}.png"

    log "Fetching: $url"

    # Fetch JSON tap map
    curl -fsSL --connect-timeout 15 --max-time 45 "$url" -o "$json_tmp" 2>>"$LOG_FILE"
    if [ $? -ne 0 ]; then
        log "ERROR: Failed to fetch JSON from $url"
        return 1
    fi

    # Parse image path from JSON (jq if available, grep/sed fallback)
    image_path=$(jq -r '.image' "$json_tmp" 2>/dev/null)
    if [ -z "$image_path" ] || [ "$image_path" = "null" ]; then
        image_path=$(grep -o '"image"[[:space:]]*:[[:space:]]*"[^"]*"' "$json_tmp" | sed 's/.*"image"[[:space:]]*:[[:space:]]*"//;s/"$//')
    fi
    refresh_sec=$(jq -r '.refresh_sec // 0' "$json_tmp" 2>/dev/null || echo "0")

    if [ -z "$image_path" ]; then
        log "ERROR: No image path in JSON"
        return 1
    fi

    # Fetch the PNG image
    img_url="${SERVER}${image_path}"
    log "Fetching image: $img_url"
    curl -fsSL --connect-timeout 15 --max-time 45 "$img_url" -o "$png_tmp" 2>>"$LOG_FILE"
    if [ $? -ne 0 ]; then
        log "ERROR: Failed to fetch PNG from $img_url"
        return 1
    fi

    # Atomic move (prevents corrupt display on partial downloads)
    mv "$json_tmp" "$json_file"
    mv "$png_tmp" "$png_file"

    CURRENT_PNG="$png_file"
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
    eips -f -g "$CURRENT_PNG" 2>>"$LOG_FILE"
    return $?
}

# Show error screen using eips text mode
show_error() {
    msg="$1"
    log "ERROR SCREEN: $msg"
    eips -c 2>/dev/null
    eips 1 2 "E-INK DASHBOARD" 2>/dev/null
    eips 1 4 "Error: $msg" 2>/dev/null
    eips 1 6 "Server: ${SERVER}" 2>/dev/null
    eips 1 8 "Check WiFi connection" 2>/dev/null
}

# ── Main ──
log "=== Kindle the agent Dashboard Viewer ==="
log "Server: $SERVER  Mode: $MODE"

# Prevent screensaver during active session
lipc-set-prop com.lab126.powerd preventScreenSaver 1 2>/dev/null

# Wait for WiFi if not in once mode
if [ "$MODE" != "once" ]; then
    log "Waiting 5s for WiFi..."
    sleep 5
fi

# Initial fetch
if fetch_view "$VIEW_PATH"; then
    display_view
else
    show_error "Cannot reach server"
    # Try cached view
    if [ -f "${CACHE_DIR}/home.png" ]; then
        log "Using cached home.png"
        eips -f -g "${CACHE_DIR}/home.png" 2>/dev/null
    fi
    if [ "$MODE" = "once" ]; then
        lipc-set-prop com.lab126.powerd preventScreenSaver 0 2>/dev/null
        exit 1
    fi
fi

# Once mode: exit after displaying
if [ "$MODE" = "once" ]; then
    log "Once mode complete"
    lipc-set-prop com.lab126.powerd preventScreenSaver 0 2>/dev/null
    exit 0
fi

# Auto-refresh loop
while true; do
    sleep_secs="${CURRENT_REFRESH:-3600}"
    if [ "$sleep_secs" = "0" ] || [ -z "$sleep_secs" ]; then
        sleep_secs=3600
    fi
    log "Sleeping ${sleep_secs}s before next refresh..."
    sleep "$sleep_secs" 2>/dev/null

    if fetch_view "$VIEW_PATH"; then
        display_view
    else
        log "Refresh failed, keeping current screen"
    fi
done

# Cleanup
lipc-set-prop com.lab126.powerd preventScreenSaver 0 2>/dev/null
