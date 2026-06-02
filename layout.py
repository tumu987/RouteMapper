"""布局引擎：碰撞检测 + 逐层放置 + 密度感知。"""
import math
from typing import List, Tuple, Optional

import config as _layout_cfg
# 引用 config 模块确保取值始终是最新的
ATTR_PRIM_COLOR = _layout_cfg.ATTR_PRIM_COLOR
ATTR_SEC_COLOR = _layout_cfg.ATTR_SEC_COLOR


class LayoutEngine:
    """管理元素放置位置和碰撞检测。

    所有坐标使用地图坐标（经度、纬度）。
    placed 列表存储已放置元素的矩形包围盒：[(cx, cy, hw, hh, label), ...]
    route_segs 列表存储路线段用于碰撞检测：[(x1, y1, x2, y2, half_width), ...]
    """

    # ── 布局常量（可被实例属性覆盖以缩放）──
    ROUTE_HW = 0.07
    MARGIN_PLACED = 0.06
    MARGIN_ROUTE = 0.10
    MARGIN_LABEL = 0.10
    PERP_DIST_MULTS = (1.0, 1.25, 1.55, 1.9)
    PERP_DIST_MULTS_SHORT = (1.0, 1.25, 1.55)
    MIN_DIST_EXTRA = 0.10
    MAX_SLIDE_FRAC = 0.15
    MAX_SLIDE_ABS = 0.12
    FONT_DAY = 16
    FONT_DIST = 14
    FONT_TIME = 14
    FONT_PRIM = 14
    FONT_SEC = 12
    LINE_GAP = 0.10
    # 景点搜索距离
    ATTR_SEARCH_DISTS = (0.06, 0.10, 0.16, 0.24)
    ATTR_FALLBACK_DISTS = (0.20, 0.30, 0.45, 0.65)
    GROUPED_GAP_DISTS = (0.05, 0.12, 0.22, 0.35)
    # 松弛搜索环
    def __init__(self, px_per_deg: float = 200.0, output_dpi: float = 100.0):
        self.placed: List[Tuple[float, float, float, float, str]] = []
        self.route_segs: List[Tuple[float, float, float, float, float]] = []
        self.route_midpoints: List[Tuple[float, float]] = []  # 路线中点，用于景点回避
        self.px_per_deg = px_per_deg
        # 文字像素 = pt × DPI / 72; 中文字宽≈高, 英文/数字字宽≈高×0.6
        self.px_per_pt = output_dpi / 72.0

    # ── 文字尺寸 ──

    def text_half_size(self, text: str, pt: float) -> Tuple[float, float]:
        """精确计算：文字像素 = pt × DPI/72，转为地图坐标。"""
        cn = sum(1 for c in text if '一' <= c <= '鿿' or '　' <= c <= '〿')
        en = len(text) - cn
        h_px = pt * self.px_per_pt
        w_px = cn * h_px + en * h_px * 0.6
        hw = (w_px / self.px_per_deg) / 2
        hh = (h_px / self.px_per_deg) / 2
        return hw, hh

    # ── 碰撞检测 ──

    @staticmethod
    def rect_overlap(cx1: float, cy1: float, hw1: float, hh1: float,
                     cx2: float, cy2: float, hw2: float, hh2: float,
                     margin: float = 0.0) -> bool:
        """两个轴对齐矩形是否重叠。"""
        return (abs(cx1 - cx2) < hw1 + hw2 + margin and
                abs(cy1 - cy2) < hh1 + hh2 + margin)

    @staticmethod
    def dist_to_segment(x: float, y: float,
                        x1: float, y1: float,
                        x2: float, y2: float) -> float:
        """点到线段的最短距离。"""
        dx, dy = x2 - x1, y2 - y1
        if abs(dx) < 1e-8 and abs(dy) < 1e-8:
            return math.hypot(x - x1, y - y1)
        t = ((x - x1) * dx + (y - y1) * dy) / (dx * dx + dy * dy)
        if t <= 0:
            return math.hypot(x - x1, y - y1)
        if t >= 1:
            return math.hypot(x - x2, y - y2)
        px = x1 + t * dx
        py = y1 + t * dy
        return math.hypot(x - px, y - py)

    @staticmethod
    def _same_seg(ax1: float, ay1: float, ax2: float, ay2: float,
                  bx1: float, by1: float, bx2: float, by2: float,
                  tol: float = 0.01) -> bool:
        """判断两条线段是否为同一条（端点足够接近）。"""
        return (abs(ax1 - bx1) < tol and abs(ay1 - by1) < tol and
                abs(ax2 - bx2) < tol and abs(ay2 - by2) < tol)

    def route_collision(self, cx: float, cy: float,
                        hw: float, hh: float, margin: float = 0.06,
                        skip_x1: float = None, skip_y1: float = None,
                        skip_x2: float = None, skip_y2: float = None) -> bool:
        """检查矩形是否与任何路线段碰撞（可跳过自己的段）。"""
        for x1, y1, x2, y2, hlw in self.route_segs:
            if skip_x1 is not None and self._same_seg(
                    x1, y1, x2, y2, skip_x1, skip_y1, skip_x2, skip_y2):
                continue
            d = self.dist_to_segment(cx, cy, x1, y1, x2, y2)
            dx, dy = x2 - x1, y2 - y1
            length = math.hypot(dx, dy)
            if length < 1e-8:
                continue
            nx, ny = -dy / length, dx / length
            r_eff = abs(nx) * hw + abs(ny) * hh
            if d <= r_eff + hlw + margin:
                return True
        return False

    # ── 放置管理 ──

    @staticmethod
    def _label_kind(label: str) -> str:
        """返回标签的类别前缀：city/attr/day/dist/time/iti"""
        if not label:
            return ""
        if label.startswith("city_"): return "city"
        if label.startswith("attr_"): return "attr"
        if label.startswith("day_"): return "day"
        if label.startswith("dist_"): return "dist"
        if label.startswith("time_"): return "time"
        if label.startswith("iti"): return "iti"
        return label.split("_")[0] if "_" in label else label

    def is_position_clear(self, cx: float, cy: float, hw: float, hh: float,
                          margin: float = None,
                          route_margin: float = 0.06,
                          own_x1=None, own_y1=None, own_x2=None, own_y2=None,
                          my_kind: str = "") -> bool:
        """检查位置是否可用。

        同类型元素允许更近（margin_same），不同类型保持更多间距（margin_diff）。
        """
        MARGIN_SAME = 0.15
        MARGIN_DIFF = 0.15
        if margin is not None:
            MARGIN_SAME = MARGIN_DIFF = margin

        for pcx, pcy, phw, phh, pl in self.placed:
            pk = self._label_kind(pl)
            m = MARGIN_DIFF if (my_kind and pk and my_kind != pk) else MARGIN_SAME
            if self.rect_overlap(cx, cy, hw, hh, pcx, pcy, phw, phh, m):
                return False
        if self.route_collision(cx, cy, hw, hh, route_margin, own_x1, own_y1, own_x2, own_y2):
            return False
        return True

    def place(self, cx: float, cy: float, hw: float, hh: float,
              label: str = "") -> None:
        """注册已放置元素。"""
        self.placed.append((cx, cy, hw, hh, label))

    def relax_overlaps(self, max_iter: int = 10) -> int:
        """全局松弛：反复检测重叠并移位，直到无重叠。

        dist/time 作为配对一起移动。优先级：day > dist/time > attr。
        优化：预计算标签类别、跳过同类型对（同优先级无法互移）。
        """
        PRIORITY = {"day": 0, "dist": 1, "time": 1, "attr": 2}
        OVERLAP_MARGIN = self.LINE_GAP
        SEARCH_RING = [(d * math.cos(a), d * math.sin(a))
                       for d in (0.08, 0.16, 0.28, 0.45, 0.70, 1.0, 1.5)
                       for a in (0, math.pi/4, math.pi/2, 3*math.pi/4, math.pi,
                                 5*math.pi/4, 3*math.pi/2, 7*math.pi/4)]
        SMALL_RING = [(d * math.cos(a), d * math.sin(a))
                      for d in (0.04, 0.08, 0.12)
                      for a in (0, math.pi/2, math.pi, 3*math.pi/2)]

        def _find_partner(label, placed, label_idx, kinds):
            k = kinds[label_idx]
            if k in ("dist", "time"):
                num = label.split("_")[1]
                other = f"{'time' if k == 'dist' else 'dist'}_{num}"
                for pi, p in enumerate(placed):
                    if p[4] == other:
                        return pi, (k == "dist")
            if k == "day":
                for pi, (px, py, _, _, pl) in enumerate(placed):
                    if pi == label_idx:
                        continue
                    if kinds[pi] == "day" and abs(py - placed[label_idx][1]) < self.LINE_GAP * 1.5:
                        return pi, False
            return None, False

        def _try_move(idx, cx, cy, hw, hh, label, ring, fixes_list, moved_set, kinds):
            for dx, dy in ring:
                nx, ny = cx + dx, cy + dy
                pidx, _ = _find_partner(label, self.placed, idx, kinds)
                pnx = pny = 0
                if pidx is not None:
                    pnx = self.placed[pidx][0] + dx
                    pny = self.placed[pidx][1] + dy
                ok_new = True
                for k, (px, py, phw, phh, pl) in enumerate(self.placed):
                    if k == idx or (pidx is not None and k == pidx):
                        continue
                    # 快速跳过：距离过远不可能重叠的元素
                    if abs(nx - px) >= hw + phw + OVERLAP_MARGIN or \
                       abs(ny - py) >= hh + phh + OVERLAP_MARGIN:
                        continue
                    if abs(nx - px) < hw + phw + OVERLAP_MARGIN and \
                       abs(ny - py) < hh + phh + OVERLAP_MARGIN:
                        ok_new = False; break
                    if pidx is not None:
                        if abs(pnx - px) >= self.placed[pidx][2] + phw + OVERLAP_MARGIN or \
                           abs(pny - py) >= self.placed[pidx][3] + phh + OVERLAP_MARGIN:
                            continue
                        if abs(pnx - px) < self.placed[pidx][2] + phw + OVERLAP_MARGIN and \
                           abs(pny - py) < self.placed[pidx][3] + phh + OVERLAP_MARGIN:
                            ok_new = False; break
                if ok_new and not self.route_collision(nx, ny, hw, hh, self.MARGIN_PLACED):
                    fixes_list.append((idx, nx, ny))
                    moved_set.add(idx)
                    if pidx is not None:
                        fixes_list.append((pidx, pnx, pny))
                        moved_set.add(pidx)
                    return True
            return False

        total_fixed = 0
        for _ in range(max_iter):
            fixes = []
            moved = set()
            n = len(self.placed)
            # 预计算所有标签类别，避免 O(n²) 次字符串操作
            kinds = [self._label_kind(p[4]) for p in self.placed]

            for i in range(n):
                if i in moved:
                    continue
                cx, cy, hw, hh, label = self.placed[i]
                my_kind = kinds[i]
                my_pri = PRIORITY.get(my_kind, 9)
                for j in range(n):
                    if i == j or j in moved:
                        continue
                    # 同类型跳过：同优先级无法互移
                    if my_kind == kinds[j] or my_kind == "" or kinds[j] == "":
                        continue
                    ox, oy, ohw, ohh = self.placed[j][:4]
                    if abs(cx - ox) < hw + ohw + OVERLAP_MARGIN and \
                       abs(cy - oy) < hh + ohh + OVERLAP_MARGIN:
                        if my_pri > PRIORITY.get(kinds[j], 9):
                            if _try_move(i, cx, cy, hw, hh, label, SEARCH_RING, fixes, moved, kinds):
                                break
                            # 景点移不了->微调堵路的day/dist/time腾空间
                            if _try_move(j, ox, oy, ohw, ohh, self.placed[j][4], SMALL_RING, fixes, moved, kinds):
                                break

            if not fixes:
                break

            for idx, nx, ny in fixes:
                old = self.placed[idx]
                self.placed[idx] = (nx, ny, old[2], old[3], old[4])
            total_fixed += len(fixes)

        return total_fixed

    def budge_blockers(self, anchor_x: float, anchor_y: float,
                       radius: float = 0.5) -> int:
        """景点放不下时，尝试微调附近的天次/距离/时间来腾空间。

        返回成功腾挪的元素数。
        """
        # 找到附近的 day/dist/time 元素
        nearby = []
        for i, (cx, cy, hw, hh, label) in enumerate(self.placed):
            k = self._label_kind(label)
            if k in ("day", "dist", "time"):
                d = math.hypot(cx - anchor_x, cy - anchor_y)
                if d < radius:
                    nearby.append((i, cx, cy, hw, hh, label, k))

        if not nearby:
            return 0

        budged = 0
        for idx, cx, cy, hw, hh, label, kind in nearby:
            # 螺旋搜索微调位置
            for dist in (0.06, 0.10, 0.15, 0.22):
                for a in (0, math.pi/2, math.pi, 3*math.pi/2, math.pi/4, 3*math.pi/4, 5*math.pi/4, 7*math.pi/4):
                    nx = cx + dist * math.cos(a)
                    ny = cy + dist * math.sin(a)
                    ok = True
                    for px, py, phw, phh, pl in self.placed:
                        if pl == label:
                            continue
                        pk = self._label_kind(pl)
                        m = 0.08 if (pk and pk != kind) else 0.04
                        if abs(nx - px) < hw + phw + m and abs(ny - py) < hh + phh + m:
                            ok = False
                            break
                    if ok and not self.route_collision(nx, ny, hw, hh, 0.06):
                        # 更新位置：直接赋值替换
                        self.placed[idx] = (nx, ny, hw, hh, label)
                        budged += 1
                        break
                if budged:
                    break
        return budged

    def register_route(self, x1: float, y1: float,
                       x2: float, y2: float,
                       half_width: float = 0.03) -> None:
        """注册路线段到碰撞系统，同时记录中点供景点回避。"""
        self.route_segs.append((x1, y1, x2, y2, half_width))
        self.route_midpoints.append(((x1+x2)/2, (y1+y2)/2))

    # ── 辅助几何 ──

    def place_perpendicular(self, mx: float, my: float,
                            x1: float, y1: float, x2: float, y2: float,
                            hw: float, hh: float,
                            preferred_side: int,
                            margin: float = None,
                            route_margin: float = None,
                            my_kind: str = "") -> Optional[Tuple[float, float, int]]:
        """在路线附近放置标签。三阶段：中点垂线 → 滑动 → 远距离兜底。"""
        if margin is None:
            margin = self.MARGIN_LABEL
        if route_margin is None:
            route_margin = self.MARGIN_ROUTE

        dx, dy = x2 - x1, y2 - y1
        length = math.hypot(dx, dy)
        if length < 1e-6:
            return None
        nx, ny = -dy / length, dx / length
        ux, uy = dx / length, dy / length

        r_eff = abs(nx) * hw + abs(ny) * hh
        min_dist = self.ROUTE_HW + r_eff + self.MIN_DIST_EXTRA

        # 阶段1：中点垂线，两侧，递进距离
        for side in (preferred_side, -preferred_side):
            for dist_mult in self.PERP_DIST_MULTS:
                tx = mx + nx * min_dist * dist_mult * side
                ty = my + ny * min_dist * dist_mult * side
                if self.is_position_clear(tx, ty, hw, hh, margin, route_margin,
                                          x1, y1, x2, y2, my_kind):
                    return tx, ty, side

        # 阶段2：沿路线滑动避开冲突（≤MAX_SLIDE_ABS°）
        max_slide = min(length * self.MAX_SLIDE_FRAC, self.MAX_SLIDE_ABS)
        for side in (preferred_side, -preferred_side):
            for along in (0.04, -0.04, 0.08, -0.08, 0.12, -0.12):
                if abs(along) > max_slide:
                    continue
                ax = mx + ux * along
                ay = my + uy * along
                for dist_mult in self.PERP_DIST_MULTS_SHORT:
                    tx = ax + nx * min_dist * dist_mult * side
                    ty = ay + ny * min_dist * dist_mult * side
                    if self.is_position_clear(tx, ty, hw, hh, margin, route_margin,
                                              x1, y1, x2, y2, my_kind):
                        return tx, ty, side

        # 阶段3：远距离兜底（放宽碰撞容差）
        for side in (-1, 1):
            for dist_mult in (2.5, 3.5, 4.5, 6.0, 8.0):
                tx = mx + nx * min_dist * dist_mult * side
                ty = my + ny * min_dist * dist_mult * side
                if self.is_position_clear(tx, ty, hw, hh, self.MARGIN_PLACED / 2,
                                          route_margin, x1, y1, x2, y2, my_kind):
                    return tx, ty, side
            # 最后的固定偏移尝试
            tx = mx + nx * (self.ROUTE_HW * 3 + 0.1) * side
            ty = my + ny * (self.ROUTE_HW * 3 + 0.1) * side
            if self.is_position_clear(tx, ty, hw, hh, self.MARGIN_PLACED / 2,
                                      route_margin, x1, y1, x2, y2, my_kind):
                return tx, ty, side

        return None

    # ── 天次放置 ──

    def place_travel_day(self, text: str, seg_indices: List[int],
                         all_segments: list, cities: list) -> Tuple[float, float, str]:
        """放置行车段天次——段中点垂线上。"""
        segs = [all_segments[si] for si in seg_indices]
        if len(segs) == 1:
            s = segs[0]
            x1, y1 = cities[s["from_index"]]["lon"], cities[s["from_index"]]["lat"]
            x2, y2 = cities[s["to_index"]]["lon"], cities[s["to_index"]]["lat"]
            mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        else:
            total = 0.0; seg_data = []
            for s in segs:
                sx1, sy1 = cities[s["from_index"]]["lon"], cities[s["from_index"]]["lat"]
                sx2, sy2 = cities[s["to_index"]]["lon"], cities[s["to_index"]]["lat"]
                d = math.hypot(sx2 - sx1, sy2 - sy1)
                seg_data.append(((sx1, sy1), (sx2, sy2), d)); total += d
            target = total / 2; cum = 0.0; mx = my = 0.0
            for (sx1, sy1), (sx2, sy2), d in seg_data:
                prev = cum; cum += d
                if cum >= target:
                    frac = (target - prev) / d if d > 0 else 0
                    mx = sx1 + (sx2 - sx1) * frac; my = sy1 + (sy2 - sy1) * frac
                    break

        last = segs[-1]
        x1, y1 = cities[last["from_index"]]["lon"], cities[last["from_index"]]["lat"]
        x2, y2 = cities[last["to_index"]]["lon"], cities[last["to_index"]]["lat"]

        hw, hh = self.text_half_size(text, self.FONT_DAY)
        # 天次固定右侧（1），三阶段级联 place_perpendicular 覆盖所有距离
        result = self.place_perpendicular(mx, my, x1, y1, x2, y2, hw, hh, 1,
                                          my_kind="day")
        if result:
            tx, ty, side = result
        else:
            # 最终兜底：放弃碰撞检测
            tx = mx + 0.2
            ty = my + 0.15
            side = 1

        ha = "left" if side > 0 else "right"
        self.place(tx, ty, hw, hh, f"day_{text}")
        return tx, ty, ha

    def place_rest_day(self, day_num: str, city_name: str,
                       cities: list, crs_cos: float,
                       day_display: str = None,
                       city_display: str = None) -> Tuple[float, float, str, float, float]:
        """放置休息日标注（城市正下方）。

        Returns:
            (d_x, d_y, d_ha, c_x, c_y) — 天次位置和城市全称位置
        """
        ci_list = [i for i, c in enumerate(cities) if c["name"] == city_name]
        if not ci_list:
            raise ValueError(f"城市 '{city_name}' 不在 cities 列表中")
        ci = ci_list[0]
        clon, clat = cities[ci]["lon"], cities[ci]["lat"]
        cr = _layout_cfg.CITY_RADIUS
        disp_day = day_display if day_display else day_num
        disp_city = city_display if city_display else f"{city_name}全天"

        hw_d, hh_d = self.text_half_size(disp_day, self.FONT_DAY)
        hw_c, hh_c = self.text_half_size(disp_city, self.FONT_DIST)
        LINE = self.LINE_GAP

        def pair_ok(bx: float, by: float) -> bool:
            for px, py, phw, phh, pl in self.placed:
                if pl.startswith(f"city_{city_name}"):
                    continue
                pk = self._label_kind(pl)
                m = 0.10 if (pk and pk != "day") else 0.06
                if self.rect_overlap(bx, by, hw_d, hh_d, px, py, phw, phh, m):
                    return False
                if self.rect_overlap(bx, by - LINE, hw_c, hh_c, px, py, phw, phh, m):
                    return False
            if self.route_collision(bx, by, hw_d, hh_d):
                return False
            if self.route_collision(bx, by - LINE, hw_c, hh_c):
                return False
            # 不压其他城市
            for ci2, c2 in enumerate(cities):
                if ci2 == ci:
                    continue
                if abs(bx - c2["lon"]) < hw_c + _layout_cfg.CITY_RADIUS + 0.15 and \
                   abs(by - LINE - c2["lat"]) < hh_c + _layout_cfg.CITY_RADIUS * crs_cos + 0.15:
                    return False
            return True

        base_dy = cr + 0.08
        for extra in (0, 0.03, 0.05, 0.08, 0.10, 0.15, 0.20):
            dy = base_dy + extra
            if pair_ok(clon, clat - dy):
                self.place(clon, clat - dy, hw_d, hh_d, f"day_{disp_day}")
                self.place(clon, clat - dy - LINE, hw_c, hh_c, f"day_{disp_city}")
                return clon, clat - dy, "center", clon, clat - dy - LINE

        # 下→(左/右/上中最空的)→8方向
        candidates = []
        for side_name, bx_fn, by_fn, ha_val in [
            ("左", lambda d: clon - (cr + d), lambda: clat, "right"),
            ("右", lambda d: clon + (cr + d), lambda: clat, "left"),
            ("上", lambda: clon, lambda d: clat + (cr + d), "center"),
        ]:
            for offset in (0.08, 0.12, 0.18, 0.25, 0.35, 0.50):
                if side_name == "上":
                    bx, by = bx_fn(), by_fn(offset)
                else:
                    bx, by = bx_fn(offset), by_fn()
                if pair_ok(bx, by):
                    score = offset  # 越小越好（越近）
                    candidates.append((score, bx, by, ha_val))
                    break  # 此方向找到最近的就停

        if candidates:
            candidates.sort()  # 选最近的
            score, bx, by, ha_val = candidates[0]
            self.place(bx, by, hw_d, hh_d, f"day_{disp_day}")
            self.place(bx, by - LINE, hw_c, hh_c, f"day_{disp_city}")
            return bx, by, ha_val, bx, by - LINE

        # 最终 8 方向 fallback
        for angle_deg in (0, 90, 180, 270, 45, 135, 225, 315):
            rad = math.radians(angle_deg)
            for dist in (0.35, 0.55, 0.80):
                tx = clon + dist * math.cos(rad)
                ty = clat + dist * math.sin(rad)
                if pair_ok(tx, ty):
                    ha = "center" if abs(math.cos(rad)) < 0.1 else ("left" if math.cos(rad) > 0 else "right")
                    self.place(tx, ty, hw_d, hh_d, f"day_{disp_day}")
                    self.place(tx, ty - LINE, hw_c, hh_c, f"day_{disp_city}")
                    return tx, ty, ha, tx, ty - LINE

        # 最后手段
        tx, ty = clon + 0.5, clat
        self.place(tx, ty, hw_d, hh_d, f"day_{disp_day}")
        self.place(tx, ty - LINE, hw_c, hh_c, f"day_{disp_city}")
        return tx, ty, "left", tx, ty - LINE

    # ── 距离/时间放置 ──

    def place_dist_time(self, dist_text: str, time_text: str,
                        seg_index: int, all_segments: list,
                        cities: list) -> Tuple[float, float, float, float]:
        """距离和时间——段中点垂线上，不滑动。"""
        seg = all_segments[seg_index]
        x1, y1 = cities[seg["from_index"]]["lon"], cities[seg["from_index"]]["lat"]
        x2, y2 = cities[seg["to_index"]]["lon"], cities[seg["to_index"]]["lat"]
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        dx, dy = x2 - x1, y2 - y1
        length = math.hypot(dx, dy)
        nx, ny = -dy / length, dx / length

        hw_d, hh_d = self.text_half_size(dist_text, self.FONT_DIST)
        hw_t, hh_t = self.text_half_size(time_text, self.FONT_TIME)
        LINE = self.LINE_GAP

        r_eff = abs(nx) * hw_d + abs(ny) * hh_d
        min_dist = self.ROUTE_HW + r_eff + self.MIN_DIST_EXTRA

        def _label_overlap(bx, by, hw, hh, kind):
            """检查标签是否与任何已放置元素重叠（跨类型加大边距）。"""
            for pcx, pcy, phw, phh, pl in self.placed:
                pk = self._label_kind(pl)
                m = 0.06 if (pk and kind and pk != kind) else self.MARGIN_LABEL
                if self.rect_overlap(bx, by, hw, hh, pcx, pcy, phw, phh, m):
                    return True
            return False

        def pair_ok(bx, by):
            if _label_overlap(bx, by, hw_d, hh_d, "dist"):
                return False
            # 检查距离标签-路线碰撞（跳过自己的路线段）
            for rx1, ry1, rx2, ry2, hlw in self.route_segs:
                if self._same_seg(rx1, ry1, rx2, ry2, x1, y1, x2, y2):
                    continue
                d = self.dist_to_segment(bx, by, rx1, ry1, rx2, ry2)
                rdx, rdy = rx2 - rx1, ry2 - ry1
                rlen = math.hypot(rdx, rdy)
                if rlen < 1e-8:
                    continue
                rnx, rny = -rdy / rlen, rdx / rlen
                r_eff2 = abs(rnx) * hw_d + abs(rny) * hh_d
                if d <= r_eff2 + hlw + 0.08:
                    return False
            if _label_overlap(bx, by - LINE, hw_t, hh_t, "time"):
                return False
            # 检查时间标签-路线碰撞（跳过自己的路线段）
            for rx1, ry1, rx2, ry2, hlw in self.route_segs:
                if self._same_seg(rx1, ry1, rx2, ry2, x1, y1, x2, y2):
                    continue
                d = self.dist_to_segment(bx, by - LINE, rx1, ry1, rx2, ry2)
                rdx, rdy = rx2 - rx1, ry2 - ry1
                rlen = math.hypot(rdx, rdy)
                if rlen < 1e-8:
                    continue
                rnx, rny = -rdy / rlen, rdx / rlen
                r_eff2 = abs(rnx) * hw_t + abs(rny) * hh_t
                if d <= r_eff2 + hlw + 0.08:
                    return False
            for c in cities:
                if abs(bx - c["lon"]) < hw_t + _layout_cfg.CITY_RADIUS + 0.08 and \
                   abs(by - LINE - c["lat"]) < hh_t + _layout_cfg.CITY_RADIUS + 0.08:
                    return False
            return True

        # 天次在哪侧？优先对面，对面满则同侧
        day_num = seg["day"]
        day_side = None
        for px, py, _, _, pl in self.placed:
            if pl == f"day_D{day_num}" or pl.startswith(f"day_D{day_num}（"):
                day_side = 1 if (px - mx) * nx + (py - my) * ny >= 0 else -1
                break

        # 距离/时间固定左侧，与天次（右侧）永久分隔
        side_order = (-1, 1)

        # 阶段1：中点垂线
        for side in side_order:
            for dist_mult in self.PERP_DIST_MULTS:
                bx = mx + nx * min_dist * dist_mult * side
                by = my + ny * min_dist * dist_mult * side
                if pair_ok(bx, by):
                    self.place(bx, by, hw_d, hh_d, f"dist_{seg_index}")
                    self.place(bx, by - LINE, hw_t, hh_t, f"time_{seg_index}")
                    return bx, by, bx, by - LINE

        # 阶段2：沿路线滑动避开冲突（≤MAX_SLIDE_ABS°）
        max_slide = min(length * self.MAX_SLIDE_FRAC, self.MAX_SLIDE_ABS)
        ux, uy = dx / length, dy / length
        for side in side_order:
            for along in (0.04, -0.04, 0.08, -0.08, 0.12, -0.12):
                if abs(along) > max_slide:
                    continue
                ax = mx + ux * along
                ay = my + uy * along
                for dist_mult in self.PERP_DIST_MULTS_SHORT:
                    bx = ax + nx * min_dist * dist_mult * side
                    by = ay + ny * min_dist * dist_mult * side
                    if pair_ok(bx, by):
                        self.place(bx, by, hw_d, hh_d, f"dist_{seg_index}")
                        self.place(bx, by - LINE, hw_t, hh_t, f"time_{seg_index}")
                        return bx, by, bx, by - LINE

        # 阶段3：远距离回退
        for side in side_order:
            for dist_mult in (2.8, 4.0):
                bx = mx + nx * min_dist * dist_mult * side
                by = my + ny * min_dist * dist_mult * side
                if self.is_position_clear(bx, by, hw_d, hh_d, 0.03, self.MARGIN_ROUTE,
                                         my_kind="dist"):
                    self.place(bx, by, hw_d, hh_d, f"dist_{seg_index}")
                    self.place(bx, by - LINE, hw_t, hh_t, f"time_{seg_index}")
                    return bx, by, bx, by - LINE

        bx, by = mx + 0.2, my + 0.15
        self.place(bx, by, hw_d, hh_d, f"dist_{seg_index}")
        self.place(bx, by - LINE, hw_t, hh_t, f"time_{seg_index}")
        return bx, by, bx, by - LINE

    # ── 景点放置 ──

    def place_attraction(self, name: str, alat: float, alon: float,
                         city_name: str, city_lat: float, city_lon: float,
                         is_primary: bool, idx: int, ai: int) -> Tuple[float, float, str, dict]:
        """放置单个景点标注。

        城圈外景点：真实坐标打点 + 紧邻标签
        城圈内景点：由调用方合并后统一放置

        Returns:
            (x, y, ha, leader_info) — 标注位置、对齐方式、引线信息
        """
        cr = _layout_cfg.CITY_RADIUS
        # 判断是否在城圈内
        in_circle = math.hypot(alon - city_lon, alat - city_lat) < cr + 0.02

        leader_info = {"in_circle": in_circle, "lat": alat, "lon": alon}

        if in_circle:
            return 0, 0, "left", leader_info  # 城圈内由调用方处理

        sz = self.FONT_PRIM if is_primary else self.FONT_SEC
        hw, hh = self.text_half_size(name, sz)

        # 收集所有有效位置，选离路线中点最远的（给天次留空间）
        candidates = []
        for dist in self.ATTR_SEARCH_DISTS:
            for angle_deg in (240, 300, 120, 60, 225, 315, 135, 45):
                rad = math.radians(angle_deg)
                tx = alon + dist * math.cos(rad)
                ty = alat + dist * math.sin(rad)
                if self.is_position_clear(tx, ty, hw, hh, my_kind="attr"):
                    # 评分：到最近路线中点的距离（越远越好）
                    min_dist_to_route = min(
                        (math.hypot(tx-mx, ty-my) for mx, my in self.route_midpoints),
                        default=float('inf'))
                    candidates.append((min_dist_to_route, tx, ty, dist,
                                      "left" if math.cos(rad) >= 0 else "right"))

        if candidates:
            candidates.sort(reverse=True)  # 选离路线中点最远的
            _, tx, ty, dist, ha = candidates[0]
            self.place(tx, ty, hw, hh,
                       f"attr_{idx}_{ai}_{'prim' if is_primary else 'sec'}")
            leader_info["need_leader"] = dist > 0.15
            leader_info["lx"] = tx
            leader_info["ly"] = ty
            return tx, ty, ha, leader_info

        # 尝试腾挪：微调附近的天次/距离/时间来让位
        if self.budge_blockers(alon, alat) > 0:
            # 重新尝试正常搜索
            for dist in self.ATTR_SEARCH_DISTS:
                for angle_deg in (240, 300, 120, 60, 225, 315, 135, 45):
                    rad = math.radians(angle_deg)
                    tx = alon + dist * math.cos(rad)
                    ty = alat + dist * math.sin(rad)
                    if self.is_position_clear(tx, ty, hw, hh, my_kind="attr"):
                        ha = "left" if math.cos(rad) >= 0 else "right"
                        self.place(tx, ty, hw, hh,
                                   f"attr_{idx}_{ai}_{'prim' if is_primary else 'sec'}")
                        leader_info["need_leader"] = dist > 0.15
                        leader_info["lx"] = tx
                        leader_info["ly"] = ty
                        return tx, ty, ha, leader_info

        # Fallback — 扩大搜索半径
        for radius in self.ATTR_FALLBACK_DISTS:
            for angle_deg in (240, 300, 120, 60, 210, 330, 150, 30):
                rad = math.radians(angle_deg)
                tx = alon + radius * math.cos(rad)
                ty = alat + radius * math.sin(rad)
                if self.is_position_clear(tx, ty, hw, hh, my_kind="attr"):
                    ha = "left" if math.cos(rad) >= 0 else "right"
                    self.place(tx, ty, hw, hh,
                               f"attr_{idx}_{ai}_{'prim' if is_primary else 'sec'}")
                    leader_info["need_leader"] = True
                    leader_info["lx"] = tx
                    leader_info["ly"] = ty
                    return tx, ty, ha, leader_info

        # 终极 fallback
        tx, ty = alon + 0.30, alat + 0.30
        ha = "left"
        self.place(tx, ty, hw, hh,
                   f"attr_{idx}_{ai}_{'prim' if is_primary else 'sec'}")
        leader_info["need_leader"] = True
        leader_info["lx"] = tx
        leader_info["ly"] = ty
        return tx, ty, ha, leader_info

    def place_grouped_attractions(self, city_name: str, city_lat: float,
                                   city_lon: float, idx: int,
                                   prim_names: List[str],
                                   sec_names: List[str],
                                   side: int) -> Optional[List[Tuple[float, float, str, str, int, float, float]]]:
        """城圈内景点——折线引线连接城圈。越近越好。

        Returns:
            [(x, y, name, color, size, ha, edge_x, edge_y), ...]
            其中 (edge_x, edge_y) 为城圈边缘连接点
        """
        LINE = 0.06
        cr = _layout_cfg.CITY_RADIUS

        items = []
        for n in prim_names[:2]:
            hw, hh = self.text_half_size(n, self.FONT_PRIM)
            items.append((n, hw, hh, ATTR_PRIM_COLOR, self.FONT_PRIM, "prim"))
        for n in sec_names[:2]:
            hw, hh = self.text_half_size(n, self.FONT_SEC)
            items.append((n, hw, hh, ATTR_SEC_COLOR, self.FONT_SEC, "sec"))

        if not items:
            return None

        gap = 0.06
        max_hw = max(hw for _, hw, _, _, _, _ in items)
        total_h = sum(hh * 2 for _, _, hh, _, _, _ in items) + LINE * (len(items) - 1)

        # 从城圈边缘最近开始（仅对角线确保折线可见）
        for gap in self.GROUPED_GAP_DISTS:
            dist = cr + gap
            for angle_deg in (225, 315, 135, 45):
                rad = math.radians(angle_deg)
                bx = city_lon + dist * math.cos(rad)
                by = city_lat + dist * math.sin(rad)
                side_out = 1 if math.cos(rad) >= 0 else -1
                ha = "left" if side_out > 0 else "right"

                # 城圈边缘连接点
                edge_x = city_lon + cr * math.cos(rad)
                edge_y = city_lat + cr * math.sin(rad)

                start_y = by + total_h / 2 - items[0][2]
                ok = True
                cum_y = 0.0
                prev_hh = items[0][2]
                for i, (name, hw, hh, color, sz, kind) in enumerate(items):
                    if i == 0:
                        ty = start_y
                    else:
                        cum_y += prev_hh + hh + LINE
                        ty = start_y - cum_y
                        prev_hh = hh
                    for px, py, phw, phh, pl in self.placed:
                        if pl.startswith(f"attr_{idx}_"):
                            continue
                        pk = self._label_kind(pl)
                        m = 0.06 if (pk and pk != "attr") else self.MARGIN_LABEL
                        if self.rect_overlap(bx, ty, hw, hh, px, py, phw, phh, m):
                            ok = False
                            break
                    if not ok:
                        break
                    if self.route_collision(bx, ty, hw, hh, 0.04):
                        ok = False
                        break
                if ok:
                    result = []
                    cum_y2 = 0.0
                    prev_hh2 = items[0][2]
                    for i, (name, hw, hh, color, sz, kind) in enumerate(items):
                        if i == 0:
                            ty = start_y
                        else:
                            cum_y2 += prev_hh2 + hh + LINE
                            ty = start_y - cum_y2
                            prev_hh2 = hh
                        self.place(bx, ty, hw, hh, f"attr_{idx}_{kind}_{i}")
                        result.append((bx, ty, name, color, sz, ha, edge_x, edge_y))
                    return result

        # 腾挪附近的天次/距离/时间，再试一次
        if self.budge_blockers(city_lon, city_lat, 0.8) > 0:
            # 重新尝试策略1
            for try_side in (side, -side):
                bx = city_lon + try_side * (cr + gap + max_hw)
                ha = "left" if try_side > 0 else "right"
                start_y = city_lat + total_h / 2 - items[0][2]
                cum_y = 0.0; prev_hh = items[0][2]
                ok = True
                for i, (name, hw_a, hh_a, color_a, sz_a, kind_a) in enumerate(items):
                    ty = start_y if i == 0 else (start_y - cum_y)
                    if i > 0: cum_y += prev_hh + hh_a + LINE; prev_hh = hh_a; ty = start_y - cum_y
                    for px, py, phw, phh, pl in self.placed:
                        if pl.startswith(f"attr_{idx}_"): continue
                        pk = self._label_kind(pl)
                        m = 0.10 if (pk and pk != "attr") else self.MARGIN_LABEL
                        if self.rect_overlap(bx, ty, hw_a, hh_a, px, py, phw, phh, m):
                            ok = False; break
                    if not ok: break
                    if self.route_collision(bx, ty, hw_a, hh_a, 0.04): ok = False; break
                if ok:
                    result = []
                    cum_y2 = 0.0; prev_hh2 = items[0][2]
                    for i, (name, hw_a, hh_a, color_a, sz_a, kind_a) in enumerate(items):
                        ty = start_y if i == 0 else (start_y - cum_y2)
                        if i > 0: cum_y2 += prev_hh2 + hh_a + LINE; prev_hh2 = hh_a; ty = start_y - cum_y2
                        self.place(bx, ty, hw_a, hh_a, f"attr_{idx}_{kind_a}_{i}")
                        result.append((bx, ty, name, color_a, sz_a, ha, 0, 0))  # 渲染器会重新计算 edge_x/edge_y
                    return result

        return None

    # ── 行程表放置 ──

    def place_itinerary(self, lines: List[str],
                        map_extent: List[float],
                        cities: list,
                        font_size: float = 18,
                        line_height: float = 0.21,
                        char_width: float = 0.09) -> Optional[Tuple[float, float, float, float]]:
        """网格搜索最佳空白区域放置行程表。

        Returns:
            (cx, cy, tw, th) — 左上角坐标和宽高，或 None
        """
        tw = min(max(len(l) for l in lines) * char_width + 0.3, 3.8)
        th = len(lines) * line_height + 0.10
        west, east, south, north = map_extent

        cx_min = west + 0.2
        cx_max = east - 0.2 - tw
        cy_max = north - 0.9 - 0.15 - th / 2  # 标题下方
        cy_min = south + 0.2 + th / 2

        if cx_min > cx_max or cy_min > cy_max:
            return None

        best, best_score = None, float("inf")
        y = cy_max
        while y >= cy_min:
            x = cx_min
            while x <= cx_max:
                bx, by = x + tw / 2, y
                # 评分：附近元素数 + 距顶边惩罚
                count = sum(1 for px, py, _, _, _ in self.placed
                           if math.hypot(bx - px, by - py) < 1.0)
                count += sum(3 for c in cities
                            if math.hypot(c["lon"] - bx, c["lat"] - by) < 1.0)
                score = count + (north - y) * 0.02

                if score < best_score:
                    hw, hh = tw / 2, th / 2
                    ok = True
                    for px, py, phw, phh, _ in self.placed:
                        if abs(bx - px) < hw + phw + 0.08 and \
                           abs(by - py) < hh + phh + 0.08:
                            ok = False
                            break
                    if ok:
                        best = (x, y, tw, th)
                        best_score = score
                x += 0.15
            y -= 0.15

        if best:
            x, y, tw, th = best
            self.place(x + tw / 2, y, tw / 2, th / 2, "itinerary")
            return best
        return None

    def place_itinerary_two_col(self, lines: List[str],
                                 map_extent: List[float],
                                 cities: list) -> Optional[List[Tuple[float, float, float, float]]]:
        """双列行程表放置（单列放不下时的 fallback）。

        Returns:
            [(cx1, cy1, tw1, th1), (cx2, cy2, tw2, th2)] 或 None
        """
        mid = len(lines) // 2
        col1, col2 = lines[:mid], lines[mid:]

        char_width = 0.09
        line_height = 0.21
        tw1 = min(max(len(l) for l in col1) * char_width + 0.3, 3.8)
        tw2 = min(max(len(l) for l in col2) * char_width + 0.3, 3.8)
        th1 = len(col1) * line_height + 0.10

        west, east, south, north = map_extent
        cy_max = north - 0.9 - 0.15 - th1 / 2
        cy_min = south + 0.2 + th1 / 2

        best = None
        best_score = float("inf")
        y = cy_max
        while y >= cy_min:
            x = west + 0.2
            while x + tw1 + 0.2 + tw2 <= east - 0.2:
                bx, by = x + tw1 / 2, y
                hw, hh = tw1 / 2, th1 / 2
                ok = all(
                    abs(bx - px) >= hw + phw + 0.08 or
                    abs(by - py) >= hh + phh + 0.08
                    for px, py, phw, phh, _ in self.placed
                )
                if ok:
                    # 检查第二列
                    x2 = x + tw1 + 0.2
                    bx2, by2 = x2 + tw2 / 2, y
                    hw2, hh2 = tw2 / 2, th1 / 2
                    ok2 = all(
                        abs(bx2 - px) >= hw2 + phw + 0.08 or
                        abs(by2 - py) >= hh2 + phh + 0.08
                        for px, py, phw, phh, _ in self.placed
                    )
                    if ok2:
                        count = sum(1 for px, py, _, _, _ in self.placed
                                   if math.hypot(bx - px, by - py) < 1.0)
                        score = count + (north - y) * 0.02
                        if score < best_score:
                            best = [(x, y, tw1, th1), (x2, y, tw2, th1)]
                            best_score = score
                x += 0.15
            y -= 0.15

        if best:
            for x, y, tw, th in best:
                self.place(x + tw / 2, y, tw / 2, th / 2, "itinerary")
        return best
