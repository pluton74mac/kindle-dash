# Kindle Platform Reference

Condensed technical reference for building apps on jailbroken Kindles. Extracted from a deep research run on 2026-07-16 (MobileRead forums, kindlemodding.org, kdashboard source, Kindle internals blog posts).

## Models for Dashboard Use

| Model | Nickname | Resolution | PPI | Touch | Jailbreak | Status Bar Height |
|-------|----------|-----------|-----|-------|-----------|-------------------|
| Kindle Basic (7th-10th Gen) | KT2-BASIC4 | 800×600 | 167 | Yes | WinterBreak2 | ~66px |
| Paperwhite 1-2 | PW1-PW2 | 758×1024 | 212 | Yes | WinterBreak2 | ~66px |
| Paperwhite 3-5 | PW3-PW5 | 1072×1448 | 300 | Yes | WinterBreak2/WinterBreak | ~66px |
| Kindle Voyage | KV | 1072×1448 | 300 | Yes | WinterBreak2 | ~66px |
| Oasis 1 | KOA | 1072×1448 | 300 | Yes | WinterBreak2 | ~66px |
| Oasis 2-3 | KOA2-KOA3 | 1264×1680 | 300 | Yes | WinterBreak2 | ~66px |
| Kindle Touch | K5 | 608×800 | 167 | Yes | Legacy K5 JB | ~66px |
| Kindle 4 (non-touch) | K4 | 600×800 | 167 | No | Legacy K4 JB | N/A |

**Best picks:** PW3 (300 PPI, touch, cheap used, WinterBreak2). PW5 if newer firmware.

## E-Ink Display

### Framebuffer
- Device: `/dev/fb0`
- Pixel format: 8 bpp (1 byte/pixel, 256 levels) on Touch+. 4 bpp on K1-K3.
- Physical panel: 16 grayscale levels (hardware), 8-bit framebuffer is quantized by display controller.
- 0 = black, 255 = white

### Key ioctls
| Constant | Hex | Function |
|----------|-----|----------|
| FBIOGET_VSCREENINFO | 0x4600 | Get resolution, bpp |
| FBIOGET_FSCREENINFO | — | Get line_length |
| FBIO_EINK_CLEAR_SCREEN | 0x46e1 | Clear display |
| FBIO_EINK_UPDATE_DISPLAY | 0x46db | Trigger refresh (0=partial, 1=full) |

### Refresh trigger after framebuffer write
```sh
# Kindle Touch+ — the only reliable method:
eips '' >/dev/null 2>&1

# Older Kindles (K4 and prior):
echo 1 > /proc/eink_fb/update_display
```

### eips Command Reference
```
eips ''                        # Trigger display update from framebuffer
eips -c                        # Clear screen (full refresh)
eips [col] [row] [-h] "text"   # Print text (40 cols × 50 rows grid on Touch)
eips -g image.png [-w wf -f -x N -y N -v]  # Display PNG/JPG
eips -b bitmap                 # Display raw bitmap
eips -i                       # Print framebuffer info (bpp, bytes/line)
eips -q                       # Paint checker pattern
eips -l                       # Paint grayscale gradient
```

Waveform modes (`-w` flag): `gc16` (default, 16-gray with flash), `gl16` (16-gray partial), `du` (1-bit fast).
`-f` = full refresh (visible flash, clears ghosting). Default = partial (smooth, accumulates ghosting).

### PGM Format (for native renderers)
```
P5\n
<width> <height>\n
255\n
<raw 8-bit grayscale pixels>
```
kdashboard uses P5 binary PGM for all image assets. Trivial to write in C:
```c
fprintf(file, "P5\n%d %d\n255\n", width, height);
fwrite(pixels, 1, width * height, file);
```

## KUAL Extension Format

### Required Files
```
/mnt/us/extensions/<name>/
├── config.xml    # Metadata + menu pointer
├── menu.json     # Menu structure (valid JSON required by KUAL2)
├── bin/          # Scripts and binaries
├── assets/       # Images, fonts
└── config.sh     # User configuration (optional)
```

### config.xml
```xml
<?xml version="1.0" encoding="UTF-8"?>
<extension>
    <information>
        <name>My Extension</name>
        <version>1.0</version>
        <author>Author</author>
        <id>my-extension</id>
    </information>
    <menus>
        <menu type="json" dynamic="true">menu.json</menu>
    </menus>
</extension>
```

### menu.json Keys
| Key | Required | Description |
|-----|----------|-------------|
| `name` | Yes | Button/submenu label |
| `action` | Yes (items) | Shell command (e.g., `/bin/sh`) |
| `params` | No | Args appended to action |
| `priority` | No | Sort order (default 0, negative ok) |
| `exitmenu` | No | `true` = close KUAL after; `false` = stay |
| `if` | No | RPN conditional (model checks, file existence) |
| `items` | Yes (submenus) | Array of child items |

Actions run in background, working directory = where menu.json lives. stderr → KUAL.log.

