#!/bin/sh
# Stop the Kindle dashboard viewer
killall -9 dash_interactive.sh 2>/dev/null
killall -9 dash_viewer.sh 2>/dev/null
killall -9 touch_tap 2>/dev/null
killall -9 lipc-wait-event 2>/dev/null
killall -9 curl 2>/dev/null
lipc-set-prop com.lab126.powerd preventScreenSaver 0 2>/dev/null
echo "Dashboard stopped"
