"""
每日宏观跨资产仪表盘 — AI 产业链增强版
参考 timsun.net 三引擎结构 | 时尚渐变 + 毛玻璃 + 30日趋势
运行: streamlit run dashboard.py
"""
import json
import os
import html as html_mod
from pathlib import Path
from datetime import datetime

import streamlit as st

DATA_FILE = "daily_macro.json"
HISTORY_DIR = Path("data/history")

# ===== 数据源超链接映射（全部内地可访问）=====
PRICE_LINKS = {
    "SP500":  ("https://cn.investing.com/indices/us-spx-500", "英为财情"),
    "DXY":    ("https://cn.investing.com/indices/usdollar-index", "英为财情"),
    "WTI":    ("https://cn.investing.com/commodities/crude-oil", "英为财情"),
    "NASDAQ": ("https://cn.investing.com/indices/nq-100", "英为财情"),
}
AI_STOCK_LINKS = {
    "NVDA":  "https://cn.investing.com/equities/nvidia-corp",
    "AVGO":  "https://cn.investing.com/equities/broadcom",
    "TSM":   "https://cn.investing.com/equities/taiwan-semi",
    "MSFT":  "https://cn.investing.com/equities/microsoft",
    "GOOGL": "https://cn.investing.com/equities/google-inc",
    "META":  "https://cn.investing.com/equities/facebook",
    "AMZN":  "https://cn.investing.com/equities/amazon",
    "AAPL":  "https://cn.investing.com/equities/apple",
    "PLTR":  "https://cn.investing.com/equities/palantir-tech",
    "CRM":   "https://cn.investing.com/equities/salesforce",
    "NOW":   "https://cn.investing.com/equities/servicenow",
    "AMD":   "https://cn.investing.com/equities/amd",
    "ASML":  "https://cn.investing.com/equities/asml-holdings-nv",
}
AI_ETF_LINKS = {
    "SMH":  "https://cn.investing.com/etf/vaneck-vector-semiconductor-etf",
    "BOTZ": "https://cn.investing.com/etf/global-x-robotics-artificial-intelligence-etf",
    "IGV":  "https://cn.investing.com/etf/ishares-north-american-tech-software-etf",
    "SOXX": "https://cn.investing.com/etf/ishares-semiconductor-etf",
}
MACRO_LINKS = {
    "VIX_10Y":       ("https://fred.stlouisfed.org/series/DGS10", "FRED DGS10", "10Y国债收益率"),
    "VIX":           ("https://fred.stlouisfed.org/series/VIXCLS", "FRED VIXCLS", "VIX恐慌指数"),
    "HY_OAS":        ("https://fred.stlouisfed.org/series/BAMLH0A0HYM2", "ICE BofA/FRED", "高收益债OAS利差"),
    "FED_ASSETS":    ("https://fred.stlouisfed.org/series/WALCL", "FRED WALCL", "美联储总资产"),
    "TGA":           ("https://fred.stlouisfed.org/series/WTREGEN", "FRED WTREGEN", "财政部一般账户"),
    "RRP":           ("https://fred.stlouisfed.org/series/WLRRAL", "FRED WLRRAL", "隔夜逆回购余额"),
    "NET_LIQUIDITY": ("https://fred.stlouisfed.org/series/WALCL", "计算: WALCL-RRP-TGA", "净流动性"),
}
EXTERNAL_RESOURCES = [
    ("英为财情", "https://cn.investing.com", "全球指数/外汇/商品行情"),
    ("东方财富网", "https://www.eastmoney.com", "A股/美股综合财经门户"),
    ("新浪财经", "https://finance.sina.com.cn", "美股/A股/期货行情"),
    ("雪球", "https://xueqiu.com", "投资社区/美股讨论"),
    ("华尔街见闻", "https://wallstreetcn.com", "全球宏观资讯快讯"),
    ("金十数据", "https://www.jin10.com", "财经日历/实时快讯"),
    ("FRED 经济数据", "https://fred.stlouisfed.org", "美联储经济数据库"),
    ("同花顺", "https://www.10jqka.com.cn", "A股/美股行情"),
    ("机器之心", "https://www.jiqizhixin.com", "AI行业前沿资讯"),
    ("timsun.net", "https://timsun.net/", "参考网站"),
]
PRICE_LABELS = {"SP500": "标普500", "DXY": "美元指数", "WTI": "WTI原油", "NASDAQ": "纳斯达克100"}
AI_STOCK_NAMES = {
    "NVDA": "英伟达", "AVGO": "博通", "TSM": "台积电", "MSFT": "微软",
    "GOOGL": "谷歌", "META": "Meta", "AMZN": "亚马逊", "AAPL": "苹果",
    "PLTR": "Palantir", "CRM": "Salesforce", "NOW": "ServiceNow", "AMD": "AMD",
    "ASML": "阿斯麦",
}
AI_ETF_NAMES = {"SMH": "半导体ETF", "BOTZ": "机器人AI ETF", "IGV": "软件ETF", "SOXX": "费城半导体ETF"}
SUPPLY_CHAIN_LABELS = {"chips": "芯片层", "cloud": "云基础设施", "models": "大模型", "applications": "应用层"}


