#!/usr/bin/env python3
"""
自驾路线图 v16 - 全自动排版引擎
只需修改数据段，所有位置自动计算、自动避让
"""

import os, warnings, math
warnings.filterwarnings('ignore')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
from matplotlib.patches import Ellipse
from matplotlib.font_manager import FontProperties
import cartopy.crs as ccrs
import cartopy.feature as cfeature
from cartopy.io import shapereader

def F(sz):
    return FontProperties(fname='/System/Library/Fonts/STHeiti Medium.ttc', size=sz, weight='bold')

def ST(w=4):
    return [pe.withStroke(linewidth=w, foreground='white')]

# ========== 数据 ==========
# (城市名, 纬度, 经度, [(主要景点名, 纬度, 经度), ...], [(次要景点名, 纬度, 经度), ...], 省份颜色)
CITIES = [
    ("喀什", 39.470, 75.994,
     [("喀什古城", 39.470, 75.998), ("艾提尕尔清真寺", 39.478, 75.983)],
     [("香妃墓", 39.497, 75.994), ("高台民居", 39.467, 75.996)], '#C0392B'),
    ("塔县", 37.775, 75.229,
     [("石头城", 37.776, 75.224), ("盘龙古道", 37.556, 75.411)],
     [("金草滩", 37.778, 75.226)], '#2ECC71'),
    ("莎车", 38.415, 77.249,
     [("叶尔羌汗王宫", 38.419, 77.246)],
     [("莎车老城", 38.417, 77.244)], '#2980B9'),
    ("和田", 37.116, 79.922,
     [("约特干遗址", 37.154, 79.943), ("和田博物馆", 37.112, 79.919)],
     [("和田夜市", 37.110, 79.925)], '#F39C12'),
    ("民丰", 37.064, 82.695,
     [("尼雅遗址", 37.848, 82.720)],
     [("沙漠公路起点", 37.060, 82.690)], '#D35400'),
    ("轮台", 41.782, 84.248,
     [("塔里木胡杨林", 41.567, 84.118)],
     [], '#8E44AD'),
    ("库车", 41.717, 82.962,
     [("克孜尔千佛洞", 41.790, 82.511), ("库车王府", 41.714, 82.967)],
     [("苏巴什佛寺", 41.873, 82.973), ("库车大寺", 41.713, 82.965)], '#1ABC9C'),
    ("阿克苏", 41.171, 80.266,
     [("温宿大峡谷", 41.640, 80.378)],
     [("天山神木园", 41.199, 80.147)], '#9B59B6'),
]

SEGMENTS = [
    (0, 1, 1, "294km", "4小时"),      # 喀什→塔县
    (1, 0, 2, "294km", "4小时"),      # 塔县→喀什
    (0, 2, 4, "195km", "2.5小时"),    # 喀什→莎车
    (2, 3, 5, "329km", "4小时"),      # 莎车→和田
    (3, 4, 7, "272km", "3.5小时"),    # 和田→民丰
    (4, 5, 8, "580km", "7小时"),      # 民丰→轮台（沙漠公路）
    (5, 6, 9, "113km", "1.5小时"),    # 轮台→库车
    (6, 7, 11, "252km", "3小时"),     # 库车→阿克苏
    (7, 0, 12, "461km", "5小时"),     # 阿克苏→喀什
]

REST_DAYS = {3: "喀什", 6: "和田", 10: "库车"}

DAY_COLORS = {
    1: '#E74C3C', 2: '#E67E22', 3: '#F1C40F',
    4: '#2ECC71', 5: '#1ABC9C', 6: '#3498DB',
    7: '#9B59B6', 8: '#E91E63', 9: '#FF9800',
    10: '#009688', 11: '#607D8B', 12: '#795548',
}

# 地图范围 [西经, 东经, 南纬, 北纬]
# 修改此处后，ax.set_extent 和行程表搜索区域自动适配
MAP_EXTENT = [74, 86, 36, 42.5]

# 每日景点分配（可选，覆盖CITIES中的默认全部景点）
# 格式: day_num → (["主要景点名"], ["次要景点名"])
# 未定义的日期自动使用CITIES中该城市的全部景点
DAY_ATTRACTIONS = {
    3: (["喀什古城", "艾提尕尔清真寺", "香妃墓"], []),
    6: (["约特干遗址", "和田博物馆"], ["和田夜市"]),
    10: (["克孜尔千佛洞", "库车王府"], ["苏巴什佛寺"]),
}

# 主题描述（用于标题/副标题/自动文件名）
THEME_TITLE = "南疆丝路自驾之旅"
THEME_SUB = "帕米尔·莎车·和田·沙漠公路·龟兹·喀什"

# 行程表排版常量
FONT_SZ = 14
LINE_H = 0.21
CH_W = 0.09

# 城市圈半径（按字符数）
def city_radius(name):
    if len(name) <= 2: return 0.13
    if len(name) == 3: return 0.14
    return 0.15

