# kindle-dash

Turn a jailbroken Kindle into a shared e-ink dashboard for AI agents. The Kindle
stays a dumb display — a server renders PNG images + JSON tap maps, the Kindle
fetches and displays them, and a tiny C touch helper handles taps. Any number of
MCP-capable agents can push their own data to it: each one gets a card on the
home screen and its own space of views underneath.

**Proven end-to-end on a Kindle Paperwhite 4** (10th Gen, 2018) — viewer, touch,
power-button sleep/wake, and the MCP server all verified on real hardware.

## Architecture

```
Your agent(s)                MCP server (this repo)         Kindle (this repo)
┌──────────┐    MCP tools    ┌──────────────────────┐  HTTP  ┌──────────────────┐
│ Agent A   │───────────────▶│ update_view()         │───────▶│ dash_interactive │
│ Agent B   │  push_home_    │ push_home_card()      │  LAN/  │ .sh: curl fetch  │
│ ...       │  card()        │ → Pillow renders PNG   │  Tail- │ PNG, eips -f -g  │
└──────────┘                │   + tap map, saves to  │  scale │ display, awk     │
                             │   disk                 │        │ parses taps      │
                             └───────────────────────┘        └────────┬─────────┘
                                                                        │ FIFO
                                                                ┌───────┴────────┐
                                                                │ touch_tap (C)   │
                                                                │ EVIOCGRAB, evdev│
                                                                └────────────────┘
```

## Requirements

