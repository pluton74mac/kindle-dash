# Kindle Screensaver Replacement (linkss Bind-Mount)

> ⚠️ **FW 5.16+ WARNING:** linkss 0.25.N is officially UNSUPPORTED on FW
> 5.16.x and later. NiLuJe (original author) confirmed on MobileRead
> t=195474 #2989: "it isn't supported on FW version with native custom
> screensaver support (and that was, like 5.12 or even earlier?)."
> The installer doesn't refuse to install, so it "succeeds" but the
> bind-mount mechanism conflicts with Amazon's native screensaver system.
> For FW 5.16+, see `references/screensaver-troubleshooting-5.16.md`
> for alternatives (direct FBInk, KOReader Sleep Screen).

> Verified 2026-07-25 against NiLuJe's linkss v0.25.N source code (install.sh,
> linkss.sh, linkss.conf on GitHub) and MobileRead forum threads t=195474
> (pages 1, 29, 194, 200, 203), t=201572. Confirmed by PW4 owner `0x6c616d70` on
> MobileRead, and by Reddit user `ridizn` (r/kindle).

> **This reference covers the linkss approach for older firmware (pre-5.12).
> The installation steps below may work on 5.16.x with the linker symlink
> fix, but the bind-mount may not function correctly due to the native
> screensaver system. Use with caution on newer firmware.**

## Why Direct Copy to the Blanket Dir Fails

The Kindle framework stores screensaver images at:

```
/usr/share/blanket/screensaver/
```

**This is NOT a regular directory.** It is a **tmpfs mount** — RAM-backed, ~4MB.
Confirmed by `mount` output on a PW (MobileRead t=201572):

```
/usr/share/blanket/screensaver type tmpfs (rw,relatime,size=4096k)
```

Three problems with directly copying files there:

1. **Rootfs is read-only.** Writing to `/usr/share/...` requires `mntroot rw`
   first. Without it, `cp` silently fails.
2. **The directory is tmpfs.** Even if you write files there successfully, they
   live in RAM only. The framework regenerates stock screensavers into this
   tmpfs on every boot — your files are overwritten.
3. **The framework caches filenames.** The framework expects `bg_ss00.png`,
   `bg_ss01.png`, … and renames user images to this convention itself. Dropping
   a file with a different name does nothing until the framework processes it.

## The Correct Approach: linkss Bind-Mount

