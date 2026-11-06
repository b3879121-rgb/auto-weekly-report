"""產生擬真的門市 / 電商銷售資料（3 個月、多分店、多品類）。

資料是「每日 × 分店 × 品類」的彙總列，欄位與 Google Sheets 常見的營運日報相同，
讓沒有真實資料的人也能直接跑完整條流程。

刻意埋入幾個真實營運會遇到的情境，讓分析與 AI 摘要有東西可以講：
- 週末客流較高、整體營收緩步成長
- 中秋節前（9 月中下旬）食品禮盒熱賣
- 美妝保養在線上通路持續成長
- 最新一週「台中逢甲店」營收驟降（模擬周邊道路施工）
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

STORES = {
    # 分店: (區域, 通路, 規模係數)
    "台北信義店": ("北區", "門市", 1.35),
    "台北南西店": ("北區", "門市", 1.10),
    "新北板橋店": ("北區", "門市", 1.00),
    "桃園中壢店": ("北區", "門市", 0.80),
    "台中逢甲店": ("中區", "門市", 0.95),
    "高雄夢時代店": ("南區", "門市", 0.90),
    "官方網路商店": ("全區", "電商", 1.25),
}

CATEGORIES = {
    # 品類: (平均客單價, 每日基礎訂單數, 毛利率)
    "3C配件": (890, 26, 0.32),
    "居家生活": (640, 30, 0.41),
    "美妝保養": (1180, 22, 0.52),
    "食品飲料": (420, 45, 0.28),
    "服飾配件": (980, 20, 0.47),
}

# 星期一 ~ 星期日的客流係數
WEEKDAY_FACTOR = [0.85, 0.82, 0.88, 0.92, 1.08, 1.30, 1.22]


def generate_sales(
    end: date | None = None,
    weeks: int = 13,
    seed: int = 42,
    anomaly_store: str = "台中逢甲店",
    anomaly_drop: float = 0.38,
) -> pd.DataFrame:
    """產生 `weeks` 週的每日銷售資料，最後一天是 `end`（預設為最近一個星期日）。"""
    rng = np.random.default_rng(seed)
    if end is None:
        today = date.today()
        end = today - timedelta(days=today.weekday() + 1)  # 最近一個已結束的星期日
    start = end - timedelta(days=weeks * 7 - 1)
    days = pd.date_range(start, end, freq="D")
    last_week_start = pd.Timestamp(end - timedelta(days=6))

    # 中秋節前兩週為食品禮盒旺季（以資料期間中的 9/10~9/24 近似）
    festival = (pd.Timestamp(year=start.year, month=9, day=10), pd.Timestamp(year=start.year, month=9, day=24))

    rows = []
    for i, d in enumerate(days):
        trend = 1 + 0.0025 * i  # 約每週 +1.75% 的自然成長
        wd = WEEKDAY_FACTOR[d.weekday()]
        for store, (region, channel, scale) in STORES.items():
            for cat, (aov, base_orders, margin) in CATEGORIES.items():
                f = trend * scale
                f *= 1.0 if channel == "電商" else wd  # 電商較不受星期影響
                if cat == "食品飲料" and festival[0] <= d <= festival[1]:
                    f *= 1.9
                if cat == "美妝保養" and channel == "電商":
                    f *= 1 + 0.012 * i  # 線上美妝持續成長
                if cat == "3C配件" and channel == "電商":
                    f *= 1.25
                if store == anomaly_store and d >= last_week_start:
                    f *= 1 - anomaly_drop
                orders = max(0, int(rng.poisson(base_orders * f)))
                ticket = aov * rng.normal(1.0, 0.06)
                revenue = round(orders * ticket)
                units = int(round(orders * rng.uniform(1.2, 1.8)))
                gross = round(revenue * (margin + rng.normal(0, 0.015)))
                rows.append(
                    {
                        "日期": d.date().isoformat(),
                        "分店": store,
                        "區域": region,
                        "通路": channel,
                        "品類": cat,
                        "訂單數": orders,
                        "銷售數量": units,
                        "營收": revenue,
                        "毛利": gross,
                    }
                )
    return pd.DataFrame(rows)


def write_sample(path: Path, **kwargs) -> Path:
    df = generate_sales(**kwargs)
    path.parent.mkdir(parents=True, exist_ok=True)
    # utf-8-sig：用 Excel 直接開也不會亂碼
    df.to_csv(path, index=False, encoding="utf-8-sig")
    return path


if __name__ == "__main__":
    out = write_sample(Path(__file__).resolve().parent.parent / "data" / "sample_sales.csv")
    print(f"已產生範例資料：{out}")
