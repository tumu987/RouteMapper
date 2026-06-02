#!/usr/bin/env python3
"""
Generate a stylized route infographic (not a real map).
晋豫古建自驾 · 八日路线图

Strict requirements:
- 2400x2400px square, pure white background
- No map features (no borders, no oceans, no graticules)
- Vertical axis = latitude, 40°N to 33°N top to bottom
- Three grey dashed latitude lines at 40°N, 36°N, 34°N
- Glowing neon city nodes with translucent halos
- Daily route segments D1-D8 in red/orange/green gradient
- Distance/duration labels on each segment
- Minimalist temple icons next to each city name
- Bottom dark-navy banner with history timeline
- Matplotlib only, no cartopy or map libraries
"""

import matplotlib
matplotlib.use('Agg')

import matplotlib.pyplot as plt
from matplotlib.path import Path
import matplotlib.patches as mpatches
from matplotlib.patches import PathPatch, FancyBboxPatch
import matplotlib.patheffects as pe
import numpy as np
import os, copy

# ============================================================
# Output paths
# ============================================================
OUTPUT = '/Users/bubu/.hermes/cache/documents/路线图_8天自驾.png'
DESKTOP = '/Users/bubu/Desktop/路线图_8天自驾.png'

# ============================================================
# Font detection (prefer PingFang SC for CJK)
# ============================================================
FONT_CANDIDATES = [
    '/System/Library/AssetsV2/com_apple_MobileAsset_Font7/3419f2a427639ad8c8e139149a287865a90fa17e.asset/AssetData/PingFang.ttc',
    '/System/Library/Fonts/STHeiti Medium.ttc',
    '/System/Library/Fonts/STHeiti Light.ttc',
    '/System/Library/Fonts/AppleSDGothicNeo.ttc',
    '/System/Library/AssetsV2/com_apple_MobileAsset_Font7/857d6c90171c328a4892c1492291d34e401d7f25.asset/AssetData/SimSong.ttc',
    '/System/Library/Fonts/Helvetica.ttc',
]

FONT_PATH = None
for fp in FONT_CANDIDATES:
    if os.path.exists(fp):
        FONT_PATH = fp
        break

if FONT_PATH:
    from matplotlib.font_manager import FontProperties
    FONT_PROP = FontProperties(fname=FONT_PATH)
    FONT_PROP_BOLD = FontProperties(fname=FONT_PATH, weight='bold')
    print(f"[Font] Using: {FONT_PATH}")
else:
    FONT_PROP = None
    FONT_PROP_BOLD = None
    print("[Font] No CJK font found, falling back to default")

# ============================================================
# Figure setup — exactly 2400×2400 pixels
# ============================================================
fig, ax = plt.subplots(1, 1, figsize=(24, 24), dpi=100)
ax.set_xlim(0, 2400)
ax.set_ylim(0, 2400)
ax.set_aspect('equal')
ax.axis('off')
fig.subplots_adjust(left=0, right=1, top=1, bottom=0)

# ============================================================
# Layout constants (data coordinates = pixels)
# ============================================================
LAT_TOP = 40.5
LAT_BOTTOM = 32.5
Y_TOP = 230
Y_BOTTOM = 1880

def lat_to_y(lat):
    """Convert latitude to Y pixel position (40.5°N→Y_TOP, 32.5°N→Y_BOTTOM)."""
    frac = (LAT_TOP - lat) / (LAT_TOP - LAT_BOTTOM)
    return Y_TOP + frac * (Y_BOTTOM - Y_TOP)

NODE_X = 380           # x for city nodes
RETURN_X = 420         # x for return-path segments (offset right)
LABEL_X = 530          # x for text labels
TEMPLE_X = 475         # x for temple icon midpoint
LAT_LABEL_X = 80       # x for latitude labels
D_MARKER_X = 330       # x for D1-D8 day markers

# ============================================================
# City data (name, lat, attractions)
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

