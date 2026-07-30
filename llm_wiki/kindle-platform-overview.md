# Kindle Platform Overview

> Jailbreak-compatible Kindle models, screen resolutions, touch capability, and e-ink display specifications for building custom dashboard applications.

## Summary

The Kindle platform spans multiple hardware generations with varying screen resolutions, touch capabilities, and e-ink display technologies. For dashboard projects, the key models are those that support jailbreak + KUAL (Kindle Unified Application Launcher). Modern jailbreaks (WinterBreak, WinterBreak2) cover most Kindle models from the 5th generation onward. E-ink displays on Kindles are 8-bit grayscale (256 levels on newer models, 16 levels on older) accessed through `/dev/fb0`, with the built-in `eips` command for screen updates.

**Related:** [Kindle Framebuffer Rendering](kindle-framebuffer-rendering.md) | [Kindle KUAL Extension](kindle-kual-extension.md) | [Kindle Power Management](kindle-power-management.md)

---

## Jailbreak-Compatible Models

### Current Jailbreak Methods

As of 2026, two main jailbreak methods are available:

| Method | Supported Firmware | Models |
|--------|-------------------|--------|
| **WinterBreak** | < 5.18.1 | PW2–PW5, KOA1–KOA3, KT2–KT4, KV, KS1, KS2, CS |
| **WinterBreak2** | < 5.16.4 | PW2–PW5, KOA1–KOA3, KT2–KT4, KV |
| **Legacy JB** | Various | K1–K4, KT (K5), PW1 |
| **PEKI** (KUAL) | N/A | K5 and newer (modern KUAL replacement for azw2) |

