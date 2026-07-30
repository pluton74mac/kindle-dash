# Kindle Power Management

> Kindle power states, screensaver prevention, powerd LIPC properties, idle timeout configuration, and WiFi sleep behavior for always-on dashboard applications.

## Summary

Kindle devices have a multi-level power state machine: Active → Screen Saver → Ready to Suspend → Sleep. The `com.lab126.powerd` LIPC service controls these transitions. Dashboard applications prevent the screen from sleeping by setting `lipc-set-prop com.lab126.powerd preventScreenSaver 1`. WiFi can be enabled via `lipc-set-prop com.lab126.cmd wirelessEnable 1`. The kdashboard project manages power state in its launcher scripts, keeping the Kindle awake while the dashboard runs and re-enabling sleep when stopped.

**Related:** [Kindle Platform Overview](kindle-platform-overview.md) | [Kindle Framebuffer Rendering](kindle-framebuffer-rendering.md) | [Kindle KUAL Extension](kindle-kual-extension.md)

---

## Power State Machine

The Kindle has four distinct power states, managed by the `powerd` daemon:

| State | Duration | Description |
|-------|----------|-------------|
| **Active** | ~10 minutes (default) | Full operation, screen on, WiFi active |
| **Screen Saver** | ~1 minute | Screensaver image displayed, still responsive |
| **Ready to Suspend** | ~5 seconds | Final grace period before sleep |
| **Sleep** | Until wake event | Full suspend, WiFi off, only power button wakes |

### State Transitions

```
Active (10 min idle) → Screen Saver (1 min) → Ready to Suspend (5 sec) → Sleep
     ↑                                                          ↓
     └────────────────── Power button / cover open ───────────────┘
```

The `powerd_test -s` command shows the current state:

```
[root@kindle root]# /usr/bin/powerd_test -s
Powerd state: Active
Remaining time in this state: 581.725642
defer_suspend:1
suspend_grace:0
prevent_screen_saver:0
Battery Level: 88%
Charging: No
```

