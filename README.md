# Kindle E-Ink Dashboard

A server-driven e-ink dashboard on a jailbroken Kindle. The Kindle is a dumb display — a server generates PNG images + JSON tap maps, the Kindle fetches and displays them. A tiny C touch helper reads evdev input for tap navigation.

**Proven on Kindle Paperwhite 4 (10th Gen, 2018)** — 6" 300 PPI e-ink, capacitive touch, WiFi, jailbroken with WinterBreak + KUAL.

## Current State

**Verified working end-to-end on real hardware.** Full pipeline confirmed via on-device logs — every button navigates correctly, back/exit work, and a full power-button sleep → wake cycle returns to the dashboard cleanly:
- Python view server renders PNG + tap map over HTTP
- Kindle shell viewer fetches, displays via `eips`, routes taps
- C touch helper provides exclusive evdev reading (EVIOCGRAB)
- Power button sleep/wake lifecycle (Kindle sleeps naturally, wakes to dashboard)
- Offline cache — network down → last view stays on screen
- Clean exit to Kindle home

The ready-to-copy KUAL extension bundle (`config.xml` + `menu.json` + `bin/`) lives in [`spike/kindle-dash/`](spike/kindle-dash/) — see Quick Start below.

**Not yet built:**
- MCP server (multi-agent data push — see [DECISIONS.md](DECISIONS.md) D02/D03)
- Tailscale mesh networking (remote access beyond LAN)
- Custom screensaver (abandoned — linkss unsupported on FW 5.16+)

## Architecture

```
Server (Python)               Kindle (shell + C)
┌──────────────┐            ┌──────────────────┐
│ View Server   │  HTTP LAN  │ dash_interactive.sh│
│ (Pillow PNG)  │───────────▶│ • curl fetch PNG   │
│ + tap map JSON│            │ • eips -f -g display│
│               │            │ • awk parse taps    │
│ Data sources  │  pipe:x y  │ • hit test → navigate│
│ → PIL render  │◀───────────│                     │
│ → PNG + JSON  │            └──────┬─────────────┘
└──────────────┘                   │ FIFO: "x y\n"
                            ┌──────┴─────────────┐
                            │ touch_tap (C, 50ln) │
                            │ • EVIOCGRAB         │
                            │ • evdev /dev/input  │
                            │ • prints tap coords │
                            └────────────────────┘
```

**Core principle:** Kindle is dumb, server is smart. New screens = new Python functions, not Kindle code changes.

## Quick Start

### Server (Mac/PC)

```sh
# Requires Python 3.11+ with Pillow
pip install Pillow

# Start view server
python3 spike/view_server.py

# Verify
curl http://localhost:8888/health
curl http://localhost:8888/view?path=home
```

### Kindle

1. **Update the server IP** in `spike/kindle-dash/menu.json` — replace `YOUR_SERVER_IP` with your server's LAN IP (the `params` field passed to `dash_interactive.sh`).

2. **Copy the KUAL extension** (Kindle mounted via USB as a mass-storage volume):
```sh
cp -r spike/kindle-dash/ /Volumes/Kindle/extensions/kindle-dash/
chmod +x /Volumes/Kindle/extensions/kindle-dash/bin/*.sh /Volumes/Kindle/extensions/kindle-dash/bin/touch_tap

# CRITICAL: Clean macOS resource fork files — they break KUAL
find /Volumes/Kindle/extensions/kindle-dash -name '._*' -delete
```

3. Eject the Kindle, unplug, then **launch via KUAL** → Kindle Dashboard → Start Dashboard (interactive).

### Cross-Compiling touch_tap (only if you need to rebuild)

```sh
# Install Zig
curl -sL https://ziglang.org/download/0.13.0/zig-macos-aarch64-0.13.0.tar.xz -o /tmp/zig.tar.xz
cd /tmp && tar xf zig.tar.xz

# Cross-compile for Kindle ARM — `-s` strips symbols (no debug info, no build-path leakage)
/tmp/zig-macos-aarch64-0.13.0/zig cc -target arm-linux-musleabi -O2 -static -s -o touch_tap spike/touch_tap.c

# Verify
file touch_tap  # Should show: ELF 32-bit LSB executable, ARM, EABI5, statically linked, stripped
```

A pre-compiled, stripped `spike/touch_tap` binary is included — you only need to recompile if you modify `touch_tap.c`. Always build with `-s`: an unstripped binary embeds the absolute build path (including your local username) in plain text, recoverable with `strings touch_tap`.

## Repository Structure

