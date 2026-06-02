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
    """计算放大区域范围（以簇中心为圆心，覆盖最远点 + padding）。

    返回正方形 extent，适合圆形放大镜显示。

    Args:
        cluster_indices: 城市索引集合
        cities: 城市列表
        padding: 半径外扩倍率（>1 扩大，<1 缩小）

    Returns:
        [lon_min, lon_max, lat_min, lat_max] 或 None
    """
    all_lons = []
    all_lats = []
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

    # 计算覆盖所有点的最小半径
    max_dist = 0.0
    for lon, lat in zip(all_lons, all_lats):
        d = math.hypot(lon - center_lon, lat - center_lat)
        if d > max_dist:
            max_dist = d
    radius = max(max_dist * padding, 0.15)

    # 正方形 extent（保证圆形不裁剪）
    return [
        round(center_lon - radius, 3),
        round(center_lon + radius, 3),
        round(center_lat - radius, 3),
        round(center_lat + radius, 3),
    ]


def _place_zoom_inset(layout: LayoutEngine,
                      extent_zoom: list,
                      main_extent: list,
                      crs_cos: float) -> tuple:
    """螺旋搜索空白区域放置放大图。

    从放大区域的中心出发，螺旋式向外搜索，直到找到
    不与已有元素冲突的位置。

    Args:
        layout: 布局引擎
        extent_zoom: 放大区域 [lon_min, lon_max, lat_min, lat_max]
        main_extent: 主图范围
        crs_cos: 纬度余弦补偿

    Returns:
        (center_lon, center_lat, half_w, half_h) 永远返回有效位置
    """
    inset_fig_w = 0.25   # 嵌入后实际 5x 放大
    map_lon_span = main_extent[1] - main_extent[0]
    map_lat_span = main_extent[3] - main_extent[2]

    zoom_lon_span = extent_zoom[1] - extent_zoom[0]
    zoom_lat_span = extent_zoom[3] - extent_zoom[2]

    zoom_ratio = (zoom_lat_span / (zoom_lon_span * crs_cos)) if zoom_lon_span > 0 else 1.0
    inset_fig_h = inset_fig_w * zoom_ratio
    inset_fig_h = max(0.15, min(0.35, inset_fig_h))

    inset_hw = (inset_fig_w * map_lon_span / 0.98) / 2
    inset_hh = (inset_fig_h * map_lat_span / 0.98) / 2

    center_lon = (extent_zoom[0] + extent_zoom[1]) / 2
    center_lat = (extent_zoom[2] + extent_zoom[3]) / 2

    for step in range(1, 20):
        radius = 0.3 + step * 0.25
        for ang_idx in range(8):
            angle = math.radians(ang_idx * 45 + step * 15)
            cx = center_lon + radius * math.cos(angle)
            cy = center_lat + radius * math.sin(angle)

            if not (main_extent[0] + inset_hw < cx < main_extent[1] - inset_hw):
                continue
            if not (main_extent[2] + inset_hh < cy < main_extent[3] - inset_hh):
                continue

            if layout.is_position_clear(cx, cy, inset_hw, inset_hh,
                                        margin=0.05, my_kind="inset"):
                layout.place(cx, cy, inset_hw, inset_hh,
                            f"inset_{center_lon:.2f}_{center_lat:.2f}")
                return cx, cy, inset_hw, inset_hh

    # 回退：右上角
    cx = main_extent[1] - inset_hw - 0.3
    cy = main_extent[3] - inset_hh - 0.3
    layout.place(cx, cy, inset_hw, inset_hh,
                f"inset_fb_{center_lon:.2f}")
    return cx, cy, inset_hw, inset_hh


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
                       city_radius: float = None) -> list:
    """L4: 景点放置——仅放置，不渲染。返回 render recipes 列表。"""
    if city_radius is None:
        city_radius = CITY_RADIUS
    print("景点(放置)...")
    recipes = []
    for idx, c in enumerate(cities):
        prim_list = c.get("attractions_primary", [])
        sec_list = c.get("attractions_secondary", [])

        prim_list = _safe_attr(prim_list, c["name"], "主要")
        sec_list = _safe_attr(sec_list, c["name"], "次要")

        # 城圈内景点：合并引线
        in_prim = [a for a in prim_list
                   if math.hypot(a["lon"] - c["lon"], a["lat"] - c["lat"])
                   < city_radius + 0.02]
        in_sec = [a for a in sec_list
                  if math.hypot(a["lon"] - c["lon"], a["lat"] - c["lat"])
                  < city_radius + 0.02]
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
                      cities: list, crs_cos: float) -> list:
    """L5: 天次标注——仅放置，不渲染。返回 render recipes 列表。"""
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
            tx, ty, ha = layout.place_travel_day(
                f"D{day}", seg_indices, segments, cities,
            )
            recipes.append({
                "kind": "travel",
                "label_key": f"day_D{day}",
                "text": f"D{day}",
                "ha": ha,
            })

    return recipes