> **Source:** [sirpoot on MobileRead](https://www.mobileread.com/forums/showthread.php?t=221497)

---

## The `com.lab126.powerd` LIPC Service

### Key Properties

| Property | Access | Type | Description |
|----------|--------|------|-------------|
| `preventScreenSaver` | rw | Int | `1` = prevent screensaver/sleep; `0` = allow |
| `deferSuspend` | w | Int | Defer sleep during "Ready to Suspend" state (seconds) |
| `wakeUp` | w | Int | `1` = wake from sleep/screensaver |
| `touchScreenSaverTimeout` | rw | Int | Reset screensaver timer |
| `suspendGrace` | w | Int | Grace period before suspend |
| `abortSuspend` | w | Int | Abort a pending suspend |
| `rtcWakeup` | w | Int | Set RTC wake alarm |
| `isCharging` | r | Int | Whether device is charging |
| `battLevel` | r | Int | Battery level percentage |
| `state` | r | Str | Current power state |
| `status` | r | Str | Power status summary |
| `addSuspendLevels` | w | Int | Add suspend levels |

> **Sources:** [MobileRead Wiki - Lipc](https://wiki.mobileread.com/wiki/Lipc#com.lab126.powerd), [SixFoisNeuf Kindle internals](https://www.sixfoisneuf.fr/posts/kindle-hacking-deeper-dive-internals/)

### Events

The `com.lab126.powerd` service emits events for power state changes. These can be monitored via `lipc-wait-event`:

```
com.lab126.powerd
  Events:
    (power state change events)
```

---

## Preventing Screen Sleep

### The Primary Method

```sh
lipc-set-prop com.lab126.powerd preventScreenSaver 1
```

This prevents the Kindle from entering the Screen Saver state, keeping it in Active mode indefinitely. The kdashboard uses this in its `keep_awake()` function:

```sh
keep_awake() {
    lipc-set-prop com.lab126.powerd preventScreenSaver 1 >/dev/null 2>&1 || true
}
```

### Re-enabling Sleep

```sh
lipc-set-prop com.lab126.powerd preventScreenSaver 0
```

The kdashboard calls this when stopping:

```sh
allow_sleep() {
    lipc-set-prop com.lab126.powerd preventScreenSaver 0 >/dev/null 2>&1 || true
}
```

### When to Call

- **On dashboard start:** Call `keep_awake` before launching the native app
- **On dashboard stop:** Call `allow_sleep` after killing the native process
- **On one-shot render:** Call `keep_awake`, render, then `allow_sleep` when done

The kdashboard's `dashboard.sh` `start` action:
```sh
if [ "$DASHBOARD_KEEP_AWAKE" = "1" ]; then
    keep_awake
else
    allow_sleep
fi
```

And `stop` action:
```sh
stop_dashboard() {
    stop_existing_processes
    allow_sleep
}
```

> **Source:** kdashboard `bin/dashboard.sh`

---

## The `deferSuspend` Property

The `deferSuspend` property can extend the "Ready to Suspend" state, but it can **only be set during that state** (a ~5 second window after ~11 minutes of idle time). Attempting to set it during Active or Screen Saver states returns an error.

```sh
# This works only during "Ready to Suspend" state:
lipc-set-prop com.lab126.powerd deferSuspend 3000000
```

This is useful for applications that want to allow the screensaver to display but prevent full sleep (e.g., to maintain SSH connectivity). For dashboard use, `preventScreenSaver 1` is the simpler and more reliable approach.

> **Source:** [sirpoot on MobileRead](https://www.mobileread.com/forums/showthread.php?t=221497)

---

## Screensaver Timeout Configuration

### touchScreenSaverTimeout

```sh
# Reset the screensaver timer (extends active time by resetting the countdown)
lipc-set-prop com.lab126.powerd -i touchScreenSaverTimeout 1
```

This resets the idle timer to keep the device in Active state longer. It does not change the timeout duration — it just restarts the countdown.

### Idle Timeout

The default idle timeout is approximately 10 minutes for the Active state. This is configured by the Kindle system and may vary by model/firmware. The `preventScreenSaver` property is the most reliable way to override this for always-on applications.

> **Source:** [MobileRead forum - screensaver timer](https://www.mobileread.com/forums/showthread.php?t=337314)

---

## Detecting Power Button Wake

### Wake Events

When the Kindle wakes from sleep (via power button press or cover open), the `powerd` service transitions from Sleep → Active. Applications can detect wake events by:

1. **Monitoring LIPC events:** Use `lipc-wait-event com.lab126.powerd <event_name>` to wait for power state change events.

2. **Polling power state:** Periodically check `powerd_test -s` or `lipc-get-prop com.lab126.powerd state`.

3. **Input device monitoring:** The power button also generates input events on `/dev/input/event0` (on some models). The kdashboard's touch input system scans all `/dev/input/eventN` devices.

### Waking the Kindle Programmatically

```sh
lipc-set-prop com.lab126.powerd wakeUp 1
```

This wakes the Kindle from Sleep or Screen Saver state. Useful for scheduled updates — e.g., an RTC alarm could wake the Kindle to fetch fresh dashboard data.

### RTC Wakeup

```sh
lipc-set-prop com.lab126.powerd rtcWakeup <seconds>
```

Sets a real-time clock alarm to wake the Kindle after a specified number of seconds. Could be used for periodic dashboard refreshes without keeping the device awake continuously.

---

## WiFi Power Management

### Enabling WiFi

```sh
lipc-set-prop com.lab126.cmd wirelessEnable 1
```

The kdashboard calls this on startup to ensure WiFi is active before fetching dashboard data:

```sh
enable_wifi() {
    lipc-set-prop com.lab126.cmd wirelessEnable 1 >/dev/null 2>&1 || true
}
```

### WiFi Sleep Behavior

WiFi is disabled when the Kindle enters Sleep state. When `preventScreenSaver 1` is set, the Kindle stays in Active state, so WiFi remains active.

If the Kindle does sleep and wakes, WiFi may need to be re-enabled. The kdashboard's `launch-dashboard.sh` includes a network wait loop:

```sh
wait_for_network() {
    attempts=0
    while [ "$attempts" -lt 24 ]; do
        if ping -c 1 -W 2 1.1.1.1 >/dev/null 2>&1; then
            return 0
        fi
        attempts=$((attempts + 1))
        sleep 5
    done
    return 0
}
```

### WiFi-Related LIPC Properties (`com.lab126.wifid`)

| Property | Access | Description |
|----------|--------|-------------|
| `enable` | rw | Enable/disable WiFi |
| `currentEssid` | r | Current SSID |
| `signalStrength` | r | WiFi signal strength |
| `cmState` | r | Connection manager state |
| `profileCount` | r | Number of WiFi profiles |
| `createProfile` | rw | Create a WiFi profile |
| `cmConnect` | w | Connect to a profile |
| `cmDisconnect` | w | Disconnect |
| `scan` | w | Trigger WiFi scan |

WiFi profile management:
```sh
# Create a WiFi profile
echo '{essid="MySSID", smethod="wpa2", secured="yes", psk="hashed_psk"}' | \
    lipc-hash-prop com.lab126.wifid createProfile

# Connect
lipc-set-prop com.lab126.wifid cmConnect MySSID
```

> **Sources:** [MobileRead Wiki - Lipc](https://wiki.mobileread.com/wiki/Lipc#com.lab126.wifid), [lidskialf blog](https://blog.lidskialf.net/2021/02/08/turning-an-old-kindle-into-a-eink-development-platform/), kdashboard `launch-dashboard.sh`

---

## kdashboard Power Management Integration

### Start Flow

```
KUAL menu → start-light.sh → dashboard.sh start →
    keep_awake()          # preventScreenSaver 1
    enable_wifi()         # wirelessEnable 1
    wait_for_network()    # ping loop
    nohup native_app &    # launch renderer in background
```

### Stop Flow

```
KUAL menu → stop.sh → dashboard.sh stop →
    kill native_app       # stop the renderer
    allow_sleep()         # preventScreenSaver 0
```

### One-Shot Flow

```
KUAL menu → once-light.sh → dashboard.sh once →
    keep_awake()          # preventScreenSaver 1
    enable_wifi()         # wirelessEnable 1
    native_app --once     # single render, then exit
    allow_sleep()         # preventScreenSaver 0
```

### Sleep Window Feature

The kdashboard supports a configurable sleep window (e.g., `"23:00-07:00"`) via `DASHBOARD_SLEEP_WINDOW`:

```c
if (inSleepWindow(options.sleep_start_minute, options.sleep_end_minute)) {
    // Render "quiet hours" view from cache
    // Wait for wake event or manual refresh
}
```

During the sleep window, the dashboard:
- Renders a minimal "quiet hours" view
- Does not fetch new data
- Waits for either the window to end or a manual refresh trigger
- Does NOT call `preventScreenSaver` (the Kindle can sleep naturally during this period if `DASHBOARD_KEEP_AWAKE=0`)

> **Source:** kdashboard `kindle_dashboard.cpp` main loop, `launch-dashboard.sh`

---

## Returning to Kindle Home

When the dashboard exits (via touch on the exit button), it restores the Kindle's default state:

```c
void returnToKindleHome() {
    system(
        "lipc-set-prop com.lab126.powerd preventScreenSaver 0 >/dev/null 2>&1 || true; "
        "lipc-set-prop com.lab126.appmgrd start app://com.lab126.booklet.home >/dev/null 2>&1 || "
        "lipc-set-prop com.lab126.appmgrd start app://com.lab126.booklet.home/ >/dev/null 2>&1 || true; "
        "sleep 1; "
        "eips '' >/dev/null 2>&1 || true"
    );
}
```

This:
1. Re-enables screen saver
2. Launches the Kindle home booklet
3. Triggers a screen refresh

> **Source:** kdashboard `kindle_dashboard.cpp` `returnToKindleHome()`

---

## Battery Considerations

The `com.lab126.powerd` service exposes battery info:

```sh
lipc-get-prop com.lab126.powerd battLevel    # Battery percentage
lipc-get-prop com.lab126.powerd isCharging   # 1 if charging
```

For an always-on dashboard:
- **With `preventScreenSaver 1`:** The Kindle stays in Active state, consuming more power. WiFi stays on. Battery life: ~1-2 days depending on model and refresh frequency.
- **With sleep windows:** The Kindle can sleep during configured hours, extending battery life significantly.
- **With periodic RTC wake:** Use `rtcWakeup` to wake every N minutes, refresh, then sleep. Most power-efficient for periodic dashboards.

---

## See Also

- [Kindle Platform Overview](kindle-platform-overview.md) — Hardware specs and models
- [Kindle Framebuffer Rendering](kindle-framebuffer-rendering.md) — Screen rendering during awake periods
- [Kindle KUAL Extension](kindle-kual-extension.md) — How the dashboard is launched
- [MobileRead Wiki - Lipc](https://wiki.mobileread.com/wiki/Lipc)
- [MobileRead - Kindle suspend levels](https://www.mobileread.com/forums/showthread.php?t=221497)