# ===== CSS 注入 — 时尚渐变 + 毛玻璃 + 微动画 =====
def inject_css():
    st.markdown("""
    <style>
    /* 动画渐变背景 */
    @keyframes gradientShift {
        0% { background-position: 0% 50%; }
        50% { background-position: 100% 50%; }
        100% { background-position: 0% 50%; }
    }
    .stApp {
        background: linear-gradient(-45deg, #0a0e27, #1a1040, #0d1b2a, #16213e, #1a0a2e) !important;
        background-size: 400% 400% !important;
        animation: gradientShift 20s ease infinite;
    }
    section.main > div { background: transparent !important; }
    #MainMenu, footer, header[data-testid="stHeader"] { display: none !important; }

    /* 全局字体 */
    .stApp, p, span, div, td, th {
        font-family: 'Segoe UI','PingFang SC','Microsoft YaHei',sans-serif !important;
    }
    .stMarkdown p, .stMarkdown li { color: #c8c8e0 !important; }
    .stMarkdown h1, .stMarkdown h2, .stMarkdown h3 { color: #e8e8ff !important; }

    /* 主标题渐变 */
    .main-title {
        background: linear-gradient(135deg, #667eea 0%, #f093fb 50%, #4facfe 100%);
        -webkit-background-clip: text; -webkit-text-fill-color: transparent;
        background-clip: text;
        font-size: 2.6rem; font-weight: 800; margin: 0;
        letter-spacing: 2px;
    }
    .subtitle { color: #9999bb; font-size: 0.88rem; margin-top: 6px; }

    /* 实时指示器 */
    .live-dot {
        display: inline-block; width: 8px; height: 8px;
        background: #51cf66; border-radius: 50%; margin-right: 6px;
        box-shadow: 0 0 8px #51cf66;
        animation: pulse 2s infinite;
    }
    @keyframes pulse {
        0%, 100% { opacity: 1; transform: scale(1); }
        50% { opacity: 0.5; transform: scale(1.3); }
    }

    /* 毛玻璃卡片 */
    .glass-card {
        background: rgba(255,255,255,0.05);
        backdrop-filter: blur(20px) saturate(180%);
        -webkit-backdrop-filter: blur(20px) saturate(180%);
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 20px;
        padding: 0; margin: 8px 0; overflow: hidden;
        box-shadow: 0 8px 32px rgba(0,0,0,0.2), inset 0 1px 0 rgba(255,255,255,0.06);
        transition: all 0.4s cubic-bezier(0.16, 1, 0.3, 1);
    }
    .glass-card:hover {
        background: rgba(255,255,255,0.08);
        border-color: rgba(255,255,255,0.15);
        transform: translateY(-3px);
        box-shadow: 0 16px 48px rgba(0,0,0,0.3), 0 0 24px rgba(102,126,234,0.12);
    }

    /* 引擎头部 — 三种独特渐变 */
    .engine-header {
        padding: 14px 18px; font-size: 1.05rem; font-weight: 700;
        color: white; letter-spacing: 1px;
    }
    .engine-1 .engine-header { background: linear-gradient(135deg, #667eea, #764ba2); }
    .engine-2 .engine-header { background: linear-gradient(135deg, #f093fb, #f5576c); }
    .engine-3 .engine-header { background: linear-gradient(135deg, #4facfe, #00f2fe); }
    .engine-content { padding: 16px 18px; }
    .engine-sub {
        color: #8888aa; font-size: 0.76rem; margin: 10px 0 4px 0;
        font-weight: 600; text-transform: uppercase; letter-spacing: 1px;
    }

    /* AI 研判横幅 */
    .judgment-banner {
        background: linear-gradient(135deg, rgba(102,126,234,0.12), rgba(240,147,251,0.08), rgba(79,172,254,0.10));
        backdrop-filter: blur(20px) saturate(180%);
        border: 1px solid rgba(102,126,234,0.25);
        border-radius: 20px; padding: 24px 28px; margin: 12px 0;
        box-shadow: 0 8px 32px rgba(0,0,0,0.2);
    }

    /* 紧凑表格（引擎内） */
    .ct { width: 100%; border-collapse: collapse; font-size: 0.80rem; margin: 4px 0; }
    .ct th {
        background: rgba(102,126,234,0.12); color: #b0b0d0;
        padding: 6px 8px; text-align: left; font-weight: 600;
        border-bottom: 1px solid rgba(255,255,255,0.06);
    }
    .ct td { padding: 5px 8px; border-bottom: 1px solid rgba(255,255,255,0.03); color: #c0c0d8; }
    .ct tr:hover td { background: rgba(255,255,255,0.03); }
    .ct a { color: #6ea8fe; text-decoration: none; }
    .ct a:hover { text-decoration: underline; }

    /* 宽表格 */
    .dt { width: 100%; border-collapse: collapse; font-size: 0.88rem; margin: 8px 0; }
    .dt th {
        background: rgba(102,126,234,0.15); color: #c0c0e0;
        padding: 10px 12px; text-align: left; font-weight: 600;
        border-bottom: 1px solid rgba(255,255,255,0.08);
    }
    .dt td { padding: 9px 12px; border-bottom: 1px solid rgba(255,255,255,0.04); color: #d0d0e8; }
    .dt tr:hover td { background: rgba(255,255,255,0.03); }
    .dt a { color: #6ea8fe; text-decoration: none; }
    .dt a:hover { text-decoration: underline; }

    /* 徽章 */
    .badge {
        display: inline-block; background: rgba(255,255,255,0.08);
        padding: 3px 10px; border-radius: 16px; margin: 3px;
        font-size: 0.80rem; color: #d0d0e8;
        border: 1px solid rgba(255,255,255,0.06);
    }

    /* 产业链节点徽章 */
    .supply-badge {
        display: inline-flex; flex-direction: column;
        background: rgba(255,255,255,0.05);
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 10px; padding: 6px 10px; margin: 2px;
        font-size: 0.76rem; transition: all 0.3s ease;
    }
    .supply-badge:hover {
        background: rgba(255,255,255,0.1);
        transform: translateY(-1px);
        border-color: rgba(255,255,255,0.15);
    }

    /* 趋势卡片 */
    .trend-card {
        background: rgba(255,255,255,0.04);
        backdrop-filter: blur(12px);
        border: 1px solid rgba(255,255,255,0.06);
        border-radius: 16px; padding: 16px 18px; margin: 6px 0;
        transition: all 0.3s ease;
    }
    .trend-card:hover {
        background: rgba(255,255,255,0.07);
        border-color: rgba(255,255,255,0.12);
        transform: translateY(-2px);
    }
    .trend-label { color: #8888aa; font-size: 0.78rem; font-weight: 600; }
    .trend-value { color: #e8e8ff; font-size: 1.3rem; font-weight: 700; margin: 2px 0; }
    .trend-range { color: #666688; font-size: 0.72rem; }

    /* 资源卡片 */
    .res-card {
        display: inline-block; background: rgba(255,255,255,0.04);
        border: 1px solid rgba(255,255,255,0.08); border-radius: 12px;
        padding: 10px 14px; margin: 5px; transition: all 0.3s ease; min-width: 180px;
    }
    .res-card:hover {
        background: rgba(102,126,234,0.12); border-color: rgba(102,126,234,0.3);
        transform: translateY(-2px);
        box-shadow: 0 4px 16px rgba(102,126,234,0.1);
    }
    .res-card a { color: #e0e0ff; text-decoration: none; font-weight: 600; }
    .res-card a:hover { color: #6ea8fe; }

    /* 事件卡片 */
    .event-item {
        background: rgba(255,255,255,0.03); border-left: 3px solid #667eea;
        border-radius: 8px; padding: 10px 14px; margin: 6px 0; transition: all 0.3s ease;
    }
    .event-item:hover { background: rgba(255,255,255,0.06); border-left-color: #f5576c; }
    .event-item a { color: #6ea8fe; text-decoration: none; }
    .event-item a:hover { text-decoration: underline; }

    /* 区块标题 */
    .section-title {
        background: linear-gradient(135deg, #667eea, #f093fb);
        -webkit-background-clip: text; -webkit-text-fill-color: transparent;
        background-clip: text;
        font-size: 1.35rem; font-weight: 700; margin: 28px 0 10px 0;
        letter-spacing: 1px;
    }

    /* 信号条 */
    .signal-bar {
        height: 6px; border-radius: 3px; background: rgba(255,255,255,0.08);
        margin: 4px 0; overflow: hidden;
    }
    .signal-fill {
        height: 100%; border-radius: 3px;
        transition: width 0.6s cubic-bezier(0.16, 1, 0.3, 1);
    }
    </style>
    """, unsafe_allow_html=True)


