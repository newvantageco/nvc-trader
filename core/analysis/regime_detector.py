"""
Market Regime Detector.

THE most important edge: don't trade in the wrong regime.

Trending strategies in ranging markets = death by a thousand small losses.
Mean-reversion in a trending market = fighting a freight train.

Four regimes:
  TRENDING_BULLISH  — ADX > 25, +DI > -DI, EMA aligned up
  TRENDING_BEARISH  — ADX > 25, -DI > +DI, EMA aligned down
  RANGING           — ADX < 20, price oscillating inside a band
  VOLATILE          — ATR > 2× 20-period ATR average (news spikes, breakouts forming)

Additional regime overlays:
  EXHAUSTED         — ADX > 40 AND declining for 5+ bars (trend ending)
  BREAKOUT          — price pierces 20-period high/low WITH volume
  ACCUMULATION      — declining volume + tightening range (coiling before move)

Strategy routing:
  TRENDING  → momentum entries, wide stops, trail aggressively
  RANGING   → mean reversion, tight stops, fade extremes
  VOLATILE  → reduce size 50%, only trade with news/event catalyst
  EXHAUSTED → close trend trades, prepare for reversal
  BREAKOUT  → enter immediately with momentum, tight initial stop
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Optional
from loguru import logger

try:
    import pandas as pd
    import numpy as np
    import pandas_ta as ta
    HAS_TA = True
except ImportError:
    HAS_TA = False

_CACHE: dict[str, tuple[datetime, dict]] = {}
_TTL_SECONDS = 300   # 5-min cache


class RegimeDetector:
    """Classifies market regime from OHLCV data."""

    async def detect(self, instrument: str, ohlcv: list[dict] | None = None) -> dict:
        """
        Returns:
        {
          regime: TRENDING_BULLISH | TRENDING_BEARISH | RANGING | VOLATILE | EXHAUSTED | BREAKOUT,
          adx, plus_di, minus_di,
          atr, atr_avg, atr_ratio,
          trend_strength: 0.0–1.0,
          tradeable: bool,
          strategy_hint: str,
          confidence: 0.0–1.0,
        }
        """
        now = datetime.now(timezone.utc)
        cached = _CACHE.get(instrument)
        if cached and (now - cached[0]).total_seconds() < _TTL_SECONDS:
            return cached[1]

        if not HAS_TA or not ohlcv:
            result = self._default_regime(instrument)
            _CACHE[instrument] = (now, result)
            return result

        try:
            result = self._analyse(instrument, ohlcv)
            _CACHE[instrument] = (now, result)
            return result
        except Exception as e:
            logger.warning(f"[Regime] {instrument}: {e}")
            return self._default_regime(instrument)

    def _analyse(self, instrument: str, ohlcv: list[dict]) -> dict:
        df = pd.DataFrame(ohlcv)
        if len(df) < 30:
            return self._default_regime(instrument)

        # Ensure required columns
        for col in ["high", "low", "close", "volume"]:
            if col not in df.columns:
                return self._default_regime(instrument)

        # Convert to float
        for col in ["open", "high", "low", "close"]:
            if col in df.columns:
                df[col] = df[col].astype(float)

        # ── ADX / DMI ─────────────────────────────────────────────────────────
        adx_data   = ta.adx(df["high"], df["low"], df["close"], length=14)
        if adx_data is None or adx_data.empty:
            return self._default_regime(instrument)

        adx_col     = [c for c in adx_data.columns if c.startswith("ADX_")][0]
        dmp_col     = [c for c in adx_data.columns if c.startswith("DMP_")][0]
        dmn_col     = [c for c in adx_data.columns if c.startswith("DMN_")][0]

        adx         = float(adx_data[adx_col].iloc[-1])
        plus_di     = float(adx_data[dmp_col].iloc[-1])
        minus_di    = float(adx_data[dmn_col].iloc[-1])

        # ADX trend: is it rising or falling?
        adx_5ago    = float(adx_data[adx_col].iloc[-6]) if len(adx_data) > 6 else adx
        adx_rising  = adx > adx_5ago

        # ── ATR ───────────────────────────────────────────────────────────────
        atr_s       = ta.atr(df["high"], df["low"], df["close"], length=14)
        atr         = float(atr_s.iloc[-1]) if atr_s is not None else 0
        atr_avg     = float(atr_s.rolling(20).mean().iloc[-1]) if atr_s is not None else atr
        atr_ratio   = atr / atr_avg if atr_avg > 0 else 1.0

        # ── EMA alignment ─────────────────────────────────────────────────────
        ema9   = ta.ema(df["close"], length=9)
        ema21  = ta.ema(df["close"], length=21)
        ema200 = ta.ema(df["close"], length=200)

        price    = float(df["close"].iloc[-1])
        e9       = float(ema9.iloc[-1])  if ema9  is not None else price
        e21      = float(ema21.iloc[-1]) if ema21 is not None else price
        e200     = float(ema200.iloc[-1]) if ema200 is not None and not pd.isna(ema200.iloc[-1]) else price

        ema_bullish = e9 > e21 > e200 and price > e200
        ema_bearish = e9 < e21 < e200 and price < e200

        # ── 20-bar high/low (breakout detection) ──────────────────────────────
        high_20 = float(df["high"].rolling(20).max().iloc[-2])   # previous bar's 20-bar high
        low_20  = float(df["low"].rolling(20).min().iloc[-2])
        is_breakout_up   = price > high_20
        is_breakout_down = price < low_20

        # ── Classify regime ───────────────────────────────────────────────────
        if adx > 40 and not adx_rising:
            regime   = "EXHAUSTED"
            tradeable = False
            hint     = "Trend exhausting — close trend trades, watch for reversal"
            strength = min((adx - 25) / 30, 1.0)
            conf     = 0.80

        elif is_breakout_up or is_breakout_down:
            regime   = "BREAKOUT"
            tradeable = True
            hint     = f"{'Upside' if is_breakout_up else 'Downside'} breakout of 20-bar range — enter with momentum"
            strength = 0.85
            conf     = 0.75

        elif atr_ratio > 1.8:
            regime   = "VOLATILE"
            tradeable = False   # don't trade volatility spikes without a catalyst
            hint     = f"High volatility (ATR {atr_ratio:.1f}× normal) — reduce size, wait for structure"
            strength = 0.0
            conf     = 0.85

        elif adx > 25:
            if plus_di > minus_di and ema_bullish:
                regime = "TRENDING_BULLISH"
                hint   = f"Strong uptrend (ADX={adx:.0f}) — buy dips, trail stops"
            elif minus_di > plus_di and ema_bearish:
                regime = "TRENDING_BEARISH"
                hint   = f"Strong downtrend (ADX={adx:.0f}) — sell rallies, trail stops"
            else:
                regime = "TRENDING_BULLISH" if plus_di > minus_di else "TRENDING_BEARISH"
                hint   = f"Trending (ADX={adx:.0f}) but EMA not fully aligned — use caution"
            tradeable = True
            strength  = min((adx - 25) / 30, 1.0)
            conf      = 0.80 if ema_bullish or ema_bearish else 0.60

        else:
            regime   = "RANGING"
            tradeable = True   # ranging = mean reversion trades
            hint     = f"Range-bound (ADX={adx:.0f}) — fade extremes, tight stops, RSI divergence"
            strength = 0.3
            conf     = 0.70

        return {
            "instrument":     instrument,
            "regime":         regime,
            "adx":            round(adx, 1),
            "plus_di":        round(plus_di, 1),
            "minus_di":       round(minus_di, 1),
            "atr":            round(atr, 5),
            "atr_ratio":      round(atr_ratio, 2),
            "ema_aligned":    ema_bullish or ema_bearish,
            "trend_strength": round(strength, 2),
            "tradeable":      tradeable,
            "strategy_hint":  hint,
            "confidence":     conf,
        }

    @staticmethod
    def _default_regime(instrument: str) -> dict:
        return {
            "instrument":     instrument,
            "regime":         "RANGING",
            "adx":            0.0,
            "plus_di":        0.0,
            "minus_di":       0.0,
            "atr":            0.0,
            "atr_ratio":      1.0,
            "ema_aligned":    False,
            "trend_strength": 0.3,
            "tradeable":      True,
            "strategy_hint":  "No data — default to RANGING approach",
            "confidence":     0.30,
        }

    # ── Multi-instrument scan ─────────────────────────────────────────────────

    async def scan_regimes(
        self, instruments: list[str], ohlcv_map: dict[str, list[dict]]
    ) -> dict[str, dict]:
        """Classify regime for a list of instruments simultaneously."""
        tasks = [
            self.detect(sym, ohlcv_map.get(sym))
            for sym in instruments
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return {
            sym: r if not isinstance(r, Exception) else self._default_regime(sym)
            for sym, r in zip(instruments, results)
        }
