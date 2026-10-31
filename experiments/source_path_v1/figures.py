"""Draw the three method-two views (A forest, B one call, C cross-step path) from real records.

Outputs SVG (editable) + PNG preview. English/Chinese labels use Microsoft YaHei when available.
"""

from __future__ import annotations

import json
import pathlib
from collections import Counter

import matplotlib

matplotlib.use("Agg")
import matplotlib.patches as patches
import matplotlib.pyplot as plt

REPO = pathlib.Path(r"F:\CodexProject\MemoryFlow-research")
OUT = REPO / "experiments/source_path_v1/out"
FOREST = json.loads((OUT / "forest_v6_fixed.json").read_text(encoding="utf-8"))
CUAD = json.loads((OUT / "path_cuad.json").read_text(encoding="utf-8"))

CALLS_BY_AGENT = Counter(call["agent"] for call in FOREST["calls"].values())
ROOTS_BY_AGENT = {agent: len(calls) for agent, calls in FOREST["roots"].items()}
REPORT_SCORES = sorted(
    [edge for edge in CUAD["edges"]
     if edge["to"] == "report_span_0" and edge["kind"] == "estimate"],
    key=lambda edge: -edge["score"],
)

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

fig, axes = plt.subplots(1, 3, figsize=(18, 8.6), gridspec_kw={"width_ratios": [1.15, 1.0, 1.15]})
for ax in axes:
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10)
    ax.axis("off")

COLORS = {"recorded": "#1f4e79", "estimate": "#b05a00", "gap": "#a00000", "box": "#eef3fa"}


def box(ax, x, y, w, h, text, color=COLORS["box"], edge=COLORS["recorded"], fontsize=9):
    ax.add_patch(patches.FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.08,rounding_size=0.15",
                                        linewidth=1.4, edgecolor=edge, facecolor=color))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fontsize, wrap=True)


def arrow(ax, x1, y1, x2, y2, color=COLORS["recorded"], style="-", text=None, fontsize=8):
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                arrowprops={"arrowstyle": "->", "color": color, "lw": 1.6, "linestyle": style})
    if text:
        ax.text((x1 + x2) / 2, (y1 + y2) / 2 + 0.25, text, ha="center", fontsize=fontsize, color=color)


# ---------------- View A ----------------
ax = axes[0]
ax.set_title("A  为什么是森林：主/子 Agent 各有上下文", fontsize=13, pad=10)
box(ax, 0.4, 6.9, 4.2, 2.2,
    f"Central 会话\n{CALLS_BY_AGENT['central']} calls / {ROOTS_BY_AGENT.get('central', 0)} roots\n"
    f"实际恢复：{sum(ROOTS_BY_AGENT.values())} roots，{len(FOREST['branches'])} 分支", fontsize=8.5)
box(ax, 5.4, 6.9, 4.2, 2.2,
    "结构示意（非真实分支）\n恢复/改写会切断前缀\n同一历史可能有不同后续",
    color="#fff6e6", edge=COLORS["estimate"], fontsize=8.5)
for index, name in enumerate(("memory_recaller", "perception", "coder")):
    box(ax, 1.0 + index * 3.0, 3.6, 2.5, 1.5,
        f"{name}\n{CALLS_BY_AGENT[name]} calls / {ROOTS_BY_AGENT.get(name, 0)} roots",
        fontsize=8.5, edge="#555555")
ax.text(5, 2.5,
        "delegate → 子 Agent 的 session/委派标识未落盘\n只能按同角色请求前缀恢复树，跨会话映射 unresolved",
        ha="center", fontsize=8.5, color=COLORS["gap"])
ax.text(5, 1.2, "实线=记录确认；橙色=回放估计；红色=缺口", ha="center", fontsize=8.5, color="#444444")

