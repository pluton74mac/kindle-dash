# Kindle Networking on Jailbroken Devices

## Summary

Jailbroken Kindles connect to WiFi networks using the built-in Kindle networking stack. The `curl` binary is included in Kindle firmware at `/usr/bin/curl`, making HTTP fetching straightforward. Kindles can reach LAN IP addresses (e.g., `192.168.x.x`) for fetching from a local server. DNS resolution works for both local and remote hosts. The main challenges are WiFi power management (the Kindle aggressively turns off WiFi to save battery) and potential SSL certificate issues. For a LAN dashboard, HTTP (not HTTPS) to a local server is the simplest and most reliable approach.

## WiFi Configuration

### Kindle Built-in WiFi

The Kindle manages WiFi through the `com.lab126.wifid` LIPC service and the `wifid` daemon. WiFi configuration is done through the Kindle's Settings UI, not through manual file editing.

Key WiFi states (observable via LIPC):

```
cmStateChange "NA"        → Not available
cmStateChange "PENDING"   → Connecting
scanning                  → Scanning for networks
scanComplete              → Scan finished
cmConnected               → Connected to network
cmStateChange "CONNECTED" → Connected state confirmed
signalStrength "4/5"      → Signal strength
```

### WiFi Power Management

The Kindle aggressively manages WiFi power to conserve battery. This is the **primary networking challenge** for always-on dashboard applications:

- WiFi stays on briefly after the screen turns off, then disconnects
- WiFi may randomly turn on/off
- During deep sleep, WiFi is completely off
- After waking, WiFi takes several seconds to reconnect

### Forcing Maximum WiFi Performance

For development/debugging, force WiFi to maximum performance mode:

```bash
wmiconfig -i wlan0 --power maxperf
```

