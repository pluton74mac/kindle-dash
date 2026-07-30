# Kindle Framebuffer Rendering

> How to render images and text to the Kindle e-ink display via `/dev/fb0` and the `eips` command, with pixel format details and a comparison of approaches.

## Summary

The Kindle exposes its e-ink display as a Linux framebuffer device at `/dev/fb0`. Two approaches exist for rendering: (1) direct framebuffer writes via `mmap()` + ioctl, and (2) the built-in `eips` command for text and image display. The framebuffer is 8-bit grayscale on modern Kindles (Touch onward). Images must be converted to the correct pixel format; the kdashboard project uses PGM (Portable GrayMap) as an intermediate format and writes directly to the framebuffer for full-screen dashboard rendering, using `eips ''` to trigger the display refresh.

**Related:** [Kindle Platform Overview](kindle-platform-overview.md) | [Kindle KUAL Extension](kindle-kual-extension.md) | [Kindle Power Management](kindle-power-management.md)

---

## The Framebuffer Device (`/dev/fb0`)

### Accessing the Framebuffer

The framebuffer is a standard Linux framebuffer device at `/dev/fb0`. The standard approach for native code:

1. **Open** the device: `open("/dev/fb0", O_RDWR)`
2. **Query screen info** via two ioctls:
   - `FBIOGET_VSCREENINFO` → `fb_var_screeninfo` (xres, yres, bits_per_pixel)
   - `FBIOGET_FSCREENINFO` → `fb_fix_screeninfo` (line_length, smem_len)
3. **Memory-map** the framebuffer: `mmap(0, screensize, PROT_READ|PROT_WRITE, MAP_SHARED, fd, 0)`
4. **Write pixels** to the mapped memory
5. **Sync** with `msync(fb, screensize, MS_SYNC)`
6. **Trigger display refresh** (see below)
7. **Unmap and close**: `munmap()`, `close(fd)`

### Screen Size Calculation

```c
long screensize = finfo.line_length * (vinfo.yres_virtual ? vinfo.yres_virtual : vinfo.yres);
```

The `line_length` may be larger than `xres * bytes_per_pixel` due to padding. Always use `line_length` for row offsets.

