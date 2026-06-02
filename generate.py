#!/usr/bin/env python3
"""路线图生成主入口。

用法:
    python generate.py routes/nanjiang_config.json
    python generate.py routes/nanjiang_config.json --output ~/Desktop/my_map.png
"""
import argparse
import math
import os
import platform
import shutil
import sys
import warnings

warnings.filterwarnings("ignore")
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import cartopy.crs as ccrs

from config import (
    load_config, CITY_RADIUS,
    EN_PROV_MAP, PROV_CN_NAMES, PROVINCE_COLORS,
    ATTR_PRIM_COLOR, INSET_THRESHOLD, INSET_PADDING,
)
from layout import LayoutEngine
from renderer import (
    F, ST, render_base_map, render_provinces, render_all_routes,
    render_city_node, render_day_label, render_rest_day_label,
    render_dist_time, render_attraction_outside,
    render_grouped_attractions,
    render_title, render_itinerary,
    render_zoom_inset_content, render_zoom_indicator,
)


# ═══════════════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════════════

def _build_itinerary_lines(cfg: dict, all_days: list,
                           day_to_segs: dict) -> list:
    """构建行程表文本行。"""
    cities = cfg["cities"]
    segments = cfg["segments"]
    rest_days = cfg.get("rest_days", {})
    day_attractions = cfg.get("day_attractions", {})
    all_seg_days = set(day_to_segs.keys())
    all_rest_days = set(int(k) for k in rest_days.keys())

    lines = []
    for day in all_days:
        seg_indices = day_to_segs.get(day, [])
        is_rest = str(day) in rest_days
        rc = rest_days.get(str(day))

        if is_rest and rc:
            if str(day) in day_attractions:
                da = day_attractions[str(day)]
                aa = da.get("primary", []) + da.get("secondary", [])
            else:
                ci_list = [i for i, c in enumerate(cities) if c["name"] == rc]
                if ci_list:
                    ci = ci_list[0]
                    aa = [a["name"] for a in cities[ci].get("attractions_primary", [])] + \
                         [a["name"] for a in cities[ci].get("attractions_secondary", [])]
                else:
                    aa = []
            line = f"D{day}  {rc}全天"
            if aa:
                line += f"  .  {'、'.join(aa)}"
            lines.append(line)
        elif seg_indices:
            cr = []
            aa = []
            for si in seg_indices:
                s = segments[si]
                if not cr:
                    cr.append(cities[s["from_index"]]["name"])
                cr.append(cities[s["to_index"]]["name"])
                ci = s["to_index"]
                if str(day) in day_attractions:
                    da = day_attractions[str(day)]
                    aa.extend(da.get("primary", []) + da.get("secondary", []))
                else:
                    aa.extend([a["name"] for a in cities[ci].get("attractions_primary", [])])
                    aa.extend([a["name"] for a in cities[ci].get("attractions_secondary", [])])
            line = f"D{day}  {'→'.join(dict.fromkeys(cr))}"
            unique_attrs = list(dict.fromkeys(aa))
            if unique_attrs:
                line += f"  .  {'、'.join(unique_attrs)}"
            lines.append(line)
        else:
            # 驻留日：沿用前一旅行日到达城市
            prev = [d for d in sorted(all_seg_days | all_rest_days | {0}) if d < day]
            city = ""
            if prev:
                pd = prev[-1]
                if pd in day_to_segs:
                    city = cities[segments[day_to_segs[pd][-1]]["to_index"]]["name"]
                elif str(pd) in rest_days:
                    city = rest_days[str(pd)]
            if not city:
                continue  # 驻留日城市为空则跳过
            if str(day) in day_attractions:
                da = day_attractions[str(day)]
                aa = da.get("primary", []) + da.get("secondary", [])
                line = f"D{day}  {city}"
                if aa:
                    line += f"  .  {'、'.join(aa)}"
            else:
                line = f"D{day}  {city}"
            lines.append(line)

    return lines


def _detect_close_pairs(cities: list, segments: list,
                        threshold: float) -> list:
    """检测 segments 中距离过近的相邻城市对。

    Args:
        cities: 城市列表
        segments: 路线段列表
        threshold: 距离阈值（地图坐标）

    Returns:
        [(from_index, to_index), ...] 过近的相邻城市对
    """
    lons = [c["lon"] for c in cities]
    lats = [c["lat"] for c in cities]
    diagonal = math.hypot(max(lons) - min(lons), max(lats) - min(lats))
    threshold_dist = diagonal * threshold

    close = []
    for seg in segments:
        fi, ti = seg["from_index"], seg["to_index"]
        dist = math.hypot(
            cities[fi]["lon"] - cities[ti]["lon"],
            cities[fi]["lat"] - cities[ti]["lat"],
        )
        if dist < threshold_dist:
            close.append((fi, ti))
    return close


def _group_connected_pairs(pairs: list) -> list:
    """将过近城市对按连通关系聚合为城市簇。

    使用并查集（union-find）。A-B 且 B-C → 合并为一个簇 {A, B, C}。

    Args:
        pairs: [(from_index, to_index), ...]

    Returns:
        [{idx1, idx2, idx3}, ...] 每个集合是一个需要放大的城市簇
    """
    if not pairs:
        return []

    parent = {}

    def find(x):
        if x not in parent:
            parent[x] = x
        if parent[x] != x:
            parent[x] = find(parent[x])
        return parent[x]

    def union(x, y):
        px, py = find(x), find(y)
        if px != py:
            parent[px] = py

    for i, j in pairs:
        union(i, j)

    groups = {}
    for i, j in pairs:
        root = find(i)
        groups.setdefault(root, set()).add(i)
        groups.setdefault(root, set()).add(j)

    return list(groups.values())


