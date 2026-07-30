#!/bin/sh
# install_screensaver.sh — One-shot: install custom screensaver via bind-mount.
# Survives reboots via an upstart job.
#
# Run via KUAL → kindle-dash → Install Screensaver
# KUAL runs as root, so we can write to /etc/upstart/

SS_SRC="/mnt/us/extensions/kindle-dash/bin/bg_ss0.png"
SS_DIR="/mnt/us/screensavers"
UPSTART_CONF="/etc/upstart/kindle-dash-screensaver.conf"

echo "Installing custom screensaver (bind-mount + upstart)..."

# 1. Create persistent screensaver directory on user store
mkdir -p "$SS_DIR"

# 2. Copy our image, named correctly (bg_ss00.png)
if [ -f "$SS_SRC" ]; then
    rm -f "$SS_DIR"/bg_ss*.png
    cp "$SS_SRC" "$SS_DIR/bg_ss00.png"
    chmod 644 "$SS_DIR/bg_ss00.png"
    echo "Image installed: $SS_DIR/bg_ss00.png"
else
    echo "ERROR: Source image not found at $SS_SRC"
    exit 1
fi

# 3. Write upstart job to survive reboots
#    Runs before framework starts, bind-mounts our dir over the tmpfs
mntroot rw
cat > "$UPSTART_CONF" << 'UPSTART'
# kindle-dash-screensaver — bind-mount custom screensaver dir
# over /usr/share/blanket/screensaver before framework starts
start on starting framework
stop on (stopped framework or ota-update)

pre-start script
    SS_DIR="/mnt/us/screensavers"
    TARGET="/usr/share/blanket/screensaver"
    if [ -d "$SS_DIR" ] && [ -f "$SS_DIR/bg_ss00.png" ]; then
        mount --bind "$SS_DIR" "$TARGET" 2>/dev/null || true
    fi
end script
UPSTART
mntroot ro

echo "Upstart job installed: $UPSTART_CONF"

# 4. Do the bind-mount now (for current session)
mount --bind "$SS_DIR" /usr/share/blanket/screensaver 2>/dev/null
if [ $? -eq 0 ]; then
    echo "Bind-mount active for current session"
else
    echo "WARN: bind-mount failed (may already be mounted or framework running)"
fi

# 5. Restart framework to pick up the new screensaver
echo "Restarting framework..."
stop framework
sync
sleep 1
start framework

echo ""
echo "=== DONE ==="
echo "Screensaver installed. The Kindle will now show the custom image on sleep."
echo "This persists across reboots via the upstart job."
echo ""
echo "To update the image later:"
echo "  1. Copy new bg_ss0.png to /mnt/us/extensions/kindle-dash/bin/"
echo "  2. Run this script again"
echo ""