# Y positions with offset for same-latitude cities
city_y = {}
for name, lat, attr in cities:
    y = lat_to_y(lat)
    if name == '平顺':
        y -= 28  # slightly higher
    elif name == '长治':
        y += 28  # slightly lower
    city_y[name] = y

# ============================================================
# Route data
# ============================================================
route_order = ['北京', '涞源', '平顺', '长治', '晋城', '洛阳', '栾川', '开封', '邢台', '北京']

# (from, to, day, distance_str, time_str)
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

# Full-day markers
full_day = {'洛阳': 'D4·全天', '开封': 'D7·全天'}

# ============================================================
# Color palette for D1-D8 (red → orange → green gradient)
# ============================================================
day_colors_rgb = [
    '#D32F2F',  # D1 - deep red
    '#EF6C00',  # D2 - orange
    '#F9A825',  # D3 - amber
    '#FDD835',  # D4 - yellow (no travel)
    '#7CB342',  # D5 - light green
    '#43A047',  # D6 - green
    '#2E7D32',  # D7 - dark green (no travel)
    '#1B5E20',  # D8 - forest green
]

def get_day_color(day):
    idx = day - 1
    return day_colors_rgb[idx] if idx < len(day_colors_rgb) else '#666666'

def hex_to_rgba(hex_color, alpha=1.0):
    h = hex_color.lstrip('#')
    r, g, b = int(h[0:2], 16)/255, int(h[2:4], 16)/255, int(h[4:6], 16)/255
    return (r, g, b, alpha)

# ============================================================
# Drawing helpers
# ============================================================

def draw_glowing_node(ax, x, y, color, radius=9):
    """Draw a glowing neon dot with multi-layer translucent halo."""
    # Outer glow (large, very transparent)
    ax.add_patch(plt.Circle((x, y), radius * 4.0,
                 facecolor=hex_to_rgba(color, 0.05), edgecolor='none', zorder=18))
    # Mid glow
    ax.add_patch(plt.Circle((x, y), radius * 2.4,
                 facecolor=hex_to_rgba(color, 0.12), edgecolor='none', zorder=19))
    # Inner glow
    ax.add_patch(plt.Circle((x, y), radius * 1.4,
                 facecolor=hex_to_rgba(color, 0.30), edgecolor='none', zorder=20))
    # Core
    ax.add_patch(plt.Circle((x, y), radius * 0.65,
                 facecolor=color, edgecolor='white', linewidth=1.8, zorder=21))


def draw_glowing_line(ax, x1, y1, x2, y2, color, lw=3.5):
    """Draw a glowing line between two points (multi-layer)."""
    for mult, alpha in [(5, 0.04), (3, 0.10), (1.8, 0.25)]:
        ax.plot([x1, x2], [y1, y2],
                color=hex_to_rgba(color, alpha),
                linewidth=lw * mult, solid_capstyle='round', zorder=8)
    # Core
    ax.plot([x1, x2], [y1, y2], color=color,
            linewidth=lw, solid_capstyle='round', zorder=11)


def is_return_segment(from_city, to_city):
    """Check if segment goes northward (return path)."""
    y1 = city_y.get(from_city, 0)
    y2 = city_y.get(to_city, 0)
    return y2 < y1  # going up = return