def _compute_zoom_extent(cluster_indices: set, cities: list,
                         padding: float) -> list:
    """计算放大镜的地理范围。

    Returns:
        [lon_min, lon_max, lat_min, lat_max, zoom_radius]
        zoom_radius：圆内实际展示的地理半径。
        渲染半径 = zoom_radius * RENDER_MARGIN（方图比圆大一倍）。
    """
    from config import ZOOM_FACTOR, RENDER_MARGIN

    all_lons, all_lats = [], []
    for idx in cluster_indices:
        c = cities[idx]
        all_lons.append(c["lon"])
        all_lats.append(c["lat"])
        for attr_key in ("attractions_primary", "attractions_secondary"):
            for a in c.get(attr_key, []):
                try:
                    all_lons.append(float(a["lon"]))
                    all_lats.append(float(a["lat"]))
                except (ValueError, TypeError):
                    pass

    if not all_lons:
        return None

    center_lon = (min(all_lons) + max(all_lons)) / 2
    center_lat = (min(all_lats) + max(all_lats)) / 2
    max_dist = 0.0
    for lon, lat in zip(all_lons, all_lats):
        d = math.hypot(lon - center_lon, lat - center_lat)
        max_dist = max(max_dist, d)

    base_radius = max(max_dist * padding, 0.15)
    # 选取框半径：簇范围 + 主图城圈补偿
    select_radius = max(base_radius, max_dist * 1.3) + CITY_RADIUS
    # 放大镜内容半径 = 选取框半径 / ZOOM_FACTOR × 5（基准 5x）
    display_radius = select_radius * 5 / ZOOM_FACTOR
    # 渲染半径（方图）：放大镜内容半径 × RENDER_MARGIN
    render_radius = display_radius * RENDER_MARGIN

    return [
        round(center_lon - render_radius, 3),
        round(center_lon + render_radius, 3),
        round(center_lat - render_radius, 3),
        round(center_lat + render_radius, 3),
        select_radius,   # 选取框半径
        display_radius,  # 放大镜内容半径
    ]




def _detect_city_provinces(cities: list) -> dict:
    """根据城市坐标自动判断所属省份。返回 {城市名: 省份简称}。"""
    from cartopy.io import shapereader
    from shapely.geometry import Point
    result = {}
    try:
        reader = shapereader.Reader(
            shapereader.natural_earth(resolution='50m', category='cultural',
                                      name='admin_1_states_provinces'))
        provinces = []
        for rec in reader.records():
            name_en = rec.attributes.get('name', '')
            short = EN_PROV_MAP.get(name_en, '')
            if short and rec.geometry:
                provinces.append((short, rec.geometry))
        for c in cities:
            pt = Point(c["lon"], c["lat"])
            for short, geom in provinces:
                if geom.contains(pt):
                    result[c["name"]] = short
                    break
    except (OSError, ValueError, ImportError) as e:
        print(f"  [省份检测] 失败: {e}")
    return result


def _safe_attr(attrs: list, city_name: str, attr_kind: str = "景点") -> list:
    """安全转换景点 lat/lon 为 float，跳过无效坐标。"""
    result = []
    skipped = 0
    for a in attrs:
        try:
            result.append({
                **a,
                "lat": float(a["lat"]),
                "lon": float(a["lon"]),
            })
        except (ValueError, TypeError):
            skipped += 1
    if skipped:
        print(f"  警告: {city_name} 的 {skipped} 个{attr_kind}坐标无效，已跳过")
    return result


def _lookup_placed(layout, label: str):
    """在 layout.placed 中查找精确匹配的标签坐标。"""
    for cx, cy, hw, hh, pl in layout.placed:
        if pl == label:
            return cx, cy
    return None, None


# ═══════════════════════════════════════════════════════════════════
# 图层渲染函数（从 generate 拆分）
# ═══════════════════════════════════════════════════════════════════

def _compute_extent_and_figure(cfg: dict, cities: list,
                               all_days: list, day_to_segs: dict):
    """计算地图范围和图形尺寸。

    Returns:
        (extent, fig_w, fig_h, original_north)
    """
    output = cfg["output"]
    lons = [c["lon"] for c in cities]
    lats = [c["lat"] for c in cities]
    m = 1.0
    raw = [min(lons) - m, max(lons) + m, min(lats) - m, max(lats) + m]
    extent = [
        round(raw[0] * 2 - 0.5) / 2,
        round(raw[1] * 2 + 0.5) / 2,
        round(raw[2] * 2 - 0.5) / 2,
        round(raw[3] * 2 + 0.5) / 2,
    ]
    original_north = extent[3]

    # 扩展北边界（仅当行程表放不下时）
    if output.get("auto_extent", True):
        LINE_H = 0.21
        table_lines = _build_itinerary_lines(cfg, all_days, day_to_segs)
        th_table = len(table_lines) * LINE_H + 0.10
        peak_node_top = max(
            c["lat"] + CITY_RADIUS + 0.04 for c in cities
        )
        table_north = peak_node_top + th_table + 0.4
        if table_north > extent[3]:
            print(f"  扩展北边界(行程表): {extent[3]:.1f} -> {table_north:.1f}")
            extent[3] = table_north

    # 图幅自动适配路线长宽比
    fig_w = output.get("width_inch", 22)
    fig_h = output.get("height_inch", 26)
    if output.get("auto_extent", True):
        avg_lat = sum(c["lat"] for c in cities) / len(cities)
        crs_cos = math.cos(math.radians(avg_lat))
        lon_span = max(lons) - min(lons)
        lat_span = max(lats) - min(lats)
        ratio = (lon_span * crs_cos) / lat_span if lat_span > 0 else 1.0
        ratio = max(0.5, min(2.0, ratio))
        if ratio > 1.0:
            fig_w, fig_h = 26, max(16, 26 / ratio)
        else:
            fig_w, fig_h = max(16, 26 * ratio), 26

    return extent, fig_w, fig_h, original_north


