#!/usr/bin/env python3
"""
Route infographic v1 — 方案1: 南下暖色系/北上冷色系渐变发光线条
Midjourney-style vector infographic, 2400×2400, pure white bg.
"""
import matplotlib
matplotlib.use('Agg')

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.font_manager import FontProperties
from matplotlib.path import Path
import numpy as np
import os, copy

# ============================================================
# Output paths
# ============================================================
OUTPUT  = '/Users/bubu/.hermes/cache/documents/路线图_方案1.png'
DESKTOP = '/Users/bubu/Desktop/路线图_方案1.png'

# ============================================================
# Font
# ============================================================
FONT_PATH = '/System/Library/AssetsV2/com_apple_MobileAsset_Font7/857d6c90171c328a4892c1492291d34e401d7f25.asset/AssetData/SimSong.ttc'
FP = FontProperties(fname=FONT_PATH)
FP_BOLD = FontProperties(fname=FONT_PATH, weight='bold')
FP_L = FontProperties(fname=FONT_PATH, size=11)

def F(size=12):
    return FontProperties(fname=FONT_PATH, size=size)

# ============================================================
# Figure setup
# ============================================================
fig, ax = plt.subplots(1, 1, figsize=(24, 24), dpi=100)
ax.set_xlim(0, 2400)
ax.set_ylim(0, 2400)
ax.set_aspect('equal')
ax.axis('off')
fig.subplots_adjust(left=0, right=1, top=1, bottom=0)

# ============================================================
# Layout
# ============================================================
LAT_TOP, LAT_BOT = 40.5, 32.5
Y_TOP, Y_BOT = 220, 1780

def lat_to_y(lat):
    frac = (LAT_TOP - lat) / (LAT_TOP - LAT_BOT)
    return Y_TOP + frac * (Y_BOT - Y_TOP)

NODE_X = 380
RETURN_X = 430
LABEL_X = 540
TEMPLE_X = 480
LAT_LABEL_X = 70
D_MARKER_X = 290

# ============================================================
# Data
# ============================================================
cities = [
    ('北京', 40.0, ''),
    ('涞源', 39.35, '阁院寺'),
    ('邢台', 37.07, '开元寺'),
    ('平顺', 36.2, '天台庵·大云院·龙门寺'),
    ('长治', 36.2, '观音堂·法兴寺'),
    ('晋城', 35.5, '玉皇庙'),
    ('开封', 34.8, '山陕甘会馆·清明上河园'),
    ('洛阳', 34.62, '龙门石窟·二里头'),
    ('栾川', 33.73, '老君山'),
]

city_y = {}
for name, lat, attr in cities:
    y = lat_to_y(lat)
    if name == '平顺':
        y -= 30
    elif name == '长治':
        y += 30
    city_y[name] = y

route_order = ['北京', '涞源', '平顺', '长治', '晋城', '洛阳', '栾川', '开封', '邢台', '北京']

segments = [
    ('北京', '涞源', 1, '200km', '2.5h'),
    ('涞源', '平顺', 1, '280km', '3.5h'),
    ('平顺', '长治', 2, '60km', '1h'),
    ('长治', '晋城', 3, '80km', '1.5h'),
    ('晋城', '洛阳', 3, '130km', '2h'),
    ('洛阳', '栾川', 5, '160km', '2.5h'),
    ('栾川', '开封', 6, '350km', '4.5h'),
    ('开封', '邢台', 8, '350km', '4h'),
    ('邢台', '北京', 8, '360km', '4h'),
]

# Day scatter data
day_stops = {
    1: '北京→涞源→平顺',
    2: '平顺→长治',
    3: '长治→晋城→洛阳',
    4: '洛阳全天',
    5: '洛阳→栾川',
    6: '栾川→开封',
    7: '开封全天',
    8: '开封→邢台→北京',
}

# ============================================================
# Colors: southbound warm (red→orange→yellow), northbound cool (green→blue→purple)
# ============================================================
WARM = ['#E53935', '#EF6C00', '#F9A825', '#FDD835', '#FFB74D', '#FF8A65', '#E53935', '#C62828']
COOL = ['#43A047', '#2E7D32', '#1B5E20', '#00897B', '#039BE5', '#5C6BC0', '#7E57C2', '#8D6E63']

def hex2rgb(h):
    h = h.lstrip('#')
    return tuple(int(h[i:i+2], 16)/255 for i in (0, 2, 4))

