# View Protocol Spec — Kindle ↔ View Server

> **Status:** Proposed design. Based on the architecture in [IDEA.md](../IDEA.md) and patterns observed in similar projects (see [similar-projects.md](similar-projects.md)).

## Summary

Defines the JSON protocol between the write-once Kindle viewer and the Python view server running on the Mac. The viewer fetches a PNG image plus a tap map from the server over local HTTP. The server owns all view logic — the Kindle never needs code changes for new views.

## Protocol Overview

### Transport

- **Protocol:** HTTP/1.1 over local network (no TLS needed; LAN only)
- **Server:** Python HTTP server on the Mac (e.g. `http.server` or Flask/FastAPI)
- **Client:** Kindle viewer (C or Python), fetches via `wget` or native HTTP

### Core Endpoint

```
GET /view?path=<view_path>
```

Returns a JSON response containing the rendered image reference, a tap map for navigation, metadata, and refresh timing.

### Response Schema

```json
{
  "version": 1,
  "title": "Home",
  "image": "/images/home.png",
  "image_data": null,
  "taps": [
    {
      "x": 0,
      "y": 400,
      "w": 400,
      "h": 200,
      "action": "navigate",
      "target": "coaching/readiness"
    }
  ],
  "back": null,
  "refresh_sec": 3600,
  "error": null,
  "cache": {
    "key": "home",
    "ttl_sec": 3600
  }
}
```

### Field Reference

| Field | Type | Required | Description |
|---|---|---|---|
| `version` | int | Yes | Protocol version. Increment when schema changes. Viewer rejects incompatible versions. |
| `title` | string | Yes | Display title shown in viewer header/status bar |
| `image` | string | Yes* | Path or URL to the PNG image. If relative, prepended to server base URL. |
| `image_data` | string\|null | No | Base64-encoded PNG (alternative to `image` path for inline delivery). Omit if using `image` path. |
| `taps` | array | Yes | Array of tap regions (see below). Empty array = no interactive elements. |
| `back` | string\|null | Yes | View path to navigate to on "back" action. `null` if at root (home). |
| `refresh_sec` | int | Yes | Seconds before viewer should auto-refresh this view. 0 = no auto-refresh. |
| `error` | string\|null | No | Error message if view generation failed. Viewer displays error image + retry prompt. |
| `cache` | object\|null | No | Cache metadata for offline support (see Offline Cache below). |

### Tap Region Schema

```json
{
  "x": 0,
  "y": 400,
  "w": 400,
  "h": 200,
  "action": "navigate",
  "target": "coaching/readiness",
  "label": "Coaching",
  "data": null
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `x` | int | Yes | Top-left X in image pixels (0 = left edge) |
| `y` | int | Yes | Top-left Y in image pixels (0 = top edge) |
| `w` | int | Yes | Width of tap region in pixels |
| `h` | int | Yes | Height of tap region in pixels |
| `action` | string | Yes | One of: `navigate`, `refresh`, `toggle`, `custom` |
| `target` | string | Conditional | Required for `navigate` — view path to fetch |
| `label` | string | No | Optional label for accessibility/debug |
| `data` | object | No | Arbitrary payload for `toggle` or `custom` actions |

### Action Types

| Action | Behavior | Required Fields |
|---|---|---|
| `navigate` | Viewer fetches `GET /view?path=<target>` and renders the new view | `target` |
| `refresh` | Viewer re-fetches the current view path | None |
| `toggle` | Viewer sends `POST /toggle` with `data`, then re-fetches current view | `data` (toggle payload) |
| `custom` | Viewer sends `POST /action` with `data`, response determines next step | `data` (custom payload) |
| `exit` | Viewer kills touch helper, restores screensaver, relaunches Kindle home via `lipc-set-prop com.lab126.appmgrd start app://com.lab126.booklet.home` | None |

> **Note:** The `exit` action is Kindle-specific (uses `lipc-set-prop`). It was validated in the spike — clean exit without leaving a blank/white screen.

## Toggle / Custom Endpoints

### POST /toggle

```json
{
  "view_path": "coaching/readiness",
  "data": { "field": "show_detail", "value": true }
}
```

Response: same schema as `GET /view` — the server returns the updated view.

### POST /action

```json
{
  "view_path": "workflows/trigger/deploy",
  "data": { "workflow": "deploy-prod" }
}
```

Response:
```json
{
  "result": "triggered",
  "next_view": "workflows/active",
  "message": "Deploy workflow triggered"
}
```

Viewer fetches `next_view` if provided, otherwise re-fetches current view.

## Example Payloads

### Home View

```json
{
  "version": 1,
  "title": "Dashboard",
  "image": "/images/home_20260716_0800.png",
  "taps": [
    {
      "x": 0, "y": 50, "w": 536, "h": 340,
      "action": "navigate",
      "target": "coaching/readiness",
      "label": "Training Readiness"
    },
    {
      "x": 536, "y": 50, "w": 536, "h": 340,
      "action": "navigate",
      "target": "calendar/today",
      "label": "Calendar"
    },
    {
      "x": 0, "y": 390, "w": 536, "h": 340,
      "action": "navigate",
      "target": "cron/list",
      "label": "Cron Jobs"
    },
    {
      "x": 536, "y": 390, "w": 536, "h": 340,
      "action": "navigate",
      "target": "workflows/active",
      "label": "Workflows"
    },
    {
      "x": 200, "y": 730, "w": 672, "h": 200,
      "action": "refresh",
      "label": "Refresh"
    }
  ],
  "back": null,
  "refresh_sec": 3600,
  "error": null,
  "cache": {
    "key": "home",
    "ttl_sec": 1800
  }
}
```

