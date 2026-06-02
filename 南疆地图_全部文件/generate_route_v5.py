#!/usr/bin/env python3
"""
路线图 v5 — 省界 + 城市名在圆圈内 + 大字加粗清晰区分
"""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.colors as mcolors
from matplotlib.font_manager import FontProperties
import cartopy.crs as ccrs
import cartopy.feature as cfeature
from cartopy.io.shapereader import natural_earth
import cartopy.io.shapereader as shpreader
import numpy as np
import matplotlib.patheffects as pe
import os, shutil

# ============================================================
# Output
# ============================================================
OUTPUT  = '/Users/bubu/.hermes/cache/documents/路线图_省界精致版.png'
DESKTOP = '/Users/bubu/Desktop/路线图_省界精致版.png'

# ============================================================
# Font
# ============================================================
FONT_PATH = None
for fp in [
    '/System/Library/Fonts/STHeiti Medium.ttc',
    '/System/Library/AssetsV2/com_apple_MobileAsset_Font7/f7f6b250e97c182e68ac53a2b359ec44548878b9.asset/AssetData/Lantinghei.ttc',
    '/System/Library/AssetsV2/com_apple_MobileAsset_Font7/62032b9b64a0e3a9121c50aeb2ed794e3e2c201f.asset/AssetData/Hei.ttf',
    '/System/Library/Fonts/PingFang.ttc',
]:
    if os.path.exists(fp):
        FONT_PATH = fp
        break
if not FONT_PATH:
    FONT_PATH = '/System/Library/Fonts/Helvetica.ttc'

def F(size=12, bold=False):
    return FontProperties(fname=FONT_PATH, size=size, weight='bold' if bold else 'normal')

# 所有文字统一加白色描边（避免被线路/底色干扰）
TEXT_STROKE = [pe.withStroke(linewidth=3, foreground='white')]

# ============================================================
# Data
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
route = ['北京','涞源','平顺','长治','晋城','洛阳','栾川','开封','邢台','北京']

segments = [
    ('北京','涞源',1, '200km','2.5小时'),
    ('涞源','平顺',1, '280km','3.5小时'),
    ('平顺','长治',2, '60km','1小时'),
    ('长治','晋城',3, '80km','1.5小时'),
    ('晋城','洛阳',3, '130km','2小时'),
    ('洛阳','栾川',5, '160km','2.5小时'),
    ('栾川','开封',6, '350km','4.5小时'),
    ('开封','邢台',8, '350km','4小时'),
    ('邢台','北京',8, '360km','4小时'),
]

# 次要景点
secondary_attr = {
    '涞源': '白石山',
    '长治': '上党门·城隍庙',
    '晋城': '青莲寺',
    '洛阳': '白马寺·应天门·洛邑古城',
    '开封': '大相国寺·开封府',
}
rest_days = {4: '洛阳全天', 7: '开封全天'}

PROV_COLORS = {'冀':'#2E7D32','晋':'#1565C0','豫':'#C62828'}
DAY_COLORS  = ['#E53935','#FB8C00','#FDD835','#43A047','#1E88E5','#8E24AA','#00ACC1','#6D4C41']
city_coords = {c[0]:(c[2],c[1]) for c in cities_data}
# 同纬度城市手动偏移
city_coords['平顺'] = (city_coords['平顺'][0], city_coords['平顺'][1] - 0.08)
city_coords['长治'] = (city_coords['长治'][0], city_coords['长治'][1] + 0.08)
city_prov   = {c[0]:c[4] for c in cities_data}
city_attr   = {c[0]:c[3] for c in cities_data}

def is_return(fc, tc):
    _,ly1=city_coords[fc]; _,ly2=city_coords[tc]
    return ly2 > ly1  # 向北行驶=返程

# ============================================================
# Map
# ============================================================
fig = plt.figure(figsize=(22, 26), dpi=120)
fig.patch.set_facecolor('white')
ax = fig.add_axes([0.03, 0.04, 0.94, 0.92], projection=ccrs.PlateCarree())
ax.set_extent([110.3, 117.7, 32.5, 41.3], crs=ccrs.PlateCarree())