def is_return(from_c, to_c):
    y1 = city_y.get(from_c, 0)
    y2 = city_y.get(to_c, 0)
    return y2 < y1

def get_seg_color(seg_idx, returning):
    """Get gradient color for a segment. Use warmer as seg goes south, cooler as goes north."""
    # Map segment index to a position in the gradient
    t = seg_idx / max(len(segments)-1, 1)
    if returning:
        # Northbound: cool gradient green→blue→purple
        c1 = hex2rgb('#43A047')
        c2 = hex2rgb('#5C6BC0')
        c3 = hex2rgb('#7E57C2')
        if t < 0.5:
            r, g, b = c1[0]+(c2[0]-c1[0])*t*2, c1[1]+(c2[1]-c1[1])*t*2, c1[2]+(c2[2]-c1[2])*t*2
        else:
            r, g, b = c2[0]+(c3[0]-c2[0])*(t-0.5)*2, c2[1]+(c3[1]-c2[1])*(t-0.5)*2, c2[2]+(c3[2]-c2[2])*(t-0.5)*2
    else:
        # Southbound: warm gradient red→orange→yellow
        c1 = hex2rgb('#C62828')
        c2 = hex2rgb('#EF6C00')
        c3 = hex2rgb('#F9A825')
        if t < 0.5:
            r, g, b = c1[0]+(c2[0]-c1[0])*t*2, c1[1]+(c2[1]-c1[1])*t*2, c1[2]+(c2[2]-c1[2])*t*2
        else:
            r, g, b = c2[0]+(c3[0]-c2[0])*(t-0.5)*2, c2[1]+(c3[1]-c2[1])*(t-0.5)*2, c2[2]+(c3[2]-c2[2])*(t-0.5)*2
    return (r, g, b)

def get_day_color(day):
    # soft muted color for day labels
    pal = ['#D32F2F','#E65100','#F57F17','#F9A825','#7CB342','#388E3C','#2E7D32','#1B5E20']
    return pal[day-1] if day <= len(pal) else '#666666'

# ============================================================
# Drawing helpers
# ============================================================

def draw_glowing_node(ax, x, y, color_rgb, radius=10):
    """Neon glow with multiple translucent halos."""
    r, g, b = color_rgb
    # Outer
    ax.add_patch(plt.Circle((x, y), radius*4.5,
        facecolor=(r, g, b, 0.04), edgecolor='none', zorder=18))
    # Mid outer
    ax.add_patch(plt.Circle((x, y), radius*2.8,
        facecolor=(r, g, b, 0.10), edgecolor='none', zorder=19))
    # Mid inner
    ax.add_patch(plt.Circle((x, y), radius*1.6,
        facecolor=(r, g, b, 0.25), edgecolor='none', zorder=20))
    # Core
    ax.add_patch(plt.Circle((x, y), radius*0.7,
        facecolor=(r, g, b, 1.0), edgecolor='white', linewidth=2.0, zorder=21))

def draw_glowing_line(ax, x1, y1, x2, y2, color_rgb, lw=4.0):
    """Glowing line with multi-layer transparent halo."""
    r, g, b = color_rgb
    for mult, alpha in [(5, 0.04), (3, 0.10), (1.8, 0.22)]:
        ax.plot([x1, x2], [y1, y2],
            color=(r, g, b, alpha), linewidth=lw*mult,
            solid_capstyle='round', zorder=8)
    ax.plot([x1, x2], [y1, y2],
        color=(r, g, b, 0.85), linewidth=lw,
        solid_capstyle='round', zorder=11)

def draw_gradient_line(ax, x1, y1, x2, y2, color_start, color_end, lw=4.0, n_seg=60):
    """Draw a visually smooth gradient line by approximating with many short segments."""
    xs = np.linspace(x1, x2, n_seg)
    ys = np.linspace(y1, y2, n_seg)
    for i in range(n_seg - 1):
        t = i / (n_seg - 1)
        r = color_start[0] + (color_end[0] - color_start[0]) * t
        g = color_start[1] + (color_end[1] - color_start[1]) * t
        b = color_start[2] + (color_end[2] - color_start[2]) * t
        color = (r, g, b)
        glow_alpha = 0.08 + t * 0.04
        for mult, alpha in [(4, 0.03), (2.5, 0.08), (1.5, 0.18)]:
            ax.plot([xs[i], xs[i+1]], [ys[i], ys[i+1]],
                color=(r, g, b, alpha*0.6 if mult>2 else alpha),
                linewidth=lw*mult, solid_capstyle='round', zorder=8)
        ax.plot([xs[i], xs[i+1]], [ys[i], ys[i+1]],
            color=(r, g, b, 0.85), linewidth=lw,
            solid_capstyle='round', zorder=11)