> **Source:** [kindlemodding.org](https://kindlemodding.org/kindle-models.html), [MobileRead jailbreak forum](https://www.mobileread.com/forums/showthread.php?t=361822)

### Key Models for Dashboard Projects

| Amazon Name | Nickname | Gen | Latest Firmware | Resolution | PPI | Touch | Jailbreak |
|-------------|----------|-----|-----------------|------------|-----|-------|-----------|
| Kindle (7th Gen) | KT2 / BASIC | 7 | 5.12.2.2 | 800×600 | 167 | Yes | WinterBreak2 |
| Kindle Paperwhite (7th Gen) | PW3 | 7 | 5.16.2.1.1 | 1072×1448 | 300 | Yes | WinterBreak2 |
| Kindle Paperwhite (6th Gen) | PW2 | 6 | 5.12.2.2 | 758×1024 | 212 | Yes | WinterBreak2 |
| Kindle Paperwhite (5th Gen) | PW5 | 11 | 5.17.x | 1072×1448 | 300 | Yes | WinterBreak |
| Kindle Oasis (8th Gen) | KOA1 | 8 | 5.16.2.1.1 | 1072×1448 | 300 | Yes | WinterBreak2 |
| Kindle Oasis (9th Gen) | KOA2 | 9 | 5.16.2.1.1 | 1264×1680 | 300 | Yes | WinterBreak2 |
| Kindle Oasis (10th Gen) | KOA3 | 10 | 5.16.2.1.1 | 1264×1680 | 300 | Yes | WinterBreak2 |
| Kindle Voyage | KV | 7 | 5.13.6 | 1072×1448 | 300 | Yes | WinterBreak2 |
| Kindle Touch | KT / K5 | 4 | 5.3.7.3 | 600×800 | 167 | Yes | Legacy K5 JB |
| Kindle (4th Gen) | K4 / K4S | 4 | 4.1.4 | 600×800 | 167 | No | Legacy K4 JB |

> **Sources:** [kindlemodding.org Kindle Models](https://kindlemodding.org/kindle-models.html), [ebookdetectives.com](https://ebookdetectives.com/tag/ed08/), [businessinsider.com](https://www.businessinsider.com/reference/what-is-kindle-paperwhite)

### Recommended Models for Dashboard Use

For a dashboard project, the ideal Kindle is one with:
- **Touch screen** (required for interactive tap zones)
- **300 PPI** (crisp text rendering)
- **Jailbreak available** on current firmware
- **Low cost** (used market)

The **Kindle Paperwhite 3 (PW3)** and **Paperwhite 5 (PW5)** are the best candidates. The PW3 in particular is widely available used, has 300 PPI, touch, and is jailbreakable via WinterBreak2 on firmware < 5.16.4.

The kdashboard project targets the Paperwhite family, using a fallback resolution of 760×1024 (PW2-class) and supporting the status bar height of 66 pixels.

---

## Screen Resolutions

| Model | Resolution (px) | Aspect Ratio | PPI | Screen Size |
|-------|-----------------|---------------|-----|-------------|
| Kindle Basic (7th-10th Gen) | 800×600 | 4:3 | 167 | 6" |
| Kindle Paperwhite 1 (PW1) | 758×1024 | 3:4 | 212 | 6" |
| Kindle Paperwhite 2 (PW2) | 758×1024 | 3:4 | 212 | 6" |
| Kindle Paperwhite 3+ (PW3-PW5) | 1072×1448 | 3:4 | 300 | 6" |
| Kindle Voyage | 1072×1448 | 3:4 | 300 | 6" |
| Kindle Oasis 1 (KOA) | 1072×1448 | 3:4 | 300 | 6" |
| Kindle Oasis 2+ (KOA2-KOA3) | 1264×1680 | 3:4 | 300 | 7" |
| Kindle Scribe (KS) | 1860×2480 | 3:4 | 300 | 10.2" |

> **Note:** The framebuffer orientation may differ from the physical screen orientation. The kdashboard code uses portrait orientation (width < height) and preserves the top 66 pixels as the Kindle status bar.

---

## Touch Capability

| Model | Touch | Input Device | Notes |
|-------|-------|---------------|-------|
| K1–K4 (pre-Touch) | No | `/dev/input/event0` (buttons) | Use physical keys only |
| Kindle Touch (K5) onward | Yes | `/dev/input/eventN` (capacitive) | Multi-touch on some models |

The kdashboard project reads touch input by scanning `/dev/input/event0` through `event15`, looking for devices with `ABS_X`/`ABS_Y` or `ABS_MT_POSITION_X`/`ABS_MT_POSITION_Y` ranges (using `EVIOCGABS` ioctl). It uses `EVIOCGRAB` to exclusively grab the touch device while the dashboard is running, preventing the Kindle framework from also receiving touch events.

Touch coordinates are scaled from the device's absolute range to screen pixels:

```c
scaled = (value - minimum) * (screen_size - 1) / (maximum - minimum)
```

> **Source:** kdashboard `kindle_dashboard.cpp` `initTouchInput()` and `scaleAbsValue()` functions; [SixFoisNeuf Kindle internals](https://www.sixfoisneuf.fr/posts/kindle-hacking-deeper-dive-internals/)

---

## E-Ink Display Specifications

### Grayscale Levels

| Model Generation | Bits per Pixel | Grayscale Levels | Framebuffer Width |
|-----------------|----------------|------------------|-------------------|
| K1–K3 (legacy) | 4 bpp | 16 | 600 |
| K4 (non-touch) | 8 bpp | 256 | 600 |
| Kindle Touch (K5) | 8 bpp | 256 | 608 (right 8px not visible) |
| PW1 onward | 8 bpp | 256 | Model-dependent (758/1072/1264) |

> **Source:** [geekmaster on MobileRead](https://www.mobileread.com/forums/showthread.php?t=162743), confirmed by `eips -i` output

The kdashboard renders to an internal 8-bit grayscale canvas (one byte per pixel, 0=black, 255=white), then writes pixel-by-pixel to the framebuffer using `putFramebufferPixel()`, which handles the conversion for 1/4/8/16/32 bpp framebuffers.

### E-Ink Technologies

| Technology | Generation | Grayscale | Notes |
|-----------|-----------|-----------|-------|
| E Ink Pearl | 2010 | 16 levels | Older Kindles (K3, K4) |
| E Ink Carta | 2013+ | 16 levels (hardware) | PW1 onward; 8-bit framebuffer but ~16 physical gray levels |
| E Ink Carta HD | 2014+ | 16 levels | PW2+; higher resolution |

The framebuffer is 8-bit (256 values per pixel), but the physical e-ink panel typically renders **16 grayscale levels**. The intermediate framebuffer values are dithered or quantized by the display controller.

> **Sources:** [E Ink Wikipedia](https://en.wikipedia.org/wiki/E_Ink), [Glider e-ink documentation](https://github.com/Modos-Labs/Glider), [eink.com Kaleido 3](https://www.eink.com/brand/detail/Kaleido3)

### Refresh Types

Kindle e-ink displays support two primary refresh modes:

| Mode | Eips Flag | Description | Use Case |
|------|-----------|-------------|----------|
| **Full refresh** | `-f` | Full screen flash (black→white→content). Clears ghosting. | Initial render, image display |
| **Partial refresh** | (default) | Updates only changed pixels. No flash. Faster but may leave ghosting. | Text updates, incremental changes |
| **Clear** | `-c` | Clears entire framebuffer to blank. | Before full re-render |

### Waveform Modes (eips `-w` flag)

| Waveform | Description | Use Case |
|----------|-------------|----------|
| `gc16` | Gray Clear 16 — full 16-level grayscale, with clearing flash | Default for images |
| `gl16` | Gray Low 16 — 16-level grayscale, partial update (less clearing) | Text/graphics partial update |
| `du` | Direct Update — 1-bit (black/white only), fastest | Fast text updates |

> **Source:** [MobileRead Wiki - Eips](https://wiki.mobileread.com/wiki/Eips), [Glider waveform documentation](https://github.com/Modos-Labs/Glider)

### Display Update Trigger

After writing pixels to the framebuffer (`/dev/fb0`), the display must be told to refresh:

1. **From native code (older Kindles):** `ioctl(fd, FBIO_EINK_UPDATE_DISPLAY, mode)` where `0` = partial, `1` = full refresh
2. **From scripts (older Kindles):** `echo 1 > /proc/eink_fb/update_display`
3. **From scripts/native (Kindle Touch+):** `eips ''` (empty string triggers a display update from framebuffer)

The kdashboard uses `system("eips '' >/dev/null 2>&1 || true")` after writing to the framebuffer to trigger a refresh.

> **Source:** [geekmaster MobileRead thread](https://www.mobileread.com/forums/showthread.php?t=162743), [SixFoisNeuf Kindle internals](https://www.sixfoisneuf.fr/posts/kindle-hacking-deeper-dive-internals/)

---

## Framebuffer ioctl Constants

Discovered via `strace` on the `eips` binary:

| Constant | Hex Value | Function |
|----------|-----------|----------|
| `FBIOGET_VSCREENINFO` | `0x4600` | Get variable screen info (resolution, bpp) |
| `FBIOGET_FSCREENINFO` | — | Get fixed screen info (line length) |
| `FBIO_EINK_CLEAR_SCREEN` | `0x46e1` | Clear e-ink display |
| `FBIO_EINK_UPDATE_DISPLAY` | `0x46db` | Trigger display refresh (0=partial, 1=full) |

> **Source:** [SixFoisNeuf Kindle internals](https://www.sixfoisneuf.fr/posts/kindle-hacking-deeper-dive-internals/)

---

## System Architecture

Kindles run a Linux kernel (2.6.31-rt11 on K4) on ARM processors:

- **K4:** Freescale i.MX508 800 MHz, ARMv7l
- **PW2+:** Freescale i.MX6 / i.MX7 / MediaTek (varies by model)
- **Filesystem:** Read-only root (`/`), writable user partition at `/mnt/us` (FAT32, USB-accessible)
- **Init:** `rc.d` scripts, runlevel 5 = normal Kindle UI
- **Java framework:** Amazon's ebook reader runs as a Java application in `/opt/amazon`

The user partition `/mnt/us` is the only writable area accessible over USB. KUAL extensions install here at `/mnt/us/extensions/`.

> **Sources:** [SixFoisNeuf](https://www.sixfoisneuf.fr/posts/kindle-hacking-deeper-dive-internals/), [lidskialf blog](https://blog.lidskialf.net/2021/02/08/turning-an-old-kindle-into-a-eink-development-platform/)

---

## See Also

- [Kindle Framebuffer Rendering](kindle-framebuffer-rendering.md) — How to draw to the screen
- [Kindle KUAL Extension](kindle-kual-extension.md) — Packaging and launching apps
- [Kindle Power Management](kindle-power-management.md) — Keeping the screen awake