# ========== 布局引擎 ==========
class Layout:
    def __init__(self, ax):
        self.ax = ax
        self.fig = ax.figure
        self.placed = []  # [(x, y, r, label), ...]
    
    def _dist(self, x1, y1, x2, y2):
        return math.hypot(x1-x2, y1-y2)
    
    def _check(self, x, y, r, margin=0.04):
        """检查位置是否可用"""
        for px, py, pr, _ in self.placed:
            if self._dist(x, y, px, py) < r + pr + margin:
                return False
        return True
    
    def _place(self, x, y, r, label=""):
        self.placed.append((x, y, r, label))
    
    def _text_r(self, text, pt):
        """根据文字长度和字号返回视觉范围半径（度），匹配 CJK 字符实际宽度"""
        return len(text) * pt * 0.004 / 2 + 0.03  # 0.03固定安全垫
    
    def place_city(self, name, lat, lon, color):
        r = city_radius(name)
        ax = self.ax
        # 椭圆补偿 set_aspect 的 y 拉伸，使城圈在屏幕上为正圆
        ax.add_patch(Ellipse((lon, lat), width=2*r, height=2*r*CRS_COS,
                             facecolor='white', edgecolor=color,
                             linewidth=3, transform=ccrs.PlateCarree(), zorder=20))
        ax.text(lon, lat, name, fontproperties=F(15), color=color,
                ha='center', va='center', zorder=21, path_effects=ST(4))
        self._place(lon, lat, r + 0.04, f"city_{name}")
    
    def normal_offset(self, x1, y1, x2, y2, offset=0.15, side=1):
        """返回垂直于路线方向的偏移坐标"""
        dx, dy = x2 - x1, y2 - y1
        length = math.hypot(dx, dy)
        if length < 0.001:
            return (0, 0)
        nx, ny = -dy/length * side, dx/length * side
        return (nx * offset, ny * offset)
    
    def place_day_label(self, text, seg_indices, is_rest=False, rest_city=None):
        """自动放置天次标注"""
        ax = self.ax
        if is_rest and rest_city:
            # 休息日 - 城市正下方（拆为两行：D7 + 开封全天，视为整体）
            ci = [c[0] for c in CITIES].index(rest_city)
            clon, clat = CITIES[ci][2], CITIES[ci][1]
            cr = city_radius(rest_city)
            day_num = text.split('（')[0]  # "D4"
            city_full = f"{rest_city}全天"
            LINE = 0.10
            r_d = self._text_r(day_num, 16)
            r_c = self._text_r(city_full, 14)
            def pair_fits(bx, by):
                """检查两行是否都可用"""
                for px, py, pr, pl in self.placed:
                    if pl.startswith(f"city_{rest_city}"):
                        continue
                    # 检查第一行（D4）
                    if self._dist(bx, by, px, py) < r_d + pr + 0.03:
                        return False
                    # 检查第二行（开封全天）
                    if self._dist(bx, by - LINE, px, py) < r_c + pr + 0.03:
                        return False
                # 第二行不能太靠近城市
                for _ci, (_, clat2, clon2, *_) in enumerate(CITIES):
                    if _ci == ci: continue
                    if self._dist(bx, by - LINE, clon2, clat2) < city_radius(CITIES[_ci][0]) + 0.15:
                        return False
                return True
            
            def place_pair(bx, by):
                t1 = ax.text(bx, by, day_num, fontproperties=F(16), color='#8B44AC',
                            ha='center', va='center', zorder=30, path_effects=ST(4))
                self._place(bx, by, r_d, f"day_{day_num}")
                t2 = ax.text(bx, by - LINE, city_full, fontproperties=F(14), color='#8B44AC',
                            ha='center', va='center', zorder=30, path_effects=ST(4))
                self._place(bx, by - LINE, r_c, f"day_{city_full}")
                return t1, t2
            
            # 第一遍：圆下方最近距离
            base_dy = cr + 0.08
            for extra in [0, 0.03, 0.05, 0.08, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40]:
                dy = base_dy + extra
                if pair_fits(clon, clat - dy):
                    return place_pair(clon, clat - dy)
            # fallback——搜索更远距离
            for angle_deg in [0, 180, 90, 270, 45, 135, 225, 315]:
                rad = math.radians(angle_deg)
                tx = clon + 0.50 * math.cos(rad)
                ty = clat + 0.50 * math.sin(rad)
                if pair_fits(tx, ty):
                    return place_pair(tx, ty)
            return place_pair(clon, clat - 0.55)
        else:
            if not seg_indices:
                return  # 驻留日无对应路段，无需在地图上标天次
            # 计算多段总和中间位置
            if len(seg_indices) == 1:
                si = seg_indices[0]
                seg = SEGMENTS[si]
                x1, y1 = CITIES[seg[0]][2], CITIES[seg[0]][1]
                x2, y2 = CITIES[seg[1]][2], CITIES[seg[1]][1]
                mx, my = (x1+x2)/2, (y1+y2)/2
            else:
                # 多段：累积找到中点
                total = 0.0
                seg_lens = []
                for si in seg_indices:
                    seg = SEGMENTS[si]
                    x1, y1 = CITIES[seg[0]][2], CITIES[seg[0]][1]
                    x2, y2 = CITIES[seg[1]][2], CITIES[seg[1]][1]
                    d = math.hypot(x2-x1, y2-y1)
                    seg_lens.append(((x1,y1),(x2,y2),d))
                    total += d
                target = total / 2
                cum = 0.0
                mx, my = 0, 0
                for (x1,y1),(x2,y2),d in seg_lens:
                    prev = cum
                    cum += d
                    if cum >= target:
                        frac = (target - prev) / d if d > 0 else 0
                        mx = x1 + (x2-x1)*frac
                        my = y1 + (y2-y1)*frac
                        break
            
            # 密度感知侧选（替代奇偶规则）
            last_si = seg_indices[-1]
            last_seg = SEGMENTS[last_si]
            x1, y1 = CITIES[last_seg[0]][2], CITIES[last_seg[0]][1]
            x2, y2 = CITIES[last_seg[1]][2], CITIES[last_seg[1]][1]
            side_scores = []
            for s in [1, -1]:
                nox, noy = self.normal_offset(x1, y1, x2, y2, 0.30, s)
                cx, cy = mx + nox, my + noy
                count = sum(1 for px, py, _, _ in self.placed
                           if self._dist(cx, cy, px, py) < 0.5)
                side_scores.append((count, s))
            side_scores.sort()
            preferred_sides = [s for _, s in side_scores]
            
            for side in preferred_sides:
                seg = SEGMENTS[last_si]
                x1, y1 = CITIES[seg[0]][2], CITIES[seg[0]][1]
                x2, y2 = CITIES[seg[1]][2], CITIES[seg[1]][1]
                nox, noy = self.normal_offset(x1, y1, x2, y2, 0.12, side)
                
                for mult in [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0]:
                    tx = mx + nox * mult
                    ty = my + noy * mult
                    if self._check(tx, ty, self._text_r(text, 18)):
                        ha = 'left' if side > 0 else 'right'
                        t = ax.text(tx, ty, text, fontproperties=F(18), color='#8B44AC',
                                    ha=ha, va='center', zorder=30, path_effects=ST(4))
                        self._place(tx, ty, self._text_r(text, 18), f"day_{text}")
                        return t
            
            # 再试沿着路线方向的偏移
            for dx, dy in [(0.25,0),(-0.25,0),(0,0.25),(0,-0.25),(0.4,0.1),(-0.4,-0.1)]:
                tx, ty = mx+dx, my+dy
                if self._check(tx, ty, self._text_r(text, 18)):
                    ha = 'left' if dx >= 0 else 'right'
                    t = ax.text(tx, ty, text, fontproperties=F(18), color='#8B44AC',
                                ha=ha, va='center', zorder=30, path_effects=ST(4))
                    self._place(tx, ty, self._text_r(text, 18), f"day_{text}")
                    return t
            # 最终 fallback——8方向搜索
            for angle_deg in [45, 135, 225, 315, 0, 90, 180, 270]:
                rad = math.radians(angle_deg)
                tx, ty = mx + 0.35 * math.cos(rad), my + 0.35 * math.sin(rad)
                if self._check(tx, ty, self._text_r(text, 18)):
                    ha = 'left' if math.cos(rad) >= 0 else 'right'
                    t = ax.text(tx, ty, text, fontproperties=F(18), color='#8B44AC',
                                ha=ha, va='center', zorder=30, path_effects=ST(4))
                    self._place(tx, ty, self._text_r(text, 18), f"day_{text}")
                    return t
            # 真的没办法了
            t = ax.text(mx+0.3, my+0.2, text, fontproperties=F(18), color='#8B44AC',
                        ha='left', va='center', zorder=30, path_effects=ST(4))
            self._place(mx+0.3, my+0.2, self._text_r(text, 18), f"day_{text}")
            return t
    
    def place_dist_time(self, dist_text, time_text, si):
        """放置距离和时间——固定上下叠放（0.10°行高间距），视为一个整体"""
        ax = self.ax
        seg = SEGMENTS[si]
        x1, y1 = CITIES[seg[0]][2], CITIES[seg[0]][1]
        x2, y2 = CITIES[seg[1]][2], CITIES[seg[1]][1]
        mx, my = (x1+x2)/2, (y1+y2)/2
        
        # 智能选择方向
        side_scores = []
        for s in [1, -1]:
            nox, noy = self.normal_offset(x1, y1, x2, y2, 0.25, s)
            cx, cy = mx + nox, my + noy
            count = sum(1 for px, py, _, _ in self.placed if self._dist(cx, cy, px, py) < 0.8)
            side_scores.append((count, s))
        side_scores.sort()
        preferred_sides = [s for _, s in side_scores]
        
        # 段长度（影响标签偏移基数：短段自动增大偏移）
        seg_len_deg = math.hypot(x2 - x1, y2 - y1)
        pair_mults = [1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0] if seg_len_deg < 1.5 else [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0]
        fallback_mults = [2.0, 2.5, 3.0, 3.5, 4.0, 5.0, 6.0, 8.0] if seg_len_deg < 1.5 else [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0, 6.0, 8.0]
        LINE_GAP = 0.10
        r_dist = self._text_r(dist_text, 16)
        r_time = self._text_r(time_text, 14)
        
        def pair_fits(bx, by):
            """检查 dist 在 (bx,by)、time 在 (bx,by-LINE_GAP) 是否都可用"""
            if not self._check(bx, by, r_dist): return False
            if not self._check(bx, by - LINE_GAP, r_time): return False
            # time 不能太靠近城市
            ty = by - LINE_GAP
            for ci, (_, clat, clon, *_) in enumerate(CITIES):
                if self._dist(bx, ty, clon, clat) < city_radius(CITIES[ci][0]) + 0.15:
                    return False
            return True
        
        def place_pair(bx, by):
            t1 = ax.text(bx, by, dist_text, fontproperties=F(16), color='#2980B9',
                        ha='center', va='center', zorder=30, path_effects=ST(4))
            self._place(bx, by, r_dist, f"dist_{si}")
            t2 = ax.text(bx, by - LINE_GAP, time_text, fontproperties=F(14), color='#E67E22',
                        ha='center', va='center', zorder=30, path_effects=ST(4))
            self._place(bx, by - LINE_GAP, r_time, f"time_{si}")
            return t1, t2
        
        # 第一遍：尝试放置整个对
        for side in preferred_sides:
            nox, noy = self.normal_offset(x1, y1, x2, y2, 0.12, side)
            for mult in pair_mults:
                for dy_off in [0, 0.15, -0.15, 0.25, -0.25, 0.30, -0.30, 0.40]:
                    bx = mx + nox * mult - 0.02
                    by = my + noy * mult + dy_off
                    if pair_fits(bx, by):
                        return place_pair(bx, by)
        
        # 放不下整个对——放整对并进一步搜索更远位置
        for side in preferred_sides:
            nox, noy = self.normal_offset(x1, y1, x2, y2, 0.12, side)
            for mult in fallback_mults:
                for dy_off in [0, 0.15, -0.15, 0.25, -0.25, 0.30, -0.30]:
                    bx = mx + nox * mult - 0.02
                    by = my + noy * mult + dy_off
                    if self._check(bx, by, r_dist):
                        return place_pair(bx, by)
        
        # 最终 fallback——8方向搜索
        for angle_deg in [45, 135, 225, 315, 0, 90, 180, 270]:
            rad = math.radians(angle_deg)
            bx = mx + 0.50 * math.cos(rad)
            by = my + 0.50 * math.sin(rad)
            if self._check(bx, by, r_dist):
                return place_pair(bx, by)
        return place_pair(mx + 0.2, my + 0.15)
    
    def place_attractions(self, idx, name, lat, lon, prim, sec, color):
        """真实坐标打点 + 可选引线 + 标签自动寻位"""
        ax = self.ax
        cr = city_radius(name)
        
        def place_outside(attr_name, at_lat, at_lon, is_prim, ai):
            """城圈外的景点：打点 + 紧挨标签"""
            color_p = '#8B4513' if is_prim else '#27AE60'
            sz = 14 if is_prim else 13
            r_check = self._text_r(attr_name, sz)
            
            # 打点
            mfc = color_p if is_prim else 'none'
            ax.plot(at_lon, at_lat, 'o', color=color_p, markersize=5,
                    markerfacecolor=mfc, markeredgewidth=2,
                    transform=ccrs.PlateCarree(), zorder=16)
            
            # 从0.08°开始寻找紧邻位置
            for dist in [0.08, 0.14, 0.22, 0.35, 0.50]:
                for angle_deg in [225, 315, 180, 0, 270, 90, 135, 45]:
                    rad = math.radians(angle_deg)
                    tx = at_lon + dist * math.cos(rad)
                    ty = at_lat + dist * math.sin(rad)
                    if self._check(tx, ty, r_check):
                        side = 1 if math.cos(rad) >= 0 else -1
                        ha = 'left' if side > 0 else 'right'
                        if dist > 0.20:
                            ls = '-' if is_prim else '--'
                            ax.plot([tx, at_lon], [ty, at_lat], color=color_p,
                                    linewidth=1.5, linestyle=ls, alpha=0.7,
                                    transform=ccrs.PlateCarree(), zorder=15)
                        ax.text(tx, ty, attr_name, fontproperties=F(sz), color=color_p,
                                ha=ha, va='center', zorder=17, path_effects=ST(3.5))
                        self._place(tx, ty, r_check,
                                    f"{'prim' if is_prim else 'sec'}_{idx}_{ai}")
                        return
            # fallback
            tx = at_lon + 0.25; ty = at_lat
            ls = '-' if is_prim else '--'
            ax.plot([tx, at_lon], [ty, at_lat], color=color_p,
                    linewidth=1.5, linestyle=ls, alpha=0.7,
                    transform=ccrs.PlateCarree(), zorder=15)
            ax.text(tx, ty, attr_name, fontproperties=F(sz), color=color_p,
                    ha='left', va='center', zorder=17, path_effects=ST(3.5))
            self._place(tx, ty, r_check,
                        f"{'prim' if is_prim else 'sec'}_{idx}_{ai}")
        
        def place_grouped(prim_list, sec_list):
            """城圈内的景点：合并成一个整体，从城圈拉一根引线"""
            if not prim_list and not sec_list:
                return
            prim_str = "、".join(n for n, _, _ in prim_list) if prim_list else ""
            sec_str = "、".join(n for n, _, _ in sec_list) if sec_list else ""
            LINE = 0.14  # 主次景点行间距（增大以避开相邻景点标签）
            r_pair = max(self._text_r(prim_str, 14), self._text_r(sec_str, 13))
            
            def pair_fits(bx, by, side):
                r = 0.15  # 匹配 place_outside 的 r_check，防止景点标签间视觉堆叠
                for d in [0, -LINE]:
                    tx, ty = bx, by + d
                    # 手动检查，跳过自己的城圈
                    ok = True
                    for px, py, pr, pl in self.placed:
                        if pl == f"city_{name}":
                            continue
                        if self._dist(tx, ty, px, py) < r + pr + 0.03:
                            ok = False
                            break
                    if not ok:
                        return False
                return True
            
            for dist in [cr + 0.10, cr + 0.18, cr + 0.28, cr + 0.40, cr + 0.55]:
                for angle_deg in [225, 315, 180, 0, 270, 90, 135, 45]:
                    rad = math.radians(angle_deg)
                    bx = lon + dist * math.cos(rad)
                    by = lat + dist * math.sin(rad)
                    side = 1 if math.cos(rad) >= 0 else -1
                    ha = 'left' if side > 0 else 'right'
                    
                    if pair_fits(bx, by, side):
                        # 引线
                        ed_x = lon + cr * math.cos(rad)
                        ed_y = lat + cr * math.sin(rad)
                        ax.plot([bx, ed_x], [by, ed_y], color='#8B4513',
                                linewidth=1.5, alpha=0.7,
                                transform=ccrs.PlateCarree(), zorder=15)
                        # prim
                        if prim_str:
                            ax.text(bx, by, prim_str, fontproperties=F(14),
                                    color='#8B4513', ha=ha, va='center',
                                    zorder=17, path_effects=ST(3.5))
                            self._place(bx, by, 0.15, f"gprim_{idx}")
                        # sec
                        if sec_str:
                            ax.text(bx, by - LINE, sec_str, fontproperties=F(13),
                                    color='#27AE60', ha=ha, va='center',
                                    zorder=17, path_effects=ST(3.5))
                            self._place(bx, by - LINE, 0.15, f"gsec_{idx}")
                        return
            
            # fallback——8方向搜索
            for angle_deg in [225, 315, 180, 0, 270, 90, 135, 45]:
                rad = math.radians(angle_deg)
                bx = lon + (cr + 0.20) * math.cos(rad)
                by = lat + (cr + 0.20) * math.sin(rad)
                side = 1 if math.cos(rad) >= 0 else -1
                ha = 'left' if side > 0 else 'right'
                ok = True
                for d in [0, -LINE]:
                    tx, ty = bx, by + d
                    for px, py, pr, pl in self.placed:
                        if pl == f"city_{name}":
                            continue
                        if self._dist(tx, ty, px, py) < r_pair + pr + 0.03:
                            ok = False
                            break
                    if not ok:
                        break
                if ok:
                    ed_x = lon + cr * math.cos(rad)
                    ed_y = lat + cr * math.sin(rad)
                    ax.plot([bx, ed_x], [by, ed_y], color='#8B4513',
                            linewidth=1.5, alpha=0.7,
                            transform=ccrs.PlateCarree(), zorder=15)
                    if prim_str:
                        ax.text(bx, by, prim_str, fontproperties=F(14), color='#8B4513',
                                ha=ha, va='center', zorder=17, path_effects=ST(3.5))
                        self._place(bx, by, 0.15, f"gprim_{idx}")
                    if sec_str:
                        ax.text(bx, by - LINE, sec_str, fontproperties=F(13), color='#27AE60',
                                ha=ha, va='center', zorder=17, path_effects=ST(3.5))
                        self._place(bx, by - LINE, 0.15, f"gsec_{idx}")
                    return
            
            # 终极 fallback——右侧
            bx, by = lon + cr + 0.25, lat
            ed_x, ed_y = lon + cr, lat
            ax.plot([bx, ed_x], [by, ed_y], color='#8B4513',
                    linewidth=1.5, alpha=0.7,
                    transform=ccrs.PlateCarree(), zorder=15)
            if prim_str:
                ax.text(bx, by, prim_str, fontproperties=F(14), color='#8B4513',
                        ha='left', va='center', zorder=17, path_effects=ST(3.5))
                self._place(bx, by, 0.15, f"gprim_{idx}")
            if sec_str:
                ax.text(bx, by - LINE, sec_str, fontproperties=F(13), color='#27AE60',
                        ha='left', va='center', zorder=17, path_effects=ST(3.5))
                self._place(bx, by - LINE, 0.15, f"gsec_{idx}")
        
        # 按是否在城圈内分类（cr+0.01：把紧贴城圈边缘的景点独立打点，避免合并文字过长）
        in_prim = [(n, alat, alon) for (n, alat, alon) in prim
                   if math.hypot(alon - lon, alat - lat) < cr + 0.01]
        out_prim = [(n, alat, alon) for (n, alat, alon) in prim
                    if math.hypot(alon - lon, alat - lat) >= cr + 0.01]
        in_sec = [(n, alat, alon) for (n, alat, alon) in sec
                  if math.hypot(alon - lon, alat - lat) < cr + 0.01]
        out_sec = [(n, alat, alon) for (n, alat, alon) in sec
                   if math.hypot(alon - lon, alat - lat) >= cr + 0.01]
        
        # 城圈内 → 合并
        if in_prim or in_sec:
            place_grouped(in_prim, in_sec)
        
        # 城圈外 → 单个打点
        for ai, (n, alat, alon) in enumerate(out_prim):
            place_outside(n, alat, alon, True, ai)
        for ai, (n, alat, alon) in enumerate(out_sec):
            place_outside(n, alat, alon, False, ai)


