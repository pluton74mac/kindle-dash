# Kindle Wake Detection and Sleep/Power Management

## Summary

Jailbroken Kindles transition through four power states (Active → Screen Saver → Ready to Suspend → Sleep). The `com.lab126.powerd` LIPC service emits events for each transition, accessible via the `lipc-wait-event` command-line tool. Applications can detect wake events, prevent sleep using `deferSuspend` or `preventScreenSaver`, and schedule RTC-based wake-ups. A long-running process (C or Python daemon) survives the screensaver state and can detect wake by polling power state or subscribing to LIPC events.

## Kindle Power States

The Kindle power daemon (`powerd`) manages four distinct power states, documented via `powerd_test -s`:

| State | Duration | Description |
|-------|----------|-------------|
| **Active** | ~10 minutes | Normal operation, screen on, WiFi on |
| **Screen Saver** | ~1 minute | Screensaver displayed, WiFi still on, SSH stays alive |
| **Ready to Suspend** | ~5 seconds | Final grace period before deep sleep |
| **Sleep** | Indefinite | Deep sleep (suspend-to-RAM), WiFi off, minimal power |

> Source: [MobileRead Forums: Kindle touch suspend levels](https://www.mobileread.com/forums/showthread.php?t=221497)

### State Transitions

```
Active → Screen Saver → Ready to Suspend → Sleep
                                         ↑
                                    (power button or RTC alarm)
```

- Active → Screen Saver: automatic after 10 minutes of inactivity
- Screen Saver → Ready to Suspend: automatic after ~1 minute
- Ready to Suspend → Sleep: automatic after ~5 seconds
- Sleep → Active: triggered by power button press, USB connect, or RTC alarm

## Detecting Power Events with LIPC

### lipc-wait-event

The `lipc-wait-event` command-line tool subscribes to LIPC events from `com.lab126.powerd`:

```bash
lipc-wait-event -m "com.lab126.powerd" "*"
```

Output (observed on a real device):

```
[11:28:12.711741] goingToScreenSaver 2     # Power button pressed (sleep)
[11:28:17.554321] t1TimerReset
[11:28:17.580866] outOfScreenSaver 1       # Power button pressed (wake)
[11:28:24.081409] goingToScreenSaver 2
[11:28:27.298605] outOfScreenSaver 1
[11:29:27.421299] charging                  # Charger connected
[11:30:20.656191] battLevelChanged 21      # Battery level changed
```

> Source: [blog.davidv.dev: Integrating a Kindle into house automation](https://blog.davidv.dev/posts/integrating-a-kindle-into-house-automation/)

### Key Power Events

| Event | Meaning |
|-------|---------|
| `goingToScreenSaver` | Device entering screensaver state (power button pressed or timeout) |
| `outOfScreenSaver` | Device waking from screensaver (power button pressed) |
| `charging` | Charger connected |
| `battLevelChanged` | Battery level changed (value = percentage) |
| `t1TimerReset` | Activity timer reset (user interaction detected) |

### WiFi Events (com.lab126.wifid)

```bash
lipc-wait-event -m "com.lab126.wifid" "*"
```

Relevant events: `cmConnected`, `cmDisconnected`, `cmStateChange`, `scanning`, `scanComplete`

## Polling Power State

### Using powerd_test

```bash
/usr/bin/powerd_test -s
```

Returns current state and remaining time:

```
Powerd state: Active
Remaining time in this state: 581.725642
defer_suspend:1
...
```

### Using /var/log/messages

Power state transitions are logged to `/var/log/messages`:

```
powerd[1096]: I def:statech:prev=ACTIVE, next=SCREEN SAVER:State change: ACTIVE -> SCREEN SAVER
powerd[1096]: I def:statech:prev=SCREEN SAVER, next=READY TO SUSPEND:State change: SCREEN SAVER -> READY TO SUSPEND
```

This can be tailed in a script:

```bash
grep SCREEN /var/log/messages | while read -r line; do
    # process state change
done
```

> Source: [blog.davidv.dev](https://blog.davidv.dev/posts/integrating-a-kindle-into-house-automation/) — notes that this approach is fragile because WiFi shuts off during sleep, so messages may not be delivered immediately.

## Preventing Sleep

### preventScreenSaver

```bash
lipc-set-prop com.lab126.powerd preventScreenSaver 1
```

Prevents the device from entering screensaver mode. Must be set to 0 when the app exits:

```bash
lipc-set-prop com.lab126.powerd preventScreenSaver 0
```

kdashboard uses this on exit to return the Kindle to normal behavior:

```cpp
void returnToKindleHome() {
    system("lipc-set-prop com.lab126.powerd preventScreenSaver 0 >/dev/null 2>&1 || true; "
           "lipc-set-prop com.lab126.appmgrd start app://com.lab126.booklet.home >/dev/null 2>&1 || true");
}
```

### deferSuspend

During the "Ready to Suspend" state (5-second window), you can extend the grace period:

```bash
lipc-set-prop com.lab126.powerd deferSuspend 3000000
```

This sets the remaining suspend time to ~3 million seconds (~35 days), effectively preventing deep sleep. This only works during the "Ready to Suspend" state — attempting it in other states returns `lipcErrNoSuchProperty`.

### Disabling Deep Sleep (~ds command)

Typing `~ds` in the Kindle search bar and pressing enter **disables automatic deep sleep** entirely. This is the simplest approach for a always-on dashboard:

> "Normally, after 10 minutes of inactivity, a Kindle goes into deep sleep, without the wakeup timer enabled. This needs to be disabled, otherwise each time the Dashboard wakes up for ~45 seconds to refresh its data, the clock is ticking... and once 10 minutes have passed in total the Kindle goes into deep sleep permanently until the power button is pressed."
> — [4DCu.be Kindle Dashboard Tutorial](https://blog.4dcu.be/diy/2020/10/04/PythonKindleDashboard_2.html)

## RTC-Based Wake Alarms

The Kindle has an RTC (real-time clock) that can trigger wake from deep sleep via `/sys/class/rtc/rtc1/wakealarm`:

```bash
# Clear any existing alarm
echo "" > /sys/class/rtc/rtc1/wakealarm

# Set alarm for N seconds from now
echo "+3600" > /sys/class/rtc/rtc1/wakealarm

# Enter deep sleep until alarm triggers
echo mem > /sys/power/state
```

This is the pattern used by periodic dashboard refresh scripts: set a wake alarm, enter mem sleep, and when the RTC fires, the device wakes and the script continues.

## Does an App Process Survive Screensaver?

### Short Answer: Yes, through Screen Saver and Ready to Suspend states

SSH connections and running processes **survive** through the Active, Screen Saver, and Ready to Suspend states (total ~11 minutes). Only when the device enters full Sleep (suspend-to-RAM) are processes frozen.

> "My SSH connection will not drop as long as the state is Active, Screen Saver or Ready to Suspend."
> — [MobileRead Forums](https://www.mobileread.com/forums/showthread.php?t=221497)

### During Deep Sleep

When the Kindle enters `echo mem > /sys/power/state` (deep sleep/suspend-to-RAM):
- All processes are frozen
- WiFi disconnects
- The process resumes when the device wakes (power button or RTC alarm)
- A daemon process will continue execution from where it was frozen — it doesn't need to restart

### Detecting Wake in a Daemon

A long-running C/Python daemon can detect wake by:

1. **LIPC event subscription:** Run `lipc-wait-event` in a subprocess and watch for `outOfScreenSaver`
2. **Time gap detection:** Check `gettimeofday()` before and after a `sleep()` — if the gap is much larger than the sleep duration, the device was suspended
3. **Power state polling:** Periodically run `powerd_test -s` and check the state

Example Python pattern from [blog.davidv.dev](https://blog.davidv.dev/posts/integrating-a-kindle-into-house-automation/):

```python
import subprocess

def pub_event(source, events):
    comm = ['lipc-wait-event', '-m', source]
    comm.extend(events)
    s = subprocess.Popen(comm, stdout=subprocess.PIPE)
    for line in iter(s.stdout.readline, ""):
        line = line.strip()
        if 'goingToScreenSaver' in line:
            print('screen off')
        if 'outOfScreenSaver' in line:
            print('screen on')
```

## Hooking the Power Button Wake Event

The power button press triggers `outOfScreenSaver` via LIPC. There is no need to read `/dev/input/event*` for the power button specifically — the LIPC event is the cleanest hook.

However, the power button also generates an evdev event on a separate `/dev/input/event*` device (typically `EV_KEY` with code `KEY_POWER` = 116). This could be read if raw event handling is needed, but LIPC is the recommended approach.

## kdashboard's Approach to Sleep

kdashboard uses a **sleep window** feature rather than detecting actual device sleep:

```cpp
// Check if current time is within a configured sleep window (e.g., 00:00-08:00)
int inSleepWindow(int start_minute, int end_minute) {
    const int now = currentLocalMinute();
    if (start_minute < end_minute) return now >= start_minute && now < end_minute;
    return now >= start_minute || now < end_minute;
}
```

During the sleep window, it stops fetching new data and just waits. It doesn't actually put the device to sleep — it just avoids network activity during quiet hours. The `waitForWakeEvent()` function is a misnomer; it's actually just a timed wait loop that also checks for touch events and refresh flags:

```cpp
int waitForWakeEvent(const Options* options, int seconds, int allow_repaint) {
    for (int elapsed = 1; elapsed <= seconds && g_running; elapsed++) {
        if (g_pending_action != kTouchNone) {
            handlePendingTouch(options);
            // ...
        }
        if (g_event_refresh) return 1;
        sleep(1);
    }
    return 1;
}
```

## Key Takeaways for the Kindle Dashboard Project

1. **Use `lipc-wait-event` for wake detection** — subscribe to `com.lab126.powerd` events and watch for `outOfScreenSaver`
2. **Disable deep sleep with `~ds`** for an always-on dashboard, OR use RTC wake alarms for periodic refresh
3. **A daemon process survives screensaver** but freezes during deep sleep — it will resume on wake without restarting
4. **Use `preventScreenSaver`** if the dashboard should never sleep, or clear it on exit
5. **Time-gap detection** is a simple alternative: if `sleep(5)` takes 60 seconds, the device was suspended
6. **WiFi needs reconnection after wake** — the `com.lab126.wifid` `cmConnected` event signals WiFi is back

## Related Wiki Files

- [kindle-touch-input.md](kindle-touch-input.md) — Touch event handling on jailbroken Kindle
- [kindle-networking.md](kindle-networking.md) — Network connectivity after wake
- [kindle-python-availability.md](kindle-python-availability.md) — Running a Python daemon on Kindle

## Sources

- [MobileRead: Kindle touch suspend levels](https://www.mobileread.com/forums/showthread.php?t=221497)
- [MobileRead: Wake up from sleep](https://www.mobileread.com/forums/showthread.php?t=235821)
- [MobileRead: Online screensaver extension](https://www.mobileread.com/forums/showthread.php?t=236104)
- [MobileRead Wiki: LIPC](https://wiki.mobileread.com/wiki/Lipc)
- [blog.davidv.dev: Integrating a Kindle into house automation](https://blog.davidv.dev/posts/integrating-a-kindle-into-house-automation/)
- [4DCu.be: Kindle + Python Dashboard Part 2](https://blog.4dcu.be/diy/2020/10/04/PythonKindleDashboard_2.html)
- [kdashboard GitHub](https://github.com/thecodedose/kdashboard)
