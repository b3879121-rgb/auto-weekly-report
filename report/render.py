"""輸出：單檔 HTML（圖表內嵌）＋ PDF。

PDF 依序嘗試：
1. Edge / Chrome / Chromium 的 headless 列印（Windows 內建 Edge，免安裝任何東西）
2. weasyprint（若有安裝）
"""

from __future__ import annotations

import base64
import os
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"

BROWSER_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
]
BROWSER_NAMES = ["msedge", "microsoft-edge", "google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome"]


def _data_uri(path: Path) -> str:
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode()


def _delta(v: float | None, suffix: str = "較上週") -> tuple[str, str]:
    if v is None:
        return "—", "flat"
    arrow = "▲" if v > 0 else ("▼" if v < 0 else "■")
    return f"{arrow} {v:+.1%} {suffix}", "up" if v > 0 else ("down" if v < 0 else "flat")


def kpi_cards(k: dict) -> list[dict]:
    cards = []
    d, c = _delta(k["revenue_wow"])
    cards.append({"label": "本週營收", "value": f"{k['revenue'] / 10000:,.1f} 萬", "delta": d, "cls": c})
    d, c = _delta(k["orders_wow"])
    cards.append({"label": "訂單數", "value": f"{k['orders']:,}", "delta": d, "cls": c})
    d, c = _delta(k["aov_wow"])
    cards.append({"label": "平均客單價", "value": f"{k['aov']:,} 元" if k["aov"] else "—", "delta": d, "cls": c})
    if k["gross_margin"] is not None:
        diff = k["gross_margin"] - (k["gross_margin_prev"] or k["gross_margin"])
        cls = "up" if diff > 0 else ("down" if diff < 0 else "flat")
        cards.append({"label": "毛利率", "value": f"{k['gross_margin']:.1%}", "delta": f"{diff * 100:+.1f} 個百分點 較上週", "cls": cls})
    else:
        d, c = _delta(k["revenue_vs_4w"], "較前 4 週平均")
        cards.append({"label": "營收 vs 4 週平均", "value": f"{k['revenue_vs_4w']:+.1%}", "delta": d, "cls": c})
    return cards


def render_html(facts: dict, summary: dict, charts: dict[str, Path], out_path: Path, company: str, source_name: str) -> Path:
    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR), autoescape=select_autoescape(["html", "j2"]))
    html = env.get_template("report.html.j2").render(
        company=company,
        p=facts["period"],
        facts=facts,
        summary=summary,
        kpi_cards=kpi_cards(facts["kpi"]),
        charts={k: _data_uri(v) for k, v in charts.items()},
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
        source_name=source_name,
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    return out_path


def find_browser() -> str | None:
    env_path = os.getenv("BROWSER_PATH")
    if env_path and Path(env_path).exists():
        return env_path
    for p in BROWSER_CANDIDATES:
        if Path(p).exists():
            return p
    for name in BROWSER_NAMES:
        found = shutil.which(name)
        if found:
            return found
    return None


def _pdf_with_browser(browser: str, html_path: Path, pdf_path: Path) -> bool:
    # 獨立的 user-data-dir：就算使用者正在開 Edge，headless 也不會被既有視窗攔截
    with tempfile.TemporaryDirectory() as profile:
        cmd = [
            browser,
            "--headless=new",
            "--disable-gpu",
            "--no-sandbox",
            "--no-first-run",
            "--disable-extensions",
            f"--user-data-dir={profile}",
            "--no-pdf-header-footer",
            "--run-all-compositor-stages-before-draw",
            "--virtual-time-budget=5000",
            f"--print-to-pdf={pdf_path.resolve()}",
            html_path.resolve().as_uri(),
        ]
        subprocess.run(cmd, capture_output=True, timeout=120)
    return pdf_path.exists() and pdf_path.stat().st_size > 0


def render_pdf(html_path: Path, pdf_path: Path) -> tuple[Path | None, str]:
    """回傳 (PDF 路徑或 None, 使用的引擎)。"""
    if pdf_path.exists():
        pdf_path.unlink()
    browser = find_browser()
    if browser and _pdf_with_browser(browser, html_path, pdf_path):
        return pdf_path, Path(browser).stem
    try:
        from weasyprint import HTML  # type: ignore

        HTML(filename=str(html_path)).write_pdf(str(pdf_path))
        return pdf_path, "weasyprint"
    except Exception:
        if browser:
            return None, f"{Path(browser).stem} 列印失敗（若在沙箱或遠端環境執行，請改在一般終端機執行），且未安裝 weasyprint"
        return None, "找不到 Edge / Chrome，也未安裝 weasyprint"
