#!/usr/bin/env python3
"""
路线图 v4 — Cartopy 省界 + 城市名在圆圈内 + 大字体区分
"""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.font_manager import FontProperties
from matplotlib.path import Path
import cartopy.crs as ccrs
import cartopy.feature as cfeature
from cartopy.io.shapereader import natural_earth
import numpy as np
import os

# ============================================================
# Output
# ============================================================
OUTPUT  = '/Users/bubu/.hermes/cache/documents/路线图_省界精致版.png'
DESKTOP = '/Users/bubu/Desktop/路线图_省界精致版.png'

# ============================================================
# Font
# ============================================================
FONT_CANDIDATES = [
    '/System/Library/AssetsV2/com_apple_MobileAsset_Font7/857d6c90171c328a4892c1492291d34e401d7f25.asset/AssetData/SimSong.ttc',
    '/System/Library/Fonts/STHeiti Medium.ttc',
    '/System/Library/Fonts/PingFang.ttc',
    '/System/Library/Fonts/AppleSDGothicNeo.ttc',
]
FONT_PATH = None
for fp in FONT_CANDIDATES:
    if os.path.exists(fp):
        FONT_PATH = fp
        break
if FONT_PATH:
    print(f"[Font] Using: {FONT_PATH}")
else:
    FONT_PATH = '/System/Library/Fonts/Helvetica.ttc'
    print("[Font] Fallback to Helvetica")

def F(size=12, bold=False):
    return FontProperties(fname=FONT_PATH, size=size, weight='bold' if bold else 'normal')

# ============================================================
# City data (name, lat, lon, attractions, province)
# ============================================================
cities_data = [
    ('北京', 39.91, 116.40, '', '冀'),
    ('涞源', 39.35, 114.68, '阁院寺', '冀'),
    ('邢台', 37.07, 114.50, '开元寺', '冀'),
    ('平顺', 36.20, 113.43, '天台庵·大云院·龙门寺', '晋'),
    ('长治', 36.20, 113.12, '观音堂·法兴寺', '晋'),
    ('晋城', 35.50, 112.85, '玉皇庙', '晋'),
    ('洛阳', 34.62, 112.45, '龙门石窟·二里头', '豫'),
    ('栾川', 33.73, 111.62, '老君山', '豫'),
    ('开封', 34.80, 114.30, '山陕甘会馆·清明上河园', '豫'),
]

# Route order
route_cities = ['北京', '涞源', '平顺', '长治', '晋城', '洛阳', '栾川', '开封', '邢台', '北京']

# Segments: (from, to, day, dist_km, time_h, dist_str, time_str)
segments = [
    ('北京', '涞源', 1, 200, 2.5, '200km', '2.5h'),
    ('涞源', '平顺', 1, 280, 3.5, '280km', '3.5h'),
    ('平顺', '长治', 2, 60, 1.0, '60km', '1h'),
    ('长治', '晋城', 3, 80, 1.5, '80km', '1.5h'),
    ('晋城', '洛阳', 3, 130, 2.0, '130km', '2h'),
    ('洛阳', '栾川', 5, 160, 2.5, '160km', '2.5h'),
    ('栾川', '开封', 6, 350, 4.5, '350km', '4.5h'),
    ('开封', '邢台', 8, 350, 4.0, '350km', '4h'),
    ('邢台', '北京', 8, 360, 4.0, '360km', '4h'),
]

# Rest days
rest_days = {4: ('洛阳', 'D4·洛阳全天'), 7: ('开封', 'D7·开封全天')}

# Province colors
PROV_COLORS = {
    '冀': '#2E7D32',   # Hebei - green
    '晋': '#1565C0',   # Shanxi - blue
    '豫': '#C62828',   # Henan - red
}

# Node sizes by province
PROV_NODE_RADIUS = {
    '冀': 24,
    '晋': 24,
    '豫': 24,
}

# ============================================================
# Map setup
# ============================================================
lon_min, lon_max = 110.5, 117.5
lat_min, lat_max = 32.8, 41.0