def draw_temple_icon(ax, x, y, size=12, color='#555555'):
    """Minimalist temple silhouette — elegant line-art pagoda."""
    lw = 1.8
    s = size

    # Roof: curved eaves trapezoid
    roof = Path([
        (x - s*0.90, y + s*0.30),
        (x - s*0.55, y + s*0.10),
        (x - s*0.30, y + s*0.40),
        (x,           y + s*1.10),
        (x + s*0.30, y + s*0.40),
        (x + s*0.55, y + s*0.10),
        (x + s*0.90, y + s*0.30),
    ])
    ax.add_patch(mpatches.PathPatch(roof, facecolor='none', edgecolor=color,
        linewidth=lw, joinstyle='round', capstyle='round', zorder=25))

    # Curved roof tips
    ax.plot([x - s*0.90, x + s*0.90], [y + s*0.30, y + s*0.30],
        color=color, linewidth=lw*0.8, solid_capstyle='round', zorder=25)

    # Ridge line ornament
    ax.plot([x - s*0.25, x + s*0.25], [y + s*0.65, y + s*0.65],
        color=color, linewidth=lw*0.5, solid_capstyle='round', zorder=25)

    # Body
    body = Path([
        (x - s*0.38, y + s*0.30),
        (x - s*0.38, y - s*0.02),
        (x + s*0.38, y - s*0.02),
        (x + s*0.38, y + s*0.30),
    ])
    ax.add_patch(mpatches.PathPatch(body, facecolor='none', edgecolor=color,
        linewidth=lw, joinstyle='round', capstyle='round', zorder=25))

    # Door arch
    door = Path([
        (x - s*0.12, y + s*0.10),
        (x - s*0.12, y - s*0.02),
        (x + s*0.12, y - s*0.02),
        (x + s*0.12, y + s*0.10),
        (x,           y + s*0.22),
        (x - s*0.12, y + s*0.10),
    ])
    ax.add_patch(mpatches.PathPatch(door, facecolor='none', edgecolor=color,
        linewidth=lw*0.6, joinstyle='round', zorder=26))

    # Base platform
    ax.plot([x - s*0.65, x + s*0.65], [y - s*0.02, y - s*0.02],
        color=color, linewidth=lw, solid_capstyle='round', zorder=25)

    # Decorative finial at roof peak
    ax.plot(x, y + s*1.10, 'o', color=color, markersize=2.5, zorder=26)

    # Small eave dots
    for tip_x in [x - s*0.90, x + s*0.90]:
        ax.plot(tip_x, y + s*0.30, 'o', color=color, markersize=1.8, zorder=26)

def draw_lat_line(ax, lat, y):
    """Grey dashed latitude line."""
    ax.plot([40, 2360], [y, y], color='#D5D5D5', linewidth=1.5,
        linestyle='--', dashes=(10, 7), zorder=1)
    kw = dict(va='center', ha='left', fontsize=15, color='#AAAAAA', zorder=2,
              fontproperties=F(15))
    ax.text(LAT_LABEL_X, y, f'{lat}°N', **kw)

def draw_dist_label(ax, x1, y1, x2, y2, dist, duration, day, side=1):
    """Distance label offset perpendicular from segment."""
    mx, my = (x1+x2)/2, (y1+y2)/2
    dx, dy = x2-x1, y2-y1
    length = np.hypot(dx, dy)
    if length < 5:
        return
    nx, ny = -dy/length, dx/length
    off = 55
    lx = mx + nx * off * side
    ly = my + ny * off * side
    lx = max(100, min(2350, lx))
    ly = max(Y_TOP-25, min(Y_BOT+25, ly))

    txt = f'{dist}  {duration}'
    color = get_day_color(day)
    kw = dict(va='center', ha='center', fontsize=12, color=color,
              zorder=15, alpha=0.85, fontproperties=F(12))
    # slight white background for readability
    ax.text(lx, ly, txt, **kw)

