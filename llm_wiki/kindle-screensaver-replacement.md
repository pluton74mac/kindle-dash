# Kindle Paperwhite 4 — Native Screensaver Replacement

> Research for the **Kindle the agent Dashboard** project.
> Device: Kindle Paperwhite 4 (10th Gen, 2018) — 6" 300 PPI e-ink, 1072×1448 portrait, jailbroken with KUAL.
>
> **Status:** Verified against NiLuJe's linkss source (v0.25.N), MobileRead forum threads
> (t=195474 pages 1, 29, 194), and confirmed by PW4 owner `0x6c616d70` on the same thread.

---

## TL;DR — Why Our Direct Replacement Failed

Our KUAL script tried to **overwrite files in `/usr/share/blanket/screensaver/`**
directly. This directory is **not a regular folder** — it is a **tmpfs mount**
(RAM-backed, ~4 MB, `size=4096k`). Three things go wrong:

1. **Rootfs is read-only by default.** Writing to `/usr/share/...` requires
   `mntroot rw` first. Without it, `cp` silently fails (or the write is
   discarded).
2. **The directory is tmpfs.** Even if you write files there successfully,
   they live in RAM only. The Kindle framework **regenerates the stock
   screensavers into this tmpfs on every boot** via its own upstart job —
   your files are overwritten or ignored.
3. **The framework caches filenames.** The framework expects files named
   `bg_ss00.png`, `bg_ss01.png`, … and **renames** user images to this
   convention on its own schedule. Dropping a file with a different name
   into the raw blanket dir does nothing until the framework processes it
   — and the framework only processes images from its **expected source**,
   not arbitrary files placed in the tmpfs.

The **correct** approach (used by linkss) is to **bind-mount** a directory
from the user store (`/mnt/us/`) over `/usr/share/blanket/screensaver/` at
boot time, *before* the framework starts. This is what the linkss hack does.

---

## 1. Exact Paths

### Stock screensaver directory (the tmpfs)

```
/usr/share/blanket/screensaver/
```

- Confirmed by `mount` output on a PW:
  `/usr/share/blanket/screensaver type tmpfs (rw,relatime,size=4096k)`
  — source: MobileRead t=201572
- This is where the framework **looks** for `bg_ss*.png` files at sleep time.
- It is **volatile** — rebuilt on every boot.

### Stock image source (read-only rootfs squashfs)

The *original* `bg_ss*.png` files are baked into the read-only rootfs and
copied into the tmpfs at boot. The source path inside the squashfs is the
same: `/usr/share/blanket/screensaver/`. You cannot permanently modify these
without rebuilding the rootfs image.

### linkss user-facing directory (persistent, on user store)

```
/mnt/us/linkss/screensavers/
```

- This is where you, the user, drop your custom PNG files.
- `/mnt/us/` is the USB-visible partition (FAT32), so you can access it by
  plugging the Kindle into a computer — no SSH required.
- The linkss upstart job copies/converts these into the active pool and
  bind-mounts the result over the tmpfs path.

### Active pool (internal, linkss-managed)

```
/var/linkss/   (or /mnt/us/linkss/ss-internal/ on some versions)
```

- linkss creates a tmpfs here, populates it with your converted images
  (renamed to `bg_ss00.png`, `bg_ss01.png`, …), and bind-mounts it over
  `/usr/share/blanket/screensaver/`.

### Legacy/alternative path (older hacks, FW < 5.5)

```
/var/local/custom_screensavers/
```

- Used by the *old* `custom_screensaver.so` blanket module (pre-linkss).
- linkss removes this on install (`lipc-set-prop com.lab126.blanket unload
  custom_screensaver`).
- **Not used on PW4** — included here for completeness only.

---

## 2. Image Format & Size Requirements

### Dimensions (PW4 / PW3 / KV / KOA)

```
1072 × 1448 pixels (portrait)
```

This is the **exact** e-ink panel resolution. Other models:
- Touch / KT2 / KT3: 600 × 800
- PW / PW2: 758 × 1024
- KV / PW3 / KOA / PW4: **1072 × 1448**
- KOA2: 1264 × 1680

### Format

- **PNG only.** Non-PNG files are discarded by the hack/framework.
- **8-bit grayscale** is the preferred/recommended format.
- Color PNGs *work* (the framework will quantize them), but grayscale is
  more efficient and avoids processing surprises.
- Alpha channel is tolerated but unnecessary.

### Bit depth — the critical detail

From the MobileRead thread (user `Machinus`, confirmed by `magick identify`):

```
bg_ss00.png PNG 1072x1448 1072x1448+0+0 8-bit Gray 256c 502614B
```

The image must be **8-bit grayscale with a 256-color palette** (`8-bit Gray
256c` in ImageMagick terms). linkss's own staging processor produces exactly
this via:

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

The key ImageMagick defines:
- `-define png:color-type=0` → grayscale (color type 0)
- `-define png:bit-depth=8` → 8-bit

**Our dashboard image** (PIL `mode='L'`, 1072×1448, no alpha) matches this
spec. The image format is **not** the reason our replacement failed.

### How to verify your image

On a machine with ImageMagick:
```bash
magick identify your_image.png
# Expected: your_image.png PNG 1072x1448 1072x1448+0+0 8-bit Gray 256c ...
```

