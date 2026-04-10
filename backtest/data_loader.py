"""
Historical OHLCV data loader for backtesting.
Primary: OANDA historical candles API (most accurate for our broker).
Fallback: Yahoo Finance via yfinance.
"""

import os
from datetime import datetime, timedelta, timezone

import pandas as pd
import httpx
from loguru import logger

OANDA_PRACTICE_URL = "https://api-fxpractice.oanda.com"

OANDA_INSTRUMENT_MAP = {
    "EURUSD": "EUR_USD", "GBPUSD": "GBP_USD", "USDJPY": "USD_JPY",
    "AUDUSD": "AUD_USD", "USDCAD": "USD_CAD", "NZDUSD": "NZD_USD",
    "USDCHF": "USD_CHF", "EURJPY": "EUR_JPY", "GBPJPY": "GBP_JPY",
    "XAUUSD": "XAU_USD", "XAGUSD": "XAG_USD",
    "USOIL":  "WTICO_USD", "UKOIL": "BCO_USD",
}

YAHOO_MAP = {
    "EURUSD": "EURUSD=X", "GBPUSD": "GBPUSD=X", "USDJPY": "JPY=X",
    "AUDUSD": "AUDUSD=X", "USDCAD": "CAD=X",    "NZDUSD": "NZDUSD=X",
    "USDCHF": "CHF=X",    "EURJPY": "EURJPY=X",  "GBPJPY": "GBPJPY=X",
    "XAUUSD": "GC=F",     "XAGUSD": "SI=F",
    "USOIL":  "CL=F",     "UKOIL":  "BZ=F",      "NATGAS": "NG=F",
}


async def load_ohlcv(
    instrument: str,
    timeframe: str = "H1",
    days: int = 365,
) -> pd.DataFrame:
    """
    Load historical OHLCV data. Tries OANDA first, falls back to yfinance.
    Returns DataFrame with columns: open, high, low, close, volume, datetime index.
    """
    df = await _load_oanda(instrument, timeframe, days)
    if df is not None and len(df) > 50:
        logger.info(f"[DATA] {instrument} {timeframe}: {len(df)} candles from OANDA")
        return df

    df = _load_yfinance(instrument, timeframe, days)
    if df is not None and len(df) > 50:
        logger.info(f"[DATA] {instrument} {timeframe}: {len(df)} candles from Yahoo Finance")
        return df

    raise RuntimeError(f"Could not load data for {instrument} {timeframe}")


async def _load_oanda(instrument: str, timeframe: str, days: int) -> pd.DataFrame | None:
    api_key    = os.environ.get("OANDA_API_KEY", "")
    account_id = os.environ.get("OANDA_ACCOUNT_ID", "")
    if not api_key:
        return None

    oanda_sym = OANDA_INSTRUMENT_MAP.get(instrument)
    if not oanda_sym:
        return None

    tf_map = {"M1": "M1", "M5": "M5", "M15": "M15", "H1": "H1", "H4": "H4", "D1": "D"}
    gran   = tf_map.get(timeframe, "H1")

    from_dt = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(
                f"{OANDA_PRACTICE_URL}/v3/instruments/{oanda_sym}/candles",
                headers={"Authorization": f"Bearer {api_key}"},
                params={"granularity": gran, "from": from_dt, "count": 5000, "price": "M"},
            )
            if r.status_code != 200:
                return None
            data = r.json()

        candles = data.get("candles", [])
        rows = []
        for c in candles:
            if not c.get("complete", True):
                continue
            mid = c.get("mid", {})
            rows.append({
                "datetime": pd.Timestamp(c["time"]),
                "open":     float(mid.get("o", 0)),
                "high":     float(mid.get("h", 0)),
                "low":      float(mid.get("l", 0)),
                "close":    float(mid.get("c", 0)),
                "volume":   float(c.get("volume", 0)),
            })

        if not rows:
            return None

        df = pd.DataFrame(rows).set_index("datetime")
        df.index = pd.DatetimeIndex(df.index)
        return df

    except Exception as exc:
        logger.warning(f"[DATA] OANDA load failed for {instrument}: {exc}")
        return None


def _load_yfinance(instrument: str, timeframe: str, days: int) -> pd.DataFrame | None:
    try:
        import yfinance as yf

        sym = YAHOO_MAP.get(instrument)
        if not sym:
            return None

        tf_map    = {"M15": "15m", "H1": "1h", "H4": "4h", "D1": "1d"}
        period_map = {"M15": f"{min(days,60)}d", "H1": f"{min(days,730)}d", "H4": f"{min(days,730)}d", "D1": f"{days}d"}

        interval = tf_map.get(timeframe, "1h")
        period   = period_map.get(timeframe, f"{days}d")

        df = yf.download(sym, period=period, interval=interval, progress=False, auto_adjust=True)
        if df.empty:
            return None
        df.columns = [c.lower() for c in df.columns]
        df.index.name = "datetime"
        if "volume" not in df.columns:
            df["volume"] = 0.0
        return df.dropna()

    except Exception as exc:
        logger.warning(f"[DATA] yfinance load failed for {instrument}: {exc}")
        return None
