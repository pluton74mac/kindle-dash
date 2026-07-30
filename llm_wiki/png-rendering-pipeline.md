# PNG Rendering Pipeline for Kindle E-ink Dashboard

> **Status:** Research + proposed design. E-ink rendering characteristics are based on community findings. Pipeline architecture is proposed for the the agent Kindle dashboard.

## Summary

How to render dashboard views as PNG images on the Mac using PIL/Pillow, optimized for Kindle e-ink displays. Covers image dimensions, grayscale conversion, dithering, font selection, anti-aliasing considerations, and PGM as an intermediate format.

## Kindle Screen Resolutions

| Model | Resolution (px) | DPI | Grayscale Levels | Orientation |
|---|---|---|---|---|
| Kindle 4 NT | 600×800 | 167 | 16 | Portrait |
| Kindle Paperwhite 2 (PW2) | 758×1024 | 212 | 16 | Portrait |
| Kindle Paperwhite 3 / 7th gen | 1072×1448 | 300 | 16 | Portrait |
| Kindle Paperwhite 11th gen | 1236×1648 | 300 | 16 | Portrait |
| Kindle Basic (2024) | 1072×1448 | 300 | 16 | Portrait |

**Key constraint:** All current Kindle e-ink screens display **16 levels of grayscale** (4-bit). The framebuffer accepts 8-bit grayscale PNG but quantizes to 16 levels on display. Design for this limitation.

