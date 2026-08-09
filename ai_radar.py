"""
AI 产业链雷达 (AI Supply Chain Radar)
=====================================
对标 timsun.net 的 AI Supply Chain Radar 功能，把 AI 产业链拆解为四个层级，
结合实时股价涨跌、新闻事件流与财报信号，合成 24h / 1-7d 投资含义判断。

产业链层级：
  - 芯片层    : 设计(NVDA/AMD/AVGO)、制造(TSM)、设备(ASML)
  - 云基础设施: AWS(AMZN)、Azure(MSFT)、GCP(GOOGL)
  - 大模型    : OpenAI(私有)、Anthropic(私有)、Google(GOOGL)、Meta(META)
  - 应用层    : PLTR、CRM、NOW、FIG

数据源（全部免费、免鉴权公开 API）：
  - Google News RSS : AI 相关新闻流
  - ai_stocks 参数  : 来自 macro_collector 的 AI 股票涨跌数据

依赖:  pip install feedparser requests
"""
from __future__ import annotations

import statistics
from datetime import datetime, timezone
from urllib.parse import quote_plus

import requests

try:
    import feedparser
except ImportError:
    feedparser = None


# --------------------------------------------------------------------------- #
# 1. AI 产业链节点定义（静态映射：公司名/代码/角色，涨跌从 ai_stocks 获取）
# --------------------------------------------------------------------------- #
SUPPLY_CHAIN_NODES: dict[str, list[dict]] = {
    "chips": [
        {"ticker": "NVDA", "name": "英伟达",     "role": "芯片设计 (GPU/AI加速器)", "segment": "设计"},
        {"ticker": "AMD",  "name": "超微半导体", "role": "芯片设计 (CPU/GPU)",      "segment": "设计"},
        {"ticker": "AVGO", "name": "博通",       "role": "芯片设计 (网络/定制ASIC)", "segment": "设计"},
        {"ticker": "TSM",  "name": "台积电",     "role": "芯片制造 (晶圆代工)",     "segment": "制造"},
        {"ticker": "ASML", "name": "阿斯麦",     "role": "半导体设备 (光刻机)",     "segment": "设备"},
    ],
    "cloud": [
        {"ticker": "AMZN",  "name": "亚马逊", "role": "云基础设施 (AWS)",    "segment": "AWS"},
        {"ticker": "MSFT",  "name": "微软",   "role": "云基础设施 (Azure)", "segment": "Azure"},
        {"ticker": "GOOGL", "name": "谷歌",   "role": "云基础设施 (GCP)",   "segment": "GCP"},
    ],
    "models": [
        {"ticker": None,    "name": "OpenAI",    "role": "大模型 (GPT 系列)",     "segment": "私有", "note": "私有公司，无公开股价"},
        {"ticker": None,    "name": "Anthropic", "role": "大模型 (Claude 系列)",  "segment": "私有", "note": "私有公司，无公开股价"},
        {"ticker": "GOOGL", "name": "谷歌",      "role": "大模型 (Gemini)",       "segment": "上市"},
        {"ticker": "META",  "name": "Meta",      "role": "大模型 (Llama)",        "segment": "上市"},
    ],
    "applications": [
        {"ticker": "PLTR", "name": "Palantir",   "role": "AI 数据分析平台",       "segment": "应用"},
        {"ticker": "CRM",  "name": "Salesforce", "role": "AI CRM / SaaS",         "segment": "应用"},
        {"ticker": "NOW",  "name": "ServiceNow", "role": "AI IT 服务管理",        "segment": "应用"},
        {"ticker": "FIG",  "name": "Figma",      "role": "AI 设计工具",           "segment": "应用"},
    ],
}


def build_supply_chain(ai_stocks: dict | None = None) -> dict[str, list[dict]]:
    """
    构建 AI 产业链节点视图，注入当日涨跌数据。

    参数:
        ai_stocks: macro_collector.fetch_ai_stocks() 的输出，
                   形如 {"NVDA": {"value":..., "change_pct":..., ...}, ...}

    返回:
        {"chips": [...], "cloud": [...], "models": [...], "applications": [...]}
        每个节点增加 value / change_pct / date 字段（有数据时），
        无数据的节点标记 data_available=False。
    """
    ai_stocks = ai_stocks or {}
    result: dict[str, list[dict]] = {}

    for layer, nodes in SUPPLY_CHAIN_NODES.items():
        enriched = []
        for node in nodes:
            entry = dict(node)  # 浅拷贝静态信息
            ticker = node.get("ticker")
            if ticker and ticker in ai_stocks:
                stock = ai_stocks[ticker]
                entry["value"] = stock.get("value")
                entry["change_pct"] = stock.get("change_pct")
                entry["date"] = stock.get("date")
                entry["data_available"] = True
            else:
                entry["data_available"] = False
            enriched.append(entry)
        result[layer] = enriched

    return result