# --- Province boundaries ---
try:
    reader = shpreader.Reader(
        natural_earth(resolution='50m', category='cultural', name='admin_1_states_provinces'))
    for rec in reader.records():
        nm = rec.attributes.get('name','')
        prov_map = {'Hebei':'冀','Shanxi':'晋','Henan':'豫'}
        if nm in prov_map:
            ax.add_geometries([rec.geometry], ccrs.PlateCarree(),
                facecolor='none',
                edgecolor=PROV_COLORS[prov_map[nm]],
                linewidth=2.0, alpha=0.3, zorder=3)
    # Province labels
    prov_labels = [
        ('Hebei', 115.5, 39.0, '冀 · 河北', '#2E7D32'),
        ('Shanxi', 112.0, 37.5, '晋 · 山西', '#1565C0'),
        ('Henan', 113.5, 34.5, '豫 · 河南', '#C62828'),
    ]
    for rec in reader.records():
        nm = rec.attributes.get('name','')
        if nm == 'Hebei':
            cx, cy = 115.5, 39.0
        elif nm == 'Shanxi':
            cx, cy = 112.0, 37.5
        elif nm == 'Henan':
            cx, cy = 113.5, 34.5
        else:
            continue
        ax.text(cx, cy, {'Hebei':'冀·河北','Shanxi':'晋·山西','Henan':'豫·河南'}[nm],
            fontproperties=F(14, True), color=PROV_COLORS[{'Hebei':'冀','Shanxi':'晋','Henan':'豫'}[nm]],
            ha='center', va='center', alpha=0.12, transform=ccrs.PlateCarree(), zorder=2)
    print("[Map] Provinces OK")
except Exception as e:
    print(f"[Map] Province error: {e}")

# --- Base map ---
ax.add_feature(cfeature.LAND,      facecolor='#F8F4EC', zorder=0)
ax.add_feature(cfeature.OCEAN,     facecolor='#E8EDF4', zorder=0)
ax.add_feature(cfeature.LAKES,     facecolor='#DAE5F0', edgecolor='#AABBCC',linewidth=1,zorder=1)
ax.add_feature(cfeature.COASTLINE, edgecolor='#999999', linewidth=1.2, zorder=2)
ax.add_feature(cfeature.BORDERS,   edgecolor='#AAAAAA', linewidth=0.8, linestyle=':', zorder=2)

gl = ax.gridlines(draw_labels=True, linestyle='--', color='#D5D5D5',linewidth=0.5,alpha=0.4)
gl.top_labels=False; gl.right_labels=False
gl.xlabel_style={'size':9,'color':'#999999'}
gl.ylabel_style={'size':9,'color':'#999999'}

# ============================================================
# Route lines
# ============================================================
def draw_glow_line(x1,y1,x2,y2,color):
    for m,a in [(4,0.06),(2.5,0.12),(1.5,0.25)]:
        ax.plot([x1,x2],[y1,y2], color=mcolors.to_rgba(color,a),
                linewidth=5*m, solid_capstyle='round', transform=ccrs.PlateCarree(), zorder=8)
    ax.plot([x1,x2],[y1,y2], color=color, linewidth=5,
            solid_capstyle='round', transform=ccrs.PlateCarree(), zorder=10)

forward_segs = [(s,is_return(s[0],s[1])) for s in segments]
for seg, ret in forward_segs:
    fc,tc,day,dist_s,time_s=seg
    if ret: continue
    x1,y1=city_coords[fc]; x2,y2=city_coords[tc]
    draw_glow_line(x1,y1,x2,y2,DAY_COLORS[day-1])

for seg, ret in forward_segs:
    fc,tc,day,dist_s,time_s=seg
    if not ret: continue
    x1,y1=city_coords[fc]; x2,y2=city_coords[tc]
    draw_glow_line(x1,y1,x2,y2,DAY_COLORS[day-1])

# ============================================================
# City nodes — big circles, name INSIDE
# ============================================================
NODE_RADIUS_DEG = 0.15  # 约50px