> "Doing remote work on the kindle is quite annoying as it will try to limit its bandwidth and shut down the wifi at any opportunity; setting the wlan power setting to maxperf solves the issue."
> — [blog.davidv.dev](https://blog.davidv.dev/posts/integrating-a-kindle-into-house-automation/)

**Warning:** `maxperf` mode drains battery quickly. Set it back to normal mode (`rec`) for production:

```bash
wmiconfig -i wlan0 --power rec
```

### Waiting for WiFi After Wake

Dashboard scripts should wait for WiFi reconnection after the device wakes:

```bash
#!/bin/sh
cd "/mnt/us/extensions/dashboard/"
sleep 30  # Wait for WiFi to reconnect
python3 ./bin/run.py
```

> Source: [4DCu.be](https://blog.4dcu.be/diy/2020/10/04/PythonKindleDashboard_2.html)

Alternatively, monitor for the `cmConnected` event via LIPC:

```python
# Wait for WiFi to reconnect after wake
import subprocess
proc = subprocess.Popen(['lipc-wait-event', '-m', 'com.lab126.wifid', 'cmConnected'],
                        stdout=subprocess.PIPE)
proc.stdout.readline()  # Blocks until cmConnected event
```

## curl Availability

### Built-in curl

The Kindle firmware includes `curl` at `/usr/bin/curl`:

```bash
/usr/bin/curl --version
```

kdashboard's code confirms curl availability by checking `commandExists("curl")`:

```cpp
int commandExists(const char* command) {
    char probe[160];
    snprintf(probe, sizeof(probe), "command -v '%s' >/dev/null 2>&1", command);
    return system(probe) == 0;
}
```

### curl Usage in kdashboard

kdashboard uses curl for two purposes:

**1. Fetching dashboard data (GET):**

```cpp
if (commandExists("curl")) {
    snprintf(command, sizeof(command),
        "curl -fsSL --connect-timeout 20 --max-time 55 --max-filesize %ld %s%s%s -o %s %s",
        kMaxDashboardPayloadBytes,
        quoted_header[0] ? "-H " : "",
        quoted_header[0] ? quoted_header : "",
        quoted_header[0] ? " " : "",
        quoted_tmp,
        quoted_url);
}
```

Key flags:
- `-fsSL` — fail silently, show errors, follow redirects
- `--connect-timeout 20` — 20 second connect timeout
- `--max-time 55` — 55 second total timeout
- `--max-filesize` — limit download size (512KB for dashboard payload)
- `-o` — output to file (atomic rename pattern: download to `.tmp`, then rename)

**2. Listening for SSE events (streaming):**

```cpp
snprintf(command, sizeof(command),
    "curl -fsSL --no-buffer --connect-timeout 20 --max-time 65 %s%s%s %s 2>/dev/null",
    quoted_header[0] ? "-H " : "",
    quoted_header[0] ? quoted_header : "",
    quoted_header[0] ? " " : "",
    quoted_url);
FILE* stream = popen(command, "r");
while (g_running && fgets(line_buffer, sizeof(line_buffer), stream)) {
    if (strncmp(line_buffer, "event: planner", 14) == 0) {
        g_event_refresh = 1;
    }
}
```

**3. Posting toggle actions (POST):**

```cpp
snprintf(command, sizeof(command),
    "curl -fsSL --connect-timeout 5 --max-time 12 -X POST "
    "-H 'Content-Type: application/json' -H %s -d %s %s >/dev/null 2>&1 &",
    quoted_header, quoted_body, quoted_url);
```

Note the trailing `&` — the POST is fire-and-forget, running in the background.

### wget as Fallback

kdashboard also supports `wget` as a fallback:

```cpp
} else if (commandExists("wget")) {
    snprintf(command, sizeof(command),
        "wget -q -T 55 %s%s%s -O %s %s",
        quoted_header[0] ? "--header=" : "",
        quoted_header[0] ? quoted_header : "",
        quoted_header[0] ? " " : "",
        quoted_tmp, quoted_url);
}
```

### curl Version Issues

On some Kindle firmware versions, the built-in curl may be outdated or have issues with modern TLS. A [KindleFetch GitHub issue](https://github.com/justrals/KindleFetch/issues/40) documents that replacing `/usr/bin/curl` with a modern static build resolved connection failures. For LAN HTTP (not HTTPS), the built-in curl should work fine.

## Fetching from a Local HTTP Server

### LAN Access

Jailbroken Kindles **can access LAN IP addresses**. The Kindle is a standard Linux device on the network — once connected to WiFi, it has a local IP (typically `192.168.x.x` or `10.0.x.x`) and can reach other devices on the same subnet.

```bash
# From the Kindle, fetch from a local server
curl http://192.168.1.100:8080/dashboard.json
```

### DNS Resolution

DNS resolution works on the Kindle for both:
- **Public domains:** Resolved via configured DNS servers
- **Local hostnames:** Resolved via mDNS/Avahi if available, or via `/etc/hosts`

**Potential issue:** If the Kindle's DNS servers are on the same subnet as the Kindle itself, there can be an IP stack error:

> "The issue is that the Kindle will fail to connect to the Internet when the DNS servers are in the same subnet as the Kindle."
> — [TechRepublic Forums](https://www.techrepublic.com/forums/discussions/kindle-wifi-ip-stack-error/)

For a LAN dashboard, using direct IP addresses (e.g., `192.168.1.100:8080`) avoids DNS issues entirely.

### HTTP vs HTTPS for LAN

For local network communication, **use HTTP** (not HTTPS):
- No SSL certificate issues
- No CA certificate problems
- Faster connection setup
- The kdashboard project uses HTTP for its dashboard fetch and SSE event stream

If HTTPS is needed (e.g., cloud backend), the Kindle's curl may have certificate issues. kdashboard handles this by fetching from cloud endpoints with standard curl flags.

## Python Networking (urllib)

When using Python on the Kindle, `urllib.request` from the standard library works for HTTP/HTTPS:

```python
import urllib.request
import json

url = 'http://192.168.1.100:8080/dashboard.json'
with urllib.request.urlopen(url) as response:
    data = json.load(response)
```

For HTTPS, create an unverified SSL context:

```python
import ssl
import urllib.request

ssl_context = ssl._create_unverified_context()
with urllib.request.urlopen(url, context=ssl_context) as response:
    data = response.read()
```

> Source: [4DCu.be](https://blog.4dcu.be/diy/2020/10/04/PythonKindleDashboard_2.html)

## Network Restrictions on Jailbroken Kindle

### No Firewall

Jailbroken Kindles run a standard Linux kernel with **no firewall rules** by default. There are no restrictions on outbound connections to LAN or WAN addresses.

### noexec and Network

The `/mnt/us/` partition (USB-accessible storage) is mounted with the `noexec` flag. This affects running binaries but not network access — network connections work normally regardless of where the script is stored.

### 2.4GHz WiFi Limitation

Most older Kindle models only support **2.4GHz WiFi**:

> "Kindles can only connect to 2.4gHz except for the latest Paperwhite."
> — [Amazon Forum](https://www.amazonforum.com/s/question/0D56Q00008YQdCYSA1/accessing-a-lan-from-the-kindle-browser)

Ensure your WiFi access point broadcasts a 2.4GHz SSID, or use a mixed-mode router.

### Proxy/VPN Considerations

If your local server is behind a VPN (e.g., WireGuard), the Kindle won't have access unless the VPN client is installed on the Kindle. A [MobileRead thread](https://www.mobileread.com/forums/showthread.php?t=369945) discusses WireGuard on jailbroken Kindle — it's possible but complex.

For a dashboard project, keeping the local server on plain LAN (no VPN) is the simplest approach.

## kdashboard's Network Architecture

kdashboard uses a **three-endpoint** architecture:

| Endpoint | Purpose | Method |
|----------|---------|--------|
| Dashboard URL | Fetch JSON payload | `curl -fsSL -o cache.tmp URL` |
| Events URL (SSE) | Listen for change notifications | `curl -fsSL --no-buffer URL` (long-lived stream) |
| Toggle URL | POST item toggle | `curl -fsSL -X POST -d body URL &` (fire-and-forget) |

The SSE (Server-Sent Events) stream is a key pattern: the Kindle keeps a long-lived HTTP connection open to the server. When the dashboard data changes, the server sends an `event: planner` line. The Kindle's curl watcher detects this and triggers a refresh:

```cpp
if (strncmp(line_buffer, "event: planner", 14) == 0) {
    g_event_refresh = 1;
    fprintf(stderr, "events=planner refresh=1\n");
}
```

When the curl connection drops, it automatically reconnects:

```cpp
const int status = pclose(stream);
if (g_running) {
    fprintf(stderr, "events=reconnect status=%d\n", status);
    sleep(2);
}
```

## Key Takeaways for the Kindle Dashboard Project

1. **curl is available** at `/usr/bin/curl` — use it for all HTTP fetching
2. **LAN access works** — the Kindle can reach `192.168.x.x` addresses on the same WiFi
3. **Use HTTP, not HTTPS** for local server communication to avoid SSL issues
4. **Use direct IP addresses** to avoid DNS resolution issues
5. **WiFi power management is the main challenge** — use `wmiconfig --power maxperf` during development, wait 30s for WiFi after wake
6. **Monitor WiFi via LIPC** — `cmConnected` event from `com.lab126.wifid` signals reconnection
7. **SSE pattern works well** — long-lived curl connection for real-time push notifications from the server
8. **2.4GHz WiFi only** on most Kindle models — ensure your AP supports it

## Related Wiki Files

- [kindle-touch-input.md](kindle-touch-input.md) — Touch event handling
- [kindle-wake-detection.md](kindle-wake-detection.md) — Wake detection and WiFi reconnection after wake
- [kindle-python-availability.md](kindle-python-availability.md) — Python urllib for network access

## Sources

- [kdashboard GitHub](https://github.com/thecodedose/kdashboard) — curl usage patterns in `kindle_dashboard.cpp`
- [blog.davidv.dev: Integrating a Kindle into house automation](https://blog.davidv.dev/posts/integrating-a-kindle-into-house-automation/)
- [4DCu.be: Kindle + Python Dashboard Part 2](https://blog.4dcu.be/diy/2020/10/04/PythonKindleDashboard_2.html)
- [KindleFetch GitHub Issue #40](https://github.com/justrals/KindleFetch/issues/40) — curl replacement on Kindle
- [MobileRead: WireGuard on jailbroken Kindle](https://www.mobileread.com/forums/showthread.php?t=369945)
- [MobileRead Wiki: LIPC](https://wiki.mobileread.com/wiki/Lipc)
