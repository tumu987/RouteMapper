"""渲染引擎：所有 matplotlib 绘制函数。"""
import math
import os
import platform
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
from matplotlib.font_manager import FontProperties
from matplotlib.patches import Ellipse
import cartopy.crs as ccrs
import cartopy.feature as cfeature
from cartopy.io import shapereader
from shapely.geometry import box
from typing import Any, Dict, List, Set

from config import (
    CITY_RADIUS, DAY_LABEL_COLOR, DIST_COLOR, TIME_COLOR,
    ITINERARY_COLOR, TITLE_COLOR, SUBTITLE_COLOR,
    ATTR_PRIM_COLOR, ATTR_SEC_COLOR, LEADER_LINE_COLOR, TITLE_SEP_COLOR,
    _count_total_days,
)

# ── 字体 ──

_FONT_PATH = None
_FONT_CANDIDATES: List[str] = []

_system = platform.system()
if _system == "Darwin":
    _FONT_CANDIDATES = [
        "/System/Library/Fonts/STHeiti Medium.ttc",
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/System/Library/Fonts/AppleSDGothicNeo.ttc",
    ]
elif _system == "Linux":
    _FONT_CANDIDATES = [
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
        "/usr/share/fonts/truetype/arphic/uming.ttc",
    ]
elif _system == "Windows":
    _FONT_CANDIDATES = [
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simhei.ttf",
        "C:/Windows/Fonts/simsun.ttc",
    ]

for _fp in _FONT_CANDIDATES:
    if os.path.exists(_fp):
        _FONT_PATH = _fp
        break

if _FONT_PATH is None:
    print("=" * 60)
    print("  警告: 未找到中文字体!")
    print("  Helvetica 无法渲染中文，图上中文将显示为方块(tofu)。")
    print("  请安装中文字体，例如:")
    print("    macOS:  STHeiti 或 PingFang (通常已内置)")
    print("    Linux:  sudo apt install fonts-wqy-zenhei")
    print("    Windows: 微软雅黑 或 SimHei (通常已内置)")
    print("=" * 60)
    _FONT_PATH = "/System/Library/Fonts/Helvetica.ttc"


def F(size: float = 12) -> FontProperties:
    """创建加粗华文黑体 FontProperties。"""
    return FontProperties(fname=_FONT_PATH, size=size, weight="bold")


def ST(w: float = 4) -> list:
    """白色描边 path effect。"""
    return [pe.withStroke(linewidth=w, foreground="white")]


# ── 底图渲染 ──

def render_base_map(ax: Any, extent: List[float]) -> None:
    """渲染底图：陆地、水域、湖泊、海岸线、河流、经纬网。"""
    ax.add_feature(cfeature.LAND, facecolor="#F8F4EC", zorder=1)
    ax.add_feature(cfeature.OCEAN, facecolor="#E8EDF4", zorder=1)
    ax.add_feature(cfeature.LAKES, facecolor="#DAE5F0",
                   edgecolor="#AABBCC", linewidth=1.0, zorder=2)
    ax.add_feature(cfeature.COASTLINE, edgecolor=LEADER_LINE_COLOR,
                   linewidth=2.0, zorder=3)
    ax.add_feature(cfeature.BORDERS, edgecolor="#888888",
                   linewidth=1.5, alpha=0.6, zorder=3)
    ax.add_feature(cfeature.RIVERS, edgecolor="#BFD7EA",
                   linewidth=0.8, alpha=0.5, zorder=2)

    ax.gridlines(draw_labels=False, linewidth=1.0, color="#BBBBBB",
                 alpha=0.3, linestyle="--")


