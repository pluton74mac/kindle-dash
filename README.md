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
- **Tailscale support (optional, additive)** — the Kindle reaches the server over Tailscale instead of a plain LAN IP, so the same setup works both at home and away. See [Tailscale Setup](#tailscale-setup-optional) below.

The ready-to-copy KUAL extension bundle (`config.xml` + `menu.json` + `bin/`) lives in [`spike/kindle-dash/`](spike/kindle-dash/) — see Quick Start below.

**Not yet built:**
- MCP server (multi-agent data push — see [DECISIONS.md](DECISIONS.md) D02/D03)
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

## Tailscale Setup (optional)

Lets the Kindle reach the server from any network, not just home WiFi — Tailscale automatically uses a direct connection when possible (e.g. both devices on the same LAN) and falls back to its relay network otherwise, so one config works everywhere. Purely additive: without it, everything above works exactly as described over plain LAN.

**Prerequisites:**
- A [Tailscale](https://tailscale.com) account, with the server machine already joined to your tailnet.
- A Tailscale KUAL extension installed on the Kindle. This repo doesn't bundle one — [mitanshu7/tailscale_kual](https://github.com/mitanshu7/tailscale_kual) is the one this was built and tested against (three daemon modes, an installer, KUAL menu; see also [Tailscale's own writeup](https://tailscale.com/blog/tailscale-jailbroken-kindle)). Install it to `/mnt/us/extensions/tailscale/`.

**Setup:**
1. Generate an auth key at [login.tailscale.com/admin/settings/keys](https://login.tailscale.com/admin/settings/keys) — **leave "Ephemeral" off** (the Kindle sleeps and reconnects constantly; an ephemeral key gets it removed from the tailnet every time it disconnects).
2. Drop the key into `/mnt/us/extensions/tailscale/bin/auth.key` on the Kindle.
3. On the Kindle: **KUAL → Tailscale → Start Tailscaled → Proxy Mode (SOCKS5/HTTP)**, then **Start Tailscale**.
4. Set `spike/kindle-dash/menu.json`'s `params` (and/or the `dash_interactive.sh` argument) to the server's **Tailscale IP** (`100.x.x.x`), not its LAN IP.

**Why proxy mode, not kernel TUN:** `dash_interactive.sh` auto-starts `tailscaled` in userspace-networking + SOCKS5/HTTP proxy mode (`ensure_tailscale_proxy()`), and routes `curl` through `--proxy http://localhost:1055`. Kernel TUN mode was tested directly on a PW4 (FW 5.16.7) and failed outright — confirmed empirically, not assumed from the extension's own cautious comment. Without a kernel TUN device, plain `curl` can't route through the tailnet at all; only the explicit local proxy works.

**Bonus: SSH access.** Since `tailscale up --ssh` is what registers the device, once both machines share a tailnet you get root SSH straight into the Kindle — `ssh root@<kindle-tailscale-ip>` — no separate SSH server needed. Much faster than USB mass-storage for iterating (which, notably, suspends all background processes including `tailscaled` while mounted — expect to restart it via KUAL after every USB session).

**Known limitation:** `touch_tap` grabs the touchscreen early in `dash_interactive.sh`'s startup, before the code that handles sleep/wake is running. If the Kindle's own screen timeout fires during the (now short, ~6s max) Tailscale connection wait, swipe-to-unlock can break until the orphaned `touch_tap` is killed (over SSH: `kill $(pgrep touch_tap)` — the grab releases automatically). Reduced but not eliminated; see LOG.md 2026-07-31.

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