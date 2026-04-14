"""
Multi-timeframe technical analysis engine.
Computes all indicators and pattern detection across M15, H1, H4, D1.
"""

import os
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd
import pandas_ta as ta
from loguru import logger


class IndicatorEngine:
    """
    Fetches OHLCV data and computes technical indicators across multiple timeframes.
    Uses pandas-ta for indicator computation (no TA-Lib C dependency required).
    """

    def __init__(self) -> None:
        self._cache: dict[str, dict] = {}

    async def analyse(
        self, instrument: str, timeframes: list[str] | None = None
    ) -> dict:
        if timeframes is None:
            timeframes = ["M15", "H1", "H4", "D1"]

        results = {}
        for tf in timeframes:
            try:
                df = await self._get_ohlcv(instrument, tf)
                results[tf] = self._compute_indicators(df)
            except Exception as exc:
                logger.warning(f"[TA] Failed {instrument} {tf}: {exc}")
                results[tf] = {"error": str(exc)}

        # Overall confluence
        bias, strength = self._confluence(results)
        return {
            "instrument": instrument,
            "analysed_at": datetime.now(timezone.utc).isoformat(),
            "timeframes": results,
            "overall_bias": bias,
            "ta_score": round(strength, 4),
        }

    async def get_price_data(self, instrument: str, timeframe: str = "H1") -> dict:
        from core.bridge.oanda_client import DRY_RUN_PRICES
        try:
            df = await self._get_ohlcv(instrument, timeframe)
            latest = df.iloc[-1]
            mid = float(latest["close"])
            return {
                "instrument": instrument,
                "timeframe": timeframe,
                "bid": mid - 0.00005,
                "ask": mid + 0.00005,
                "high_24h": float(df.tail(24)["high"].max()),
                "low_24h": float(df.tail(24)["low"].min()),
                "last_candles": df.tail(20)[["open", "high", "low", "close", "volume"]].to_dict("records"),
            }
        except Exception as exc:
            logger.warning(f"[TA] get_price_data fallback for {instrument}: {exc}")
            mid = DRY_RUN_PRICES.get(instrument, 1.09000)
            return {
                "instrument": instrument,
                "timeframe": timeframe,
                "bid": mid - 0.00005,
                "ask": mid + 0.00005,
                "high_24h": mid * 1.005,
                "low_24h": mid * 0.995,
                "last_candles": [],
            }

    def _compute_indicators(self, df: pd.DataFrame) -> dict:
        c = df["close"]
        h = df["high"]
        l = df["low"]
        v = df.get("volume", pd.Series(dtype=float))

        # ── Trend ──────────────────────────────────────────────────────────────
        ema9 = ta.ema(c, length=9)
        ema21 = ta.ema(c, length=21)
        ema200 = ta.ema(c, length=200)

        # ── Momentum ──────────────────────────────────────────────────────────
        rsi = ta.rsi(c, length=14)
        macd_df = ta.macd(c, fast=12, slow=26, signal=9)
        stoch_df = ta.stoch(h, l, c, k=14, d=3, smooth_k=3)

        # ── Volatility ────────────────────────────────────────────────────────
        atr = ta.atr(h, l, c, length=14)
        bbands = ta.bbands(c, length=20, std=2.0)
        # pandas-ta column names vary by version (e.g. BBU_20_2.0 vs BBU_20_2)
        # Use dynamic lookup so a version mismatch never crashes the whole TF
        bb_upper = self._bb_col(bbands, "BBU")
        bb_middle = self._bb_col(bbands, "BBM")
        bb_lower = self._bb_col(bbands, "BBL")
        bb_bw = self._bb_col(bbands, "BBB")

        # ── Levels ────────────────────────────────────────────────────────────
        pivot = self._pivot_points(df)

        # ── Patterns ──────────────────────────────────────────────────────────
        patterns = self._detect_patterns(df)

        latest_price = float(c.iloc[-1])

        return {
            "price": latest_price,
            "ema": {
                "ema9": self._last(ema9),
                "ema21": self._last(ema21),
                "ema200": self._last(ema200),
                "ema9_above_21": self._last(ema9) > self._last(ema21),
                "price_above_200": latest_price > self._last(ema200),
            },
            "rsi": {
                "value": self._last(rsi),
                "overbought": self._last(rsi) > 70,
                "oversold": self._last(rsi) < 30,
                "momentum": self._last(rsi) - float(rsi.iloc[-5]) if len(rsi) > 5 else 0,
            },
            "macd": {
                "macd": self._last(macd_df["MACD_12_26_9"]) if macd_df is not None else None,
                "signal": self._last(macd_df["MACDs_12_26_9"]) if macd_df is not None else None,
                "histogram": self._last(macd_df["MACDh_12_26_9"]) if macd_df is not None else None,
                "bullish_cross": self._detect_macd_cross(macd_df, bullish=True),
                "bearish_cross": self._detect_macd_cross(macd_df, bullish=False),
            },
            "stochastic": {
                "k": self._last(stoch_df["STOCHk_14_3_3"]) if stoch_df is not None else None,
                "d": self._last(stoch_df["STOCHd_14_3_3"]) if stoch_df is not None else None,
            },
            "atr": self._last(atr),
            "bollinger": {
                "upper": self._last(bb_upper),
                "middle": self._last(bb_middle),
                "lower": self._last(bb_lower),
                "bandwidth": self._last(bb_bw),
            },
            "pivots": pivot,
            "patterns": patterns,
        }

    def _confluence(self, tf_results: dict) -> tuple[str, float]:
        """Score overall TA confluence across timeframes."""
        bull_votes = 0
        bear_votes = 0
        total = 0

        weights = {"M15": 0.10, "H1": 0.25, "H4": 0.40, "D1": 0.25}

        for tf, data in tf_results.items():
            if "error" in data:
                continue
            w = weights.get(tf, 0.25)
            total += w

            ema = data.get("ema", {})
            rsi = data.get("rsi", {})
            macd = data.get("macd", {})

            # Accumulate sub-scores per TF (0–2 possible), then normalise to w
            tf_bull = 0.0
            tf_bear = 0.0

            # EMA trend (weight 1.0)
            if ema.get("ema9_above_21") and ema.get("price_above_200"):
                tf_bull += 1.0
            elif not ema.get("ema9_above_21") and not ema.get("price_above_200"):
                tf_bear += 1.0

            # RSI (weight 0.5)
            rsi_val = rsi.get("value", 50)
            if 45 < rsi_val < 70 and rsi.get("momentum", 0) > 0:
                tf_bull += 0.5
            elif 30 < rsi_val < 55 and rsi.get("momentum", 0) < 0:
                tf_bear += 0.5

            # MACD (weight 0.5)
            if macd.get("bullish_cross"):
                tf_bull += 0.5
            elif macd.get("bearish_cross"):
                tf_bear += 0.5

            # Normalise each TF contribution to max w (divide by 2.0 = max sub-score)
            bull_votes += w * (tf_bull / 2.0)
            bear_votes += w * (tf_bear / 2.0)

        if total == 0:
            return "neutral", 0.5

        bull_score = bull_votes / total   # now in [0.0, 1.0]
        bear_score = bear_votes / total

        if bull_score > bear_score + 0.15:
            return "bullish", round(0.5 + bull_score * 0.5, 4)
        elif bear_score > bull_score + 0.15:
            return "bearish", round(0.5 + bear_score * 0.5, 4)
        else:
            return "neutral", 0.5

    def _detect_patterns(self, df: pd.DataFrame) -> list[str]:
        patterns = []
        o, h, l, c = df["open"], df["high"], df["low"], df["close"]

        if len(df) < 3:
            return patterns

        # Bullish engulfing
        if (c.iloc[-2] < o.iloc[-2] and  # prev bearish
                c.iloc[-1] > o.iloc[-1] and  # curr bullish
                o.iloc[-1] < c.iloc[-2] and
                c.iloc[-1] > o.iloc[-2]):
            patterns.append("bullish_engulfing")

        # Bearish engulfing
        if (c.iloc[-2] > o.iloc[-2] and
                c.iloc[-1] < o.iloc[-1] and
                o.iloc[-1] > c.iloc[-2] and
                c.iloc[-1] < o.iloc[-2]):
            patterns.append("bearish_engulfing")

        # Doji
        body = abs(c.iloc[-1] - o.iloc[-1])
        candle_range = h.iloc[-1] - l.iloc[-1]
        if candle_range > 0 and body / candle_range < 0.1:
            patterns.append("doji")

        # Inside bar
        if h.iloc[-1] < h.iloc[-2] and l.iloc[-1] > l.iloc[-2]:
            patterns.append("inside_bar")

        return patterns

    def _pivot_points(self, df: pd.DataFrame) -> dict:
        prev = df.iloc[-2] if len(df) > 1 else df.iloc[-1]
        pivot = (float(prev["high"]) + float(prev["low"]) + float(prev["close"])) / 3
        r1 = 2 * pivot - float(prev["low"])
        s1 = 2 * pivot - float(prev["high"])
        r2 = pivot + (float(prev["high"]) - float(prev["low"]))
        s2 = pivot - (float(prev["high"]) - float(prev["low"]))
        return {"pivot": pivot, "r1": r1, "r2": r2, "s1": s1, "s2": s2}

    def _detect_macd_cross(
        self, macd_df: pd.DataFrame | None, bullish: bool
    ) -> bool:
        if macd_df is None or len(macd_df) < 2:
            return False
        macd = macd_df["MACD_12_26_9"]
        sig = macd_df["MACDs_12_26_9"]
        if bullish:
            return bool(macd.iloc[-2] < sig.iloc[-2] and macd.iloc[-1] > sig.iloc[-1])
        return bool(macd.iloc[-2] > sig.iloc[-2] and macd.iloc[-1] < sig.iloc[-1])

    @staticmethod
    def _bb_col(bbands: pd.DataFrame | None, prefix: str) -> pd.Series | None:
        """Return the first Bollinger Band column matching a prefix (e.g. 'BBU').
        Handles version-dependent column names like BBU_20_2.0 vs BBU_20_2."""
        if bbands is None:
            return None
        matches = [c for c in bbands.columns if str(c).startswith(prefix)]
        return bbands[matches[0]] if matches else None

    @staticmethod
    def _last(series: pd.Series | None) -> float | None:
        if series is None or series.empty:
            return None
        val = series.dropna()
        return float(val.iloc[-1]) if not val.empty else None

    async def _get_ohlcv(self, instrument: str, timeframe: str) -> pd.DataFrame:
        """
        Fetch OHLCV data.
        Primary: OANDA REST candles API (live instrument-accurate data).
        Fallback: Yahoo Finance (free, slightly delayed, good enough for M1H+).
        Raises RuntimeError if both fail — never returns synthetic data.
        """
        # ── Primary: OANDA candles ────────────────────────────────────────────
        try:
            df = await self._fetch_oanda_candles(instrument, timeframe)
            if df is not None and len(df) >= 50:
                return df
        except Exception as exc:
            logger.warning(f"[OHLCV] OANDA candles failed for {instrument} {timeframe}: {exc}")

        # ── Fallback: yfinance ─────────────────────────────────────────────────
        try:
            import yfinance as yf
            tf_map = {"M15": "15m", "H1": "1h", "H4": "4h", "D1": "1d"}
            period_map = {"M15": "5d", "H1": "60d", "H4": "180d", "D1": "365d"}
            sym_map = {
                "EURUSD": "EURUSD=X", "GBPUSD": "GBPUSD=X", "USDJPY": "JPY=X",
                "AUDUSD": "AUDUSD=X", "USDCAD": "CAD=X",    "NZDUSD": "NZDUSD=X",
                "USDCHF": "CHF=X",    "EURJPY": "EURJPY=X", "GBPJPY": "GBPJPY=X",
                "XAUUSD": "GC=F",     "XAGUSD": "SI=F",     "USOIL":  "CL=F",
                "UKOIL":  "BZ=F",     "NATGAS": "NG=F",
            }
            ticker = sym_map.get(instrument, f"{instrument}=X")
            df = yf.download(
                ticker,
                period=period_map.get(timeframe, "60d"),
                interval=tf_map.get(timeframe, "1h"),
                progress=False,
                auto_adjust=True,
            )
            if df is not None and len(df) >= 50:
                # yfinance >= 0.2 returns MultiIndex columns like ('Close', 'EURUSD=X')
                # Flatten to single level before lowercasing
                if hasattr(df.columns, 'levels'):
                    df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
                df.columns = [str(c).lower() for c in df.columns]
                # Ensure required columns exist
                required = {"open", "high", "low", "close"}
                if not required.issubset(set(df.columns)):
                    logger.warning(f"[OHLCV] yfinance missing columns for {instrument}: {list(df.columns)}")
                else:
                    if "volume" not in df.columns:
                        df["volume"] = 0.0
                    logger.info(f"[OHLCV] yfinance fallback used for {instrument} {timeframe} ({len(df)} bars)")
                    return df.dropna(subset=["open", "high", "low", "close"])
        except Exception as exc:
            logger.error(f"[OHLCV] yfinance also failed for {instrument} {timeframe}: {exc}")

        # ── Fallback 3: Stooq (free, no auth, reliable FX/commodity CSVs) ────────
        try:
            df = await self._fetch_stooq(instrument, timeframe)
            if df is not None and len(df) >= 50:
                return df
        except Exception as exc:
            logger.error(f"[OHLCV] Stooq also failed for {instrument} {timeframe}: {exc}")

        # ── All three failed — refuse to trade on fake data ────────────────────
        raise RuntimeError(
            f"No OHLCV data available for {instrument} {timeframe} — "
            f"OANDA and yfinance both failed. Refusing to use synthetic data."
        )

    async def _fetch_oanda_candles(self, instrument: str, timeframe: str) -> pd.DataFrame | None:
        """Fetch candles directly from OANDA REST API."""
        import os, httpx
        api_key    = os.environ.get("OANDA_API_KEY", "")
        account_id = os.environ.get("OANDA_ACCOUNT_ID", "")
        is_live    = os.environ.get("OANDA_LIVE", "false").lower() == "true"

        if not api_key:
            return None  # No API key — fall through to yfinance
        # account_id is NOT required for the public candles endpoint

        base_url = "https://api-fxtrade.oanda.com" if is_live else "https://api-fxpractice.oanda.com"

        # OANDA granularity mapping
        gran_map = {"M15": "M15", "H1": "H1", "H4": "H4", "D1": "D"}
        count_map = {"M15": 400, "H1": 500, "H4": 400, "D1": 365}

        from core.bridge.oanda_client import INSTRUMENT_MAP
        oanda_sym = INSTRUMENT_MAP.get(instrument, instrument.replace("USD", "_USD"))
        granularity = gran_map.get(timeframe, "H1")
        count       = count_map.get(timeframe, 500)

        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(
                f"{base_url}/v3/instruments/{oanda_sym}/candles",
                headers={"Authorization": f"Bearer {api_key}"},
                params={"granularity": granularity, "count": count, "price": "M"},
            )
            r.raise_for_status()
            candles = r.json().get("candles", [])

        if not candles:
            return None

        rows = []
        for c in candles:
            if c.get("complete", True):
                m = c["mid"]
                rows.append({
                    "open":   float(m["o"]),
                    "high":   float(m["h"]),
                    "low":    float(m["l"]),
                    "close":  float(m["c"]),
                    "volume": float(c.get("volume", 0)),
                })

        return pd.DataFrame(rows) if rows else None

    async def _fetch_stooq(self, instrument: str, timeframe: str) -> pd.DataFrame | None:
        """
        Stooq.com free historical data — no auth required.
        Covers FX, indices, commodities. Data is end-of-day or intraday depending on instrument.
        URL: https://stooq.com/q/d/l/?s=<symbol>&i=<interval>
        Interval: d=daily, w=weekly (no intraday for FX on Stooq)
        For intraday we use daily bars and treat them as D1 equivalent.
        """
        import io
        import aiohttp

        stooq_map = {
            "EURUSD": "eurusd", "GBPUSD": "gbpusd", "USDJPY": "usdjpy",
            "AUDUSD": "audusd", "USDCAD": "usdcad", "NZDUSD": "nzdusd",
            "USDCHF": "usdchf", "EURJPY": "eurjpy", "GBPJPY": "gbpjpy",
            "XAUUSD": "xauusd", "XAGUSD": "xagusd",
            "USOIL":  "cl.f",   "UKOIL":  "bz.f",   "NATGAS": "ng.f",
        }
        sym = stooq_map.get(instrument)
        if not sym:
            return None

        url = f"https://stooq.com/q/d/l/?s={sym}&i=d"
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=15),
            headers={"User-Agent": "Mozilla/5.0 (compatible; NVC-Trader/1.0)"},
        ) as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return None
                text = await resp.text()

        if not text or "No data" in text or len(text) < 100:
            return None

        df = pd.read_csv(io.StringIO(text))
        df.columns = [c.strip().lower() for c in df.columns]

        # Stooq columns: date, open, high, low, close, volume
        col_map = {"date": "date", "open": "open", "high": "high", "low": "low",
                   "close": "close", "vol": "volume", "volume": "volume"}
        df = df.rename(columns={c: col_map.get(c, c) for c in df.columns})

        required = {"open", "high", "low", "close"}
        if not required.issubset(set(df.columns)):
            return None

        if "volume" not in df.columns:
            df["volume"] = 0.0

        df = df[["open", "high", "low", "close", "volume"]].dropna()
        if len(df) >= 50:
            logger.info(f"[OHLCV] Stooq fallback used for {instrument} {timeframe} ({len(df)} bars)")
        return df if len(df) >= 50 else None
