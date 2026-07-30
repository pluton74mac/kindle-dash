#!/bin/sh
# fix_linker.sh — Create missing dynamic linker symlink so xzdec and other
# NiLuJe binaries can run. Required on PW4 FW 5.16+ (confirmed on 5.16.7).
#
# Run via KUAL (runs as root). One-time fix — symlink persists across reboots.
# After running this, re-install linkss: KUAL → Helper → Install MR Packages

echo "Checking dynamic linker..."

if [ -f /lib/ld-linux.so.3 ]; then
    echo "Symlink already exists. No fix needed."
else
    echo "Creating symlink: /lib/ld-linux.so.3 -> /lib/ld-linux-armhf.so.3"
    mntroot rw
    ln -s /lib/ld-linux-armhf.so.3 /lib/ld-linux.so.3
    mntroot ro
    echo "Done."
fi

echo ""
echo "Now retry: KUAL → Helper → Install MR Packages"
