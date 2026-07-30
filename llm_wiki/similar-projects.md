# Similar Projects — Kindle & E-ink Dashboard Survey

> **Status:** Research. Findings from web searches, project READMEs, and blog posts. Links included for reference.

## Summary

Survey of Kindle dashboard and e-ink display projects beyond kdashboard. Covers approaches (browser-based, framebuffer, Python, image-push), proven patterns, and common pitfalls. This research informs the the agent Kindle dashboard architecture described in [IDEA.md](../IDEA.md) and [view-protocol-spec.md](view-protocol-spec.md).

## Project Survey

### 1. Pascal's kindle-dash (TerminalBytes)

**URL:** [github.com/pascalw/kindle-dash](https://github.com/pascalw/kindle-dash) / [terminalbytes.com](https://terminalbytes.com/reviving-kindle-paperwhite-7th-gen/)

**Approach:** Image-push. A shell script on the jailbroken Kindle wakes up via RTC alarm, fetches a PNG from a server via `wget`, displays it with `eips -f -g`, and goes back to deep sleep. The server (Python/Node) renders the PNG.

**Key details:**
- Kindle Paperwhite 7 (1072×1448, 300 DPI)
- 3-hour refresh cycle, 4-6 weeks battery life
- Server uses Playwright + Sharp to render HTML → PNG → grayscale
- `REFRESH_SCHEDULE` cron expression supports different images at different times
- SSH key auth (must use `ssh-rsa`, not `ssh-ed25519` — Kindle's Dropbear doesn't support it)

**What we take from it:** The client-side sleep/wake cycle is proven and reliable. The `eips -f -g` command for displaying PNGs is the standard approach.

### 2. matopeto/kindle-weather-dashboard

**URL:** [github.com/matopeto/kindle-weather-dashboard](https://github.com/matopeto/kindle-weather-dashboard) (269 stars, 65 forks)

**Approach:** Browser-based. A static HTML/CSS/JS webpage served from a server. The Kindle's built-in browser loads it and auto-refreshes.

**Key details:**
- Works on Kindle 3/4/5, Paperwhite 3, iPad Air
- Uses OpenWeatherMap API
- Pure HTML/CSS/JS (no Python on Kindle)
- Auto-refresh via JavaScript `setInterval`
- Supports portrait/landscape rotation
- Night mode (auto based on sunrise/sunset)
- Configurable via URL parameters or `config.js`

**Strengths:** No jailbreak needed for browser approach (just disable screensaver via `~ds`). Simple to deploy.
**Weaknesses:** Kindle browser is old and limited (no modern JS, no flexbox reliably). Browser keeps running = higher power draw. No touch interaction beyond browser links.

### 3. 4DCu.be KUAL Dashboard (Sebastian Proost)

**URL:** [blog.4dcu.be](https://blog.4dcu.be/diy/2020/10/04/PythonKindleDashboard_2.html) / [github.com/4dcu-be/kual-dashboard](https://github.com/4dcu-be/kual-dashboard)

**Approach:** Python on Kindle + SVG rendering. A KUAL extension runs Python 3 on the Kindle itself. The script fetches data from APIs, fills an SVG template, converts to PNG with `rsvg-convert`, and displays with `fbink`.

**Key details:**
- Kindle Paperwhite 3 (1072×1448)
- Uses only Python standard library (urllib, json, re) — no pip packages
- SVG template with token replacement for dynamic data
- `rsvg-convert` for SVG→PNG, `fbink` for display
- Caching decorator: fetch data, cache to JSON, serve from cache on failure
- Deep sleep via RTC alarm (`/sys/class/rtc/rtc1/wakealarm`)
- Disable screensaver: type `~ds` in search bar

**Pitfalls documented:**
- `noexec` flag on Kindle's mounted partitions — can't run binaries directly. Workaround: copy to `/var/tmp` and set `LD_LIBRARY_PATH`
- Kindle's deep sleep overrides custom wake timer — must disable with `~ds`
- Debugging is painful — errors only surface after long periods

**What we take from it:** The caching decorator pattern (fetch → cache → fallback to cache on failure) is exactly what our view server needs. The `noexec` workaround and `fbink` usage inform Kindle-side implementation.

### 4. Homecircuits.eu PW2 + RPi5 Dashboard

**URL:** [homecircuits.eu](https://homecircuits.eu/blog/repurposing-kindle-paperwhite-dashboard/)

**Approach:** Image-push with production-grade reliability. RPi5 renders HTML via Playwright/Chromium → PNG → Flask serves it. Kindle fetches via `wget`, displays with `eips -f -g`, deep sleeps via RTC.

**Key details:**
- Kindle Paperwhite 2 (758×1024)
- 30-minute refresh cycle, 2-3 weeks battery life
- RPi5 renders every 5 minutes via cron with lockfile
- Flask server serves PNG + browser preview for debugging
- Kindle passes battery level as query param: `wget ... ?batt=85`

**Production reliability features:**
- `while true` loop with full error recovery at every step
- Atomic downloads (download to `.tmp`, rename only on success)
- Gateway fix after deep sleep (Kindle loses default route)
- Progressive ping backoff (up to 10 attempts with increasing delays)
- Battery protection (below 5%, show low-battery image, sleep 1h)
- Error counter — after 10 consecutive errors, Kindle reboots itself
- Upstart job for auto-start after boot
- Log rotation (trim to last 300 lines)

**Rendering pipeline:** HTML/CSS (Jinja2 template) → Chromium headless screenshot → Pillow grayscale conversion → save PNG

**E-ink CSS optimization:**
```css
-webkit-font-smoothing: none;
-moz-osx-font-smoothing: grayscale;
shape-rendering: crispEdges;
```

**What we take from it:** The entire production reliability pattern — atomic downloads, error recovery, progressive backoff, auto-reboot, battery protection — should be adopted by our Kindle viewer. The CSS anti-aliasing guidance informs our [PNG rendering pipeline](png-rendering-pipeline.md).

### 5. TRMNL Kindle Client

**URL:** [github.com/usetrmnl/trmnl-kindle](https://github.com/usetrmnl/trmnl-kindle) (336 stars)

**Approach:** Purpose-built Kindle client for the TRMNL e-ink platform. 27-step setup process. Can use TRMNL cloud (900+ plugins) or self-hosted server.

**Key details:**
- Requires jailbreak
- Supports weather, calendar, Hacker News, GitHub stats, smart home feeds
- Cloud or self-hosted
- Purpose-built hardware also available ($139)

**What we take from it:** The plugin ecosystem concept — 900+ plugins — validates that a server-driven model where the Kindle is a dumb display is the right architecture. Our view tree is essentially a plugin system, just server-side.

### 6. sibbl/hass-lovelace-kindle-4

**URL:** [github.com/sibbl/hass-lovelace-kindle-4](https://github.com/sibbl/hass-lovelace-kindle-4)

**Approach:** Home Assistant screenshot method. Docker container runs alongside HA, takes Chromium screenshots of HA dashboards, converts to grayscale, serves over HTTP. Kindle fetches and displays.

**Key details:**
- Designed for Home Assistant Lovelace dashboards
- Chromium headless → screenshot → Pillow grayscale → PNG
- Error recovery patterns: ping test, `wpa_cli reconnect`, gateway fix, auto-reboot

**What we take from it:** The error recovery patterns (ping test, reconnect, gateway fix) were adopted by the homecircuits.eu project. Our viewer should implement similar patterns.

### 7. Kindle as E-ink Monitor (adtac)

**URL:** [gist.github.com/adtac/eb639d3c707b55a28f0ee9a420aa7e0c](https://gist.github.com/adtac/eb639d3c707b55a28f0ee9a420aa7e0c)

**Approach:** Mac screencapture + ImageMagick → `eips` on Kindle. Turn the Kindle into a secondary e-ink monitor.

**Key details:**
- `screencapture` on Mac → ImageMagick for resize/grayscale → `scp` to Kindle → `eips -g`
- Continuous loop with configurable refresh rate
- Useful for text/code display on e-ink

**What we take from it:** The `eips -g` command is the universal display primitive on jailbroken Kindles. Our viewer will use it (or `fbink` as an alternative).

### 8. mattzzw/kindle-gphotos

**URL:** [github.com/mattzzw/kindle-gphotos](https://github.com/mattzzw/kindle-gphotos)

**Approach:** Digital photo frame displaying Google Photos. Fetches a new photo every 24h from a shared Google Photos album.

**Key details:**
- Kindle Paperwhite
- Long refresh interval (24h) for ultra-low power
- Google Photos API integration
- KUAL extension

### 9. InkyPi (Colour E-Ink Dashboard)

**URL:** [instructables.com](https://www.instructables.com/Build-a-COLOUR-E-INK-DASHBOARD-Weather-Calendar-Ph/) / [printables.com](https://www.printables.com/model/1518955)

**Approach:** Raspberry Pi Zero 2 + Waveshare colour e-ink display. Open-source software renders weather, calendar, photos, news.

**Key details:**
- Uses Waveshare 7-color e-ink panel (not Kindle)
- Python-based rendering
- Open source

**Relevance:** Demonstrates the server-render-then-push pattern on a different e-ink platform. The rendering concepts (dithering for limited color, grayscale optimization) transfer to Kindle's 16-level grayscale.

## Pattern Analysis

### Proven Patterns

| Pattern | Used By | Description |
|---|---|---|
| **Image-push** | pascalw/kindle-dash, homecircuits, 4dcu.be, TRMNL | Server renders PNG, Kindle fetches and displays. Most common and reliable approach. |
| **RTC deep sleep** | pascalw, 4dcu.be, homecircuits | Kindle wakes via `/sys/class/rtc/rtcN/wakealarm`, does work, sleeps via `echo mem > /sys/power/state`. Weeks of battery life. |
| **`eips -f -g`** | All framebuffer projects | Kindle's built-in command to display PNG on e-ink. `-f` for full refresh (anti-ghosting). |
| **`fbink`** | 4dcu.be | Alternative to `eips` — handles PNG display without needing `pngcrush` conversion. More versatile. |
| **Atomic downloads** | homecircuits | Download to `.tmp` file, rename on success. Prevents corrupt image display. |
| **Caching with fallback** | 4dcu.be | Fetch data, cache locally, serve from cache on fetch failure. |
| **Error recovery loop** | homecircuits, sibbl | `while true` with progressive backoff, auto-reboot after N consecutive errors. |
| **Browser-based** | matopeto | No jailbreak needed (just `~ds`), but limited browser, higher power draw. |
| **HTML→PNG rendering** | homecircuits, terminalbytes, sibbl | Render HTML/CSS with headless Chromium, screenshot to PNG. Easier layout than Pillow drawing. |
| **Pillow direct rendering** | homecircuits (v1) | Draw directly with PIL. Simpler for basic layouts but unwieldy for complex dashboards. |

### Common Pitfalls

| Pitfall | Source | Mitigation |
|---|---|---|
| **`noexec` partition** | 4dcu.be | Kindle mounts USB storage with `noexec`. Copy binaries to `/var/tmp` and set `LD_LIBRARY_PATH`. |
| **Deep sleep overrides** | 4dcu.be | Kindle goes to permanent deep sleep after 10 min idle. Disable with `~ds` in search bar. |
| **SSH key compatibility** | terminalbytes | Kindle's Dropbear SSH only supports `ssh-rsa`, not `ssh-ed25519`. |
| **Gateway route lost after sleep** | homecircuits | Kindle loses default gateway after deep sleep. Check and restore with `route add default gw ...`. |
| **WiFi reports connected but not ready** | homecircuits | `lipc-get-prop com.lab126.wifid cmState` says CONNECTED but link isn't ready. Use progressive ping backoff. |
| **Corrupt downloads** | homecircuits | Partial `wget` downloads produce broken images. Download to `.tmp`, validate, then rename. |
| **Ghosting** | all projects | E-ink retains previous image faintly. Use `eips -f` (full refresh) to flash black/white and clear. |
| **16-level grayscale** | terminalbytes, homecircuits | Kindle only has 16 gray levels. Design for high contrast — pure black/white for text, limited grays for secondary elements. |
| **Wrong image dimensions** | terminalbytes | Sending wrong resolution produces distorted or blank display. Use exact framebuffer dimensions. Run `eips -i` to check. |
| **OTA firmware updates** | homecircuits | Amazon can auto-update and kill jailbreak. Use `renameotabin` to prevent. |
| **SSL on Kindle** | 4dcu.be | Kindle Python needs `ssl._create_unverified_context()` for HTTPS. |

## Architecture Decision for the agent Dashboard

Based on this survey, the the agent Kindle dashboard should adopt:

1. **Image-push architecture** — Server renders PNG, Kindle fetches via HTTP. This is the dominant proven pattern.
2. **Pillow for rendering** — Simpler than HTML→Chromium for our data-driven views. Our views are text + bars + sparklines, not complex layouts. See [png-rendering-pipeline.md](png-rendering-pipeline.md).
3. **JSON tap map protocol** — Novel (no surveyed project uses interactive tap navigation). This is our key innovation. See [view-protocol-spec.md](view-protocol-spec.md).
4. **Production reliability patterns** — Atomic downloads, error recovery loop, progressive backoff, auto-reboot. From homecircuits.eu.
5. **Caching with fallback** — Server caches rendered images; Kindle caches last-good view for offline. From 4dcu.be.

### What We're NOT Doing

- **No browser-based approach** — Kindle browser is too limited for our needs, and we want touch interaction.
- **No Python on Kindle** — The viewer will be a single C binary or minimal shell script. All logic is server-side.
- **No Chromium dependency** — Pillow is sufficient for our text/data rendering and avoids the heavyweight browser dependency.

## Related Files

- [IDEA.md](../IDEA.md) — Original architecture hypothesis
- [view-protocol-spec.md](view-protocol-spec.md) — Our novel tap-map protocol
- [the agent-data-sources.md](the agent-data-sources.md) — Data sources for dashboard views
- [png-rendering-pipeline.md](png-rendering-pipeline.md) — Rendering approach