# ===== 辅助函数 =====
def load_data():
    if not os.path.exists(DATA_FILE):
        return None
    with open(DATA_FILE, encoding="utf-8") as f:
        return json.load(f)


def load_history():
    """加载 data/history/ 目录下所有历史数据（最多30天）"""
    if not HISTORY_DIR.exists():
        return []
    files = sorted(HISTORY_DIR.glob("*.json"))
    history = []
    for f in files:
        try:
            with open(f, encoding="utf-8") as fh:
                history.append(json.load(fh))
        except Exception:
            pass
    return history


def esc(text):
    if text is None:
        return ""
    return html_mod.escape(str(text))


def fmt_chg(val):
    """涨跌幅 → 带颜色 HTML（涨红跌绿）"""
    if val is None:
        return "<span style='color:#888'>—</span>"
    if val > 0:
        return f"<span style='color:#ff6b6b;font-weight:600'>▲ +{val:.2f}%</span>"
    if val < 0:
        return f"<span style='color:#51cf66;font-weight:600'>▼ {val:.2f}%</span>"
    return f"<span style='color:#aaa'>● {val:.2f}%</span>"


def fmt_val(key, val):
    if val is None:
        return "—"
    if isinstance(val, str):
        return esc(val)
    if not isinstance(val, (int, float)):
        return esc(str(val))
    if key in ("SP500", "NASDAQ"):
        return f"{val:,.2f}"
    if key == "WTI":
        return f"${val:.2f}"
    if key in ("VIX", "DXY"):
        return f"{val:.2f}"
    if key in ("VIX_10Y", "HY_OAS"):
        return f"{val:.2f}%"
    if key in ("FED_ASSETS", "TGA", "RRP", "NET_LIQUIDITY"):
        return f"{val/1000:.2f}万亿" if val > 1000 else f"{val:.1f}亿"
    return f"${val:.2f}"


