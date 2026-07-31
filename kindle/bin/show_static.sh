#!/bin/sh
# Display a static PNG from /mnt/us/documents/ via eips
# Usage: show_static.sh <image_name_without_extension>
IMG="/mnt/us/documents/${1}.png"
if [ -f "$IMG" ]; then
    eips -f -g "$IMG"
else
    eips -c
    eips 1 2 "Image not found: $IMG"
fi