# ---------------- View B ----------------
ax = axes[1]
ax.set_title("B  每次调用上挂什么：call7 与有效 CUAD 局部矩阵", fontsize=13, pad=10)
box(ax, 0.3, 7.2, 4.5, 1.8, "输入：call7 请求\nsummary_final + 原文片段 2593:3850", fontsize=8.5)
box(ax, 5.2, 7.2, 4.4, 1.8, "输出：report_span_0\n2.1 条款片段", fontsize=8.5, edge=COLORS["estimate"])
arrow(ax, 4.8, 8.1, 5.2, 8.1)
box(ax, 0.3, 4.6, 9.3, 1.8,
    f"局部矩阵：{len(REPORT_SCORES)} 个可见候选；分数为固定头回放质量\n"
    "不是把 0.6437 当成概率", fontsize=8.5)
arrow(ax, 2.5, 7.2, 2.5, 6.4)
ax.text(0.6, 3.9, "候选分数（归一化质量）：", fontsize=8.5)
for index, edge in enumerate(REPORT_SCORES):
    label = "摘要" if edge["from"] == "summary_final" else "原文片段"
    value = float(edge["score"])
    ax.add_patch(patches.Rectangle((0.6, 2.7 - index * 0.7), 8.0 * value, 0.45,
                                   color="#d9822b" if index == 0 else "#8aa7c8"))
    ax.text(0.6 + 8.0 * value + 0.15, 2.92 - index * 0.7, f"{label}: {value:.4f}", fontsize=8)
ax.text(0.6, 1.1, "有效的小矩阵可直接核对；v6 的 58×55 回放退化为 seg000，\n另记 gap，不混入这张有效图", fontsize=8.5,
        color=COLORS["gap"])

# ---------------- View C ----------------
ax = axes[2]
ax.set_title("C  跨步追查：CUAD 两跳（真实记录）", fontsize=13, pad=10)
box(ax, 0.2, 7.0, 3.0, 1.7, "合同原文\n2593:3850", fontsize=8.5)
box(ax, 3.6, 7.0, 2.8, 1.7, "call4\n研究者调用", fontsize=8.5)
box(ax, 6.8, 7.0, 2.9, 1.7, "summary_final\n整段摘要", fontsize=8.5)
box(ax, 3.6, 4.0, 2.8, 1.7, "call7\n报告者调用", fontsize=8.5)
box(ax, 6.8, 4.0, 2.9, 1.7, "report_span_0\n2.1 条款", fontsize=8.5)
arrow(ax, 3.2, 7.85, 3.6, 7.85, text="可见", fontsize=7.5)
arrow(ax, 6.4, 7.85, 6.8, 7.85, text="生成", fontsize=7.5)
arrow(ax, 8.2, 7.0, 8.2, 5.7, text="0.6437", color=COLORS["estimate"], style="--")
arrow(ax, 1.7, 7.0, 1.7, 5.6, color=COLORS["estimate"], style="--")
ax.text(1.75, 6.2, "0.3563（直达）", fontsize=7.5, color=COLORS["estimate"], rotation=90)
arrow(ax, 1.7, 5.6, 3.6, 4.85, color=COLORS["estimate"], style="--")
arrow(ax, 8.2, 7.0, 6.4, 5.7, text="可见", fontsize=7.5)
ax.text(5, 2.2,
        "最后调用实际可见摘要和原文；0.7569 是原文→摘要的整段回放分数\n"
        "句级分数未回放，标 gap；0.6437/0.3563 是摘要/原文→报告的估计",
        ha="center", fontsize=8.5)
ax.text(5, 0.8, "实线=记录确认；橙色虚线=回放估计；红色=缺口", ha="center", fontsize=8.5, color="#444444")

fig.suptitle("MemoryFlow 方法二：森林上的来源关系（真实 v6/CUAD 记录 + 一处标记的示意）", fontsize=15, y=0.98)
fig.tight_layout(rect=(0, 0, 1, 0.96))
OUT.mkdir(parents=True, exist_ok=True)
fig.savefig(OUT / "method2_views.png", dpi=170)
fig.savefig(OUT / "method2_views.svg")
print(json.dumps({"png": str(OUT / "method2_views.png"), "svg": str(OUT / "method2_views.svg")}))