def _render_base_layers(ax, extent: list, cfg: dict):
    """L1: 底图 + 省界, L2: 路线渲染 + 碰撞注册。

    Returns:
        layout engine
    """
    segments = cfg["segments"]
    cities = cfg["cities"]
    day_colors = cfg["day_colors"]
    output = cfg["output"]

    # L1 底图
    print("底图...")
    render_base_map(ax, extent)
    render_provinces(ax, extent, PROVINCE_COLORS, EN_PROV_MAP, PROV_CN_NAMES)

    # L2 路线
    print("路线...")
    route_pairs = render_all_routes(ax, segments, cities, day_colors)

    # 布局引擎初始化
    extent_w = extent[1] - extent[0]
    px_per_deg = (output["width_inch"] * 0.98 * output["dpi"]) / extent_w if extent_w > 0 else 200
    layout = LayoutEngine(px_per_deg, output["dpi"])

    # 注册路线到碰撞系统
    for fi, ti in route_pairs:
        x1, y1 = cities[fi]["lon"], cities[fi]["lat"]
        x2, y2 = cities[ti]["lon"], cities[ti]["lat"]
        layout.register_route(x1, y1, x2, y2, LayoutEngine.ROUTE_HW)

    return layout


def _render_cities(ax, layout: LayoutEngine, cities: list,
                   crs_cos: float) -> None:
    """L3: 城市节点渲染 + 布局注册。"""
    print("城市...")
    city_provinces = _detect_city_provinces(cities)
    for c in cities:
        prov = city_provinces.get(c["name"], "")
        city_color = PROVINCE_COLORS.get(prov, c.get("color", "#888888"))
        render_city_node(ax, c["name"], c["lon"], c["lat"], city_color, crs_cos)
        layout.place(c["lon"], c["lat"],
                     CITY_RADIUS + 0.02,
                     CITY_RADIUS * crs_cos + 0.02,
                     f"city_{c['name']}")


def _place_attractions(layout: LayoutEngine, cities: list,
                       skip_city_indices: set = None) -> list:
    """L4: 景点放置——仅放置，不渲染。返回 render recipes 列表。"""
    if skip_city_indices is None:
        skip_city_indices = set()
    print("景点(放置)...")
    recipes = []
    for idx, c in enumerate(cities):
        # 跳过放大簇内的城市景点
        if idx in skip_city_indices:
            continue
        prim_list = c.get("attractions_primary", [])
        sec_list = c.get("attractions_secondary", [])

        prim_list = _safe_attr(prim_list, c["name"], "主要")
        sec_list = _safe_attr(sec_list, c["name"], "次要")

        # 城圈内景点：合并引线
        in_prim = [a for a in prim_list
                   if math.hypot(a["lon"] - c["lon"], a["lat"] - c["lat"])
                   < CITY_RADIUS + 0.02]
        in_sec = [a for a in sec_list
                  if math.hypot(a["lon"] - c["lon"], a["lat"] - c["lat"])
                  < CITY_RADIUS + 0.02]
        out_prim = [a for a in prim_list if a not in in_prim]
        out_sec = [a for a in sec_list if a not in in_sec]

        # 城圈内：上下排列，紧贴城市圈
        if in_prim or in_sec:
            side = -1 if idx % 2 == 0 else 1
            items = layout.place_grouped_attractions(
                c["name"], c["lat"], c["lon"], idx,
                [a["name"] for a in in_prim],
                [a["name"] for a in in_sec],
                side,
            )
            if items:
                items_meta = []
                for i, (bx, ty, name, color, sz, ha, edge_x, edge_y) in enumerate(items):
                    kind = "prim" if color == ATTR_PRIM_COLOR else "sec"
                    label_key = f"attr_{idx}_{kind}_{i}"
                    items_meta.append({
                        "label_key": label_key,
                        "name": name,
                        "color": color,
                        "sz": sz,
                        "ha": ha,
                    })
                recipes.append({
                    "kind": "grouped",
                    "city_lon": c["lon"],
                    "city_lat": c["lat"],
                    "items_meta": items_meta,
                })

        # 城圈外：单独打点
        for ai, a in enumerate(out_prim):
            tx, ty, ha, leader = layout.place_attraction(
                a["name"], a["lat"], a["lon"],
                c["name"], c["lat"], c["lon"],
                True, idx, ai,
            )
            recipes.append({
                "kind": "outside",
                "label_key": f"attr_{idx}_{ai}_prim",
                "name": a["name"],
                "alat": a["lat"],
                "alon": a["lon"],
                "is_primary": True,
                "ha": ha,
                "need_leader": leader.get("need_leader", False),
            })
        for ai, a in enumerate(out_sec):
            tx, ty, ha, leader = layout.place_attraction(
                a["name"], a["lat"], a["lon"],
                c["name"], c["lat"], c["lon"],
                False, idx, ai + len(out_prim),
            )
            recipes.append({
                "kind": "outside",
                "label_key": f"attr_{idx}_{ai + len(out_prim)}_sec",
                "name": a["name"],
                "alat": a["lat"],
                "alon": a["lon"],
                "is_primary": False,
                "ha": ha,
                "need_leader": leader.get("need_leader", False),
            })

    return recipes