Or with Python/Pillow:
```python
from PIL import Image
img = Image.open("your_image.png")
assert img.size == (1072, 1448), f"Wrong size: {img.size}"
assert img.mode == "L", f"Wrong mode: {img.mode} (expected 'L' = 8-bit grayscale)"
```

---

## 3. Filename Convention

### The `bg_ssNN.png` pattern

The Kindle framework expects screensaver files named:

```
bg_ss00.png
bg_ss01.png
bg_ss02.png
...
```

- **Zero-indexed, zero-padded to 2 digits.**
- The framework cycles through these in order on each sleep event.
- **The framework renames files to this pattern itself** — confirmed by
  `Machinus` on MobileRead: *"I noticed that it renamed the first image to
  `bg_ss00.png` when it finally worked."*

### What this means for manual replacement

If you're using **linkss**, you do **not** need to follow this convention.
You drop arbitrarily-named `.png` files into `/mnt/us/linkss/screensavers/`
and the hack renames them to `bg_ssNN.png` when populating the active pool.

If you're doing a **manual bind-mount** (see §5), you **must** name your
files `bg_ss00.png`, `bg_ss01.png`, etc. yourself, because there's no hack
layer doing the rename for you.

---

## 4. Permissions & How KUAL Scripts Run

### KUAL runs scripts as **root**

Confirmed by the linkss KUAL helper script (`src/extensions/linkss/bin/linkss.sh`):

```bash
# We need the proper privileges...
if [ "$(id -u)" -ne 0 ] ; then
    kh_msg "unprivileged user, aborting" E v
    exit 1
fi
```

This guard exists because KUAL **does** launch extensions as root. Your
KUAL-launched shell script inherits root. No `sudo` needed.

### The rootfs is mounted read-only

Even as root, you cannot write to `/usr/share/...` without remounting:

```bash
mntroot rw    # remount rootfs read-write
# ... your writes ...
mntroot ro    # remount read-only (important for safety)
```

`/mnt/us/` (the user store) is always writable — no remount needed.

### File permissions for images

