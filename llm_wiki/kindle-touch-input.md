# Kindle Touch Input Handling on Jailbroken Devices

## Summary

Jailbroken Kindles expose touchscreen input through the Linux evdev interface at `/dev/input/event*`. Touch events follow the standard Linux input protocol (`struct input_event`), using `EV_ABS` with `ABS_X`/`ABS_Y` (single-touch) or `ABS_MT_POSITION_X`/`ABS_MT_POSITION_Y` (multi-touch) codes. A C or Python program can open these device files, read `input_event` structs, scale absolute touch coordinates to screen pixel coordinates, and map taps to UI regions. The kdashboard project demonstrates a complete C++ implementation of this pattern.

## Evdev Device Discovery

### Device Path Instability

Kindle touch input devices live at `/dev/input/event0`, `/dev/input/event1`, etc. However, **the event number can change between boot modes**. A MobileRead forum post by geekmaster documents that on the Kindle Touch, the touchscreen events appear at `/dev/input/event4` when booted to main, but `/dev/input/event3` when booted to diags mode.

> "I discovered that when I boot my touch to main and launch SSH using yifanlu's launcher menu, the touchscreen events are at /dev/input/event4... But when I boot diags and run SSH from the Enable USBnet menu, the touchscreen events are at /dev/input/event3."
> — [geekmaster, MobileRead Forums](https://www.mobileread.com/forums/showthread.php?t=171821)

**Correct approach:** Scan all `/dev/input/event*` devices (event0 through event15) and probe each one for `ABS_X`/`ABS_Y` or `ABS_MT_POSITION_X`/`ABS_MT_POSITION_Y` capability using `ioctl(fd, EVIOCGABS(code), &abs_info)`. Only open devices that report absolute touch coordinates.

### How kdashboard Discovers Devices

From `kindle_dashboard.cpp`, the `initTouchInput()` function:

```cpp
void initTouchInput(TouchInput* input) {
    memset(input, 0, sizeof(*input));
    input->x = -1;
    input->y = -1;
    for (int i = 0; i < 16 && input->count < 16; i++) {
        char path[48];
        snprintf(path, sizeof(path), "/dev/input/event%d", i);
        int fd = open(path, O_RDONLY | O_NONBLOCK);
        if (fd < 0) continue;

        TouchInput::Device* device = &input->devices[input->count];
        memset(device, 0, sizeof(*device));
        device->fd = fd;
        device->has_x_range = readAbsRange(fd, ABS_X, &device->min_x, &device->max_x) ||
            readAbsRange(fd, ABS_MT_POSITION_X, &device->min_x, &device->max_x);
        device->has_y_range = readAbsRange(fd, ABS_Y, &device->min_y, &device->max_y) ||
            readAbsRange(fd, ABS_MT_POSITION_Y, &device->min_y, &device->max_y);

        if (!device->has_x_range || !device->has_y_range) {
            close(fd);
            continue;
        }

        if (ioctl(fd, EVIOCGRAB, 1) == 0) device->grabbed = 1;
        input->count++;
    }
}
```

Key details:
- Opens devices with `O_RDONLY | O_NONBLOCK` (non-blocking reads)
- Probes for both single-touch (`ABS_X`/`ABS_Y`) and multi-touch (`ABS_MT_POSITION_X`/`ABS_MT_POSITION_Y`) ranges
- Uses `EVIOCGABS` ioctl to get min/max range for coordinate scaling
- Uses `EVIOCGRAB` to exclusively grab the device (prevents Kindle framework from also receiving events)

## Event Structure (evdev)

Each event is a `struct input_event` (from `<linux/input.h>`):

```c
struct input_event {
    struct timeval time;  // timestamp
    unsigned short type;   // event type (EV_ABS, EV_KEY, EV_SYN)
    unsigned short code;   // event code (ABS_X, ABS_Y, BTN_TOUCH, etc.)
    int value;             // event value
};
```

### Event Types Used

| Type | Code | Meaning |
|------|------|---------|
| `EV_ABS` (0x03) | `ABS_X` (0x00) | Single-touch X coordinate |
| `EV_ABS` | `ABS_Y` (0x01) | Single-touch Y coordinate |
| `EV_ABS` | `ABS_MT_POSITION_X` (0x35) | Multi-touch X coordinate |
| `EV_ABS` | `ABS_MT_POSITION_Y` (0x36) | Multi-touch Y coordinate |
| `EV_ABS` | `ABS_MT_TRACKING_ID` (0x39) | Multi-touch tracking ID (negative = finger lifted) |
| `EV_KEY` (0x01) | `BTN_TOUCH` (0x14a) | Touch contact state (1 = down, 0 = up) |
| `EV_KEY` | `BTN_LEFT` (0x110) | Alternative touch button code |
| `EV_SYN` (0x00) | `SYN_REPORT` (0x00) | Frame synchronization (end of event group) |

## Coordinate System Mapping

Touch hardware reports coordinates in a device-specific range (e.g., 0–4095), not screen pixels. The range is obtained via `EVIOCGABS` which fills `input_absinfo` with `.minimum` and `.maximum` fields.

### Scaling Formula

kdashboard's `scaleAbsValue()` function:

```cpp
int scaleAbsValue(int value, int minimum, int maximum, int screen_size) {
    if (maximum <= minimum || screen_size <= 1) return value;
    long scaled = (static_cast<long>(value - minimum) * static_cast<long>(screen_size - 1))
                  / static_cast<long>(maximum - minimum);
    if (scaled < 0) scaled = 0;
    if (scaled >= screen_size) scaled = screen_size - 1;
    return static_cast<int>(scaled);
}
```

Formula: `screen_pixel = (raw_value - min) * (screen_size - 1) / (max - min)`

Screen dimensions are obtained from the framebuffer (`/dev/fb0` via `FBIOGET_VSCREENINFO`), typically 1072×1448 on Paperwhite 3 or 758×1024 on older models.

### Rotation/Coordinate Flip

The Kindle may report touch coordinates in a different orientation than the display. kdashboard handles this by trying multiple coordinate transformations when a tap misses all defined regions:

```cpp
if (!applyTouchAt(x, y) &&
    !applyTouchAt(w - 1 - x, y) &&
    !applyTouchAt(x, h - 1 - y) &&
    !applyTouchAt(w - 1 - x, h - 1 - y) &&
    !applyTouchAt((y * w) / h, (x * h) / w) &&
    // ... more rotations)
```

This tries: identity, X-flip, Y-flip, both-flip, 90° rotation, and combinations — covering all possible orientation mismatches.

## Reading Touch Events in C

### pollExitTouch() — kdashboard's Event Loop

```cpp
int pollExitTouch(TouchInput* input) {
    for (int i = 0; i < input->count; i++) {
        TouchInput::Device* device = &input->devices[i];
        while (1) {
            input_event event;
            const ssize_t bytes = read(device->fd, &event, sizeof(event));
            if (bytes != sizeof(event)) break;

            if (event.type == EV_ABS) {
                if (event.code == ABS_X || event.code == ABS_MT_POSITION_X) {
                    input->x = scaleAbsValue(event.value, device->min_x, device->max_x, screen_width);
                    input->has_x = 1;
                    input->was_down = 1;
                } else if (event.code == ABS_Y || event.code == ABS_MT_POSITION_Y) {
                    input->y = scaleAbsValue(event.value, device->min_y, device->max_y, screen_height);
                    input->has_y = 1;
                    input->was_down = 1;
                } else if (event.code == ABS_MT_TRACKING_ID) {
                    input->was_down = event.value >= 0 ? 1 : 0;
                }
            } else if (event.type == EV_KEY && (event.code == BTN_TOUCH || event.code == BTN_LEFT)) {
                if (event.value > 0) input->was_down = 1;
                if (event.value == 0 && input->was_down && input->has_x && input->has_y) {
                    // Touch release → process tap
                    applyTouchWithDebounce(input);
                }
            } else if (event.type == EV_SYN && input->has_x && input->has_y) {
                // Synchronization frame → process tap
                applyTouchWithDebounce(input);
            }
        }
    }
    return 0;
}
```

The function runs in a separate thread (`startTouchWatcher` → `touchWatcherMain`) that polls every 250ms:

```cpp
void* touchWatcherMain(void* raw) {
    while (g_running) {
        pollExitTouch(touch);
        usleep(250000);
    }
}
```

### Touch Debouncing

kdashboard applies a 700ms debounce between touch actions to prevent rapid double-triggering:

```cpp
int applyTouchWithDebounce(TouchInput* input) {
    const long now = nowMs();
    if (now - input->last_action_ms < 700) return 0;
    // ... map coordinates to touch regions ...
    input->last_action_ms = now;
    return 1;
}
```

### Touch Region Mapping

Touch regions are defined as rectangles (`Rect {x, y, w, h}`) with associated actions. The `applyTouchAt(x, y)` function checks if coordinates fall within any registered `TouchRegion` and sets `g_pending_action` accordingly.

## Reading Touch Events in Python

### evdev Library Availability

The `python-evdev` library is **not included by default** on Kindle firmware. However:

- **Python 2.7** can be installed via the [MobileRead Python package](https://www.mobileread.com/forums/showthread.php?t=195474) or KUAL extension
- **Python 3.8** is available as a KUAL extension for Paperwhite 3 and similar devices (see [4DCu.be Kindle dashboard tutorial](https://blog.4dcu.be/diy/2020/10/04/PythonKindleDashboard_2.html))
- The `evdev` Python package requires compiling a C extension against kernel headers, which is impractical on the Kindle itself

### Alternative: Raw File Reading in Python

Since `evdev` is hard to install, you can read `/dev/input/event*` directly using `struct`:

```python
import struct
import os

# input_event is: timeval (16 bytes: 8+8) + type (2) + code (2) + value (4) = 24 bytes
# On 32-bit ARM Kindle: timeval is 8+4 = 12 bytes, so total = 16 bytes
EVENT_FORMAT = 'iiHHi'  # time_sec, time_usec, type, code, value
EVENT_SIZE = struct.calcsize(EVENT_FORMAT)

fd = os.open('/dev/input/event1', os.O_RDONLY)
while True:
    data = os.read(fd, EVENT_SIZE)
    if len(data) == EVENT_SIZE:
        _, _, ev_type, ev_code, ev_value = struct.unpack(EVENT_FORMAT, data)
        if ev_type == 0x03:  # EV_ABS
            if ev_code == 0x00:  # ABS_X
                print(f"X={ev_value}")
            elif ev_code == 0x01:  # ABS_Y
                print(f"Y={ev_value}")
        elif ev_type == 0x01 and ev_code == 0x14a:  # BTN_TOUCH
            print(f"Touch: {'down' if ev_value else 'up'}")
```

**Important:** The `struct input_event` size differs between 32-bit and 64-bit systems. Kindles use 32-bit ARM (EABI5), so `timeval` is `{long tv_sec, long tv_usec}` = 4+4 = 8 bytes, making the struct 16 bytes total (not 24 as on 64-bit). The format string should be `'iiHHi'` (4+4+2+2+4 = 16).

## Multi-touch vs Single-touch

Kindle touchscreens may report using either protocol:

- **Single-touch (`ABS_X`/`ABS_Y` + `BTN_TOUCH`):** Simpler, one contact point at a time. Common on older Kindle models.
- **Multi-touch (`ABS_MT_POSITION_X`/`ABS_MT_POSITION_Y` + `ABS_MT_TRACKING_ID`):** Protocol B (Type B), tracks individual contacts. The `ABS_MT_TRACKING_ID` value of -1 indicates finger lift.

kdashboard handles both by checking for both sets of codes and treating `ABS_MT_TRACKING_ID >= 0` as "finger down" and `< 0` as "finger up". For a dashboard application, only single-tap detection is needed — no gesture or multi-touch tracking is required.

## Key Takeaways for the Kindle Dashboard Project

1. **Scan all `/dev/input/event*` devices** — don't hardcode an event number
2. **Use `EVIOCGABS` to get coordinate ranges** and scale to screen pixels
3. **Use `EVIOCGRAB`** to prevent the Kindle framework from processing touches simultaneously
4. **Handle coordinate rotation** — the touch coordinate system may not match display orientation
5. **C is preferred for touch handling** on Kindle due to direct access to `ioctl`, `read()`, and `struct input_event`; Python requires manual `struct.unpack` and careful handling of the 32-bit ABI
6. **Debounce taps** (kdashboard uses 700ms) to prevent accidental double-triggering on e-ink which has slow refresh

## Related Wiki Files

- [kindle-wake-detection.md](kindle-wake-detection.md) — How to detect sleep/wake transitions
- [kindle-python-availability.md](kindle-python-availability.md) — Python runtime and library options on Kindle
- [kindle-networking.md](kindle-networking.md) — Network connectivity for fetching dashboard data

## Sources

- [kdashboard GitHub repo](https://github.com/thecodedose/kdashboard) — `kindle/native/src/kindle_dashboard.cpp`
- [MobileRead: Kindle input event device file names can CHANGE](https://www.mobileread.com/forums/showthread.php?t=171821)
- [Kernel.org: Input event codes](https://docs.kernel.org/input/event-codes.html)
- [python-evdev documentation](https://python-evdev.readthedocs.io/en/latest/tutorial.html)
- [4DCu.be: Kindle + Python e-Ink Dashboard](https://blog.4dcu.be/diy/2020/10/04/PythonKindleDashboard_2.html)