> **Source:** kdashboard `kindle_dashboard.cpp` `renderToFramebuffer()`, [SixFoisNeuf Kindle internals](https://www.sixfoisneuf.fr/posts/kindle-hacking-deeper-dive-internals/)

### Pixel Format

| Generation | Bits per Pixel | Format |
|-----------|---------------|--------|
| K1–K3 | 4 bpp | Packed nibbles (2 pixels per byte) |
| K4 | 8 bpp | 1 byte per pixel |
| K5 (Touch)+ | 8 bpp | 1 byte per pixel, 256 grayscale levels |
| Some newer models | 16/32 bpp | RGB565 or XRGB8888 |

The kdashboard handles all of 1, 4, 8, 16, and 32 bpp via `putFramebufferPixel()`:

```c
if (vinfo.bits_per_pixel != 1 && vinfo.bits_per_pixel != 4 && 
    vinfo.bits_per_pixel != 8 && vinfo.bits_per_pixel != 16 && 
    vinfo.bits_per_pixel != 32) {
    // unsupported
}
```

For 8-bit: write the grayscale byte directly. For other depths, the code converts the 8-bit grayscale value to the appropriate format.

> **Source:** kdashboard `kindle_dashboard.cpp` lines 2334-2340, [geekmaster MobileRead](https://www.mobileread.com/forums/showthread.php?t=162743)

### Framebuffer Dimensions by Model

| Model | Width (px) | Height (px) | Notes |
|-------|-----------|-------------|-------|
| K4 (non-touch) | 600 | 800 | 8 bpp |
| K5 (Touch) | 608 | 800 | Right 8px not visible |
| PW1/PW2 | 758 | 1024 | 8 bpp |
| PW3+ | 1072 | 1448 | 8 bpp |
| KOA2+ | 1264 | 1680 | 8 bpp |

Query at runtime with `eips -i` or `FBIOGET_VSCREENINFO`.

---

## The `eips` Command

`eips` (E Ink Display Support) is a built-in Kindle utility at `/usr/sbin/eips` that can display text, images, and trigger screen refreshes.

> **Source:** [MobileRead Wiki - Eips](https://wiki.mobileread.com/wiki/Eips)

### Command Reference

#### Update Screen (trigger display refresh from framebuffer)

```sh
eips ''
```

This is the primary way to trigger a display update after writing to `/dev/fb0` on Kindle Touch and later. It reads the current framebuffer contents and pushes them to the e-ink panel.

#### Display an Image

```sh
eips -g|-b image_path [-w waveform -f -x xpos -y ypos -v]
```

| Flag | Description |
|------|-------------|
| `-g` | Display a PNG or JPG image |
| `-b` | Display a bitmap (raw framebuffer format) |
| `-w` | Waveform mode: `gc16` (default), `gl16`, or `du` |
| `-f` | Full update (with flash); default is partial |
| `-x` | X position in pixels (does not work on K4) |
| `-y` | Y position in pixels (does not work on K4) |
| `-v` | Inverted picture (does not work on K4) |

#### Print Text

```sh
eips [col] [row] [-h] "string"
```

- Text grid: 50 rows × 40 columns (on Touch)
- `-h` for highlighted (bold) text
- Column/row are 0-indexed in character grid units

#### Clear Screen

```sh
eips -c
```

Clears the entire framebuffer and triggers a full refresh.

#### Get Framebuffer Info

```sh
eips -i
```

Prints bits/pixel, bytes/line, resolution. Add any character for colormap:

```sh
eips -i c
```

#### Other Commands

| Command | Description |
|---------|-------------|
| `eips -q` | Paint checker pattern (not on K4) |
| `eips -l` | Paint grayscale gradient (not on K4) |
| `eips -p` | Paint pattern |
| `eips -r barcode` | Paint barcode |
| `eips -z first_row last_row` | Scroll screen between two rows |
| `eips -d l=level,w=width,h=height` | Paint rectangle (not on K4) |

### How `eips` Works Internally

From `strace` analysis of `eips -c`:

```
open("/dev/fb0", O_RDWR)
ioctl(3, FBIOGET_VSCREENINFO, ...)
mmap2(NULL, 480000, PROT_READ|PROT_WRITE, MAP_SHARED|MAP_LOCKED, 3, 0)
ioctl(3, FBIO_EINK_CLEAR_SCREEN, 0)
close(3)
```

The mmap'd region is exactly `width × height` bytes (e.g., 600×800 = 480000 bytes), confirming one byte per pixel.

> **Source:** [SixFoisNeuf strace analysis](https://www.sixfoisneuf.fr/posts/kindle-hacking-deeper-dive-internals/)

---

## Image Format Requirements

### PGM (Portable GrayMap) — kdashboard's Format

The kdashboard uses **P5 binary PGM** as its image format. This is the simplest grayscale format:

```c
int writePgm(const char* path, const Canvas* canvas) {
    FILE* file = fopen(path, "wb");
    if (!file) return 0;
    fprintf(file, "P5\n%d %d\n255\n", canvas->width, canvas->height);
    const size_t bytes = canvas->width * canvas->height;
    const int ok = fwrite(canvas->pixels, 1, bytes, file) == bytes;
    fclose(file);
    return ok;
}
```

PGM P5 format:
```
P5\n
<width> <height>\n
255\n
<raw 8-bit grayscale pixel data>
```

- 0 = black, 255 = white
- One byte per pixel
- No compression
- Trivially parseable in C

### PNG and JPG

`eips -g` can display PNG and JPG files directly. The Kindle's `eips` handles format conversion and dithering internally. However, this approach is slower than direct framebuffer writes for full-screen updates.

### BMP

`eips -b` can display raw bitmap files in the framebuffer's native format.

### Dithering

The framebuffer is 8-bit (256 levels), but the physical e-ink panel typically renders only **16 grayscale levels**. The display controller handles quantization/dithering. For photographic images, ordered dithering or Floyd-Steinberg dithering should be applied before writing to the framebuffer to reduce banding artifacts.

The kdashboard handles image inversion via a `--invert-images` flag, which flips the grayscale values (useful for dark mode where the framebuffer polarity is inverted on some Kindle models).

---

## Comparison: Direct Framebuffer Write vs `eips`

| Aspect | Direct `/dev/fb0` mmap | `eips` Command |
|--------|----------------------|-----------------|
| **Speed** | Fast — single mmap + pixel write + single `eips ''` refresh | Slower — process spawn per text line or image |
| **Full-screen render** | ✅ Write all pixels, one refresh call | ⚠️ Multiple `eips` calls or one `-g` image call |
| **Text rendering** | Must implement font rendering yourself | Built-in text grid (40×50 chars) |
| **Image display** | Write raw pixels to mmap'd buffer | `eips -g image.png` handles format conversion |
| **Partial updates** | ✅ Write only changed pixels, `eips ''` to refresh | `eips` partial update is default (no `-f` flag) |
| **Ghosting** | Must manage — call `eips ''` after writes | `eips` handles waveform selection |
| **Status bar** | Must skip top ~66 px manually | Text mode uses rows, doesn't overlap status bar |
| **Flexibility** | Full control over every pixel | Limited to text grid or pre-rendered images |
| **Dependencies** | None (standard Linux fb API) | Requires `eips` binary present |

### kdashboard's Approach

The kdashboard uses a **hybrid approach**:

1. **Primary rendering:** Direct framebuffer write via `mmap()`
   - Allocates an in-memory `Canvas` (width × height, 8-bit grayscale)
   - Renders the entire dashboard to the canvas (text, lines, images, cards)
   - Optionally saves canvas as PGM via `writePgm()`
   - Copies canvas pixels to the mmap'd framebuffer, skipping the top 66 pixels (status bar)
   - Calls `msync()` then `eips ''` to trigger refresh

2. **Fallback text rendering:** `eips` text grid
   - `renderToEips()` uses `eips 1 <row> '<text>'` for each line
   - Used when framebuffer is unavailable or for error messages

3. **FBInk fallback:** (disabled in current code)
   - Would write PGM to `/tmp/` and call `fbink` to display it
   - Preserves the status bar by only updating the content area

> **Source:** kdashboard `kindle_dashboard.cpp` `renderToFramebuffer()`, `renderToEips()`, `renderViaFbink()`

---

## Saving and Restoring the Framebuffer

From geekmaster's MobileRead post:

```sh
# Save framebuffer
dd if=/dev/fb0 bs=608 count=800 > /mnt/us/fb0.raw

# Restore framebuffer
cat /mnt/us/fb0.raw > /dev/fb0
eips -g . > /dev/null
```

Adjust `bs` (bytes per line) and `count` (number of lines) for the target model. The kdashboard saves its last render as PGM via `--save-pgm` for debugging.

> **Source:** [geekmaster on MobileRead](https://www.mobileread.com/forums/showthread.php?t=162743)

---

## Touch Visual Feedback (Framebuffer Blink)

The kdashboard implements a visual touch feedback by inverting a rectangular region on the framebuffer:

1. `open("/dev/fb0")`
2. `mmap()` the framebuffer
3. Invert pixels in the touch region (XOR with 0xFF)
4. `msync()` + `eips ''` to refresh
5. `usleep(120000)` (120ms)
6. Invert back (restore original pixels)
7. `msync()` + `eips ''` again

This creates a brief "blink" effect on touch, confirming the tap registered.

> **Source:** kdashboard `kindle_dashboard.cpp` `flashTouchRectOnFramebuffer()`

---

## See Also

- [Kindle Platform Overview](kindle-platform-overview.md) — Model specs and e-ink details
- [Kindle KUAL Extension](kindle-kual-extension.md) — How to package and launch the renderer
- [Kindle Power Management](kindle-power-management.md) — Keeping the screen awake during rendering
- [MobileRead Wiki - Eips](https://wiki.mobileread.com/wiki/Eips)
- [MobileRead Wiki - Framebuffer for Kindle](https://wiki.mobileread.com/wiki/Framebuffer_for_Kindle)
