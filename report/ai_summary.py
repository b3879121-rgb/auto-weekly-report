"""主管摘要：5 點重點 + 建議行動。

- 有 ANTHROPIC_API_KEY：呼叫 Claude（claude-sonnet-5-5），用結構化輸出拿到固定格式的 JSON。
- 沒有 key、或 API 失敗：改用規則式摘要，流程一樣跑得完，報告上會標示摘要來源。

AI 只拿到 analysis.py 算好的數字（不是原始資料），一來省 token，二來避免模型自己算錯數字。
"""

from __future__ import annotations

import json
import os

MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5")

SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {
        "headline": {"type": "string", "description": "一句話總結本週表現，30 字內"},
        "highlights": {
            "type": "array",
            "items": {"type": "string"},
            "description": "5 點主管重點，每點 60 字內，要有具體數字",
        },
        "actions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "action": {"type": "string"},
                    "owner": {"type": "string", "description": "建議負責單位，例如 營運部、行銷部、電商組"},
                    "priority": {"type": "string", "enum": ["高", "中", "低"]},
                },
                "required": ["action", "owner", "priority"],
                "additionalProperties": False,
            },
            "description": "3 項建議行動",
        },
    },
    "required": ["headline", "highlights", "actions"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """你是零售連鎖企業的營運分析師，負責替總經理撰寫每週營運週報的摘要。
讀者是忙碌的主管，只會花 30 秒看這段文字，所以：
- 使用繁體中文（台灣用語），金額用「萬」為單位、百分比保留一位小數。
- 只能使用提供的數據，不要編造數字；資料無法說明的原因，用「可能」並建議如何查證。
- 重點依重要性排序：先講整體營收、再講異常與風險、最後講機會。
- 建議行動要具體、可在一週內執行，並指定負責單位。"""


def _fmt_pct(v: float | None) -> str:
    return "—" if v is None else f"{v:+.1%}"


def _wan(v: float) -> str:
    return f"{v / 10000:,.1f} 萬"


def rule_based_summary(facts: dict) -> dict:
    """沒有 API key 時的備援：用固定規則產出同樣格式的摘要。"""
    k = facts["kpi"]
    cats = facts["categories"]
    top = cats[0]
    fastest = max(cats, key=lambda c: c["wow"])
    weakest = min(cats, key=lambda c: c["wow"])
    stores = facts["stores"]
    best_store = max(stores, key=lambda s: s["vs_4w_avg"])
    trend = "成長" if (k["revenue_wow"] or 0) >= 0 else "下滑"

    highlights = [
        f"本週營收 {_wan(k['revenue'])}，較上週{trend} {abs(k['revenue_wow'] or 0):.1%}，"
        f"較前 4 週平均 {_fmt_pct(k['revenue_vs_4w'])}。",
        f"訂單 {k['orders']:,} 筆（{_fmt_pct(k['orders_wow'])}），客單價 {k['aov']:,} 元（{_fmt_pct(k['aov_wow'])}）"
        + (f"，毛利率 {k['gross_margin']:.1%}。" if k["gross_margin"] is not None else "。"),
        f"營收最高品類為「{top['category']}」（{_wan(top['revenue'])}，占 {top['share']:.1%}）；"
        f"成長最快為「{fastest['category']}」（{_fmt_pct(fastest['wow'])}）。",
    ]
    actions = []
    if facts["anomalies"]:
        a = facts["anomalies"][0]
        worst = "、".join(f"{c}（{v:+.0%}）" for c, v in list(a["worst_categories"].items())[:2])
        highlights.append(
            f"⚠ {a['store']} 本週營收較前 4 週平均 {a['vs_base']:+.1%}，少了約 {_wan(a['lost_revenue'])}，"
            f"跌幅最大品類為 {worst}。"
        )
        actions.append(
            {
                "action": f"本週內與 {a['store']} 店長確認原因（周邊施工、人力、缺貨或競品促銷），並回報改善計畫",
                "owner": "營運部",
                "priority": "高",
            }
        )
    else:
        highlights.append("本週各分店營收皆在前 4 週平均的正常範圍內，無異常分店。")
    highlights.append(
        f"表現最佳分店為 {best_store['store']}（較前 4 週平均 {_fmt_pct(best_store['vs_4w_avg'])}）；"
        f"「{weakest['category']}」週減 {abs(weakest['wow']):.1%}，需留意。"
    )
    actions.append(
        {
            "action": f"檢視「{weakest['category']}」的庫存與促銷檔期，評估下週是否加碼曝光或組合優惠",
            "owner": "行銷部",
            "priority": "中",
        }
    )
    actions.append(
        {
            "action": f"複製 {best_store['store']} 的做法（陳列、活動、排班）到表現持平的分店試行兩週",
            "owner": "營運部",
            "priority": "中",
        }
    )
    headline = (
        f"本週營收 {_wan(k['revenue'])}（{_fmt_pct(k['revenue_wow'])}）"
        + (f"，{facts['anomalies'][0]['store']} 需立即關注" if facts["anomalies"] else "，各店表現穩定")
    )
    return {"headline": headline, "highlights": highlights[:5], "actions": actions[:3], "source": "規則式摘要（未設定 API key）"}


def claude_summary(facts: dict) -> dict:
    import anthropic

    client = anthropic.Anthropic()
    payload = {k: v for k, v in facts.items() if k != "trend_13w"}
    payload["trend_13w_revenue"] = [t["revenue"] for t in facts["trend_13w"]]
    user_msg = (
        "以下是本週營運數據（JSON）。請寫出：一句話總結、5 點主管重點、3 項建議行動。\n\n"
        + json.dumps(payload, ensure_ascii=False)
    )
    request = dict(
        model=MODEL,
        max_tokens=16000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
        output_config={"effort": "medium", "format": {"type": "json_schema", "schema": SUMMARY_SCHEMA}},
    )
    try:
        # 若主模型因安全分類拒答，由伺服器自動改用備援模型重跑
        response = client.beta.messages.create(
            **request, betas=["server-side-fallback-2026-07-01"], fallbacks="default"
        )
    except anthropic.BadRequestError:
        # 部分平台 / 帳號不支援 fallbacks 參數時，改用一般呼叫
        response = client.messages.create(**request)
    if response.stop_reason == "refusal":
        raise RuntimeError("Claude 拒絕回應此請求")
    text = next(b.text for b in response.content if b.type == "text")
    result = json.loads(text)
    result["highlights"] = result["highlights"][:5]
    result["actions"] = result["actions"][:3]
    result["source"] = f"Claude（{response.model}）"
    return result


def summarize(facts: dict, use_ai: bool = True) -> dict:
    has_key = bool(os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN"))
    if use_ai and has_key:
        try:
            return claude_summary(facts)
        except Exception as e:  # 網路、額度、格式錯誤都退回規則式，週報照常產出
            print(f"[AI 摘要] Claude 呼叫失敗，改用規則式摘要：{type(e).__name__}: {e}")
            result = rule_based_summary(facts)
            result["source"] = "規則式摘要（Claude 呼叫失敗）"
            return result
    return rule_based_summary(facts)