for name, lat, lon, attr, prov in cities_data:
    x, y = city_coords[name]  # use adjusted coordinates
    pc = PROV_COLORS[prov]

    # Outer glow
    for m,a in [(1.8,0.06),(1.3,0.12),(0.9,0.25)]:
        ax.add_patch(plt.Circle((x,y), NODE_RADIUS_DEG*m,
            fc=mcolors.to_rgba(pc,a), ec='none', transform=ccrs.PlateCarree(), zorder=15))

    # Main circle: white fill + thick colored border
    ax.add_patch(plt.Circle((x,y), NODE_RADIUS_DEG,
        fc='white', ec=pc, lw=3.5, transform=ccrs.PlateCarree(), zorder=17))

    # Inner decoration ring
    ax.add_patch(plt.Circle((x,y), NODE_RADIUS_DEG*0.7,
        fc='none', ec=mcolors.to_rgba(pc,0.25), lw=1.0, transform=ccrs.PlateCarree(), zorder=18))

    # City name — BOLD, large, centered INSIDE the circle
    fs_name = 18 if len(name)<=2 else 15
    ax.text(x, y, name,
        fontproperties=F(fs_name, True),
        color=pc, ha='center', va='center',
        transform=ccrs.PlateCarree(), zorder=20,
        path_effects=TEXT_STROKE)

    # ── Attractions with leader lines ──
    # Alternate side: even/odd index in city list
    city_names = [c[0] for c in cities_data]
    idx = city_names.index(name)
    # 北京 goes left, others alternate
    if idx == 0:
        side, ha = -1, 'right'
    elif idx % 2 == 1:
        side, ha = 1, 'left'
    else:
        side, ha = -1, 'right'

    leader_x = x + NODE_RADIUS_DEG * 0.85 * side

    if side == 1:
        tx = x + NODE_RADIUS_DEG * 2.0
    else:
        tx = x - NODE_RADIUS_DEG * 2.0

    # Ensure text stays within map bounds
    MAP_LON_MIN, MAP_LON_MAX = 110.3, 117.7
    tx = max(MAP_LON_MIN + 0.3, min(MAP_LON_MAX - 0.3, tx))
    if tx == MAP_LON_MIN + 0.3 or tx == MAP_LON_MAX - 0.3:
        ha = 'left' if tx == MAP_LON_MIN + 0.3 else 'right'

    leader_color = mcolors.to_rgba(pc, 0.4)
    leader_lw = 1.5

    # Main attraction — same y as node, solid leader line, full circle marker
    if attr:
        ax.plot([leader_x, tx], [y, y],
            color=leader_color, linewidth=leader_lw, solid_capstyle='round',
            transform=ccrs.PlateCarree(), zorder=14)
        ax.plot(leader_x, y, 'o', color=pc, markersize=5,
                transform=ccrs.PlateCarree(), zorder=15)
        ax.text(tx, y, attr,
            fontproperties=F(18, True), color='#5D4037',
            ha=ha, va='center',
            transform=ccrs.PlateCarree(), zorder=16,
            path_effects=TEXT_STROKE)

    # Secondary attraction — below main, dashed line, hollow marker
    if name in secondary_attr:
        sty = y - 0.09  # 明显低于主要景点
        ax.plot([leader_x, tx], [y, sty],
            color=mcolors.to_rgba('#999999', 0.5), linewidth=1.0,
            solid_capstyle='round', linestyle='--',
            transform=ccrs.PlateCarree(), zorder=13)
        ax.plot(leader_x, sty, 'o', color='#999999', markersize=3,
                markerfacecolor='white', markeredgewidth=1.0,
                transform=ccrs.PlateCarree(), zorder=14)
        ax.text(tx, sty, secondary_attr[name],
            fontproperties=F(16, True), color='#666666',
            ha=ha, va='center',
            transform=ccrs.PlateCarree(), zorder=15,
            path_effects=TEXT_STROKE)

# ============================================================
# Labels: Day / Distance / Time — clearly differentiated
# ============================================================
# 所有标签用垂直偏移，靠近线路但不叠加
OFF = 0.28  # 偏移量：靠近线路但留够间隙

