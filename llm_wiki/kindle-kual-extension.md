# Kindle KUAL Extension

> KUAL (Kindle Unified Application Launcher) extension structure, packaging, and the kdashboard project's approach to building and installing a KUAL extension.

## Summary

KUAL is the standard mechanism for launching homebrew applications on jailbroken Kindles. An extension is a directory under `/mnt/us/extensions/` containing two required files: `config.xml` (metadata) and `menu.json` (menu structure). Shell scripts or native binaries are launched by KUAL when the user selects a menu item. The kdashboard project packages its native C++ renderer, shell launchers, PGM assets, and configuration into a tar.gz that unpacks to the correct `/mnt/us/extensions/kindle-dashboard/` directory structure.

**Related:** [Kindle Platform Overview](kindle-platform-overview.md) | [Kindle Framebuffer Rendering](kindle-framebuffer-rendering.md) | [Kindle Power Management](kindle-power-management.md)

---

## What is KUAL?

KUAL (Kindle Unified Application Launcher) is a launcher application that provides buttons and menus for running homebrew on jailbroken Kindles. It runs on any Kindle with firmware ≥ 2.3 (with caveats on specific models). Extensions plug into KUAL by placing a directory with `config.xml` and `menu.json` under `/mnt/us/extensions/`.

### Installation Methods

| Method | Device | Installation |
|--------|--------|-------------|
| **PEKI** | K5+ (modern) | Copy `KUAL.sh` and `KUAL.jar` to `documents/` folder |
| **KDK-2.0 azw2** | K5+ (older method) | Copy `.azw2` file to `documents/` folder |
| **KDK-1.0 azw2** | K1–K4 | Copy `.azw2` file to `documents/` folder |
| **Booklet** | KOA/KT3+ | Install via MRPI (`;log mrpi` command) |

