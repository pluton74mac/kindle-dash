# Spike Debugging: Touch + JSON Parsing

> Real debugging session from the first end-to-end spike on a Kindle Paperwhite 4 (10th Gen). Captures the exact failure modes, log analysis, and fixes.

## Session Context

**Device:** Kindle Paperwhite 4 (10th Gen), 1072×1448, capacitive touch, jailbroken with WinterBreak + KUAL
**Server:** Mac, Python 3.11 + Pillow 12.2, local HTTP on port 8888
**Architecture:** Shell viewer (curl + eips) + C touch helper (touch_tap, cross-compiled with Zig 0.16.0)

## Failure 1: KUAL Extension Not Appearing

**Symptom:** KUAL menu doesn't show "Kindle Dashboard" after copying extension files via USB.

**Root cause:** `config.xml` used `<about>` and `<mainmenu>` tags — these are not recognized by KUAL. KUAL requires `<information>` and `<menus>` tags with specific child elements.

**Fix:** Match the format used by a known-working extension (koreader):
```xml
<extension>
    <information>
        <name>Kindle Dashboard</name>
        <version>0.1.0</version>
        <author>...</author>
        <id>kindle-dash</id>
    </information>
    <menus>
        <menu type="json" dynamic="true">menu.json</menu>
    </menus>
</extension>
```

**Also:** macOS `._*` resource fork files can confuse KUAL's scanner. Clean with:
```sh
find /Volumes/Kindle/extensions/kindle-dash -name '._*' -delete
```

## Failure 2: Touch Registered But No Hit

**Symptom:** Log shows ~30 taps with valid coordinates (e.g., "Tap: (193,824)") but all report "No tap region hit". The JSON tap map is valid — tap regions are at x:20 y:650 w:506 h:320, and (193,824) is clearly inside that rectangle.

**Root cause:** The `hit_test` function in v2 tried `python3` first (via `command -v python3`). The Kindle had a python3 binary that `command -v` found, but it failed silently when executed (likely missing modules or ABI mismatch). The awk fallback was also broken — it ran awk twice (once for exit code, once for output) and the output capture was lost in a subshell.

**Debugging steps:**
1. Read the viewer log: `cat /Volumes/Kindle/documents/kindle-dash/viewer.log`
2. Saw "ERROR: No image path in JSON" — this meant the JSON parsing failed
3. Checked if `home.json.tmp` existed and was valid JSON — it was
4. Realized `jq` was not installed on Kindle (confirmed: `ls /Volumes/Kindle/usr/bin/jq` → not found)
5. Tested the awk parser locally against the actual JSON — it worked correctly
6. Realized the v2 `hit_test` function's subshell structure was losing the awk output

**Fix (v3):** Rewrote `hit_test` to:
- Use pure awk (no python3, no jq)
- Echo the result to stdout (not set globals)
- Caller captures with `hit_result=$(hit_test "$tx" "$ty")`
- Parse the result with `awk '{print $1}'` and `awk '{print $2}'`

The working awk JSON parser for tap regions:
```awk
BEGIN { x=y=w=h=act=tgt="" }
/"x"/ { gsub(/.*"x"[[:space:]]*:[[:space:]]*/, ""); gsub(/[^0-9-].*/, ""); x=$0 }
/"y"/ { gsub(/.*"y"[[:space:]]*:[[:space:]]*/, ""); gsub(/[^0-9-].*/, ""); y=$0 }
/"w"/ { gsub(/.*"w"[[:space:]]*:[[:space:]]*/, ""); gsub(/[^0-9-].*/, ""); w=$0 }
/"h"/ { gsub(/.*"h"[[:space:]]*:[[:space:]]*/, ""); gsub(/[^0-9-].*/, ""); h=$0 }
/"action"/ { gsub(/.*"action"[[:space:]]*:[[:space:]]*"/, ""); gsub(/".*/, ""); act=$0 }
/"target"/ { gsub(/.*"target"[[:space:]]*:[[:space:]]*"/, ""); gsub(/".*/, ""); tgt=$0 }
/}/ && x != "" {
    if (tx+0 >= x+0 && tx+0 < x+0+w+0 && ty+0 >= y+0 && ty+0 < y+0+h+0) {
        print act " " tgt; exit 0
    }
    x=y=w=h=act=tgt=""
}
```