fig = plt.figure(figsize=(20, 24), dpi=150)
fig.patch.set_facecolor('white')

# Map axes with good projection
ax = fig.add_axes([0.05, 0.05, 0.90, 0.90], projection=ccrs.PlateCarree())
ax.set_extent([lon_min, lon_max, lat_min, lat_max], crs=ccrs.PlateCarree())

# --- Province boundaries ---
try:
    # Try to get province boundaries from Natural Earth
    provinces = cfeature.NaturalEarthFeature(
        category='cultural',
        name='admin_1_states_provinces',
        scale='50m',
        facecolor='none',
    )
    # Filter to only our provinces
    import cartopy.io.shapereader as shpreader
    reader = shpreader.Reader(natural_earth(resolution='50m', category='cultural', name='admin_1_states_provinces'))
    records = list(reader.records())

    prov_names = ['Hebei', 'Shanxi', 'Henan']
    for record in records:
        name = record.attributes.get('name', '')
        if name in prov_names:
            geom = record.geometry
            ax.add_geometries([geom], ccrs.PlateCarree(),
                facecolor='none',
                edgecolor=PROV_COLORS.get({
                    'Hebei': '冀', 'Shanxi': '晋', 'Henan': '豫',
                }.get(name, ''), '#888888'),
                linewidth=2.5,
                alpha=0.8,
                zorder=3)

    print("[Map] Province boundaries loaded")
except Exception as e:
    print(f"[Map] Province boundary error: {e}")

# --- Map features ---
ax.add_feature(cfeature.LAND, facecolor='#F5F0E8', zorder=0)
ax.add_feature(cfeature.OCEAN, facecolor='#DCE5F0', zorder=0)
ax.add_feature(cfeature.LAKES, facecolor='#D6E4F0', edgecolor='#B0C4DE', linewidth=1, zorder=1)
ax.add_feature(cfeature.RIVERS, facecolor='none', edgecolor='#B0C4DE', linewidth=0.8, zorder=1)
ax.add_feature(cfeature.COASTLINE, edgecolor='#888888', linewidth=1.2, zorder=2)
ax.add_feature(cfeature.BORDERS, edgecolor='#AAAAAA', linewidth=0.8, linestyle=':', zorder=2)

# Gridlines
gl = ax.gridlines(draw_labels=True, linestyle='--', color='#CCCCCC', linewidth=0.5, alpha=0.5)
gl.top_labels = False
gl.right_labels = False
gl.xlabel_style = {'size': 10, 'color': '#888888'}
gl.ylabel_style = {'size': 10, 'color': '#888888'}

# ============================================================
# Data lookups
# ============================================================
city_lookup = {c[0]: c for c in cities_data}
city_coords = {c[0]: (c[2], c[1]) for c in cities_data}  # lon, lat

def is_return_seg(from_c, to_c):
    """Northward = return"""
    _, lat1 = city_coords[from_c]
    _, lat2 = city_coords[to_c]
    return lat2 < lat1

# ============================================================
# Day colors
# ============================================================
DAY_COLORS = ['#D32F2F', '#E65100', '#F9A825', '#FDD835', '#7CB342', '#388E3C', '#2E7D32', '#1B5E20']

def get_day_color(day):
    return DAY_COLORS[day - 1] if 1 <= day <= 8 else '#666666'

# Helper to convert data coords to figure display coords
def get_xy(name):
    lon, lat = city_coords[name]
    return ax.projection.transform_point(lon, lat, ccrs.PlateCarree())

# ============================================================
# Draw route segments
# ============================================================
# Separate forward and return
forward_segs = []
return_segs = []
for seg in segments:
    fc, tc, day, d_km, d_h, dist_s, time_s = seg
    if is_return_seg(fc, tc):
        return_segs.append(seg)
    else:
        forward_segs.append(seg)