def build_table(headers, rows, cls="ct"):
    t = f"<table class='{cls}'><thead><tr>"
    for h in headers:
        t += f"<th>{h}</th>"
    t += "</tr></thead><tbody>"
    for row in rows:
        t += "<tr>"
        for cell in row:
            t += f"<td>{cell}</td>"
        t += "</tr>"
    t += "</tbody></table>"
    return t


def badge(text, color="#aaa"):
    return f"<span class='badge' style='background:{color}1a;color:{color};border-color:{color}33'>{esc(text)}</span>"


def make_sparkline(values, color="#4facfe", width=260, height=50, chart_id="spark"):
    """生成 SVG 迷你折线图，带渐变填充和发光端点"""
    valid = [(i, v) for i, v in enumerate(values) if v is not None]
    if len(valid) < 2:
        return "<span style='color:#666;font-size:0.78rem'>数据不足</span>"
    n = len(values)
    min_v = min(v for _, v in valid)
    max_v = max(v for _, v in valid)
    rng = max_v - min_v if max_v != min_v else 1
    pts = []
    for i, v in valid:
        x = (i / (n - 1)) * width if n > 1 else 0
        y = height - 4 - ((v - min_v) / rng) * (height - 8)
        pts.append((x, y))
    line_path = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    fill_path = f"M {pts[0][0]:.1f},{height} " + \
                " ".join(f"L {x:.1f},{y:.1f}" for x, y in pts) + \
                f" L {pts[-1][0]:.1f},{height} Z"
    lx, ly = pts[-1]
    gid = f"grad-{chart_id}"
    return f"""
    <svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg" style="overflow:visible">
        <defs><linearGradient id="{gid}" x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stop-color="{color}" stop-opacity="0.35"/>
            <stop offset="100%" stop-color="{color}" stop-opacity="0"/>
        </linearGradient></defs>
        <path d="{fill_path}" fill="url(#{gid})"/>
        <polyline points="{line_path}" fill="none" stroke="{color}" stroke-width="2"
                  stroke-linejoin="round" stroke-linecap="round"/>
        <circle cx="{lx:.1f}" cy="{ly:.1f}" r="3.5" fill="{color}"
                style="filter:drop-shadow(0 0 6px {color})"/>
    </svg>"""


def render_supply_node(title, items):
    """渲染产业链节点为信息徽章"""
    h = f"<div style='margin:8px 0'>"
    h += f"<div style='color:#8888aa;font-size:0.74rem;margin-bottom:4px;font-weight:600'>{esc(title)}</div>"
    if not items:
        h += "<span style='color:#666;font-size:0.78rem'>暂无数据</span>"
    else:
        h += "<div style='display:flex;flex-wrap:wrap;gap:3px'>"
        for item in items[:8]:
            if isinstance(item, dict):
                name = item.get("name", "")
                chg = item.get("change_pct")
                available = item.get("data_available", False)
                if available and chg is not None:
                    cc = "#ff6b6b" if chg > 0 else "#51cf66" if chg < 0 else "#aaa"
                    ct = f"▲+{chg:.1f}%" if chg > 0 else f"▼{chg:.1f}%" if chg < 0 else "●0%"
                    h += f"<span class='supply-badge'><b>{esc(name)}</b><span style='color:{cc};font-size:0.72rem'>{ct}</span></span>"
                else:
                    note = item.get("note", "")
                    h += f"<span class='supply-badge' style='opacity:0.5'><b>{esc(name)}</b><span style='color:#666;font-size:0.70rem'>{esc(note)}</span></span>"
            else:
                h += f"<span class='supply-badge'>{esc(str(item))}</span>"
        h += "</div>"
    return h + "</div>"


def stock_list(items):
    if not items:
        return "<span style='color:#666;font-size:0.78rem'>暂无数据</span>"
    h = ""
    for item in items[:6]:
        if isinstance(item, dict):
            t = item.get("ticker", item.get("name", "?"))
            c = item.get("change_pct")
            h += f"<span class='badge'>{esc(t)} {fmt_chg(c) if c is not None else ''}</span>"
        else:
            h += f"<span class='badge'>{esc(str(item))}</span>"
    return h


def signal_bar(label, value, max_val=100, color="#4facfe"):
    """生成信号强度条"""
    pct = min(abs(value) / max_val * 100, 100) if max_val else 0
    return f"""
    <div style='margin:6px 0'>
        <span style='color:#9999bb;font-size:0.76rem'>{esc(label)}</span>
        <div class='signal-bar'><div class='signal-fill' style='width:{pct:.0f}%;background:{color}'></div></div>
    </div>"""