# --------------------------------------------------------------------------- #
# 2. AI 新闻事件流（Google News RSS）
# --------------------------------------------------------------------------- #
AI_NEWS_QUERIES = [
    "artificial intelligence",
    "AI chip",
]

_AI_NEWS_HEADERS = {"User-Agent": "ai-radar/1.0 (research)"}


def fetch_ai_news(limit: int = 10) -> list[dict]:
    """
    从 Google News RSS 采集 AI 相关新闻。

    搜索关键词: "artificial intelligence" 和 "AI chip"
    返回最近 limit 条，每条包含 title / url / published / source。
    """
    if feedparser is None:
        print("[warn] feedparser 未安装，跳过 AI 新闻流")
        return []

    items: list[dict] = []
    seen_urls: set[str] = set()

    for q in AI_NEWS_QUERIES:
        url = (
            f"https://news.google.com/rss/search?"
            f"q={quote_plus(q)}&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"
        )
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries:
                link = entry.get("link", "")
                # 去重
                if link in seen_urls:
                    continue
                seen_urls.add(link)

                items.append({
                    "title": entry.get("title", ""),
                    "url": link,
                    "published": entry.get("published", ""),
                    "source": entry.get("source", {}).get("title", "google_news")
                              if hasattr(entry.get("source", ""), "get")
                              else "google_news",
                    "query": q,
                })
                if len(items) >= limit:
                    break
            if len(items) >= limit:
                break
        except Exception as e:
            print(f"[warn] AI 新闻 RSS 抓取失败 ({q}): {e}")

    return items[:limit]


# --------------------------------------------------------------------------- #
# 3. AI 财报信号（基于已采集的 AI 股票涨跌）
# --------------------------------------------------------------------------- #
def compute_earnings_signals(ai_stocks: dict | None = None) -> dict:
    """
    基于 AI 股票当日涨跌生成信号。

    - 计算 AI 股票整体涨跌中位数
    - 识别领涨 / 领跌股票
    - 生成投资含义判断
    """
    ai_stocks = ai_stocks or {}

    # 提取所有有 change_pct 的股票
    changes: list[tuple[str, float]] = []
    for ticker, data in ai_stocks.items():
        chg = data.get("change_pct")
        if chg is not None:
            changes.append((ticker, float(chg)))

    if not changes:
        return {
            "median_change_pct": None,
            "mean_change_pct": None,
            "up_count": 0,
            "down_count": 0,
            "total": 0,
            "up_ratio": 0,
            "leaders": [],
            "laggers": [],
            "verdict": "无可用 AI 股票数据，无法生成信号",
        }

    # 按涨跌幅排序
    changes.sort(key=lambda x: x[1], reverse=True)
    pct_values = [c[1] for c in changes]

    median_chg = statistics.median(pct_values)
    mean_chg = statistics.mean(pct_values)
    up_count = sum(1 for _, v in changes if v > 0)
    down_count = sum(1 for _, v in changes if v < 0)
    total = len(changes)
    up_ratio = up_count / total if total else 0

    # 领涨 / 领跌（取前 3）
    leaders = [
        {"ticker": t, "name": ai_stocks.get(t, {}).get("name", t),
         "change_pct": v}
        for t, v in changes[:3] if v > 0
    ]
    laggards = [
        {"ticker": t, "name": ai_stocks.get(t, {}).get("name", t),
         "change_pct": v}
        for t, v in changes[-3:][::-1] if v < 0
    ]

    # 综合信号判断
    if median_chg > 2 and up_ratio >= 0.7:
        verdict = "AI 板块全面走强，多头情绪高涨"
    elif median_chg > 1:
        verdict = "AI 板块偏强，多数个股上涨"
    elif median_chg > 0:
        verdict = "AI 板块温和偏多，涨跌互现"
    elif median_chg > -1:
        verdict = "AI 板块震荡，方向不明"
    elif median_chg > -2:
        verdict = "AI 板块偏弱，多数个股下跌"
    else:
        verdict = "AI 板块全面承压，空头情绪浓厚"

    return {
        "median_change_pct": round(median_chg, 2),
        "mean_change_pct": round(mean_chg, 2),
        "up_count": up_count,
        "down_count": down_count,
        "total": total,
        "up_ratio": round(up_ratio, 2),
        "leaders": leaders,
        "laggers": laggards,
        "verdict": verdict,
    }


