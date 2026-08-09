"""
宏观 + AI 产业链数据采集器（timsun.net 同款数据源复刻版）
=========================================================
抓取标普500/美元指数/原油/纳斯达克100、AI 核心股票与 ETF、
10Y国债收益率、VIX、高收益债OAS、美联储资产负债表/RRP/TGA
并计算净流动性，外加 Reddit 市场事件流与 AI 产业链雷达。

数据源：
  - Yahoo Finance      : 价格类（标普500、DXY、WTI、^NDX、AI 股票、AI ETF）
  - FRED API           : VIX(VIXCLS)、高收益OAS(BAMLH0A0HYM2)、10Y(DGS10)、
                         总资产(WALCL)、TGA(WTREGEN)、RRP(WLRRAL)
  - 美国财政部          : 收益率曲线（FRED 兜底）
  - Reddit 公开 JSON   : 市场事件流
  - ai_radar.py        : AI 产业链雷达（新闻流 + 信号 + 投资含义）

依赖:  pip install yfinance pandas requests feedparser
FRED API Key (免费申请): https://fred.stlouisfed.org/docs/api/api_key.html
设为环境变量 FRED_API_KEY 即可；未设置时 VIX/HY 等会尝试无 key 访问（有限流）。
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests
import pandas as pd

try:
    import yfinance as yf
except ImportError:
    yf = None

FRED_API_KEY = os.getenv("FRED_API_KEY", "")
FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"

# 项目根目录（用于历史数据存储）
_PROJECT_DIR = Path(__file__).parent.resolve()
_HISTORY_DIR = _PROJECT_DIR / "data" / "history"


# --------------------------------------------------------------------------- #
# 1. 价格类：Yahoo Finance（标普500 / 美元指数 / WTI 原油 / 纳斯达克100）
# --------------------------------------------------------------------------- #
YF_TICKERS = {
    "SP500":   "^GSPC",      # 标普500
    "DXY":     "DX-Y.NYB",   # 美元指数
    "WTI":     "CL=F",       # WTI 原油期货
    "NASDAQ":  "^NDX",       # 纳斯达克100指数
}


def _extract_close(df: pd.DataFrame, position: int = -1) -> float:
    """
    从 DataFrame 中提取 Close 值，兼容 yfinance MultiIndex 列。
    position=-1 取最后一行（最新），-2 取倒数第二行（前一日）。
    """
    val = df.iloc[position]["Close"]
    if isinstance(val, pd.Series):
        # MultiIndex 情况：取第一个元素
        return float(val.iloc[0])
    return float(val)


def fetch_prices() -> dict:
    """抓取最新收盘价与日涨跌幅（标普500 / DXY / WTI / 纳斯达克100）。"""
    if yf is None:
        print("[warn] yfinance 未安装，跳过价格类")
        return {}
    out = {}
    for name, sym in YF_TICKERS.items():
        df = None
        for attempt in range(3):  # 最多重试 3 次，缓解 Yahoo 限流
            try:
                df = yf.download(sym, period="5d", interval="1d",
                                 progress=False, auto_adjust=True)
                if not df.empty:
                    break
            except Exception as e:
                print(f"[warn] {name} 第{attempt+1}次失败: {e}")
            time.sleep(3)  # 限流退避
        if df is None or df.empty:
            continue
        try:
            last = _extract_close(df, -1)
            prev = _extract_close(df, -2) if len(df) > 1 else last
            chg = (last - prev) / prev * 100
            out[name] = {
                "value": round(last, 2),
                "change_pct": round(chg, 2),
                "date": str(df.index[-1].date()),
                "source": "Yahoo Finance",
            }
        except Exception as e:
            print(f"[warn] {name} 数据解析失败: {e}")
        time.sleep(1.5)  # 每只标的之间留间隔，降低 429 概率
    return out


# --------------------------------------------------------------------------- #
# 2. AI 核心股票：Yahoo Finance
# --------------------------------------------------------------------------- #
AI_STOCKS = {
    "NVDA":  "英伟达",
    "AVGO":  "博通",
    "TSM":   "台积电",
    "ASML":  "阿斯麦",
    "MSFT":  "微软",
    "GOOGL": "谷歌",
    "META":  "Meta",
    "AMZN":  "亚马逊",
    "AAPL":  "苹果",
    "PLTR":  "Palantir",
    "CRM":   "Salesforce",
    "NOW":   "ServiceNow",
    "AMD":   "超微",
}


def fetch_ai_stocks() -> dict:
    """抓取 AI 核心股票的最新价格与日涨跌幅。"""
    if yf is None:
        print("[warn] yfinance 未安装，跳过 AI 股票")
        return {}
    out = {}
    for ticker, name in AI_STOCKS.items():
        df = None
        for attempt in range(3):  # 最多重试 3 次
            try:
                df = yf.download(ticker, period="5d", interval="1d",
                                 progress=False, auto_adjust=True)
                if not df.empty:
                    break
            except Exception as e:
                print(f"[warn] {ticker} 第{attempt+1}次失败: {e}")
            time.sleep(3)  # 限流退避
        if df is None or df.empty:
            continue
        try:
            last = _extract_close(df, -1)
            prev = _extract_close(df, -2) if len(df) > 1 else last
            chg = (last - prev) / prev * 100
            out[ticker] = {
                "value": round(last, 2),
                "change_pct": round(chg, 2),
                "date": str(df.index[-1].date()),
                "source": "Yahoo Finance",
                "name": name,
            }
        except Exception as e:
            print(f"[warn] {ticker} 数据解析失败: {e}")
        time.sleep(1.5)  # 限流退避
    return out


# --------------------------------------------------------------------------- #
# 3. AI ETF：Yahoo Finance
# --------------------------------------------------------------------------- #
AI_ETFS = {
    "SMH":  "半导体ETF",
    "BOTZ": "机器人ETF",
    "IGV":  "软件ETF",
    "SOXX": "费城半导体ETF",
}


def fetch_ai_etfs() -> dict:
    """抓取 AI 相关 ETF 的最新价格与日涨跌幅。"""
    if yf is None:
        print("[warn] yfinance 未安装，跳过 AI ETF")
        return {}
    out = {}
    for ticker, name in AI_ETFS.items():
        df = None
        for attempt in range(3):  # 最多重试 3 次
            try:
                df = yf.download(ticker, period="5d", interval="1d",
                                 progress=False, auto_adjust=True)
                if not df.empty:
                    break
            except Exception as e:
                print(f"[warn] {ticker} 第{attempt+1}次失败: {e}")
            time.sleep(3)  # 限流退避
        if df is None or df.empty:
            continue
        try:
            last = _extract_close(df, -1)
            prev = _extract_close(df, -2) if len(df) > 1 else last
            chg = (last - prev) / prev * 100
            out[ticker] = {
                "value": round(last, 2),
                "change_pct": round(chg, 2),
                "date": str(df.index[-1].date()),
                "source": "Yahoo Finance",
                "name": name,
            }
        except Exception as e:
            print(f"[warn] {ticker} 数据解析失败: {e}")
        time.sleep(1.5)  # 限流退避
    return out


# --------------------------------------------------------------------------- #
# 4. FRED 序列：VIX / 高收益OAS / 10Y / WALCL / TGA / RRP
# --------------------------------------------------------------------------- #
FRED_SERIES = {
    "VIX_10Y":    "DGS10",          # 10Y 国债收益率
    "VIX":        "VIXCLS",         # VIX
    "HY_OAS":     "BAMLH0A0HYM2",   # 高收益债 OAS
    "FED_ASSETS": "WALCL",          # 美联储总资产（十亿）
    "TGA":        "WTREGEN",        # 财政部一般账户（十亿）
    "RRP":        "WLRRAL",         # 隔夜逆回购（十亿）
}


def fetch_fred_series(series_id: str) -> dict | None:
    """从 FRED 抓取单个序列的最新观测值。"""
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
    """抓取全部 FRED 宏观序列并计算净流动性。"""
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
# 5. Reddit 事件流（公开 JSON，无需鉴权，仅需 User-Agent）
# --------------------------------------------------------------------------- #
REDDIT_SUBS = {
    "reddit_equities": "stocks",
    "reddit_wsb":      "wallstreetbets",
}


def fetch_reddit_events(limit: int = 8) -> list[dict]:
    """从 Reddit 公开 JSON 采集市场事件流。"""
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
# 6. 安全采集封装（依赖缺失/网络失败时优雅降级）
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


def _safe_collect_ai_radar(ai_stocks: dict) -> dict:
    """AI 产业链雷达（缺依赖/网络则降级为空结构）。"""
    try:
        from ai_radar import collect_ai_radar
        return collect_ai_radar(ai_stocks)
    except Exception as e:
        print(f"[warn] AI 产业链雷达跳过: {e}")
        return {
            "supply_chain": {"chips": [], "cloud": [], "models": [], "applications": []},
            "news_flow": [],
            "earnings_signals": {},
            "investment_implications": {},
        }


# --------------------------------------------------------------------------- #
# 7. 历史数据保存
# --------------------------------------------------------------------------- #
def save_history(payload: dict, history_dir: Path | str | None = None) -> Path | None:
    """
    将采集数据保存到历史目录 data/history/YYYY-MM-DD.json。

    自动清理超过 30 天的历史文件。

    参数:
        payload    : 采集到的完整数据
        history_dir: 历史目录路径，默认为项目根目录下的 data/history/

    返回:
        保存的文件路径，失败返回 None
    """
    if history_dir is None:
        history_dir = _HISTORY_DIR
    history_dir = Path(history_dir)

    try:
        history_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        print(f"[warn] 创建历史目录失败: {e}")
        return None

    trade_date = payload.get(
        "trade_date",
        datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    )
    history_file = history_dir / f"{trade_date}.json"

    try:
        with open(history_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        print(f"[info] 历史数据已保存: {history_file}")
    except Exception as e:
        print(f"[warn] 历史数据保存失败: {e}")
        return None

    # 清理超过 30 天的历史文件
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    for old_file in history_dir.glob("*.json"):
        try:
            # 文件名格式: YYYY-MM-DD.json
            file_date_str = old_file.stem
            file_date = datetime.strptime(file_date_str, "%Y-%m-%d").replace(
                tzinfo=timezone.utc
            )
            if file_date < cutoff:
                old_file.unlink()
                print(f"[info] 已删除过期历史文件: {old_file.name}")
        except ValueError:
            # 文件名不是日期格式，跳过
            continue
        except Exception as e:
            print(f"[warn] 清理历史文件失败 {old_file.name}: {e}")

    return history_file


# --------------------------------------------------------------------------- #
# 8. 汇总 & 落盘
# --------------------------------------------------------------------------- #
def collect_all(out_path: str = "daily_macro.json") -> dict:
    """
    采集全部数据并写入 JSON 文件。

    采集内容：
      - 核心价格 (SP500 / DXY / WTI / NASDAQ)
      - AI 核心股票 (NVDA / AVGO / TSM / MSFT / ...)
      - AI ETF (SMH / BOTZ / IGV / SOXX)
      - 宏观与流动性 (FRED: VIX / 10Y / HY_OAS / WALCL / TGA / RRP / NET_LIQUIDITY)
      - Reddit 市场事件流
      - AI 产业链雷达 (ai_radar.py)
      - 卖方研报结构化 (research_structurer.py)
      - AI 研判 (ai_judgment.py)
    """
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # ---- 采集核心价格 ----
    print("[info] 采集核心价格 (SP500 / DXY / WTI / NASDAQ)...")
    prices = fetch_prices()

    # ---- 采集 AI 股票 ----
    print("[info] 采集 AI 核心股票...")
    ai_stocks = fetch_ai_stocks()

    # ---- 采集 AI ETF ----
    print("[info] 采集 AI ETF...")
    ai_etfs = fetch_ai_etfs()

    # ---- 采集宏观数据 ----
    print("[info] 采集 FRED 宏观数据...")
    macro = fetch_fred_all()

    # ---- 采集 Reddit 事件流 ----
    print("[info] 采集 Reddit 事件流...")
    events = fetch_reddit_events()

    payload = {
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "trade_date": today,
        "prices": prices,
        "ai_stocks": ai_stocks,
        "ai_etfs": ai_etfs,
        "macro": macro,
        "events": events,
    }

    # ---- AI 产业链雷达（依赖 ai_stocks 数据）----
    print("[info] 采集 AI 产业链雷达...")
    payload["ai_radar"] = _safe_collect_ai_radar(payload.get("ai_stocks", {}))

    # ---- 卖方研报结构化 ----
    print("[info] 采集卖方研报...")
    payload["research"] = _safe_collect_research()

    # ---- AI 研判（依赖前面所有数据）----
    print("[info] 生成 AI 研判...")
    judgment = _safe_generate_judgment(payload)
    if judgment:
        payload["judgment"] = judgment

    # ---- 写入主文件 ----
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    # ---- 保存历史数据 ----
    save_history(payload)

    # ---- 汇总日志 ----
    n_res = (
        len(payload["research"]["ratings"])
        + len(payload["research"]["rss_structured"])
    )
    ai_impl = payload.get("ai_radar", {}).get("investment_implications", {})
    print(
        f"[ok] 已写入 {out_path}  "
        f"价格{len(payload['prices'])}项 "
        f"AI股票{len(payload['ai_stocks'])}只 "
        f"AI ETF {len(payload['ai_etfs'])}只 "
        f"宏观{len(payload['macro'])}项 "
        f"事件{len(payload['events'])}条 "
        f"研报{n_res}条 "
        f"AI雷达{'有' if ai_impl else '无'}"
    )
    return payload


if __name__ == "__main__":
    collect_all()