From the KOReader issue tracker (koreader/koreader#13330, ViToni):

> Make sure your new files have the same permissions as original ones.
> I believe those were `chmod 655` (rw-r--r--).

In practice, `chmod 644` also works. The key is that the framework must be
able to **read** the file.

---

## 5. The Bind-Mount Approach (How linkss Works)

This is the **core mechanism** and the reason direct file replacement fails.

### The problem

`/usr/share/blanket/screensaver/` is a tmpfs that the framework populates at
boot. You cannot "replace" files in it permanently because:
- The framework overwrites them on every boot.
- The tmpfs is RAM-only — even surviving across sleep cycles isn't guaranteed
  if the framework reclaims the space.

### The linkss solution

linkss creates its own directory on the persistent user store, populates it
with your images, and then **bind-mounts** it over the tmpfs path *before*
the framework starts looking for screensavers.

#### The upstart job

linkss installs an upstart job at `/etc/upstart/linkss.conf`:

```bash
# Start late so we can recover if it goes wrong...
start on starting framework
stop on (stopped framework or ota-update)
```

The critical line is `start on starting framework` — linkss runs its setup
**just before** the framework starts, so the bind-mount is in place before
the framework tries to read screensavers.

#### The bind-mount (conceptual)

```bash
# 1. Create a persistent directory with your images
mkdir -p /mnt/us/linkss/screensavers
cp your_image.png /mnt/us/linkss/screensavers/bg_ss00.png

# 2. Mount it over the tmpfs path (as root, before framework start)
mount --bind /mnt/us/linkss/screensavers /usr/share/blanket/screensaver
```

After this, when the framework reads `/usr/share/blanket/screensaver/`,
it actually reads from `/mnt/us/linkss/screensavers/`.

> **Note:** The actual linkss implementation is slightly more sophisticated —
> it uses a tmpfs on `/mnt/us/linkss/ss-internal/` and bind-mounts *that*
> (see MobileRead t=195474 page 29: *"mount a tmpfs on
> $LINKSS_BASEDIR/ss-internal and bind-mount that over
> /usr/share/blanket/screensaver"*). This avoids wearing the flash with
> frequent image swaps and allows the hack to process/rename images without
> touching the user-visible directory.

#### How to do it manually (without linkss)

If you want to replicate the mechanism without installing the full hack:

```bash
#!/bin/sh
# Manual screensaver bind-mount — run as root, before framework start
# (e.g., via an upstart job or KUAL "run at boot" extension)

SS_DIR="/mnt/us/screensavers"          # your persistent image dir
TARGET="/usr/share/blanket/screensaver" # the framework's expected path

# Ensure your image is named correctly
# cp /mnt/us/my_dashboard.png "$SS_DIR/bg_ss00.png"

# Bind-mount
mount --bind "$SS_DIR" "$TARGET"
```

**But:** This will not survive a reboot unless you install it as an upstart
job (like linkss does). For the the agent Dashboard project, the **recommended
approach is to install linkss** and drop images into its directory — see §7.

---

## 6. Framework Restart — When and Why

### You MUST restart the framework after changing images

From NiLuJe's hack documentation (MobileRead t=195474, post #1):

> You'll **have** to restart your Kindle in order to take your new
> screensavers into account and prevent the framework from going crazy.

The framework **caches** the screensaver list at boot. Adding/removing files
in the active pool without a restart can cause:
- New images not showing up
- Black screen on sleep
- Framework instability ("going crazy")

### How to restart the framework

#### Method A: KUAL button (preferred, no SSH)

```
KUAL → Screen Savers → Restart framework now
```

This calls linkss's `framework_restart()` function, which does:
```bash
stop framework
sync
start framework
```

(On FW 5.x it also shows the splash screen during restart.)

#### Method B: Full Kindle restart

```
[HOME] → [MENU] → Settings → [MENU] → Restart
```

#### Method C: Command line (SSH / KUAL script)

```bash
# Upstart-based (FW 5.x, includes PW4)
stop framework
sync
start framework

# Or the legacy init.d path (not used on PW4)
/etc/init.d/framework restart
```

#### Method D: The autoreboot trigger

linkss has an "autoreboot" feature — drop a blank file named `reboot` in
`/mnt/us/linkss/` and the Kindle does a quick framework restart ~10 seconds
after you unplug USB. Useful for a dashboard that updates images over USB
mass storage periodically.

### Do NOT use `lipc-set-prop` to refresh screensavers

There is no `lipc-set-prop` command that forces a screensaver image reload.
The `lipc-set-prop com.lab126.powerd -i touchScreenSaverTimeout` trick only
resets the *sleep timer*, not the image pool. The framework must be
restarted to pick up new images.

---

## 7. Recommended Approach: Install linkss

For the the agent Dashboard project, **install the linkss hack** rather than
rolling a custom bind-mount. Here's why:

- It handles the upstart job, bind-mount, image conversion, and filename
  renaming automatically.
- It survives reboots.
- It provides KUAL buttons for framework restart and image management.
- It's battle-tested on PW4 (the install .bin explicitly targets `pw4`).

### Installation steps

1. **Jailbreak the Kindle** (already done — KUAL is running).

2. **Install MRPI** (MobileRead Package Installer):
   - Download from MobileRead t=251143
   - Copy the extension to `/mnt/us/extensions/`

3. **Install linkss** via MRPI:
   - Download `Update_linkss_0.25.N_install_pw2_kt2_kv_pw3_koa_kt3_koa2_pw4_kt4.bin`
     from the Snapshots thread (MobileRead t=225030) or the
     [bfabiszewski fork](https://github.com/bfabiszewski/kindle-screensavers)
     (pythonless, includes prebuilt .bin)
   - Copy the `.bin` to `/mnt/us/mrpackages/`
   - Run: `KUAL → Helper → Install MR Packages`
   - Kindle reboots. You should see a "hack installed" screensaver on sleep.

4. **Enable the hack**:
   - `KUAL → Screen Savers → Enable hack at boot` (creates `/mnt/us/linkss/auto`)

5. **Add your images**:
   - Copy your 1072×1448 8-bit grayscale PNGs to `/mnt/us/linkss/screensavers/`
   - **Delete** the default `00_you_can_delete_me-*.png` placeholder

6. **Restart the framework**:
   - `KUAL → Screen Savers → Restart framework now`

### Using linkss with the the agent Dashboard

For the dashboard use case (single image, updated periodically):

```bash
# On the Kindle (via SSH or KUAL script):
# 1. Copy new dashboard image to linkss screensavers dir
cp /mnt/us/dashboard/latest.png /mnt/us/linkss/screensavers/bg_ss00.png

# 2. Remove any other images (we want only our dashboard)
rm -f /mnt/us/linkss/screensavers/bg_ss01.png
rm -f /mnt/us/linkss/screensavers/bg_ss02.png
# ... etc

# 3. Restart framework to pick up the new image
stop framework
sync
start framework
```

Or use the **autoreboot** trigger for USB-based updates:
```bash
# Enable autoreboot once:
# KUAL → Screen Savers → Enable autoreboot

# After each image update via USB:
touch /mnt/us/linkss/reboot
# Kindle restarts framework ~10s after USB unplug
```

---

## 8. PW4-Specific Quirks

### No major quirks — PW4 is well-supported

The PW4 (device IDs `0G1`–`0G6`, `0LK`, `0LL`, etc. in the new ID scheme)
is explicitly supported by linkss v0.25.N. The install .bin filename
includes `pw4`:
```
Update_linkss_0.25.N_install_pw2_kt2_kv_pw3_koa_kt3_koa2_pw4_kt4.bin
```

### FW 5.17+ requires a linker symlink

From MobileRead t=195474 page 203 (user `rand0m`, confirmed on Oasis 3
with FW 5.17+):

If running firmware **5.17 or above**, the linkss binary may fail to start
because it can't find `/lib/ld-linux.so.3`. Fix:

```bash
mntroot rw
ln -s /lib/ld-linux-armhf.so.3 /lib/ld-linux.so.3
mntroot ro
```

Then install linkss via MRPI as usual. **Check your firmware version first** —
if below 5.17, this step is unnecessary.

### Special Offers (ads) devices

If the Kindle has Special Offers (lock screen ads), **linkss will not
bypass them**. You must unsubscribe from Special Offers first (via Amazon
account settings, costs ~$20). The "Swipe to Unlock" behavior of SO devices
is also not replicated by the hack.

For the the agent Dashboard, the Kindle should be **SO-free** (already
unsubscribed).

### Screen size auto-detection

linkss auto-detects the screen size from the device. For PW4, it correctly
identifies 1072×1448. You can verify by checking the `MY_SCREEN_SIZE`
variable in the hack's internal scripts after install.

---

## 9. Step-by-Step: Complete Working Procedure for PW4

### Prerequisites
- Jailbroken PW4 with KUAL installed and working
- SSH access (via USBNetwork or WiFi) — recommended but not strictly required
- Your dashboard image: 1072×1448, 8-bit grayscale PNG (`mode='L'` in PIL)

### Step 1: Install linkss

```bash
# On your computer:
# 1. Download linkss .bin for PW4 from GitHub (bfabiszewski fork, prebuilt)
#    or MobileRead Snapshots thread (t=225030)

# 2. Copy to Kindle's mrpackages dir (USB mass storage)
cp Update_linkss_0.25.N_install_pw2_kt2_kv_pw3_koa_kt3_koa2_pw4_kt4.bin \
   /Volumes/Kindle/mrpackages/

# 3. On Kindle: KUAL → Helper → Install MR Packages
# 4. Wait for reboot
```

### Step 2: Verify linkss is active

```bash
# After reboot, put Kindle to sleep.
# You should see a "hack installed" confirmation screensaver.
# If you see stock Amazon screensavers, the hack isn't enabled.

# Enable via KUAL:
# KUAL → Screen Savers → Enable hack at boot
```

### Step 3: Prepare your image

```python
# Python/Pillow — verify format
from PIL import Image
img = Image.open("dashboard.png")
assert img.size == (1072, 1448)
assert img.mode == "L"  # 8-bit grayscale

# If you need to convert:
img = img.convert("L").resize((1072, 1448))
img.save("dashboard.png")
```

### Step 4: Copy image to linkss directory

```bash
# Via USB mass storage:
cp dashboard.png /Volumes/Kindle/linkss/screensavers/bg_ss00.png

# Remove the placeholder:
rm /Volumes/Kindle/linkss/screensavers/00_you_can_delete_me*.png

# Or via SSH:
scp dashboard.png root@kindle:/mnt/us/linkss/screensavers/bg_ss00.png
```

### Step 5: Restart the framework

```bash
# Via KUAL:
# KUAL → Screen Savers → Restart framework now

# Or via SSH:
stop framework
sync
start framework
```

### Step 6: Verify

Put the Kindle to sleep (press power button briefly). Your dashboard image
should appear as the screensaver.

### Step 7: For periodic dashboard updates

```bash
#!/bin/sh
# update-screensaver.sh — run via KUAL or cron
# Copies latest dashboard image and restarts framework

DASHBOARD_IMG="/mnt/us/dashboard/latest.png"
SS_DIR="/mnt/us/linkss/screensavers"

# Clear old images
rm -f "$SS_DIR"/bg_ss*.png

# Copy new image
cp "$DASHBOARD_IMG" "$SS_DIR/bg_ss00.png"

# Restart framework (required to pick up new image)
stop framework
sync
start framework
```

---

## 10. Alternative Approaches (Summary)

| Approach | Complexity | Persistence | Recommended? |
|---|---|---|---|
| **linkss hack** (bind-mount) | Install .bin via MRPI | Survives reboot | ✅ **Yes** |
| Manual bind-mount script | Medium (need upstart job) | Survives reboot if upstart | For custom setups |
| Direct tmpfs file copy | Low | ❌ Lost on reboot | ❌ Does not work |
| KOReader screensaver | Medium | App-level only | For KOReader users only |
| Online Screensaver hack | Medium | Fetches from URL | For web-served images |
| Book cover as screensaver | Low (built-in FW 5.13.5+) | Native | Not for dashboards |

### linkss (NiLuJe's ScreenSavers Hack)
- **Repo:** [bfabiszewski/kindle-screensavers](https://github.com/bfabiszewski/kindle-screensavers) (pythonless fork with prebuilt .bin)
- **Original:** MobileRead t=195474 (NiLuJe)
- **Snapshots:** MobileRead t=225030
- **How:** Bind-mounts a tmpfs over `/usr/share/blanket/screensaver/` via upstart

### MRPI (MobileRead Package Installer)
- **Thread:** MobileRead t=251143
- **Purpose:** Installs .bin packages via KUAL — required to install linkss

### Online Screensaver hack
- **Repo:** [poja1993/onlinescreensaver](https://github.com/poja1993/onlinescreensaver)
- **Purpose:** Fetches screensaver images from a URL at intervals
- **Relevance:** Could be used for a web-served dashboard, but linkss + cron is simpler

### KOReader's built-in screensaver
- KOReader has its own screensaver handler that bypasses the native framework
- Only active when KOReader is running — not useful for a system-level dashboard

---

## 11. Key Source References

| Source | URL | What it confirms |
|---|---|---|
| NiLuJe linkss hack (main thread) | [MobileRead t=195474](https://www.mobileread.com/forums/showthread.php?t=195474) | Image sizes per model, install process, framework restart requirement |
| linkss page 29 | [t=195474 p=29](https://www.mobileread.com/forums/showthread.php?t=195474&page=29) | Bind-mount over tmpfs mechanism |
| linkss page 194 | [t=195474 p=194](https://www.mobileread.com/forums/showthread.php?t=195474&page=194) | 8-bit Gray 256c format, `bg_ss00.png` renaming, PW4 confirmation |
| linkss page 203 | [t=195474 p=203](https://www.mobileread.com/forums/showthread.php?t=195474&page=203) | FW 5.17+ linker symlink fix |
| bfabiszewski fork (source) | [github.com/bfabiszewski/kindle-screensavers](https://github.com/bfabiszewski/kindle-screensavers) | install.sh, linkss.sh, linkss.conf source code |
| PW4 user confirmation | Reddit r/kindle (ridizn) | `/mnt/us/linkss/screensavers/` + 1072×1448 for PW4 |
| PW mount output | [MobileRead t=201572](https://www.mobileread.com/forums/showthread.php?t=201572) | `tmpfs (rw,relatime,size=4096k)` on blanket/screensaver |
| KUAL runs as root | linkss.sh source (`id -u` check) | KUAL extensions execute with root privileges |
| Image permissions | [koreader#13330](https://github.com/koreader/koreader/issues/13330) | `chmod 655` (rw-r--r--) for image files |

---

## 12. Quick Reference Card

```bash
# === ONE-TIME SETUP ===
# 1. Install linkss via MRPI (KUAL → Helper → Install MR Packages)
# 2. Enable: KUAL → Screen Savers → Enable hack at boot
# 3. Delete placeholder: rm /mnt/us/linkss/screensavers/00_you_can_delete_me*.png

# === UPDATE DASHBOARD IMAGE ===
# Image must be: 1072×1448, 8-bit grayscale PNG (PIL mode 'L')
cp dashboard.png /mnt/us/linkss/screensavers/bg_ss00.png

# Restart framework (REQUIRED after every image change):
stop framework && sync && start framework
# OR: KUAL → Screen Savers → Restart framework now

# === TROUBLESHOOTING ===
# Check if linkss is running:
ls -la /usr/share/blanket/screensaver/  # should show your bg_ss00.png
mount | grep blanket                     # should show a bind-mount

# Check image format (on computer with ImageMagick):
magick identify bg_ss00.png
# Expected: PNG 1072x1448 1072x1448+0+0 8-bit Gray 256c

# FW 5.17+ fix (if linkss won't start):
mntroot rw && ln -s /lib/ld-linux-armhf.so.3 /lib/ld-linux.so.3 && mntroot ro

# === DO NOT ===
# Do NOT write directly to /usr/share/blanket/screensaver/ (it's tmpfs, volatile)
# Do NOT skip the framework restart (framework caches the image list)
# Do NOT use non-PNG formats (jpg, gif, bmp — all discarded)
# Do NOT use wrong dimensions (causes "framework going crazy")
```

---

## 13. Troubleshooting: linkss on PW4 FW 5.16.7

> **Context:** linkss v0.25.N installed on PW4 (10th Gen) running FW 5.16.7.
> The hack installed (we fixed the `/lib/ld-linux.so.3` symlink first). KUAL
> shows the Screen Savers menu. But custom images in
> `/mnt/us/linkss/screensavers/` are NOT showing — the Kindle still displays
> default Amazon screensavers. "Restart framework now" causes a freeze.
>
> **Sources:** MobileRead t=195474 (pages 200, 203), GitHub koreader#13449,
> jcs.org Kindle Scribe guide, NiLuJe forum posts, Discord Kindle Modding
> community, bfabiszewski/kindle-screensavers repo.

---

### 13.1 Known Issues with linkss 0.25.N on PW4 FW 5.16.x

**Critical finding:** linkss 0.25.N was last updated in **June 2020** (commit
`ac26552` on the bfabiszewski fork). It was designed for FW 5.x *before*
Amazon added native custom-screensaver support (~FW 5.12+). NiLuJe (the
original author) confirmed on MobileRead t=195474 post #2989 (Dec 2023):

> "No, it isn't supported on FW version with native custom screensaver support
> (and that was, like 5.12 or even earlier?); so, yes, it will fail to install.
> That's perfectly harmless."

**What this means for PW4 + 5.16.7:**

- linkss 0.25.N is **officially unsupported** on FW 5.16.x. The installer
  does not refuse to install (it lacks a FW version check), so it "succeeds"
  but the bind-mount mechanism it relies on conflicts with the native
  screensaver system introduced in later firmware.
- Users on MobileRead report that on FW 5.16.2.1.1 and 5.17.x, linkss
  installs but either: (a) shows default screensavers anyway, (b) shows
  the custom image once or twice then reverts, or (c) the "random"/"shuffle"
  cycling modes don't work. (t=195474 posts #2993, #3036)
- The `Update_linkss_0.25.N_install_touch_pw.bin` package targets older
  devices (Touch/PW1). The `Update_linkss_0.25.N_install_pw2_and_up.bin`
  targets PW2+ but was built before FW 5.16 existed.
- Some users have worked around the FW check by rebuilding the package
  with KindleTool (`kindletool create ota2 -d kindle5`), but this only
  fixes the install — the underlying bind-mount mechanism still has issues
  on newer firmware. (t=195474 post #3037)

---

### 13.2 Why "Restart Framework Now" Causes a Freeze

**This is a known, widely-reported issue** on FW 5.16+ and 5.17+.

From MobileRead t=195474 post #3037 (qqqqqqqqqqqz, June 2025):

> "When I hit 'restart framework now' in KUAL, after the restart, I can't
> unlock my Kindle. The frontlight is stuck on, there's no pin entry dialog,
> and pressing the power button does nothing. However, after forcing a reboot
> by holding down the power button for a while, I can use it just fine."

**Root cause analysis:**

1. The KUAL "Restart framework now" option calls `stop framework` then
   `start framework` via the Kindle's init system. On FW 5.16+, the
   framework startup sequence has changed — it now does more initialization
   (including the native screensaver/cover system) and the restart command
   can leave the device in a half-initialized state.
2. When linkss's bind-mount is active, the framework startup may fail
   or hang because it expects to write to `/usr/share/blanket/screensaver/`
   (the tmpfs) but instead finds the bind-mounted user directory, which may
   not match expected file names or permissions. This can cause the framework
   to hang during the "load screen" phase.
3. The `autoreboot` flag (which linkss uses to auto-reboot on crash) was
   removed in our case — so when the framework hangs, there's no recovery
   mechanism except a hard power-button hold.

**The workaround that works:** Don't use KUAL's "Restart framework now."
Instead, use the Kindle's own menu: **Menu → Settings → Menu (again) →
Restart**. This performs a proper framework restart through the OS's
own restart path, which handles the native screensaver system correctly.
(qqqqqqqqqqqz confirmed this works.)

An alternative that avoids restart entirely: use `lipc-set-prop`
to trigger a framework restart from SSH or KUAL's terminal, or simply do
a **full device reboot** (power button → Restart) which re-runs the upstart
jobs including linkss's mount job.

---

### 13.3 How to Verify if the Bind-Mount Actually Took Effect

The `/mnt/us/linkss/mounted_ss` file (0 bytes) is a **sentinel** that linkss
creates when it *believes* the mount succeeded — but its existence does NOT
guarantee the mount is actually active. The mount can fail silently if the
upstart job ran before the framework or if the mount point was already in use.

**Verification commands (run via SSH, KOReader terminal, or KUAL →
Helper → Show SSH info):**

```bash
# 1. Check if the bind-mount is actually in the kernel mount table
# The mount MUST appear here for it to be active:
cat /proc/mounts | grep blanket
# Expected if working:
# /mnt/us/linkss/screensavers /usr/share/blanket/screensaver none rw,bind 0 0

# If you see the tmpfs line instead, the bind-mount FAILED:
# tmpfs /usr/share/blanket/screensaver tmpfs rw,relatime,size=4096k 0 0

# 2. Check what the framework actually sees:
ls -la /usr/share/blanket/screensaver/
# If bind-mount works: you'll see YOUR bg_ss00.png (and the inode will
# match the file in /mnt/us/linkss/screensavers/)
# If bind-mount failed: you'll see Amazon's stock bg_ss*.png files

# 3. Compare inodes to prove it's the same file (not a copy):
stat -c '%i' /mnt/us/linkss/screensavers/bg_ss00.png
stat -c '%i' /usr/share/blanket/screensaver/bg_ss00.png
# If the bind-mount is active, both inode numbers will be IDENTICAL.

# 4. Check the mount syscall directly:
mount | grep -i blanket
# or:
mount | grep -i screensaver
```

**If the bind-mount is NOT active** (most likely scenario on 5.16.7):
- The upstart job may not have run (check `/etc/upstart/linkss.conf` exists)
- The mount may have been overridden by the framework's own boot sequence
- The framework's native screensaver system may have re-mounted tmpfs
  *after* linkss's bind-mount, effectively hiding it

---

### 13.4 linkss Log File

linkss does **not** write a dedicated log file by default. However:

- **KUAL log:** When you run linkss actions from KUAL, output is captured
  in the KUAL log. Check via KUAL → Helper → Show KUAL log, or look for
  `KPPMainAPPV2*` files in `/mnt/us/` (user arooni on t=195474 post #2988
  reported finding these after a failed install).
- **Upstart log:** If the linkss upstart job runs at boot, its output goes
  to the system log. Check via SSH:
  ```bash
  # Kindle system log (may require root):
  cat /var/log/messages | grep -i linkss
  # or check the upstart job directly:
  cat /etc/upstart/linkss.conf
  # Run it manually to see output:
  sh /etc/upstart/linkss.conf
  ```
- **`/mnt/us/linkss/` contents:** The presence of `mounted_ss` (sentinel)
  and the `screensavers/` subdirectory confirm installation, but not
  operation. There is no `linkss.log` or similar.

---

### 13.5 Staging Directory vs. Screensavers Directory

**Yes, there is a staging directory** — and this matters.

linkss has a KUAL menu option called **"Process staging images"**. The
workflow is:

1. Place new images in `/mnt/us/linkss/staging/` (note: **staging**, not
   `screensavers/`)
2. Run KUAL → Screen Savers → "Process staging images"
3. linkss renames, validates, and moves them to `/mnt/us/linkss/screensavers/`
   with the correct `bg_ssNN.png` naming convention
4. The screensavers directory is what gets bind-mounted over
   `/usr/share/blanket/screensaver/`

From MobileRead t=195474 page 144 (NiLuJe):
> "The latest snapshots now have a 'Process staging images' menu entry...
  linkss/staging directory). Should accept whatever [image format]..."

**Our problem:** We placed `bg_ss00.png` directly in `screensavers/` (correct
naming) but the "Process staging images" command says "no new images to
process" — this is **expected** if there's nothing in the `staging/` dir.
The file in `screensavers/` should still work IF the bind-mount is active.

**Action:** Verify that:
- `/mnt/us/linkss/screensavers/bg_ss00.png` exists and is readable
- The file is a valid 8-bit grayscale PNG at exactly 1072×1448
- The bind-mount is actually active (see 13.3)

If the bind-mount is not active, the file sitting in `screensavers/` does
nothing — the framework sees the tmpfs stock images instead.

---

### 13.6 FW 5.16.7 — Different Screensaver Mechanism Than Earlier FW

**Yes, significantly different.** Starting around FW 5.12, Amazon introduced
**native custom screensaver / "Display Cover" support** — the ability to show
the cover of the book you're reading as the sleep screen. This changed how
the screensaver system works:

1. **The framework now actively manages `/usr/share/blanket/screensaver/`**
   at boot — it regenerates stock images into the tmpfs and may re-mount it,
   potentially overriding linkss's bind-mount.
2. **The "Screen Saver Behavior" / "Display Cover" setting** (in
   Settings → Device Options → Display Cover, or on some FW: Settings →
   Screen Saver) controls whether the framework uses: book covers, stock
   images, or last-page content. When set to "Cover" mode, the framework
   actively populates the screensaver directory — conflicting with linkss.
3. **NiLuJe explicitly stated** linkss is not supported on FW with native
   screensaver support (t=195474 #2989). The bind-mount approach was
   designed for a time when the framework did NOT actively manage the
   screensaver directory.

**On FW 5.16.7 specifically:**
- The "Display Cover" / "Show covers on lock screen" toggle exists in
  Settings → Device Options or Settings → Screen and brightness
- If this is enabled, the framework will override any bind-mounted content
- Even if disabled, the framework's boot sequence may re-mount the tmpfs
  after linkss's upstart job runs, breaking the bind-mount

---

### 13.7 Screen Saver Behavior Setting — Does It Matter?

**Yes, critically.** The Kindle's native screensaver behavior setting
directly conflicts with linkss:

| Setting | Effect on linkss |
|---------|-----------------|
| **"Cover" / "Display Cover: ON"** | Framework actively writes book covers to the screensaver dir at sleep time — **overrides bind-mount content**. linkss images will NOT show. |
| **"Last Screen" / "Last page read"** | Framework shows the last page of your book — bypasses the screensaver dir entirely. linkss images will NOT show. |
| **"Image Cycle" / stock images / OFF** | Framework uses the tmpfs screensaver dir — this is the ONLY mode where linkss's bind-mount can work. |

**Required action:** Ensure the Kindle's screensaver behavior is set to
use stock/cycle images, NOT cover or last-page mode:

1. Go to **Settings → Device Options → Display Cover** (or "Screen Saver"
   on some FW versions)
2. Set it to **OFF** / "Image Cycle" / stock images
3. On the Kindle Scribe guide (jcs.org), the author explicitly notes:
   > "Make sure the 'Show covers on lock screen' option is disabled."
4. If the device has **Special Offers (ads)**, the ads will override
   everything — you must deregister or remove ads first. (Discord Kindle
   Modding community: "You do need to remove the ads before linkss can work.")

---

### 13.8 Alternative Approaches (No Framework Restart Required)

**Option A: KOReader's built-in Sleep Screen (RECOMMENDED for dashboards)**

KOReader has its own screensaver system that works independently of the
Kindle framework. It draws directly to the framebuffer using FBInk.

1. Install KOReader (already installed in our case)
2. In KOReader: Settings (gear) → Screen → Sleep screen
3. Set "Sleep screen" to: **Image file** or **Random image from folder**
4. Set the folder to `/mnt/us/linkss/screensavers/` or any custom path
5. Set "Sleep screen message" to OFF (removes the "Sleeping..." text)
6. KOReader draws the image to the e-ink panel directly — **no framework
   restart needed, no bind-mount, no conflict with native FW**

**Caveat:** KOReader's sleep screen only activates when KOReader is the
active app. If you're on the Kindle home screen, the native framework
screensaver takes over. For a dedicated dashboard, you'd keep KOReader
running in the foreground.

**Option B: Direct FBInk image display (no screensaver hack at all)**

Use `fbink` directly to push an image to the e-ink panel. This is what
dashboard projects (Home Assistant, weather displays) typically use:

```bash
# Via SSH or KUAL terminal:
/mnt/us/koreader/fbink -i /mnt/us/your_image.png -g
# or if fbink is installed standalone:
fbink -i /path/to/image.png
```

This bypasses the entire screensaver system — you just draw an image to
the framebuffer. The image stays until you draw another one or the device
sleeps and the framework overwrites it.

**For a dashboard that updates periodically:**
- Disable sleep entirely: `lipc-set-prop -i com.lab126.powerd powerd 0`
- Run a cron/script that calls `fbink -i new_image.png` on a schedule
- No linkss, no bind-mount, no framework restart needed

**Option C: Manual direct copy (jcs.org approach)**

From the Kindle Scribe guide (jcs.org), which works on newer FW without
linkss:

```bash
# Via SSH or KOReader terminal:
mount -o remount,rw /
rm /usr/share/blanket/screensaver/*.png
cp /mnt/us/bg_ss*.png /usr/share/blanket/screensaver/
mount -o remount,ro /
# Then restart the device (not framework) via Settings → Restart
```

This directly replaces stock images in the tmpfs. **Note:** They're in
tmpfs, so this only lasts until the next reboot — the framework regenerates
stock images. For a persistent dashboard, you'd need to re-run this after
every boot, or combine with the FBInk approach.

---

### 13.9 Checking if the Upstart Job Is Actually Installed and Running

linkss installs an upstart job that runs the bind-mount at boot. To verify:

```bash
# Check if the upstart job file exists:
ls -la /etc/upstart/linkss*
# Expected: /etc/upstart/linkss.conf (and possibly linkss-post.conf)

# Check the job content:
cat /etc/upstart/linkss.conf

# Check if it ran at last boot:
# (Kindle system log - may need root)
grep -i linkss /var/log/messages 2>/dev/null || \
  grep -i linkss /var/log/syslog 2>/dev/null || \
  echo "No system log found"

# Manually run the upstart job to see errors:
sh /etc/upstart/linkss.conf 2>&1

# Check if the linkss binaries exist:
ls -la /mnt/us/linkss/bin/
# Should contain: fbink, convert, identify, mogrify, sort, etc.

# Check the sentinel file (means the job THINKS it mounted):
ls -la /mnt/us/linkss/mounted_ss
# But remember: sentinel existence ≠ mount active (see 13.3)
```

**If the upstart job file doesn't exist**, linkss wasn't fully installed —
the package may have failed to write to `/etc/upstart/` (rootfs was
read-only, or the FW blocked it). Reinstall with the correct binary package
(`Update_linkss_0.25.N_install_pw2_and_up.bin`, NOT the `touch_pw` variant).

---

### 13.10 Known Fix / Workaround for the Framework Restart Freeze

**The freeze itself:**

There is **no fix** for the KUAL "Restart framework now" freeze on FW 5.16+
because linkss 0.25.N is not maintained for this firmware. The workaround is
to **never use that menu option** and instead:

1. **Use the Kindle's own restart:** Menu → Settings → Menu → Restart
2. **Do a full reboot:** Hold power button 15+ seconds → release → press
   once to restart. This re-runs all upstart jobs cleanly.
3. **Use `lipc-set-prop` from SSH/KUAL terminal:**
   ```bash
   lipc-set-prop -i com.lab126.cmd restartFramework 1
   ```
   (This uses the same path as the menu restart and is more reliable than
   KUAL's stop/start approach.)

**The overall "screensaver not showing" problem:**

Given that linkss 0.25.N is unsupported on FW 5.16.7, the **recommended path
forward** for our dashboard project is:

1. **Uninstall linkss** (KUAL → Screen Savers → Uninstall, or delete
   `/mnt/us/linkss/` and remove the upstart job)
2. **Use KOReader's built-in Sleep Screen** feature (Option A in 13.8) if
   you need the sleep-screen to show a custom image
3. **Use direct FBInk calls** (Option B in 13.8) for a dashboard that
   pushes images on a schedule — this is what most Kindle dashboard
   projects (HASS Lovelace, weather displays) actually use, and it
   completely bypasses the broken linkss bind-mount mechanism

**If you insist on making linkss work**, try this sequence:
1. Confirm the bind-mount is active via `/proc/mounts` (13.3)
2. Ensure "Display Cover" / "Show covers on lock screen" is OFF (13.7)
3. Remove Special Offers (ads) if present — these override everything
4. Don't use KUAL "Restart framework now" — use full reboot instead
5. Use the `pw2_and_up` binary, NOT the `touch_pw` binary
6. After reboot, verify via SSH that `/proc/mounts` shows the bind line
7. If the bind-mount fails at boot but works manually, the framework is
   re-mounting tmpfs after linkss's upstart job — you may need to add a
   delay or move the linkss upstart job to run later in the boot sequence

---

### 13.11 Summary Decision Matrix

| Approach | Works on 5.16.7? | Framework restart? | Persistent? | Complexity |
|----------|:---:|:---:|:---:|:---:|
| linkss 0.25.N bind-mount | ❌ Unsupported | ❌ Freezes | ❌ Broken | High |
| KOReader Sleep Screen | ✅ | ❌ Not needed | ✅ (while KOReader open) | Low |
| Direct FBInk image push | ✅ | ❌ Not needed | ✅ (until sleep) | Low |
| Manual tmpfs copy + reboot | ⚠️ Until next reboot | ✅ Full reboot | ❌ Volatile | Medium |

**Recommendation for the the agent Dashboard project:** Use **direct FBInk
image pushes** — disable sleep, run a script that calls `fbink -i` on a
schedule. This is the most reliable approach on unsupported firmware and
is what production Kindle dashboard projects use.