> **Sources:** [kindlemodding.org - Installing KUAL](https://kindlemodding.org/jailbreaking/post-jailbreak/installing-kual-mrpi/), [KUAL MobileRead thread](https://www.mobileread.com/forums/showthread.php?t=203326)

---

## Extension Directory Structure

A KUAL extension lives as a subdirectory under `/mnt/us/extensions/`. The required structure:

```
/mnt/us/extensions/
└── <extension-name>/
    ├── config.xml          # Required: metadata + menu file pointer
    ├── menu.json           # Required: menu structure (JSON)
    ├── bin/                # Optional: scripts and binaries
    │   ├── start.sh
    │   ├── stop.sh
    │   └── ...
    ├── assets/             # Optional: images, fonts, etc.
    │   └── ...
    └── config.sh           # Optional: user configuration
```

KUAL scans `/mnt/us/extensions/` (default search depth: 2 levels) looking for `config.xml` files. When found, it reads the `<menu>` tag to locate the `menu.json` file.

> **Source:** [MobileRead Wiki - KUAL What's New](https://wiki.mobileread.com/wiki/KUAL_What%27s_New)

---

## config.xml Format

The `config.xml` file declares the extension's metadata and points to the menu file:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<extension>
    <information>
        <name>Kindle Dashboard</name>
        <version>1.0</version>
        <author>Codex</author>
        <id>kindle-dashboard</id>
    </information>
    <menus>
        <menu type="json" dynamic="true">menu.json</menu>
    </menus>
</extension>
```

| Tag | Description |
|-----|-------------|
| `<name>` | Display name of the extension |
| `<version>` | Version string |
| `<author>` | Author name |
| `<id>` | Unique extension identifier |
| `<menu type="json">` | Path to the menu.json file (relative to config.xml location) |
| `dynamic="true"` | Enables dynamic menu reloading |

> **Note:** KUAL2 only considers the `<menu>` tag value when `type="json"`. The kdashboard uses `dynamic="true"` to allow menu refresh.

> **Source:** kdashboard `config.xml`, [MobileRead Wiki - KUAL What's New](https://wiki.mobileread.com/wiki/KUAL_What%27s_New)

---

## menu.json Format

The `menu.json` defines the menu structure as nested JSON. KUAL2 requires valid JSON (rejects invalid syntax).

### Structure

```json
{
  "items": [
    {
      "name": "Submenu Name",
      "priority": 10,
      "items": [
        {
          "name": "Button Label",
          "priority": 1,
          "action": "/bin/sh",
          "params": "/path/to/script.sh",
          "exitmenu": true
        }
      ]
    }
  ]
}
```

### Action Item Keys

| Key | Required | Description |
|-----|----------|-------------|
| `name` | Yes | Button label displayed in KUAL |
| `action` | Yes (for action items) | Shell command to execute (e.g., `/bin/sh`) |
| `params` | No | Parameters appended to `action` |
| `priority` | No | Numeric sort order (default 0; negative is valid) |
| `exitmenu` | No | `true` = close KUAL after action; `false` = stay in menu (default: exits) |
| `internal` | No | Internal KUAL command (`breadcrumb`, `status`) |
| `if` | No | RPN conditional expression — item shown only if true |
| `checked` | No | `true` = show checkmark after press |
| `refresh` | No | `true` = reload menu after action (for dynamic menus) |
| `status` | No | `false` = don't show action in status line |
| `date` | No | `true` = show date/time in status line |

### Sub-menu Keys

| Key | Description |
|-----|-------------|
| `name` | Sub-menu label |
| `priority` | Sort order |
| `items` | Array of child items (action items or nested sub-menus) |

> **Source:** [MobileRead Wiki - KUAL What's New - Action Items](https://wiki.mobileread.com/wiki/KUAL_What%27s_New#Action_Items)

### Template

KUAL2 uses **Template 1** (deprecated Template 2 wraps the top-level in a `name` key that KUAL2 ignores). Only the `items` array at the top level is read.

### Actions Run In

Actions execute as background processes in the working directory where `menu.json` is located. Unredirected stderr goes to `/mnt/us/extensions/KUAL.log`.

---

## kdashboard's KUAL Extension

### Directory Layout

```
/mnt/us/extensions/kindle-dashboard/
├── config.xml              # Extension metadata
├── menu.json               # Menu structure
├── config.sh.example       # Template config (user copies to config.sh)
├── config.sh               # User-created config (not in package)
├── assets/
│   ├── meal-planner-cover.pgm
│   ├── challenge-75-day.pgm
│   ├── profile-placeholder.pgm
│   └── recipes/            # Recipe PGM images
└── bin/
    ├── kindle-dashboard        # Native ARM binary (C++ renderer)
    ├── start.sh                # Start wrapper
    ├── start-light.sh          # Start with light theme
    ├── start-dark.sh           # Start with dark theme
    ├── once.sh                 # One-shot render (light)
    ├── once-light.sh           # One-shot render (light)
    ├── once-dark.sh            # One-shot render (dark)
    ├── stop.sh                 # Stop wrapper
    ├── dashboard.sh            # Main launcher script
    ├── diagnose.sh             # Diagnostic tool
    ├── proof.sh                # Proof-of-concept render
    └── menu-ping.sh            # Menu sanity check
```

### menu.json (kdashboard)

```json
{
  "items": [
    {
      "name": "Kindle Dashboard",
      "priority": 10,
      "items": [
        {
          "name": "Start Dashboard (Light)",
          "priority": 1,
          "action": "/bin/sh",
          "params": "/mnt/us/extensions/kindle-dashboard/bin/start-light.sh",
          "exitmenu": true
        },
        {
          "name": "Start Dashboard (Dark)",
          "priority": 2,
          "action": "/bin/sh",
          "params": "/mnt/us/extensions/kindle-dashboard/bin/start-dark.sh",
          "exitmenu": true
        },
        {
          "name": "Refresh Once (Light)",
          "priority": 3,
          "action": "/bin/sh",
          "params": "/mnt/us/extensions/kindle-dashboard/bin/once-light.sh",
          "exitmenu": false
        },
        {
          "name": "Refresh Once (Dark)",
          "priority": 4,
          "action": "/bin/sh",
          "params": "/mnt/us/extensions/kindle-dashboard/bin/once-dark.sh",
          "exitmenu": false
        },
        {
          "name": "Stop Dashboard",
          "priority": 5,
          "action": "/bin/sh",
          "params": "/mnt/us/extensions/kindle-dashboard/bin/stop.sh",
          "exitmenu": false
        }
      ]
    }
  ]
}
```

> **Source:** kdashboard `menu.json`

---

## Shell Launchers

### start.sh (wrapper)

```sh
#!/bin/sh
DASHBOARD="/mnt/us/extensions/kindle-dashboard/bin/dashboard.sh"
LOG="/mnt/us/documents/kindle-dashboard-kual-action.log"
echo "kindle-dashboard start wrapper $(date '+%Y-%m-%d %H:%M:%S')" >> "$LOG"
/bin/sh "$DASHBOARD" start >> "$LOG" 2>&1
```

### dashboard.sh (main launcher)

The `dashboard.sh` script is the core launcher with `start`, `stop`, and `once` actions:

```sh
#!/bin/sh
CONFIG="${DASHBOARD_CONFIG:-/mnt/us/extensions/kindle-dashboard/config.sh}"
[ -f "$CONFIG" ] && . "$CONFIG"

# Source config values
DASHBOARD_DATA_URL="${DASHBOARD_DATA_URL:-}"
# ... other config vars

# Power management functions
keep_awake() {
    lipc-set-prop com.lab126.powerd preventScreenSaver 1 >/dev/null 2>&1 || true
}

allow_sleep() {
    lipc-set-prop com.lab126.powerd preventScreenSaver 0 >/dev/null 2>&1 || true
}

enable_wifi() {
    lipc-set-prop com.lab126.cmd wirelessEnable 1 >/dev/null 2>&1 || true
}

# Start action
start_dashboard() {
    stop_existing_processes
    # Copy native binary to /tmp (writable, not on USB)
    cp "$NATIVE_APP" "$RUN_APP"
    chmod 755 "$RUN_APP"
    
    if [ "$DASHBOARD_KEEP_AWAKE" = "1" ]; then
        keep_awake
    else
        allow_sleep
    fi
    enable_wifi
    
    # Launch native app in background with nohup
    nohup "$RUN_APP" \
        --url "$DASHBOARD_DATA_URL" \
        --events-url "$DASHBOARD_EVENTS_URL" \
        --toggle-url "$DASHBOARD_TOGGLE_URL" \
        --read-token "$DASHBOARD_READ_TOKEN" \
        --toggle-token "$DASHBOARD_TOGGLE_TOKEN" \
        --cache "$CACHE" \
        --interval "$INTERVAL" \
        --sleep-window "$DASHBOARD_SLEEP_WINDOW" \
        $image_args $save_args >> "$LOG" 2>&1 &
    echo "$!" > "$PIDFILE"
}

case "$1" in
    start) start_dashboard ;;
    once) # One-shot render with --once flag ;;
    stop) stop_dashboard ;;