def draw_bottom_banner(ax):
    """Dark navy banner with dynasty timeline."""
    by0 = 1850
    bh = 450

    # Dark navy background with rounded top corners
    ax.add_patch(mpatches.FancyBboxPatch((0, by0), 2400, bh,
        boxstyle="round,pad=0,rounding_size=0",
        facecolor='#16202E', edgecolor='none', zorder=30))

    # Top accent line (subtle lighter stripe)
    ax.plot([0, 2400], [by0, by0], color='#2A3A50', linewidth=2.5, zorder=31)

    # Inner subtle decorative line
    ax.plot([80, 2320], [by0+8, by0+8], color='#1E2A3A', linewidth=1, zorder=31)

    dynasties = ['夏', '商', '辽', '唐', '五代', '宋', '元', '明', '清']
    # Arrow separator
    parts = []
    for i, d in enumerate(dynasties):
        if i > 0:
            parts.append(' → ')
        parts.append(d)
    timeline = ''.join(parts)

    fs = 28
    kw = dict(va='center', ha='center', fontsize=fs, color='#F0F0F0',
              zorder=32, alpha=0.95, fontproperties=F(fs))
    ax.text(1200, by0 + bh/2 + 8, timeline, **kw)

    # Subtitle
    kw2 = dict(va='top', ha='center', fontsize=13, color='#8899AA',
               zorder=32, fontproperties=F(13))
    ax.text(1200, by0 - 8, '─ 历史时间线 ─', **kw2)

    # Decorative small triangles framing
    for xx in [200, 2200]:
        tri = Path([(xx, by0+15), (xx+12, by0+15), (xx+6, by0+25)])
        ax.add_patch(mpatches.PathPatch(tri, facecolor='#2A3A50', edgecolor='none', zorder=32))

def draw_legend(ax):
    """D1-D8 legend in bottom-right area."""
    lx, ly0 = 1850, 1920  # just above banner

    # Background subtle rounded rect
    ax.add_patch(mpatches.FancyBboxPatch(
        (lx-20, ly0-15), 480, 240,
        boxstyle="round,pad=0,rounding_size=8",
        facecolor='#F8F8F8', edgecolor='#E0E0E0', linewidth=1.2, zorder=25))

    kw_h = dict(va='bottom', ha='left', fontsize=14, color='#444444',
                fontproperties=F(14), zorder=26)
    ax.text(lx, ly0 - 10, '图 例', **kw_h)

    day_labels = [
        'D1  北京→涞源→平顺',
        'D2  浊漳河谷·古建群',
        'D3  长治→晋城→洛阳',
        'D4  洛阳·龙门石窟',
        'D5  洛阳→老君山',
        'D6  栾川→开封',
        'D7  开封·古都巡礼',
        'D8  开封→邢台→北京',
    ]

    for i, label in enumerate(day_labels):
        col = i // 2
        row = i % 2
        xx = lx + col * 230
        yy = ly0 + 25 + row * 90

        pal = ['#D32F2F','#E65100','#F57F17','#F9A825','#7CB342','#388E3C','#2E7D32','#1B5E20']
        c = pal[i]

        # color swatch dot
        ax.add_patch(plt.Circle((xx + 10, yy + 5), 5,
            facecolor=c, edgecolor='none', zorder=27))

        kw = dict(va='center', ha='left', fontsize=11, color='#555555',
                  fontproperties=F(11), zorder=27)
        ax.text(xx + 22, yy + 5, label, **kw)


# ============================================================
# MAIN DRAWING
# ============================================================

# --- 1. Latitude guidelines ---
for lat in (40, 36, 34):
    draw_lat_line(ax, lat, lat_to_y(lat))

# --- 2. Categorize forward vs return segments ---
forward_segs = []
return_segs = []
for seg in segments:
    fc, tc, day, dist, dur = seg
    if is_return(fc, tc):
        return_segs.append(seg)
    else:
        forward_segs.append(seg)