def _place_dist_time_labels(layout: LayoutEngine,
                            segments: list, cities: list) -> list:
    """L6: 距离/时间标注——仅放置，不渲染。返回 render recipes 列表。"""
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

def _render_zoom_pipeline(ax, extent_zoom: list,
                          cluster: set, cities: list, segments: list,
                          day_colors: dict, output: dict) -> None:
    """在给定 axes 上运行完整生成管道。

    只处理簇内城市（景点、标注），外部连线只画路线不标注。
    """
    # 只取簇内城市
    cluster_list = sorted(cluster)

    # 局部城市列表 + index 映射
    local_cities = [cities[i] for i in cluster_list]
    idx_map = {old: new for new, old in enumerate(cluster_list)}

    # 段：两端都在簇内 → 完整标注；一端在簇内 → 只画线
    local_segs = []     # 完整标注
    external_segs = []  # 只画线
    for seg in segments:
        fi, ti = seg["from_index"], seg["to_index"]
        f_in = fi in cluster
        t_in = ti in cluster
        if f_in and t_in:
            ls = dict(seg)
            ls["from_index"] = idx_map[fi]
            ls["to_index"] = idx_map[ti]
            local_segs.append(ls)
        elif f_in and not t_in:
            external_segs.append((fi, ti, seg))
        elif t_in and not f_in:
            external_segs.append((ti, fi, seg))

    # 局部天次颜色
    local_day_colors = {}
    for seg in local_segs + [s for _, _, s in external_segs]:
        d = str(seg["day"])
        if d not in local_day_colors:
            local_day_colors[d] = day_colors.get(d, "#888888")

    # 纬度补偿
    avg_lat = sum(c["lat"] for c in local_cities) / len(local_cities)
    crs_cos = math.cos(math.radians(avg_lat))

    from config import ZOOM_FACTOR
    zoom_city_radius = CITY_RADIUS / ZOOM_FACTOR

    # LayoutEngine
    extent_w = extent_zoom[1] - extent_zoom[0]
    px_per_deg = (output.get("width_inch", 5.0) * 0.98 * output["dpi"]) / extent_w if extent_w > 0 else 200
    layout = LayoutEngine(px_per_deg, output["dpi"])

    # ── 先画外部连线（只画线，不参与布局） ──
    from renderer import render_route_segment as _draw_route
    for fi, ti, seg in external_segs:
        color = day_colors.get(str(seg["day"]), "#888888")
        _draw_route(ax,
                    cities[fi]["lon"], cities[fi]["lat"],
                    cities[ti]["lon"], cities[ti]["lat"],
                    color)

    # L2: 簇内路线 + 注册
    from renderer import render_all_routes as _render_routes
    route_pairs = _render_routes(ax, local_segs, local_cities, local_day_colors)
    for fi, ti in route_pairs:
        x1, y1 = local_cities[fi]["lon"], local_cities[fi]["lat"]
        x2, y2 = local_cities[ti]["lon"], local_cities[ti]["lat"]
        layout.register_route(x1, y1, x2, y2, LayoutEngine.ROUTE_HW)

    # L3: 城市节点
    from renderer import render_city_node as _render_node
    for c in local_cities:
        _render_node(ax, c["name"], c["lon"], c["lat"],
                     c.get("color", "#888888"), crs_cos,
                     radius=zoom_city_radius)
        layout.place(c["lon"], c["lat"],
                     zoom_city_radius + 0.02,
                     zoom_city_radius * crs_cos + 0.02,
                     f"city_{c['name']}")

    # 临时 cfg
    local_cfg = {
        "cities": local_cities,
        "segments": local_segs,
        "day_colors": local_day_colors,
        "rest_days": {},
        "day_attractions": {},
        "output": output,
    }

    # 预计算天数
    day_to_segs = {}
    for si, seg in enumerate(local_segs):
        d = seg["day"]
        day_to_segs.setdefault(d, []).append(si)
    all_days = sorted(day_to_segs.keys())

    if not all_days:
        return  # 无簇内段

    # L5: 天次
    day_recipes = _place_day_labels(
        layout, local_cfg, all_days, day_to_segs, local_cities, crs_cos)
    # L6: 距离/时间
    dt_recipes = _place_dist_time_labels(layout, local_segs, local_cities)
    # L4: 景点（传入缩放后的城圈半径）
    attr_recipes = _place_attractions(layout, local_cities,
                                      city_radius=zoom_city_radius)

    # 全局松弛（范围 0.5°+ 足够，不会推到外面）
    layout.relax_overlaps()

    # 渲染
    _render_day_items(ax, layout, day_recipes)
    _render_attr_items(ax, layout, attr_recipes)
    _render_dt_items(ax, layout, dt_recipes)


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

    # 阶段1 — 放置所有可松弛元素（仅注册坐标，不渲染）
    day_recipes = _place_day_labels(layout, cfg, all_days, day_to_segs, cities, crs_cos)
    dt_recipes = _place_dist_time_labels(layout, segments, cities)
    attr_recipes = _place_attractions(layout, cities)

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
        close_pairs = _detect_close_pairs(cities, segments, INSET_THRESHOLD)
        if close_pairs:
            print(f"  检测到 {len(close_pairs)} 对过近城市")
            clusters = _group_connected_pairs(close_pairs)

            for ci, cluster in enumerate(clusters):
                extent_zoom = _compute_zoom_extent(
                    cluster, cities, INSET_PADDING)
                if extent_zoom is None:
                    continue

                # ── 创建独立 figure 渲染放大图 ──
                zoom_dpi = output["dpi"]
                zoom_w, zoom_h = 5.0, 5.0  # 正方形英寸
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
                render_zoom_inset_content(
                    zoom_ax, extent_zoom, cluster,
                    cities, segments, cfg["day_colors"],
                )
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

                # 圆形 mask（外圈透明，红色边框）
                h, w = buf.shape[:2]
                y, x_arr = np.ogrid[:h, :w]
                cx_px, cy_px = w / 2, h / 2
                out_r = min(w, h) / 2           # 外半径
                in_r = out_r - 3                 # 内半径（3px 红色环）
                dist = np.sqrt((x_arr - cx_px)**2 + (y - cy_px)**2)
                # 圈外透明
                buf[dist >= out_r] = [0, 0, 0, 0]
                # 红色环
                ring = (dist >= in_r) & (dist < out_r)
                buf[ring] = [228, 60, 60, 255]  # #E74C3C

                # ── 螺旋搜索放置位置（地图坐标） → figure 像素坐标 ──
                cx, cy, hw, hh = _place_zoom_inset(
                    layout, extent_zoom, extent, crs_cos)

                # 地图坐标 → figure 坐标 → 像素
                disp_xy = ax.transData.transform((cx, cy))
                fig_xy = fig.transFigure.inverted().transform(disp_xy)
                fig_w_px = int(fig.get_figwidth() * fig.get_dpi())
                fig_h_px = int(fig.get_figheight() * fig.get_dpi())
                px_cx = int(fig_xy[0] * fig_w_px)
                px_cy = int(fig_xy[1] * fig_h_px)

                # 直接在 figure 画布上放置圆形 RGBA 图片（无 axes、无白边）
                fig.figimage(
                    buf,
                    xo=px_cx - buf.shape[1] // 2,
                    yo=px_cy - buf.shape[0] // 2,
                    origin="upper",
                    zorder=99,
                )

                # ── 主图标记：虚线圆 + 连接线 ──
                render_zoom_indicator(ax, extent_zoom, cx, cy, hw, hh, crs_cos)

                city_names = [cities[i]["name"] for i in sorted(cluster)]
                print(f"  放大图{ci+1}: {'+'.join(city_names)} -> "
                      f"({extent_zoom[0]:.2f},{extent_zoom[1]:.2f},"
                      f"{extent_zoom[2]:.2f},{extent_zoom[3]:.2f})")
    except Exception as e:
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
