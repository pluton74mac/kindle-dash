# DECISIONS — Kindle the agent Dashboard

## 2026-07-16 — D01: Kindle viewer architecture: hybrid shell + C touch helper

**Decision:** The Kindle viewer will be a shell script (curl + jq + eips) paired with a ~50-line C touch helper. Not a full C binary, not Python on Kindle.

**Context:** Three options were evaluated — full C binary (kdashboard pattern), pure shell (curl + eips), and Python on Kindle. A 10-dimension comparison was conducted across reliability, ease of implementation, rendering speed, touch handling, expandability, power efficiency, debuggability, maintenance burden, binary distribution, and sleep/wake lifecycle.

**Rationale:**
- **Iteration speed:** Shell is editable in place (scp + run). C requires cross-compilation (Zig or arm-linux-gnueabi-g++) for every change. 10x faster iteration with shell.
- **Debuggability:** `set -x` produces readable logs. C segfaults on Kindle are nearly impossible to debug without valgrind or proper gdb support.
- **Touch quality:** The 50-line C helper provides EVIOCGRAB (exclusive touch), coordinate scaling via EVIOCGABS, and 700ms debounce — all the touch advantages of full C, in a trivial program compiled once.
- **Rendering speed:** C direct framebuffer write is ~200ms faster than `eips -g` PNG decode. But e-ink panel refresh takes 300-500ms regardless — the difference is imperceptible for full-screen view swaps.
- **Production reliability:** homecircuits.eu project proves shell-based image-push with full error recovery (atomic downloads, progressive backoff, auto-reboot) works in production for weeks.
- **Design philosophy:** "Kindle is dumb, server is smart." The shell is a thin router — new features almost always live server-side.

**Rejected alternatives:**
- **Full C binary:** Rejected due to cross-compilation burden, slow iteration, and debugging difficulty. Would only be justified for real-time partial updates or animations — not our use case.
- **Python on Kindle:** Rejected due to no PIL/Pillow availability, 2-3s startup, no EVIOCGRAB for exclusive touch, and additional dependency (KUAL Python extension).
- **Pure shell (no C):** Rejected because without EVIOCGRAB the Kindle framework would also receive touch events, causing unwanted UI responses. The 50-line C helper solves this cleanly.

**Reference:** Full analysis at `llm_wiki/viewer-implementation-c-vs-shell.md`

## 2026-07-16 — D02: Dashboard interface as MCP Server

**Decision:** The Kindle Dashboard will be built as an MCP Server, not a skill or standalone service.

**Context:** Multiple agents (sports coach, life coach, future agents) need to push data to the Kindle display. Evaluated three packaging options: Skill (teaches agents to render), MCP Server (shared service with tools), Standalone HTTP Service (agents POST via curl).

**Rationale:**
- The Kindle dashboard is shared infrastructure, not an agent capability — multiple agents push data TO it independently.
- Agents shouldn't know about Pillow, eips, tap maps, or Kindle internals. They call `update_view(path, data)` and the MCP handles rendering, tap maps, HTTP serving, and view tree.
- MCP gives every connected agent a first-class, discoverable tool interface.
- A skill would mean each agent runs its own server, fights over port 8888, and the Kindle only sees one agent's views at a time.
- A standalone service would require agents to use `execute_code`/`terminal` to POST — no clean tool interface, no discoverability.

**Rejected alternatives:**
- **Skill:** Rejected because rendering, view tree management, and HTTP serving are infrastructure, not agent knowledge. Multiple agents loading the same skill would conflict (port, view tree, Kindle session).
- **Standalone HTTP Service:** Functionally similar but inferior agent ergonomics — no tool interface, no type safety, agents would need `execute_code` to interact.

**Architecture:**
```
Sports Coach Agent    Life Coach Agent    Future Agent
     │                     │                   │
     │ update_view()        │ update_view()     │ register_view()
     ▼                     ▼                   ▼
┌──────────────────────────────────────────────────┐
│           Kindle Dashboard MCP Server             │
│  Tools: register_view, update_view,             │
│         get_status, list_views, push_notification│
│  Internal: Pillow rendering, HTTP server, tree   │
└──────────────────────┬───────────────────────────┘
                         │ HTTP
                  ┌──────┴──────┐
                  │   Kindle     │
                  └─────────────┘
```