# ========== 主程序 ==========
print("底图...")
fig = plt.figure(figsize=(16, 20), facecolor='white')
ax = fig.add_subplot(111, projection=ccrs.PlateCarree())
fig.subplots_adjust(left=0.01, right=0.99, top=0.99, bottom=0.01)
# 纬度补偿：1°经度实际距离 = 1°纬度 × cos(纬度)，自动从城市坐标计算
CRS_LAT = round(sum(c[1] for c in CITIES) / len(CITIES))
CRS_COS = math.cos(math.radians(CRS_LAT))

# 自动扩展北边界，为行程表留足空间——一劳永逸，不依赖手动调参
day_to_segs_pre = {}
for si, seg in enumerate(SEGMENTS):
    d = seg[2]
    day_to_segs_pre.setdefault(d, []).append(si)
all_seg_days_pre = set(day_to_segs_pre.keys())
all_rest_days_pre = set(REST_DAYS.keys())
max_day_pre = max(list(all_seg_days_pre | all_rest_days_pre) + list(DAY_ATTRACTIONS.keys()) + [0])
table_line_count = len(range(1, max_day_pre + 1))
th_table = table_line_count * LINE_H + 0.10
# 最高城市圆圈顶部（含放置间距）
peak_node_top = max(c[1] + city_radius(c[0]) + 0.04 for c in CITIES)
# 刚好能放下行程表的最小北边界：
#   行程表底部（north-1.05-th_table）刚好在最高城市圆圈顶部 + 3%°
TABLE_GAP = 0.03
TABLE_NORTH = peak_node_top + TABLE_GAP + 1.05 + th_table
if TABLE_NORTH > MAP_EXTENT[3]:
    print(f"  自动扩展北边界: {MAP_EXTENT[3]:.1f}° → {TABLE_NORTH:.1f}°")
    MAP_EXTENT[3] = TABLE_NORTH