def render_provinces(ax: Any, extent: List[float],
                     province_colors: Dict[str, str],
                     en_prov_map: Dict[str, str],
                     prov_cn_names: Dict[str, str]) -> Set[str]:
    """渲染省界和省份名水印。返回途经省份简称集合。

    Args:
        province_colors: {简称: 颜色}
        en_prov_map: {Natural Earth 英文名: 简称}
        prov_cn_names: {简称: 中文名}
    """
    extent_box = box(extent[0], extent[2], extent[1], extent[3])
    seen_provinces: Set[str] = set()

    try:
        reader = shapereader.Reader(
            shapereader.natural_earth(
                resolution="50m", category="cultural",
                name="admin_1_states_provinces"
            )
        )
    except (OSError, ValueError, ImportError) as e:
        print(f"  [省界] Natural Earth 数据加载失败: {e}")
        print(f"  [省界] 请检查网络连接或 cartopy 数据文件")
        return seen_provinces

    try:
        for rec in reader.records():
            name_en = rec.attributes.get("name", "")
            short = en_prov_map.get(name_en, "")
            if not short:
                continue
            if not extent_box.intersects(rec.geometry):
                continue

            seen_provinces.add(short)
            color = province_colors.get(short, "#888888")

            # 省界线
            ax.add_geometries(
                [rec.geometry], crs=ccrs.PlateCarree(),
                facecolor="none", edgecolor=color,
                linewidth=2.5, alpha=0.50, zorder=4,
            )

            # 省份名水印
            centroid = rec.geometry.centroid
            cx, cy = centroid.x, centroid.y
            if not (extent[0] <= cx <= extent[1] and extent[2] <= cy <= extent[3]):
                bounds = rec.geometry.bounds
                cx = (bounds[0] + bounds[2]) / 2
                cy = (bounds[1] + bounds[3]) / 2
            cn_name = prov_cn_names.get(short, short)
            ax.text(cx, cy, cn_name, fontproperties=F(20),
                    color=color, alpha=0.35, ha="center", va="center", zorder=4)
    except (OSError, ValueError) as e:
        print(f"  [省界] 渲染失败: {e}")

    return seen_provinces


# ── 路线渲染 ──

def render_route_segment(ax: Any, x1: float, y1: float, x2: float, y2: float,
                         color: str) -> None:
    """渲染单条路线段（多层发光羽化）。

    宽22×a0.06 → 宽16×a0.12 → 宽10×a0.25 → 核心线宽6
    """
    from matplotlib.colors import to_rgba
    for gw, ga in [(12, 0.08), (6, 0.20)]:
        ax.plot([x1, x2], [y1, y2], color=to_rgba(color, ga),
                linewidth=gw, solid_capstyle="round",
                transform=ccrs.PlateCarree(), zorder=5)
    ax.plot([x1, x2], [y1, y2], color=color, linewidth=5,
            alpha=1.0, solid_capstyle="round",
            transform=ccrs.PlateCarree(), zorder=6,
            path_effects=[
                pe.withStroke(linewidth=7, foreground="white", alpha=0.30)
            ])


def render_all_routes(ax: Any, segments: List[dict], cities: List[dict],
                      day_colors: Dict[str, str]) -> Set[tuple]:
    """渲染所有路线段。返回已注册的路线对集合（用于去重碰撞注册）。"""
    seen_pairs: Set[tuple] = set()
    for seg in segments:
        fi, ti = seg["from_index"], seg["to_index"]
        day = seg["day"]
        color = day_colors.get(str(day), "#888888")
        x1, y1 = cities[fi]["lon"], cities[fi]["lat"]
        x2, y2 = cities[ti]["lon"], cities[ti]["lat"]
        render_route_segment(ax, x1, y1, x2, y2, color)

        # 去重往返段
        key = tuple(sorted([fi, ti]))
        if key not in seen_pairs:
            seen_pairs.add(key)
    return seen_pairs


# ── 城市节点 ──

def render_city_node(ax: Any, name: str, lon: float, lat: float,
                     color: str, crs_cos: float) -> None:
    """渲染城市节点：椭圆圈 + 圈内文字。"""
    r = CITY_RADIUS
    # 椭圆补偿纬度拉伸
    ax.add_patch(Ellipse(
        (lon, lat), width=2 * r, height=2 * r * crs_cos,
        facecolor="white", edgecolor=color, linewidth=4,
        transform=ccrs.PlateCarree(), zorder=20,
    ))
    ax.text(lon, lat, name, fontproperties=F(16), color=color,
            ha="center", va="center", zorder=21, path_effects=ST(4))


# ── 天次标注 ──

def render_day_label(ax: Any, text: str, x: float, y: float,
                     ha: str, color: str = None,
                     size: int = 16) -> None:
    """渲染天次标注。"""
    if color is None:
        color = DAY_LABEL_COLOR
    ax.text(x, y, text, fontproperties=F(size), color=color,
            ha=ha, va="center", zorder=30, path_effects=ST(4))


