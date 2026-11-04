"""Generate 'BachHoa705' logo concepts as hand-built SVG (no filters).

'705' is drawn from real glyph OUTLINES (extracted once from Jost Black --
a free/OFL "Futura-style" geometric sans, since actual Futura isn't freely
licensed for embedding -- via extract_glyphs.py -> jost_glyphs.json), baked
in as static <path> data. This keeps the font-substitution risk the same as
the old hand-drawn LED segments: zero, because no font needs to be installed
wherever this SVG is later rasterized to .ico/.icns. The neon glow is faked
with layered strokes (QtSvg = SVG Tiny, which drops <feGaussianBlur>), not
an SVG filter.
"""
import json
import os

OUT = os.path.dirname(os.path.abspath(__file__))

with open(os.path.join(OUT, "jost_glyphs.json"), encoding="utf-8") as _f:
    _GLYPHS = json.load(_f)

UPM = _GLYPHS["unitsPerEm"]
Y_MIN = _GLYPHS["overallYMin"]
Y_MAX = _GLYPHS["overallYMax"]
Y_SPAN = Y_MAX - Y_MIN

BADGE_SIZE = 512
BADGE_RX = round(BADGE_SIZE * 0.20)  # 20% corner radius, as requested
BADGE_INNER_RX = BADGE_RX - 8


def digits_block_width(height_px, tracking_frac=0.02):
    """Pixel width of the '705' block at the given visual height -- for
    callers that need to left/right-align it instead of centering."""
    scale = height_px / Y_SPAN
    tracking = tracking_frac * UPM
    widths = [_GLYPHS["glyphs"][c]["advanceWidth"] for c in "705"]
    return (sum(widths) + tracking * 2) * scale


def build_705_group(cx, cy, height_px, cyan="#5eead4", bright="#ecfeff", glow="#22d3ee",
                     tracking_frac=0.02):
    """'705' set in real Jost-Black glyph outlines, centered at (cx, cy),
    with the digits' combined visual height equal to height_px."""
    scale = height_px / Y_SPAN
    tracking = tracking_frac * UPM
    chars = "705"
    widths = [_GLYPHS["glyphs"][c]["advanceWidth"] for c in chars]
    total_units = sum(widths) + tracking * (len(chars) - 1)
    block_w = total_units * scale
    start_x = cx - block_w / 2
    y0 = (cy - height_px / 2) + Y_MAX * scale

    cursor = 0.0
    transforms = []
    for c, w in zip(chars, widths):
        gx = start_x + cursor * scale
        transforms.append((c, f"translate({gx:.2f},{y0:.2f}) scale({scale:.5f},{-scale:.5f})"))
        cursor += w + tracking

    def layer(fill, stroke, stroke_width, opacity):
        f = f'fill="{fill}"' if fill else 'fill="none"'
        s = f' stroke="{stroke}" stroke-width="{stroke_width:.2f}" stroke-linejoin="round"' if stroke else ""
        parts = []
        for c, t in transforms:
            d = _GLYPHS["glyphs"][c]["d"]
            parts.append(f'<path transform="{t}" d="{d}" {f}{s} opacity="{opacity}"/>')
        return "\n".join(parts)

    layers = [
        layer(None, glow, height_px * 0.09, 0.10),
        layer(None, glow, height_px * 0.045, 0.22),
        layer(cyan, bright, height_px * 0.010, 1.0),
    ]
    return "<g>" + "\n".join(layers) + "</g>"


def badge_svg(path_out, title):
    """Concept A: square app-icon badge, '705' centered, bold and large."""
    size = 512
    height_px = 154

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}" width="{size}" height="{size}">
  <title>{title}</title>
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#0b1b2b"/>
      <stop offset="1" stop-color="#071320"/>
    </linearGradient>
  </defs>
  <rect x="0" y="0" width="{size}" height="{size}" rx="{BADGE_RX}" fill="url(#bg)"/>
  <rect x="8" y="8" width="{size - 16}" height="{size - 16}" rx="{BADGE_INNER_RX}" fill="none" stroke="#1b3a52" stroke-width="3"/>
  {build_705_group(size / 2, size / 2, height_px)}