# ===== 页面区块渲染 =====
def render_header(data):
    collected = data.get("collected_at", "")[:19].replace("T", " ")
    trade_date = data.get("trade_date", "")
    st.markdown(f"""
    <div style='text-align:center;padding:24px 0 12px 0'>
        <h1 class='main-title'>每日宏观跨资产仪表盘</h1>
        <div class='subtitle'>
            <span class='live-dot'></span>
            采集时间：{esc(collected)} UTC · 交易日：{esc(trade_date)}
        </div>
    </div>
    """, unsafe_allow_html=True)


def render_judgment(data):
    j = data.get("judgment")
    if not j:
        st.markdown(
            "<div class='judgment-banner' style='text-align:center;color:#9999bb'>"
            "未生成 AI 研判（需配置 LLM_API_KEY）</div>",
            unsafe_allow_html=True,
        )
        return
    conf = j.get("confidence", "")
    conf_color = {"低": "#ff6b6b", "中": "#ffd43b", "高": "#51cf66"}.get(conf, "#aaa")
    catalysts = j.get("catalysts", [])
    cat_html = "".join(badge(c, "#4facfe") for c in catalysts)
    st.markdown(f"""
    <div class='judgment-banner'>
        <h3 style='color:#e8e8ff;margin:0 0 12px 0'>{esc(j.get('headline', ''))}</h3>
        <div style='display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px'>
            <span class='badge' style='background:{conf_color}1a;color:{conf_color};border-color:{conf_color}33'>置信度：{esc(conf)}</span>
            <span class='badge'>时间窗口：{esc(j.get('timeframe', ''))}</span>
        </div>
        <p style='color:#c0c0d8;margin:6px 0'><b style='color:#8888aa'>为什么：</b>{esc(j.get('why', ''))}</p>
        <p style='color:#c0c0d8;margin:6px 0'><b style='color:#8888aa'>什么情况下判断会错：</b>{esc(j.get('risk', ''))}</p>
        <div style='margin-top:10px'><b style='color:#8888aa;font-size:0.82rem'>催化剂：</b>{cat_html}</div>
    </div>
    """, unsafe_allow_html=True)


