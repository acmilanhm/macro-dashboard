"""
卖方研报结构化模块
==================
两个数据来源 + LLM 结构化，输出统一 schema：

1. yfinance 分析师接口（已结构化）
   - upgrades_downgrades  : 评级变动（升级/降级/首次覆盖）
   - analyst_price_targets : 一致目标价（低/均/高）
2. RSS 新闻流（Google News 关键词检索，始终免费可用）
   - 原始文本经 LLM 抽取为结构化字段

统一输出 schema:
{
  "bank":        "花旗/Citi",
  "action":      "upgrade|downgrade|initiate|reiterate|target_change",
  "ticker":      "FIG",
  "company":     "Figma",
  "target_price": 37,
  "prev_target": null,
  "direction":   "bullish|bearish|neutral",
  "rationale":   "一句话理由",
  "source":      "yfinance|marketbeat.com|...",
  "url":         "https://...",
  "date":        "2026-08-08"
}
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from urllib.parse import quote_plus

import requests

try:
    import yfinance as yf
except ImportError:
    yf = None

try:
    import feedparser
except ImportError:
    feedparser = None

from llm_utils import call_llm_json

# 关注列表：AI/半导体/宏观相关龙头（可自行增减）
WATCHLIST = [
    "NVDA", "AMD", "AVGO", "TSM", "ASML", "MU",          # 半导体
    "MSFT", "GOOGL", "META", "AMZN", "AAPL",              # 大型科技
    "FIG", "PLTR", "CRM", "NOW",                          # AI 应用/SaaS
]


# --------------------------------------------------------------------------- #
# 1. yfinance：已结构化的评级变动 + 目标价
# --------------------------------------------------------------------------- #
def fetch_analyst_ratings(tickers: list[str] = WATCHLIST) -> list[dict]:
    if yf is None:
        print("[warn] yfinance 未安装，跳过分析师评级")
        return []
    results = []
    for sym in tickers:
        for attempt in range(2):
            try:
                t = yf.Ticker(sym)
                grades = t.upgrades_downgrades
                targets = t.analyst_price_targets
                break
            except Exception as e:
                print(f"[warn] {sym} 评级抓取第{attempt+1}次失败: {e}")
                time.sleep(3)
        else:
            continue
        time.sleep(1.5)  # 限流退避

        # 评级变动（取最近 5 条）
        if grades is not None and not grades.empty:
            recent = grades.tail(5)
            for date, row in recent.iterrows():
                results.append({
                    "bank": row.get("Brokerage", "unknown"),
                    "action": _norm_action(row.get("Action", "")),
                    "ticker": sym,
                    "company": t.info.get("shortName", sym) if hasattr(t, "info") else sym,
                    "target_price": None,
                    "prev_target": None,
                    "direction": _grade_to_direction(row.get("Grade", "")),
                    "rationale": f"评级调整: {row.get('FromGrade','?')} -> {row.get('Grade','?')}",
                    "source": "yfinance",
                    "url": f"https://finance.yahoo.com/quote/{sym}",
                    "date": str(date.date()) if hasattr(date, "date") else str(date),
                })

        # 一致目标价
        if targets:
            results.append({
                "bank": "consensus",
                "action": "target_change",
                "ticker": sym,
                "company": sym,
                "target_price": targets.get("mean") or targets.get("median"),
                "prev_target": None,
                "direction": _target_direction(
                    targets.get("current"), targets.get("mean")),
                "rationale": f"一致目标 {targets.get('mean')} (低 {targets.get('low')}/高 {targets.get('high')}), 现价 {targets.get('current')}",
                "source": "yfinance",
                "url": f"https://finance.yahoo.com/quote/{sym}",
                "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            })
    return results


def _norm_action(action: str) -> str:
    a = action.lower()
    if "up" in a or "init" in a and "buy" in a:
        return "upgrade" if "up" in a else "initiate"
    if "down" in a:
        return "downgrade"
    if "init" in a:
        return "initiate"
    if "reit" in a or "maint" in a:
        return "reiterate"
    return "target_change"


def _grade_to_direction(grade: str) -> str:
    g = grade.lower()
    if any(k in g for k in ("buy", "overweight", "outperform", "strong")):
        return "bullish"
    if any(k in g for k in ("sell", "underweight", "underperform")):
        return "bearish"
    return "neutral"


def _target_direction(current, target):
    try:
        if target and current and target > current * 1.05:
            return "bullish"
        if target and current and target < current * 0.95:
            return "bearish"
    except Exception:
        pass
    return "neutral"


# --------------------------------------------------------------------------- #
# 2. RSS 新闻流：Google News 关键词检索 -> LLM 结构化
# --------------------------------------------------------------------------- #
RSS_QUERIES = [
    "analyst upgrade OR downgrade price target",
    "investment bank rating change semiconductor OR AI",
]


def fetch_research_rss(limit_per_query: int = 10) -> list[dict]:
    if feedparser is None:
        print("[warn] feedparser 未安装，跳过 RSS 研报")
        return []
    items = []
    for q in RSS_QUERIES:
        url = f"https://news.google.com/rss/search?q={quote_plus(q)}&hl=en-US&gl=US&ceid=US:en"
        try:
            feed = feedparser.parse(url)
            for e in feed.entries[:limit_per_query]:
                items.append({
                    "title": e.get("title", ""),
                    "url": e.get("link", ""),
                    "published": e.get("published", ""),
                    "summary": e.get("summary", "")[:500],
                    "source": "google_news",
                })
        except Exception as e:
            print(f"[warn] RSS 抓取失败 ({q}): {e}")
    return items


# --------------------------------------------------------------------------- #
# 3. LLM 结构化：把多条 RSS 标题批量抽取为统一 schema
# --------------------------------------------------------------------------- #
STRUCTURE_SYSTEM = """你是金融研报结构化助手。把输入的多条市场新闻标题，
抽取其中属于"卖方分析师评级/目标价变动"的条目，输出 JSON 数组。
只保留真正涉及分析师评级、目标价、覆盖变动的条目，过滤纯新闻。
每条字段: bank(机构), action(upgrade/downgrade/initiate/reiterate/target_change),
ticker, company, target_price(数字或null), prev_target(数字或null),
direction(bullish/bearish/neutral), rationale(中文一句话), source, url, date(YYYY-MM-DD或null)。
若信息不足，对应字段填 null。只输出 JSON 数组，不要多余文字。"""


def structure_rss_with_llm(items: list[dict]) -> list[dict]:
    if not items:
        return []
    # 批量喂给 LLM，每批最多 15 条
    batched = []
    for i in range(0, len(items), 15):
        chunk = items[i:i + 15]
        text = "\n".join(
            f"{n}. [{c.get('source')}] {c.get('title')} | {c.get('summary')} | {c.get('url')}"
            for n, c in enumerate(chunk, 1)
        )
        try:
            parsed, _ = call_llm_json(STRUCTURE_SYSTEM, text, max_tokens=1200)
            if isinstance(parsed, list):
                # 补全 url/source
                for j, rec in enumerate(parsed):
                    if j < len(chunk):
                        rec.setdefault("url", chunk[j].get("url"))
                        rec.setdefault("source", chunk[j].get("source"))
                batched.extend(parsed)
        except Exception as e:
            print(f"[warn] LLM 结构化失败: {e}")
    return batched


# --------------------------------------------------------------------------- #
# 4. 汇总
# --------------------------------------------------------------------------- #
def collect_research() -> dict:
    """收集并结构化卖方研报，返回 {'ratings': [...], 'rss_structured': [...]}"""
    print("[info] 抓取 yfinance 分析师评级...")
    ratings = fetch_analyst_ratings()
    print(f"[info] yfinance 评级 {len(ratings)} 条")

    print("[info] 抓取 RSS 研报流...")
    rss = fetch_research_rss()
    print(f"[info] RSS 原始 {len(rss)} 条，调用 LLM 结构化...")
    structured = structure_rss_with_llm(rss)
    print(f"[info] 结构化研报 {len(structured)} 条")

    return {"ratings": ratings, "rss_structured": structured}


if __name__ == "__main__":
    import json
    print(json.dumps(collect_research(), ensure_ascii=False, indent=2))