**Next step:** Grill the MCP design in a new session — tools, rendering templates, view registration, data schemas, multi-agent view tree.

## 2026-07-24 — D03: MCP Server Design (Architecture Grill)

**Decision:** Full MCP server design grilled and crystallized across 7 dimensions.

**Context:** The spike proved the Kindle viewer (shell + C touch helper, PNG + tap map, touch navigation, exit). D02 decided the dashboard interface is an MCP server. This decision records the MCP architecture that emerged from the design grill.

**Key design decisions:**

1. **Rendering model — Typed view types (Model B).** Agents push `data = {type: "<view_type>", ...fields}`. MCP has builtin renderers per type. Agents never touch Pillow. Phase 1: 5 generic types (status_grid, metric_dashboard, text_list, chart_view, progress_view). Phase 2: agent-domain types (habit_tracker, mood_journal, etc.) added as agent data patterns are understood.

2. **Home view — Fixed grid of agent slots (Option 3).** Each agent has a designated card position. `push_home_card(agent_id, title, summary, nav_target)` updates the agent's slot. No ordering, no priority — positions are fixed. Dashboard = "agent newspaper" where each agent contributes a front-page section.

3. **View tree — Namespaced by agent.** Paths are `sports/readiness`, `life/habits`, `system/cron`. No path collisions. No registration step — `update_view` creates views on first push, overwrites on subsequent pushes. Implicit registration.

4. **Freshness — No polling.** Kindle fetches on interaction only (tap, refresh button, wake from sleep). E-ink holds the image when idle — its superpower. Dropped the 60-min auto-refresh timer from the spike. The Kindle always gets the latest PNG on disk when it fetches.

5. **Process lifecycle — Stdio MCP (Option A).** the agent-managed subprocess with HTTP server as background thread. `idle_timeout_seconds: 0`. PNGs + view metadata persisted to disk. Kindle offline cache covers the agent restart gaps. Subprocess respawns on next cron push, so the HTTP server is up when new data exists.

6. **Extensibility — Builtin types only.** No custom renderers, no raw_image escape hatch. New types = code change to MCP. Safe because cronjobs are deterministic — no surprise data shapes. When a new need emerges, we add a type.

7. **Cronjobs are the trigger.** Each agent has a scheduled cron job that fetches data and pushes to the dashboard. Agents don't sit in loops. The dashboard shows the last-pushed state.

**Tool surface:**

| Tool | Called by | Purpose |
|------|----------|---------|
| `update_view(path, data)` | Agent cron jobs | Push data to a view path, MCP renders PNG + tap map |
| `push_home_card(agent_id, title, summary, nav_target)` | Agent cron jobs | Update the agent's card on the home grid |
| `get_status()` | Agents, debugging | Kindle last seen, view count, agent list, port, uptime |
| `list_views()` | Agents, debugging | All registered views with metadata |

**HTTP endpoints (Kindle-facing, internal to MCP):**
- `GET /view?path=<path>` → view protocol JSON (image ref + tap map)
- `GET /images/<name>.png` → PNG bytes
- `GET /health` → server health check

**Rejected alternatives:**
- **Freeform text data (Model A):** Can't do progress bars, sparklines, hero numbers — the things that make e-ink dashboards good.
- **Layout DSL (Model C):** Over-engineered for ~10 views; designing the DSL becomes the project.
- **Raw PNG (Model D):** Violates D02 — agents need Pillow + e-ink knowledge.
- **MCP auto-generated home (Option 1):** Less control over card content.
- **Orchestrator agent home (Option 2):** Single point of failure, extra agent.
- **Push freshness (Option B):** Requires Kindle-side listener, breaks "dumb display" principle.
- **HTTP MCP daemon (Option B):** More setup (launchd plist), unnecessary given disk persistence + Kindle cache.
- **Custom renderers / raw_image escape hatch:** Violates D02, unnecessary given deterministic cron tasks.

**Reference:** Full grill session in LOG.md (2026-07-24). MCP design spec at `llm_wiki/mcp-server-design.md`.

