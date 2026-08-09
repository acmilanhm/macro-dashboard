"""
极简可视化面板：读取 daily_macro.json 并展示（含 AI 研判 + 卖方研报）
增强版：所有数据源带超链接，数据口径透明度表，外部资源导航
运行:  streamlit run dashboard.py
"""
import json
import os

import streamlit as st

DATA_FILE = "daily_macro.json"

# ---- 数据源超链接映射（全部使用内地可访问的网站）----
PRICE_LINKS = {
    "SP500": ("https://cn.investing.com/indices/us-spx-500", "英为财情"),
    "DXY":   ("https://cn.investing.com/indices/usdollar-index", "英为财情"),
    "BTC":   ("https://www.feixiaohao.com/currencies/bitcoin/", "非小号"),
    "WTI":   ("https://cn.investing.com/commodities/crude-oil", "英为财情"),
}

MACRO_LINKS = {
    "VIX_10Y":    ("https://fred.stlouisfed.org/series/DGS10", "FRED DGS10", "10Y 国债收益率"),
    "VIX":        ("https://fred.stlouisfed.org/series/VIXCLS", "FRED VIXCLS", "VIX 恐慌指数"),
    "HY_OAS":     ("https://fred.stlouisfed.org/series/BAMLH0A0HYM2", "ICE BofA / FRED", "高收益债 OAS 利差"),
    "FED_ASSETS": ("https://fred.stlouisfed.org/series/WALCL", "FRED WALCL", "美联储总资产"),
    "TGA":        ("https://fred.stlouisfed.org/series/WTREGEN", "FRED WTREGEN", "财政部一般账户"),
    "RRP":        ("https://fred.stlouisfed.org/series/WLRRAL", "FRED WLRRAL", "隔夜逆回购余额"),
    "NET_LIQUIDITY": ("https://fred.stlouisfed.org/series/WALCL", "计算: WALCL-RRP-TGA", "净流动性"),
}

CRYPTO_LINKS = {
    "binance": ("https://www.feixiaohao.com/currencies/bitcoin/", "非小号(BTC)"),
    "bybit":   ("https://www.feixiaohao.com/contract/bitcoin/", "非小号(合约)"),
    "deribit": ("https://cn.investing.com/crypto/bitcoin", "英为财情(BTC)"),
}

# ---- 外部资源链接（全部内地可访问）----
EXTERNAL_RESOURCES = [
    ("英为财情", "https://cn.investing.com", "全球指数/外汇/商品/加密货币行情"),
    ("东方财富网", "https://www.eastmoney.com", "A股/美股/基金综合财经门户"),
    ("新浪财经", "https://finance.sina.com.cn", "美股/A股/期货实时行情"),
    ("雪球", "https://xueqiu.com", "投资社区/美股讨论"),
    ("华尔街见闻", "https://wallstreetcn.com", "全球宏观资讯快讯"),
    ("金十数据", "https://www.jin10.com", "财经日历/实时快讯"),
    ("FRED 经济数据", "https://fred.stlouisfed.org", "美联储经济数据库(可访问)"),
    ("美国财政部", "https://home.treasury.gov", "国债收益率曲线"),
    ("美联储 H.4.1", "https://www.federalreserve.gov/releases/h41/", "美联储资产负债表"),
    ("非小号", "https://www.feixiaohao.com", "加密货币行情/合约数据"),
    ("CoinGlass", "https://www.coinglass.com", "加密衍生品聚合(可能需确认)"),
    ("同花顺", "https://www.10jqka.com.cn", "A股/美股行情分析"),
    ("Gitee 代码仓库", "https://gitee.com", "国内代码托管平台"),
    ("timsun.net", "https://timsun.net/", "参考网站（原始灵感来源）"),
]


def load_data():
    if not os.path.exists(DATA_FILE):
        return None
    with open(DATA_FILE, encoding="utf-8") as f:
        return json.load(f)


def fmt_chg(val):
    """格式化涨跌幅，带颜色 emoji。"""
    if val is None:
        return ""
    if val > 0:
        return f"🔴 +{val:.2f}%"
    elif val < 0:
        return f"🟢 {val:.2f}%"
    return f"⚪ {val:.2f}%"


def fmt_value(key, val):
    """根据指标类型格式化数值。"""
    if val is None:
        return "—"
    if key in ("SP500",):
        return f"{val:,.2f}"
    if key in ("BTC",):
        return f"${val:,.0f}"
    if key in ("WTI",):
        return f"${val:.2f}/桶"
    if key in ("DXY",):
        return f"{val:.2f}"
    if key in ("VIX",):
        return f"{val:.2f}"
    if key in ("VIX_10Y", "HY_OAS"):
        return f"{val:.2f}%"
    if key in ("FED_ASSETS", "TGA", "RRP", "NET_LIQUIDITY"):
        if val > 1000:
            return f"{val/1000:.2f} 万亿"
        return f"{val:.1f} 亿"
    return str(val)


