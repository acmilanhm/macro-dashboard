"""
加密衍生品雷达 (Crypto Derivatives Radar)
==========================================
对标 timsun.net 的 Crypto Derivatives Radar：
把 ETF、永续杠杆、Deribit 期权合成 24h / 1-7d 市场质量判断。

数据源（全部免费、免鉴权公开 API）：
  - Binance USD-M 永续 : 资金费率、未平仓量    (fapi.binance.com)
  - Bybit 永续         : 资金费率、未平仓量    (api.bybit.com)
  - Deribit            : DVOL 波动率指数、期权 put/call OI、永续资金费率 (deribit.com)
  - yfinance           : BTC 现货 ETF 价格/成交 (IBIT/FBTC/ARKB/BITB)
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

import requests

try:
    import yfinance as yf
except ImportError:
    yf = None

_HEADERS = {"User-Agent": "crypto-radar/1.0 (research)"}
_BTC_ETFS = {"IBIT": "BlackRock", "FBTC": "Fidelity", "ARKB": "ARK", "BITB": "Bitwise"}


# --------------------------------------------------------------------------- #
# 1. Binance 永续：资金费率 + 未平仓量
# --------------------------------------------------------------------------- #
def fetch_binance() -> dict:
    out = {"source": "binance"}
    try:
        # premiumIndex: 标记价、最近资金费率、下次结算时间
        r = requests.get("https://fapi.binance.com/fapi/v1/premiumIndex",
                         params={"symbol": "BTCUSDT"}, headers=_HEADERS, timeout=15)
        r.raise_for_status()
        d = r.json()
        out["mark_price"] = float(d.get("markPrice", 0))
        out["funding_rate"] = float(d.get("lastFundingRate", 0))
        out["next_funding_time"] = d.get("nextFundingTime")
        # 未平仓量
        r2 = requests.get("https://fapi.binance.com/fapi/v1/openInterest",
                          params={"symbol": "BTCUSDT"}, headers=_HEADERS, timeout=15)
        r2.raise_for_status()
        out["open_interest"] = float(r2.json().get("openInterest", 0))
    except Exception as e:
        print(f"[warn] Binance 抓取失败: {e}")
        out["error"] = str(e)
    return out


# --------------------------------------------------------------------------- #
# 2. Bybit 永续：资金费率 + 未平仓量
# --------------------------------------------------------------------------- #
def fetch_bybit() -> dict:
    out = {"source": "bybit"}
    try:
        r = requests.get("https://api.bybit.com/v5/market/tickers",
                         params={"category": "linear", "symbol": "BTCUSDT"},
                         headers=_HEADERS, timeout=15)
        r.raise_for_status()
        lst = r.json().get("result", {}).get("list", [])
        if lst:
            t = lst[0]
            out["funding_rate"] = float(t.get("fundingRate", 0))
            out["next_funding_time"] = t.get("nextFundingTime")
            out["last_price"] = float(t.get("lastPrice", 0))
            out["open_interest"] = float(t.get("openInterest", 0))
    except Exception as e:
        print(f"[warn] Bybit 抓取失败: {e}")
        out["error"] = str(e)
    return out


# --------------------------------------------------------------------------- #
# 3. Deribit：DVOL + 期权 put/call OI + 永续
# --------------------------------------------------------------------------- #
def fetch_deribit() -> dict:
    out = {"source": "deribit"}
    try:
        # DVOL 波动率指数（日线最新收盘）
        r = requests.get("https://www.deribit.com/api/v2/public/get_volatility_index_data",
                         params={"currency": "BTC", "resolution": "1D", "limit": "1"},
                         headers=_HEADERS, timeout=15)
        r.raise_for_status()
        data = r.json().get("result", {}).get("data", [])
        if data:
            # [ts, open, high, low, close]
            out["dvol"] = float(data[0][-1])

        # 期权全市场 book summary -> put/call OI
        r2 = requests.get("https://www.deribit.com/api/v2/public/get_book_summary_by_currency",
                          params={"currency": "BTC", "kind": "option"},
                          headers=_HEADERS, timeout=20)
        r2.raise_for_status()
        opts = r2.json().get("result", [])
        put_oi = call_oi = 0.0
        for o in opts:
            name = o.get("instrument_name", "")
            oi = float(o.get("open_interest", 0))
            if name.endswith("-P"):
                put_oi += oi
            elif name.endswith("-C"):
                call_oi += oi
        out["put_oi"] = put_oi
        out["call_oi"] = call_oi
        out["put_call_ratio"] = round(put_oi / call_oi, 3) if call_oi else None
        out["total_options_oi"] = put_oi + call_oi

        # 永续资金费率
        r3 = requests.get("https://www.deribit.com/api/v2/public/ticker",
                          params={"instrument_name": "BTC-PERPETUAL"},
                          headers=_HEADERS, timeout=15)
        r3.raise_for_status()
        tk = r3.json().get("result", {})
        out["perp_funding_8h"] = float(tk.get("funding_8h", 0))
        out["perp_oi"] = float(tk.get("open_interest", 0))
    except Exception as e:
        print(f"[warn] Deribit 抓取失败: {e}")
        out["error"] = str(e)
    return out


# --------------------------------------------------------------------------- #
# 4. BTC 现货 ETF（价格 / 成交 / 溢价代理）
# --------------------------------------------------------------------------- #
def fetch_btc_etfs() -> list[dict]:
    if yf is None:
        print("[warn] yfinance 未安装，跳过 BTC ETF")
        return []
    out = []
    for sym, issuer in _BTC_ETFS.items():
        for attempt in range(2):
            try:
                df = yf.download(sym, period="5d", interval="1d",
                                 progress=False, auto_adjust=True)
                if not df.empty:
                    break
            except Exception as e:
                print(f"[warn] {sym} 第{attempt+1}次失败: {e}")
            time.sleep(2)
        else:
            continue
        if df.empty:
            continue
        last = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else last
        out.append({
            "ticker": sym,
            "issuer": issuer,
            "price": round(float(last["Close"]), 2),
            "volume": round(float(last["Volume"]), 0),
            "change_pct": round((float(last["Close"]) - float(prev["Close"]))
                                / float(prev["Close"]) * 100, 2),
            "date": str(df.index[-1].date()),
            "source": "Yahoo Finance",
        })
        time.sleep(1.2)
    return out


# --------------------------------------------------------------------------- #
# 5. 市场质量合成：24h / 1-7d 判断（启发式）
# --------------------------------------------------------------------------- #
def _funding_heat(rate_8h: float) -> tuple[str, str]:
    """资金费率热度 -> (热度, 方向)。rate 为单次(8h)费率小数。"""
    if rate_8h is None:
        return ("unknown", "unknown")
    pct = rate_8h * 100  # 百分比
    if pct > 0.05:
        return ("hot", "bullish_overheated")     # 多头拥挤，过热
    if pct > 0.01:
        return ("warm", "bullish")
    if pct >= -0.01:
        return ("cool", "neutral")
    if pct >= -0.05:
        return ("cool", "bearish")
    return ("cold", "bearish_squeeze")           # 空头拥挤，轧空风险


def _dvol_regime(dvol: float | None) -> str:
    if dvol is None:
        return "unknown"
    if dvol < 45:
        return "low_complacent"
    if dvol < 70:
        return "normal"
    if dvol < 90:
        return "elevated"
    return "high_fearful"


def _pcr_positioning(pcr: float | None) -> str:
    if pcr is None:
        return "unknown"
    if pcr < 0.6:
        return "call_heavy_bullish"
    if pcr < 1.0:
        return "balanced"
    return "put_heavy_hedging"


def compute_market_quality(crypto: dict) -> dict:
    """根据资金费率/DVOL/put-call 合成市场质量判断。"""
    # 取 Binance 资金费率为主（流动性最大），Bybit 佐证
    bn = crypto.get("binance", {})
    by = crypto.get("bybit", {})
    der = crypto.get("deribit", {})

    fund = bn.get("funding_rate", by.get("funding_rate"))
    dvol = der.get("dvol")
    pcr = der.get("put_call_ratio")

    # 数据全部缺失时直接返回"数据不足"，避免误判
    if fund is None and dvol is None and pcr is None:
        return {
            "verdict_24h": "数据不足，无法判断",
            "verdict_1_7d": "数据不足，无法判断",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    heat, lev_dir = _funding_heat(fund)
    dvol_regime = _dvol_regime(dvol)
    pcr_pos = _pcr_positioning(pcr)

    # 综合 verdict
    bullish_signals = sum([
        lev_dir in ("bullish", "bullish_overheated"),
        pcr_pos == "call_heavy_bullish",
        dvol_regime in ("low_complacent", "normal"),
    ])
    bearish_signals = sum([
        lev_dir in ("bearish", "bearish_squeeze"),
        pcr_pos == "put_heavy_hedging",
        dvol_regime == "high_fearful",
    ])

    if lev_dir == "bullish_overheated":
        verdict_24h = "多头杠杆过热，短线回调风险上升"
        verdict_1_7d = "趋势偏多但需去杠杆，关注资金费率回落"
    elif lev_dir == "bearish_squeeze":
        verdict_24h = "空头杠杆拥挤，上行轧空概率升高"
        verdict_1_7d = "资金面偏空但易反弹，关注空头平仓"
    elif bullish_signals > bearish_signals:
        verdict_24h = "衍生品结构偏多，短线动能健康"
        verdict_1_7d = "中期偏多，资金费率与期权定位支撑"
    elif bearish_signals > bullish_signals:
        verdict_24h = "衍生品结构偏空，下行压力增加"
        verdict_1_7d = "中期偏空，对冲需求上升"
    else:
        verdict_24h = "衍生品信号中性，短线震荡"
        verdict_1_7d = "中性，等待资金费率与期权定位突破"

    return {
        "funding_rate_8h": fund,
        "funding_heat": heat,
        "leverage_direction": lev_dir,
        "dvol": der.get("dvol"),
        "dvol_regime": dvol_regime,
        "put_call_ratio": der.get("put_call_ratio"),
        "options_positioning": pcr_pos,
        "verdict_24h": verdict_24h,
        "verdict_1_7d": verdict_1_7d,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# --------------------------------------------------------------------------- #
# 6. 汇总
# --------------------------------------------------------------------------- #
def collect_crypto_radar() -> dict:
    print("[info] 抓取 Binance 永续...")
    bn = fetch_binance()
    print("[info] 抓取 Bybit 永续...")
    by = fetch_bybit()
    print("[info] 抓取 Deribit 期权/DVOL...")
    der = fetch_deribit()
    print("[info] 抓取 BTC 现货 ETF...")
    etfs = fetch_btc_etfs()

    crypto = {"binance": bn, "bybit": by, "deribit": der, "etfs": etfs}
    crypto["market_quality"] = compute_market_quality(crypto)
    return crypto


if __name__ == "__main__":
    import json
    print(json.dumps(collect_crypto_radar(), ensure_ascii=False, indent=2))
