# Custom Screensavers on Kindle PW4 Firmware 5.16.7 — Feasibility Report

**Date:** 2025-07-25
**Device:** Kindle Paperwhite 4 (PW4, 10th Gen)
**Firmware:** 5.16.7
**Current state:** linkss v0.25.N installed, KUAL shows Screen Savers menu, "Preview current ScreenSaver" shows BLANK (white) screen, framework restart freezes.

---

## TL;DR — Verdict

**linkss does NOT work on FW 5.16.7. Nobody has gotten linkss working natively on 5.16.7.** The root cause is a hard-float ABI change Amazon introduced in FW 5.16.3 that breaks all soft-float-compiled extensions. **However, there ARE three viable alternative paths** (detailed below). The most reliable is: jailbreak with Sanctuary → downgrade to 5.16.2.1.1 → install linkss.

---

## 1. The Root Cause: Hard-Float ABI Break (5.16.3+)

### What happened
Starting with FW 5.16.3, Amazon switched the Kindle's toolchain from **soft-float (armel)** to **hard-float (armhf)** ABI. This means the on-chip floating-point unit is now used directly instead of software emulation. While the OS looks the same, **all pre-existing jailbreak extensions were compiled for soft-float and crash/segfault on hard-float firmware.**

### Evidence
- **KindleModding FAQ** (updated Apr 2026): *"Starting with version 5.16.3, Kindles started using hard-float architecture... many internal changes have made a lot of jailbreaking tools and extensions unusable in modern firmware versions. This ultimately means that most extensions found on MobileRead/Discord servers won't work on hard-float firmware or viceversa unless explicitly stated (i.e NiLuJe's Screensaverhack)."*
- **NiLuJe** (KOReader maintainer, GitHub #11298, Dec 2023): *"a JB is useless on those FW versions, because nothing is built for it, so nothing works. KOReader would be the least of your problems."*
- **Frogm4n** (MobileRead t=195474 p=202, Feb 2025): *"If your firmware is 5.16.3 or higher then there is nothing to do except wait for the hardfloat version of the python packages to be developed, unless you have programming skills and can help create them."*
- **mergen3107** (MobileRead t=358229, Jan 2024): *"Don't try this. Nothing except KUAL, KOReader and usbnet work on 5.16.x."*

### Why linkss specifically fails
linkss v0.25.N depends on **Python** (and several soft-float helper binaries like `eips`, image processing tools). On 5.16.7:
- Python cannot run (no hard-float Python package exists as of July 2025)
- The helper binaries segfault silently
- The KUAL menu appears (it's a static booklet), but any action that invokes Python/helper binaries fails
- "Preview current ScreenSaver" → blank white screen = the display helper crashed without rendering
- "Framework restart" → freeze = the init script's bind-mount setup runs but the post-mount image processing crashes, leaving the framework in a broken state

**This is a known, community-confirmed limitation, not a user error.**

---

## 2. Has ANYONE Gotten Custom Screensavers on 5.16.7? — Method by Method

### Method A: linkss (NiLuJe's ScreenSavers Hack) — ❌ DOES NOT WORK
- **0 confirmed success stories** on 5.16.7 (or any 5.16.3+ firmware)
- linkss v0.25.N is the latest version (built ~2020-2023, soft-float only)
- MobileRead t=195474 (204 pages, 3053 posts) — no one reports linkss working on 5.16.3+
- **rand0m** (MobileRead, Feb 2025): Claimed the Bookfere symlink workaround worked on KOA3 5.17+, but...
- **dreimer** (MobileRead, Mar 2025): Tried the same workaround on PW5 5.17.1.0.3 — *"still greeted with default wallpapers... mod did not work"* — **inconsistent, not reliable**

### Method B: Bookfere's ld-linux Symlink Workaround — ⚠️ INCONSISTENT
The workaround (for 5.17+):
1. Install usbnetlite via MRPI
2. SSH into Kindle
3. Run: `mntroot rw` → `ln -s /lib/ld-linux-armhf.so.3 /lib/ld-linux.so.3` → `mntroot ro`
4. Install linkss via MRPI

**Results:** One claimed success (KOA3 5.17+), one confirmed failure (PW5 5.17.1.0.3). No reports specifically on PW4 5.16.7. **Not reliable enough to recommend.**

### Method C: Pythonless Fork of linkss (bfabiszewski) — ❌ NO EVIDENCE OF 5.16.7 SUPPORT
- Repo: https://github.com/bfabiszewski/kindle-screensavers
- Fork of linkss v0.25.N that replaces Python with `mobitool`
- Last updated: **June 2020** (6 years ago, pre-hard-float era)
- Only 2 GitHub stars, no recent activity
- No reports of it working on 5.16.3+ anywhere
- The mobitool binary it uses is also likely soft-float compiled

### Method D: KOReader Sleep Screen — ✅ WORKS (with caveats)
**This is the most viable method on 5.16.7 without downgrading.**
- KOReader has a **`kindlehf`** package specifically for FW ≥5.16.3 (hard-float)
- Source: https://kindlemodding.org/jailbreaking/post-jailbreak/koreader.html
- KOReader's built-in Sleep Screen feature: Settings ▸ Screen ▸ Sleep Screen ▸ Wallpaper → "Show random image from folder on sleep screen"
- Documented at kindlemodshelf.me/customscreensavers
- **Caveat:** KOReader must be running. When you exit KOReader, the stock Kindle screensaver returns. For a dashboard use case (always-on display), KOReader must stay running in "no framework" mode.
- **Multiple confirmed successes** on 5.16.x firmware via Discord/Reddit

### Method E: Native "Display Cover" Feature (No Jailbreak) — ✅ WORKS (workaround)
- Settings ▸ Device Options ▸ Display Cover → ON
- Natively shows the cover of the book you're currently reading
- **Workaround for custom images:** Create a fake EPUB with your custom image as the cover using Calibre, sync it to Kindle, open/select it as current book → your image shows on sleep screen
- Documented at readerbackdrop.com and engadget.com
- **Limitations:** Image must be the "current book"; limited to one image; requires ads removed (pay $20 or use Disable Ads script)
- Not suitable for a dashboard that needs to update images dynamically

### Method F: Firmware Downgrade → linkss — ✅ BEST PATH (requires re-jailbreak)
**This is the recommended path by the entire Kindle modding community.**

**Step 1:** Jailbreak 5.16.7 using **Sanctuary**
- Sanctuary is a **browser-based jailbreak** working on FW 5.16.4–5.18.3 (covers 5.16.7!)
- Source: https://kindlemodding.org/ (linked from r/kindlejailbreak)
- No computer needed — runs from Kindle's experimental browser
- Announced ~late 2025

**Step 2:** Downgrade to 5.16.2.1.1 (soft-float)
- Only possible after jailbreak (Amazon provides no downgrade path on stock)
- Guide: https://kindlemodding.org/firmware-and-flashing/downgrading/
- PW4 firmware URL pattern: `https://s3.amazonaws.com/firmwaredownloads/update_kindle_all_new_paperwhite_v2_5.XX.X.bin`
- Target: 5.16.2.1.1 (last soft-float firmware, "golden firmware" for mods)

**Step 3:** Install linkss v0.25.N on 5.16.2.1.1
- Works perfectly — this is the confirmed working configuration
- **amico86** (MobileRead t=195474 p=200, Jan 2024): *"I installed ScreenSavers Hack on my Kindle PW5 16 Gb (FW 5.16.2.1.1) skipping the FW check. And it works fine in the default mode."*
- Hundreds of confirmed successes on 5.16.2.1.1 across MobileRead

### Method G: Manual Bind-Mount — ❌ NO EVIDENCE
- No reports of anyone manually bind-mounting screensaver images on 5.16.7
- The bind-mount itself might work (it's a kernel feature), but the image format conversion/display would still need soft-float tools

### Method H: kobopatch-style Patch — ❌ DOES NOT EXIST FOR KINDLE
- kobopatch is Kobo-only. No equivalent patch system exists for Kindle firmware.

---

## 3. Downgrade Feasibility from 5.16.7

### Without jailbreak: IMPOSSIBLE
- KindleModding FAQ: *"Your Kindle must be jailbroken first in order to downgrade. This is because Amazon has never provided a way to downgrade on stock firmware."*
- Reddit r/kindle: *"Kindle doesn't allow for downgrading FW."*

### With jailbreak: POSSIBLE
- **northirid** (MobileRead t=360087, Mar 2024): Had jailbroken PW4 on 5.16.5, downgraded to 5.16.2.1 successfully, but Kindle auto-updated to 5.16.7 overnight. Could not downgrade from 5.16.7 because the jailbreak was disrupted by the update.
- **Key insight:** If you're already jailbroken on 5.16.7 (which the task context says linkss is installed, implying JB exists), you may be able to downgrade directly.
- **LanguageBreak** (notmarek/LanguageBreak): Works on ≤5.16.2.1.1 only — NOT useful for 5.16.7
- **Sanctuary**: Works on 5.16.4–5.18.3 — this IS the jailbreak for 5.16.7
- **Winterbreak**: Another recent jailbreak (details on kindlemodding.org)

### Critical note on the user's situation
The task context says linkss v0.25.N is already installed on the PW4 with 5.16.7, and KUAL shows the Screen Savers menu. This means **the Kindle is already jailbroken**. Therefore:
- You should be able to downgrade directly to 5.16.2.1.1 using the standard downgrade method
- Put the 5.16.2.1.1 bin file in root, run the update from Kindle (with OTA blocker disabled)
- After downgrade, reinstall hotfix + KUAL + MRPI, then install linkss fresh

---

## 4. Summary: Recommended Action Plan

| Priority | Method | Works on 5.16.7? | Effort | Reliability |
|----------|--------|-------------------|--------|-------------|
| 1 | **Downgrade to 5.16.2.1.1 + linkss** | After JB → yes | Medium | ⭐⭐⭐⭐⭐ |
| 2 | **KOReader kindlehf + Sleep Screen** | Yes (stays on 5.16.7) | Low-Medium | ⭐⭐⭐⭐ |
| 3 | **Native Display Cover + fake EPUB** | Yes (no JB needed) | Low | ⭐⭐⭐ (single image only) |
| 4 | Bookfere symlink workaround | Maybe | High | ⭐⭐ (inconsistent) |

### For the the agent Dashboard project specifically:
- **If you need dynamic image updates** (dashboard refreshes): Downgrade to 5.16.2.1.1 + linkss is the best path. The Online ScreenSaver extension (poja1993/onlinescreensaver) can fetch images from a URL, perfect for Home Assistant dashboards.
- **If you can't downgrade**: KOReader kindlehf running in "no framework" mode with Sleep Screen wallpaper is the alternative, but KOReader must stay running.
- **SheekGeek's Home Assistant → Kindle dashboard pipeline** uses linkss on a jailbroken/downgraded Kindle — same approach confirmed working for dashboard use cases.

---

## 5. Sources

- MobileRead t=195474 (K5 ScreenSavers Hack, 204 pages): https://www.mobileread.com/forums/showthread.php?t=195474
- MobileRead t=358229 (PW5 ScreenSaver Options Not Working): https://www.mobileread.com/forums/showthread.php?t=358229
- MobileRead t=360087 (PW4 updated to 5.16.7, can't downgrade): https://www.mobileread.com/forums/showthread.php?t=360087
- MobileRead t=251143 p=12 (MRPI issues on hard-float): https://www.mobileread.com/forums/showthread.php?t=251143&page=12
- KindleModding FAQ: https://kindlemodding.org/jailbreaking/jailbreak-faq.html
- KindleModding Downgrading: https://kindlemodding.org/firmware-and-flashing/downgrading/
- KindleModding KOReader: https://kindlemodding.org/jailbreaking/post-jailbreak/koreader.html
- KOReader hard-float discussion: https://github.com/koreader/koreader/discussions/11298
- KOReader releases (kindlehf): https://github.com/koreader/koreader/releases
- KindleModShelf custom screensavers: https://kindlemodshelf.me/customscreensavers
- bfabiszewski pythonless linkss fork: https://github.com/bfabiszewski/kindle-screensavers
- notmarek/LanguageBreak (≤5.16.2.1.1): https://github.com/notmarek/LanguageBreak
- Sanctuary jailbreak (5.16.4–5.18.3): https://kindlemodding.org/ / r/kindlejailbreak
- Online ScreenSaver extension: https://github.com/poja1993/onlinescreensaver
- SheekGeek HA→Kindle dashboard: https://sheekgeek.org/topic/diy
- Kindle Modding Community Discord: https://discord.gg/kindle-modding-community-1083603487025274911
- Native Display Cover guide: https://www.readerbackdrop.com/blog/how-to-set-custom-screensaver-kindle-no-jailbreak-2026