linkss (NiLuJe's ScreenSavers Hack) creates a directory on the persistent user
store, populates it with your images, and **bind-mounts** it over the tmpfs path
*before* the framework starts looking for screensavers.

### How linkss works (from source)

**Upstart job** (`/etc/upstart/linkss.conf`):
```bash
start on starting framework    # ← runs BEFORE the framework
stop on (stopped framework or ota-update)
```

The `pre-start script` block runs `/mnt/us/linkss/bin/linkss`, which:
1. Creates a tmpfs on `/mnt/us/linkss/ss-internal/`
2. Copies/converts user images from `/mnt/us/linkss/screensavers/` into the
   internal dir, renaming them to `bg_ss00.png`, `bg_ss01.png`, …
3. Bind-mounts the internal dir over `/usr/share/blanket/screensaver/`

When the framework reads `/usr/share/blanket/screensaver/`, it actually reads
from the linkss-managed directory. The bind-mount persists until the framework
stops (reboot/shutdown).

### KUAL scripts run as root

Confirmed by the linkss KUAL helper (`linkss.sh`):
```bash
if [ "$(id -u)" -ne 0 ] ; then
    kh_msg "unprivileged user, aborting" E v
    exit 1
fi
```
KUAL extensions execute with root privileges. No `sudo` needed.

## Image Format Requirements (PW4)

| Property | Value |
|---|---|
| **Dimensions** | 1072 × 1448 pixels (portrait) |
| **Format** | PNG only (non-PNG discarded) |
| **Bit depth** | 8-bit grayscale, 256-color palette |
| **ImageMagick identify** | `PNG 1072x1448 1072x1448+0+0 8-bit Gray 256c` |
| **PIL mode** | `"L"` (8-bit grayscale) |
| **Color** | Grayscale preferred; color works but framework quantizes |
| **Alpha** | Tolerated but unnecessary |

linkss's own staging processor produces exactly this format:
```bash
convert input.png \
  -filter LanczosSharp \
  -resize 1072x1448 \
  -colorspace Gray \
  -dither FloydSteinberg \
  -remap kindle_colors.gif \
  -quality 75 \
  -define png:color-type=0 \
  -define png:bit-depth=8 \
  output.png
```

### Filename convention

Framework expects: `bg_ss00.png`, `bg_ss01.png`, `bg_ss02.png` (zero-indexed,
zero-padded to 2 digits). The framework **renames files to this pattern itself**
— confirmed by MobileRead user `Machinus`: *"I noticed that it renamed the first
image to bg_ss00.png when it finally worked."*

With linkss, you drop arbitrarily-named `.png` files into
`/mnt/us/linkss/screensavers/` and the hack renames them.

### Verify your image

```bash
# ImageMagick
magick identify your_image.png
# Expected: your_image.png PNG 1072x1448 1072x1448+0+0 8-bit Gray 256c

# Python/Pillow
from PIL import Image
img = Image.open("your_image.png")
assert img.size == (1072, 1448)
assert img.mode == "L"
```

File permissions should be `chmod 644` or `655` (rw-r--r--). Confirmed by
KOReader issue #13330 (ViToni).

## Installation (One-Time)

### Prerequisites
- Jailbroken PW4 with KUAL installed
- MRPI (MobileRead Package Installer) — from MobileRead t=251143

### Steps

1. Download linkss .bin for PW4:
   - **Pythonless fork (prebuilt .bin):** [github.com/bfabiszewski/kindle-screensavers](https://github.com/bfabiszewski/kindle-screensavers)
   - File: `Update_linkss_0.25.N.mobitool_install_pw2_kt2_kv_pw3_koa_kt3_koa2_pw4_kt4.bin`
   - Or original from MobileRead Snapshots thread (t=225030)

2. Copy to Kindle's mrpackages dir (USB mass storage):
   ```sh
   cp Update_linkss_0.25.N.*_install_*pw4*.bin /Volumes/Kindle/mrpackages/
   ```

3. On Kindle: `KUAL → Helper → Install MR Packages`

4. Wait for reboot. Put Kindle to sleep — you should see a "hack installed"
   confirmation screensaver.

5. Enable at boot: `KUAL → Screen Savers → Enable hack at boot`

6. Delete the placeholder:
   ```sh
   rm /mnt/us/linkss/screensavers/00_you_can_delete_me*.png
   ```

## FW 5.16+ quirk — `xzdec: not found` during MRPI install AND runtime

If running firmware **5.16 or above** (not just 5.17+ as some forum posts
suggest — confirmed on a PW4 running 5.16.7), the linkss `.bin` installer
extracted by MRPI contains an `xzdec` binary that needs `/lib/ld-linux.so.3`
to run. On newer firmware this symlink doesn't exist, so MRPI's log shows:

```
./install.sh: line 88: ./xzdec: not found
tar: short read
Hu oh... Got return code 1 . . . :(
```

**Fix:** create the symlink via a KUAL script (KUAL runs as root), then
re-install linkss. The symlink persists across reboots. A minimal KUAL script:

```bash
#!/bin/sh
if [ ! -f /lib/ld-linux.so.3 ]; then
    mntroot rw
    ln -s /lib/ld-linux-armhf.so.3 /lib/ld-linux.so.3
    mntroot ro
fi
```

Or via SSH: `mntroot rw && ln -s /lib/ld-linux-armhf.so.3 /lib/ld-linux.so.3 && mntroot ro`.

**To SSH in without USBNetwork:** if Tailscale is installed on the Kindle
(`/mnt/us/extensions/tailscale/`), start it via
`KUAL → Tailscale → Start Tailscaled → Standard (Userspace)`, then
`ssh root@<kindle-ip>` (default password: `kindle`).

**Check MRPI log to diagnose:** `/mnt/us/extensions/MRInstaller/log/mrinstaller.log`
(via USB at `/Volumes/Kindle/extensions/MRInstaller/log/mrinstaller.log`)
shows the exact error if the install failed.

### CRITICAL: ALL linkss runtime binaries need the linker symlink too

Even after a successful linkss install (the `.bin` extraction works), **all
linkss runtime binaries** also depend on `/lib/ld-linux.so.3`:

```
/mnt/us/linkss/bin/identify  → interpreter /lib/ld-linux.so.3
/mnt/us/linkss/bin/convert   → interpreter /lib/ld-linux.so.3
/mnt/us/linkss/bin/fbink     → interpreter /lib/ld-linux.so.3
/mnt/us/linkss/bin/mobitool  → interpreter /lib/ld-linux.so.3
```

If the symlink is missing, these binaries silently fail when linkss tries to
process images (on framework restart, on USB unplug autoreboot, or on
"Process staging images"). Symptoms:

- **Framework restart hangs at the load screen** — `KUAL → Screen Savers →
  Restart framework now` starts a restart, but linkss's pre-start script
  fails because `convert`/`identify` can't execute. The framework hangs at
  the boot/load screen and never completes. User must hard-reboot (hold power
  button 15s).
- **"No new images to process"** even though images exist in
  `/mnt/us/linkss/screensavers/` — the staging processor can't run
  `identify` to validate the image, so it skips it.
- **Default screensavers still showing** after framework restart — the
  bind-mount never happens because the upstart pre-start script fails.

**Verify the symlink exists before any linkss operation.** If you ran the
`fix_linker.sh` KUAL script and the install succeeded, the symlink is
already in place — but verify if anything goes wrong. The symlink is
permanent across reboots once created.

### FW 5.16+ quirk — `xzdec: not found` during MRPI install AND runtime

> **Note:** This affects FW 5.16+ — not just 5.17+ as some forum posts suggest.
> Confirmed on a PW4 running **5.16.7**.

### `autoreboot` flag causes framework restart hangs

After linkss installs successfully, the `autoreboot` flag
(`/mnt/us/linkss/autoreboot`) is set by default. When you do
`KUAL → Screen Savers → Restart framework now`, the framework hangs at the
load screen and never completes — the user must hard-reboot (hold power 15s).

**Fix:** remove the autoreboot flag before restarting:
```sh
rm /Volumes/Kindle/linkss/autoreboot
```
Then use a **full Kindle reboot** (Settings → Menu → Restart) instead of a
framework restart. The linkss upstart job (`start on starting framework`) runs
during a full boot and the bind-mount succeeds. Framework restart skips the
upstart job's trigger.

### Special Offers (ads) devices

linkss does NOT bypass Special Offers. Unsubscribe via Amazon account settings
(~$20) first. The Kindle for this project should be SO-free.

## Deploying the Dashboard Screensaver Image

### One-time: install the image

```sh
# Via USB mass storage:
cp bg_ss00.png /Volumes/Kindle/linkss/screensavers/bg_ss00.png
find /Volumes/Kindle/linkss -name '._*' -delete   # clean macOS resource forks

# Or via SSH:
scp bg_ss00.png root@kindle:/mnt/us/linkss/screensavers/bg_ss00.png
```

Then restart the framework (REQUIRED after every image change):

```sh
# Via KUAL:
# KUAL → Screen Savers → Restart framework now

# Or via SSH:
stop framework
sync
start framework
```

### Generating the screensaver PNG (server-side, Pillow)

```python
from PIL import Image, ImageDraw, ImageFont

img = Image.new("L", (1072, 1448), 0)  # black background, 8-bit grayscale
draw = ImageDraw.Draw(img)

font_brand = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 48)
font_small = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 28)

# "KINDLE DASH" centered
label = "KINDLE DASH"
bbox = draw.textbbox((0, 0), label, font=font_brand)
lw = bbox[2] - bbox[0]
lh = bbox[3] - bbox[1]
draw.text(((1072 - lw) // 2, (1448 - lh) // 2), label, fill=255, font=font_brand)

# Subtle line below
line_y = (1448 // 2) + lh + 20
draw.line([(1072//2 - 200, line_y), (1072//2 + 200, line_y)], fill=80, width=2)

# URL at bottom
footer = "the agent-agent.nousresearch.com"
bbox = draw.textbbox((0, 0), footer, font=font_small)
fw = bbox[2] - bbox[0]
draw.text(((1072 - fw) // 2, 1448 - 80), footer, fill=100, font=font_small)

img.save("bg_ss00.png", format="PNG")
```

### For periodic updates (dashboard script)

```sh
#!/bin/sh
# update-screensaver.sh — copies latest dashboard image and restarts framework

DASHBOARD_IMG="/mnt/us/dashboard/latest.png"
SS_DIR="/mnt/us/linkss/screensavers"

rm -f "$SS_DIR"/bg_ss*.png
cp "$DASHBOARD_IMG" "$SS_DIR/bg_ss00.png"

# Restart framework (required to pick up new image)
stop framework
sync
start framework
```

Or use the **autoreboot** trigger for USB-based updates:
```sh
# Enable autoreboot once: KUAL → Screen Savers → Enable autoreboot
# After each image update via USB:
touch /mnt/us/linkss/reboot
# Kindle restarts framework ~10s after USB unplug
```

## Framework Restart — Required After Every Image Change

The framework caches the screensaver list at boot. Adding/removing files
without a restart can cause: new images not showing, black screen on sleep,
framework instability ("going crazy").

**There is no `lipc-set-prop` that forces a screensaver reload.** The
`lipc-set-prop com.lab126.powerd -i touchScreenSaverTimeout` trick only
resets the sleep timer, not the image pool.

Restart methods:
- **KUAL:** `KUAL → Screen Savers → Restart framework now`
- **SSH:** `stop framework && sync && start framework`
- **Full restart:** `[HOME] → [MENU] → Settings → [MENU] → Restart`
- **Autoreboot:** drop blank file `reboot` in `/mnt/us/linkss/`, framework
  restarts ~10s after USB unplug

## Manual Bind-Mount (Alternative to linkss)

If you want to replicate the mechanism without installing linkss:

```sh
#!/bin/sh
# Run as root, before framework start (via upstart job or KUAL boot extension)
SS_DIR="/mnt/us/screensavers"           # your persistent image dir
TARGET="/usr/share/blanket/screensaver"  # framework's expected path

# Name your file correctly
cp /mnt/us/my_dashboard.png "$SS_DIR/bg_ss00.png"

# Bind-mount
mount --bind "$SS_DIR" "$TARGET"
```

This will NOT survive a reboot unless installed as an upstart job.
**For this project, use linkss — it handles everything.**

## Restoring Original Screensavers

To restore native Kindle screensavers, uninstall linkss:

```sh
# Via MRPI: install the uninstall .bin
# Update_linkss_0.25.N_uninstall.bin → /mnt/us/mrpackages/
# KUAL → Helper → Install MR Packages
```

Or disable at boot:
```sh
# KUAL → Screen Savers → Disable hack at boot
# (removes /mnt/us/linkss/auto trigger file)
```

## Source References

| Source | URL | What it confirms |
|---|---|---|
| NiLuJe linkss main thread | [MobileRead t=195474](https://www.mobileread.com/forums/showthread.php?t=195474) | Image sizes, install process, framework restart requirement |
| linkss page 29 | [t=195474 p=29](https://www.mobileread.com/forums/showthread.php?t=195474&page=29) | Bind-mount over tmpfs mechanism |
| linkss page 194 | [t=195474 p=194](https://www.mobileread.com/forums/showthread.php?t=195474&page=194) | 8-bit Gray 256c format, bg_ss00.png renaming, PW4 confirmation |
| linkss page 203 | [t=195474 p=203](https://www.mobileread.com/forums/showthread.php?t=195474&page=203) | FW 5.17+ linker symlink fix |
| bfabiszewski fork (source) | [github.com/bfabiszewski/kindle-screensavers](https://github.com/bfabiszewski/kindle-screensavers) | install.sh, linkss.sh, linkss.conf source code |
| PW4 user confirmation | Reddit r/kindle (ridizn) | `/mnt/us/linkss/screensavers/` + 1072×1448 for PW4 |
| PW mount output | [MobileRead t=201572](https://www.mobileread.com/forums/showthread.php?t=201572) | `tmpfs (rw,relatime,size=4096k)` on blanket/screensaver |
| KUAL runs as root | linkss.sh source (`id -u` check) | KUAL extensions execute with root privileges |
| Image permissions | [koreader#13330](https://github.com/koreader/koreader/issues/13330) | `chmod 655` (rw-r--r--) for image files |
