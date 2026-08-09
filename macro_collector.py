"""
每日宏观跨资产数据收集器（timsun.net 同款数据源复刻版）
=========================================================
抓取标普500/美元指数/比特币/原油、10Y国债收益率、VIX、高收益债OAS、
美联储资产负债表/RRP/TGA 并计算净流动性，外加 Reddit 市场事件流。
全部使用免费公开数据源，无需付费终端。

数据源：
  - Yahoo Finance      : 价格类（标普500、DXY、BTC、WTI）
  - FRED API           : VIX(VIXCLS)、高收益OAS(BAMLH0A0HYM2)、10Y(DGS10)、
                         总资产(WALCL)、TGA(WTREGEN)、RRP(WLRRAL)
  - 美国财政部          : 收益率曲线（FRED 兜底）
  - Reddit 公开 JSON   : 市场事件流

依赖:  pip install yfinance pandas requests
FRED API Key (免费申请): https://fred.stlouisfed.org/docs/api/api_key.html
设为环境变量 FRED_API_KEY 即可；未设置时 VIX/HY 等会尝试无 key 访问（有限流）。
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone, timedelta

import requests
import pandas as pd

try:
    import yfinance as yf
except ImportError:
    yf = None

FRED_API_KEY = os.getenv("FRED_API_KEY", "")
FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"


# --------------------------------------------------------------------------- #
# 1. 价格类：Yahoo Finance
# --------------------------------------------------------------------------- #
YF_TICKERS = {
    "SP500": "^GSPC",       # 标普500
    "DXY":   "DX-Y.NYB",    # 美元指数
    "BTC":   "BTC-USD",     # 比特币
    "WTI":   "CL=F",        # WTI 原油期货
}


def fetch_prices() -> dict:
    """抓取最新收盘价与日涨跌幅。"""
    if yf is None:
        print("[warn] yfinance 未安装，跳过价格类")
        return {}
    out = {}
    for name, sym in YF_TICKERS.items():
        for attempt in range(3):  # 最多重试 3 次，缓解 Yahoo 限流
            try:
                df = yf.download(sym, period="5d", interval="1d",
                                 progress=False, auto_adjust=True)
                if not df.empty:
                    break
            except Exception as e:
                print(f"[warn] {name} 第{attempt+1}次失败: {e}")
            time.sleep(3)  # 限流退避
        else:
            continue
        if df.empty:
            continue
        last = df.iloc[-1]["Close"]
        prev = df.iloc[-2]["Close"] if len(df) > 1 else last
        chg = (last - prev) / prev * 100
        out[name] = {
            "value": round(float(last), 2),
            "change_pct": round(float(chg), 2),
            "date": str(df.index[-1].date()),
            "source": "Yahoo Finance",
        }
        time.sleep(1.5)  # 每只标的之间留间隔，降低 429 概率
    return out


# --------------------------------------------------------------------------- #
# 2. FRED 序列：VIX / 高收益OAS / 10Y / WALCL / TGA / RRP
# --------------------------------------------------------------------------- #
FRED_SERIES = {
    "VIX_10Y":        "DGS10",          # 10Y 国债收益率
    "VIX":            "VIXCLS",         # VIX
    "HY_OAS":         "BAMLH0A0HYM2",   # 高收益债 OAS
    "FED_ASSETS":     "WALCL",          # 美联储总资产（十亿）
    "TGA":            "WTREGEN",        # 财政部一般账户（十亿）
    "RRP":            "WLRRAL",         # 隔夜逆回购（十亿）
}


def fetch_fred_series(series_id: str) -> dict | None:
    params = {
        "series_id": series_id,
        "file_type": "json",
        "sort_order": "desc",
        "limit": 5,
    }
    if FRED_API_KEY:
        params["api_key"] = FRED_API_KEY
    else:
        # 无 key 时 FRED 不允许 API 访问；这里给出降级提示
        print(f"[warn] 未设置 FRED_API_KEY，无法抓取 {series_id}")
        return None
    try:
        r = requests.get(FRED_BASE, params=params, timeout=20)
        r.raise_for_status()
        obs = r.json().get("observations", [])
        obs = [o for o in obs if o["value"] != "."]
        if not obs:
            return None
        return {"value": float(obs[0]["value"]), "date": obs[0]["date"]}
    except Exception as e:
        print(f"[warn] FRED {series_id} 抓取失败: {e}")
        return None


def fetch_fred_all() -> dict:
    out = {}
    for name, sid in FRED_SERIES.items():
        d = fetch_fred_series(sid)
        if d:
            out[name] = {**d, "source": "FRED " + sid}
        time.sleep(0.3)  # 礼貌限速
    # 计算净流动性 = WALCL - RRP - TGA（单位：十亿美元）
    if all(k in out for k in ("FED_ASSETS", "RRP", "TGA")):
        net = out["FED_ASSETS"]["value"] - out["RRP"]["value"] - out["TGA"]["value"]
        out["NET_LIQUIDITY"] = {
            "value": round(net, 1),
            "unit": "billion_usd",
            "formula": "WALCL - RRP - TGA",
            "source": "computed from FRED",
            "date": out["FED_ASSETS"]["date"],
        }
    return out


# --------------------------------------------------------------------------- #
# 3. Reddit 事件流（公开 JSON，无需鉴权，仅需 User-Agent）
# --------------------------------------------------------------------------- #
REDDIT_SUBS = {
    "reddit_equities": "stocks",
    "reddit_crypto":   "CryptoCurrency",
    "reddit_wsb":      "wallstreetbets",
}


def fetch_reddit_events(limit: int = 8) -> list[dict]:
    headers = {"User-Agent": "macro-collector/1.0 (research)"}
    events = []
    for tag, sub in REDDIT_SUBS.items():
        try:
            url = f"https://www.reddit.com/r/{sub}/top.json?t=day&limit={limit}"
            r = requests.get(url, headers=headers, timeout=15)
            r.raise_for_status()
            children = r.json()["data"]["children"]
            for c in children:
                d = c["data"]
                events.append({
                    "title": d["title"],
                    "source": tag,
                    "url": "https://reddit.com" + d["permalink"],
                    "score": d.get("score", 0),
                    "created_utc": datetime.fromtimestamp(
                        d["created_utc"], tz=timezone.utc
                    ).isoformat(),
                })
        except Exception as e:
            print(f"[warn] r/{sub} 抓取失败: {e}")
    events.sort(key=lambda x: x.get("score", 0), reverse=True)
    return events[:20]


# --------------------------------------------------------------------------- #
# 4. 汇总 & 落盘
# --------------------------------------------------------------------------- #
def _safe_collect_research() -> dict:
    """卖方研报结构化（需 openai/feedparser，缺失则降级为空）。"""
    try:
        from research_structurer import collect_research
        return collect_research()
    except Exception as e:
        print(f"[warn] 研报结构化跳过: {e}")
        return {"ratings": [], "rss_structured": []}


def _safe_generate_judgment(payload: dict) -> dict | None:
    """AI 研判生成（需 LLM_API_KEY，缺失则跳过）。"""
    try:
        from ai_judgment import generate_judgment
        return generate_judgment(payload)
    except Exception as e:
        print(f"[warn] AI 研判跳过: {e}")
        return None


def _safe_collect_crypto() -> dict:
    """加密衍生品雷达（缺依赖/网络则降级为空）。"""
    try:
        from crypto_derivatives_radar import collect_crypto_radar
        return collect_crypto_radar()
    except Exception as e:
        print(f"[warn] 加密衍生品雷达跳过: {e}")
        return {"binance": {}, "bybit": {}, "deribit": {}, "etfs": [],
                "market_quality": {}}


def collect_all(out_path: str = "daily_macro.json") -> dict:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    payload = {
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "trade_date": today,
        "prices": fetch_prices(),
        "macro": fetch_fred_all(),
        "events": fetch_reddit_events(),
    }
    # 卖方研报结构化
    payload["research"] = _safe_collect_research()
    # 加密衍生品雷达
    payload["crypto"] = _safe_collect_crypto()
    # AI 研判（依赖前面所有数据）
    judgment = _safe_generate_judgment(payload)
    if judgment:
        payload["judgment"] = judgment

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    n_res = len(payload["research"]["ratings"]) + len(payload["research"]["rss_structured"])
    mq = payload["crypto"].get("market_quality", {})
    print(f"[ok] 已写入 {out_path}  "
          f"价格{len(payload['prices'])}项 宏观{len(payload['macro'])}项 "
          f"事件{len(payload['events'])}条 研报{n_res}条 "
          f"加密{'有' if mq else '无'}")
    return payload


if __name__ == "__main__":
    collect_all()