def draw_temple_icon(ax, x, y, size=10, color='#666666'):
    """Draw a minimalist temple / 古建筑 icon centered at (x, y) as bottom-center."""
    lw = 1.6
    s = size

    # Roof — trapezoid with slight overhang
    roof = Path([
        (x - s*0.85, y + s*0.30),
        (x - s*0.55, y + s*0.15),
        (x,           y + s*1.05),
        (x + s*0.55, y + s*0.15),
        (x + s*0.85, y + s*0.30),
    ])
    ax.add_patch(PathPatch(roof, facecolor='none', edgecolor=color,
                           linewidth=lw, joinstyle='round', capstyle='round', zorder=25))

    # Ridge line
    ax.plot([x - s*0.30, x + s*0.30], [y + s*0.60, y + s*0.60],
            color=color, linewidth=lw*0.6, solid_capstyle='round', zorder=25)

    # Body rectangle
    body = Path([
        (x - s*0.42, y + s*0.30),
        (x - s*0.42, y),
        (x + s*0.42, y),
        (x + s*0.42, y + s*0.30),
    ])
    ax.add_patch(PathPatch(body, facecolor='none', edgecolor=color,
                           linewidth=lw, joinstyle='round', capstyle='round', zorder=25))

    # Door
    door = Path([
        (x - s*0.10, y + s*0.08),
        (x - s*0.10, y),
        (x + s*0.10, y),
        (x + s*0.10, y + s*0.08),
    ])
    ax.add_patch(PathPatch(door, facecolor='none', edgecolor=color,
                           linewidth=lw*0.6, joinstyle='round', zorder=26))

    # Base platform
    ax.plot([x - s*0.70, x + s*0.70], [y, y],
            color=color, linewidth=lw, solid_capstyle='round', zorder=25)

    # Decorative roof tips (small dots at eaves)
    for tip_x in [x - s*0.85, x + s*0.85]:
        ax.plot(tip_x, y + s*0.30, 'o', color=color, markersize=1.8, zorder=26)


def draw_latitude_guideline(ax, lat, y):
    """Draw a dashed grey horizontal line with latitude label on the left."""
    ax.plot([50, 2350], [y, y], color='#D0D0D0', linewidth=1.5,
            linestyle='--', dashes=(8, 6), zorder=1)
    fs = 16
    kw = dict(va='center', ha='left', fontsize=fs, color='#999999', zorder=2)
    if FONT_PROP:
        kw['fontproperties'] = FontProperties(fname=FONT_PATH, size=fs)
    ax.text(LAT_LABEL_X, y, f'{lat}°N', **kw)


def draw_distance_label(ax, x1, y1, x2, y2, dist, duration, day, side=1):
    """Place a distance/duration label near the segment midpoint, offset perpendicularly."""
    mx, my = (x1 + x2) / 2, (y1 + y2) / 2
    dx, dy = x2 - x1, y2 - y1
    length = np.hypot(dx, dy)
    if length < 5:
        return  # too short to label

    # Perpendicular offset direction
    nx, ny = -dy / length, dx / length
    off = 50
    lx = mx + nx * off * side
    ly = my + ny * off * side

    # Clamp to screen
    lx = max(100, min(2300, lx))
    ly = max(Y_TOP - 20, min(Y_BOTTOM + 20, ly))

    txt = f'{dist}  {duration}'
    color = get_day_color(day)
    fs = 11
    kw = dict(va='center', ha='center', fontsize=fs, color=color,
              zorder=15, alpha=0.85)
    if FONT_PROP:
        kw['fontproperties'] = FontProperties(fname=FONT_PATH, size=fs)
    ax.text(lx, ly, txt, **kw)


def draw_bottom_banner(ax):
    """Dark navy banner with dynasty timeline."""
    banner_y0 = 1930
    banner_h = 400
    banner_color = '#1a2332'

    ax.add_patch(FancyBboxPatch((0, banner_y0), 2400, banner_h,
                 boxstyle="round,pad=0,rounding_size=0",
                 facecolor=banner_color, edgecolor='none', zorder=30))
    # Top accent line
    ax.plot([0, 2400], [banner_y0, banner_y0], color='#2a3a4a', linewidth=2, zorder=31)

    dynasties = ['夏', '商', '辽', '唐', '五代', '宋', '元', '明', '清']
    timeline = '  ←  '.join(dynasties)

    fs = 24
    kw = dict(va='center', ha='center', fontsize=fs, color='white',
              zorder=32, alpha=0.93)
    if FONT_PROP:
        kw['fontproperties'] = FontProperties(fname=FONT_PATH, size=fs)
    ax.text(1200, banner_y0 + banner_h / 2, timeline, **kw)

    # Label
    fs2 = 13
    kw2 = dict(va='bottom', ha='center', fontsize=fs2, color='#999999', zorder=5)
    if FONT_PROP:
        kw2['fontproperties'] = FontProperties(fname=FONT_PATH, size=fs2)
    ax.text(1200, banner_y0 - 10, '历史时间线', **kw2)


