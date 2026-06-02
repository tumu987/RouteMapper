"""路线配置加载与验证模块。"""
import json
import math
import os
from typing import Any, Dict, List, Optional


# ── 城市圈半径（地图坐标）──
CITY_RADIUS = 0.13

# ── 颜色常量 ──
DAY_LABEL_COLOR = "#8B44AC"
DIST_COLOR = "#2980B9"
TIME_COLOR = "#E67E22"
ITINERARY_COLOR = "#2C3E50"
TITLE_COLOR = "#2C3E50"
SUBTITLE_COLOR = "#7F8C8D"
ATTR_PRIM_COLOR = "#8B4513"
ATTR_SEC_COLOR = "#27AE60"
LEADER_LINE_COLOR = "#999999"
TITLE_SEP_COLOR = "#CCCCCC"

# 默认输出配置
DEFAULT_OUTPUT = {
    "width_inch": 22,
    "height_inch": 26,
    "dpi": 120,
    "cache_dir": os.path.expanduser("~/.hermes/cache/documents/"),
    "desktop_copy": True,
    "auto_extent": True,
    "tight_extent": True,
}

# 自动天次颜色调色板（20 色，相邻区分度足够）
AUTO_DAY_COLORS = [
    "#E74C3C", "#E67E22", "#F1C40F", "#2ECC71", "#1ABC9C",
    "#3498DB", "#9B59B6", "#E91E63", "#FF9800", "#009688",
    "#607D8B", "#795548", "#CDDC39", "#00BCD4",
    "#FF5722", "#3F51B5", "#4CAF50", "#FFC107",
    "#2196F3", "#F44336",
]

# 省份颜色映射
PROVINCE_COLORS: Dict[str, str] = {
    "XJ": "#CDDC39", "GS": "#673AB7", "QH": "#3F51B5",
    "SN": "#009688", "NX": "#00BCD4", "NM": "#1ABC9C",
    "BJ": "#C0392B", "TJ": "#E74C3C", "HE": "#27AE60",
    "SX": "#2980B9", "HA": "#E67E22", "HB": "#FF9800",
    "SD": "#16A085", "LN": "#E67E22", "JL": "#F39C12",
    "HL": "#F1C40F", "SH": "#E91E63", "JS": "#9B59B6",
    "ZJ": "#8E44AD", "AH": "#D35400", "FJ": "#3498DB",
    "JX": "#2ECC71", "HN": "#FF5722", "GD": "#795548",
    "GX": "#607D8B", "HI": "#FF9800", "CQ": "#9C27B0",
    "SC": "#4CAF50", "GZ": "#2196F3", "YN": "#FF5722",
    "XZ": "#8BC34A", "TW": "#00BCD4", "HK": "#E91E63",
    "MO": "#009688",
}

# Natural Earth 英文名到省份简称
EN_PROV_MAP: Dict[str, str] = {
    "Xinjiang": "XJ", "Xinjiang Uygur": "XJ", "Gansu": "GS", "Qinghai": "QH",
    "Shaanxi": "SN", "Ningxia": "NX", "Ningxia Hui": "NX",
    "Nei Mongol": "NM", "Inner Mongol": "NM",
    "Beijing": "BJ", "Tianjin": "TJ", "Hebei": "HE",
    "Shanxi": "SX", "Henan": "HA", "Hubei": "HB",
    "Shandong": "SD", "Liaoning": "LN", "Jilin": "JL",
    "Heilongjiang": "HL", "Shanghai": "SH", "Jiangsu": "JS",
    "Zhejiang": "ZJ", "Anhui": "AH", "Fujian": "FJ",
    "Jiangxi": "JX", "Hunan": "HN", "Guangdong": "GD",
    "Guangxi": "GX", "Hainan": "HI", "Chongqing": "CQ",
    "Sichuan": "SC", "Guizhou": "GZ", "Yunnan": "YN",
    "Xizang": "XZ", "Taiwan": "TW", "Hong Kong": "HK",
    "Macao": "MO",
}

PROV_CN_NAMES: Dict[str, str] = {
    "BJ": "北京", "TJ": "天津", "HE": "河北", "SX": "山西",
    "NM": "内蒙古", "LN": "辽宁", "JL": "吉林", "HL": "黑龙江",
    "SH": "上海", "JS": "江苏", "ZJ": "浙江", "AH": "安徽",
    "FJ": "福建", "JX": "江西", "SD": "山东", "HA": "河南",
    "HB": "湖北", "HN": "湖南", "GD": "广东", "GX": "广西",
    "HI": "海南", "CQ": "重庆", "SC": "四川", "GZ": "贵州",
    "YN": "云南", "XZ": "西藏", "SN": "陕西", "GS": "甘肃",
    "QH": "青海", "NX": "宁夏", "XJ": "新疆", "TW": "台湾",
    "HK": "香港", "MO": "澳门",
}