ax.set_extent(MAP_EXTENT)
ax.set_aspect(1.0 / CRS_COS, adjustable='box')

ax.add_feature(cfeature.LAND, facecolor='#F8F4EC', zorder=1)
ax.add_feature(cfeature.OCEAN, facecolor='#E8EDF4', zorder=1)
ax.add_feature(cfeature.LAKES, facecolor='#DAE5F0', edgecolor='#AABBCC', linewidth=1.0, zorder=2)
ax.add_feature(cfeature.COASTLINE, edgecolor='#999999', linewidth=2.0, zorder=3)
ax.add_feature(cfeature.RIVERS, edgecolor='#BFD7EA', linewidth=0.8, alpha=0.5, zorder=2)

gl = ax.gridlines(draw_labels=True, linewidth=1.0, color='#BBBBBB', alpha=0.3, linestyle='--')
gl.top_labels = False
gl.right_labels = False
gl.xlabel_style = {'size': 13, 'color': '#999999'}
gl.ylabel_style = {'size': 13, 'color': '#999999'}

# 省界——自动检测地图范围内有哪些省，标签位置从几何中心计算
print("省界...")
PROV_CN = {
    'BJ':'北京','TJ':'天津','HE':'河北','SX':'山西','NM':'内蒙古',
    'LN':'辽宁','JL':'吉林','HL':'黑龙江','SH':'上海','JS':'江苏',
    'ZJ':'浙江','AH':'安徽','FJ':'福建','JX':'江西','SD':'山东',
    'HA':'河南','HB':'湖北','HN':'湖南','GD':'广东','GX':'广西',
    'HI':'海南','CQ':'重庆','SC':'四川','GZ':'贵州','YN':'云南',
    'XZ':'西藏','SN':'陕西','GS':'甘肃','QH':'青海','NX':'宁夏',
    'XJ':'新疆','TW':'台湾','HK':'香港','MO':'澳门',
}
PROV_COLORS = {
    'BJ':'#C0392B','TJ':'#E74C3C','HE':'#27AE60','SX':'#2980B9','NM':'#1ABC9C',
    'LN':'#E67E22','JL':'#F39C12','HL':'#F1C40F','SH':'#E91E63','JS':'#9B59B6',
    'ZJ':'#8E44AD','AH':'#D35400','FJ':'#3498DB','JX':'#2ECC71','SD':'#16A085',
    'HA':'#E67E22','HB':'#FF9800','HN':'#FF5722','GD':'#795548','GX':'#607D8B',
    'SN':'#009688','GS':'#673AB7','QH':'#3F51B5','NX':'#00BCD4','XJ':'#CDDC39',
}
from shapely.geometry import box
extent_box = box(MAP_EXTENT[0], MAP_EXTENT[2], MAP_EXTENT[1], MAP_EXTENT[3])
try:
    for rec in shapereader.Reader(shapereader.natural_earth(resolution='50m', category='cultural', name='admin_1_states_provinces')).records():
        iso = rec.attributes.get('iso_3166_2','')
        short = iso.split('-')[-1] if '-' in iso else ''
        if not short: continue
        # 检测是否与地图范围相交
        if not extent_box.intersects(rec.geometry):
            continue
        c = PROV_COLORS.get(short, '#888888')
        ax.add_geometries([rec.geometry], crs=ccrs.PlateCarree(), facecolor='none',
                          edgecolor=c, linewidth=3.0, alpha=0.35, zorder=4)
        # 标签位置：几何中心（若在范围外则取范围中心）
        centroid = rec.geometry.centroid
        cx, cy = centroid.x, centroid.y
        if not (MAP_EXTENT[0] <= cx <= MAP_EXTENT[1] and MAP_EXTENT[2] <= cy <= MAP_EXTENT[3]):
            cx = (MAP_EXTENT[0] + MAP_EXTENT[1]) / 2
            cy = (MAP_EXTENT[2] + MAP_EXTENT[3]) / 2
        cn_name = PROV_CN.get(short, short)
        ax.text(cx, cy, cn_name, fontproperties=F(30), color=c, alpha=0.35,
                ha='center', va='center', zorder=4)
