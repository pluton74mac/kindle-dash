# Screensaver Replacement on FW 5.16.x — Troubleshooting Guide

> Research compiled 2026-07-25. Sources: MobileRead t=195474 (pages 200,
> 203), GitHub koreader#13449, jcs.org Kindle Scribe guide, NiLuJe forum
> posts, Discord Kindle Modding community, bfabiszewski/kindle-screensavers
> repo.

## linkss 0.25.N on PW4 FW 5.16.7 — The Core Problem

linkss 0.25.N was last updated **June 2020** (commit `ac26552` on the
bfabiszewski fork). It was designed for FW 5.x *before* Amazon added
native custom-screensaver support (~FW 5.12+).

NiLuJe (the original author) confirmed on MobileRead t=195474 post #2989
(Dec 2023):

> "No, it isn't supported on FW version with native custom screensaver
> support (and that was, like 5.12 or even earlier?); so, yes, it will
> fail to install. That's perfectly harmless."

The installer doesn't refuse to install (no FW version check), so it
"succeeds" but the bind-mount mechanism conflicts with the native
screensaver system.

**Symptoms on FW 5.16.7:**
- Default Amazon screensavers still showing after linkss install
- Custom image appearing once or twice, then reverting to stock
- "Random"/"shuffle" cycling modes not working (only `bg_ss00` shows)
- KUAL "Restart framework now" causes a freeze/hang

## Framework Restart Freeze — Known Issue

From MobileRead t=195474 post #3037 (qqqqqqqqqqqz, June 2025):

> "When I hit 'restart framework now' in KUAL, after the restart, I can't
> unlock my Kindle. The frontlight is stuck on, there's no pin entry
> dialog, and pressing the power button does nothing. However, after
> forcing a reboot by holding down the power button for a while, I can
> use it just fine. Using Menu → Settings → Menu → Restart works."

**Root causes:**
1. KUAL's restart does `stop framework` then `start framework`. On FW
   5.16+, the framework startup does more initialization (including the
   native screensaver/cover system) and the restart can leave the device
   half-initialized.
2. When linkss's bind-mount is active, the framework may hang during
   startup because it expects to write to the tmpfs but finds the
   bind-mounted user directory instead.
3. The `autoreboot` flag provides no recovery mechanism when the
   framework hangs — user must hard-reboot (hold power 15s).

**Workarounds:**
- **Don't use KUAL's "Restart framework now"** on FW 5.16+
- Use Kindle's own menu: Menu → Settings → Menu → Restart
- Or do a full device reboot (hold power 15s → release → press to boot)
- Or via SSH: `lipc-set-prop -i com.lab126.cmd restartFramework 1`

## Verifying the Bind-Mount

The `/mnt/us/linkss/mounted_ss` sentinel file only means linkss *thinks*
it mounted — it does NOT guarantee the mount is actually active.

```bash
# 1. Check the kernel mount table
cat /proc/mounts | grep blanket
# Working: /mnt/us/linkss/screensavers /usr/share/blanket/screensaver none rw,bind 0 0
# Failed:  tmpfs /usr/share/blanket/screensaver tmpfs rw,relatime,size=4096k 0 0

# 2. Check what the framework sees
ls -la /usr/share/blanket/screensaver/
# Working: your bg_ss00.png  |  Failed: Amazon's stock bg_ss*.png

# 3. Compare inodes (proves it's the same file, not a copy)
stat -c '%i' /mnt/us/linkss/screensavers/bg_ss00.png
stat -c '%i' /usr/share/blanket/screensaver/bg_ss00.png
# If bind-mount active, both inode numbers are IDENTICAL.
```

## Staging vs. Screensavers Directory

linkss has a `/mnt/us/linkss/staging/` directory. The KUAL menu option
"Process staging images" only processes files in `staging/`, not
`screensavers/`.

Workflow:
1. Place new images in `/mnt/us/linkss/staging/`
2. Run KUAL → Screen Savers → "Process staging images"
3. linkss renames, validates, moves to `/mnt/us/linkss/screensavers/`
4. `screensavers/` is what gets bind-mounted

If your image is already correctly named (`bg_ss00.png`) in
`screensavers/`, the staging processor says "no new images to process" —
this is **expected**. The file should work IF the bind-mount is active.

## FW 5.16.7 Native Screensaver Mechanism

Starting ~FW 5.12, Amazon introduced native "Display Cover" support.
This changed how the screensaver system works:

1. The framework **actively manages** `/usr/share/blanket/screensaver/`
   at boot — regenerates stock images into the tmpfs, may re-mount it.
2. The "Display Cover" setting controls whether the framework uses book
   covers, stock images, or last-page content.
3. When set to "Cover" mode, the framework actively populates the
   screensaver directory — **conflicting with linkss's bind-mount**.

### Screen Saver Behavior Setting — Critical for linkss

| Setting | Effect on linkss |
|---------|-----------------|
| "Cover" / "Display Cover: ON" | Framework overrides bind-mount — linkss images will NOT show |
| "Last Screen" / "Last page read" | Framework bypasses screensaver dir entirely — linkss won't work |
| "Image Cycle" / stock images / OFF | Only mode where linkss's bind-mount can work |

**Required:** Settings → Device Options → Display Cover → OFF

If the device has Special Offers (ads), they override everything —
remove ads first.

## linkss Log File

linkss does **not** write a dedicated log file. Check:
- KUAL log: KUAL → Helper → Show KUAL log, or `KPPMainAPPV2*` files in
  `/mnt/us/`
- Upstart log: `grep -i linkss /var/log/messages` (via SSH)
- Manually run the upstart job: `sh /etc/upstart/linkss.conf 2>&1`

## Checking the Upstart Job

```bash
ls -la /etc/upstart/linkss*          # job file exists?
cat /etc/upstart/linkss.conf         # check content
ls -la /mnt/us/linkss/bin/           # binaries exist?
ls -la /mnt/us/linkss/mounted_ss     # sentinel (≠ active mount)
```

If the upstart job file doesn't exist, linkss wasn't fully installed.

## Alternative Approaches (No Framework Restart)

### Option A: KOReader Sleep Screen
KOReader has its own screensaver system independent of the Kindle
framework. It draws directly to the framebuffer using FBInk.

1. Settings (gear) → Screen → Sleep screen
2. Set to: Image file or Random image from folder
3. Set folder to `/mnt/us/linkss/screensavers/` or custom path
4. Set "Sleep screen message" to OFF
5. No framework restart, no bind-mount, no conflict

Caveat: only active when KOReader is the foreground app.

### Option B: Direct FBInk (RECOMMENDED for dashboards)
Bypass the entire screensaver system — draw directly to framebuffer:

```bash
/mnt/us/koreader/fbink -i /mnt/us/your_image.png -g
```

For periodic updates:
- Disable sleep: `lipc-set-prop -i com.lab126.powerd powerd 0`
- Cron/script calling `fbink -i new_image.png` on schedule
- No linkss, no bind-mount, no framework restart

### Option C: Manual tmpfs copy (jcs.org approach)
Direct replacement, but volatile (lost on reboot):

```bash
mount -o remount,rw /
rm /usr/share/blanket/screensaver/*.png
cp /mnt/us/bg_ss*.png /usr/share/blanket/screensaver/
mount -o remount,ro /
# Then full device reboot (not framework restart)
```

## Decision Matrix

| Approach | Works on 5.16.7? | Framework restart? | Persistent? | Complexity |
|----------|:---:|:---:|:---:|:---:|
| linkss 0.25.N bind-mount | ❌ Unsupported | ❌ Freezes | ❌ Broken | High |
| KOReader Sleep Screen | ✅ | ❌ Not needed | ✅ (while KOReader open) | Low |
| Direct FBInk image push | ✅ | ❌ Not needed | ✅ (until sleep) | Low |
| Manual tmpfs copy + reboot | ⚠️ Until next reboot | ✅ Full reboot | ❌ Volatile | Medium |

**Recommendation:** Use direct FBInk image pushes for dashboards on FW
5.16+. Disable sleep, run a script that calls `fbink -i` on a schedule.
This is what production Kindle dashboard projects use.

## If You Insist on Making linkss Work

1. Confirm bind-mount is active via `/proc/mounts` (see above)
2. Ensure "Display Cover" / "Show covers on lock screen" is OFF
3. Remove Special Offers (ads) if present
4. Don't use KUAL "Restart framework now" — use full reboot
5. Use `pw2_and_up` binary, NOT the `touch_pw` binary
6. After reboot, verify via SSH that `/proc/mounts` shows the bind line
7. If bind-mount fails at boot but works manually, the framework is
   re-mounting tmpfs after linkss's upstart job — may need to delay or
   move the linkss upstart job later in the boot sequence
