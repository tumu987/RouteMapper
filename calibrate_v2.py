#!/usr/bin/env python3
"""精确文字校准 — 在实际输出DPI(120)下测量，输出可直接用的参数。"""
import os, warnings, math, json
warnings.filterwarnings('ignore')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties

DPI = 120  # 实际输出DPI
FONT = None
for fp in [
    '/System/Library/Fonts/STHeiti Medium.ttc',
    '/System/Library/Fonts/PingFang.ttc',
]:
    if os.path.exists(fp):
        FONT = fp
        break

print(f"字体: {FONT}, DPI: {DPI}")

# 测试文本
texts = {
    "cn_2": "喀什",
    "cn_3": "观音堂",
    "cn_4": "巴音布鲁克",
    "cn_5": "艾提尕尔",
    "mix_dist": "294km",
    "mix_time": "4小时",
    "mix_time2": "2.5小时",
    "en": "D1",
    "en2": "D12",
    "num": "580km",
}

sizes = [12, 14, 16, 18, 20, 22, 24, 28, 30]

fig, ax = plt.subplots(figsize=(30, 2), dpi=DPI)
ax.set_xlim(0, 30)
ax.set_ylim(-1, 1)
ax.axis('off')

results = {}
x = 0.3

for sz in sizes:
    fp = FontProperties(fname=FONT, size=sz, weight='bold')
    for label, text in texts.items():
        t = ax.text(x, 0, text, fontproperties=fp, va='center')
        fig.canvas.draw()
        bbox = t.get_window_extent()
        w_px = bbox.width
        h_px = bbox.height
        t.remove()
        results[(sz, label)] = {"text": text, "w": w_px, "h": h_px}
        x += 2.8
        if x > 28:
            x = 0.3
            # 需要新一行，这里简化处理
            break

plt.close(fig)

# 分析：分离中英文
print("\n=== 中文宽度 (px/字) ===")
for sz in sizes:
    cn_widths = []
    for label in ["cn_2", "cn_3", "cn_4", "cn_5"]:
        if (sz, label) in results:
            r = results[(sz, label)]
            n = len(r["text"])
            cn_widths.append(r["w"] / n)
    if cn_widths:
        print(f"  {sz}pt: {sum(cn_widths)/len(cn_widths):.1f}px/字 (理论pt*{DPI}/72={sz*DPI/72:.1f})")

print("\n=== EN宽度 (px/字) ===")
for sz in sizes:
    en_widths = []
    for label in ["en", "en2"]:
        if (sz, label) in results:
            r = results[(sz, label)]
            n = len(r["text"])
            en_widths.append(r["w"] / n)
    for label in ["num"]:
        if (sz, label) in results:
            r = results[(sz, label)]
            n = len(r["text"])
            en_widths.append(r["w"] / n)
    if en_widths:
        print(f"  {sz}pt: {sum(en_widths)/len(en_widths):.1f}px/字")

print("\n=== 高度 (px) ===")
for sz in sizes:
    heights = []
    for key in results:
        if key[0] == sz:
            heights.append(results[key]["h"])
    if heights:
        print(f"  {sz}pt: {sum(heights)/len(heights):.1f}px (理论pt*{DPI}/72={sz*DPI/72:.1f})")

#输出推荐系数
print("\n=== 推荐 text_half_size 实现 ===")
print("直接使用 DPI 换算，不需要经验系数：")
print("""
def text_half_size(self, text, pt):
    # 实际像素 = pt × DPI / 72
    px_per_pt = self.render_dpi / 72.0
    h_px = pt * px_per_pt
    # 宽度：中文字宽≈高，英文/数字字宽≈0.6×高
    cn = sum(1 for c in text if ord(c) > 127)
    en = len(text) - cn
    w_px = cn * pt * px_per_pt + en * pt * px_per_pt * 0.6
    hw = w_px / self.ppd / 2
    hh = h_px / self.ppd / 2
    return hw, hh
""")
