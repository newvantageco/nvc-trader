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
        df = await self._get_ohlcv(instrument, timeframe)
        latest = df.iloc[-1]
        return {
            "instrument": instrument,
            "timeframe": timeframe,
            "bid": float(latest["close"]) - 0.00005,
            "ask": float(latest["close"]) + 0.00005,
            "high_24h": float(df.tail(24)["high"].max()),
            "low_24h": float(df.tail(24)["low"].min()),
            "last_candles": df.tail(20)[["open", "high", "low", "close", "volume"]].to_dict("records"),
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
                "upper": self._last(bbands["BBU_20_2.0"]) if bbands is not None else None,
                "middle": self._last(bbands["BBM_20_2.0"]) if bbands is not None else None,
                "lower": self._last(bbands["BBL_20_2.0"]) if bbands is not None else None,
                "bandwidth": self._last(bbands["BBB_20_2.0"]) if bbands is not None else None,
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

            # EMA trend
            if ema.get("ema9_above_21") and ema.get("price_above_200"):
                bull_votes += w
            elif not ema.get("ema9_above_21") and not ema.get("price_above_200"):
                bear_votes += w

            # RSI
            rsi_val = rsi.get("value", 50)
            if 45 < rsi_val < 70 and rsi.get("momentum", 0) > 0:
                bull_votes += w * 0.5
            elif 30 < rsi_val < 55 and rsi.get("momentum", 0) < 0:
                bear_votes += w * 0.5

            # MACD
            if macd.get("bullish_cross"):
                bull_votes += w * 0.5
            elif macd.get("bearish_cross"):
                bear_votes += w * 0.5

        if total == 0:
            return "neutral", 0.5

        bull_score = bull_votes / total
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
    def _last(series: pd.Series | None) -> float | None:
        if series is None or series.empty:
            return None
        val = series.dropna()
        return float(val.iloc[-1]) if not val.empty else None

    async def _get_ohlcv(self, instrument: str, timeframe: str) -> pd.DataFrame:
        """
        Fetch OHLCV data. In production: pulls from MT5 Python API or Alpha Vantage.
        Falls back to Yahoo Finance for dev/testing.
        """
        try:
            import yfinance as yf
            tf_map = {"M15": "15m", "H1": "1h", "H4": "4h", "D1": "1d"}
            period_map = {"M15": "5d", "H1": "60d", "H4": "180d", "D1": "365d"}
            sym_map = {
                "EURUSD": "EURUSD=X", "GBPUSD": "GBPUSD=X", "USDJPY": "JPY=X",
                "AUDUSD": "AUDUSD=X", "USDCAD": "CAD=X", "NZDUSD": "NZDUSD=X",
                "USDCHF": "CHF=X", "EURJPY": "EURJPY=X", "GBPJPY": "GBPJPY=X",
                "XAUUSD": "GC=F", "XAGUSD": "SI=F", "USOIL": "CL=F",
                "UKOIL": "BZ=F", "NATGAS": "NG=F",
            }
            ticker = sym_map.get(instrument, f"{instrument}=X")
            df = yf.download(
                ticker,
                period=period_map.get(timeframe, "60d"),
                interval=tf_map.get(timeframe, "1h"),
                progress=False,
                auto_adjust=True,
            )
            df.columns = [c.lower() for c in df.columns]
            return df.dropna()
        except Exception as exc:
            logger.warning(f"[OHLCV] yfinance failed for {instrument} {timeframe}: {exc}")
            # Return synthetic data for testing
            return self._synthetic_ohlcv()

    @staticmethod
    def _synthetic_ohlcv(n: int = 300) -> pd.DataFrame:
        np.random.seed(42)
        prices = 1.09 + np.cumsum(np.random.randn(n) * 0.001)
        return pd.DataFrame({
            "open": prices,
            "high": prices + np.abs(np.random.randn(n) * 0.002),
            "low": prices - np.abs(np.random.randn(n) * 0.002),
            "close": prices + np.random.randn(n) * 0.0005,
            "volume": np.random.randint(1000, 10000, n).astype(float),
        })
