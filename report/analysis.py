"""週報核心指標：週營收、成長率、品類排行、分店異常。

所有結果都整理成一個純 dict（可 JSON 序列化），同時給圖表、HTML 範本與 AI 摘要使用，
確保三者講的是同一組數字。
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

ANOMALY_THRESHOLD = -0.20  # 分店本週營收比前 4 週平均低 20% 以上 → 視為異常


@dataclass
class Analysis:
    facts: dict  # 給範本與 AI 的數字摘要
    weekly: pd.DataFrame  # 每週總營收
    store_weekly: pd.DataFrame  # 分店 × 週 營收
    category_compare: pd.DataFrame  # 品類 本週 vs 上週
    store_compare: pd.DataFrame  # 分店 本週 vs 前 4 週平均


def _pct(new: float, old: float) -> float | None:
    return None if not old else (new - old) / old


def analyze(df: pd.DataFrame, week_end: pd.Timestamp | None = None) -> Analysis:
    df = df.copy()
    df["week"] = df["date"].dt.to_period("W-SUN").dt.start_time  # 週一為一週起點

    # 只取完整的週，避免資料最後一天是週三時把半週當成一週
    last_day = df["date"].max()
    if week_end is None:
        week_end = last_day if last_day.weekday() == 6 else last_day - pd.Timedelta(days=last_day.weekday() + 1)
    this_week = (week_end - pd.Timedelta(days=6)).normalize()
    df = df[df["week"] <= this_week]
    prev_week = this_week - pd.Timedelta(weeks=1)
    base_weeks = [this_week - pd.Timedelta(weeks=k) for k in range(1, 5)]

    weekly = (
        df.groupby("week")
        .agg(revenue=("revenue", "sum"), orders=("orders", "sum"), gross_profit=("gross_profit", "sum"))
        .reset_index()
    )
    weekly["wow"] = weekly["revenue"].pct_change()

    cur = weekly.loc[weekly["week"] == this_week].iloc[0]
    prev = weekly.loc[weekly["week"] == prev_week].iloc[0]
    base_avg = weekly.loc[weekly["week"].isin(base_weeks), "revenue"].mean()

    # 品類：本週 vs 上週
    cat = df[df["week"].isin([this_week, prev_week])].pivot_table(
        index="category", columns="week", values="revenue", aggfunc="sum", fill_value=0
    )
    category_compare = pd.DataFrame(
        {"this_week": cat.get(this_week, 0), "last_week": cat.get(prev_week, 0)}
    ).sort_values("this_week", ascending=False)
    category_compare["wow"] = category_compare["this_week"] / category_compare["last_week"] - 1
    category_compare["share"] = category_compare["this_week"] / category_compare["this_week"].sum()

    # 分店：本週 vs 前 4 週平均（比單看上週更不容易被單週波動誤導）
    store_weekly = df.pivot_table(index="store", columns="week", values="revenue", aggfunc="sum", fill_value=0)
    store_compare = pd.DataFrame(
        {
            "this_week": store_weekly[this_week],
            "last_week": store_weekly[prev_week],
            "base_avg": store_weekly[[w for w in base_weeks if w in store_weekly.columns]].mean(axis=1),
        }
    )
    store_compare["vs_base"] = store_compare["this_week"] / store_compare["base_avg"] - 1
    store_compare["wow"] = store_compare["this_week"] / store_compare["last_week"] - 1
    store_compare["anomaly"] = store_compare["vs_base"] <= ANOMALY_THRESHOLD
    store_compare = store_compare.sort_values("vs_base")

    # 異常分店：拆解是哪個品類掉最多，給 AI 與主管更具體的線索
    anomalies = []
    for store, row in store_compare[store_compare["anomaly"]].iterrows():
        sub = df[(df["store"] == store) & df["week"].isin([this_week, *base_weeks])]
        by_cat = sub.pivot_table(index="category", columns="week", values="revenue", aggfunc="sum", fill_value=0)
        cat_drop = (by_cat[this_week] / by_cat[[w for w in base_weeks if w in by_cat.columns]].mean(axis=1) - 1).sort_values()
        anomalies.append(
            {
                "store": store,
                "this_week": int(row["this_week"]),
                "base_avg": int(row["base_avg"]),
                "vs_base": round(float(row["vs_base"]), 4),
                "lost_revenue": int(row["base_avg"] - row["this_week"]),
                "worst_categories": {k: round(float(v), 4) for k, v in cat_drop.head(3).items()},
            }
        )

    has_gp = df["gross_profit"].notna().any()
    top_cat = category_compare.index[0]
    fastest_cat = category_compare["wow"].idxmax()
    channel = df[df["week"] == this_week].groupby("channel")["revenue"].sum()

    facts = {
        "period": {
            "week_start": this_week.date().isoformat(),
            "week_end": (this_week + pd.Timedelta(days=6)).date().isoformat(),
            "weeks_in_data": int(weekly.shape[0]),
            "data_start": df["date"].min().date().isoformat(),
        },
        "kpi": {
            "revenue": int(cur["revenue"]),
            "revenue_wow": _pct(cur["revenue"], prev["revenue"]),
            "revenue_vs_4w": _pct(cur["revenue"], base_avg),
            "orders": int(cur["orders"]),
            "orders_wow": _pct(cur["orders"], prev["orders"]),
            "aov": round(cur["revenue"] / cur["orders"]) if cur["orders"] else None,
            "aov_wow": _pct(cur["revenue"] / cur["orders"], prev["revenue"] / prev["orders"]) if cur["orders"] and prev["orders"] else None,
            "gross_margin": float(cur["gross_profit"] / cur["revenue"]) if has_gp and cur["revenue"] else None,
            "gross_margin_prev": float(prev["gross_profit"] / prev["revenue"]) if has_gp and prev["revenue"] else None,
        },
        "trend_13w": [
            {"week": w.date().isoformat(), "revenue": int(r)} for w, r in zip(weekly["week"], weekly["revenue"])
        ],
        "categories": [
            {
                "category": c,
                "revenue": int(r["this_week"]),
                "wow": round(float(r["wow"]), 4),
                "share": round(float(r["share"]), 4),
            }
            for c, r in category_compare.iterrows()
        ],
        "top_category": top_cat,
        "fastest_growing_category": fastest_cat,
        "stores": [
            {
                "store": s,
                "revenue": int(r["this_week"]),
                "wow": round(float(r["wow"]), 4),
                "vs_4w_avg": round(float(r["vs_base"]), 4),
                "anomaly": bool(r["anomaly"]),
            }
            for s, r in store_compare.sort_values("this_week", ascending=False).iterrows()
        ],
        "anomalies": anomalies,
        "channel_share": {k: round(float(v / channel.sum()), 4) for k, v in channel.items()},
        "anomaly_rule": f"分店本週營收低於前 4 週平均 {abs(ANOMALY_THRESHOLD):.0%} 以上",
    }

    weekly_out = weekly[weekly["week"] <= this_week]
    return Analysis(facts, weekly_out, store_weekly, category_compare, store_compare)