esac
```

Key patterns:
- **Config sourcing:** `config.sh` is sourced if present, providing user-specific URLs and tokens
- **Binary copy to /tmp:** The native binary is copied from `/mnt/us` (USB FAT32) to `/tmp` (writable RAM) before execution, because the FAT32 partition may have no-execute flags
- **PID file:** Process PID stored at `/mnt/us/documents/kindle-dashboard-native.pid`
- **Background launch:** Uses `nohup` + `&` for long-running dashboard mode

### stop.sh

```sh
#!/bin/sh
DASHBOARD="/mnt/us/extensions/kindle-dashboard/bin/dashboard.sh"
/bin/sh "$DASHBOARD" stop >> "$LOG" 2>&1
```

The stop action in `dashboard.sh` kills the running process and re-enables screen saver:
```sh
stop_dashboard() {
    stop_existing_processes
    allow_sleep
}
```

> **Source:** kdashboard `bin/dashboard.sh`, `bin/start.sh`, `bin/stop.sh`

---

## config.sh Pattern

The config file is the user's entry point for customization:

```sh
# config.sh.example — copy to config.sh and edit
DASHBOARD_DATA_URL="https://your-project.insforge.app/functions/kindle-dashboard-data"
DASHBOARD_EVENTS_URL="https://your-project.function2.insforge.app/kindle-dashboard-events"
DASHBOARD_TOGGLE_URL="https://your-project.insforge.app/functions/kindle-dashboard-toggle"
DASHBOARD_READ_TOKEN="replace-with-your-generated-read-token"
DASHBOARD_TOGGLE_TOKEN="replace-with-your-generated-toggle-token"

