"""讀取銷售 CSV：本機檔案，或 Google Sheets「發佈到網路 → CSV」的網址。

為了讓不同團隊的試算表都能直接套用，欄位名稱支援中英文別名，
讀進來後統一成內部欄位：date, store, region, channel, category, orders, units, revenue, gross_profit。
"""

from __future__ import annotations

import io
import urllib.request
from pathlib import Path

import pandas as pd

COLUMN_ALIASES = {
    "date": ["日期", "date", "order_date", "訂單日期"],
    "store": ["分店", "門市", "store", "branch", "shop"],
    "region": ["區域", "region", "area"],
    "channel": ["通路", "channel"],
    "category": ["品類", "類別", "category", "product_category"],
    "orders": ["訂單數", "orders", "order_count"],
    "units": ["銷售數量", "數量", "units", "qty", "quantity"],
    "revenue": ["營收", "銷售額", "revenue", "sales", "amount"],
    "gross_profit": ["毛利", "gross_profit", "profit"],
}
REQUIRED = ["date", "store", "category", "revenue"]


def google_sheet_csv_url(url: str) -> str:
    """把一般的 Google Sheets 分享網址轉成 CSV 匯出網址（已是 CSV 網址則原樣回傳）。"""
    if "docs.google.com/spreadsheets" in url and "output=csv" not in url and "format=csv" not in url:
        # https://docs.google.com/spreadsheets/d/<ID>/edit#gid=0 → /export?format=csv&gid=0
        sheet_id = url.split("/d/")[1].split("/")[0]
        gid = url.split("gid=")[1].split("&")[0] if "gid=" in url else "0"
        return f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"
    return url


def _read_raw(source: str) -> pd.DataFrame:
    if source.startswith(("http://", "https://")):
        url = google_sheet_csv_url(source)
        req = urllib.request.Request(url, headers={"User-Agent": "auto-report/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            return pd.read_csv(io.BytesIO(resp.read()), encoding="utf-8-sig")
    return pd.read_csv(Path(source), encoding="utf-8-sig")


def normalize(df: pd.DataFrame) -> pd.DataFrame:
    lookup = {alias.strip().lower(): key for key, aliases in COLUMN_ALIASES.items() for alias in aliases}
    df = df.rename(columns={c: lookup[c.strip().lower()] for c in df.columns if c.strip().lower() in lookup})
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(f"CSV 缺少必要欄位：{missing}（可用欄位：{list(df.columns)}）")

    df["date"] = pd.to_datetime(df["date"])
    for col in ["orders", "units", "revenue", "gross_profit"]:
        if col in df.columns:
            # Google Sheets 匯出的金額常帶千分位逗號或 $ 符號
            df[col] = pd.to_numeric(df[col].astype(str).str.replace(r"[,$\s]", "", regex=True), errors="coerce").fillna(0)
    defaults = {"region": "未分區", "channel": "門市", "orders": 0, "units": 0, "gross_profit": float("nan")}
    for col, val in defaults.items():
        if col not in df.columns:
            df[col] = val
    return df


def load_sales(source: str) -> pd.DataFrame:
    return normalize(_read_raw(source))