## 2026-07-31 — D04: Tailscale via userspace proxy mode, not kernel TUN

**Decision:** The Kindle reaches the server over Tailscale using userspace-networking + an explicit local SOCKS5/HTTP proxy (`--socks5-server`, `--outbound-http-proxy-listen`), with `curl` in `dash_interactive.sh` routed through `--proxy http://localhost:1055`. `SERVER` is the server's Tailscale IP, used identically whether the Kindle is on the home LAN or away — Tailscale itself chooses a direct path or its DERP relay.

**Context:** The goal (per the developer, 2026-07-31) is for the dashboard to work "from any network," not just home WiFi. Kernel TUN mode (a real virtual network interface, transparent to all apps) was the alternative — if it worked, no proxy config would be needed anywhere.

**Rationale:**
- **Kernel TUN tested directly on hardware and failed.** `/dev/net/tun` exists as a device node on this PW4 (FW 5.16.7), but `tailscaled -tun <default>` fails to start against it — confirmed empirically via SSH, not inferred from documentation. Userspace-networking mode is the only one that actually connects.
- **Without a kernel TUN interface, an explicit proxy is required** for any ordinary Linux process (`curl`) to route through the tailnet — userspace-networking alone gives tailscaled its own isolated network stack that other processes can't see.
- **One SERVER config for both home and away**, rather than maintaining separate LAN/Tailscale URLs, by always using the Tailscale IP + local proxy. Confirmed Tailscale prefers a direct LAN path when available (`tailscale ping` showed a direct 192.168.x.x round-trip, not just DERP) and falls back to relay otherwise — so this doesn't sacrifice home-LAN performance.
- **Tailscale SSH as a side effect:** since the extension's `start_tailscale.sh` already runs `tailscale up --ssh`, this also gives root SSH into the Kindle once both devices share a tailnet — a major workflow improvement over USB mass-storage for iteration (see LOG.md 2026-07-31).
- **Purely additive:** `ensure_tailscale_proxy()` no-ops entirely if the Tailscale extension isn't installed (`[ ! -x "$TAILSCALED_BIN" ]`) — the dashboard's original LAN-only behavior is unaffected for anyone who doesn't set it up.

**Rejected alternatives:**
- **Kernel TUN mode:** Would be the cleaner design (no proxy, no per-app config) but does not work on this hardware/firmware — not a matter of preference.
- **Tailscale Funnel/Serve (server-side only, no Kindle-side client):** Considered before hardware testing began, as a way to avoid any Kindle-side networking risk entirely (confirmed this Kindle's `curl` has real HTTPS/OpenSSL support, so it would have worked). Not pursued once the Tailscale extension was discovered already installed and working on the device — using what's already there was simpler than standing up Funnel. Worth reconsidering if a future user doesn't want a Tailscale client on the Kindle at all.
- **A fixed sleep after starting tailscaled:** Tried first: unreliable, since actual DERP connection time varies (~6-20s+ observed). Replaced with polling the server's `/health` through the proxy, bounded at 6s (see the touch-grab incident in LOG.md 2026-07-31 for why it isn't bounded higher).

**Known limitation:** `touch_tap` grabs the touchscreen before `dash_interactive.sh`'s sleep/wake handling is active, so a screen timeout during the (bounded, ~6s) Tailscale connection wait can leave swipe-to-unlock broken until the orphaned process is killed. Reduced, not eliminated. See LOG.md 2026-07-31.

**Reference:** LOG.md (2026-07-31) has the full investigation, including the empirical TUN test and the touch-grab incident.

## 2026-07-31 — D05: MCP server built per D02/D03, generalized beyond one agent framework

**Decision:** Implemented `mcp_server/` (package `kindle-dash-mcp`) exactly per the D02/D03 design, with one deliberate generalization: nothing in it assumes a specific agent framework, a specific set of agents, or PW4-specific hardware. It's meant to be usable by anyone with a jailbroken Kindle and an MCP-capable agent, not just this project's original two agents.

**Context:** D02/D03 specified the architecture (typed view types, stdio MCP + HTTP thread, disk-backed state, fixed-but-now-dynamic home slots) but were never implemented — `skill/templates/mcp_server_skeleton.py` was a stub with `# ... draw cards ...` comments in place of real renderers. This session built the real thing.