# Always-on defaults
INTERVAL="3600"
DASHBOARD_KEEP_AWAKE="1"
DASHBOARD_SLEEP_WINDOW="off"
# DASHBOARD_TIMEZONE="Asia/Kolkata"
INVERT_IMAGES="0"
```

| Variable | Default | Description |
|----------|---------|-------------|
| `DASHBOARD_DATA_URL` | (required) | URL to fetch dashboard JSON |
| `DASHBOARD_EVENTS_URL` | (optional) | SSE endpoint for live updates |
| `DASHBOARD_TOGGLE_URL` | (optional) | URL to toggle items |
| `DASHBOARD_READ_TOKEN` | (optional) | Auth token for read endpoints |
| `DASHBOARD_TOGGLE_TOKEN` | (optional) | Auth token for toggle endpoints |
| `INTERVAL` | `3600` | Seconds between auto-refresh |
| `DASHBOARD_KEEP_AWAKE` | `1` | `1` = prevent screen saver; `0` = allow sleep |
| `DASHBOARD_SLEEP_WINDOW` | `off` | Time window to go quiet (e.g., `"23:00-07:00"`) |
| `DASHBOARD_TIMEZONE` | (unset) | Override timezone (`TZ` env var) |
| `INVERT_IMAGES` | `0` | `1` = invert image polarity (dark mode) |

> **Source:** kdashboard `config.sh.example`

---

## Packaging and Installation

### Building the Extension (Makefile)

The kdashboard Makefile builds the extension as a tar.gz:

```makefile
extension: $(KINDLE_TARGET)
    rm -rf $(EXTENSION_ROOT)
    mkdir -p $(EXTENSION_DIR)/bin
    mkdir -p $(EXTENSION_DIR)/assets
    # Copy config files
    cp ../kual/kindle-dashboard/config.xml $(EXTENSION_DIR)/config.xml
    cp ../kual/kindle-dashboard/config.sh.example $(EXTENSION_DIR)/config.sh.example
    cp ../kual/kindle-dashboard/menu.json $(EXTENSION_DIR)/menu.json
    # Copy assets
    cp ../kual/kindle-dashboard/assets/*.pgm $(EXTENSION_DIR)/assets/
    # Copy scripts
    cp ../kual/kindle-dashboard/bin/*.sh $(EXTENSION_DIR)/bin/
    # Copy native binary
    cp $(KINDLE_TARGET) $(EXTENSION_DIR)/bin/kindle-dashboard
    chmod +x $(EXTENSION_DIR)/bin/*.sh $(EXTENSION_DIR)/bin/kindle-dashboard
    # Create tarball
    tar -C $(EXTENSION_ROOT) -czf $(EXTENSION_ARCHIVE) kindle-dashboard
```

### Cross-Compilation

The native binary is compiled for ARM (Kindle's architecture):

| Method | Compiler | Target |
|--------|----------|--------|
| **ARM cross-compiler** | `arm-linux-gnueabi-g++` | Static binary for Kindle |
| **Zig** | `zig c++ -target arm-linux-musleabi` | Static binary via Zig's cross-compilation |

Both produce statically-linked binaries (no shared library dependencies on the Kindle).

```makefile
# ARM cross-compiler
$(KINDLE_CXX) $(CXXFLAGS) -static -o $@ $<

# Zig cross-compiler
$(ZIG) c++ -target $(ZIG_TARGET) $(CXXFLAGS) $(ZIG_LDFLAGS) -s -o $@ $<
```

> **Source:** kdashboard `kindle/native/Makefile`

### Installation Steps

1. **Build the extension package:**
   ```sh
   make kindle        # or: make kindle-zig
   make extension     # or: make extension-zig
   ```

2. **Copy the tarball to the Kindle** via USB:
   ```sh
   # The Kindle appears as a USB mass storage device at /mnt/us
   cp build/kindle-dashboard-kual.tar.gz /media/<kindle>/
   ```

3. **Extract on the Kindle:**
   ```sh
   # Via SSH or terminal on the Kindle:
   cd /mnt/us
   tar xzf kindle-dashboard-kual.tar.gz
   # This creates /mnt/us/extensions/kindle-dashboard/
   ```

4. **Create config:**
   ```sh
   cp /mnt/us/extensions/kindle-dashboard/config.sh.example \
      /mnt/us/extensions/kindle-dashboard/config.sh
   vi /mnt/us/extensions/kindle-dashboard/config.sh
   # Edit URLs and tokens
   ```

5. **Launch via KUAL:**
   - Open KUAL from the Kindle library
   - Select "Kindle Dashboard" → "Start Dashboard (Light)"
   - The dashboard launches in the background

### Uninstallation

```sh
# Stop the dashboard first
/mnt/us/extensions/kindle-dashboard/bin/stop.sh

# Remove the extension
rm -rf /mnt/us/extensions/kindle-dashboard

# Remove cache and logs
rm -f /mnt/us/documents/kindle-dashboard-*
```

---

## See Also

- [Kindle Platform Overview](kindle-platform-overview.md) — Compatible models and specs
- [Kindle Framebuffer Rendering](kindle-framebuffer-rendering.md) — How the native binary renders to screen
- [Kindle Power Management](kindle-power-management.md) — `preventScreenSaver` and sleep control
- [MobileRead Wiki - KUAL](https://wiki.mobileread.com/wiki/KUAL)
- [MobileRead Wiki - KUAL What's New](https://wiki.mobileread.com/wiki/KUAL_What%27s_New)