</svg>'''
    with open(path_out, "w", encoding="utf-8") as f:
        f.write(svg)


def _unit(dx, dy):
    length = (dx * dx + dy * dy) ** 0.5
    return (dx / length, dy / length) if length else (0.0, 0.0)


def rounded_polyline_path(points, radius, closed=False):
    """Build an SVG path 'd' string for a polyline/polygon with filleted
    (rounded) corners -- each sharp vertex is replaced by a short straight
    inset plus a quadratic curve through the original vertex."""
    n = len(points)
    corner_idxs = range(n) if closed else range(1, n - 1)
    before, after = {}, {}
    for i in corner_idxs:
        prev_p = points[(i - 1) % n]
        cur_p = points[i]
        next_p = points[(i + 1) % n]
        ux1, uy1 = _unit(cur_p[0] - prev_p[0], cur_p[1] - prev_p[1])
        ux2, uy2 = _unit(next_p[0] - cur_p[0], next_p[1] - cur_p[1])
        edge1 = ((cur_p[0] - prev_p[0]) ** 2 + (cur_p[1] - prev_p[1]) ** 2) ** 0.5
        edge2 = ((next_p[0] - cur_p[0]) ** 2 + (next_p[1] - cur_p[1]) ** 2) ** 0.5
        r = min(radius, edge1 * 0.5, edge2 * 0.5)
        before[i] = (cur_p[0] - ux1 * r, cur_p[1] - uy1 * r)
        after[i] = (cur_p[0] + ux2 * r, cur_p[1] + uy2 * r)

    if closed:
        start = after[0]
        d = f"M {start[0]:.2f} {start[1]:.2f} "
        for i in range(n):
            nxt = (i + 1) % n
            b = before[nxt]
            c = points[nxt]
            a = after[nxt]
            d += f"L {b[0]:.2f} {b[1]:.2f} Q {c[0]:.2f} {c[1]:.2f} {a[0]:.2f} {a[1]:.2f} "
        return d + "Z"

    d = f"M {points[0][0]:.2f} {points[0][1]:.2f} "
    for i in range(1, n - 1):
        b, c, a = before[i], points[i], after[i]
        d += f"L {b[0]:.2f} {b[1]:.2f} Q {c[0]:.2f} {c[1]:.2f} {a[0]:.2f} {a[1]:.2f} "
    return d + f"L {points[-1][0]:.2f} {points[-1][1]:.2f}"


def cart_glyph(ox, oy, scale=1.0, cyan="#5eead4", bright="#ecfeff", glow="#22d3ee"):
    """Shopping-cart silhouette (trapezoid basket + handle + 2 wheels),
    drawn as stroked paths only -- no fonts, no filters, same layered-glow
    technique as the digits. Corners are filleted (not just stroke-linejoin
    round) per feedback that the sharp corners read as too hard-edged."""
    # local coordinate box, roughly 190 x 140
    handle_pts = [(0, 8), (20, 8), (38, 32)]
    basket_pts = [(38, 32), (168, 32), (150, 92), (64, 92)]
    handle_path = rounded_polyline_path(handle_pts, radius=9, closed=False)
    basket_path = rounded_polyline_path(basket_pts, radius=16, closed=True)
    path = (
        f"{handle_path} "
        f"{basket_path} "
        "M 50 62 L 158 62 "                     # mid cross-bar (basket texture)
        "M 70 92 L 76 104 "                     # left leg
        "M 144 92 L 138 104"                    # right leg
    )
    wheels = (
        f'<circle cx="76" cy="116" r="12"/>'
        f'<circle cx="138" cy="116" r="12"/>'
    )
    g_open = f'<g transform="translate({ox},{oy}) scale({scale})">'
    layers = [
        f'<path d="{path}" fill="none" stroke="{glow}" stroke-width="20" '
        f'stroke-linejoin="round" stroke-linecap="round" opacity="0.10"/>'
        f'<g fill="none" stroke="{glow}" stroke-width="20" opacity="0.10">{wheels}</g>',

        f'<path d="{path}" fill="none" stroke="{glow}" stroke-width="10" '
        f'stroke-linejoin="round" stroke-linecap="round" opacity="0.22"/>'
        f'<g fill="none" stroke="{glow}" stroke-width="10" opacity="0.22">{wheels}</g>',

        f'<path d="{path}" fill="none" stroke="{bright}" stroke-width="9" '
        f'stroke-linejoin="round" stroke-linecap="round" opacity="1.0"/>'
        f'<g fill="{cyan}" stroke="{bright}" stroke-width="2">{wheels}</g>',
    ]
    return g_open + "\n".join(layers) + "</g>"


def badge_svg_cart(path_out, title):
    """Concept B v2: bigger, bolder '705' riding on a shopping-cart glyph."""
    size = BADGE_SIZE
    digit_h = 140

    cart_scale = 1.25
    cart_w, cart_h = 190 * cart_scale, 140 * cart_scale

    gap = 40
    total_h = digit_h + gap + cart_h
    top = (size - total_h) / 2
    digit_cy = top + digit_h / 2

    cart_oy = top + digit_h + gap
    cart_ox = (size - cart_w) / 2

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}" width="{size}" height="{size}">
  <title>{title}</title>
  <defs>
    <linearGradient id="bg2" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#0b1b2b"/>
      <stop offset="1" stop-color="#071320"/>
    </linearGradient>
  </defs>
  <rect x="0" y="0" width="{size}" height="{size}" rx="{BADGE_RX}" fill="url(#bg2)"/>
  <rect x="8" y="8" width="{size - 16}" height="{size - 16}" rx="{BADGE_INNER_RX}" fill="none" stroke="#1b3a52" stroke-width="3"/>
  {build_705_group(size / 2, digit_cy, digit_h)}
  {cart_glyph(cart_ox, cart_oy, cart_scale)}
</svg>'''
    with open(path_out, "w", encoding="utf-8") as f:
        f.write(svg)


