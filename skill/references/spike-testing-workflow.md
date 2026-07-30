# Spike Testing & Deployment Workflow

> How to test a Kindle e-ink dashboard end-to-end, from first static image to full network pipeline.

## Phase 1: Static Display Test (no WiFi needed)

Proves the eips display pipeline works. Zero networking.

1. **Server renders PNG** on Mac:
   ```sh
   python3 view_server.py &
   curl http://localhost:8888/view?path=home  # triggers PNG render
   ```

2. **Copy PNG to Kindle via USB:**
   ```sh
   cp /tmp/kindle-dash/home.png /Volumes/Kindle/documents/
   ```

3. **Display on Kindle via KUAL:**
   - Open KUAL → "Kindle Dashboard" → "Show Home (static test)"
   - This runs `eips -f -g /mnt/us/documents/home.png`
   - Screen flashes → dashboard appears

4. **Verify:** Screen shows the rendered dashboard with no distortion.

## Phase 2: Network Fetch Test (WiFi required)

Proves the Kindle can reach the Mac server over WiFi.

### Prerequisites
- Kindle connected to WiFi (2.4GHz for PW4)
- Mac server running on same network
- Kindle USB-ejected (KUAL needs to run, USB mode blocks it on some firmware)

### Kindle WiFi setup
1. Eject Kindle from USB (Finder → Eject, or `diskutil eject`)
2. On Kindle: Settings → WiFi → connect to home network
3. Kindle gets a local IP (check via Settings → Device Info → Wi-Fi)

### Mac server
```sh
python3 view_server.py
# Note the Mac's LAN IP (ifconfig | grep "inet ")
```

### Kindle fetch test
1. Open KUAL → "Kindle Dashboard" → "Fetch from server (once)"
2. Script runs: `dash_viewer.sh http://MAC_IP:8888 once`
3. If success: screen shows fresh dashboard
4. If failure: error screen shows, check log at `/mnt/us/documents/kindle-dash/viewer.log`

### Common WiFi issues
- **WiFi not ready after USB eject:** The Kindle takes 5-15s to reconnect WiFi after USB eject. A blind `sleep 3` is not enough. The script must actively wait for network: `ping -c 1 -W 2 1.1.1.1` in a loop (up to 30s) before the first fetch. If the script shows "cannot reach server" immediately after eject, this is why.
- **Kindle not on same subnet:** Verify both on 192.168.x.x
- **PW4 only supports 2.4GHz:** Ensure AP broadcasts 2.4GHz SSID
- **WiFi power management:** Kindle may sleep WiFi. For dev: `wmiconfig -i wlan0 --power maxperf`
- **curl version:** Built-in curl may have TLS issues with HTTPS. Use HTTP for LAN.
- **Firewall:** Mac may block incoming connections. Allow Python in System Settings → Network → Firewall.

## Phase 3: Full Pipeline Test (auto-refresh loop)

1. Open KUAL → "Kindle Dashboard" → "Start Dashboard (auto-refresh)"
2. Script fetches home view, displays, sleeps for refresh_sec, repeats
3. To stop: KUAL → "Kindle Dashboard" → "Stop Dashboard" (kills process + restores screensaver)

## KUAL Extension Deployment

Directory structure on Kindle:
```
/mnt/us/extensions/kindle-dash/
├── config.xml          # KUAL extension metadata
├── menu.json           # KUAL menu items
└── bin/
    ├── dash_viewer.sh  # Main viewer script
    ├── show_static.sh  # Static PNG display (no network)
    └── stop.sh         # Kill viewer + restore screensaver
```

Deploy via USB:
```sh
# Copy extension files
cp -r templates/kual-extension/* /Volumes/Kindle/extensions/kindle-dash/
# Edit menu.json: replace SERVER_IP with Mac's LAN IP

# Clear stale cache from previous session — old .png/.json files persist
# and the dashboard shows stale content if the fetch partially fails
rm -f /Volumes/Kindle/documents/kindle-dash/*.png
rm -f /Volumes/Kindle/documents/kindle-dash/*.json
rm -f /Volumes/Kindle/documents/kindle-dash/*.tmp
rm -f /Volumes/Kindle/documents/kindle-dash/touch_fifo
rm -f /Volumes/Kindle/documents/kindle-dash/viewer.pid

# Clean macOS resource fork files — they break KUAL
find /Volumes/Kindle/extensions/kindle-dash -name '._*' -delete

# Eject Kindle, open KUAL
```

## Spike Checklist

- [ ] Python view server starts and serves /view?path=home
- [ ] PNG renders at correct resolution (1072×1448 for PW4, mode="L")
- [ ] PNG copied to Kindle via USB displays correctly via eips
- [ ] KUAL extension appears in KUAL menu
- [ ] Kindle reaches Mac server over WiFi (curl fetch succeeds)
- [ ] Auto-refresh loop works (screen updates after refresh_sec)
- [ ] Stop command kills viewer and restores screensaver
- [ ] Logs written to /mnt/us/documents/kindle-dash/viewer.log

## Iterative Testing Rules (learned the hard way)

1. **One change per deploy.** Don't batch multiple fixes — if something breaks, you can't isolate which change caused it.
2. **Test on hardware after every change.** `sh -n` catches syntax errors only. FIFO behavior, LIPC event timing, busybox ash quirks, and EVIOCGRAB conflicts only manifest on the Kindle.
3. **Always keep the last-working version.** No git on the spike directory. Before making changes, save a copy: `cp dash_interactive.sh dash_interactive.sh.working`
4. **Check the log first.** `cat /mnt/us/documents/kindle-dash/viewer.log` — every fetch, tap, sleep/wake event, and error is logged. The log answers most "why doesn't it work" questions without guessing.
5. **Stale cache causes confusion.** Old `.png`/`.json` files from a previous session persist in `/mnt/us/documents/kindle-dash/`. Clear them on every deploy to avoid the "it's showing an old image" red herring.