**What changed from the D03 spec vs. what was kept:**
- **Kept as designed:** 4 MCP tools (`update_view`, `push_home_card`, `get_status`, `list_views`), 3 HTTP endpoints (`/view`, `/images`, `/health`), 5 Phase-1 view types, stdio transport, no polling, no custom-renderer escape hatch, disk as source of truth.
- **Generalized — home grid slots:** D03's home grid assumed a small fixed set of named agents. Implemented instead as *dynamic* slot assignment: any `agent_id` gets the next free slot on first `push_home_card()` call, stable thereafter (persisted in `home_cards.json`). Beyond `KINDLE_DASH_HOME_MAX_CARDS` (default 8), extra agents collapse into a "+N more" tile linking to an auto-generated `system/agents` overview (a `text_list` view built the same way `home` is). This is what makes "anyone with any number of agents" actually work, not just the original two.
- **Generalized — hardware assumptions:** screen width/height, HTTP port/host, and data directory are all environment variables (`KINDLE_DASH_WIDTH`/`HEIGHT`/`PORT`/`HOST`/`DATA_DIR`), not hardcoded PW4 constants. Nothing else in the rendering or serving code assumes 1072x1448.
- **Reserved namespace, not in original spec:** `home` and `system/*` are reserved — `update_view()` rejects direct writes to them with a clear error pointing at `push_home_card()`. This wasn't in D03 but was needed once home became dynamically composed rather than a single renderer agents could theoretically clobber.

**MCP SDK version — pinned to 1.9.4, not the newer 2.0.0 line:** `mcp` 2.0.0 (released after D03 was written) restructures the SDK — `FastMCP` moves and is renamed, the decorator API changes. For a server meant to be broadly reusable, the 1.x `FastMCP` API is what the overwhelming majority of existing MCP client docs/examples target; 2.0 is too new to assume client-side familiarity. Revisit if 2.0 becomes the de facto standard.

**Protocol detail that isn't obvious from the design docs and cost a real bug during testing:** the Kindle's `hit_test()` in `dash_interactive.sh` parses the `/view` JSON with a line-by-line awk scanner (see SKILL.md, "No `jq` on Kindle"). `http_server.py` must serialize with `json.dumps(payload, indent=2)` — compact single-line JSON parses "successfully" (no error) but every tap silently fails to hit, because the awk script's `/}/`-terminated per-record scan never sees a matching line. This is now a comment directly on the serialization call, not just documentation, since it's the kind of "harmless-looking" simplification a future cleanup pass could reintroduce.

**Verification:** all 4 tools exercised directly (Python), all 5 renderers visually inspected (rendered PNGs read back and checked), HTTP endpoints hit via curl including a path-traversal attempt (403/404 as expected), a full real MCP stdio round-trip via `mcp.client.stdio` (spawn subprocess, `list_tools()`, `call_tool()` for two tools), and **confirmed end-to-end on the physical Kindle, same session**: the deployed KUAL bundle (unmodified, `menu.json` already pointed at the Mac's Tailscale IP from the earlier Tailscale session) fetched `home`, navigated to two different agents' cards (two different view types — metric_dashboard and progress_view), and navigated back, all against `kindle-dash-mcp` instead of `spike/view_server.py`. See LOG.md 2026-07-31 for the access-log evidence.

**Rejected alternatives:**
- **`mcp` 2.0.0 SDK:** rejected for now — see above. Not a permanent rejection, just too new for a "generalized for anyone" server today.
- **Fixed/hardcoded home slots per named agent (the literal D03 spec):** rejected in favor of dynamic assignment — a fixed slot list is definitionally incompatible with "for anyone with any agents," not just this project's original two.
- **Custom/pluggable renderers:** re-confirmed rejected, same rationale as D03 (deterministic cron-driven data doesn't need it, and it would reopen the exact scope D02 was trying to keep out of agents' hands).

**Reference:** `mcp_server/README.md` for usage, `mcp_server/src/kindle_dash_mcp/` for implementation, LOG.md (2026-07-31) for the build session.