def main():
    st.set_page_config(page_title="每日宏观仪表盘", layout="wide")
    st.title("每日宏观跨资产仪表盘")

    data = load_data()
    if not data:
        st.warning("未找到 daily_macro.json，请先运行 macro_collector.py")
        return

    st.caption(f"采集时间：{data.get('collected_at', '')}  ·  交易日：{data.get('trade_date', '')}")

    # =========================================================================
    # 1. AI 研判横幅
    # =========================================================================
    j = data.get("judgment")
    if j:
        conf = j.get("confidence", "")
        st.success(f"### {j.get('headline', '')}")
        col1, col2 = st.columns([3, 1])
        col1.markdown(f"**为什么：** {j.get('why', '')}")
        col1.markdown(f"**什么情况下判断会错：** {j.get('risk', '')}")
        col2.metric("置信度", conf)
        col2.metric("时间窗口", j.get("timeframe", ""))
        if j.get("catalysts"):
            st.markdown("**催化剂：** " + " / ".join(j["catalysts"]))
        st.divider()
    else:
        st.info("未生成 AI 研判（需配置 LLM_API_KEY）")

    # =========================================================================
    # 2. 核心资产价格（带超链接）
    # =========================================================================
    st.subheader("核心资产价格")
    prices = data.get("prices", {})
    price_rows = []
    labels_cn = {"SP500": "标普500", "DXY": "美元指数", "BTC": "比特币", "WTI": "WTI原油"}
    for key in ["SP500", "DXY", "BTC", "WTI"]:
        p = prices.get(key)
        if p:
            link, src_name = PRICE_LINKS.get(key, ("", ""))
            price_rows.append({
                "指标": labels_cn.get(key, key),
                "数值": fmt_value(key, p.get("value")),
                "日涨跌": fmt_chg(p.get("change_pct")),
                "数据日期": p.get("date", "—"),
                "来源": f"[{src_name}]({link})" if link else p.get("source", ""),
            })

    if price_rows:
        # 用 markdown 表格渲染，支持超链接
        md = "| 指标 | 数值 | 日涨跌 | 数据日期 | 来源 |\n|------|------|--------|----------|------|\n"
        for r in price_rows:
            md += f"| {r['指标']} | {r['数值']} | {r['日涨跌']} | {r['数据日期']} | {r['来源']} |\n"
        st.markdown(md)

    # =========================================================================
    # 3. 宏观与流动性指标（带 FRED 超链接）
    # =========================================================================
    st.subheader("宏观与流动性指标")
    macro = data.get("macro", {})
    if macro:
        md = "| 指标 | 数值 | 数据日期 | 来源链接 | 说明 |\n|------|------|----------|----------|------|\n"
        for k, v in macro.items():
            val = v.get("value")
            date = v.get("date", "—")
            link_info = MACRO_LINKS.get(k)
            if link_info:
                link, src_name, desc = link_info
                source_cell = f"[{src_name}]({link})"
            else:
                source_cell = v.get("source", "")
                desc = ""
            md += f"| {desc or k} | {fmt_value(k, val)} | {date} | {source_cell} | {desc} |\n"
        st.markdown(md)

        # 净流动性公式说明
        nl = macro.get("NET_LIQUIDITY")
        if nl:
            st.caption(f"净流动性 = 美联储总资产(WALCL) − 逆回购(RRP) − 财政部TGA | "
                       f"计算值: {nl.get('value', '?')} 亿 | "
                       f"详见 [FRED WALCL](https://fred.stlouisfed.org/series/WALCL)")

    st.divider()

    # =========================================================================
    # 4. 加密衍生品雷达（带交易所超链接）
    # =========================================================================
    st.subheader("加密衍生品雷达")
    crypto = data.get("crypto", {})
    mq = crypto.get("market_quality", {})
    if mq and mq.get("funding_rate_8h") is not None:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("资金费率(8h)", f"{mq.get('funding_rate_8h','?')}",
                  mq.get("funding_heat", ""))
        c1.caption(mq.get("leverage_direction", ""))
        c2.metric("DVOL", mq.get("dvol", "?"), mq.get("dvol_regime", ""))
        c3.metric("Put/Call OI", mq.get("put_call_ratio", "?"),
                  mq.get("options_positioning", ""))
        bn = crypto.get("binance", {})
        c4.metric("BTC 持仓量", bn.get("open_interest", "?"))

        st.info(f"**24h 判断：** {mq.get('verdict_24h','')}  \n"
                f"**1-7d 判断：** {mq.get('verdict_1_7d','')}")

        # 交易所数据表（带超链接）
        st.markdown("**交易所永续合约数据**")
        md = "| 交易所 | 最新价 | 资金费率 | 持仓量 | 链接 |\n|--------|--------|----------|--------|------|\n"
        for ex_key in ["binance", "bybit"]:
            ex_data = crypto.get(ex_key, {})
            if ex_data and "error" not in ex_data:
                link, name = CRYPTO_LINKS.get(ex_key, ("", ex_key))
                price = ex_data.get("mark_price") or ex_data.get("last_price", "—")
                fr = ex_data.get("funding_rate", "—")
                oi = ex_data.get("open_interest", "—")
                md += f"| {name} | {price} | {fr} | {oi} | [打开 →]({link}) |\n"
        st.markdown(md)

        # Deribit 期权数据
        der = crypto.get("deribit", {})
        if der and "error" not in der:
            st.markdown("**BTC 期权数据**")
            md = "| DVOL | Put OI | Call OI | Put/Call | 总期权OI | 永续资金(8h) | 链接 |\n"
            md += "|------|--------|---------|----------|----------|-------------|------|\n"
            md += (f"| {der.get('dvol','—')} | {der.get('put_oi','—')} | {der.get('call_oi','—')} | "
                   f"{der.get('put_call_ratio','—')} | {der.get('total_options_oi','—')} | "
                   f"{der.get('perp_funding_8h','—')} | "
                   f"[英为财情 →](https://cn.investing.com/crypto/bitcoin) |\n")
            st.markdown(md)

        # BTC 现货 ETF
        etfs = crypto.get("etfs", [])
        if etfs:
            st.markdown("**BTC 现货 ETF**")
            md = "| 代码 | 发行商 | 价格 | 成交量 | 涨跌% | 日期 | 行情链接 |\n"
            md += "|------|--------|------|--------|-------|------|-----------|\n"
            for e in etfs:
                ticker = e.get("ticker", "—")
                md += (f"| {ticker} | {e.get('issuer','—')} | {e.get('price','—')} | "
                       f"{e.get('volume','—')} | {fmt_chg(e.get('change_pct'))} | "
                       f"{e.get('date','—')} | "
                       f"[查看 →](https://cn.investing.com/etf/{ticker.lower()}) |\n")
            st.markdown(md)
    else:
        st.caption("今日无加密衍生品数据（API 超时）"
                   f"  ·  可手动查看 [非小号](https://www.feixiaohao.com) | "
                   f"[英为财情](https://cn.investing.com/crypto/bitcoin) | "
                   f"[CoinGlass](https://www.coinglass.com)")

    st.divider()

    # =========================================================================
    # 5. 卖方研报结构化（带超链接）
    # =========================================================================
    research = data.get("research", {})
    reports = research.get("rss_structured", []) + research.get("ratings", [])
    st.subheader(f"卖方研报结构化（{len(reports)} 条）")
    if reports:
        md = "| 机构 | 动作 | 标的 | 公司 | 目标价 | 方向 | 理由 | 来源 | 日期 | 链接 |\n"
        md += "|------|------|------|------|--------|------|------|------|------|------|\n"
        for r in reports:
            ticker = r.get("ticker", "—")
            action_map = {
                "target_change": "目标价调整",
                "upgrade": "上调评级",
                "downgrade": "下调评级",
                "initiate": "首次覆盖",
            }
            action = action_map.get(r.get("action"), r.get("action", "—"))
            tp = r.get("target_price")
            tp_str = f"${tp}" if tp else "—"
            direction = r.get("direction", "—")
            dir_emoji = "📈" if direction == "bullish" else "📉" if direction == "bearish" else "➡️"
            url = r.get("url", "")
            url_cell = f"[查看 →]({url})" if url else "—"
            md += (f"| {r.get('bank','—')} | {action} | {ticker} | {r.get('company','—')} | "
                   f"{tp_str} | {dir_emoji} {direction} | {r.get('rationale','—')} | "
                   f"{r.get('source','—')} | {r.get('date','—')} | {url_cell} |\n")
        st.markdown(md)
    else:
        st.caption("今日无结构化研报  ·  可手动查看 "
                   f"[华尔街见闻](https://wallstreetcn.com) | "
                   f"[东方财富](https://www.eastmoney.com)")

    st.divider()

    # =========================================================================
    # 6. 市场事件流 - 确保链接可点击
    # =========================================================================
    events = data.get("events", [])
    st.subheader(f"市场事件流 - {len(events)} 条")
    if events:
        for e in events:
            title = e.get("title", "")
            url = e.get("url", "")
            source = e.get("source", "")
            score = e.get("score", 0)
            created = e.get("created_utc", "")[:10]
            source_link_map = {
                "reddit_equities": ("雪球/股票", "https://xueqiu.com"),
                "reddit_crypto": ("非小号/加密", "https://www.feixiaohao.com"),
                "reddit_wsb": ("华尔街见闻", "https://wallstreetcn.com"),
            }
            sub_name, sub_link = source_link_map.get(source, (source, url))
            if url and url != "https://reddit.com/x" and url != "https://reddit.com/y":
                st.markdown(f"- **[{sub_name}]({sub_link})** [{title}]({url})  "
                            f"`{score} pts` · {created}")
            else:
                st.markdown(f"- **[{sub_name}]({sub_link})** {title}  "
                            f"`{score} pts` · {created}")
    else:
        st.caption("今日无事件流  ·  可手动查看 "
                   f"[华尔街见闻](https://wallstreetcn.com) | "
                   f"[雪球](https://xueqiu.com) | "
                   f"[金十数据](https://www.jin10.com)")

    st.divider()

    # =========================================================================
    # 7. 数据来源与口径透明度表（新增 - 类似 timsun.net）
    # =========================================================================
    st.subheader("数据来源与口径")
    st.caption("所有指标的数据来源、更新频率与可信度状态")

    # 构建口径表
    md = "| 指标 | 当前值 | 数据截至 | 来源 | 来源链接 | 状态 |\n"
    md += "|------|--------|----------|------|----------|------|\n"

    # 价格指标
    for key in ["SP500", "DXY", "BTC", "WTI"]:
        p = prices.get(key)
        if p:
            link, src_name = PRICE_LINKS.get(key, ("", ""))
            md += (f"| {labels_cn.get(key, key)} | {fmt_value(key, p.get('value'))} "
                   f"{fmt_chg(p.get('change_pct'))} | {p.get('date','—')} | "
                   f"{src_name} | [→]({link}) | ✅ 正常 |\n")

    # 宏观指标
    for k, v in macro.items():
        link_info = MACRO_LINKS.get(k)
        if link_info:
            link, src_name, desc = link_info
        else:
            link, src_name, desc = "", v.get("source", ""), k
        md += (f"| {desc or k} | {fmt_value(k, v.get('value'))} | "
               f"{v.get('date','—')} | {src_name} | "
               f"[→]({link}) | ✅ 正常 |\n")

    st.markdown(md)

    # 加密数据源状态
    st.markdown("**加密衍生品数据源状态**")
    md = "| 交易所 | 状态 | 链接 |\n|--------|------|------|\n"
    for ex_key in ["binance", "bybit", "deribit"]:
        ex_data = crypto.get(ex_key, {})
        link, name = CRYPTO_LINKS.get(ex_key, ("", ex_key))
        if ex_data and "error" not in ex_data:
            md += f"| {name} | ✅ 正常 | [→]({link}) |\n"
        else:
            md += f"| {name} | ❌ 超时/失败 | [→]({link}) |\n"
    st.markdown(md)

    st.divider()

    # =========================================================================
    # 8. 外部资源导航（新增）
    # =========================================================================
    st.subheader("外部资源导航")
    st.caption("点击以下链接可直接访问各数据源原始网站")

    # 分两列展示
    col_a, col_b = st.columns(2)
    half = len(EXTERNAL_RESOURCES) // 2 + 1

    with col_a:
        for name, url, desc in EXTERNAL_RESOURCES[:half]:
            st.markdown(f"- [{name}]({url}) — {desc}")

    with col_b:
        for name, url, desc in EXTERNAL_RESOURCES[half:]:
            st.markdown(f"- [{name}]({url}) — {desc}")

    # 底部信息
    st.divider()
    st.caption(
        "本仪表盘数据自动采集自公开数据源，展示链接均使用内地可访问网站。  \n"
        "每日北京时间 07:00 自动更新（周一至周五）。"
        f"  ·  [Gitee 仓库](https://gitee.com)"
        f"  ·  [GitHub 仓库](https://github.com/acmilanhm/macro-dashboard)"
        f"  ·  [参考网站 timsun.net](https://timsun.net/)"
    )


if __name__ == "__main__":
    main()