### Sub-View: Coaching Readiness

```json
{
  "version": 1,
  "title": "Training Readiness",
  "image": "/images/readiness_20260716_0800.png",
  "taps": [
    {
      "x": 0, "y": 900, "w": 350, "h": 120,
      "action": "navigate",
      "target": "home",
      "label": "Back"
    },
    {
      "x": 350, "y": 900, "w": 350, "h": 120,
      "action": "toggle",
      "data": { "field": "show_hrv_detail", "value": null },
      "label": "Toggle HRV Detail"
    },
    {
      "x": 700, "y": 900, "w": 372, "h": 120,
      "action": "navigate",
      "target": "coaching/training",
      "label": "Training →"
    }
  ],
  "back": "home",
  "refresh_sec": 1800,
  "error": null,
  "cache": {
    "key": "coaching/readiness",
    "ttl_sec": 1800
  }
}
```

## Error Handling

### Server Error (HTTP 5xx)

Viewer displays a cached or fallback error image:
```json
{
  "version": 1,
  "title": "Error",
  "image": "/images/error.png",
  "taps": [
    { "x": 0, "y": 0, "w": 1072, "h": 1448, "action": "refresh", "label": "Retry" }
  ],
  "back": "home",
  "refresh_sec": 60,
  "error": "Server unreachable"
}
```

### View Not Found (HTTP 404)

```json
{
  "version": 1,
  "title": "Not Found",
  "image": "/images/not_found.png",
  "taps": [
    { "x": 0, "y": 0, "w": 1072, "h": 1448, "action": "navigate", "target": "home" }
  ],
  "back": "home",
  "refresh_sec": 0,
  "error": "View not found: bad/path"
}
```

### Partial Data Error

If some data sources are unavailable, the server renders what it can and sets the `error` field to a non-fatal warning:
```json
{
  "version": 1,
  "title": "Home",
  "image": "/images/home_partial.png",
  "taps": [...],
  "back": null,
  "refresh_sec": 1800,
  "error": "Calendar data unavailable — showing cached data",
  "cache": { "key": "home", "ttl_sec": 300 }
}
```

## Offline Cache

The viewer maintains a local cache to handle network interruptions:

### Cache Strategy

1. **On successful fetch:** Save `{image, taps, back, refresh_sec}` keyed by view path to local storage (e.g. `/tmp/dash_cache/<path_hash>.json`)
2. **On fetch failure:** Load last cached view for the current path
3. **Cache invalidation:** Use `cache.ttl_sec` — if cached entry is older than TTL, viewer should still attempt a fetch but fall back to cache on failure
4. **Home fallback:** If no cache exists for current path, always fall back to `home` (which may itself be cached)

### Cache Entry Format

```json
{
  "path": "coaching/readiness",
  "fetched_at": "2026-07-16T08:00:00Z",
  "response": { "version": 1, "title": "...", "image": "...", "taps": [...], "back": "home", "refresh_sec": 1800 },
  "image_path": "/tmp/dash_cache/readiness.png"
}
```

## Version Field & Change Detection

The `version` field serves two purposes:

1. **Schema compatibility:** The viewer checks `version` on each response. If it encounters an unsupported version, it displays an "update viewer" message. This lets the server evolve the protocol without breaking old viewers.
2. **View change detection (optional):** The server can include a `content_hash` in the `cache` object:

```json
"cache": {
  "key": "home",
  "ttl_sec": 3600,
  "content_hash": "a3f2e1b8"
}
```

On auto-refresh, the viewer can send `If-None-Match: <content_hash>` as a query parameter:
```
GET /view?path=home&etag=a3f2e1b8
```

Server returns `HTTP 304` with no body if the view hasn't changed, saving bandwidth and avoiding unnecessary e-ink refreshes.

## Image Delivery Options

### Option A: Path-based (recommended)

Server saves PNG to a served directory and returns a relative path. Viewer fetches the image separately:
```
GET /view?path=home  →  { "image": "/images/home.png", ... }
GET /images/home.png  →  <PNG bytes>
```

**Pros:** Simple, cacheable by HTTP, viewer can fetch image asynchronously.
**Cons:** Two HTTP requests per view.

### Option B: Inline base64

Server returns the PNG as base64 in the JSON response:
```json
{
  "image": null,
  "image_data": "iVBORw0KGgoAAAANSUhEUgAA...",
  ...
}
```

**Pros:** Single request per view.
**Cons:** Larger payload (~33% overhead), not HTTP-cacheable.

**Recommendation:** Use Option A. The two-request overhead is negligible on a LAN, and HTTP caching of images is valuable.

## Related Files

- [IDEA.md](../IDEA.md) — Original architecture hypothesis
- [the agent-data-sources.md](the agent-data-sources.md) — What data feeds into each view
- [png-rendering-pipeline.md](png-rendering-pipeline.md) — How images are rendered
- [similar-projects.md](similar-projects.md) — Patterns from other Kindle dashboard projects
