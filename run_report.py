"""AI 自動化營運週報：一鍵產出 HTML + PDF。

用法：
    python run_report.py                         # 用範例資料（不存在會自動產生）
    python run_report.py --input data/my.csv     # 用自己的 CSV
    python run_report.py --input "https://docs.google.com/spreadsheets/d/<ID>/edit#gid=0"
    python run_report.py --send                  # 產出後用 n8n webhook / Email 寄出
    python run_report.py --no-ai                 # 強制使用規則式摘要
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from report import ai_summary, analysis, charts, loader, notify, render  # noqa: E402
from report.data_gen import write_sample  # noqa: E402

SAMPLE = ROOT / "data" / "sample_sales.csv"


def load_dotenv(path: Path) -> None:
    """簡易 .env 載入（不覆蓋已存在的環境變數），省掉一個相依套件。"""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # Windows 工作排程器的主控台也能正常顯示中文
    load_dotenv(ROOT / ".env")

    ap = argparse.ArgumentParser(description="AI 自動化營運週報")
    ap.add_argument("--input", default=os.getenv("REPORT_INPUT") or str(SAMPLE), help="CSV 路徑或 Google Sheets 網址")
    ap.add_argument("--out", default=str(ROOT / "output"), help="輸出資料夾")
    ap.add_argument("--company", default=os.getenv("REPORT_COMPANY", "好日子生活百貨"), help="報告抬頭的公司名稱")
    ap.add_argument("--regen-sample", action="store_true", help="重新產生範例資料（以最近一個週日為結尾）")
    ap.add_argument("--no-ai", action="store_true", help="不呼叫 Claude，直接用規則式摘要")
    ap.add_argument("--send", action="store_true", help="產出後透過 n8n webhook / Email 寄出")
    args = ap.parse_args()

    t0 = time.perf_counter()
    out = Path(args.out)

    if args.input == str(SAMPLE) and (args.regen_sample or not SAMPLE.exists()):
        write_sample(SAMPLE)
        print(f"[1/5] 已產生範例資料 {SAMPLE.relative_to(ROOT)}")

    df = loader.load_sales(args.input)
    src_name = "範例資料（程式產生）" if args.input == str(SAMPLE) else Path(args.input).name if not args.input.startswith("http") else "Google Sheets"
    print(f"[1/5] 讀取資料：{len(df):,} 列，{df['date'].min():%Y-%m-%d} ~ {df['date'].max():%Y-%m-%d}")

    a = analysis.analyze(df)
    p = a.facts["period"]
    print(f"[2/5] 分析完成：本週 {p['week_start']} ~ {p['week_end']}，異常分店 {len(a.facts['anomalies'])} 間")

    chart_paths = charts.make_all(a, out / "charts")
    print(f"[3/5] 圖表 {len(chart_paths)} 張 → {(out / 'charts').relative_to(ROOT) if out.is_relative_to(ROOT) else out / 'charts'}")

    summary = ai_summary.summarize(a.facts, use_ai=not args.no_ai)
    print(f"[4/5] 摘要來源：{summary['source']}")

    stem = f"weekly_report_{p['week_start']}"
    html_path = render.render_html(a.facts, summary, chart_paths, out / f"{stem}.html", args.company, src_name)
    pdf_path, engine = render.render_pdf(html_path, out / f"{stem}.pdf")
    (out / f"{stem}.json").write_text(json.dumps({"facts": a.facts, "summary": summary}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[5/5] HTML → {html_path}")
    print(f"      PDF  → {pdf_path if pdf_path else '未產生'}（{engine}）")

    if args.send:
        for msg in notify.deliver(a.facts, summary, pdf_path, html_path, args.company):
            print(f"      寄送：{msg}")

    print(f"完成，耗時 {time.perf_counter() - t0:.1f} 秒")
    return 0 if pdf_path else 1


if __name__ == "__main__":
    raise SystemExit(main())