def _place_day_labels(layout: LayoutEngine, cfg: dict,
                      all_days: list, day_to_segs: dict,
                      cities: list, crs_cos: float,
                      skip_city_indices: set = None) -> list:
    """L5: 天次标注——仅放置，不渲染。返回 render recipes 列表。"""
    if skip_city_indices is None:
        skip_city_indices = set()
    print("天次(放置)...")
    segments = cfg["segments"]
    rest_days = cfg.get("rest_days", {})
    recipes = []

    # 合并连续同城休息日
    merged_rest = {}
    rest_items = sorted((int(k), v) for k, v in rest_days.items())
    i = 0
    while i < len(rest_items):
        day_start, city = rest_items[i]
        day_end = day_start
        j = i + 1
        while j < len(rest_items) and rest_items[j][1] == city and rest_items[j][0] == day_end + 1:
            day_end = rest_items[j][0]
            j += 1
        if day_end > day_start:
            merged_rest[str(day_start)] = (city, day_end)
        else:
            merged_rest[str(day_start)] = (city, None)
        i = j

    for day in all_days:
        seg_indices = day_to_segs.get(day, [])
        if str(day) in merged_rest:
            rest_city, end_day = merged_rest[str(day)]
            if end_day:
                day_label = f"D{day}-D{end_day}"
                city_label = f"{rest_city}休整"
            else:
                day_label = f"D{day}"
                city_label = f"{rest_city}全天"
            dx, dy, dha, cx, cy = layout.place_rest_day(
                day_label, rest_city, cities, crs_cos,
                day_display=day_label, city_display=city_label,
            )
            recipes.append({
                "kind": "rest",
                "day_key": f"day_{day_label}",
                "city_key": f"day_{city_label}",
                "day_label": day_label,
                "city_label": city_label,
                "dha": dha,
            })
        elif seg_indices:
            # 跳过两端都在放大簇内的段
            skip_segs = []
            segs_to_place = []
            for si in seg_indices:
                s = segments[si]
                if s["from_index"] in skip_city_indices and s["to_index"] in skip_city_indices:
                    skip_segs.append(si)
                else:
                    segs_to_place.append(si)
            if not segs_to_place:
                continue
            tx, ty, ha = layout.place_travel_day(
                f"D{day}", segs_to_place, segments, cities,
            )
            recipes.append({
                "kind": "travel",
                "label_key": f"day_D{day}",
                "text": f"D{day}",
                "ha": ha,
            })

    return recipes


def _place_dist_time_labels(layout: LayoutEngine,
                            segments: list, cities: list,
                            skip_city_indices: set = None) -> list:
    """L6: 距离/时间标注——仅放置，不渲染。返回 render recipes 列表。"""
    if skip_city_indices is None:
        skip_city_indices = set()
    print("距离/时间(放置)...")
    # 去重往返段（只标一个方向的 dist/time）
    round_trip_skip = set()
    seen_pairs = set()
    for i, s1 in enumerate(segments):
        pair = frozenset([s1["from_index"], s1["to_index"]])
        if pair in seen_pairs:
            round_trip_skip.add(i)
        else:
            seen_pairs.add(pair)

    recipes = []
    for si, seg in enumerate(segments):
        # 跳过放大簇内的段
        if seg["from_index"] in skip_city_indices and seg["to_index"] in skip_city_indices:
            continue
        if si in round_trip_skip:
            continue
        dist_text = seg.get("distance", "0km")
        time_text = seg.get("time", "0h")
        dx, dy, tx, ty = layout.place_dist_time(
            dist_text, time_text, si, segments, cities,
        )
        recipes.append({
            "kind": "dist_time",
            "dist_key": f"dist_{si}",
            "time_key": f"time_{si}",
            "dist_text": dist_text,
            "time_text": time_text,
        })

    return recipes


def _render_itinerary_and_title(ax, layout: LayoutEngine, cfg: dict,
                                all_days: list, day_to_segs: dict,
                                extent: list) -> None:
    """L7: 行程表 + 标题。"""
    cities = cfg["cities"]

    # ── 行程表 ──
    print("行程表...")
    table_lines = _build_itinerary_lines(cfg, all_days, day_to_segs)
    result = layout.place_itinerary(table_lines, extent, cities)
    if not result:
        result = layout.place_itinerary_two_col(table_lines, extent, cities)
        if not result:
            # 回退：拓宽东边界 2° 重试（使用本地副本，不污染原始 extent）
            wider_extent = list(extent)
            wider_extent[1] += 2.0
            print(f"  拓宽东边界 -> {wider_extent[1]:.1f}")
            ax.set_extent(wider_extent)
            result = layout.place_itinerary(table_lines, wider_extent, cities)
            if not result:
                result = layout.place_itinerary_two_col(table_lines, wider_extent, cities)

    if isinstance(result, tuple) and len(result) == 4:
        cx, cy, tw, th = result
        render_itinerary(ax, table_lines, cx, cy, tw, th)
        print(f"  单列: ({cx:.1f}, {cy:.1f})")
    elif isinstance(result, list):
        mid = len(table_lines) // 2
        for (cx, cy, tw, th), col_lines in zip(
            result, [table_lines[:mid], table_lines[mid:]]
        ):
            render_itinerary(ax, col_lines, cx, cy, tw, th)
        print("  双列")
    else:
        print("  行程表：未找到位置")

    # ── 标题 ──
    print("标题...")
    render_title(ax, cfg)