def draw_path(ax, x1, y1, x2, y2, color, lw=4.0, zorder=10):
    """Draw a segment with glow effect."""
    # Glow layers
    for mult, alpha in [(4, 0.08), (2.5, 0.15), (1.5, 0.30)]:
        ax.plot([x1, x2], [y1, y2],
            color=matplotlib.colors.to_rgba(color, alpha),
            linewidth=lw * mult,
            solid_capstyle='round',
            transform=ccrs.PlateCarree(),
            zorder=zorder - 1)
    # Core line
    ax.plot([x1, x2], [y1, y2],
        color=color,
        linewidth=lw,
        solid_capstyle='round',
        transform=ccrs.PlateCarree(),
        zorder=zorder)

for seg in forward_segs:
    fc, tc, day, d_km, d_h, dist_s, time_s = seg
    x1, y1 = city_coords[fc]
    x2, y2 = city_coords[tc]
    color = get_day_color(day)
    draw_path(ax, x1, y1, x2, y2, color, lw=4.0, zorder=10)

for seg in return_segs:
    fc, tc, day, d_km, d_h, dist_s, time_s = seg
    x1, y1 = city_coords[fc]
    x2, y2 = city_coords[tc]
    color = get_day_color(day)
    draw_path(ax, x1, y1, x2, y2, color, lw=4.0, zorder=10)

# ============================================================
# Draw city nodes with names INSIDE
# ============================================================
for name, lat, lon, attr, prov in cities_data:
    x, y = lon, lat
    node_color = PROV_COLORS[prov]
    radius = PROV_NODE_RADIUS[prov]

    # Outer glow
    for mult, alpha in [(3.0, 0.10), (2.0, 0.20), (1.3, 0.40)]:
        ax.add_patch(plt.Circle(
            (x, y), radius * mult / 111.0,  # approximate degree conversion
            facecolor=matplotlib.colors.to_rgba(node_color, alpha),
            edgecolor='none',
            transform=ccrs.PlateCarree(),
            zorder=15))

    # Main circle (white fill with colored border)
    ax.add_patch(plt.Circle(
        (x, y), radius / 111.0,
        facecolor='white',
        edgecolor=node_color,
        linewidth=3.0,
        transform=ccrs.PlateCarree(),
        zorder=17))

    # Inner subtle accent ring
    ax.add_patch(plt.Circle(
        (x, y), radius * 0.85 / 111.0,
        facecolor='none',
        edgecolor=matplotlib.colors.to_rgba(node_color, 0.3),
        linewidth=1.0,
        transform=ccrs.PlateCarree(),
        zorder=18))

    # City name INSIDE the circle
    # For 2-char names (北京, 邢台, 长治...), display side by side
    # For 1-char (none here), just the name
    fs_city = 14 if len(name) <= 2 else 12
    ax.text(x, y, name,
        fontproperties=F(fs_city, bold=True),
        color=node_color,
        ha='center', va='center',
        transform=ccrs.PlateCarree(),
        zorder=20)

    # Attraction name (below the node with background box)
    if attr:
        y_attr = y - radius / 111.0 - 0.15
        kw_attr = dict(
            fontproperties=F(14, bold=True),
            color='#5D4037',
            ha='center', va='top',
            transform=ccrs.PlateCarree(),
            zorder=16,
        )
        # White background for readability
        ax.text(x, y_attr, attr,
            fontproperties=F(14, bold=True),
            color='#5D4037',
            ha='center', va='top',
            transform=ccrs.PlateCarree(),
            zorder=16)