**Source:** [TerminalBytes Kindle dashboard guide](https://terminalbytes.com/kindle-dashboard-eink-display-2026/), Amazon product specs, community research. See [similar-projects.md](similar-projects.md) for project-specific usage.

## Rendering with PIL/Pillow

### Core Library

```python
from PIL import Image, ImageDraw, ImageFont
```

Pillow is the standard Python imaging library. It's pre-installed on macOS via Homebrew or pip, and provides all the primitives needed: text rendering, shape drawing, image composition, and format conversion.

### Creating the Canvas

```python
# Kindle Paperwhite 3 resolution
WIDTH, HEIGHT = 1072, 1448

# Start with white background (grayscale mode 'L' = 8-bit luminance)
img = Image.new('L', (WIDTH, HEIGHT), 255)  # 255 = white
draw = ImageDraw.Draw(img)
```

### Font Selection

For e-ink readability at a distance, use clean, monospace or semi-proportional fonts:

```python
# macOS system fonts
FONT_PATHS = {
    'mono_large': '/System/Library/Fonts/Menlo.ttc',
    'mono_medium': '/System/Library/Fonts/Menlo.ttc',
    'sans_large': '/System/Library/Fonts/Helvetica.ttc',
    'sans_medium': '/System/Library/Fonts/Helvetica.ttc',
    'sans_bold': '/System/Library/Fonts/Helvetica Bold.ttf',
}

# Or use DejaVu (commonly available, cross-platform)
# /usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf
# /usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf

font_title = ImageFont.truetype(FONT_PATHS['sans_bold'], 64)
font_h1 = ImageFont.truetype(FONT_PATHS['sans_bold'], 48)
font_body = ImageFont.truetype(FONT_PATHS['sans_medium'], 32)
font_small = ImageFont.truetype(FONT_PATHS['mono_medium'], 24)
font_huge = ImageFont.truetype(FONT_PATHS['sans_bold'], 120)  # for hero numbers
```

**Font guidelines for e-ink:**
- **Minimum size:** 20px for any text (at 300 DPI, this is ~2.5mm — readable at arm's length)
- **Hero numbers:** 100-140px (readiness score, temperature, time)
- **Body text:** 28-36px
- **Captions/labels:** 20-24px
- **Avoid thin weights** — e-ink renders thin strokes faintly. Use Bold or Regular weights.
- **Monospace for numbers** — alignment is critical for data displays; Menlo or DejaVu Sans Mono

### Drawing Primitives

#### Text

```python
draw.text((40, 40), "Training Readiness", font=font_title, fill=0)  # 0 = black
draw.text((40, 120), "72", font=font_huge, fill=0)
draw.text((200, 160), "/ 100", font=font_body, fill=80)  # gray for secondary
```

#### Lines & Dividers

```python
# Horizontal divider
draw.line((40, 260, WIDTH - 40, 260), fill=0, width=3)

# Vertical separator
draw.line((WIDTH // 2, 120, WIDTH // 2, 800), fill=0, width=2)
```

#### Rectangles & Cards

```python
# Card border (for navigation tiles)
draw.rectangle((40, 400, 520, 740), outline=0, width=3)

# Filled status indicator
draw.rectangle((40, 400, 80, 440), fill=0)  # solid black square = OK
draw.rectangle((40, 400, 80, 440), outline=0, width=2)  # hollow = warning
```

#### Progress Bars

```python
def draw_progress_bar(draw, x, y, w, h, value, max_val, fill_color=0):
    """Draw a horizontal progress bar."""
    # Background (light gray)
    draw.rectangle((x, y, x + w, y + h), fill=220, outline=0, width=1)
    # Fill
    fill_w = int((value / max_val) * (w - 2))
    draw.rectangle((x + 1, y + 1, x + fill_w, y + h - 1), fill=fill_color)

# Example: calorie progress
draw_progress_bar(draw, 40, 500, 400, 30, calories=1450, max_val=2000)
```

#### Sparklines / Mini Charts

```python
def draw_sparkline(draw, x, y, w, h, values, fill=0):
    """Draw a simple sparkline (no axes, just the line)."""
    if not values or len(values) < 2:
        return
    min_v, max_v = min(values), max(values)
    if max_v == min_v:
        max_v = min_v + 1
    points = []
    for i, v in enumerate(values):
        px = x + int(i * w / (len(values) - 1))
        py = y + h - int((v - min_v) / (max_v - min_v) * h)
        points.append((px, py))
    draw.line(points, fill=fill, width=2)
    # Optional: dot at the end
    draw.ellipse((points[-1][0]-3, points[-1][1]-3, points[-1][0]+3, points[-1][1]+3), fill=fill)

# Example: 7-day HRV trend
draw_sparkline(draw, 40, 600, 400, 80, hrv_values=[45, 48, 42, 50, 47, 52, 49])
```

## Grayscale Optimization for E-ink

### The 16-Level Constraint

Kindle e-ink panels display 16 levels of gray (4-bit). Pillow's `'L'` mode is 8-bit (256 levels), but the Kindle hardware quantizes this to 16 on display. To maximize contrast and avoid muddy midtones:

### Strategy 1: Pure Black & White (recommended for text)

```python
img = Image.new('L', (WIDTH, HEIGHT), 255)
# Draw everything in fill=0 (black) on fill=255 (white)
# Use gray (fill=128) sparingly for secondary/de-emphasized elements
```

**Best for:** Text-heavy views, status indicators, navigation.
**Why:** E-ink excels at crisp black-on-white. Grays can look muddy on 16-level panels.

### Strategy 2: Limited Grayscale Palette

```python
# Use only a few well-chosen gray levels that map cleanly to the 16-level hardware
GRAY_DARK = 0      # black
GRAY_MID_DARK = 85  # ~33% gray
GRAY_MID = 128      # 50% gray
GRAY_MID_LIGHT = 170 # 67% gray
GRAY_LIGHT = 220    # ~85% gray (backgrounds)
WHITE = 255

# These map to specific hardware levels: 0, 4, 8, 11, 14, 15 (of 0-15)
```

### Strategy 3: Dithering for Photos/Gradients

For images that need smooth gradients (weather icons, charts), apply ordered dithering:

```python
# Convert to 4-bit grayscale with Floyd-Steinberg dithering
img_4bit = img.convert('L').quantize(colors=16, method=Image.FLOYDSTEINBERG)

# Or use ordered dithering (Bayer matrix) for a more regular pattern:
# Pillow doesn't have built-in ordered dithering, but you can use:
img_dithered = img.convert('1', dither=Image.ORDERED)  # 1-bit only

# For 4-bit ordered dithering, use the hitherdither library:
# pip install hitherdither
# import hitherdither
# palette = hitherdither.palette.GrayscalePalette()
# img_dithered = hitherdither.ordered.bayer.bayer(img, palette, [3])
```

**Dithering guidance:**
- **Floyd-Steinberg** (`Image.FLOYDSTEINBERG`): Best for photographs, produces smooth gradients but can look noisy on e-ink
- **Ordered (Bayer)**: Produces regular patterns, more predictable on e-ink, better for UI elements
- **No dithering** (`dither=Image.NONE`): Sharpest text, but causes banding in gradients
- **For dashboard UIs:** Use no dithering for text and UI elements. Only dither images/icons that have gradients.

### Anti-Aliasing Considerations

E-ink pixels are physical — anti-aliasing creates gray subpixels that look muddy on 16-level panels.

**Recommendation:**
```python
# Disable font anti-aliasing by drawing in bilevel mode
# Pillow doesn't directly disable AA, but you can post-process:

# Method 1: Threshold to 1-bit, then back to grayscale
img_bw = img.point(lambda p: 0 if p < 128 else 255, '1')
img_final = img_bw.convert('L')

# Method 2: Use mode '1' for drawing text (crisp, no AA)
# But this limits you to black/white only
```

**From community research** (homecircuits.eu build): Their CSS explicitly disables font smoothing:
```css
-webkit-font-smoothing: none;
-moz-osx-font-smoothing: grayscale;
shape-rendering: crispEdges;
```
The same principle applies when rendering with Pillow: use higher resolution fonts and threshold rather than relying on anti-aliasing.

**Practical approach:** Render at 2x resolution, then downscale with `Image.NEAREST` (no interpolation):
```python
# Render at 2x for sharper text
img_2x = Image.new('L', (WIDTH * 2, HEIGHT * 2), 255)
draw_2x = ImageDraw.Draw(img_2x)
# Draw with 2x font sizes...
# Downscale without interpolation
img = img_2x.resize((WIDTH, HEIGHT), Image.NEAREST)
```

## Output Format

### PNG (primary)

```python
img.save('/tmp/dashboard.png', format='PNG')
```

PNG is the standard format for Kindle framebuffer display. The `eips` command on jailbroken Kindles accepts PNG directly:
```bash
eips -f -g /tmp/dashboard.png
```

- `-f`: Full refresh (black/white flash, eliminates ghosting)
- `-g`: Display graphic file

### PGM (intermediate format)

PGM (Portable Gray Map) can be used as an intermediate format for testing or for Kindles that have trouble with PNG:

```python
img.save('/tmp/dashboard.pgm', format='PGM')
```

**Why PGM?**
- Simpler format than PNG — no compression overhead
- Direct pixel data, easy to inspect/debug
- Some Kindle tools (like `fbink`) handle PGM natively
- Faster to write for testing (no PNG encoding)

**When to use PGM:**
- Debug rendering (inspect raw pixel values)
- Testing dithering algorithms (compare input/output)
- When PNG encoding is too slow on the rendering machine (unlikely on a Mac, but relevant for Pi-based servers)

**When to use PNG:**
- Final output to Kindle (`eips` expects PNG or JPG)
- Serving over HTTP (PNG has better compression)

### Final Pipeline

```python
def render_and_save(view_path, data):
    """Full rendering pipeline for a dashboard view."""
    # 1. Create canvas at target resolution
    img = Image.new('L', (WIDTH, HEIGHT), 255)
    draw = ImageDraw.Draw(img)

    # 2. Render view content
    render_view(draw, view_path, data)

    # 3. Save as PNG for HTTP serving
    output_path = f'/tmp/dash_images/{view_path.replace("/", "_")}.png'
    img.save(output_path, format='PNG', optimize=True)

    return output_path
```

## Complete Example: Readiness View

```python
from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 1072, 1448

def render_readiness_view(readiness_data):
    img = Image.new('L', (WIDTH, HEIGHT), 255)
    draw = ImageDraw.Draw(img)

    # Fonts
    font_title = ImageFont.truetype('/System/Library/Fonts/Helvetica Bold.ttf', 56)
    font_huge = ImageFont.truetype('/System/Library/Fonts/Helvetica Bold.ttf', 140)
    font_body = ImageFont.truetype('/System/Library/Fonts/Helvetica.ttc', 36)
    font_small = ImageFont.truetype('/System/Library/Fonts/Menlo.ttc', 24)

    # Header
    draw.text((40, 40), "Training Readiness", font=font_title, fill=0)
    draw.line((40, 120, WIDTH - 40, 120), fill=0, width=3)

    # Hero score
    score = readiness_data.get('score', 0)
    draw.text((40, 160), str(score), font=font_huge, fill=0)
    draw.text((250, 220), "/ 100", font=font_body, fill=128)

    # Safety gate indicator
    gate = readiness_data.get('safety_gate', 'green')
    gate_x, gate_y = 450, 180
    if gate == 'green':
        draw.rectangle((gate_x, gate_y, gate_x + 80, gate_y + 80), fill=0)  # solid = good
    elif gate == 'yellow':
        draw.rectangle((gate_x, gate_y, gate_x + 80, gate_y + 80), outline=0, width=4)  # hollow = caution
    else:  # red
        draw.line((gate_x, gate_y, gate_x + 80, gate_y + 80), fill=0, width=6)
        draw.line((gate_x, gate_y + 80, gate_x + 80, gate_y), fill=0, width=6)  # X = stop

    # Factor breakdown
    y = 380
    factors = readiness_data.get('factors', [])
    for factor in factors:
        name = factor['name']
        value = factor['value']
        status = factor['status']  # 'good', 'caution', 'poor'

        draw.text((40, y), name, font=font_body, fill=0)
        draw.text((WIDTH - 200, y), str(value), font=font_body, fill=0)

        # Status bar
        bar_y = y + 50
        bar_w = 400
        fill_w = int(factor['percent'] / 100 * bar_w)
        draw.rectangle((40, bar_y, 40 + bar_w, bar_y + 12), fill=220, outline=0)
        draw.rectangle((40, bar_y, 40 + fill_w, bar_y + 12), fill=0)

        y += 100

    # Footer
    draw.line((40, HEIGHT - 120, WIDTH - 40, HEIGHT - 120), fill=0, width=2)
    draw.text((40, HEIGHT - 80), "Tap to refresh  ·  Back: Home", font=font_small, fill=128)

    return img
```

## Performance Notes

- **Render time on Mac:** < 100ms for a typical view (Pillow is fast on x86)
- **Image file size:** 1072×1448 8-bit grayscale PNG ≈ 200-500KB
- **HTTP serving:** Use Python's `http.server` or Flask/FastAPI; the Mac can serve the Kindle easily
- **Caching rendered images:** Cache the last rendered PNG per view path. Only re-render if data changed or TTL expired. See [view-protocol-spec.md](view-protocol-spec.md) for cache fields.

## Related Files

- [view-protocol-spec.md](view-protocol-spec.md) — How images are delivered to the Kindle
- [the agent-data-sources.md](the agent-data-sources.md) — What data feeds into the rendering
- [similar-projects.md](similar-projects.md) — How other projects handle rendering