# --- 3. Draw forward (southbound) route — gradient warm ---
for idx, (fc, tc, day, dist, dur) in enumerate(forward_segs):
    if fc not in city_y or tc not in city_y:
        continue
    y1, y2 = city_y[fc], city_y[tc]
    # Gradient from warmer to warmer as we go south
    t = idx / max(len(forward_segs)-1, 1)
    c_start = hex2rgb('#C62828')  # deep red
    c_mid   = hex2rgb('#EF6C00')  # orange
    c_end   = hex2rgb('#F9A825')  # amber
    if t < 0.5:
        cr1, cg1, cb1 = c_start[0]+(c_mid[0]-c_start[0])*t*2, c_start[1]+(c_mid[1]-c_start[1])*t*2, c_start[2]+(c_mid[2]-c_start[2])*t*2
        cr2, cg2, cb2 = c_mid[0]+(c_end[0]-c_mid[0])*t*2, c_mid[1]+(c_end[1]-c_mid[1])*t*2, c_mid[2]+(c_end[2]-c_mid[2])*t*2
    else:
        t2 = (t - 0.5)*2
        cr1, cg1, cb1 = c_mid[0]+(c_end[0]-c_mid[0])*t2, c_mid[1]+(c_end[1]-c_mid[1])*t2, c_mid[2]+(c_end[2]-c_mid[2])*t2
        cr2, cg2, cb2 = c_end[0], c_end[1], c_end[2]

    # Add a slight variation per segment for visual interest
    draw_gradient_line(ax, NODE_X, y1, NODE_X, y2,
        (cr1, cg1, cb1), (cr2, cg2, cb2), lw=4.0)

# --- 4. Draw return (northbound) route — gradient cool ---
for idx, (fc, tc, day, dist, dur) in enumerate(return_segs):
    if fc not in city_y or tc not in city_y:
        continue
    y1, y2 = city_y[fc], city_y[tc]
    t = idx / max(len(return_segs)-1, 1)
    c_start = hex2rgb('#388E3C')  # green
    c_mid   = hex2rgb('#039BE5')  # blue
    c_end   = hex2rgb('#5C6BC0')  # indigo
    if t < 0.5:
        cr1, cg1, cb1 = c_start[0]+(c_mid[0]-c_start[0])*t*2, c_start[1]+(c_mid[1]-c_start[1])*t*2, c_start[2]+(c_mid[2]-c_start[2])*t*2
        cr2, cg2, cb2 = c_mid[0]+(c_end[0]-c_mid[0])*t*2, c_mid[1]+(c_end[1]-c_mid[1])*t*2, c_mid[2]+(c_end[2]-c_mid[2])*t*2
    else:
        t2 = (t - 0.5)*2
        cr1, cg1, cb1 = c_mid[0]+(c_end[0]-c_mid[0])*t2, c_mid[1]+(c_end[1]-c_mid[1])*t2, c_mid[2]+(c_end[2]-c_mid[2])*t2
        cr2, cg2, cb2 = c_end[0], c_end[1], c_end[2]

    draw_gradient_line(ax, RETURN_X, y1, RETURN_X, y2,
        (cr1, cg1, cb1), (cr2, cg2, cb2), lw=4.0)

    # Horizontal connectors
    for endpoint, ep_y in [(fc, y1), (tc, y2)]:
        ax.plot([NODE_X+3, RETURN_X-3], [ep_y, ep_y],
            color=(cr1, cg1, cb1, 0.7), linewidth=2.0,
            solid_capstyle='round', zorder=10)

# --- 5. Distance labels ---
for seg in segments:
    fc, tc, day, dist, dur = seg
    if fc not in city_y or tc not in city_y:
        continue
    y1, y2 = city_y[fc], city_y[tc]
    ret = is_return(fc, tc)
    x = RETURN_X if ret else NODE_X
    side = -1 if ret else 1
    draw_dist_label(ax, x, y1, x, y2, dist, dur, day, side=side)

# --- 6. City nodes and labels ---
cities_sorted = sorted(cities, key=lambda c: c[1], reverse=True)