# ============================================================
# Day / Distance / Time labels along segments
# ============================================================
for seg in segments:
    fc, tc, day, d_km, d_h, dist_s, time_s = seg
    x1, y1 = city_coords[fc]
    x2, y2 = city_coords[tc]

    # Midpoint
    mx, my = (x1 + x2) / 2, (y1 + y2) / 2

    ret = is_return_seg(fc, tc)
    # Offset perpendicular
    dx, dy = x2 - x1, y2 - y1
    length = np.hypot(dx, dy)
    if length > 0.5:
        nx, ny = -dy / length, dx / length
    else:
        nx, ny = 0.3, 0.3

    side = -1 if ret else 1
    off = 0.25  # degree offset
    lx = mx + nx * off * side
    ly = my + ny * off * side

    day_color = get_day_color(day)

    # Day label (large, colored background)
    kw_day = dict(
        fontproperties=F(22, bold=True),
        color=day_color,
        ha='center', va='bottom',
        transform=ccrs.PlateCarree(),
        zorder=18,
    )
    ax.text(lx, ly + 0.08, f'D{day}', **kw_day)

    # Distance (blue, bold) - slightly offset below day
    kw_dist = dict(
        fontproperties=F(18, bold=True),
        color='#1565C0',
        ha='center', va='top',
        transform=ccrs.PlateCarree(),
        zorder=18,
    )
    ax.text(lx, ly - 0.02, dist_s, **kw_dist)

    # Time (orange, bold) - below distance
    kw_time = dict(
        fontproperties=F(16, bold=True),
        color='#E65100',
        ha='center', va='top',
        transform=ccrs.PlateCarree(),
        zorder=18,
    )
    ax.text(lx, ly - 0.12, time_s, **kw_time)

# ============================================================
# Rest day markers
# ============================================================
for day, (city, label) in rest_days.items():
    x, y = city_coords[city]
    ly = y - 0.65
    kw_rest = dict(
        fontproperties=F(18, bold=True),
        color=get_day_color(day),
        ha='center', va='top',
        transform=ccrs.PlateCarree(),
        zorder=16,
    )
    # Semi-transparent white background
    ax.text(x, ly, label, **kw_rest)

# ============================================================
# Title
# ============================================================
kw_title = dict(
    fontproperties=F(32, bold=True),
    color='#222222',
    ha='center', va='center',
    zorder=30,
)
fig.text(0.5, 0.97, '晋豫古建自驾 · 八日路线图', **kw_title)

kw_sub = dict(
    fontproperties=F(16),
    color='#888888',
    ha='center', va='center',
    zorder=30,
)
fig.text(0.5, 0.945, '北京 → 浊漳河谷 → 老君山 → 开封  ｜  全程约2300km', **kw_sub)

# ============================================================
# Legend
# ============================================================
legend_x, legend_y = 0.78, 0.82

# Province legend
prov_items = [
    ('冀 · 河北', '#2E7D32'),
    ('晋 · 山西', '#1565C0'),
    ('豫 · 河南', '#C62828'),
]
for i, (label, color) in enumerate(prov_items):
    y_pos = legend_y - i * 0.035
    fig.add_artist(plt.Circle((legend_x - 0.002, y_pos), 0.015,
        facecolor='white', edgecolor=color, linewidth=2.5,
        transform=fig.transFigure, zorder=30))
    fig.text(legend_x + 0.025, y_pos, label,
        fontproperties=F(12, bold=True), color=color,
        ha='left', va='center', zorder=30)

# Distance/Time legend
fig.text(legend_x, legend_y - 0.12, '图例',
    fontproperties=F(14, bold=True), color='#555555',
    ha='left', va='center', zorder=30)

legend_items = [
    ('D1-D8  天次', DAY_COLORS[0]),
    ('距离', '#1565C0'),
    ('车程时间', '#E65100'),
    ('景点名称', '#5D4037'),
]
for i, (lbl, clr) in enumerate(legend_items):
    y_pos = legend_y - 0.155 - i * 0.03
    fig.text(legend_x + 0.025, y_pos, lbl,
        fontproperties=F(11, bold=True), color=clr,
        ha='left', va='center', zorder=30)
    # Colored dot
    fig.add_artist(plt.Circle((legend_x, y_pos), 0.008,
        facecolor=clr, edgecolor='none',
        transform=fig.transFigure, zorder=30))

# ============================================================
# Save
# ============================================================
print("[Save] Saving...")
fig.savefig(OUTPUT, dpi=150, facecolor='white', edgecolor='none', bbox_inches='tight')
print(f"[Save] -> {OUTPUT}")

import shutil
shutil.copy2(OUTPUT, DESKTOP)
print(f"[Save] -> {DESKTOP}")

plt.close(fig)
print("[Done]")