# ═══════════════════════════════════════════════════════════════════
# 后置渲染函数（从 layout.placed 读取松弛后坐标）
# ═══════════════════════════════════════════════════════════════════

def _render_day_items(ax, layout, recipes: list) -> None:
    """从 recipes 和 layout.placed 读取天次坐标并渲染。"""
    for r in recipes:
        if r["kind"] == "travel":
            x, y = _lookup_placed(layout, r["label_key"])
            if x is not None:
                render_day_label(ax, r["text"], x, y, r["ha"])
        elif r["kind"] == "rest":
            dx, dy = _lookup_placed(layout, r["day_key"])
            cx, cy = _lookup_placed(layout, r["city_key"])
            if dx is not None and cx is not None:
                render_rest_day_label(
                    ax, r["day_label"], r["city_label"],
                    dx, dy, r["dha"], cx, cy,
                )


def _render_attr_items(ax, layout, recipes: list) -> None:
    """从 recipes 和 layout.placed 读取景点坐标并渲染。"""
    for r in recipes:
        if r["kind"] == "outside":
            x, y = _lookup_placed(layout, r["label_key"])
            if x is None:
                continue
            leader_info = {
                "need_leader": r["need_leader"],
                "lx": x, "ly": y,
            }
            render_attraction_outside(
                ax, r["name"], r["alat"], r["alon"],
                r["is_primary"], x, y, r["ha"], leader_info,
            )
        elif r["kind"] == "grouped":
            updated_items = []
            for im in r["items_meta"]:
                x, y = _lookup_placed(layout, im["label_key"])
                if x is not None:
                    updated_items.append(
                        (x, y, im["name"], im["color"], im["sz"],
                         im["ha"], 0, 0))
            if updated_items:
                render_grouped_attractions(
                    ax, updated_items,
                    r["city_lon"], r["city_lat"],
                )


def _render_dt_items(ax, layout, recipes: list) -> None:
    """从 recipes 和 layout.placed 读取距离/时间坐标并渲染。"""
    for r in recipes:
        dx, dy = _lookup_placed(layout, r["dist_key"])
        tx, ty = _lookup_placed(layout, r["time_key"])
        if dx is not None and tx is not None:
            render_dist_time(ax, r["dist_text"], r["time_text"],
                             dx, dy, tx, ty)


# ═══════════════════════════════════════════════════════════════════
# 放大图子管道：在独立 figure 上运行完整布局引擎
# ═══════════════════════════════════════════════════════════════════

    return recipes