def render_rest_day_label(ax: Any, day_num: str, city_full: str,
                          dx: float, dy: float, dha: str,
                          cx: float, cy: float,
                          line_gap: float = 0.10) -> None:
    """渲染休息日标注（两行）。"""
    ax.text(dx, dy, day_num, fontproperties=F(16), color=DAY_LABEL_COLOR,
            ha=dha, va="center", zorder=30, path_effects=ST(4))
    ax.text(cx, cy, city_full, fontproperties=F(14), color=DAY_LABEL_COLOR,
            ha="center", va="center", zorder=30, path_effects=ST(4))


# ── 距离/时间 ──

def render_dist_time(ax: Any, dist_text: str, time_text: str,
                     dx: float, dy: float, tx: float, ty: float) -> None:
    """渲染距离和时间标注。"""
    ax.text(dx, dy, dist_text, fontproperties=F(14), color=DIST_COLOR,
            ha="center", va="center", zorder=30, path_effects=ST(4))
    ax.text(tx, ty, time_text, fontproperties=F(14), color=TIME_COLOR,
            ha="center", va="center", zorder=30, path_effects=ST(4))


# ── 景点 ──

def render_attraction_outside(ax: Any, name: str, alat: float, alon: float,
                               is_primary: bool, x: float, y: float,
                               ha: str, leader_info: dict) -> None:
    """渲染城圈外景点：打点 + 紧邻标签 + 可选折线引线。"""
    color = ATTR_PRIM_COLOR if is_primary else ATTR_SEC_COLOR
    sz = 14 if is_primary else 12
    mfc = color if is_primary else "none"

    # 打点
    ax.plot(alon, alat, "o", color=color, markersize=4,
            markerfacecolor=mfc, markeredgewidth=1.5,
            transform=ccrs.PlateCarree(), zorder=16)

    # 折线引线：打点→斜线→拐点→水平线→文字
    if leader_info.get("need_leader", False):
        lx, ly = leader_info.get("lx", x), leader_info.get("ly", y)
        # 拐点x延伸60%，拐点y对齐水平线确保不断开
        knee_x = alon + (lx - alon) * 0.6
        ls = "--" if not is_primary else "-"
        ax.plot([alon, knee_x], [alat, ly], color=color,
                linewidth=1.0, alpha=0.5, linestyle=ls,
                transform=ccrs.PlateCarree(), zorder=15)
        ax.plot([knee_x, lx], [ly, ly], color=color,
                linewidth=1.0, alpha=0.5, linestyle=ls,
                transform=ccrs.PlateCarree(), zorder=15)

    # 标签
    ax.text(x, y, name, fontproperties=F(sz), color=color,
            ha=ha, va="center", zorder=17, path_effects=ST(3))


def render_grouped_attractions(ax: Any, items: List[tuple],
                                city_lon: float, city_lat: float) -> None:
    """城圈内景点共享一条折线引线：城圈边缘→斜线→拐点→水平线→文字。"""
    if not items:
        return
    bx = items[0][0]
    mid_y = (items[0][1] + items[-1][1]) / 2

    # 城圈边缘连接点：城圈上朝向文字组的角度
    angle = math.atan2(mid_y - city_lat, bx - city_lon)
    cr = CITY_RADIUS
    edge_x = city_lon + cr * math.cos(angle)
    edge_y = city_lat + cr * math.sin(angle)

    # 拐点x：斜线延伸到60%处；拐点y对齐水平线
    knee_x = edge_x + (bx - edge_x) * 0.6
    # 斜线：城圈边缘 → 拐点（拐点y=mid_y，确保连接）
    ax.plot([edge_x, knee_x], [edge_y, mid_y], color=LEADER_LINE_COLOR,
            linewidth=1.0, alpha=0.5, transform=ccrs.PlateCarree(), zorder=15)
    # 水平线：拐点 → 文字
    ax.plot([knee_x, bx], [mid_y, mid_y], color=LEADER_LINE_COLOR,
            linewidth=1.0, alpha=0.5, transform=ccrs.PlateCarree(), zorder=15)

    for x, y, name, color, sz, ha_text, edge_x2, edge_y2 in items:
        ax.text(x, y, name, fontproperties=F(sz), color=color,
                ha=ha_text, va="center", zorder=17, path_effects=ST(3))