except Exception as e:
    print(f"省界: {e}")

# 路线
print("路线...")
for s_idx, e_idx, day, _, _ in SEGMENTS:
    color = DAY_COLORS.get(day, '#888888')
    x1, y1 = CITIES[s_idx][2], CITIES[s_idx][1]
    x2, y2 = CITIES[e_idx][2], CITIES[e_idx][1]
    for gw, ga in [(22,0.06),(16,0.12),(10,0.25)]:
        ax.plot([x1,x2],[y1,y2], color=color, linewidth=gw, alpha=ga, solid_capstyle='round', zorder=5)
    ax.plot([x1,x2],[y1,y2], color=color, linewidth=6, alpha=1.0, solid_capstyle='round', zorder=6,
            path_effects=[pe.withStroke(linewidth=8, foreground='white', alpha=0.35)])

# 布局引擎
layout = Layout(ax)

# 天次索引（提前计算，行程表需要）
day_to_segs = {}
for si, seg in enumerate(SEGMENTS):
    d = seg[2]
    day_to_segs.setdefault(d, []).append(si)
# 生成连续天数 D1..Dmax，自动填充无路段/无休息日的驻留日
all_seg_days = set(day_to_segs.keys())
all_rest_days = set(REST_DAYS.keys())
max_day = max(list(all_seg_days | all_rest_days) + list(DAY_ATTRACTIONS.keys()) + [0])
all_days = sorted(range(1, max_day + 1))