def _render_zoom_pipeline(ax, extent_zoom: list,
                          cluster: set, cities: list, segments: list,
                          day_colors: dict, output: dict) -> None:
    """放大镜简化管道：偏移量基于 zoom_city_radius 统一缩放，不走 LayoutEngine。

    天次/距离放路线中点上下，景点引线偏移按缩放城圈计算。
    """
    from config import ZOOM_FACTOR
    zoom_cr = CITY_RADIUS / ZOOM_FACTOR

    cluster_list = sorted(cluster)
    local_cities = [cities[i] for i in cluster_list]
    idx_map = {old: new for new, old in enumerate(cluster_list)}

    local_segs, external_segs = [], []
    for seg in segments:
        fi, ti = seg["from_index"], seg["to_index"]
        f_in, t_in = fi in cluster, ti in cluster
        if f_in and t_in:
            ls = dict(seg); ls["from_index"] = idx_map[fi]; ls["to_index"] = idx_map[ti]
            local_segs.append(ls)
        elif f_in and not t_in:
            external_segs.append((fi, ti, seg))
        elif t_in and not f_in:
            external_segs.append((ti, fi, seg))

    local_day_colors = {}
    for seg in local_segs + [s for _, _, s in external_segs]:
        d = str(seg["day"])
        if d not in local_day_colors:
            local_day_colors[d] = day_colors.get(d, "#888888")

    avg_lat = sum(c["lat"] for c in local_cities) / len(local_cities)
    crs_cos = math.cos(math.radians(avg_lat))

    from renderer import (render_route_segment, render_all_routes,
                          render_city_node, render_day_label,
                          render_dist_time, render_attraction_outside,
                          ATTR_PRIM_COLOR, ATTR_SEC_COLOR)

    # 外部连线
    for fi, ti, seg in external_segs:
        render_route_segment(ax, cities[fi]["lon"], cities[fi]["lat"],
                             cities[ti]["lon"], cities[ti]["lat"],
                             day_colors.get(str(seg["day"]), "#888888"))

    # 簇内路线
    render_all_routes(ax, local_segs, local_cities, local_day_colors)

    # 城市节点
    for c in local_cities:
        render_city_node(ax, c["name"], c["lon"], c["lat"],
                         c.get("color", "#888888"), crs_cos, radius=zoom_cr)

    # ── LayoutEngine（缩放版，只用于天次/距离/时间放置+松弛）──
    extent_w = extent_zoom[1] - extent_zoom[0]
    px_per_deg = (output.get("width_inch", 5.0) * 0.98 * output["dpi"]) / extent_w if extent_w > 0 else 200
    layout = LayoutEngine(px_per_deg, output["dpi"])
    scale = zoom_cr / CITY_RADIUS
    layout.ROUTE_HW *= scale
    layout.MARGIN_PLACED *= scale
    layout.MARGIN_ROUTE *= scale
    layout.MARGIN_LABEL *= scale
    layout.MIN_DIST_EXTRA *= scale
    layout.LINE_GAP *= scale
    layout.MAX_SLIDE_FRAC *= scale
    layout.MAX_SLIDE_ABS *= scale

    # 注册路线和城市到碰撞系统
    for fi, ti in [(s["from_index"], s["to_index"]) for s in local_segs]:
        layout.register_route(local_cities[fi]["lon"], local_cities[fi]["lat"],
                              local_cities[ti]["lon"], local_cities[ti]["lat"],
                              layout.ROUTE_HW)
    for c in local_cities:
        layout.place(c["lon"], c["lat"], zoom_cr + 0.02,
                     zoom_cr * crs_cos + 0.02, f"city_{c['name']}")

    # 天次 + 距离/时间（LayoutEngine 放置 + 松弛）
    local_cfg = {"cities": local_cities, "segments": local_segs,
                 "day_colors": local_day_colors, "rest_days": {},
                 "day_attractions": {}, "output": output}
    day_to_segs = {}
    for si, seg in enumerate(local_segs):
        day_to_segs.setdefault(seg["day"], []).append(si)
    all_days = sorted(day_to_segs.keys())
    day_recipes = _place_day_labels(layout, local_cfg, all_days, day_to_segs,
                                     local_cities, crs_cos)
    dt_recipes = _place_dist_time_labels(layout, local_segs, local_cities)

    # 全局松弛
    layout.relax_overlaps()

    _render_day_items(ax, layout, day_recipes)
    _render_dt_items(ax, layout, dt_recipes)

    # 景点（引线偏移随 zoom_cr 缩放）
    leader_dist = zoom_cr * 3.0
    for idx, c in enumerate(local_cities):
        for is_prim, attr_key in [(True, "attractions_primary"),
                                   (False, "attractions_secondary")]:
            color = ATTR_PRIM_COLOR if is_prim else ATTR_SEC_COLOR
            for a in c.get(attr_key, []):
                try:
                    alon, alat = float(a["lon"]), float(a["lat"])
                except (ValueError, TypeError):
                    continue
                dx, dy = alon - c["lon"], alat - c["lat"]
                d = math.hypot(dx, dy)
                ux = dx / d if d > 0.001 else 1.0
                uy = dy / d if d > 0.001 else 0.0
                lx, ly = alon + ux * leader_dist, alat + uy * leader_dist
                ha = "left" if ux >= 0 else "right"
                render_attraction_outside(
                    ax, a["name"], alat, alon, is_prim,
                    lx, ly, ha,
                    {"need_leader": True, "lx": lx, "ly": ly},
                )


# ═══════════════════════════════════════════════════════════════════
# 核心生成函数
# ═══════════════════════════════════════════════════════════════════