- A **jailbroken Kindle** with KUAL installed. This repo doesn't cover jailbreaking
  — it's device/firmware-specific and changes over time. Use
  [kindlemodding.org's jailbreak guide](https://kindlemodding.org/jailbreaking/jailbreak-faq.html)
  (community-maintained, current as of writing) to get WinterBreak (or whatever
  the current recommended method is for your model/firmware) and KUAL installed.
- A machine to run the MCP server: Python 3.11+, reachable on the Kindle's LAN
  (or via [Tailscale](#remote-access-tailscale-optional) for off-network access).
- An MCP-capable agent — [Hermes Agent](#hermes-agent) is a one-command setup;
  anything else that speaks MCP over stdio works too (see
  [`mcp_server/README.md`](mcp_server/README.md)).

**Proven on a Paperwhite 4 specifically.** The MCP server is hardware-agnostic
(screen size is a config value), but the Kindle-side viewer — `touch_tap`'s touch
driver assumptions, the shell script's busybox/LIPC behavior — was verified
empirically on this device and firmware. A different model will very likely need
some re-verification on your own hardware; see [`skill/SKILL.md`](skill/SKILL.md)
for exactly what was verified and how, if you're porting it.

## Quick Start

### 1. Deploy the Kindle-side viewer

```sh
# Set your server's IP/hostname in kindle/menu.json first (replace YOUR_SERVER_IP)
cp -r kindle/ /Volumes/Kindle/extensions/kindle-dash/
chmod +x /Volumes/Kindle/extensions/kindle-dash/bin/*
find /Volumes/Kindle/extensions/kindle-dash -name '._*' -delete   # macOS resource forks break KUAL
```

Eject, unplug, then on the Kindle: **KUAL → Kindle Dashboard → Start Dashboard**.

### 2. Run the MCP server

```sh
cd mcp_server
uv sync
uv run kindle-dash-mcp
```

Defaults to port 8888 (matching `kindle/menu.json`) and screen size 1072×1448
(Paperwhite 4). See [`mcp_server/README.md`](mcp_server/README.md) for every
config option (screen size, port, data directory, home-grid capacity).

### 3. Connect an agent

**Hermes Agent:**
```sh
cd mcp_server
./scripts/hermes-setup.sh
```
One command: installs `uv` standalone if needed, creates a wrapper script,
registers the server in `~/.hermes/config.yaml`, verifies the connection. Then
`/reload-mcp` in your Hermes chat. Full details (why a wrapper script is needed,
troubleshooting) in [`mcp_server/README.md`](mcp_server/README.md#connecting-an-agent).

**Any other MCP client:**
```json
{
  "mcpServers": {
    "kindle-dash": {
      "command": "uv",
      "args": ["run", "--directory", "/absolute/path/to/mcp_server", "kindle-dash-mcp"]
    }
  }
}
```

### 4. Push your first view

Once connected, call `push_home_card(agent_id="demo", title="Hello", summary=["It works!"], nav_target="demo/hello")` and `update_view(path="demo/hello", data={"type": "text_list", "title": "Hello", "rows": [{"left": "First view", "right": "✓"}]})` from your agent. Tap the Kindle's power button (or the KUAL launch) to refresh and see it.

## What agents can push

5 built-in, typed view renderers — agents hand over structured data, never touch
Pillow or tap-map geometry directly:

| Type | Use case |
|---|---|
| `status_grid` | Grid of navigable cards (this is what the home screen is made of) |
| `metric_dashboard` | Hero number + factor bars + an optional safety-gate banner |
| `text_list` | Header + rows with a left/right column and a status marker |
| `chart_view` | Hero value + sparkline + optional baseline + caption |
| `progress_view` | Progress bars + an optional stacked bar + a bullet list |

Full schema for each type, the 4-tool MCP surface (`update_view`,
`push_home_card`, `get_status`, `list_views`), and every config option:
[`mcp_server/README.md`](mcp_server/README.md).

## Remote access (Tailscale, optional)

Lets the Kindle reach the server from any network, not just home WiFi —
Tailscale uses a direct connection when possible and falls back to its relay
otherwise, so one config works everywhere. Purely additive: without it,
everything above works exactly as described over plain LAN.

1. A [Tailscale](https://tailscale.com) account, with the server machine already
   joined to your tailnet.
2. A Tailscale KUAL extension on the Kindle —
   [mitanshu7/tailscale_kual](https://github.com/mitanshu7/tailscale_kual) is
   what this was built and tested against (see also
   [Tailscale's own Kindle writeup](https://tailscale.com/blog/tailscale-jailbroken-kindle)).
3. Generate a non-ephemeral auth key (the Kindle sleeps/reconnects constantly —
   an ephemeral key gets it dropped from the tailnet every time), start
   Tailscale on the Kindle in **userspace-networking + SOCKS5/HTTP proxy mode**
   (kernel TUN doesn't work on at least this device/firmware — confirmed, not
   assumed), and set `kindle/menu.json`'s server address to the Mac's Tailscale
   IP. `dash_interactive.sh` already routes its fetches through the local proxy
   when the Tailscale extension is present — this is purely additive and skipped
   entirely if it isn't installed.
4. Bonus: `tailscale up --ssh` (which the extension's start script already runs)
   gives you root SSH straight into the Kindle once both devices share a
   tailnet — much faster than USB mass-storage for iterating (which, notably,
   suspends all Kindle background processes while mounted).

## Repository Structure

```
├── kindle/          # KUAL extension: config.xml, menu.json, bin/ (shell viewer + C touch helper)
├── mcp_server/       # kindle-dash-mcp — the MCP server agents connect to
│   ├── README.md            # Full install/config/tool/view-type reference
│   ├── scripts/hermes-setup.sh
│   └── src/kindle_dash_mcp/  # config, store, renderers, http_server, server, __main__
└── skill/SKILL.md    # Operational reference for AI agents working on the Kindle-side code
```

## License

MIT — see [LICENSE](LICENSE).

## Acknowledgments

- [kdashboard](https://github.com/thecodedose/kdashboard) — Kindle e-ink dashboard with a C++ renderer; inspiration for the server-driven inversion this project uses instead
- [KindleModding](https://kindlemodding.org/) and the [MobileRead](https://www.mobileread.com/) community — jailbreaking, KUAL, and Kindle firmware knowledge