# ========== 行程表：优先放置，其他元素自动避让 ==========
print("行程表...")
# 格式：D1 城市→城市 · 景点
all_lines = []
for day in all_days:
    seg_indices = day_to_segs.get(day, [])
    is_rest = day in REST_DAYS
    rest_city = REST_DAYS.get(day)
    if is_rest and rest_city:
        if day in DAY_ATTRACTIONS:
            prim_attrs, sec_attrs = DAY_ATTRACTIONS[day]
            all_attrs = prim_attrs + sec_attrs
        else:
            ci = [c[0] for c in CITIES].index(rest_city)
            all_attrs = [a[0] for a in CITIES[ci][3]] + [a[0] for a in CITIES[ci][4]]
        attr_str = "、".join(all_attrs) if all_attrs else ""
        line = f"D{day}  {rest_city}全天"
        if attr_str: line += f"  ·  {attr_str}"
        all_lines.append(line)
    elif seg_indices:
        cities_in_route = []
        all_attrs = []
        for si in seg_indices:
            s = SEGMENTS[si]
            if not cities_in_route: cities_in_route.append(CITIES[s[0]][0])
            cities_in_route.append(CITIES[s[1]][0])
            ci = s[1]
            if day in DAY_ATTRACTIONS:
                pa, sa = DAY_ATTRACTIONS[day]
            else:
                pa = [a[0] for a in CITIES[ci][3]]
                sa = [a[0] for a in CITIES[ci][4]]
            all_attrs.extend(pa + sa)
        line = f"D{day}  {'→'.join(cities_in_route)}"
        attrs = "、".join(dict.fromkeys(all_attrs)) if all_attrs else ""
        if attrs: line += f"  ·  {attrs}"
        all_lines.append(line)
    else:
        # 驻留日：无路段、非休息日，沿用上一个旅行日到达的城市
        prev_me = [d for d in sorted(all_seg_days | all_rest_days | {0}) if d < day]
        if prev_me:
            prev_d = prev_me[-1]
            if prev_d in day_to_segs:
                last_seg = SEGMENTS[day_to_segs[prev_d][-1]]
                city = CITIES[last_seg[1]][0]
            elif prev_d in REST_DAYS:
                city = REST_DAYS[prev_d]
            else:
                city = ""
            if day in DAY_ATTRACTIONS:
                prim_attrs, sec_attrs = DAY_ATTRACTIONS[day]
                all_attrs = prim_attrs + sec_attrs
                attr_str = "、".join(all_attrs) if all_attrs else ""
                line = f"D{day}  {city}"
                if attr_str: line += f"  ·  {attr_str}"
            else:
                line = f"D{day}  {city}"
            all_lines.append(line)