def generate(cfg: dict) -> str:
    """根据配置生成路线图，返回输出文件路径。"""
    output = cfg["output"]
    cities = cfg["cities"]
    segments = cfg["segments"]

    # ── 预计算天数 ──
    day_to_segs = {}
    for si, seg in enumerate(segments):
        d = seg["day"]
        day_to_segs.setdefault(d, []).append(si)

    all_seg_days = set(day_to_segs.keys())
    all_rest_days = set(int(k) for k in cfg.get("rest_days", {}).keys())
    all_attr_days = set(int(k) for k in cfg.get("day_attractions", {}).keys())
    max_day = max(all_seg_days | all_rest_days | all_attr_days | {1})
    all_days = sorted(range(1, max_day + 1))

    # ── 计算地图范围和图形尺寸 ──
    extent, fig_w, fig_h, original_north = _compute_extent_and_figure(
        cfg, cities, all_days, day_to_segs)

    # ── 计算纬度补偿 ──
    avg_lat = sum(c["lat"] for c in cities) / len(cities)
    crs_cos = math.cos(math.radians(avg_lat))

    # ── 创建图形 ──
    fig = plt.figure(figsize=(fig_w, fig_h), facecolor="white")
    ax = fig.add_subplot(111, projection=ccrs.PlateCarree())
    fig.subplots_adjust(left=0.01, right=0.99, top=0.99, bottom=0.01)
    ax.set_extent(extent)
    ax.set_aspect(1.0 / crs_cos, adjustable="box")

    # ── 图层渲染（两阶段：放置 → 全局松弛 → 渲染）──
    layout = _render_base_layers(ax, extent, cfg)

    # L3: 城市节点 — 固定位置，立即渲染
    _render_cities(ax, layout, cities, crs_cos)

    # 提前检测放大簇，用于跳过主图标注
    zoom_skip = set()
    zoom_clusters = []
    close_pairs = _detect_close_pairs(cities, segments, INSET_THRESHOLD)
    if close_pairs:
        zoom_clusters = _group_connected_pairs(close_pairs)
        for cluster in zoom_clusters:
            zoom_skip.update(cluster)
        print(f"  主图跳过标注: {sorted(zoom_skip)}")

    # 阶段1 — 放置所有可松弛元素（放大区跳过主图标注）
    day_recipes = _place_day_labels(
        layout, cfg, all_days, day_to_segs, cities, crs_cos,
        skip_city_indices=zoom_skip)
    dt_recipes = _place_dist_time_labels(
        layout, segments, cities, skip_city_indices=zoom_skip)
    attr_recipes = _place_attractions(
        layout, cities, skip_city_indices=zoom_skip)

    # 全局松弛
    n = layout.relax_overlaps()
    if n:
        print(f"  全局松弛: 修复 {n} 处重叠")

    # 渲染所有元素
    _render_day_items(ax, layout, day_recipes)
    _render_attr_items(ax, layout, attr_recipes)
    _render_dt_items(ax, layout, dt_recipes)

    # L7: 行程表 + 标题（最后，不影响其他元素布局）
    _render_itinerary_and_title(ax, layout, cfg, all_days, day_to_segs, extent)

    # L8: 局部放大图（独立 figure 渲染 + 截图嵌入）
    try:
        if zoom_clusters:
            print(f"  {len(close_pairs)} 对过近城市 → 生成放大图")

            for ci, cluster in enumerate(zoom_clusters):
                result = _compute_zoom_extent(
                    cluster, cities, INSET_PADDING)
                if result is None:
                    continue
                extent_zoom = result[:4]
                select_radius = result[4]   # 主图选取框半径
                display_radius = result[5]  # 放大镜内容半径

                # ── 创建独立 figure 渲染放大图 ──
                zoom_dpi = output["dpi"]
                zoom_w, zoom_h = 8.0, 8.0  # 圆形直径 4 英寸
                zoom_fig = plt.figure(
                    figsize=(zoom_w, zoom_h),
                    facecolor="#F8F4EC", dpi=zoom_dpi,
                )
                zoom_ax = zoom_fig.add_subplot(
                    111, projection=ccrs.PlateCarree(),
                )
                # 无边框、无边距
                zoom_ax.spines["geo"].set_visible(False)
                zoom_fig.subplots_adjust(
                    left=0.0, right=1.0, top=1.0, bottom=0.0,
                )
                local_lat = (extent_zoom[2] + extent_zoom[3]) / 2
                local_cos = math.cos(math.radians(local_lat))
                zoom_ax.set_aspect(1.0 / local_cos, adjustable="box")
                zoom_ax.set_extent(extent_zoom, crs=ccrs.PlateCarree())

                # 底图 + 省界
                render_zoom_inset_content(zoom_ax, extent_zoom)
                # 完整布局管道（LayoutEngine + 放置 + 松弛 + 渲染）
                _render_zoom_pipeline(
                    zoom_ax, extent_zoom, cluster,
                    cities, segments, cfg["day_colors"], output,
                )

                # 截图 → RGBA → 圆形裁剪
                zoom_fig.canvas.draw()
                import numpy as np
                buf = np.array(zoom_fig.canvas.renderer.buffer_rgba())
                plt.close(zoom_fig)

                # 圆形 mask：渲染范围 = render_r, 圆展示范围 = zoom_r
                h, w = buf.shape[:2]
                y, x_arr = np.ogrid[:h, :w]
                cx_px, cy_px = w / 2, h / 2
                render_r = (extent_zoom[1] - extent_zoom[0]) / 2  # 渲染半径(°)
                # 圆在像素空间中的半径（方图大的范围，圆只取中心部分）
                circle_r_px = (min(w, h) / 2) * (display_radius / render_r)
                ring_w = 3  # 红色环宽度 px
                dist = np.sqrt((x_arr - cx_px)**2 + (y - cy_px)**2)
                # 圈外透明
                buf[dist >= circle_r_px] = [0, 0, 0, 0]
                # 红色环
                ring = (dist >= circle_r_px - ring_w) & (dist < circle_r_px)
                buf[ring] = [228, 60, 60, 255]  # #E74C3C

                # ── 螺旋搜索放置（用圆形实际尺寸碰撞）──
                from config import RENDER_MARGIN as _RM
                circle_dia_inch = zoom_w / _RM
                circle_fig_w = circle_dia_inch / fig.get_figwidth()
                circle_fig_h = circle_dia_inch / fig.get_figheight()
                # 转为地图坐标碰撞尺寸
                map_lon_span = extent[1] - extent[0]
                map_lat_span = extent[3] - extent[2]
                circle_hw = (circle_fig_w * map_lon_span / 0.98) / 2
                circle_hh = (circle_fig_h * map_lat_span / 0.98) / 2

                center_lon = (extent_zoom[0] + extent_zoom[1]) / 2
                center_lat = (extent_zoom[2] + extent_zoom[3]) / 2
                cx = cy = None
                for step in range(1, 25):
                    radius = 0.5 + step * 0.2
                    for ang_idx in range(8):
                        angle = math.radians(ang_idx * 45 + step * 15)
                        tx = center_lon + radius * math.cos(angle)
                        ty = center_lat + radius * math.sin(angle)
                        if not (extent[0] + circle_hw < tx < extent[1] - circle_hw):
                            continue
                        if not (extent[2] + circle_hh < ty < extent[3] - circle_hh):
                            continue
                        if layout.is_position_clear(tx, ty, circle_hw, circle_hh,
                                                    margin=0.03, my_kind="inset"):
                            cx, cy = tx, ty
                            break
                    if cx is not None:
                        break
                if cx is None:
                    print(f"  放大镜{ci+1}: 无合适位置，跳过")
                    continue
                layout.place(cx, cy, circle_hw, circle_hh, f"inset_{cx:.2f}")

                # 地图坐标 → figure 坐标
                ax_bbox = ax.get_position()
                xlim = ax.get_xlim()
                ylim = ax.get_ylim()
                fig_cx = ax_bbox.x0 + ax_bbox.width * (cx - xlim[0]) / (xlim[1] - xlim[0])
                fig_cy = ax_bbox.y0 + ax_bbox.height * (cy - ylim[0]) / (ylim[1] - ylim[0])
                ins_fig_w = zoom_w / fig.get_figwidth()
                ins_fig_h = zoom_h / fig.get_figheight()

                ins_ax = fig.add_axes([
                    fig_cx - ins_fig_w / 2, fig_cy - ins_fig_h / 2,
                    ins_fig_w, ins_fig_h,
                ])
                ins_ax.imshow(buf, origin="upper")
                ins_ax.set_xticks([])
                ins_ax.set_yticks([])
                for spine in ins_ax.spines.values():
                    spine.set_visible(False)
                ins_ax.set_facecolor("none")

                # ── 主图虚线圆 + 引线 ──
                # 放大镜在 figure 空间是正圆→地理空间是椭圆，需要 lon/lat 两个半径
                ax_bbox2 = ax.get_position()
                xlim2 = ax.get_xlim()
                ylim2 = ax.get_ylim()
                circle_fig_r = (circle_dia_inch / 2) / fig.get_figwidth()
                ins_r_lon = circle_fig_r / ax_bbox2.width * (xlim2[1] - xlim2[0])
                ins_r_lat = circle_fig_r / ax_bbox2.height * (ylim2[1] - ylim2[0])
                render_zoom_indicator(ax, extent_zoom, select_radius, crs_cos,
                                      inset_cx=cx, inset_cy=cy,
                                      inset_r_lon=ins_r_lon, inset_r_lat=ins_r_lat)

                city_names = [cities[i]["name"] for i in sorted(cluster)]
                print(f"  放大图{ci+1}: {'+'.join(city_names)} -> "
                      f"({extent_zoom[0]:.2f},{extent_zoom[1]:.2f},"
                      f"{extent_zoom[2]:.2f},{extent_zoom[3]:.2f})")
    except (ValueError, TypeError, OSError, RuntimeError) as e:
        print(f"  局部放大图失败(跳过): {e}")
        import traceback
        traceback.print_exc()

    # ── 输出 ──
    print("保存...")
    if "output_filename" in output:
        route_name = output["output_filename"]
    else:
        route_name = f"{cities[0]['name']}-{cities[-1]['name']}-{cfg['title']}"
    # 跨平台兼容：替换非法文件名字符
    route_name = route_name.replace("→", "-").replace("->", "-")
    route_name = route_name.replace("/", "-").replace(":", "-").replace("\\", "-")
    cache_dir = os.path.expanduser(output["cache_dir"])
    os.makedirs(cache_dir, exist_ok=True)
    out_path = os.path.join(cache_dir, f"{route_name}.png")

    plt.savefig(out_path, dpi=output["dpi"], facecolor="white")
    plt.close()

    if output.get("desktop_copy", False):
        if platform.system() == "Darwin":
            desktop = os.path.expanduser(f"~/Desktop/{route_name}.png")
        elif platform.system() == "Windows":
            desktop = os.path.join(os.environ.get("USERPROFILE", ""),
                                   "Desktop", f"{route_name}.png")
        else:
            desktop = os.path.expanduser(f"~/Desktop/{route_name}.png")
        shutil.copy2(out_path, desktop)
        print(f"  桌面副本: {desktop}")

    mb = os.path.getsize(out_path) / 1024 / 1024
    print(f"完成! {mb:.1f} MB -> {out_path}")
    return out_path


