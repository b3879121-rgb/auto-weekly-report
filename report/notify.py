"""寄送週報：n8n Webhook 或 Email（SMTP）。兩者都是選用，沒設定就略過。

n8n：建立一個 Webhook 節點（POST），後面可接 Gmail / Slack / LINE / Teams 節點，
     收到的 JSON 已包含標題、重點、行動與 PDF（base64），直接拿來組訊息即可。
Email：用一般 SMTP（Gmail 請用「應用程式密碼」），PDF 會作為附件。
"""

from __future__ import annotations

import base64
import json
import mimetypes
import os
import smtplib
import urllib.request
from email.message import EmailMessage
from pathlib import Path


def _subject(facts: dict, company: str) -> str:
    p = facts["period"]
    return f"【{company}營運週報】{p['week_start']} ~ {p['week_end']}"


def _plain_text(facts: dict, summary: dict) -> str:
    lines = [summary["headline"], "", "本週重點："]
    lines += [f"{i}. {h}" for i, h in enumerate(summary["highlights"], 1)]
    lines += ["", "建議行動："]
    lines += [f"- [{a['priority']}] {a['action']}（{a['owner']}）" for a in summary["actions"]]
    lines += ["", f"摘要來源：{summary['source']}", "完整圖表請見附件 PDF。"]
    return "\n".join(lines)


def send_webhook(url: str, facts: dict, summary: dict, pdf: Path | None, company: str) -> int:
    body = {
        "subject": _subject(facts, company),
        "text": _plain_text(facts, summary),
        "period": facts["period"],
        "kpi": facts["kpi"],
        "summary": summary,
        "anomalies": facts["anomalies"],
    }
    if pdf and pdf.exists():
        body["pdf_filename"] = pdf.name
        body["pdf_base64"] = base64.b64encode(pdf.read_bytes()).decode()
    req = urllib.request.Request(
        url,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8", "User-Agent": "auto-report/1.0"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.status


def send_email(facts: dict, summary: dict, pdf: Path | None, html: Path | None, company: str) -> str:
    host = os.environ["SMTP_HOST"]
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.environ["SMTP_USER"]
    password = os.environ["SMTP_PASSWORD"]
    to = [x.strip() for x in os.environ["REPORT_TO"].split(",") if x.strip()]

    msg = EmailMessage()
    msg["Subject"] = _subject(facts, company)
    msg["From"] = os.getenv("SMTP_FROM", user)
    msg["To"] = ", ".join(to)
    msg.set_content(_plain_text(facts, summary))
    if html and html.exists():
        msg.add_alternative(html.read_text(encoding="utf-8"), subtype="html")
    if pdf and pdf.exists():
        ctype = mimetypes.guess_type(pdf.name)[0] or "application/pdf"
        maintype, subtype = ctype.split("/")
        msg.add_attachment(pdf.read_bytes(), maintype=maintype, subtype=subtype, filename=pdf.name)

    with smtplib.SMTP(host, port, timeout=30) as s:
        s.starttls()
        s.login(user, password)
        s.send_message(msg)
    return ", ".join(to)


def deliver(facts: dict, summary: dict, pdf: Path | None, html: Path | None, company: str) -> list[str]:
    """依環境變數決定要寄哪些管道，回傳結果訊息。"""
    results = []
    url = os.getenv("N8N_WEBHOOK_URL")
    if url:
        try:
            status = send_webhook(url, facts, summary, pdf, company)
            results.append(f"n8n Webhook 已送出（HTTP {status}）")
        except Exception as e:
            results.append(f"n8n Webhook 失敗：{e}")
    if os.getenv("SMTP_HOST") and os.getenv("REPORT_TO"):
        try:
            results.append(f"Email 已寄給 {send_email(facts, summary, pdf, html, company)}")
        except Exception as e:
            results.append(f"Email 失敗：{e}")
    if not results:
        results.append("未設定 N8N_WEBHOOK_URL 或 SMTP_*，略過寄送（請參考 .env.example）")
    return results