FONT_SZ = 14
LINE_H = 0.21
CH_W = 0.09

def _txt_ok(cx, cy, tw, th):
    """文本框 (cx,cy)~(cx+tw, cy+th) 是否可用"""
    l, r = cx, cx + tw
    t, b = cy + th/2, cy - th/2
    for px, py, pr, _ in layout.placed:
        dx = max(l - px, 0, px - r)
        dy = max(b - py, 0, py - t)
        if math.hypot(dx, dy) < pr + 0.08: return False
    return True

def _find_spot(lines):
    """左上优先找空位（搜索区域由 MAP_EXTENT 动态计算）"""
    tw = min(max(len(l) for l in lines) * CH_W + 0.3, 3.8)
    th = len(lines) * LINE_H + 0.10
    west, east, south, north = MAP_EXTENT
    # 副标题基线（居中于主标题下方，va='bottom'，文字向上排）
    sub_y = north - 0.9
    CX_MIN = west + 0.2                # 左边界留 0.2°
    CX_MAX = east - 0.2 - tw           # 右边界留 0.2°
    CY_MAX = sub_y - 0.15 - th/2     # 上边界：副标题下留 0.15°
    CY_MIN = south + 0.2 + th/2        # 下边界留 0.2°
    if CX_MIN > CX_MAX or CY_MIN > CY_MAX: return None
    best, best_s = None, 999
    y = CY_MAX
    while y >= CY_MIN:
        x = CX_MIN
        while x <= CX_MAX:
            bx, by = x + tw/2, y
            cnt = sum(1 for px, py, _, _ in layout.placed if math.hypot(bx-px, by-py) < 1.0)
            cnt += sum(3 for _, clat, clon, *_ in CITIES if math.hypot(clon-bx, clat-by) < 1.0)
            sc = cnt + (north - y) * 0.02
            if sc < best_s and _txt_ok(x, y, tw, th):
                best, best_s = (x, y), sc
            x += 0.15
        y -= 0.15
    return (*best, tw, th) if best else None