def render_engines(data):
    """三个研究引擎板块 — 并列毛玻璃卡片"""
    prices = data.get("prices", {})
    macro = data.get("macro", {})
    ai_stocks = data.get("ai_stocks", {})
    ai_etfs = data.get("ai_etfs", {})
    ai_radar = data.get("ai_radar", {})

    col1, col2, col3 = st.columns(3)

    # === 引擎 1: 宏观主线判断 ===
    with col1:
        price_rows = []
        for key in ["SP500", "NASDAQ", "DXY", "WTI"]:
            p = prices.get(key)
            link, _ = PRICE_LINKS.get(key, ("", ""))
            if p:
                name_cell = f"<a href='{esc(link)}' target='_blank'>{PRICE_LABELS.get(key, key)}</a>"
                price_rows.append([name_cell, fmt_val(key, p.get("value")), fmt_chg(p.get("change_pct"))])
            else:
                price_rows.append([PRICE_LABELS.get(key, key), "—", "<span style='color:#888'>—</span>"])
        price_tbl = build_table(["资产", "数值", "涨跌"], price_rows)

        macro_rows = []
        for k, v in macro.items():
            link, src, desc = MACRO_LINKS.get(k, ("", v.get("source", ""), k))
            src_cell = f"<a href='{esc(link)}' target='_blank'>{esc(src)}</a>" if link else esc(v.get("source", ""))
            macro_rows.append([esc(desc or k), fmt_val(k, v.get("value")), src_cell])
        macro_tbl = build_table(["指标", "数值", "来源"], macro_rows) if macro_rows else "<span style='color:#666;font-size:0.8rem'>暂无数据</span>"

        st.markdown(f"""
        <div class='glass-card engine-1'>
            <div class='engine-header'>引擎 1 · 宏观主线判断</div>
            <div class='engine-content'>
                <div class='engine-sub'>核心资产价格</div>
                {price_tbl}
                <div class='engine-sub'>宏观与流动性指标</div>
                {macro_tbl}
            </div>
        </div>
        """, unsafe_allow_html=True)

    # === 引擎 2: AI 产业链研究 ===
    with col2:
        sc = ai_radar.get("supply_chain", {})
        sc_html = "".join(render_supply_node(SUPPLY_CHAIN_LABELS.get(k, k), v) for k, v in sc.items()) if sc else "<span style='color:#666;font-size:0.8rem'>暂无产业链数据</span>"

        nf = ai_radar.get("news_flow", [])[:4]
        nf_html = ""
        for n in nf:
            title = n.get("title", "")
            url = n.get("url", "")
            pub = n.get("published", "")[:10]
            link_html = f"<a href='{esc(url)}' target='_blank'>{esc(title)}</a>" if url else esc(title)
            nf_html += f"<div class='event-item'>{link_html}<br><span style='color:#666;font-size:0.74rem'>{esc(pub)}</span></div>"
        if not nf:
            nf_html = "<span style='color:#666;font-size:0.8rem'>暂无新闻流</span>"

        imp = ai_radar.get("investment_implications", {})
        if imp:
            health = imp.get("supply_chain_health", "")
            flow = imp.get("capital_flow", "")
            h_color = {"强": "#51cf66", "中": "#ffd43b", "弱": "#ff6b6b"}.get(health, "#aaa")
            f_color = {"流入": "#51cf66", "流出": "#ff6b6b", "均衡": "#ffd43b"}.get(flow, "#aaa")
            imp_html = f"<div style='margin:6px 0'>{badge('健康度: ' + health, h_color)}{badge('资金: ' + flow, f_color)}</div>"
            if imp.get("verdict_24h"):
                imp_html += f"<p style='color:#c0c0d8;font-size:0.80rem;margin:4px 0'><b style='color:#8888aa'>24h：</b>{esc(imp['verdict_24h'])}</p>"
            if imp.get("verdict_1_7d"):
                imp_html += f"<p style='color:#c0c0d8;font-size:0.80rem;margin:4px 0'><b style='color:#8888aa'>1-7d：</b>{esc(imp['verdict_1_7d'])}</p>"
        else:
            imp_html = "<span style='color:#666;font-size:0.8rem'>暂无投资含义判断</span>"

        st.markdown(f"""
        <div class='glass-card engine-2'>
            <div class='engine-header'>引擎 2 · AI 产业链研究</div>
            <div class='engine-content'>
                <div class='engine-sub'>产业链节点</div>
                {sc_html}
                <div class='engine-sub'>AI 新闻流</div>
                {nf_html}
                <div class='engine-sub'>投资含义</div>
                {imp_html}
            </div>
        </div>
        """, unsafe_allow_html=True)

    # === 引擎 3: AI 资产追踪 ===
    with col3:
        # AI 核心股票
        stock_rows = []
        for ticker in AI_STOCK_LINKS:
            s = ai_stocks.get(ticker)
            if s:
                name = s.get("name", AI_STOCK_NAMES.get(ticker, ticker))
                link = AI_STOCK_LINKS[ticker]
                stock_rows.append([
                    f"<a href='{link}' target='_blank'>{esc(ticker)}</a>",
                    esc(name), fmt_val(ticker, s.get("value")), fmt_chg(s.get("change_pct")),
                ])
        stock_tbl = build_table(["代码", "名称", "价格", "涨跌"], stock_rows) if stock_rows else "<span style='color:#666;font-size:0.8rem'>暂无数据</span>"

        # AI ETF
        etf_rows = []
        for ticker in AI_ETF_LINKS:
            e = ai_etfs.get(ticker)
            if e:
                name = e.get("name", AI_ETF_NAMES.get(ticker, ticker))
                link = AI_ETF_LINKS[ticker]
                etf_rows.append([
                    f"<a href='{link}' target='_blank'>{esc(ticker)}</a>",
                    esc(name), fmt_val(ticker, e.get("value")), fmt_chg(e.get("change_pct")),
                ])
        etf_tbl = build_table(["ETF", "名称", "价格", "涨跌"], etf_rows) if etf_rows else "<span style='color:#666;font-size:0.8rem'>暂无数据</span>"

        # 财报信号
        es = ai_radar.get("earnings_signals", {})
        median = es.get("median_change_pct")
        median_html = f"<div style='margin:6px 0'><span class='badge'>中位数涨跌</span> {fmt_chg(median) if median is not None else '—'}</div>" if median is not None else ""
        up_ratio = es.get("up_ratio", 0)
        up_count = es.get("up_count", 0)
        down_count = es.get("down_count", 0)
        total = es.get("total", 0)
        ratio_html = f"<div style='margin:4px 0'><span style='color:#8888aa;font-size:0.76rem'>涨跌比：{up_count}涨 / {down_count}跌（共{total}只）</span></div>" if total else ""
        bar_html = signal_bar("多头强度", up_ratio * 100 if up_ratio else 0, 100, "#ff6b6b") if total else ""

        leaders_html = f"<div style='margin:6px 0'><span style='color:#8888aa;font-size:0.74rem;font-weight:600'>领涨</span><br>{stock_list(es.get('leaders', []))}</div>"
        laggers_html = f"<div style='margin:6px 0'><span style='color:#8888aa;font-size:0.74rem;font-weight:600'>领跌</span><br>{stock_list(es.get('laggers', []))}</div>"

        st.markdown(f"""
        <div class='glass-card engine-3'>
            <div class='engine-header'>引擎 3 · AI 资产追踪</div>
            <div class='engine-content'>
                <div class='engine-sub'>AI 核心股票</div>
                {stock_tbl}
                <div class='engine-sub'>AI ETF</div>
                {etf_tbl}
                <div class='engine-sub'>财报信号</div>
                {median_html}
                {ratio_html}
                {bar_html}
                {leaders_html}
                {laggers_html}
            </div>
        </div>
        """, unsafe_allow_html=True)


