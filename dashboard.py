"""
极简可视化面板：读取 daily_macro.json 并展示（含 AI 研判 + 卖方研报）
运行:  streamlit run dashboard.py
"""
import json
import os

import streamlit as st

DATA_FILE = "daily_macro.json"


def load_data():
    if not os.path.exists(DATA_FILE):
        return None
    with open(DATA_FILE, encoding="utf-8") as f:
        return json.load(f)


def main():
    st.set_page_config(page_title="每日宏观仪表盘", layout="wide")
    st.title("每日宏观跨资产仪表盘")

    data = load_data()
    if not data:
        st.warning("未找到 daily_macro.json，请先运行 macro_collector.py")
        return

    st.caption(f"采集时间：{data.get('collected_at', '')}  ·  交易日：{data.get('trade_date', '')}")

    # ---- AI 研判横幅 ----
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

    # ---- 价格卡片 ----
    st.subheader("核心资产价格")
    cols = st.columns(4)
    labels = {"SP500": "标普500", "DXY": "美元指数", "BTC": "比特币", "WTI": "WTI原油"}
    for i, key in enumerate(["SP500", "DXY", "BTC", "WTI"]):
        p = data["prices"].get(key)
        if p:
            chg = p["change_pct"]
            cols[i].metric(labels[key], p["value"], f"{chg:+.2f}%")

    # ---- 宏观指标表 ----
    st.subheader("宏观与流动性指标")
    rows = []
    for k, v in data["macro"].items():
        rows.append({
            "指标": k,
            "数值": v.get("value"),
            "日期": v.get("date"),
            "来源": v.get("source"),
        })
    st.dataframe(rows, width="stretch")

    # ---- 加密衍生品雷达 ----
    crypto = data.get("crypto", {})
    mq = crypto.get("market_quality", {})
    st.subheader("加密衍生品雷达")
    if mq:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("资金费率(8h)", f"{mq.get('funding_rate_8h','?')}",
                  mq.get("funding_heat", ""))
        c1.caption(mq.get("leverage_direction", ""))
        c2.metric("DVOL", mq.get("dvol", "?"), mq.get("dvol_regime", ""))
        c3.metric("Put/Call OI", mq.get("put_call_ratio", "?"),
                  mq.get("options_positioning", ""))
        bn = crypto.get("binance", {})
        c4.metric("Binance OI", bn.get("open_interest", "?"))
        st.info(f"**24h：** {mq.get('verdict_24h','')}  \n"
                f"**1-7d：** {mq.get('verdict_1_7d','')}")
        etfs = crypto.get("etfs", [])
        if etfs:
            st.caption("BTC 现货 ETF")
            st.dataframe([{
                "代码": e.get("ticker"), "发行商": e.get("issuer"),
                "价格": e.get("price"), "成交": e.get("volume"),
                "涨跌%": e.get("change_pct"), "日期": e.get("date"),
            } for e in etfs], width="stretch")
    else:
        st.caption("今日无加密衍生品数据")

    # ---- 卖方研报 ----
    research = data.get("research", {})
    reports = research.get("rss_structured", []) + research.get("ratings", [])
    st.subheader(f"卖方研报结构化（{len(reports)} 条）")
    if reports:
        rrows = []
        for r in reports:
            rrows.append({
                "机构": r.get("bank"),
                "动作": r.get("action"),
                "标的": r.get("ticker"),
                "目标价": r.get("target_price"),
                "方向": r.get("direction"),
                "理由": r.get("rationale"),
                "来源": r.get("source"),
            })
        st.dataframe(rrows, width="stretch")
    else:
        st.caption("今日无结构化研报")

    # ---- 事件流 ----
    st.subheader("市场事件流 (Reddit)")
    for e in data["events"]:
        st.markdown(f"- **[{e['source']}]** [{e['title']}]({e['url']})  "
                    f"`{e.get('score', 0)} pts`")


if __name__ == "__main__":
    main()
