#!/usr/bin/env python3
"""
南疆丝路自驾路线图 v3 — 最终版
回滚到"好很多"版（天次先放 0.12°，dist/time 后放尽可能近）
+ 对侧 dist/time 减 margin 避免 dist 被天次推到远距
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
    (0, 1, 1, "294km", "4小时"), (1, 0, 2, "294km", "4小时"),
    (0, 2, 4, "195km", "2.5小时"), (2, 3, 5, "329km", "4小时"),
    (3, 4, 7, "272km", "3.5小时"), (4, 5, 8, "580km", "7小时"),
    (5, 6, 9, "113km", "1.5小时"), (6, 7, 11, "252km", "3小时"),
    (7, 0, 12, "461km", "5小时"),
]
REST_DAYS = {3: "喀什", 6: "和田", 10: "库车"}
DAY_COLORS = {1:'#E74C3C',2:'#E67E22',3:'#F1C40F',4:'#2ECC71',5:'#1ABC9C',
              6:'#3498DB',7:'#9B59B6',8:'#E91E63',9:'#FF9800',10:'#009688',11:'#607D8B',12:'#795548'}
MAP_EXTENT = [74, 86, 36, 42.5]
DAY_ATTRACTIONS = {3:(["喀什古城","艾提尕尔清真寺","香妃墓"],[]),
                   6:(["约特干遗址","和田博物馆"],["和田夜市"]),
                   10:(["克孜尔千佛洞","库车王府"],["苏巴什佛寺"])}
THEME_TITLE = "南疆丝路自驾之旅"
THEME_SUB = "帕米尔·莎车·和田·沙漠公路·龟兹·喀什"
FONT_SZ = 14; LINE_H = 0.21; CH_W = 0.09; ATTR_LINE_H = 0.12

def city_radius(name):
    if len(name)<=2: return 0.13
    if len(name)==3: return 0.14
    return 0.15

# ========== 布局引擎（矩形碰撞）==========
class Layout:
    def __init__(self, ax):
        self.ax = ax; self.fig = ax.figure; self.placed = []  # (cx, cy, hw, hh, label)
        self.route_segs = []  # (x1, y1, x2, y2, hw_line)

    def _text_wh(self, text, pt):
        """文字半宽半高（地图坐标，按 200px/° 校准）"""
        return len(text) * pt * 0.0031 + 0.005, pt * 0.0036 + 0.005

    def _rect_overlap(self, cx1, cy1, hw1, hh1, cx2, cy2, hw2, hh2, margin=0):
        return abs(cx1-cx2) < hw1+hw2+margin and abs(cy1-cy2) < hh1+hh2+margin

    def _dist_to_segment(self, x, y, x1, y1, x2, y2):
        """点到线段的最短距离"""
        dx, dy = x2-x1, y2-y1
        if abs(dx) < 1e-8 and abs(dy) < 1e-8:
            return math.hypot(x-x1, y-y1)
        t = ((x-x1)*dx + (y-y1)*dy) / (dx*dx + dy*dy)
        if t <= 0: return math.hypot(x-x1, y-y1)
        if t >= 1: return math.hypot(x-x2, y-y2)
        px = x1 + t*dx; py = y1 + t*dy
        return math.hypot(x-px, y-py)

    def _rect_route_check(self, cx, cy, hw, hh, margin=0.06):
        """矩形与路线段（厚线）是否重叠"""
        for x1,y1,x2,y2,hw_line in self.route_segs:
            d = self._dist_to_segment(cx, cy, x1, y1, x2, y2)
            dxr, dyr = x2-x1, y2-y1
            ln = math.hypot(dxr, dyr)
            if ln < 1e-8: continue
            nx, ny = -dyr/ln, dxr/ln
            r_eff = abs(nx)*hw + abs(ny)*hh
            if d <= r_eff + hw_line + margin:
                return False
        return True

    def _place(self, cx, cy, hw, hh, label=""):
        self.placed.append((cx, cy, hw, hh, label))

    # --- 基检查 ---
    def _check(self, cx, cy, hw, hh, margin=0.04):
        for pcx, pcy, phw, phh, _ in self.placed:
            if self._rect_overlap(cx, cy, hw, hh, pcx, pcy, phw, phh, margin):
                return False
        return True

    # --- 城市 ---
    def place_city(self, name, lat, lon, color):
        r = city_radius(name)
        hw = r; hh = r * CRS_COS  # 椭圆半长/半短
        ax = self.ax
        ax.add_patch(Ellipse((lon, lat), width=2*r, height=2*r*CRS_COS,
            facecolor='white', edgecolor=color, linewidth=3, transform=ccrs.PlateCarree(), zorder=20))
        ax.text(lon, lat, name, fontproperties=F(15), color=color,
                ha='center', va='center', zorder=21, path_effects=ST(4))
        self._place(lon, lat, hw+0.04, hh+0.04, f"city_{name}")

    # --- 景点 ---
    def place_attractions(self, idx, name, lat, lon, prim, sec, color):
        ax = self.ax; cr = city_radius(name); side = -1 if idx%2==0 else 1
        gap = 0.10 if len(name)>=3 else 0.03
        use_leader = len(name)>=3
        base_x = lon + side*(cr+gap); ha = 'right' if side<0 else 'left'

        def check_skip(cx, cy, hw, hh, skip_own=False):
            for px,py,phw,phh,pl in self.placed:
                if skip_own and pl==f"city_{name}": continue
                if skip_own and pl.startswith(f"attr_{idx}_"): continue
                if self._rect_overlap(cx, cy, hw, hh, px, py, phw, phh, 0.04):
                    return False
            if not self._rect_route_check(cx, cy, hw, hh):
                return False
            return True

        all_attrs = [(a[0],'#8B4513',14) for a in prim] + [(a[0],'#27AE60',13) for a in sec]
        start_y = lat + (len(all_attrs)-1)*ATTR_LINE_H/2
        for ai,(an,ac,as_) in enumerate(all_attrs):
            hw_a, hh_a = self._text_wh(an, as_)
            ty = start_y - ai*ATTR_LINE_H
            def _place(bx,by):
                if use_leader:
                    ax.plot([lon+side*cr,bx],[lat,by],color=ac,linewidth=1.5,alpha=0.7,
                            transform=ccrs.PlateCarree(),zorder=15)
                ax.text(bx,by,an,fontproperties=F(as_),color=ac,ha=ha,va='center',zorder=17,path_effects=ST(3.5))
                self._place(bx,by,hw_a,hh_a,f"attr_{idx}_{ai}")
            if check_skip(base_x, ty, hw_a, hh_a, skip_own=True):
                _place(base_x, ty)
            else:
                found=False
                for dy in [0.06,-0.06,0.12,-0.12,0.18,-0.18]:
                    if check_skip(base_x, ty+dy, hw_a, hh_a, skip_own=True):
                        _place(base_x, ty+dy); found=True; break
                if not found:
                    for ex in [0.03,0.06,0.10,0.18]:
                        bx = lon+side*(cr+gap+ex)
                        if check_skip(bx, ty, hw_a, hh_a, skip_own=True):
                            _place(bx, ty); found=True; break
                if not found: _place(base_x, ty)

    # --- 天次（行车段）---
    def _travel_day_placement(self, text, seg_indices):
        ax = self.ax; segs=[SEGMENTS[si] for si in seg_indices]
        if len(segs)==1:
            x1,y1=CITIES[segs[0][0]][2],CITIES[segs[0][0]][1]
            x2,y2=CITIES[segs[0][1]][2],CITIES[segs[0][1]][1]
            mx,my=(x1+x2)/2,(y1+y2)/2
        else:
            total=0; seg_lens=[]
            for s in segs:
                x1,y1=CITIES[s[0]][2],CITIES[s[0]][1]
                x2,y2=CITIES[s[1]][2],CITIES[s[1]][1]
                d=math.hypot(x2-x1,y2-y1); seg_lens.append(((x1,y1),(x2,y2),d)); total+=d
            target=total/2; cum=0; mx=my=0
            for (x1,y1),(x2,y2),d in seg_lens:
                prev=cum; cum+=d
                if cum>=target: frac=(target-prev)/d if d>0 else 0; mx=x1+(x2-x1)*frac; my=y1+(y2-y1)*frac; break
        last=SEGMENTS[seg_indices[-1]]
        x1,y1=CITIES[last[0]][2],CITIES[last[0]][1]; x2,y2=CITIES[last[1]][2],CITIES[last[1]][1]
        dx_,dy_=x2-x1,y2-y1; ln=math.hypot(dx_,dy_); n_x,n_y=-dy_/ln,dx_/ln

        hw_lbl, hh_lbl = self._text_wh(text, 18)

        # 最小偏移：文字矩形外缘不压路线（r_eff+路线半宽+margin）
        r_eff = abs(n_x) * hw_lbl + abs(n_y) * hh_lbl
        base_off = max(0.12, r_eff + 0.03 + 0.06 + 0.001)

        # side: 优先去 dist 对侧
        dist_side=None
        for si in seg_indices:
            for px,py,_,_,pl in self.placed:
                if pl==f"dist_{si}":
                    dist_side=1 if (px-mx)*n_x+(py-my)*n_y>=0 else -1; break
            if dist_side: break
        if dist_side:
            preferred=[-dist_side,dist_side]
        else:
            sc=[]
            for s in [1,-1]:
                nox,noy=self.normal_offset(x1,y1,x2,y2,0.30,s)
                cnt=sum(1 for px,py,_,_,_ in self.placed if self._dist(mx+nox,my+noy,px,py)<0.5)
                sc.append((cnt,s))
            sc.sort(); preferred=[s for _,s in sc]

        def check_day(cx, cy):
            for px,py,phw,phh,pl in self.placed:
                m=0.04
                for si in seg_indices:
                    if pl in (f"dist_{si}",f"time_{si}"):
                        el_side=1 if (px-mx)*n_x+(py-my)*n_y>=0 else -1
                        if el_side!=side: m=0.01
                        break
                if self._rect_overlap(cx, cy, hw_lbl, hh_lbl, px, py, phw, phh, m):
                    return False
            if not self._rect_route_check(cx, cy, hw_lbl, hh_lbl):
                return False
            return True

        for side in preferred:
            nox,noy=self.normal_offset(x1,y1,x2,y2,base_off,side)
            tx,ty=mx+nox,my+noy
            if check_day(tx,ty):
                ha='left' if side>0 else 'right'
                ax.text(tx,ty,text,fontproperties=F(18),color='#8B44AC',ha=ha,va='center',zorder=30,path_effects=ST(4))
                self._place(tx,ty,hw_lbl,hh_lbl,f"day_{text}"); return
        for mult in [1.5,2.0,2.5,3.0]:
            for side in preferred:
                nox,noy=self.normal_offset(x1,y1,x2,y2,base_off,side)
                tx,ty=mx+nox*mult,my+noy*mult
                if check_day(tx,ty):
                    ha='left' if side>0 else 'right'
                    ax.text(tx,ty,text,fontproperties=F(18),color='#8B44AC',ha=ha,va='center',zorder=30,path_effects=ST(4))
                    self._place(tx,ty,hw_lbl,hh_lbl,f"day_{text}"); return
        for dx_,dy_ in [(0.25,0),(-0.25,0),(0,0.25),(0,-0.25),(0.4,0.1),(-0.4,-0.1)]:
            tx,ty=mx+dx_,my+dy_
            if check_day(tx,ty):
                ha='left' if dx_>=0 else 'right'
                ax.text(tx,ty,text,fontproperties=F(18),color='#8B44AC',ha=ha,va='center',zorder=30,path_effects=ST(4))
                self._place(tx,ty,hw_lbl,hh_lbl,f"day_{text}"); return
        for a in [45,135,225,315,0,90,180,270]:
            rad=math.radians(a); tx,ty=mx+0.35*math.cos(rad),my+0.35*math.sin(rad)
            if check_day(tx,ty):
                ha='left' if math.cos(rad)>=0 else 'right'
                ax.text(tx,ty,text,fontproperties=F(18),color='#8B44AC',ha=ha,va='center',zorder=30,path_effects=ST(4))
                self._place(tx,ty,hw_lbl,hh_lbl,f"day_{text}"); return
        ax.text(mx+0.3,my+0.2,text,fontproperties=F(18),color='#8B44AC',ha='left',va='center',zorder=30,path_effects=ST(4))
        self._place(mx+0.3,my+0.2,hw_lbl,hh_lbl,f"day_{text}")

    # --- 休整天 ---
    def _rest_day_placement(self, text, rest_city):
        ax=self.ax; ci=[c[0] for c in CITIES].index(rest_city)
        clon,clat=CITIES[ci][2],CITIES[ci][1]; cr=city_radius(rest_city)
        dn=text.split('（')[0]; cf=f"{rest_city}全天"
        hw_d, hh_d = self._text_wh(dn, 16)
        hw_c, hh_c = self._text_wh(cf, 14)
        LINE=0.10
        city_hw = cr; city_hh = cr * CRS_COS
        def pf(cx, cy):
            # 休整天两行 vs 所有已放置
            for px,py,phw,phh,pl in self.placed:
                if pl.startswith(f"city_{rest_city}"): continue
                if self._rect_overlap(cx, cy, hw_d, hh_d, px, py, phw, phh, 0.03): return False
                if self._rect_overlap(cx, cy-LINE, hw_c, hh_c, px, py, phw, phh, 0.03): return False
            # 不压其他城市
            for ci2,(_,clat2,clon2,*_) in enumerate(CITIES):
                if ci2==ci: continue
                c_r = city_radius(CITIES[ci2][0])
                if self._rect_overlap(cx, cy-LINE, hw_c, hh_c, clon2, clat2, c_r, c_r*CRS_COS, 0.15): return False
            if not self._rect_route_check(cx, cy, hw_d, hh_d): return False
            if not self._rect_route_check(cx, cy-LINE, hw_c, hh_c): return False
            return True
        bd=cr+0.08
        for ex in [0,0.03,0.05,0.08,0.10,0.15,0.20,0.25,0.30,0.35,0.40]:
            dy=bd+ex
            if pf(clon,clat-dy):
                ax.text(clon,clat-dy,dn,fontproperties=F(16),color='#8B44AC',ha='center',va='center',zorder=30,path_effects=ST(4))
                self._place(clon,clat-dy,hw_d,hh_d,f"day_{dn}")
                ax.text(clon,clat-dy-LINE,cf,fontproperties=F(14),color='#8B44AC',ha='center',va='center',zorder=30,path_effects=ST(4))
                self._place(clon,clat-dy-LINE,hw_c,hh_c,f"day_{cf}"); return
        for a in [0,180,90,270,45,135,225,315]:
            rad=math.radians(a); tx=clon+0.5*math.cos(rad); ty=clat+0.5*math.sin(rad)
            if pf(tx,ty):
                ha='center' if abs(math.cos(rad))<0.1 else ('left' if math.cos(rad)>0 else 'right')
                ax.text(tx,ty,dn,fontproperties=F(16),color='#8B44AC',ha=ha,va='center',zorder=30,path_effects=ST(4))
                self._place(tx,ty,hw_d,hh_d,f"day_{dn}")
                ax.text(tx,ty-LINE,cf,fontproperties=F(14),color='#8B44AC',ha=ha,va='center',zorder=30,path_effects=ST(4))
                self._place(tx,ty-LINE,hw_c,hh_c,f"day_{cf}"); return
        ax.text(clon,clat-0.55,dn,fontproperties=F(16),color='#8B44AC',ha='center',va='center',zorder=30,path_effects=ST(4))
        self._place(clon,clat-0.55,hw_d,hh_d,f"day_{dn}")
        ax.text(clon,clat-0.55-LINE,cf,fontproperties=F(14),color='#8B44AC',ha='center',va='center',zorder=30,path_effects=ST(4))
        self._place(clon,clat-0.55-LINE,hw_c,hh_c,f"day_{cf}")

    def place_day_label(self, text, seg_indices, is_rest=False, rest_city=None):
        if is_rest and rest_city: self._rest_day_placement(text, rest_city)
        else: self._travel_day_placement(text, seg_indices)

    def _dist(self, x1, y1, x2, y2):
        return math.hypot(x1-x2, y1-y2)

    def normal_offset(self, x1, y1, x2, y2, offset=0.15, side=1):
        dx, dy = x2-x1, y2-y1; l = math.hypot(dx, dy)
        if l < 0.001: return (0, 0)
        return (-dy/l*side*offset, dx/l*side*offset)

    # --- 距离/时间 ---
    def place_dist_time(self, dist_text, time_text, si):
        ax=self.ax; seg=SEGMENTS[si]
        x1,y1=CITIES[seg[0]][2],CITIES[seg[0]][1]; x2,y2=CITIES[seg[1]][2],CITIES[seg[1]][1]
        mx,my=(x1+x2)/2,(y1+y2)/2; dx_,dy_=x2-x1,y2-y1; ln=math.hypot(dx_,dy_)
        n_x,n_y=-dy_/ln,dx_/ln
        LINE=0.10

        day_prefix=f"day_D{seg[2]}"
        day_side=None
        for px,py,_,_,pl in self.placed:
            if pl==day_prefix or pl.startswith(day_prefix+"（"):
                day_side=1 if (px-mx)*n_x+(py-my)*n_y>=0 else -1; break
        sc=[]
        for side in [1,-1]:
            nox,noy=self.normal_offset(x1,y1,x2,y2,0.25,side)
            cnt=sum(1 for px,py,_,_,_ in self.placed if self._dist(mx+nox,my+noy,px,py)<0.8)
            if day_side and side==day_side: cnt+=5
            sc.append((cnt,side))
        sc.sort(); preferred=[side for _,side in sc]

        hw_d, hh_d = self._text_wh(dist_text, 16)
        hw_t, hh_t = self._text_wh(time_text, 14)

        # 最小偏移：dist/time 都不压路线
        r_eff_d = abs(n_x) * hw_d + abs(n_y) * hh_d
        r_eff_t = abs(n_x) * hw_t + abs(n_y) * hh_t
        base_off = max(0.12, max(r_eff_d, r_eff_t) + 0.03 + 0.06)

        def check_dist(cx, cy, hw, hh):
            for px,py,phw,phh,pl in self.placed:
                m=0.04
                if pl.startswith("day_D"):
                    for si2 in range(len(SEGMENTS)):
                        if pl==f"day_D{SEGMENTS[si2][2]}":
                            el_side=1 if (px-mx)*n_x+(py-my)*n_y>=0 else -1
                            if el_side!=side: m=0.01
                            break
                if self._rect_overlap(cx, cy, hw, hh, px, py, phw, phh, m):
                    return False
            if not self._rect_route_check(cx, cy, hw, hh):
                return False
            return True

        def place_dist(bx,by):
            ax.text(bx,by,dist_text,fontproperties=F(16),color='#2980B9',ha='center',va='center',zorder=30,path_effects=ST(4))
            self._place(bx,by,hw_d,hh_d,f"dist_{si}")
        def place_time(tx,ty):
            ax.text(tx,ty,time_text,fontproperties=F(14),color='#E67E22',ha='center',va='center',zorder=30,path_effects=ST(4))
            self._place(tx,ty,hw_t,hh_t,f"time_{si}")

        # Phase 1
        for mult in [1.0,1.5,2.0,2.5]:
            for side in preferred:
                nox,noy=self.normal_offset(x1,y1,x2,y2,base_off,side)
                bx=mx+nox*mult-0.02; by=my+noy*mult
                if check_dist(bx,by,hw_d,hh_d) and check_dist(bx,by-LINE,hw_t,hh_t):
                    too_close=False
                    for ci,(_,clat,clon,*_) in enumerate(CITIES):
                        c_r=city_radius(CITIES[ci][0])
                        if self._rect_overlap(bx,by-LINE,hw_t,hh_t,clon,clat,c_r,c_r*CRS_COS,0.15):
                            too_close=True; break
                    if not too_close:
                        place_dist(bx,by); place_time(bx,by-LINE); return

        # Phase 2
        for mult in [1.0,1.5,2.0,2.5,3.0]:
            for side in preferred:
                nox,noy=self.normal_offset(x1,y1,x2,y2,base_off,side)
                bx=mx+nox*mult-0.02; by=my+noy*mult
                if check_dist(bx,by,hw_d,hh_d):
                    place_dist(bx,by)
                    for tdx,tdy in [(0,-LINE),(0.15,-LINE),(-0.15,-LINE),(0,-LINE-0.10),(0,-LINE+0.10)]:
                        tx,ty=bx+tdx,by+tdy
                        too_close=False
                        for ci,(_,clat,clon,*_) in enumerate(CITIES):
                            c_r=city_radius(CITIES[ci][0])
                            if self._rect_overlap(tx,ty,hw_t,hh_t,clon,clat,c_r,c_r*CRS_COS,0.15):
                                too_close=True; break
                        if too_close: continue
                        if check_dist(tx,ty,hw_t,hh_t):
                            place_time(tx,ty); return
                    self.placed.pop()
                    break
            else: continue
            break

        # Phase 3
        for a in [180,135,225,90,270,45,315,0]:
            rad=math.radians(a)
            for pr in [0.35,0.50,0.80,1.00]:
                bx=mx+pr*math.cos(rad); by=my+pr*math.sin(rad)
                if check_dist(bx,by,hw_d,hh_d):
                    place_dist(bx,by); place_time(bx,by-LINE); return
        ax.text(mx+0.4,my,dist_text,fontproperties=F(16),color='#2980B9',ha='center',va='center',zorder=30,path_effects=ST(4))
        self._place(mx+0.4,my,hw_d,hh_d,f"dist_{si}")
        ax.text(mx+0.4,my-LINE,time_text,fontproperties=F(14),color='#E67E22',ha='center',va='center',zorder=30,path_effects=ST(4))
        self._place(mx+0.4,my-LINE,hw_t,hh_t,f"time_{si}")

# ========== 主程序 ==========
print("底图...")
fig=plt.figure(figsize=(16,20),facecolor='white')
ax=fig.add_subplot(111,projection=ccrs.PlateCarree())
fig.subplots_adjust(left=0.01,right=0.99,top=0.99,bottom=0.01)
CRS_LAT=round(sum(c[1] for c in CITIES)/len(CITIES))
CRS_COS=math.cos(math.radians(CRS_LAT))

# 自动扩展北边界
day_to_segs_pre={}
for si,seg in enumerate(SEGMENTS):
    d=seg[2]; day_to_segs_pre.setdefault(d,[]).append(si)
all_seg_days_pre=set(day_to_segs_pre.keys())
all_rest_days_pre=set(REST_DAYS.keys())
max_day_pre=max(list(all_seg_days_pre|all_rest_days_pre)+list(DAY_ATTRACTIONS.keys())+[0])
th_table=max_day_pre*LINE_H+0.10
peak_node_top=max(c[1]+city_radius(c[0])+0.04 for c in CITIES)
TABLE_NORTH=peak_node_top+0.03+1.05+th_table
if TABLE_NORTH>MAP_EXTENT[3]:
    print(f"  自动扩展北边界: {MAP_EXTENT[3]:.1f}° → {TABLE_NORTH:.1f}°")
    MAP_EXTENT[3]=TABLE_NORTH
ax.set_extent(MAP_EXTENT)
ax.set_aspect(1.0/CRS_COS,adjustable='box')
ax.add_feature(cfeature.LAND,facecolor='#F8F4EC',zorder=1)
ax.add_feature(cfeature.OCEAN,facecolor='#E8EDF4',zorder=1)
ax.add_feature(cfeature.LAKES,facecolor='#DAE5F0',edgecolor='#AABBCC',linewidth=1.0,zorder=2)
ax.add_feature(cfeature.COASTLINE,edgecolor='#999999',linewidth=2.0,zorder=3)
ax.add_feature(cfeature.RIVERS,edgecolor='#BFD7EA',linewidth=0.8,alpha=0.5,zorder=2)
gl=ax.gridlines(draw_labels=True,linewidth=1.0,color='#BBBBBB',alpha=0.3,linestyle='--')
gl.top_labels=False; gl.right_labels=False
gl.xlabel_style={'size':13,'color':'#999999'}; gl.ylabel_style={'size':13,'color':'#999999'}

# 省界
print("省界...")
from shapely.geometry import box
extent_box=box(MAP_EXTENT[0],MAP_EXTENT[2],MAP_EXTENT[1],MAP_EXTENT[3])
try:
    for rec in shapereader.Reader(shapereader.natural_earth(resolution='50m',category='cultural',name='admin_1_states_provinces')).records():
        iso=rec.attributes.get('iso_3166_2',''); short=iso.split('-')[-1] if '-' in iso else ''
        if not short or not extent_box.intersects(rec.geometry): continue
        ax.add_geometries([rec.geometry],crs=ccrs.PlateCarree(),facecolor='none',edgecolor='#888888',linewidth=2,alpha=0.25,zorder=4)
        cx=(rec.geometry.bounds[0]+rec.geometry.bounds[2])/2; cy=(rec.geometry.bounds[1]+rec.geometry.bounds[3])/2
        ax.text(cx,cy,rec.attributes.get('name',''),fontproperties=F(28),color='#888888',alpha=0.20,ha='center',va='center',zorder=4)
except Exception as e: print(f"省界: {e}")

# 路线
print("路线...")
for s_idx,e_idx,day,_,_ in SEGMENTS:
    color=DAY_COLORS.get(day,'#888888')
    x1,y1=CITIES[s_idx][2],CITIES[s_idx][1]; x2,y2=CITIES[e_idx][2],CITIES[e_idx][1]
    for gw,ga in [(22,0.06),(16,0.12),(10,0.25)]:
        ax.plot([x1,x2],[y1,y2],color=color,linewidth=gw,alpha=ga,solid_capstyle='round',zorder=5)
    ax.plot([x1,x2],[y1,y2],color=color,linewidth=6,alpha=1,solid_capstyle='round',zorder=6,path_effects=[pe.withStroke(linewidth=8,foreground='white',alpha=0.35)])

layout=Layout(ax)

# 注册路线段到碰撞系统（去重：往返段只注册一次）
seen_pairs=set()
for s_idx,e_idx,day,_,_ in SEGMENTS:
    key = tuple(sorted([s_idx, e_idx]))
    if key in seen_pairs: continue
    seen_pairs.add(key)
    x1,y1=CITIES[s_idx][2],CITIES[s_idx][1]; x2,y2=CITIES[e_idx][2],CITIES[e_idx][1]
    layout.route_segs.append((x1,y1,x2,y2,0.03))  # 路线半宽0.03°

# 天次索引
day_to_segs={}
for si,seg in enumerate(SEGMENTS): d=seg[2]; day_to_segs.setdefault(d,[]).append(si)
all_seg_days=set(day_to_segs.keys())
all_rest_days=set(REST_DAYS.keys())
max_day=max(list(all_seg_days|all_rest_days)+list(DAY_ATTRACTIONS.keys())+[0])
all_days=sorted(range(1,max_day+1))

# 行程表
print("行程表...")
all_lines=[]
for day in all_days:
    seg_indices=day_to_segs.get(day,[])
    is_rest=day in REST_DAYS; rc=REST_DAYS.get(day)
    if is_rest and rc:
        if day in DAY_ATTRACTIONS: pa,sa=DAY_ATTRACTIONS[day]; aa=pa+sa
        else: ci=[c[0] for c in CITIES].index(rc); aa=[a[0] for a in CITIES[ci][3]]+[a[0] for a in CITIES[ci][4]]
        line=f"D{day}  {rc}全天" + (f"  ·  {'、'.join(aa)}" if aa else "")
        all_lines.append(line)
    elif seg_indices:
        cr=[]; aa=[]
        for si in seg_indices:
            s=SEGMENTS[si]
            if not cr: cr.append(CITIES[s[0]][0])
            cr.append(CITIES[s[1]][0]); ci=s[1]
            if day in DAY_ATTRACTIONS: pa,sa=DAY_ATTRACTIONS[day]
            else: pa=[a[0] for a in CITIES[ci][3]]; sa=[a[0] for a in CITIES[ci][4]]
            aa.extend(pa+sa)
        line=f"D{day}  {'→'.join(cr)}" + (f"  ·  {'、'.join(dict.fromkeys(aa))}" if aa else "")
        all_lines.append(line)
    else:
        pm=[d for d in sorted(all_seg_days|all_rest_days|{0}) if d<day]
        if pm:
            pd=pm[-1]
            if pd in day_to_segs: city=CITIES[SEGMENTS[day_to_segs[pd][-1]][1]][0]
            elif pd in REST_DAYS: city=REST_DAYS[pd]
            else: city=""
            if day in DAY_ATTRACTIONS:
                pa,sa=DAY_ATTRACTIONS[day]; aa=pa+sa
                line=f"D{day}  {city}" + (f"  ·  {'、'.join(aa)}" if aa else "")
            else: line=f"D{day}  {city}"
            all_lines.append(line)

def _txt_ok(cx,cy,tw,th):
    l,r=cx,cx+tw; t,b=cy+th/2,cy-th/2
    for px,py,phw,phh,_ in layout.placed:
        # 矩形最近点到圆心的距离（保留原逻辑）
        dx=max(l-px,0,px-r); dy=max(b-py,0,py-t)
        if math.hypot(dx,dy)<max(phw,phh)+0.08: return False
    return True

def _find_spot(lines):
    tw=min(max(len(l) for l in lines)*CH_W+0.3,3.8)
    th=len(lines)*LINE_H+0.10
    w,e,s,n=MAP_EXTENT; sub_y=n-0.9
    CX_MIN=w+0.2; CX_MAX=e-0.2-tw; CY_MAX=sub_y-0.15-th/2; CY_MIN=s+0.2+th/2
    if CX_MIN>CX_MAX or CY_MIN>CY_MAX: return None
    best,best_s=None,999; y=CY_MAX
    while y>=CY_MIN:
        x=CX_MIN
        while x<=CX_MAX:
            bx,by=x+tw/2,y
            cnt=sum(1 for px,py,_,_,_ in layout.placed if math.hypot(bx-px,by-py)<1.0)
            cnt+=sum(3 for _,clat,clon,*_ in CITIES if math.hypot(clon-bx,clat-by)<1.0)
            sc=cnt+(n-y)*0.02
            if sc<best_s and _txt_ok(x,y,tw,th): best,best_s=(x,y),sc
            x+=0.15
        y-=0.15
    return (*best,tw,th) if best else None

def _render(lines,cx,cy):
    tw=min(max(len(l) for l in lines)*CH_W+0.3,3.8)
    th=len(lines)*LINE_H+0.10
    for i,line in enumerate(lines):
        yy=cy+th/2-0.08-i*LINE_H
        ax.text(cx,yy,line,fontproperties=F(FONT_SZ),color='#2C3E50',ha='left',va='top',zorder=95,path_effects=ST(1.5))
    layout._place(cx+tw/2,cy,tw/2,th/2,"iti")
    return tw,th

placed=_find_spot(all_lines)
if placed: _render(all_lines,*placed[:2]); print(f"  单列: ({placed[0]:.1f},{placed[1]:.1f})")
else:
    mid=len(all_lines)//2; col1,col2=all_lines[:mid],all_lines[mid:]
    sp1=_find_spot(col1)
    if sp1:
        cx1,cy1,_,_=sp1
        mw1=min(max(len(l) for l in col1)*CH_W+0.3,3.8); mw2=min(max(len(l) for l in col2)*CH_W+0.3,3.8)
        cx2=cx1+mw1+0.2; l2,r2=cx2,cx2+mw2
        th1=len(col1)*LINE_H+0.10; t2,b2=cy1+th1/2,cy1-th1/2
        ok=all(not (math.hypot(max(l2-px,0,px-r2),max(b2-py,0,py-t2))<max(phw,phh)+0.08) for px,py,phw,phh,_ in layout.placed)
        if ok: _render(col1,cx1,cy1); _render(col2,cx2,cy1); print(f"  双列: ({cx1:.1f},{cy1:.1f}) ({cx2:.1f},{cy1:.1f})"); placed=True
if not placed: print("  行程表：未找到位置")

# ========== 图形元素（城市→景点→天次→dist/time）==========
print("城市...")
for idx,(name,lat,lon,prim,sec,pc) in enumerate(CITIES):
    layout.place_city(name,lat,lon,pc)
print("景点...")
for idx,(name,lat,lon,prim,sec,pc) in enumerate(CITIES):
    if prim or sec: layout.place_attractions(idx,name,lat,lon,prim,sec,pc)
print("天次...")
for day in all_days:
    seg_indices=day_to_segs.get(day,[])
    if day in REST_DAYS: layout.place_day_label(f"D{day}（{REST_DAYS[day]}全天）",seg_indices,True,REST_DAYS[day])
    else: layout.place_day_label(f"D{day}",seg_indices)
# 往返段去重：只放一次 dist/time（start<end 的方向）
round_trip_returns=set()
for si,(s,e,_,_,_) in enumerate(SEGMENTS):
    for si2,(s2,e2,_,_,_) in enumerate(SEGMENTS):
        if si!=si2 and s==e2 and e==s2:
            if s>e: round_trip_returns.add(si)
            break

print("距离/时间...")
for si,seg in enumerate(SEGMENTS):
    if si in round_trip_returns: continue
    layout.place_dist_time(seg[3],seg[4],si)

# 标题
print("标题...")
center_x=(MAP_EXTENT[0]+MAP_EXTENT[1])/2; title_y=MAP_EXTENT[3]-0.6; sub_y=MAP_EXTENT[3]-0.9
ax.text(center_x,title_y,f"{CITIES[0][0]}→{CITIES[-1][0]} · {THEME_TITLE}",fontproperties=F(30),color='#2C3E50',ha='center',va='bottom',zorder=100,path_effects=ST(6))
total_seg_km=sum(int(s[3].rstrip('km')) for s in SEGMENTS)
ax.text(center_x,sub_y,f"{THEME_SUB}  ·  {len(all_days)}天 · 约{total_seg_km}km",fontproperties=F(18),color='#7F8C8D',ha='center',va='bottom',zorder=100,path_effects=ST(4))

# 输出
print("保存...")
rn=f"{CITIES[0][0]}_{CITIES[-1][0]}_{THEME_TITLE}"
OUT=os.path.expanduser(f'~/.hermes/cache/documents/{rn}.png')
DEST=os.path.expanduser(f'~/Desktop/{rn}.png')
plt.savefig(OUT,dpi=150,facecolor='white'); plt.close()
import shutil; shutil.copy2(OUT,DEST)
mb=os.path.getsize(OUT)/1024/1024; print(f"完成! {mb:.1f} MB -> {DEST}")