def render_trends(history, data):
    """30日趋势可视化 — SVG 迷你折线图"""
    st.markdown("<div class='section-title'>30 日趋势</div>", unsafe_allow_html=True)
    if not history or len(history) < 2:
        st.markdown(
            "<span style='color:#666688;font-size:0.88rem'>历史数据不足 2 天，趋势图将在数据积累后自动显示</span>",
            unsafe_allow_html=True,
        )
        return

    # 提取时间序列
    dates = []
    sp500_vals = []
    ai_median_vals = []
    vix_vals = []
    net_liq_vals = []

    for entry in sorted(history, key=lambda x: x.get("trade_date", "")):
        d = entry.get("trade_date", "")
        if not d:
            continue
        dates.append(d)
        p = entry.get("prices", {}).get("SP500", {})
        sp500_vals.append(p.get("value") if p else None)

        ai_stocks = entry.get("ai_stocks", {})
        changes = [s.get("change_pct") for s in ai_stocks.values() if s.get("change_pct") is not None]
        if changes:
            import statistics
            ai_median_vals.append(statistics.median(changes))
        else:
            ai_median_vals.append(None)

        v = entry.get("macro", {}).get("VIX", {})
        vix_vals.append(v.get("value") if v else None)

        nl = entry.get("macro", {}).get("NET_LIQUIDITY", {})
        net_liq_vals.append(nl.get("value") if nl else None)

    # 当前值
    cur_sp500 = sp500_vals[-1] if sp500_vals else None
    cur_ai = ai_median_vals[-1] if ai_median_vals else None
    cur_vix = vix_vals[-1] if vix_vals else None
    cur_nl = net_liq_vals[-1] if net_liq_vals else None

    def trend_card(label, cur_val, fmt_fn, series, color, chart_id):
        val_str = fmt_fn(cur_val) if cur_val is not None else "—"
        valid = [v for v in series if v is not None]
        lo = min(valid) if valid else None
        hi = max(valid) if valid else None
        range_str = f"区间: {fmt_fn(lo)} ~ {fmt_fn(hi)}" if valid and lo is not None and hi is not None else ""
        spark = make_sparkline(series, color, 220, 44, chart_id)
        return f"""
        <div class='trend-card'>
            <div class='trend-label'>{esc(label)}</div>
            <div class='trend-value'>{val_str}</div>
            {spark}
            <div class='trend-range'>{range_str} · {len(valid)} 天数据</div>
        </div>"""

    cards = []
    cards.append(trend_card("标普500", cur_sp500, lambda v: f"{v:,.2f}", sp500_vals, "#667eea", "sp500"))
    cards.append(trend_card("AI板块中位数涨跌", cur_ai, lambda v: f"{v:+.2f}%", ai_median_vals, "#f5576c", "aimed"))
    cards.append(trend_card("VIX 恐慌指数", cur_vix, lambda v: f"{v:.2f}", vix_vals, "#ffd43b", "vix"))
    cards.append(trend_card("净流动性（亿）", cur_nl, lambda v: f"{v:,.1f}", net_liq_vals, "#4facfe", "netliq"))

    # 2x2 网格
    row1 = f"<div style='display:flex;gap:8px;flex-wrap:wrap'>{''.join(cards[:2])}</div>"
    row2 = f"<div style='display:flex;gap:8px;flex-wrap:wrap'>{''.join(cards[2:])}</div>"
    st.markdown(row1 + row2, unsafe_allow_html=True)


def render_transparency(data):
    st.markdown("<div class='section-title'>数据来源与口径透明度</div>", unsafe_allow_html=True)
    prices = data.get("prices", {})
    macro = data.get("macro", {})
    rows = []
    for key in ["SP500", "NASDAQ", "DXY", "WTI"]:
        p = prices.get(key)
        link, src = PRICE_LINKS.get(key, ("", ""))
        link_cell = f"<a href='{esc(link)}' target='_blank'>→</a>" if link else "—"
        if p:
            rows.append([PRICE_LABELS.get(key, key), f"{fmt_val(key, p.get('value'))} {fmt_chg(p.get('change_pct'))}",
                         esc(p.get("date", "—")), esc(src), link_cell, "✅ 正常"])
        else:
            rows.append([PRICE_LABELS.get(key, key), "—", "—", esc(src), link_cell, "⚠️ 缺失"])
    for k, v in macro.items():
        link, src, desc = MACRO_LINKS.get(k, ("", v.get("source", ""), k))
        link_cell = f"<a href='{esc(link)}' target='_blank'>→</a>" if link else "—"
        rows.append([esc(desc), fmt_val(k, v.get("value")), esc(v.get("date", "—")), esc(src), link_cell, "✅ 正常"])
    st.markdown(build_table(["指标", "当前值", "数据截至", "来源", "链接", "状态"], rows, "dt"), unsafe_allow_html=True)