def _count_total_days(cfg: dict) -> int:
    """计算总天数（从 segments、rest_days、day_attractions 汇总）。"""
    days = set()
    for seg in cfg.get("segments", []):
        days.add(seg["day"])
    for d in cfg.get("rest_days", {}):
        days.add(int(d))
    for d in cfg.get("day_attractions", {}):
        days.add(int(d))
    return max(days) if days else 0


def _max_day(cfg: dict) -> int:
    """计算最大天数（至少为 1）。"""
    return max(_count_total_days(cfg), 1)


def _ensure_color_contrast(day_colors: dict) -> dict:
    """确保相邻天颜色有足够区分度。从调色板跳跃过近的颜色。"""
    days = sorted(int(k) for k in day_colors.keys())
    result = dict(day_colors)
    for i in range(len(days) - 1):
        d1, d2 = str(days[i]), str(days[i+1])
        c1 = result[d1].lstrip('#')
        c2 = result[d2].lstrip('#')
        r1, g1, b1 = int(c1[0:2],16), int(c1[2:4],16), int(c1[4:6],16)
        r2, g2, b2 = int(c2[0:2],16), int(c2[2:4],16), int(c2[4:6],16)
        dist = math.hypot(r1-r2, g1-g2, b1-b2)
        if dist < 100:
            for alt_color in AUTO_DAY_COLORS:
                ac = alt_color.lstrip('#')
                ar, ag, ab = int(ac[0:2],16), int(ac[2:4],16), int(ac[4:6],16)
                adist = math.hypot(r1-ar, g1-ag, b1-ab)
                if adist > 150:
                    result[d2] = alt_color
                    break
    return result


def load_config(path: str) -> Dict[str, Any]:
    """加载 JSON 配置文件，补充默认值，验证必要字段。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except FileNotFoundError:
        raise FileNotFoundError(f"配置文件不存在: {path}")
    except json.JSONDecodeError as e:
        raise ValueError(f"配置文件 JSON 格式错误: {e}")

    # 验证必要字段
    _validate(cfg)

    # 补充默认值
    cfg.setdefault("output", {})
    for k, v in DEFAULT_OUTPUT.items():
        cfg["output"].setdefault(k, v)

    # 自动补全缺失的天次颜色（若无配置则全部生成）
    max_day = _max_day(cfg)
    if "day_colors" not in cfg:
        cfg["day_colors"] = {}
    for d in range(1, max_day + 1):
        if str(d) not in cfg["day_colors"]:
            cfg["day_colors"][str(d)] = AUTO_DAY_COLORS[(d - 1) % len(AUTO_DAY_COLORS)]
    # 确保相邻天颜色有足够的区分度
    cfg["day_colors"] = _ensure_color_contrast(cfg["day_colors"])

    return cfg


def _validate(cfg: dict) -> None:
    """验证配置必要字段，不合法时抛出 ValueError。"""
    if "cities" not in cfg or not cfg["cities"]:
        raise ValueError("配置缺少 cities 字段")
    if "segments" not in cfg:
        raise ValueError("配置缺少 segments 字段")
    if "title" not in cfg:
        raise ValueError("配置缺少 title 字段")

    # 验证城市坐标
    for i, c in enumerate(cfg["cities"]):
        name = c.get("name", f"#{i}")
        if "lon" not in c or "lat" not in c:
            raise ValueError(f"城市 '{name}' 缺少 lon/lat 坐标")
        try:
            c["lon"] = float(c["lon"])
            c["lat"] = float(c["lat"])
        except (ValueError, TypeError):
            raise ValueError(f"城市 '{name}' 坐标无效: lon={c.get('lon')}, lat={c.get('lat')}")

    # 验证城市索引引用
    n = len(cfg["cities"])
    for i, seg in enumerate(cfg["segments"]):
        for key in ("from_index", "to_index"):
            idx = seg.get(key)
            if idx is None or idx < 0 or idx >= n:
                raise ValueError(f"segments[{i}].{key}={idx} 越界（城市数={n}）")

    # 验证 rest_days 中的城市名存在
    city_names = {c["name"] for c in cfg["cities"]}
    for day, name in cfg.get("rest_days", {}).items():
        if name not in city_names:
            raise ValueError(f"rest_days day {day}: 城市 '{name}' 不在 cities 列表中")


def get_city_index(cfg: dict, name: str) -> Optional[int]:
    """根据城市名查找索引。"""
    for c in cfg["cities"]:
        if c["name"] == name:
            return c["index"]
    return None


# ── 局部放大图 ──
INSET_THRESHOLD = 0.02       # 触发阈值：地图对角线的比例
INSET_PADDING = 2.0          # 放大区域外扩倍率
ZOOM_FACTOR = 5.5            # 放大倍数（相对于主图）
RENDER_MARGIN = 2.0          # 方图直径 / 圆直径