# ============================================================
# Main drawing
# ============================================================

# --- 1. Latitude guidelines ---
for lat in (40, 36, 34):
    draw_latitude_guideline(ax, lat, lat_to_y(lat))

# --- 2. Categorize segments: forward (south) vs return (north) ---
forward_segs = []
return_segs = []
for seg in segments:
    from_c, to_c, day, dist, dur = seg
    if is_return_segment(from_c, to_c):
        return_segs.append(seg)
    else:
        forward_segs.append(seg)

# --- 3. Draw forward-path route segments ---
for from_c, to_c, day, dist, dur in forward_segs:
    if from_c not in city_y or to_c not in city_y:
        continue
    y1, y2 = city_y[from_c], city_y[to_c]
    draw_glowing_line(ax, NODE_X, y1, NODE_X, y2, get_day_color(day), lw=3.5)

# --- 4. Draw return-path route segments (offset to the right) ---
for from_c, to_c, day, dist, dur in return_segs:
    if from_c not in city_y or to_c not in city_y:
        continue
    y1, y2 = city_y[from_c], city_y[to_c]
    draw_glowing_line(ax, RETURN_X, y1, RETURN_X, y2, get_day_color(day), lw=3.5)

    # Short horizontal connector from node to return path at each endpoint
    for endpoint, ep_y in [(from_c, y1), (to_c, y2)]:
        ax.plot([NODE_X + 3, RETURN_X - 3], [ep_y, ep_y],
                color=get_day_color(day), linewidth=1.8,
                solid_capstyle='round', zorder=10)

# --- 5. Distance labels ---
for seg in segments:
    from_c, to_c, day, dist, dur = seg
    if from_c not in city_y or to_c not in city_y:
        continue
    y1, y2 = city_y[from_c], city_y[to_c]
    ret = is_return_segment(from_c, to_c)
    x = RETURN_X if ret else NODE_X
    side = -1 if ret else 1
    draw_distance_label(ax, x, y1, x, y2, dist, dur, day, side=side)

# --- 6. City nodes and labels ---
cities_sorted = sorted(cities, key=lambda c: c[1], reverse=True)

for name, lat, attr in cities_sorted:
    y = city_y[name]

    # Determine node color: dark for most, colored for the endpoints
    node_color = '#2a2a2a'
    draw_glowing_node(ax, NODE_X, y, node_color, radius=9)

    # City name
    fs = 20
    kw = dict(va='center', ha='left', fontsize=fs, color='#1a1a1a', zorder=15, weight='bold')
    if FONT_PROP:
        kw['fontproperties'] = FontProperties(fname=FONT_PATH, size=fs)
    ax.text(LABEL_X, y + 4, name, **kw)

    # Attraction name (small, below)
    if attr:
        fs2 = 10.5
        kw2 = dict(va='top', ha='left', fontsize=fs2, color='#777777', zorder=14)
        if FONT_PROP:
            kw2['fontproperties'] = FontProperties(fname=FONT_PATH, size=fs2)
        ax.text(LABEL_X, y - 14, attr, **kw2)

    # Full-day marker
    if name in full_day:
        fs3 = 10
        kw3 = dict(va='center', ha='left', fontsize=fs3, color='#999999',
                   zorder=14, style='italic')
        if FONT_PROP:
            kw3['fontproperties'] = FontProperties(fname=FONT_PATH, size=fs3)
        ax.text(LABEL_X + 200, y + 4, full_day[name], **kw3)

    # Temple icon
    draw_temple_icon(ax, TEMPLE_X, y + 6, size=9, color='#666666')