# ── 标题 ──

def render_title(ax: Any, cfg: Dict[str, Any]) -> None:
    """渲染主标题和副标题（使用画布相对坐标，固定在顶部）。"""
    cities = cfg["cities"]
    title = cfg["title"]
    subtitle = cfg.get("subtitle", "")
    days = _count_total_days(cfg)
    try:
        total_km = sum(float(s.get("distance", "0km").replace("km", ""))
                       for s in cfg["segments"])
    except (ValueError, TypeError):
        total_km = 0

    # 使用 axes 相对坐标，始终固定在画布顶部
    ax.text(0.5, 0.985,
            f"{cities[0]['name']}->{cities[-1]['name']} . {title}",
            fontproperties=F(28), color=TITLE_COLOR,
            ha="center", va="top", transform=ax.transAxes,
            zorder=100, path_effects=ST(6))

    sub_text = subtitle
    if days:
        sub_text += f"  .  {days}天"
    if total_km:
        sub_text += f" . 约{total_km:.0f}km"

    ax.text(0.5, 0.955, sub_text,
            fontproperties=F(16), color=SUBTITLE_COLOR,
            ha="center", va="top", transform=ax.transAxes,
            zorder=100, path_effects=ST(4))

    ax.plot([0.05, 0.95], [0.945, 0.945], color=TITLE_SEP_COLOR, linewidth=1,
            transform=ax.transAxes, zorder=100)


# ── 行程表 ──

def render_itinerary(ax: Any, lines: List[str], cx: float, cy: float,
                     tw: float, th: float, font_size: float = 14,
                     line_height: float = 0.21) -> None:
    """渲染行程表。"""
    for i, line in enumerate(lines):
        yy = cy + th / 2 - 0.08 - i * line_height
        ax.text(cx, yy, line, fontproperties=F(font_size),
                color=ITINERARY_COLOR, ha="left", va="top",
                zorder=95, path_effects=ST(1.5))


# ── 局部放大图 ──

def render_zoom_inset_content(ax: Any, extent_zoom: list,
                               cluster_indices: set,
                               cities: list, segments: list,
                               day_colors: dict) -> None:
    """在给定的 axes 上渲染放大图内容。

    包含：底图 + 省界 + 簇内城市节点 + 簇内路线段 + 景点。
    字体比主图小一号（×0.75）。

    Args:
        ax: 已创建并设好 extent 的 inset axes（PlateCarree 投影）
        extent_zoom: 放大区域范围
        cluster_indices: 簇内城市索引集合
        cities: 全部城市列表
        segments: 全部路线段列表
        day_colors: 天次颜色映射
    """
    from config import PROVINCE_COLORS, EN_PROV_MAP, PROV_CN_NAMES

    # 底图
    render_base_map(ax, extent_zoom)
    # 省界（在放大范围内）
    render_provinces(ax, extent_zoom, PROVINCE_COLORS,
                     EN_PROV_MAP, PROV_CN_NAMES)

    # 字体缩放
    font_city = 12   # 16 × 0.75
    font_prim = 10   # 14 × 0.75
    font_sec = 9     # 12 × 0.75

    # 簇内城市节点
    cluster_cities = {idx: cities[idx] for idx in cluster_indices}
    avg_lat = (sum(c["lat"] for c in cluster_cities.values()) /
               len(cluster_cities)) if cluster_cities else 45
    crs_cos_local = math.cos(math.radians(avg_lat))

    for idx, c in cluster_cities.items():
        # 城市椭圆
        r = CITY_RADIUS
        ax.add_patch(Ellipse(
            (c["lon"], c["lat"]), width=2 * r, height=2 * r * crs_cos_local,
            facecolor="white", edgecolor=c.get("color", "#888888"),
            linewidth=3, transform=ccrs.PlateCarree(), zorder=20,
        ))
        ax.text(c["lon"], c["lat"], c["name"],
                fontproperties=F(font_city), color=c.get("color", "#888888"),
                ha="center", va="center", zorder=21, path_effects=ST(3))

        # 景点直接绘制在真实坐标附近（简化布局，不做碰撞检测）
        for is_prim, attr_key in [(True, "attractions_primary"),
                                   (False, "attractions_secondary")]:
            color = ATTR_PRIM_COLOR if is_prim else ATTR_SEC_COLOR
            sz = font_prim if is_prim else font_sec
            for a in c.get(attr_key, []):
                try:
                    alon, alat = float(a["lon"]), float(a["lat"])
                except (ValueError, TypeError):
                    continue
                # 打点
                ax.plot(alon, alat, "o", color=color, markersize=4,
                        markerfacecolor=color if is_prim else "none",
                        markeredgewidth=1.5,
                        transform=ccrs.PlateCarree(), zorder=16)
                # 标签：直接放在坐标旁
                ax.text(alon + 0.03, alat + 0.02, a["name"],
                        fontproperties=F(sz), color=color,
                        ha="left", va="bottom", zorder=17,
                        path_effects=ST(2))

    # 簇内路线段
    for seg in segments:
        fi, ti = seg["from_index"], seg["to_index"]
        if fi in cluster_indices and ti in cluster_indices:
            day = seg["day"]
            color = day_colors.get(str(day), "#888888")
            render_route_segment(
                ax,
                cities[fi]["lon"], cities[fi]["lat"],
                cities[ti]["lon"], cities[ti]["lat"],
                color,
            )


