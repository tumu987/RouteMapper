#!/usr/bin/env python3
"""文字尺寸校准脚本。用实际字体渲染后量像素，反推公式系数。"""
import os, warnings
warnings.filterwarnings('ignore')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties

# 找字体
FONT = None
for fp in [
    '/System/Library/Fonts/STHeiti Medium.ttc',
    '/System/Library/Fonts/STHeiti Light.ttc',
    '/System/Library/Fonts/PingFang.ttc',
]:
    if os.path.exists(fp):
        FONT = fp
        break
if not FONT:
    FONT = '/System/Library/Fonts/Helvetica.ttc'

print(f"字体: {FONT}")

# 测试字号和样本文本
sizes = [14, 16, 18, 20, 22, 30, 36]
samples = [
    "D1", "D12", "294km", "2.5小时", "160km", "7小时",
    "喀什", "巴音布鲁克", "艾提尕尔清真寺", "叶尔羌汗王宫",
    "克孜尔千佛洞", "观音堂", "法兴寺", "测试",
]

fig, ax = plt.subplots(figsize=(20, 3))
ax.set_xlim(0, 20)
ax.set_ylim(-1, 1)
ax.axis('off')

x = 0.5
results = {}

for sz in sizes:
    fp = FontProperties(fname=FONT, size=sz, weight='bold')
    results[sz] = {}
    for text in samples:
        t = ax.text(x, 0, text, fontproperties=fp, va='center')
        fig.canvas.draw()
        bbox = t.get_window_extent(renderer=fig.canvas.get_renderer())
        w_px = bbox.width
        h_px = bbox.height
        t.remove()
        results[sz][text] = (w_px, h_px)
        x += 1.5
        if x > 18:
            x = 0.5

plt.close(fig)

# 分析：反推公式 hw = len(text) * pt * a + b, hh = pt * c + d
print("\n=== 宽度分析 (hw = len*pt*a + b) ===")
for sz in sizes:
    for text, (w, h) in sorted(results[sz].items(), key=lambda x: -len(x[0])):
        ratio = w / (len(text) * sz) if len(text) * sz > 0 else 0
        print(f"  {sz}pt \"{text}\" ({len(text)}字): {w:.0f}×{h:.0f}px, 宽比率={ratio:.5f}")

print("\n=== 高度分析 (hh = pt*c + d) ===")
for sz in sizes:
    heights = [h for _, (_, h) in results[sz].items()]
    avg_h = sum(heights) / len(heights)
    ratio = avg_h / sz
    print(f"  {sz}pt: 平均高={avg_h:.1f}px, 比率={ratio:.4f}")

# 汇总推荐系数
# 取所有字号的平均比率，但重点看 16-22pt（实际使用范围）
all_w_ratios = []
all_h_ratios = []
for sz in [16, 18, 20, 22]:
    for text, (w, h) in results[sz].items():
        all_w_ratios.append(w / (len(text) * sz))
        all_h_ratios.append(h / sz)

avg_wr = sum(all_w_ratios) / len(all_w_ratios)
avg_hr = sum(all_h_ratios) / len(all_h_ratios)

# 地图坐标系数（基于 200px/° 校准）
dpi = 120  # 渲染 DPI?
px_per_deg = 200  # matplotlib 默认 100dpi 约等于此，但需确认
coeff_w = avg_wr / px_per_deg  # hw = len * pt * coeff_w + offset
coeff_h = avg_hr / px_per_deg   # hh = pt * coeff_h + offset

print(f"\n=== 推荐系数（基于200px/°）===")
print(f"宽度: hw = len(text) * pt * {coeff_w:.6f} + offset")
print(f"高度: hh = pt * {coeff_h:.6f} + offset")
print(f"\n当前代码系数: hw = len * pt * 0.0031 + 0.005, hh = pt * 0.0036 + 0.005")
print(f"新建议系数:   hw = len * pt * {coeff_w:.6f} + 0.005, hh = pt * {coeff_h:.6f} + 0.005")