def _render(lines, cx, cy):
    tw = min(max(len(l) for l in lines) * CH_W + 0.3, 3.8)
    th = len(lines) * LINE_H + 0.10
    for i, line in enumerate(lines):
        yy = cy + th/2 - 0.08 - i * LINE_H
        ax.text(cx, yy, line, fontproperties=F(FONT_SZ), color='#2C3E50',
                ha='left', va='top', zorder=95, path_effects=ST(1.5))
    layout._place(cx + tw/2, cy, max(tw, th)/2, "iti")
    return tw, th

# 策略1：单列（优先）
placed = _find_spot(all_lines)
if placed:
    _render(all_lines, *placed[:2])
    print(f"  单列: ({placed[0]:.1f},{placed[1]:.1f})")
else:
    # 策略2：两列
    mid = len(all_lines) // 2
    col1, col2 = all_lines[:mid], all_lines[mid:]
    sp1 = _find_spot(col1)
    if sp1:
        cx1, cy1, _, _ = sp1
        mw1 = min(max(len(l) for l in col1) * CH_W + 0.3, 3.8)
        mw2 = min(max(len(l) for l in col2) * CH_W + 0.3, 3.8)
        cx2 = cx1 + mw1 + 0.2
        l2, r2 = cx2, cx2 + mw2
        th1 = len(col1) * LINE_H + 0.10
        t2, b2 = cy1 + th1/2, cy1 - th1/2
        ok = all(not (math.hypot(max(l2-px,0,px-r2), max(b2-py,0,py-t2)) < pr+0.08)
                 for px, py, pr, _ in layout.placed)
        if ok:
            _render(col1, cx1, cy1)
            _render(col2, cx2, cy1)
            print(f"  双列: ({cx1:.1f},{cy1:.1f}) ({cx2:.1f},{cy1:.1f})")
            placed = True
if not placed:
    print("  行程表：未找到位置")

# ========== 城市节点 ==========
print("城市...")
for idx, (name, lat, lon, prim, sec, pc) in enumerate(CITIES):
    layout.place_city(name, lat, lon, pc)

# 天次标注
print("天次...")
for day in all_days:
    seg_indices = day_to_segs.get(day, [])
    if day in REST_DAYS:
        layout.place_day_label(f"D{day}（{REST_DAYS[day]}全天）", seg_indices, True, REST_DAYS[day])
    else:
        layout.place_day_label(f"D{day}", seg_indices)

# 景点（放在天次之后但距离/时间之前，这样距离/时间可以避让景点）
print("景点...")
for idx, (name, lat, lon, prim, sec, pc) in enumerate(CITIES):
    if prim or sec:
        layout.place_attractions(idx, name, lat, lon, prim, sec, pc)

# 距离/时间（最后放，主动避让天次和景点）
print("距离/时间...")
for si, seg in enumerate(SEGMENTS):
    layout.place_dist_time(seg[3], seg[4], si)

# 标题（从 MAP_EXTENT 动态定位）
print("标题...")
center_x = (MAP_EXTENT[0] + MAP_EXTENT[1]) / 2
# 标题/副标题距北边界的度数：
#   北边界 - 0.6° = 标题基线  (va='bottom'，文字向上排列)
#   北边界 - 0.9° = 副标题基线（标题下方 0.3°）
#   北边界 - 0.95° = 行程表顶边 (CY_MAX + th/2)
# 这个间隔保证了标题区永远在路线视野之上，适配任意北边界
title_y = MAP_EXTENT[3] - 0.6
sub_y = MAP_EXTENT[3] - 0.9
ax.text(center_x, title_y, f"{CITIES[0][0]}→{CITIES[-1][0]} · {THEME_TITLE}",
        fontproperties=F(30), color='#2C3E50',
        ha='center', va='bottom', zorder=100, path_effects=ST(6))

# 副标题居中于主标题下方
total_seg_km = sum(int(s[3].rstrip('km')) for s in SEGMENTS)
total_days = len(all_days)
ax.text(center_x, sub_y,
        f"{THEME_SUB}  ·  {total_days}天 · 约{total_seg_km}km",
        fontproperties=F(18), color='#7F8C8D', ha='center', va='bottom', zorder=100, path_effects=ST(4))

# 输出
print("保存...")
route_name = f"{CITIES[0][0]}_{CITIES[-1][0]}_{THEME_TITLE}"
OUT = os.path.expanduser(f'~/.hermes/cache/documents/{route_name}.png')
DEST = os.path.expanduser(f'~/Desktop/{route_name}.png')
plt.savefig(OUT, dpi=150, facecolor='white')
plt.close()

import shutil
shutil.copy2(OUT, DEST)
mb = os.path.getsize(OUT) / 1024 / 1024
print(f"完成! {mb:.1f} MB")