for name, lat, attr in cities_sorted:
    y = city_y[name]

    # Node color: gradient based on latitude
    t = (40.0 - lat) / (40.0 - 33.0)
    # warm to cool
    if name == '北京':
        rgb = hex2rgb('#333333')
    elif name == '邢台':
        rgb = hex2rgb('#E65100')
    elif name == '开封':
        rgb = hex2rgb('#F9A825')
    elif name == '洛阳':
        rgb = hex2rgb('#7CB342')
    elif name == '栾川':
        rgb = hex2rgb('#2E7D32')
    elif name == '平顺' or name == '长治':
        rgb = hex2rgb('#D84315')
    elif name == '晋城':
        rgb = hex2rgb('#F57F17')
    elif name == '涞源':
        rgb = hex2rgb('#BF360C')
    else:
        rgb = hex2rgb('#555555')

    draw_glowing_node(ax, NODE_X, y, rgb, radius=10)

    # City name (large, bold)
    kw = dict(va='center', ha='left', fontsize=22, color='#1a1a1a',
              zorder=15, weight='bold', fontproperties=F(22))
    ax.text(LABEL_X, y + 5, name, **kw)

    # Attractions (smaller, below)
    if attr:
        kw2 = dict(va='top', ha='left', fontsize=12, color='#777777',
                   zorder=14, fontproperties=F(12))
        ax.text(LABEL_X, y - 16, attr, **kw2)

    # Full-day markers
    full_day = {'洛阳': 'D4·全天', '开封': 'D7·全天'}
    if name in full_day:
        kw3 = dict(va='center', ha='left', fontsize=11, color='#999999',
                   zorder=14, style='italic', fontproperties=F(11))
        ax.text(LABEL_X + 280, y + 5, full_day[name], **kw3)

    # Temple icon
    draw_temple_icon(ax, TEMPLE_X, y + 6, size=11, color='#777777')

# --- 7. Day markers (D1-D8) on left ---
day_markers = {}
for fc, tc, day, dist, dur in segments:
    if fc not in city_y or tc not in city_y:
        continue
    mid = (city_y[fc] + city_y[tc]) / 2
    day_markers.setdefault(day, []).append(mid)

for day, ys in sorted(day_markers.items()):
    avg_y = np.mean(ys)
    color = get_day_color(day)
    # Background rounded label
    kw = dict(va='center', ha='center', fontsize=13, color=color,
              zorder=16, weight='bold', fontproperties=F(13))
    ax.text(D_MARKER_X, avg_y, f'D{day}', **kw)

# --- 8. Full-day highlight markers ---
for city_name in ['洛阳', '开封']:
    if city_name not in city_y:
        continue
    y = city_y[city_name]
    # subtle gold highlight bar
    ax.plot([NODE_X-32, NODE_X+32], [y, y],
        color='#E0C070', linewidth=6, solid_capstyle='round', zorder=5, alpha=0.5)

# --- 9. Bottom banner ---
draw_bottom_banner(ax)

# --- 10. Legend ---
draw_legend(ax)

# --- 11. Title ---
kw_t = dict(va='center', ha='center', fontsize=34, color='#111111',
            zorder=20, weight='bold', fontproperties=F(34))
ax.text(1200, 70, '晋豫古建自驾 · 八日路线图', **kw_t)

kw_s = dict(va='center', ha='center', fontsize=15, color='#888888',
            zorder=20, fontproperties=F(15))
ax.text(1200, 30, '山西 · 河南  ｜  古建筑与历史文化深度之旅', **kw_s)

# --- 12. Subtle vertical axis line ---
ax.plot([NODE_X, NODE_X], [Y_TOP-20, Y_BOT+20],
    color='#E8E8E8', linewidth=1, zorder=0)
ax.plot([RETURN_X, RETURN_X], [Y_TOP-20, Y_BOT+20],
    color='#F0F0F0', linewidth=0.8, zorder=0, linestyle=':', dashes=(5, 5))

# --- 13. Route direction arrow markers ---
# Small arrows on segments indicating direction
arrow_y_positions = {
    '北京→涞源': lat_to_y(39.7),
    '涞源→平顺': lat_to_y(37.7),
    '晋城→洛阳': lat_to_y(35.0),
    '洛阳→栾川': lat_to_y(34.2),
}
for seg_key, ay in arrow_y_positions.items():
    parts = seg_key.split('→')
    if len(parts) == 2 and parts[0] in city_y and parts[1] in city_y:
        ax.annotate('', xy=(NODE_X, ay+15), xytext=(NODE_X, ay-15),
            arrowprops=dict(arrowstyle='->', color='#AAAAAA', lw=1.2,
                          connectionstyle='arc3,rad=0'), zorder=5)

# ============================================================
# SAVE
# ============================================================
os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
fig.savefig(OUTPUT, dpi=100, facecolor='white', edgecolor='none')
print(f"[Save] Saved: {OUTPUT}")

os.makedirs(os.path.dirname(DESKTOP), exist_ok=True)
fig.savefig(DESKTOP, dpi=100, facecolor='white', edgecolor='none')
print(f"[Save] Desktop: {DESKTOP}")

plt.close(fig)
print("[Done] Complete!")