def render_zoom_indicator(ax_main: Any, extent_zoom: list,
                          inset_ax: Any, color: str = "#E74C3C") -> None:
    """在主图上绘制放大区域标记和连接线。

    虚线矩形标记放大范围 + 从矩形角到放大图边框角的连接线。

    Args:
        ax_main: 主图 axes
        extent_zoom: 放大区域 [lon_min, lon_max, lat_min, lat_max]
        inset_ax: 放大图 axes（用于获取其位置）
        color: 标记颜色
    """
    lon_min, lon_max, lat_min, lat_max = extent_zoom

    # 虚线矩形标记放大范围
    rect_lons = [lon_min, lon_max, lon_max, lon_min, lon_min]
    rect_lats = [lat_min, lat_min, lat_max, lat_max, lat_min]
    ax_main.plot(rect_lons, rect_lats, color=color, linewidth=1.5,
                 linestyle="--", transform=ccrs.PlateCarree(),
                 zorder=98, alpha=0.7)

    # 获取 inset axes 在图形坐标中的边框四角
    inset_bbox = inset_ax.get_position()

    # 虚线框四角（地图坐标）
    corners_map = [(lon_min, lat_min), (lon_max, lat_min),
                   (lon_max, lat_max), (lon_min, lat_max)]

    # inset 在图形坐标中的四角
    inset_corners_fig = [
        (inset_bbox.x0, inset_bbox.y0),
        (inset_bbox.x1, inset_bbox.y0),
        (inset_bbox.x1, inset_bbox.y1),
        (inset_bbox.x0, inset_bbox.y1),
    ]

    # 找最近的角对 → 画两条连接线
    fig = ax_main.figure
    pairs = []
    for ci, (mlon, mlat) in enumerate(corners_map):
        mx, my = ax_main.transData.transform((mlon, mlat))
        mxf, myf = fig.transFigure.inverted().transform((mx, my))
        for ii, (ixf, iyf) in enumerate(inset_corners_fig):
            dist = math.hypot(mxf - ixf, myf - iyf)
            pairs.append((dist, ci, ii, mlon, mlat, ixf, iyf))

    pairs.sort()
    used_map = set()
    used_inset = set()
    for _, ci, ii, mlon, mlat, ixf, iyf in pairs:
        if ci not in used_map and ii not in used_inset:
            used_map.add(ci)
            used_inset.add(ii)
            ax_main.annotate(
                "", xy=(ixf, iyf), xycoords="figure fraction",
                xytext=(mlon, mlat), textcoords=ccrs.PlateCarree(),
                arrowprops=dict(arrowstyle="-", color=color,
                               linewidth=1, alpha=0.5, ls="--"),
                zorder=97,
            )
        if len(used_map) >= 2:
            break