def main():
    parser = argparse.ArgumentParser(description="自驾路线图生成器")
    parser.add_argument("config", nargs="?", help="JSON 配置文件路径")
    parser.add_argument("--output", "-o", default=None, help="输出文件路径")
    parser.add_argument("--all", action="store_true", help="生成 routes/ 下全部路线")
    parser.add_argument("--list", action="store_true", help="列出可用路线")
    args = parser.parse_args()

    if args.list:
        routes_dir = os.path.join(os.path.dirname(__file__), "routes")
        for f in sorted(os.listdir(routes_dir)):
            if f.endswith("_config.json"):
                cfg = load_config(os.path.join(routes_dir, f))
                print(f"  {f.replace('_config.json',''):20s} {cfg['title']}")
        return 0

    if args.all:
        routes_dir = os.path.join(os.path.dirname(__file__), "routes")
        configs = sorted(f for f in os.listdir(routes_dir) if f.endswith("_config.json"))
        for f in configs:
            path = os.path.join(routes_dir, f)
            print(f"\n{'='*40}\n  {f}\n{'='*40}")
            cfg = load_config(path)
            out = generate(cfg)
            if args.output:
                shutil.copy2(out, os.path.expanduser(args.output))
        return 0

    if not args.config:
        parser.print_help()
        return 1

    cfg = load_config(args.config)
    out = generate(cfg)
    if args.output:
        shutil.copy2(out, os.path.expanduser(args.output))
    return 0


if __name__ == "__main__":
    sys.exit(main())