```
├── spike/          # Battle-tested working code (v4 final)
│   ├── kindle-dash/         # Ready-to-copy KUAL extension bundle
│   │   ├── config.xml       # KUAL metadata (correct <information>/<menus> tags)
│   │   ├── menu.json        # KUAL menu — set your server IP here
│   │   └── bin/              # dash_interactive.sh, touch_tap, stop.sh, show_static.sh
│   ├── dash_interactive.sh  # Main viewer (touch + sleep/wake + navigation)
│   ├── touch_tap.c          # C touch helper source
│   ├── touch_tap            # Pre-compiled, stripped ARM binary
│   ├── view_server.py       # Python HTTP view server
│   ├── dash_viewer.sh       # Simple display-only loop
│   ├── stop.sh              # Cleanup script
│   ├── menu.json            # KUAL menu config (reference — use kindle-dash/menu.json to deploy)
│   └── fix_linker.sh        # FW 5.16+ ld-linux.so.3 symlink fix
├── llm_wiki/       # Research knowledge base (17 interlinked files)
├── skill/          # Agent skill — operational knowledge for AI assistants
│   ├── SKILL.md              # 39KB of hard-won Kindle development lessons
│   ├── references/           # 12 deep-dive reference docs
│   └── templates/            # Generalized code templates
├── DECISIONS.md    # Architecture Decision Records (3 ADRs)
├── POSTMORTEM-2026-07-24.md  # Code review failure — read before modifying working code
├── LOG.md          # Development chronicle
└── IDEA.md         # Project pitch and design rationale
```

## Knowledge Base

The `llm_wiki/` folder contains 17 interlinked research files covering everything learned during development:

- **Platform:** Kindle PW4 hardware, firmware, limitations, Python availability
- **Touch:** evdev, EVIOCGRAB, coordinate scaling, debounce
- **Power:** sleep/wake lifecycle, LIPC events, flag files, phantom tap draining
- **Rendering:** framebuffer, eips, PNG format, Pillow pipeline
- **Networking:** WiFi quirks, 2.4GHz only, wake reconnect timing
- **KUAL:** Extension packaging, config.xml format, menu.json
- **Screensaver:** linkss hack, FW 5.16 incompatibility, alternatives
- **Architecture:** view protocol, C-vs-shell comparison, similar projects
- **MCP:** Multi-agent server design (future direction)

## Development Notes

### Before modifying working code — read the postmortem

`POSTMORTEM-2026-07-24.md` documents a session where a code review found 29 "issues" in working code, "fixed" them all, and broke everything. Key lessons:
- Test every change on hardware — `sh -n` is not enough
- One fix at a time — deploy, test, confirm, then next
- Keep the original — always preserve the last-working version
- Theoretical bugs < working code — if it works, don't fix it
- Don't recompile a working binary without a specific demonstrated bug

### Architecture decisions

See `DECISIONS.md` for the three ADRs:
- **D01:** Hybrid shell + C touch helper (not full C, not Python on Kindle)
- **D02:** Dashboard as MCP server (multi-agent data push)
- **D03:** MCP server design — typed view types, fixed home grid, no polling

## Future Directions

### MCP Server

The dashboard is designed to evolve from a single-server model to a multi-agent MCP server. Each agent pushes data to a designated card slot on the home view via `update_view(path, data)`. The MCP renders PNGs using builtin Pillow renderers per view type. Cronjobs trigger updates — agents don't sit in loops.

Full design spec: `llm_wiki/mcp-server-design.md` and `skill/references/mcp-server-design.md`.

### Tailscale Mesh Networking

Currently the Kindle connects to the server over local WiFi (2.4GHz only on PW4). A future direction is running Tailscale on both the Kindle and the server, creating a mesh VPN that allows the dashboard to work from any network — not just home LAN.

The Kindle runs ARM Linux, so Tailscale's ARM binary (userspace WireGuard) may work. Research needed on:
- Tailscale ARM binary compatibility with Kindle's musl-based userspace
- Performance impact on e-ink display refresh latency
- Sleep/wake behavior with VPN tunnel active

## Hardware Requirements

| Component | Spec |
|---|---|
| Kindle | Paperwhite 4 (10th Gen, 2018) |
| Screen | 6" Carta E-Ink, 300 PPI, 1448×1072 |
| Touch | Capacitive touchscreen |
| WiFi | 2.4GHz only |
| Jailbreak | WinterBreak + KUAL installed |
| Server | Any machine running Python 3.11+ with Pillow, reachable on LAN |

## Acknowledgments

- [kdashboard](https://github.com/thecodedose/kdashboard) — Kindle e-ink dashboard with C++ renderer, inspiration for the server-driven inversion
- [MobileRead forums](https://www.mobileread.com/) — Kindle modding community, linkss, KUAL, firmware knowledge
- [NiLuJe](https://www.mobileread.com/forums/member.php?u=57856) — linkss, KUAL, and Kindle modding tools