# --------------------------------------------------------------------------- #
# 4. 投资含义判断（综合产业链 + 信号 -> 24h / 1-7d）
# --------------------------------------------------------------------------- #
def compute_investment_implications(
    supply_chain: dict,
    earnings_signals: dict,
) -> dict:
    """
    综合产业链节点表现与财报信号，生成投资含义判断。

    返回:
      - supply_chain_health : 产业链健康度（强/中/弱）
      - capital_flow        : 资金流向（流入/流出/均衡）
      - verdict_24h         : 24 小时判断
      - verdict_1_7d        : 1-7 天判断
    """
    median = earnings_signals.get("median_change_pct") or 0
    up_ratio = earnings_signals.get("up_ratio") or 0
    up_count = earnings_signals.get("up_count", 0)
    down_count = earnings_signals.get("down_count", 0)

    # ---- 产业链健康度 ----
    if up_ratio >= 0.7 and median > 1:
        health = "强"
    elif up_ratio >= 0.5 and median > 0:
        health = "中"
    elif up_ratio <= 0.3 and median < -1:
        health = "弱"
    else:
        health = "中"

    # ---- 资金流向 ----
    if median > 1:
        flow = "流入"
    elif median < -1:
        flow = "流出"
    else:
        flow = "均衡"

    # ---- 各层级表现汇总 ----
    layer_summary = {}
    for layer, nodes in supply_chain.items():
        changes = [
            n["change_pct"] for n in nodes
            if n.get("data_available") and n.get("change_pct") is not None
        ]
        if changes:
            layer_summary[layer] = {
                "avg_change_pct": round(statistics.mean(changes), 2),
                "up": sum(1 for c in changes if c > 0),
                "down": sum(1 for c in changes if c < 0),
                "total": len(changes),
            }
        else:
            layer_summary[layer] = {"avg_change_pct": None, "up": 0, "down": 0, "total": 0}

    # 找出表现最强和最弱的层级
    layer_avg = {
        layer: s["avg_change_pct"]
        for layer, s in layer_summary.items()
        if s["avg_change_pct"] is not None
    }
    strongest_layer = max(layer_avg, key=layer_avg.get) if layer_avg else None
    weakest_layer = min(layer_avg, key=layer_avg.get) if layer_avg else None

    layer_names_cn = {
        "chips": "芯片层",
        "cloud": "云基础设施",
        "models": "大模型",
        "applications": "应用层",
    }

    # ---- 24h 判断 ----
    if health == "强":
        verdict_24h = (
            f"AI 产业链整体强势，资金积极流入。"
            f"最强层级: {layer_names_cn.get(strongest_layer, 'N/A')}。"
            f"短线动能充沛，多头主导。"
        )
    elif health == "弱":
        verdict_24h = (
            f"AI 产业链承压，资金流出。"
            f"最弱层级: {layer_names_cn.get(weakest_layer, 'N/A')}。"
            f"短线偏弱，空头情绪升温。"
        )
    else:
        verdict_24h = (
            f"AI 产业链分化，资金流向均衡。"
            f"涨跌互现，短线震荡为主。"
        )

    # ---- 1-7d 判断 ----
    if median > 2:
        verdict_1_7d = (
            "中期趋势偏多，产业链基本面强劲。"
            "但需警惕短期过热后的回调风险，关注龙头股能否持续领涨。"
        )
    elif median > 0.5:
        verdict_1_7d = (
            "中期温和偏多，产业链整体健康。"
            "资金稳步流入，有望延续上行趋势。"
        )
    elif median > -0.5:
        verdict_1_7d = (
            "中期震荡格局，产业链表现分化。"
            "关注芯片层与云基础设施能否企稳，等待方向选择。"
        )
    elif median > -2:
        verdict_1_7d = (
            "中期偏弱，资金可能阶段性撤离 AI 板块。"
            "关注超跌反弹机会，但需等待企稳信号。"
        )
    else:
        verdict_1_7d = (
            "中期承压，AI 板块面临调整压力。"
            "建议谨慎，关注基本面变化与资金回流信号。"
        )

    return {
        "supply_chain_health": health,
        "capital_flow": flow,
        "strongest_layer": strongest_layer,
        "weakest_layer": weakest_layer,
        "layer_summary": layer_summary,
        "verdict_24h": verdict_24h,
        "verdict_1_7d": verdict_1_7d,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# --------------------------------------------------------------------------- #
# 5. 汇总
# --------------------------------------------------------------------------- #
def collect_ai_radar(ai_stocks: dict = None) -> dict:
    """
    采集 AI 产业链雷达数据。

    参数:
        ai_stocks: macro_collector.fetch_ai_stocks() 的输出。
                   包含各 AI 股票的 value / change_pct / date / name。
                   为 None 时使用空字典（产业链节点将无涨跌数据）。

    返回:
        {
            "supply_chain": {"chips": [...], "cloud": [...],
                             "models": [...], "applications": [...]},
            "news_flow": [...],
            "earnings_signals": {...},
            "investment_implications": {...}
        }
    """
    ai_stocks = ai_stocks or {}

    print("[info] 构建 AI 产业链节点视图...")
    supply_chain = build_supply_chain(ai_stocks)

    print("[info] 采集 AI 新闻事件流...")
    news_flow = fetch_ai_news(limit=10)

    print("[info] 计算 AI 财报信号...")
    earnings_signals = compute_earnings_signals(ai_stocks)

    print("[info] 生成投资含义判断...")
    investment_implications = compute_investment_implications(
        supply_chain, earnings_signals
    )

    radar = {
        "supply_chain": supply_chain,
        "news_flow": news_flow,
        "earnings_signals": earnings_signals,
        "investment_implications": investment_implications,
    }

    mq = investment_implications
    print(
        f"[ok] AI 雷达完成  "
        f"产业链健康度={mq.get('supply_chain_health')} "
        f"资金流向={mq.get('capital_flow')} "
        f"新闻{len(news_flow)}条 "
        f"信号中位数={earnings_signals.get('median_change_pct')}"
    )
    return radar


if __name__ == "__main__":
    import json

    # 自测：用一份示例 ai_stocks 数据
    sample_ai_stocks = {
        "NVDA":  {"value": 138.50, "change_pct": 2.35,  "date": "2026-08-07", "name": "英伟达",     "source": "Yahoo Finance"},
        "AMD":   {"value": 162.20, "change_pct": -0.82, "date": "2026-08-07", "name": "超微半导体", "source": "Yahoo Finance"},
        "AVGO":  {"value": 175.40, "change_pct": 1.15,  "date": "2026-08-07", "name": "博通",       "source": "Yahoo Finance"},
        "TSM":   {"value": 205.30, "change_pct": 0.95,  "date": "2026-08-07", "name": "台积电",     "source": "Yahoo Finance"},
        "MSFT":  {"value": 432.10, "change_pct": 0.55,  "date": "2026-08-07", "name": "微软",       "source": "Yahoo Finance"},
        "GOOGL": {"value": 178.90, "change_pct": -0.30, "date": "2026-08-07", "name": "谷歌",       "source": "Yahoo Finance"},
        "META":  {"value": 565.20, "change_pct": 1.80,  "date": "2026-08-07", "name": "Meta",       "source": "Yahoo Finance"},
        "AMZN":  {"value": 198.50, "change_pct": 0.42,  "date": "2026-08-07", "name": "亚马逊",     "source": "Yahoo Finance"},
        "AAPL":  {"value": 228.70, "change_pct": -0.15, "date": "2026-08-07", "name": "苹果",       "source": "Yahoo Finance"},
        "PLTR":  {"value": 35.60,  "change_pct": 3.20,  "date": "2026-08-07", "name": "Palantir",   "source": "Yahoo Finance"},
        "CRM":   {"value": 245.80, "change_pct": 0.88,  "date": "2026-08-07", "name": "Salesforce", "source": "Yahoo Finance"},
        "NOW":   {"value": 890.50, "change_pct": 1.22,  "date": "2026-08-07", "name": "ServiceNow", "source": "Yahoo Finance"},
    }

    result = collect_ai_radar(sample_ai_stocks)
    print(json.dumps(result, ensure_ascii=False, indent=2))