# 距离 & 时间 — 每段中点垂直偏移
for i, seg in enumerate(segments):
    fc,tc,day,dist_s,time_s = seg
    x1,y1=city_coords[fc]; x2,y2=city_coords[tc]
    mx,my = (x1+x2)/2, (y1+y2)/2
    dx,dy = x2-x1, y2-y1
    l = np.hypot(dx,dy)
    if l>0.3:
        nx,ny = -dy/l, dx/l
    else:
        nx,ny=0.3,0.3

    ret = is_return(fc,tc)
    side = -1 if ret else 1
    lx = mx + nx*OFF*side
    ly = my + ny*OFF*side

    # 距离
    ax.text(lx, ly, dist_s,
        fontproperties=F(20, True), color='#1565C0',
        ha='center', va='center', transform=ccrs.PlateCarree(), zorder=18,
        path_effects=TEXT_STROKE)
    # 时间 (下方)
    ax.text(lx, ly-0.10, time_s,
        fontproperties=F(18, True), color='#E65100',
        ha='center', va='top', transform=ccrs.PlateCarree(), zorder=18,
        path_effects=TEXT_STROKE)

# ═══ D1-D8 天次（非休息日）═══ — 段中点垂直偏移
day_last_seg = {}
for i, seg in enumerate(segments):
    day_last_seg[seg[2]] = i
for i, seg in enumerate(segments):
    if i != day_last_seg[seg[2]]:
        continue  # 只标每天最后一段
    fc,tc,day,dist_s,time_s = seg
    x1,y1=city_coords[fc]; x2,y2=city_coords[tc]
    mx,my = (x1+x2)/2, (y1+y2)/2
    dx,dy = x2-x1, y2-y1
    l = np.hypot(dx,dy)
    if l>0.3:
        nx,ny = -dy/l, dx/l
    else:
        nx,ny=0.3,0.3
    ret = is_return(fc,tc)
    side = -1 if ret else 1
    lx = mx + nx*OFF*side
    ly = my + ny*OFF*side + 0.12  # 在距离/时间上方
    ax.text(lx, ly, f'D{day}',
        fontproperties=F(24, True), color='#7B1FA2',
        ha='center', va='bottom', transform=ccrs.PlateCarree(), zorder=18,
        path_effects=TEXT_STROKE)

# ═══ D4（洛阳全天）、D7（开封全天）═══ — 城市正下方靠近
REST_POS = {
    4: (112.45, 34.40),  # 洛阳（112.45, 34.62）正下方
    7: (114.30, 34.58),  # 开封（114.30, 34.80）正下方
}
for day, (dx, dy) in REST_POS.items():
    label = {4: '洛阳全天', 7: '开封全天'}[day]
    ax.text(dx, dy + 0.06, f'D{day}',
        fontproperties=F(24, True), color='#7B1FA2',
        ha='center', va='bottom', transform=ccrs.PlateCarree(), zorder=18,
        path_effects=TEXT_STROKE)
    ax.text(dx, dy, f'（{label}）',
        fontproperties=F(14, True), color='#7B1FA2',
        ha='center', va='top', transform=ccrs.PlateCarree(), zorder=18,
        path_effects=TEXT_STROKE)

# ============================================================
# Title
# ============================================================
fig.text(0.5, 0.975, '晋豫古建自驾 · 八日路线图',
    fontproperties=F(36, True), color='#222222',
    ha='center', va='center', zorder=30,
    path_effects=TEXT_STROKE)
fig.text(0.5, 0.953, '北京 → 浊漳河谷 → 老君山 → 开封  ｜  全程约2300km',
    fontproperties=F(18, True), color='#888888',
    ha='center', va='center', zorder=30,
    path_effects=TEXT_STROKE)

# ============================================================
# Save
# ============================================================
print("[Save] Saving...")
fig.savefig(OUTPUT, dpi=120, facecolor='white', edgecolor='none', bbox_inches='tight')
print(f"[Save] -> {OUTPUT}")
shutil.copy2(OUTPUT, DESKTOP)
print(f"[Save] -> {DESKTOP}")
plt.close(fig)
print("[Done]")
