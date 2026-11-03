"""
Generate EdgeMind official logo, SVG assets, and multi-resolution PNG icons.
Engineered specifically for Chrome extensions toolbar visibility and instant E-symbol recognition.

Generates:
- extension/edgemind/icons/edgemind-logo.svg
- extension/edgemind/icons/edgemind-lockup.svg
- extension/edgemind/icons/icon128.png
- extension/edgemind/icons/icon48.png
- extension/edgemind/icons/icon32.png
- extension/edgemind/icons/icon16.png
"""

from pathlib import Path
from PIL import Image, ImageDraw

ICONS_DIR = Path("extension/edgemind/icons")
ICONS_DIR.mkdir(parents=True, exist_ok=True)

# Master SVG Logo: Distinctive Geometric E Symbol
SVG_MASTER_LOGO = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128" width="100%" height="100%">
  <defs>
    <!-- Geometric E Gradient: Electric Blue to Radiant Violet -->
    <linearGradient id="em-e-grad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#38BDF8" />
      <stop offset="50%" stop-color="#818CF8" />
      <stop offset="100%" stop-color="#C084FC" />
    </linearGradient>

    <!-- Subtle Drop Shadow for depth -->
    <filter id="subtle-shadow" x="-10%" y="-10%" width="120%" height="120%">
      <feDropShadow dx="0" dy="2" stdDeviation="3" flood-color="#000000" flood-opacity="0.3" />
    </filter>
  </defs>

  <!-- Geometric Letter E Brand Symbol -->
  <path d="M 20 16 L 104 16 L 112 24 L 112 36 L 36 36 L 36 56 L 84 56 L 84 72 L 36 72 L 36 92 L 112 92 L 112 104 L 104 112 L 20 112 L 16 108 L 16 20 Z"
        fill="url(#em-e-grad)" filter="url(#subtle-shadow)" />
</svg>
"""

# Horizontal Wordmark Lockup
SVG_LOCKUP = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 280 64" width="280" height="64">
  <defs>
    <linearGradient id="lockup-e-grad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#38BDF8" />
      <stop offset="50%" stop-color="#818CF8" />
      <stop offset="100%" stop-color="#C084FC" />
    </linearGradient>
    <linearGradient id="text-title-grad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#FFFFFF" />
      <stop offset="100%" stop-color="#E2E8F0" />
    </linearGradient>
  </defs>

  <!-- Left Icon Mark: Geometric E -->
  <g transform="translate(6, 6) scale(0.40625)">
    <path d="M 20 16 L 104 16 L 112 24 L 112 36 L 36 36 L 36 56 L 84 56 L 84 72 L 36 72 L 36 92 L 112 92 L 112 104 L 104 112 L 20 112 L 16 108 L 16 20 Z"
          fill="url(#lockup-e-grad)" />
  </g>

  <!-- Wordmark Text -->
  <text x="68" y="34" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" 
        font-size="22" font-weight="800" letter-spacing="-0.03em" fill="url(#text-title-grad)">Edge<tspan fill="#38BDF8">Mind</tspan></text>
  
  <text x="69" y="48" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" 
        font-size="8.5" font-weight="700" letter-spacing="0.16em" fill="#94A3B8">ADAPTIVE TEST INTELLIGENCE</text>
</svg>
"""


def render_icon_bitmap(size: int) -> Image.Image:
    """
    Render high-resolution anti-aliased geometric E icon bitmap at exact target size.
    Uses super-sampling (1024 master canvas) with Lanczos filtering.
    Ensures solid vertical spine, three distinct horizontal strokes, deep open gaps,
    and balanced high-luminance colors that pop on both dark and light Chrome toolbars.
    """
    master = 1024
    u = master / 128.0

    # Geometric E polygon points in 128-grid
    pts = [
        (20, 16),
        (104, 16),
        (112, 24),
        (112, 36),
        (36, 36),
        (36, 56),
        (84, 56),
        (84, 72),
        (36, 72),
        (36, 92),
        (112, 92),
        (112, 104),
        (104, 112),
        (20, 112),
        (16, 108),
        (16, 20),
    ]
    scaled_pts = [(int(x * u), int(y * u)) for x, y in pts]

    # Gradient background
    img = Image.new("RGB", (master, master), (0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Balanced High-Luminance Palette:
    # Top: Electric Blue (#38BDF8 -> RGB 56, 189, 248) -> Lum ~160
    # Mid: Tech Indigo (#818CF8 -> RGB 129, 140, 248) -> Lum ~150
    # Bot: Radiant Violet (#C084FC -> RGB 192, 132, 252) -> Lum ~153
    c1 = (56, 189, 248)
    c2 = (129, 140, 248)
    c3 = (192, 132, 252)

    for y in range(master):
        t = y / float(master)
        if t < 0.5:
            t2 = t * 2
            r = int(c1[0] + (c2[0] - c1[0]) * t2)
            g = int(c1[1] + (c2[1] - c1[1]) * t2)
            b = int(c1[2] + (c2[2] - c1[2]) * t2)
        else:
            t2 = (t - 0.5) * 2
            r = int(c2[0] + (c3[0] - c2[0]) * t2)
            g = int(c2[1] + (c3[1] - c2[1]) * t2)
            b = int(c2[2] + (c3[2] - c2[2]) * t2)
        draw.line([(0, y), (master, y)], fill=(r, g, b))

    # Mask with geometric E polygon
    mask = Image.new("L", (master, master), 0)
    draw_m = ImageDraw.Draw(mask)
    draw_m.polygon(scaled_pts, fill=255)

    rgba = img.convert("RGBA")
    rgba.putalpha(mask)

    # Downscale smoothly using Lanczos
    return rgba.resize((size, size), Image.Resampling.LANCZOS)


def main():
    # Write SVG files
    (ICONS_DIR / "edgemind-logo.svg").write_text(SVG_MASTER_LOGO, encoding="utf-8")
    (ICONS_DIR / "edgemind-lockup.svg").write_text(SVG_LOCKUP, encoding="utf-8")
    print("Created SVG master assets.")

    # Render PNG icons
    sizes = [16, 24, 32, 48, 128]
    for sz in sizes:
        icon_img = render_icon_bitmap(sz)
        out_path = ICONS_DIR / f"icon{sz}.png"
        icon_img.save(out_path, format="PNG", optimize=True)
        print(f"Generated {out_path} ({sz}x{sz}, {out_path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