### Shell launcher pattern (from kdashboard)
- Source `config.sh` if present
- Copy native binary from `/mnt/us` to `/tmp` (FAT32 may block exec)
- Launch with `nohup ... &` for background operation
- Store PID in a pidfile at `/mnt/us/documents/`
- `stop` action: kill by PID, re-enable sleep

### Packaging
```makefile
# Build tarball that extracts to /mnt/us/extensions/<name>/
tar -C $(EXTENSION_ROOT) -czf extension.tar.gz <name>
```
Install: `tar -C /mnt/us/extensions -xzf extension.tar.gz`

### Cross-compilation
```makefile
# ARM cross-compiler (static link):
arm-linux-gnueabi-g++ -std=c++17 -static -o kindle-dashboard src.cpp

# Zig (easiest, no toolchain install):
zig c++ -target arm-linux-musleabi -static -s -o kindle-dashboard src.cpp
```

## Power Management

### State Machine
```
Active (10 min) → Screen Saver (1 min) → Ready to Suspend (5 sec) → Sleep
```
Check: `/usr/bin/powerd_test -s`

### Key LIPC Commands
```sh
# Keep awake (primary method for dashboards):
lipc-set-prop com.lab126.powerd preventScreenSaver 1

# Re-enable sleep:
lipc-set-prop com.lab126.powerd preventScreenSaver 0

# Wake from sleep:
lipc-set-prop com.lab126.powerd wakeUp 1

# Enable WiFi:
lipc-set-prop com.lab126.cmd wirelessEnable 1

# Check battery:
lipc-get-prop com.lab126.powerd battLevel
lipc-get-prop com.lab126.powerd isCharging
```

### com.lab126.powerd Properties
| Property | Access | Description |
|----------|--------|-------------|
| preventScreenSaver | rw | 1=prevent sleep, 0=allow |
| deferSuspend | w | Defer during Ready-to-Suspend (only works in that state) |
| wakeUp | w | 1=wake from sleep |
| touchScreenSaverTimeout | rw | Reset screensaver timer |
| isCharging | r | Charging status |
| battLevel | r | Battery % |
| state | r | Current power state |

### com.lab126.wifid (WiFi control)
```sh
lipc-set-prop com.lab126.cmd wirelessEnable 1           # Enable WiFi
lipc-get-prop com.lab126.wifid cmState                  # Connection state
lipc-get-prop com.lab126.wifid signalStrength           # Signal
lipc-set-prop com.lab126.wifid cmConnect <ssid>         # Connect to profile
```
WiFi drops when Kindle sleeps. With preventScreenSaver=1, WiFi stays active.

### Battery estimates
- **Stay-awake mode (preventScreenSaver=1):** ~1-2 days (WiFi always on)
- **Sleep + RTC wake every 60 min:** ~1-2 weeks
- **Sleep + manual power-button wake:** weeks to months

## Touch Input

- Devices: `/dev/input/event0` through `event15` (scan all)
- Look for `ABS_X`/`ABS_Y` or `ABS_MT_POSITION_X`/`ABS_MT_POSITION_Y` via `EVIOCGABS`
- Use `EVIOCGRAB` to exclusively grab touch (prevents Kindle framework from also receiving)
- Scale: `screen_pixel = (raw - min) * (screen_size - 1) / (max - min)`
- kdashboard uses 700ms debounce between touch actions
- Max 32 touch regions tracked simultaneously

## File Paths
- `/mnt/us/` — USB-accessible user storage (FAT32)
- `/mnt/us/extensions/` — KUAL extensions install here
- `/mnt/us/documents/` — Logs, caches, pidfiles
- `/tmp/` — Writable RAM (copy binaries here before exec)
- `/dev/fb0` — Framebuffer device
- `/usr/sbin/eips` — E-ink display command
- `/usr/bin/lipc-set-prop` / `lipc-get-prop` — LIPC IPC commands

## Sources
- [kindlemodding.org](https://kindlemodding.org/kindle-models.html) — Model/jailbreak reference
- [MobileRead Wiki - Eips](https://wiki.mobileread.com/wiki/Eips) — eips command docs
- [MobileRead Wiki - KUAL](https://wiki.mobileread.com/wiki/KUAL_What%27s_New) — Extension format
- [MobileRead Wiki - Lipc](https://wiki.mobileread.com/wiki/Lipc) — LIPC properties
- [geekmaster MobileRead](https://www.mobileread.com/forums/showthread.php?t=162743) — Framebuffer details
- [SixFoisNeuf](https://www.sixfoisneuf.fr/posts/kindle-hacking-deeper-dive-internals/) — strace/ioctl analysis
- [sirpoot MobileRead](https://www.mobileread.com/forums/showthread.php?t=221497) — Power state machine
- [lidskialf blog](https://blog.lidskialf.net/2021/02/08/turning-an-old-kindle-into-a-eink-development-platform/) — WiFi/root access