# --- 7. Day markers (D1-D8 on the left) ---
day_markers = {}
for from_c, to_c, day, dist, dur in segments:
    if from_c not in city_y or to_c not in city_y:
        continue
    mid = (city_y[from_c] + city_y[to_c]) / 2
    day_markers.setdefault(day, []).append(mid)

for day, ys in sorted(day_markers.items()):
    avg_y = np.mean(ys)
    color = get_day_color(day)
    fs = 12
    kw = dict(va='center', ha='center', fontsize=fs, color=color,
              zorder=16, weight='bold')
    if FONT_PROP:
        kw['fontproperties'] = FontProperties(fname=FONT_PATH, size=fs)
    ax.text(D_MARKER_X, avg_y, f'D{day}', **kw)

# --- 8. Full-day horizontal highlight markers ---
for city_name in full_day:
    if city_name not in city_y:
        continue
    y = city_y[city_name]
    ax.plot([NODE_X - 28, NODE_X + 28], [y, y],
            color='#E0E0E0', linewidth=5, solid_capstyle='round', zorder=5)

# --- 9. Bottom timeline banner ---
draw_bottom_banner(ax)

# --- 10. Title ---
title_y = 70
fs_t = 34
kw_t = dict(va='center', ha='center', fontsize=fs_t, color='#111111',
            zorder=20, weight='bold')
if FONT_PROP:
    kw_t['fontproperties'] = FontProperties(fname=FONT_PATH, size=fs_t)
ax.text(1200, title_y, '晋豫古建自驾 · 八日路线图', **kw_t)

fs_s = 14
kw_s = dict(va='center', ha='center', fontsize=fs_s, color='#888888', zorder=20)
if FONT_PROP:
    kw_s['fontproperties'] = FontProperties(fname=FONT_PATH, size=fs_s)
ax.text(1200, title_y - 50, '山西 · 河南  ｜  古建筑与历史文化深度之旅', **kw_s)

# --- 11. Subtle vertical axis line ---
ax.plot([NODE_X, NODE_X], [Y_TOP - 20, Y_BOTTOM + 20],
        color='#EAEAEA', linewidth=1, zorder=0)
ax.plot([RETURN_X, RETURN_X], [Y_TOP - 20, Y_BOTTOM + 20],
        color='#F0F0F0', linewidth=0.8, zorder=0, linestyle=':', dashes=(3, 4))

# --- 12. Day color legend (upper right) ---
lx, ly0 = 2000, 220
if FONT_PROP:
    fpl = FontProperties(fname=FONT_PATH, size=10)
    ax.text(lx, ly0 - 18, '图例', fontproperties=fpl, color='#AAAAAA',
            va='bottom', ha='left', fontsize=10, zorder=5)
    for day in range(1, 9):
        ly = ly0 + day * 28
        c = get_day_color(day)
        ax.plot([lx, lx + 24], [ly, ly], color=c, linewidth=4,
                solid_capstyle='round', zorder=5)
        label = f'D{day}'
        if day == 4:
            label += ' 洛阳'
        elif day == 7:
            label += ' 开封'
        ax.text(lx + 34, ly, label, fontproperties=fpl, color='#777777',
                va='center', ha='left', fontsize=10, zorder=5)

# ============================================================
# Save
# ============================================================
os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
fig.savefig(OUTPUT, dpi=100, facecolor='white', edgecolor='none')
print(f"[Save] Output saved to: {OUTPUT}")

os.makedirs(os.path.dirname(DESKTOP), exist_ok=True)
fig.savefig(DESKTOP, dpi=100, facecolor='white', edgecolor='none')
print(f"[Save] Desktop copy: {DESKTOP}")

plt.close(fig)
print("[Done] All done!")