def badge_svg_scan(path_out, title):
    """Concept C: digits + a thin 'scan line' + two small 'robot eye' dots."""
    size = 512
    height_px = 147
    cy = size / 2 - 30
    group_w = digits_block_width(height_px)
    ox = (size - group_w) / 2

    line_y = cy + height_px / 2 + 56
    line_x0 = ox - 10
    line_x1 = ox + group_w + 10

    extras = f'''
    <line x1="{line_x0}" y1="{line_y}" x2="{line_x1}" y2="{line_y}" stroke="#22d3ee" stroke-width="10" opacity="0.12" stroke-linecap="round"/>
    <line x1="{line_x0}" y1="{line_y}" x2="{line_x1}" y2="{line_y}" stroke="#5eead4" stroke-width="3" opacity="0.9" stroke-linecap="round"/>
    <circle cx="{ox + 8}" cy="{line_y}" r="6" fill="#ecfeff"/>
    <circle cx="{line_x1 - 8}" cy="{line_y}" r="6" fill="#ecfeff"/>
    '''

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}" width="{size}" height="{size}">
  <title>{title}</title>
  <defs>
    <linearGradient id="bg3" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#0b1b2b"/>
      <stop offset="1" stop-color="#071320"/>
    </linearGradient>
  </defs>
  <rect x="0" y="0" width="{size}" height="{size}" rx="{BADGE_RX}" fill="url(#bg3)"/>
  <rect x="8" y="8" width="{size - 16}" height="{size - 16}" rx="{BADGE_INNER_RX}" fill="none" stroke="#1b3a52" stroke-width="3"/>
  {build_705_group(size / 2, cy, height_px)}
  {extras}
</svg>'''
    with open(path_out, "w", encoding="utf-8") as f:
        f.write(svg)


def wordmark_svg(path_out):
    """Horizontal lockup for README/web banner: '705' mark + 'Bách Hóa' text.
    The 'Bách Hóa' text is fine as live <text> here (not rasterized to a
    tiny .ico), browser font fallback handles Vietnamese diacritics."""
    w, h = 900, 260
    height_px = 150
    group_w = digits_block_width(height_px)
    ox = 40
    cx = ox + group_w / 2
    cy = h / 2

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">
  <defs>
    <linearGradient id="bgw" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#0b1b2b"/>
      <stop offset="1" stop-color="#0a2234"/>
    </linearGradient>
  </defs>
  <rect x="0" y="0" width="{w}" height="{h}" rx="28" fill="url(#bgw)"/>
  {build_705_group(cx, cy, height_px)}
  <text x="{ox + group_w + 36}" y="{h / 2 + 18}" font-family="Segoe UI, Arial, sans-serif" font-weight="700"
        font-size="64" fill="#ecfeff" letter-spacing="1">Bách Hóa</text>
  <text x="{ox + group_w + 36}" y="{h / 2 + 18}" font-family="Segoe UI, Arial, sans-serif" font-weight="700"
        font-size="64" fill="none" stroke="#22d3ee" stroke-width="10" opacity="0.08" letter-spacing="1">Bách Hóa</text>
</svg>'''
    with open(path_out, "w", encoding="utf-8") as f:
        f.write(svg)


if __name__ == "__main__":
    badge_svg(os.path.join(OUT, "concept_a_badge.svg"), "BachHoa705 - Concept A")
    badge_svg_cart(os.path.join(OUT, "concept_b_cart.svg"), "BachHoa705 - Concept B (cart)")
    badge_svg_scan(os.path.join(OUT, "concept_c_scan.svg"), "BachHoa705 - Concept C")
    wordmark_svg(os.path.join(OUT, "wordmark.svg"))
    print("done")