def render_evidence(data):
    """证据库 — 卖方研报 + 市场事件流"""
    st.markdown("<div class='section-title'>证据库</div>", unsafe_allow_html=True)

    # 卖方研报
    research = data.get("research", {})
    reports = research.get("rss_structured", []) + research.get("ratings", [])
    if reports:
        st.markdown("<div style='color:#8888aa;font-size:0.82rem;margin-bottom:6px;font-weight:600'>卖方研报结构化</div>", unsafe_allow_html=True)
        action_map = {"target_change": "目标价调整", "upgrade": "上调评级", "downgrade": "下调评级", "initiate": "首次覆盖"}
        dir_map = {"bullish": "看多", "bearish": "看空", "neutral": "中性"}
        rows = []
        for r in reports:
            action = action_map.get(r.get("action"), r.get("action", "—"))
            tp = r.get("target_price")
            tp_str = f"${tp}" if tp else "—"
            direction = dir_map.get(r.get("direction"), r.get("direction", "—"))
            url = r.get("url", "")
            url_cell = f"<a href='{esc(url)}' target='_blank'>查看 →</a>" if url else "—"
            rows.append([esc(r.get("bank", "—")), action, esc(r.get("ticker", "—")), esc(r.get("company", "—")),
                         tp_str, direction, esc(r.get("rationale", "—")), url_cell])
        st.markdown(build_table(["机构", "动作", "标的", "公司", "目标价", "方向", "理由", "链接"], rows, "dt"), unsafe_allow_html=True)
    else:
        st.markdown(
            "<div style='color:#666688;font-size:0.85rem;margin-bottom:10px'>今日无结构化研报 · 可查看 "
            "<a href='https://wallstreetcn.com' target='_blank' style='color:#6ea8fe'>华尔街见闻</a> | "
            "<a href='https://www.eastmoney.com' target='_blank' style='color:#6ea8fe'>东方财富</a></div>",
            unsafe_allow_html=True,
        )

    # 市场事件流
    events = data.get("events", [])
    st.markdown(f"<div style='color:#8888aa;font-size:0.82rem;margin:16px 0 6px 0;font-weight:600'>市场事件流（{len(events)} 条）</div>", unsafe_allow_html=True)
    if not events:
        st.markdown(
            "<span style='color:#666688;font-size:0.85rem'>今日无事件流 · 可查看 "
            "<a href='https://wallstreetcn.com' target='_blank' style='color:#6ea8fe'>华尔街见闻</a> | "
            "<a href='https://www.jin10.com' target='_blank' style='color:#6ea8fe'>金十数据</a></span>",
            unsafe_allow_html=True,
        )
        return
    source_map = {
        "reddit_equities": ("股票", "https://xueqiu.com"),
        "reddit_wsb": ("WSB", "https://wallstreetcn.com"),
    }
    html_str = ""
    for e in events:
        title = e.get("title", "")
        url = e.get("url", "")
        source = e.get("source", "")
        score = e.get("score", 0)
        created = e.get("created_utc", "")[:10]
        sub_name, _ = source_map.get(source, (source, url))
        valid_url = url and "reddit.com/x" not in url and "reddit.com/y" not in url
        title_html = f"<a href='{esc(url)}' target='_blank'>{esc(title)}</a>" if valid_url else esc(title)
        html_str += f"""
        <div class='event-item'>
            <span class='badge' style='background:rgba(102,126,234,0.12);color:#6ea8fe'>{esc(sub_name)}</span>
            {title_html}
            <span style='color:#666;font-size:0.78rem'> · {score} pts · {esc(created)}</span>
        </div>"""
    st.markdown(html_str, unsafe_allow_html=True)


def render_resources():
    st.markdown("<div class='section-title'>外部资源导航</div>", unsafe_allow_html=True)
    html_str = "<div style='display:flex;flex-wrap:wrap;gap:4px'>"
    for name, url, desc in EXTERNAL_RESOURCES:
        html_str += f"""
        <div class='res-card'>
            <a href='{esc(url)}' target='_blank'>{esc(name)}</a>
            <div style='color:#8888aa;font-size:0.76rem;margin-top:2px'>{esc(desc)}</div>
        </div>"""
    html_str += "</div>"
    st.markdown(html_str, unsafe_allow_html=True)


def render_footer():
    st.markdown("""
    <div style='text-align:center;padding:24px 0;color:#666688;font-size:0.82rem;
         border-top:1px solid rgba(255,255,255,0.06);margin-top:24px'>
        本仪表盘数据自动采集自公开数据源，展示链接均使用内地可访问网站<br>
        每日北京时间 07:00 自动更新（周一至周五）· 保留 30 天历史数据 ·
        <a href='https://timsun.net/' target='_blank' style='color:#6ea8fe;text-decoration:none'>timsun.net</a>
    </div>
    """, unsafe_allow_html=True)


# ===== 主函数 =====
def main():
    st.set_page_config(page_title="每日宏观跨资产仪表盘", layout="wide")
    inject_css()
    data = load_data()
    if not data:
        st.error("未找到 daily_macro.json，请先运行 macro_collector.py")
        return
    history = load_history()
    render_header(data)
    render_judgment(data)
    render_engines(data)
    render_trends(history, data)
    render_evidence(data)
    render_transparency(data)
    render_resources()
    render_footer()


if __name__ == "__main__":
    main()
