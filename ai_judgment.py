"""
AI 研判生成模块
==============
把当日全部数据（价格 / 宏观流动性 / 事件流 / 卖方研报）喂给 LLM，
生成 timsun.net 同款的三段式研判：

  - headline : 今日主线判断（一句话 + 时间窗口 + 置信度）
  - why      : 为什么（2-3 句，引用具体数据：价格、流动性、信用、利率）
  - risk     : 什么情况下这个判断会错（背离信号 / 失效条件）

输出严格 JSON，便于前端直接渲染。
"""
from __future__ import annotations

import json

from llm_utils import call_llm_json


JUDGMENT_SYSTEM = """你是一位严谨的跨资产宏观策略师，风格类似 timsun.net 的研究引擎。
你的任务：基于给定的当日市场数据，输出一个结构化的"今日主线判断"。

要求：
1. headline：一句话定性当日市场主线（如"事件驱动的流动性反弹，非基本面改善"），
   并给出时间窗口（未来1-3个交易日）和置信度（高/中/低）。格式："<定性> · <窗口> · 置信度<高/中/低>"。
2. why：2-3句，必须引用具体数据支撑（价格涨跌、净流动性、HY利差z-score、利率变动等），
   说明催化剂与跨资产是否共振。
3. risk：什么情况下这个判断会错？指出背离信号与失效条件（如某资产分化、动能偏弱等）。
4. catalysts：1-3个当日关键催化剂（简短）。

只输出 JSON，字段：headline, timeframe, confidence, why, risk, catalysts(数组)。不要多余文字。"""


def _fmt_prices(prices: dict) -> str:
    lines = []
    for k, v in prices.items():
        lines.append(f"- {k}: {v.get('value')} ({v.get('change_pct','?')}%) @ {v.get('date')}")
    return "\n".join(lines) or "(无)"


def _fmt_macro(macro: dict) -> str:
    lines = []
    for k, v in macro.items():
        lines.append(f"- {k}: {v.get('value')} {v.get('unit','')} @ {v.get('date','')} ({v.get('source','')})")
    return "\n".join(lines) or "(无)"


def _fmt_events(events: list[dict]) -> str:
    if not events:
        return "(无)"
    return "\n".join(f"- [{e.get('source')}] {e.get('title')}" for e in events[:12])


def _fmt_research(research: dict) -> str:
    items = research.get("rss_structured", []) + research.get("ratings", [])
    if not items:
        return "(无)"
    lines = []
    for r in items[:12]:
        lines.append(
            f"- {r.get('bank','?')} {r.get('action','?')} {r.get('ticker','')} "
            f"目标{r.get('target_price')} 方向{r.get('direction','?')}: {r.get('rationale','')}"
        )
    return "\n".join(lines)


def _fmt_crypto(crypto: dict) -> str:
    mq = crypto.get("market_quality") or {}
    if not mq:
        return "(无)"
    bn = crypto.get("binance", {})
    der = crypto.get("deribit", {})
    return (
        f"- 资金费率(8h): {mq.get('funding_rate_8h')} 热度={mq.get('funding_heat')} "
        f"杠杆方向={mq.get('leverage_direction')}\n"
        f"- DVOL: {mq.get('dvol')} ({mq.get('dvol_regime')})\n"
        f"- Put/Call OI: {mq.get('put_call_ratio')} ({mq.get('options_positioning')})\n"
        f"- Binance OI: {bn.get('open_interest')} | Deribit 永续 OI: {der.get('perp_oi')}\n"
        f"- 雷达判断 24h: {mq.get('verdict_24h')}\n"
        f"- 雷达判断 1-7d: {mq.get('verdict_1_7d')}"
    )


def generate_judgment(payload: dict) -> dict | None:
    """payload 为 macro_collector.collect_all 的输出（含 prices/macro/events/research）。"""
    user = f"""# 当日市场数据快照

## 核心资产价格
{_fmt_prices(payload.get('prices', {}))}

## 宏观与流动性
{_fmt_macro(payload.get('macro', {}))}

## 市场事件流
{_fmt_events(payload.get('events', []))}

## 卖方研报
{_fmt_research(payload.get('research', {}))}

## 加密衍生品雷达
{_fmt_crypto(payload.get('crypto', {}))}

请输出今日主线判断（JSON）。"""
    parsed, raw = call_llm_json(JUDGMENT_SYSTEM, user, temperature=0.4, max_tokens=900)
    if parsed is None:
        print(f"[warn] 研判生成失败，原始输出: {raw[:300]}")
        return None
    return parsed


if __name__ == "__main__":
    # 自测：用一份示例 payload
    sample = {
        "prices": {
            "SP500": {"value": 7757.64, "change_pct": 0.62, "date": "2026-08-07"},
            "DXY": {"value": 99.60, "change_pct": -0.37, "date": "2026-08-07"},
            "BTC": {"value": 64925, "change_pct": 0.07, "date": "2026-08-08"},
            "WTI": {"value": 78.18, "change_pct": 1.15, "date": "2026-08-07"},
        },
        "macro": {
            "VIX_10Y": {"value": 4.65, "unit": "%", "date": "2026-08-07", "source": "FRED DGS10"},
            "VIX": {"value": 14.90, "date": "2026-08-07", "source": "FRED VIXCLS"},
            "HY_OAS": {"value": 2.71, "unit": "%", "date": "2026-08-06", "source": "FRED BAMLH0A0HYM2"},
            "NET_LIQUIDITY": {"value": 5450, "unit": "billion_usd", "date": "2026-08-07", "source": "computed"},
        },
        "events": [{"source": "reddit_equities", "title": "Citi raises Figma price target to $37"}],
        "research": {"ratings": [], "rss_structured": []},
        "crypto": {
            "binance": {"funding_rate": 0.00012, "open_interest": 580000},
            "deribit": {"dvol": 58, "perp_oi": 12000, "put_call_ratio": 0.72},
            "market_quality": {
                "funding_rate_8h": 0.00012, "funding_heat": "warm",
                "leverage_direction": "bullish", "dvol": 58, "dvol_regime": "normal",
                "put_call_ratio": 0.72, "options_positioning": "balanced",
                "verdict_24h": "衍生品结构偏多，短线动能健康",
                "verdict_1_7d": "中期偏多，资金费率与期权定位支撑",
            },
        },
    }
    # 仅打印 prompt 构造结果（不调用 LLM）
    print("=== 加密段渲染 ===")
    print(_fmt_crypto(sample["crypto"]))
    print("=== 调用 LLM 生成研判 ===")
    print(json.dumps(generate_judgment(sample), ensure_ascii=False, indent=2))