## Failure 3: JSON Fetch Left .tmp File

**Symptom:** `home.json.tmp` exists but `home.json` doesn't. The curl fetch succeeded (JSON content is valid) but the atomic rename never happened.

**Root cause:** The script fetched JSON successfully, then tried `jq -r '.image'` to parse the image path. jq failed (not installed), so `image_path` was empty, the function returned 1 (error), and the `mv` from `.tmp` to final name never executed.

**Fix:** Use `grep -o` + `sed` for simple JSON field extraction instead of jq:
```sh
json_str() {
    grep -o "\"$2\"[[:space:]]*:[[:space:]]*\"[^\"]*\"" "$1" 2>/dev/null | head -1 | sed "s/.*\"$2\"[[:space:]]*:[[:space:]]*\"//;s/\"$//"
}
```

## Failure 4: EVIOCGABS Returns 0-0 on PW4

**Symptom:** Touch helper log shows `touch_tap: found touch device at /dev/input/event2 (x:0-0 y:0-0)`. Despite this, taps report valid coordinates (934, 847, etc.).

**Root cause:** On the Paperwhite 4, `EVIOCGABS(ABS_X)` returns `absinfo.minimum=0, absinfo.maximum=0`. This means the touch driver reports **raw screen pixel coordinates** directly, not a hardware range (like 0-4095) that needs scaling. The original `scale()` function had `if (max <= min) return value;` which happened to pass through the raw value correctly — but the logic was fragile and the `has_range=1` flag was set despite the range being invalid.

**Fix in touch_tap.c:**
```c
static int scale(int value, int min, int max, int screen_size) {
    if (max <= min) {
        if (value < 0) return 0;
        if (value >= screen_size) return screen_size - 1;
        return value;
    }
    // ... normal scaling for devices that report hardware ranges
}
```

## Failure 5: Device Locked While Viewer Running

**Symptom:** While the interactive viewer is running, the power button doesn't put the Kindle to sleep, and tapping the screen doesn't open any Kindle UI. The device appears locked.

**Root cause:** Two things combine:
1. `lipc-set-prop com.lab126.powerd preventScreenSaver 1` — prevents the screensaver from kicking in, so power button can't sleep
2. `EVIOCGRAB(1)` in touch_tap — exclusive touch grab means the Kindle framework never sees touch events

**Fix:** This is expected behavior, not a bug. The KUAL menu must include a "Stop Dashboard" option that runs `stop.sh`:
```sh
killall -9 dash_interactive.sh 2>/dev/null
killall -9 touch_tap 2>/dev/null
lipc-set-prop com.lab126.powerd preventScreenSaver 0 2>/dev/null
```

For production: consider adding an idle timeout (e.g., after 2 hours of no taps, auto-exit and restore screensaver).

## Key Takeaways

1. **Always read the viewer log** — it contains every detail of what happened: touch coordinates, fetch results, error messages, hit/miss data
2. **Test JSON parsing locally** before deploying — run the awk command against the actual JSON file to verify it works
3. **Never assume tools exist on Kindle** — jq, python3, pip are all unreliable. Use awk/grep/sed for everything
4. **Shell subshells lose variables** — if a function captures output via `$(command)`, globals set inside don't propagate. Have the function echo its result and let the caller parse it
5. **EVIOCGABS behavior varies by device** — PW4 returns 0-0 (raw coords), other devices may return 0-4095 (hardware range needing scaling). Handle both cases
6. **The viewer locks the device** — always provide a stop mechanism (KUAL menu option, SSH kill, or idle timeout)
