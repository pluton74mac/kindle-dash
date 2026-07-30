# Python Availability on Jailbroken Kindles

## Summary

Stock Kindle firmware does not include Python. However, jailbroken Kindles can run Python via KUAL extensions: Python 2.7 (legacy) or Python 3.8+ (modern). The KUAL Python extension installs a self-contained Python binary under `/mnt/us/python/` (Python 2) or `/mnt/us/python3/` (Python 3). Available libraries are limited to the standard library unless manually installed. PIL/Pillow requires compilation against system libraries and is not trivially available. For a Kindle dashboard, Python can handle data fetching, JSON parsing, and image generation via SVG, but C/C++ is preferred for real-time touch input and framebuffer rendering.

## Stock Firmware

No Kindle firmware version ships with Python accessible to the user. The Kindle's own framework runs Java (CVM/JeVM) and native C code, but there is no `python` or `python3` binary in the standard PATH.

## Installing Python via KUAL

### Python 2.7 (Legacy)

The MobileRead community provides a Python 2.7 package as a KUAL extension:

- **Source:** [MobileRead Forums: Python for Kindle](https://www.mobileread.com/forums/showthread.php?t=195474)
- **Install path:** `/mnt/us/python/bin/python2.7`
- **Binary type:** ELF 32-bit LSB executable, ARM, EABI5, dynamically linked
- **Installed via:** MRPI (MobileRead Package Installer) — place the `.bin` file in `mrpackages/` and trigger via KUAL

```bash
[root@kindle root]# file /mnt/us/python/bin/python2.7
python2.7: ELF 32-bit LSB executable, ARM, EABI5 version 1 (SYSV), dynamically linked,
interpreter /lib/ld-linux.so.3, for GNU/Linux 2.6.31, stripped
```

> Source: [blog.davidv.dev](https://blog.davidv.dev/posts/integrating-a-kindle-into-house-automation/)

### Python 3.8 (Modern)

Python 3.8 is available as a KUAL extension for Kindle Paperwhite 3 and newer devices:

- **Install method:** Download the Python 3 KUAL extension, extract to `extensions/` folder on the Kindle's USB drive
- **Binary path:** Typically `/mnt/us/python3/bin/python3` or accessed via the KUAL menu launcher
- **Documented in:** [4DCu.be Kindle Dashboard Tutorial](https://blog.4dcu.be/diy/2020/10/04/PythonKindleDashboard_2.html)

> "Python 3.8 installed and all boilerplate code was added to have a way to start our script and launch it from KUAL."
> — [4DCu.be](https://blog.4dcu.be/diy/2020/10/04/PythonKindleDashboard_2.html)

### Installation Steps

1. Jailbreak the Kindle (using WinterBreak, WatchThis, or current exploit for the firmware version)
2. Install KUAL (Kindle Unified Application Launcher) and MRPI (MobileRead Package Installer)
3. Download the Python KUAL extension package (`.bin` file)
4. Copy to `mrpackages/` on the Kindle USB drive
5. Trigger installation via KUAL → MRPI → Install Python
6. Python binary becomes available at `/mnt/us/python/bin/python` or `/mnt/us/python3/bin/python3`

> Source: [KindleModding: Installing KUAL & MRPI](https://kindlemodding.org/jailbreaking/post-jailbreak/installing-kual-mrpi/)

## Available Libraries

### Standard Library (Available)

The KUAL Python extensions include the full standard library:

- `urllib` / `urllib.request` — HTTP requests (works for fetching data)
- `json` — JSON parsing
- `ssl` — TLS/SSL (with caveats, see below)
- `subprocess` — Running shell commands (lipc-wait-event, eips, fbink, curl)
- `struct` — Reading binary data (for raw evdev input reading)
- `os`, `sys`, `time`, `datetime` — Standard utilities
- `re` — Regular expressions
- `xml.etree.ElementTree` — XML parsing

### SSL/TLS Caveat

The Kindle Python installation may have outdated CA certificates. When using `urllib.request.urlopen()` with HTTPS, you may need to create an unverified SSL context:

```python
import ssl
import urllib.request

ssl_context = ssl._create_unverified_context()
with urllib.request.urlopen(url, context=ssl_context) as response:
    html = response.read()
```

> "One odd thing is that the ssl_context needs to be created and added to the request. While the code works fine on my computer without, it gives an error on the Kindle without this bit included."
> — [4DCu.be](https://blog.4dcu.be/diy/2020/10/04/PythonKindleDashboard_2.html)

### PIL/Pillow (Not Easily Available)

**PIL/Pillow is not included** in the standard KUAL Python extension. Installing it requires:

1. Cross-compiling Pillow against the Kindle's ARM architecture and its specific library versions
2. Matching the Python extension's ABI (e.g., CPython 3.8 ARM32)
3. Bundling the compiled `.so` file with the extension

This is **non-trivial** and most Kindle dashboard projects avoid PIL entirely. Instead, they use alternative approaches:

- **SVG + rsvg-convert:** Generate an SVG template, substitute tokens, convert to PNG using `rsvg-convert` (a separate binary that must be installed)
- **FBInk:** The framebuffer ink tool (`fbink`) can display PNG images directly
- **Custom C rendering:** kdashboard draws directly to the framebuffer in C++

### requests (Not Included)

The `requests` library is not included in the standard KUAL Python extension. Projects use `urllib` instead:

> "No additional packages will be used, so only the standard library will be used. Unfortunately, this means getting websites with urllib and regular expressions rather than requests and BeautifulSoup."
> — [4DCu.be](https://blog.4dcu.be/diy/2020/10/04/PythonKindleDashboard_2.html)

### evdev (Not Easily Available)

The `python-evdev` library requires compiling a C extension against kernel headers. It is not practical to install on the Kindle. See [kindle-touch-input.md](kindle-touch-input.md) for a raw `struct.unpack` alternative.

### Third-Party Tools Commonly Used

| Tool | Purpose | Availability |
|------|---------|-------------|
| `fbink` | Framebuffer ink — display images/text on e-ink screen | Install via KUAL extension |
| `rsvg-convert` | Convert SVG to PNG | Copy binary to `/var/tmp/` (USB drive is noexec) |
| `curl` | HTTP client | Included in Kindle firmware at `/usr/bin/curl` |
| `eips` | E-ink put string (text rendering) | Built-in Kindle command |
| `lipc-wait-event` | LIPC event subscription | Built-in Kindle command |
| `lipc-set-prop` | LIPC property setting | Built-in Kindle command |

## Performance Constraints

### CPU

- Kindle Paperwhite 3: Freescale i.MX6 1GHz single-core ARM Cortex-A9
- Kindle Paperwhite 11: Similar ARM class
- Python is significantly slower than C for rendering operations
- JSON parsing and HTTP fetching are fast enough in Python
- Image manipulation (pixel-by-pixel) is impractically slow in pure Python

### Memory

- ~256MB RAM on older models, 512MB on newer
- Python itself uses ~15-30MB
- Loading large images or datasets can be memory-constrained

### Storage

- `/mnt/us/` (USB-accessible partition): Main storage, but mounted **noexec** — binaries cannot be executed directly from here
- `/var/tmp/`: Executable, but contents are cleared on reboot
- Workaround: Copy binaries from `/mnt/us/` to `/var/tmp/` before execution

```bash
if [ ! -f /var/tmp/rsvg-convert ]; then
    cp -rf ./external/* /var/tmp
fi
export LD_LIBRARY_PATH=/var/tmp/rsvg-convert-lib:/usr/lib:/lib
/var/tmp/rsvg-convert-lib/rsvg-convert --background-color=white -o output.png input.svg
```

> Source: [4DCu.be](https://blog.4dcu.be/diy/2020/10/04/PythonKindleDashboard_2.html)

## Python Daemon vs. C: Which to Use?

### Python Daemon — Good For

- Periodic data fetching (every N minutes/hours)
- JSON parsing and data transformation
- SVG generation (text template substitution)
- LIPC event monitoring via `subprocess`
- Shell command orchestration (curl, eips, fbink)

### C/C++ — Good For

- Real-time touch input reading (evdev)
- Direct framebuffer rendering (mmap `/dev/fb0`)
- Long-running processes with minimal memory overhead
- Concurrent touch watching + event listening (pthreads)

### kdashboard's Choice: C++

kdashboard uses C++ for everything: touch input, framebuffer rendering, JSON parsing, HTTP fetching (via curl subprocess), and LIPC interaction. This gives maximum performance and direct hardware access but requires cross-compilation.

### Hybrid Approach (Recommended for the agent Dashboard)

1. **Python daemon** for data fetching, JSON processing, and orchestration
2. **C helper** (or direct `/dev/fb0` mmap) for framebuffer rendering
3. **Raw Python `struct.unpack`** for touch input (no `evdev` library needed)
4. **Shell commands** for LIPC events, eips, fbink

This avoids the complexity of cross-compiling a full C++ application while still handling touch and rendering.

## Running a Python Daemon on Kindle

### Launch via KUAL Extension

Create a KUAL extension with a shell launcher:

```bash
#!/bin/sh
cd "/mnt/us/extensions/dashboard/"
sleep 30  # Wait for WiFi
python3 ./bin/run.py
```

### Launch via Upstart (Persistent Service)

Create `/etc/upstart/automation.conf`:

```ini
start on started filesystems_userstore
stop on stopping filesystems

export LANG LC_ALL

pre-start script
  python /mnt/us/dashboard.py &
end script
```

> Source: [blog.davidv.dev](https://blog.davidv.dev/posts/integrating-a-kindle-into-house-automation/)

### Launch via cron

The Kindle may have `cron` available, though it doesn't run during deep sleep. Use RTC wake alarms for reliable periodic execution.

## Key Takeaways

1. **Python 3.8 is available** as a KUAL extension — sufficient for data fetching and orchestration
2. **PIL/Pillow is not easily available** — use SVG + rsvg-convert or C rendering instead
3. **Standard library only** — use `urllib` not `requests`, `re` not `BeautifulSoup`
4. **SSL requires workaround** — create unverified context for HTTPS
5. **noexec on /mnt/us** — copy executables to `/var/tmp/` to run them
6. **Python is viable for a daemon** but C is better for touch and rendering
7. **Hybrid approach** (Python orchestration + C/raw-binary rendering) is the sweet spot

## Related Wiki Files

- [kindle-touch-input.md](kindle-touch-input.md) — Reading touch events in Python using raw struct unpacking
- [kindle-wake-detection.md](kindle-wake-detection.md) — Python daemon wake detection via LIPC
- [kindle-networking.md](kindle-networking.md) — Network access from Python using urllib

## Sources

- [MobileRead: Python for Kindle](https://www.mobileread.com/forums/showthread.php?t=195474)
- [4DCu.be: Kindle + Python e-Ink Dashboard Part 2](https://blog.4dcu.be/diy/2020/10/04/PythonKindleDashboard_2.html)
- [4DCu.be: Kindle + Python e-Ink Dashboard Part 1](https://blog.4dcu.be/diy/2020/09/27/PythonKindleDashboard_1.html)
- [KindleModding: Installing KUAL & MRPI](https://kindlemodding.org/jailbreaking/post-jailbreak/installing-kual-mrpi/)
- [blog.davidv.dev: Integrating a Kindle into house automation](https://blog.davidv.dev/posts/integrating-a-kindle-into-house-automation/)
- [kdashboard GitHub](https://github.com/thecodedose/kdashboard)
