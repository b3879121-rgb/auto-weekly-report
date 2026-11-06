"""matplotlib 中文圖表（預設 Microsoft JhengHei，Linux / GitHub Actions 自動改用 Noto Sans CJK）。"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # 排程 / 無螢幕環境也能畫圖
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
from matplotlib import font_manager

from .analysis import Analysis

FONT_CANDIDATES = ["Microsoft JhengHei", "Noto Sans CJK TC", "Noto Sans TC", "PingFang TC", "Heiti TC"]

INK = "#1f2a37"
MUTED = "#6b7280"
GRID = "#e5e7eb"
PRIMARY = "#2563eb"
PRIMARY_LIGHT = "#bfdbfe"
GOOD = "#059669"
BAD = "#dc2626"


def setup_font() -> str:
    available = {f.name for f in font_manager.fontManager.ttflist}
    for name in FONT_CANDIDATES:
        if name in available:
            plt.rcParams["font.family"] = name
            break
    else:
        name = "sans-serif"
    plt.rcParams.update(
        {
            "axes.unicode_minus": False,
            "axes.axisbelow": True,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.edgecolor": GRID,
            "axes.labelcolor": MUTED,
            "xtick.color": MUTED,
            "ytick.color": MUTED,
            "axes.titleweight": "bold",
            "axes.titlesize": 13,
            "axes.titlecolor": INK,
            "axes.titlelocation": "left",
            "axes.titlepad": 12,
            "figure.dpi": 150,
        }
    )
    return name


def _wan(x, _pos=None) -> str:
    return f"{x / 10000:,.0f} 萬"


def _save(fig, path: Path) -> Path:
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def weekly_trend(a: Analysis, path: Path) -> Path:
    w = a.weekly
    fig, ax = plt.subplots(figsize=(7.2, 3.4))
    x = np.arange(len(w))
    ax.plot(x, w["revenue"], color=PRIMARY, lw=2.2, marker="o", ms=4, zorder=3)
    ax.fill_between(x, w["revenue"], w["revenue"].min() * 0.9, color=PRIMARY_LIGHT, alpha=0.35)
    ax.scatter([x[-1]], [w["revenue"].iloc[-1]], s=80, color=PRIMARY, zorder=4, edgecolor="white", lw=2)
    ax.annotate(
        f"本週 {w['revenue'].iloc[-1] / 10000:,.0f} 萬",
        (x[-1], w["revenue"].iloc[-1]),
        xytext=(-10, -22),
        textcoords="offset points",
        ha="right",
        color=INK,
        fontsize=10,
        fontweight="bold",
    )
    ax.set_xticks(x, [d.strftime("%m/%d") for d in w["week"]], fontsize=8)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(_wan))
    ax.set_ylim(w["revenue"].min() * 0.9, w["revenue"].max() * 1.1)
    ax.grid(axis="y", color=GRID, lw=0.8)
    ax.set_title("近 13 週營收趨勢（週一起算）")
    return _save(fig, path)


def category_compare(a: Analysis, path: Path) -> Path:
    c = a.category_compare
    fig, ax = plt.subplots(figsize=(7.2, 3.4))
    y = np.arange(len(c))[::-1]
    ax.barh(y + 0.2, c["last_week"], height=0.38, color="#d1d5db", label="上週")
    ax.barh(y - 0.2, c["this_week"], height=0.38, color=PRIMARY, label="本週")
    for yi, (val, wow) in zip(y, zip(c["this_week"], c["wow"])):
        ax.text(val, yi - 0.2, f"  {wow:+.1%}", va="center", fontsize=9, color=GOOD if wow >= 0 else BAD, fontweight="bold")
    ax.set_yticks(y, c.index)
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(_wan))
    ax.set_xlim(0, c[["this_week", "last_week"]].values.max() * 1.18)
    ax.grid(axis="x", color=GRID, lw=0.8)
    ax.legend(frameon=False, loc="lower right", fontsize=9)
    ax.set_title("品類營收：本週 vs 上週")
    return _save(fig, path)


def store_change(a: Analysis, path: Path) -> Path:
    s = a.store_compare.sort_values("vs_base")
    fig, ax = plt.subplots(figsize=(7.2, 3.4))
    colors = [BAD if v else (GOOD if d >= 0 else "#f59e0b") for v, d in zip(s["anomaly"], s["vs_base"])]
    y = np.arange(len(s))
    ax.barh(y, s["vs_base"], color=colors, height=0.6)
    for yi, v in zip(y, s["vs_base"]):
        ax.text(v, yi, f" {v:+.1%} " if v >= 0 else f" {v:+.1%} ", va="center", ha="left" if v >= 0 else "right", fontsize=9, color=INK)
    ax.axvline(0, color=MUTED, lw=0.8)
    ax.axvline(-0.20, color=BAD, lw=0.8, ls="--")
    ax.text(-0.20, len(s) - 0.4, "異常門檻 -20%", color=BAD, fontsize=8, ha="center")
    ax.set_yticks(y, s.index)
    lim = max(0.3, s["vs_base"].abs().max() * 1.35)
    ax.set_xlim(-lim, lim)
    ax.xaxis.set_major_formatter(mticker.PercentFormatter(1.0, decimals=0))
    ax.grid(axis="x", color=GRID, lw=0.8)
    ax.set_title("分店本週營收 vs 前 4 週平均")
    return _save(fig, path)


def store_heatmap(a: Analysis, path: Path) -> Path:
    sw = a.store_weekly.iloc[:, -8:]  # 近 8 週
    idx = sw.div(sw.mean(axis=1), axis=0) * 100  # 以各店自己 8 週平均 = 100 做指數，大小店可比較
    fig, ax = plt.subplots(figsize=(7.2, 3.4))
    im = ax.imshow(idx.values, cmap="RdYlGn", vmin=60, vmax=140, aspect="auto")
    ax.set_yticks(range(len(idx)), idx.index)
    ax.set_xticks(range(idx.shape[1]), [c.strftime("%m/%d") for c in idx.columns], fontsize=8)
    for i in range(idx.shape[0]):
        for j in range(idx.shape[1]):
            v = idx.values[i, j]
            ax.text(j, i, f"{v:.0f}", ha="center", va="center", fontsize=8, color="white" if v < 75 or v > 125 else INK)
    for sp in ax.spines.values():
        sp.set_visible(False)
    cb = fig.colorbar(im, ax=ax, fraction=0.03, pad=0.02)
    cb.ax.tick_params(labelsize=7)
    cb.outline.set_visible(False)
    ax.set_title("分店營收指數熱力圖（各店近 8 週平均 = 100）")
    return _save(fig, path)


def make_all(a: Analysis, out_dir: Path) -> dict[str, Path]:
    setup_font()
    out_dir.mkdir(parents=True, exist_ok=True)
    return {
        "trend": weekly_trend(a, out_dir / "chart_trend.png"),
        "category": category_compare(a, out_dir / "chart_category.png"),
        "store": store_change(a, out_dir / "chart_store.png"),
        "heatmap": store_heatmap(a, out_dir / "chart_heatmap.png"),
    }
