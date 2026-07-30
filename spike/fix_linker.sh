#!/bin/sh
# fix_linker.sh — Create missing dynamic linker symlink so xzdec and other
# NiLuJe binaries can run. Required on some PW4 firmware versions.
#
# Run via KUAL → kindle-dash → Fix Linker

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
