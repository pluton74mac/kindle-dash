# Kindle PW4 Firmware Downgrade: 5.16.7 → 5.16.2.1.1

Research for the Kindle the agent Dashboard project. Device: Kindle Paperwhite 10th Gen (PW4), 2018, currently jailbroken on FW 5.16.7 via the Adbreak method. Goal: downgrade to 5.16.2.1.1 to make `linkss` work (soft-float ABI).

> **Status as of 2026-07-25**: Verified against MobileRead forums, KindleModding.org, GitHub (LanguageBreak/KOReader), and Reddit r/kindlejailbreak. Sources linked inline.

---

## TL;DR — Answers to the 8 Questions

| # | Question | Answer |
|---|----------|--------|
| 1 | Does the jailbreak survive a downgrade on PW4? | **Yes, if the jailbreak is still functional on 5.16.7.** Adbreak-based JB persists across downgrades because it lives in `/mnt/us` (user storage) and the hotfix re-applies on each boot. Downgrading does NOT wipe the JB. |
| 2 | Do KUAL and extensions survive? | **KUAL: yes (files in `/mnt/us/extensions` persist). Extensions: yes, files persist.** BUT hard-float binaries compiled for ≥5.16.3 will crash on 5.16.2.1.1 (soft-float) and vice-versa. You must reinstall soft-float builds of linkss, KOReader, etc. after downgrade. |
| 3 | Exact step-by-step procedure? | See [§ Downgrade Procedure](#downgrade-procedure) below. Uses the "Allow Downgrade" scriplet by Marek + the official PW4 5.16.2.1.1 `.bin` from Amazon S3. |
| 4 | Is 5.16.2.1.1 the best version for linkss? | **Yes.** 5.16.2.1.1 is the last soft-float firmware AND the last LanguageBreak-jailbreakable version. It is the canonical target for linkss/KOReader compatibility. Do NOT go lower unless you need a specific UI feature; 5.16.2.1.1 is the sweet spot. |
| 5 | Role of renameotabin? | renameotabin prevents OTA auto-updates (renames `update.bin.tmp.partial` etc.). It does NOT block manual firmware flashes via reboot. **You should RESTORE OTA binaries before downgrading** (KUAL → Rename OTA Binaries → Restore), then re-Rename after downgrade to prevent re-upgrade. |
| 6 | Risks? | Low-to-moderate. Bricking is rare with the scriplet method. White screen after large jumps is fixable via `DO_FACTORY_RESTORE`. Data loss: books/settings may be wiped — back up first. Losing JB: very unlikely if JB is functional before downgrade. |
| 7 | Will custom extensions (kindle-dash, touch_tap) still work? | **Shell scripts (dash_interactive.sh): yes.** `touch_tap` binary: depends on how it was compiled. If compiled soft-float (arm-linux-gnueabi), yes. If hard-float (arm-linux-gnueabihf, the ≥5.16.3 default), it will crash. Recompile with soft-float toolchain after downgrade. |
| 8 | PW4-specific quirks? | PW4 uses `update_kindle_all_new_paperwhite_v2_*.bin` (NOT the `update_kindle_10th_*.bin` — that's a different file). PW4 has no bootloader hardening issues for 5.16.x downgrades (those affect 5.18.x+ on some models). |

---

## 1. Does the Jailbreak Survive a Firmware Downgrade on PW4?

**Yes.** The jailbreak (whether Adbreak or LanguageBreak) survives firmware downgrades because:

- The JB payload lives in `/mnt/us` (the user-visible USB storage partition), which is **not touched** by firmware updates. Firmware updates only write to the system/rootfs partitions.
- The hotfix mechanism (`update_hotfix_*.bin`) re-applies the JB hooks on each reboot via the `mkk` folder and `RUNME.sh`/`;log` commands.
- Multiple MobileRead users confirm downgrading from 5.16.5 → 5.16.2.1 and even → 5.13.x while keeping the JB intact. ([t=357058, post #3](https://www.mobileread.com/forums/showthread.php?t=357058), [t=360087](https://www.mobileread.com/forums/showthread.php?t=360087))

**Critical caveat**: The JB must be *functional* before you downgrade. If `;log mrpi` and `;log runme` no longer work on 5.16.7 (as happened to user "northirid" in t=360087 after an auto-update to 5.16.7), you cannot initiate the downgrade because you can't run the downgrade scriplet. In that scenario, you're stuck until a new JB method is released for your firmware.

> ⚠️ **Your situation**: Since you have KUAL working and MRPI installed on 5.16.7, your JB is functional. You CAN downgrade.

---

## 2. Do KUAL and Extensions Survive?

### KUAL
**Yes, KUAL survives.** KUAL is installed as:
- A booklet in `/mnt/us/documents/` (the KUAL azw3/ booklet)
- Extensions in `/mnt/us/extensions/`

Both locations are on the user storage partition, which firmware updates don't touch. KUAL will be launchable immediately after downgrade.

### Extensions — File Survival vs. Binary Compatibility

**Files survive** (they're on `/mnt/us`), but **binary compatibility is the problem**:

| Firmware | ABI | Toolchain |
|----------|-----|-----------|
| ≤ 5.16.2.1.1 | **soft-float** (`arm-linux-gnueabi`) | Old Kindle SDK |
| ≥ 5.16.3 | **hard-float** (`arm-linux-gnueabihf`) | New Amazon toolchain |

This is the core issue. Amazon switched their compilation backend from soft-float to hard-float at 5.16.3. Binaries compiled for one ABI **will not run** on the other — they crash immediately with illegal instruction errors.

**Source**: [KOReader Discussion #11298](https://github.com/koreader/koreader/discussions/11298) — NiLuJe (KOReader maintainer) confirms: *"Amazon switched their compiling backend mechanism (from softfloats to hardfloats), meaning that currently compiled code in KOReader and all packages won't work with 99% chance."*

### What this means for your extensions:

| Extension | Will it work after downgrade? | Action needed |
|-----------|------------------------------|---------------|
| **linkss 0.25.N** | Currently broken on 5.16.7 (hard-float). **Will work on 5.16.2.1.1** if you install the soft-float build. | Reinstall from `kindle-linkss-0.25.N-r18981.tar.xz` (soft-float build). File: `Update_linkss_0.25.N_install_touch_pw.bin` |
| **MRPI** | Survives (it's a shell script wrapper). May need reactivation via `;log mrpi`. | Run `;log mrpi` after downgrade to confirm. |
| **KOReader** | Hard-float build won't work. Need soft-float build. | Reinstall KOReader with soft-float Kindle build. |
| **Tailscale** | Depends on binary. Tailscale for Kindle is typically soft-float. | Test after downgrade; reinstall if needed. |
| **kindle-dash** (your custom ext) | Shell scripts (`dash_interactive.sh`) will work fine. `touch_tap` binary depends on compilation. | Recompile `touch_tap` with `arm-linux-gnueabi` (soft-float) if it was built hard-float. |
| **renameotabin** | Shell-based, works on both ABIs. | No action needed (but Restore before downgrade, Rename after). |
| **/lib/ld-linux.so.3 symlink** | Your `fix_linker` symlink may be wiped by the firmware update (it's in `/lib/` on rootfs). | Recreate the symlink after downgrade if linkss still needs it. Check if the soft-float linker already exists on 5.16.2.1.1. |

---

## 3. Downgrade Procedure (Step-by-Step)

This is the verified procedure from [KindleModding.org Downgrading Guide](https://kindlemodding.org/firmware-and-flashing/downgrading/) and confirmed by MobileRead thread [t=357058](https://www.mobileread.com/forums/showthread.php?t=357058).

### Prerequisites

1. **Confirm JB is functional**: `;log mrpi` should respond (not just show search results).
2. **Download the PW4 5.16.2.1.1 firmware file**:
   ```
   https://s3.amazonaws.com/firmwaredownloads/update_kindle_all_new_paperwhite_v2_5.16.2.1.1.bin
   ```
   ⚠️ **Use `all_new_paperwhite_v2` NOT `update_kindle_10th`** — the `v2` file is the correct one for PW4. ([LanguageBreak GitHub](https://github.com/notmarek/LanguageBreak))
3. **Download the Allow Downgrade scriplet**:
   ```
   https://kindlemodding.org/firmware-and-flashing/downgrading/AllowDowngrade.sh
   ```
   (Created by Marek / [MobileRead user 340787](https://www.mobileread.com/forums/member.php?u=340787))

### Pre-Downgrade Steps

4. **Back up everything**: Copy all books, documents, and the entire `/mnt/us/extensions/` folder to your PC. Also back up `/mnt/us/kindle-dash/` and any custom scripts.
5. **Enable Airplane Mode** (Settings → All Settings → Wireless → Airplane Mode ON).
6. **Disable USBNetwork** if installed (KUAL → USBNetwork → Disable USBNetwork).
7. **Restore OTA updates** (so the updater works during downgrade):
   - KUAL → Rename OTA Binaries → **Restore**
   - Wait for reboot.

### Downgrade Steps

8. **Copy the Allow Downgrade scriplet** to the `documents` folder on your Kindle (via USB).
9. **Eject and unplug** the Kindle.
10. **Open the "Allow Downgrade" booklet** from your library.
    - The Kindle will print text on screen for a few seconds and return to the library.
    - This spoofs `version.txt` to the lowest possible version, tricking the updater into accepting the "older" firmware as an "upgrade."
11. **Plug the Kindle back into your PC.**
12. **Copy the firmware `.bin` file** to the **root directory** of the Kindle:
    ```
    update_kindle_all_new_paperwhite_v2_5.16.2.1.1.bin
    ```
13. **DO NOT eject or unplug.** While still connected, **hold the power button** until the Kindle restarts (15–30 seconds).
    - The Kindle will boot into the updater and install the firmware.
    - This takes several minutes. Do not interrupt.

### Post-Downgrade Steps

14. **Wait for the Kindle to fully boot.** It may show a progress bar or the Kindle tree logo.
15. **If you get a white screen** (common with large firmware jumps):
    - Plug into PC
    - Create an empty file named `DO_FACTORY_RESTORE` (no extension) in the root directory
    - Force reboot by holding power button 20–30 seconds
    - ⚠️ This will factory-reset settings, so have your backups ready.
16. **Verify firmware version**: Settings → Device Options → Device Info → should show `5.16.2.1.1`.
17. **Verify JB survived**: Type `;log mrpi` in the search bar — should show MRPI activity, not just search results.
18. **Reinstall the hotfix** if needed: copy `update_hotfix_languagebreak-*.bin` to root, then Settings → Update Your Kindle.
19. **Re-enable OTA blocking**: KUAL → Rename OTA Binaries → **Rename**. Wait for reboot.
20. **Reinstall soft-float extensions** (linkss, KOReader, etc.) as needed.
21. **Recreate the `/lib/ld-linux.so.3` symlink** if your `fix_linker` script is needed and the symlink was wiped.

### Alternative Method: Downgrader KUAL Extension

Some users prefer the Downgrader KUAL extension ([MobileRead t=347165](https://www.mobileread.com/forums/showthread.php?t=347165)):

1. Install the Downgrader extension in `/mnt/us/extensions/`
2. Copy the firmware `.bin` to root at the same time
3. KUAL → Downgrader → Select your device (PW4)
4. Kindle reboots and installs the firmware

This is functionally equivalent — both methods spoof `version.txt`.

---

## 4. Is 5.16.2.1.1 the Best Version for linkss?

**Yes, 5.16.2.1.1 is the optimal target.** Here's why:

| Version | ABI | linkss works? | JB available? | Notes |
|---------|-----|---------------|---------------|-------|
| 5.16.2.1.1 | soft-float | ✅ Yes (native) | ✅ LanguageBreak | **Best target** — last soft-float, last LB-jailbreakable |
| 5.16.3+ | hard-float | ❌ No (ABI mismatch) | ❌ LanguageBreak patched | linkss 0.25.N crashes |
| 5.16.7 (your current) | hard-float | ❌ No | ✅ Adbreak (if already JB) | Where you are now |
| 5.13.x – 5.16.2.0 | soft-float | ✅ Yes | ✅ WatchThis/LanguageBreak | Older UI, fewer features |

**5.16.2.1.1 is the sweet spot** because:
- It's the **last soft-float firmware** — all existing linkss/KOReader binaries work natively.
- It's the **last version LanguageBreak can jailbreak** — if you ever lose your JB, you can re-JB.
- It has the most recent soft-float UI/features before the ABI break.
- linkss 0.25.N was built and tested against this version. ([MobileRead t=195474, page 203](https://www.mobileread.com/forums/showthread.php?t=195474&page=203))

**Don't go lower** (e.g., 5.13.x) unless you specifically want the old UI layout — you'd lose features and gain nothing for linkss compatibility.

---

## 5. Role of renameotabin in the Downgrade Process

### What renameotabin does
- **Renames** the OTA update binaries (`update.bin.tmp.partial`, `/usr/sbin/otaupd`, `/usr/sbin/otav3`, etc.) so the Kindle **cannot download or install OTA updates** automatically.
- Accessed via KUAL → Rename OTA Binaries → **Rename** (to block) or **Restore** (to unblock).

### In the downgrade process:

| Step | renameotabin state | Why |
|------|-------------------|-----|
| Before downgrade | **Restore** (unblock) | The firmware updater needs the OTA binaries intact to install the downgrade `.bin`. If binaries are renamed, the updater can't function. |
| During downgrade | Restored | Updater installs 5.16.2.1.1. |
| After downgrade | **Rename** (re-block) | Prevent the Kindle from auto-upgrading back to 5.16.7+ over Wi-Fi. |

**Key insight from MobileRead user hius07** ([t=357058, post #6](https://www.mobileread.com/forums/showthread.php?t=357058)): *"renameOTAbin doesn't prevent installing firmware updates via reboot, no need to disable it."*

However, KindleModding.org recommends restoring first to avoid complications. **Best practice: Restore before, Rename after.**

### renameotabin does NOT:
- Prevent manual `.bin` installation via power-button reboot
- Prevent the "Allow Downgrade" scriplet from working
- Survive a firmware update itself (the renamed binaries are on rootfs, which gets flashed) — so you'll need to re-Rename after downgrade.

**Source**: [KindleModding.org — Disabling OTA Updates](https://kindlemodding.org/jailbreaking/post-jailbreak/disable-ota.html)

---

## 6. Risks

### Bricking
- **Risk: Low.** The scriplet-based downgrade uses Amazon's own updater mechanism. It doesn't bypass the bootloader.
- **Exception**: 5.18.x+ has bootloader hardening on some models that can reject downgrades. **PW4 on 5.16.x does NOT have this issue.**
- **Recovery**: If bricked, a 1.8V serial-to-USB adapter soldered to the UART pads can flash firmware directly. (Advanced, requires disassembly.)

### Data Loss
- **Risk: Moderate.** The firmware update itself doesn't wipe `/mnt/us` (books, extensions, custom scripts survive).
- **However**: `DO_FACTORY_RESTORE` (needed if you get a white screen) DOES wipe settings and may require re-registration.
- **Mitigation**: Back up everything to PC before starting. Copy the entire `/mnt/us/` partition if possible.

### Losing the Jailbreak
- **Risk: Very Low.** The JB payload is on `/mnt/us`, which firmware updates don't touch.
- **Exception**: If your JB is already non-functional (e.g., `;log` commands don't work), you can't initiate the downgrade. This is the "northirid scenario" from [t=360087](https://www.mobileread.com/forums/showthread.php?t=360087).
- **Your case**: JB is functional (KUAL works), so this risk doesn't apply.

### White Screen of Death
- **Risk: Low-Moderate** for large firmware jumps (5.16.7 → 5.16.2.1.1 is a moderate jump).
- **Fix**: `DO_FACTORY_RESTORE` empty file in root + force reboot. (See step 15 above.)
- **Source**: [KindleModding.org Downgrading Guide](https://kindlemodding.org/firmware-and-flashing/downgrading/)

### Extension Breakage
- **Risk: Certain.** All hard-float binaries will stop working. This is expected and fixable by reinstalling soft-float builds.
- **Your `touch_tap` binary**: If compiled with `arm-linux-gnueabihf` (hard-float), it WILL crash on 5.16.2.1.1. Recompile with `arm-linux-gnueabi` (soft-float) + `-mfloat-abi=soft`.

### Accidental Re-Upgrade
- **Risk: High if you forget to re-enable renameotabin.** The Kindle WILL auto-update over Wi-Fi if OTA binaries are restored.
- **Mitigation**: Immediately after downgrade, KUAL → Rename OTA Binaries → Rename. Keep Airplane Mode on until this is done.

---

## 7. Will Custom Extensions (kindle-dash, touch_tap) Work After Downgrade?

### dash_interactive.sh (shell script)
**Yes, will work.** Shell scripts are interpreted by `/bin/sh` and are ABI-independent. The only dependency is that any binaries *called by* the script (like `touch_tap`) must be soft-float compatible.

### touch_tap binary
**Depends on compilation target:**

```bash
# Check which ABI your touch_tap was compiled for:
file touch_tap
# If output says: "ELF 32-bit LSB executable, ARM, ... GNU/Linux 3.2.0, soft-float"
#   → ✅ Will work on 5.16.2.1.1
# If output says: "ELF 32-bit LSB executable, ARM, ... hard-float"
#   → ❌ Will crash on 5.16.2.1.1, needs recompilation
```

**To recompile for soft-float (5.16.2.1.1):**
```bash
# Use the soft-float toolchain
arm-linux-gnueabi-gcc -o touch_tap touch_tap.c -static
# NOT arm-linux-gnueabihf-gcc (that's hard-float)
```

### kindle-dash extension (KUAL extension)
**Yes, will work.** KUAL extensions are shell-script-based (`menu.json` + `config.json` + shell scripts). They're ABI-independent.

### /lib/ld-linux.so.3 symlink (your fix_linker script)
**May need recreation.** The symlink you created at `/lib/ld-linux.so.3` → `/usr/lib/ld-linux.so.3` lives on the root filesystem (`/lib/`), which **IS replaced during a firmware update**. After downgrading to 5.16.2.1.1:

- Check if the symlink still exists: `ls -la /lib/ld-linux.so.3`
- If missing, recreate it via SSH/USBNetwork or a KUAL extension script.
- **However**: On 5.16.2.1.1 (soft-float), the dynamic linker path may already be correct for soft-float binaries, so the symlink workaround (which was for hard-float 5.16.7) may no longer be needed.

---

## 8. PW4-Specific Quirks

### Correct firmware file
PW4 = "Kindle Paperwhite (10th Generation)" = `all_new_paperwhite_v2`:
```
https://s3.amazonaws.com/firmwaredownloads/update_kindle_all_new_paperwhite_v2_5.16.2.1.1.bin
```
⚠️ **Do NOT use** `update_kindle_10th_5.16.2.1.1.bin` — that's for the basic Kindle 10th gen (KT4), a different device. ([LanguageBreak GitHub](https://github.com/notmarek/LanguageBreak))

### No bootloader hardening on PW4 for 5.16.x
Unlike some newer models (Scribe, PW5) that may reject downgrades at 5.18.x+, the PW4 has **no bootloader-level downgrade protection** for the 5.16.x firmware range. You can freely downgrade within 5.16.x and below. ([KindleModding.org](https://kindlemodding.org/firmware-and-flashing/downgrading/): "Some Kindle models *might* not be able to downgrade below 5.18.x... due to Amazon's bootloader hardening" — PW4 is not affected.)

### Screensaver resolution
PW4 screensaver images for linkss should be **1072×1448 pixels** (PW4's exact e-ink resolution). ([Reddit confirmation](https://www.reddit.com/r/kindle/comments/ridizn/custom_screensavers_i_made_for_my_kindle/))

### Adbreak JB on 5.16.7
The Adbreak jailbreak works on firmware 5.18.1–5.18.5 and was patched in 5.18.6. Since 5.16.7 < 5.18.1, your PW4 was likely jailbroken via an earlier method (LanguageBreak on ≤5.16.2.1.1, then upgraded) or via the "adbreak" method referenced in your project context. Either way, the JB persistence mechanism is the same: hotfix in `/mnt/us/mkk/` + `RUNME.sh`.

---

## Source Links

1. **KindleModding.org — Downgrading Guide**: https://kindlemodding.org/firmware-and-flashing/downgrading/
2. **KindleModding.org — Disabling OTA Updates (renameotabin)**: https://kindlemodding.org/jailbreaking/post-jailbreak/disable-ota.html
3. **KindleModding.org — Downloading Firmware**: https://kindlemodding.org/firmware-and-flashing/downloading-updates.html
4. **LanguageBreak GitHub (firmware URLs)**: https://github.com/notmarek/LanguageBreak
5. **MobileRead t=357058 — Firmware downgrade after LanguageBreak**: https://www.mobileread.com/forums/showthread.php?t=357058
6. **MobileRead t=360087 — PW4 jailbroken, updated to 5.16.7, can't downgrade**: https://www.mobileread.com/forums/showthread.php?t=360087
7. **MobileRead t=356872 — LanguageBreak tutorial**: https://www.mobileread.com/forums/showthread.php?t=356872
8. **MobileRead t=195474 — K5 ScreenSavers Hack (linkss)**: https://www.mobileread.com/forums/showthread.php?t=195474
9. **MobileRead t=370281 — Updated without removing renameotabin**: https://www.mobileread.com/forums/showthread.php?t=370281
10. **KOReader Discussion #11298 — hard-float/soft-float ABI**: https://github.com/koreader/koreader/discussions/11298
11. **MobileRead t=347165 — Downgrader KUAL extension**: https://www.mobileread.com/forums/showthread.php?t=347165
12. **AnswerOverflow — Can't install linkss 0.25 on 5.16.2.1.1**: https://www.answeroverflow.com/m/1382977739186901113

---

## Action Checklist for Your PW4

```
[ ] 1. Back up /mnt/us/ entirely to PC (books, extensions, kindle-dash, scripts)
[ ] 2. Download update_kindle_all_new_paperwhite_v2_5.16.2.1.1.bin
[ ] 3. Download AllowDowngrade.sh from kindlemodding.org
[ ] 4. Enable Airplane Mode
[ ] 5. KUAL → Rename OTA Binaries → Restore (reboot)
[ ] 6. Copy AllowDowngrade.sh to /mnt/us/documents/
[ ] 7. Eject, unplug, open "Allow Downgrade" booklet
[ ] 8. Plug back in, copy .bin to root
[ ] 9. Hold power button until restart (DO NOT eject)
[ ] 10. Wait for firmware install + reboot
[ ] 11. If white screen: DO_FACTORY_RESTORE + force reboot
[ ] 12. Verify FW = 5.16.2.1.1 (Settings → Device Info)
[ ] 13. Verify JB: ;log mrpi responds
[ ] 14. Reinstall hotfix if needed
[ ] 15. KUAL → Rename OTA Binaries → Rename (reboot)
[ ] 16. Reinstall soft-float linkss 0.25.N (Update_linkss_0.25.N_install_touch_pw.bin → mrpackages)
[ ] 17. Reinstall soft-float KOReader
[ ] 18. Recompile touch_tap with arm-linux-gnueabi (soft-float) if needed
[ ] 19. Recreate /lib/ld-linux.so.3 symlink if still needed
[ ] 20. Test kindle-dash, touch_tap, linkss screensavers
```
