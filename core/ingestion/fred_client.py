"""
FRED (Federal Reserve Economic Data) Client.
Pulls macroeconomic data that drives currency and commodity trends.

Key series used:
  - DFF:    Fed Funds Rate (overnight)
  - DFEDTARU / DFEDTARL: Fed target range
  - T10Y2Y: 10Y-2Y yield curve spread (negative = recession signal)
  - T10YIE: 10Y Breakeven Inflation (inflation expectations)
  - CPIAUCSL: CPI All Urban (YoY → computed)
  - UNRATE:  Unemployment Rate
  - DEXJPUS, DEXUSUK etc: Spot rates for cross-checks
  - GOLDAMGBD228NLBM: Gold price (London fix)
  - DCOILWTICO: WTI Crude Oil
  - MORTGAGE30US: 30Y mortgage rate (USD demand indicator)

FRED API key is free: fred.stlouisfed.org/docs/api/api_key.html
If key not set, returns cached/estimated values with a warning.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone, timedelta
from typing import Optional
import aiohttp
from loguru import logger

FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"

# Series → human label + which currency pair it most influences
MACRO_SERIES = {
    "DFF":          {"label": "Fed Funds Rate",              "currency": "USD"},
    "T10Y2Y":       {"label": "10Y-2Y Yield Curve Spread",   "currency": "USD"},
    "T10YIE":       {"label": "10Y Breakeven Inflation",     "currency": "USD"},
    "CPIAUCSL":     {"label": "US CPI (All Urban)",          "currency": "USD"},
    "UNRATE":       {"label": "US Unemployment Rate",        "currency": "USD"},
    "FEDFUNDS":     {"label": "Effective Fed Funds Rate",    "currency": "USD"},
    "IRLTLT01EZM156N": {"label": "Euro Area Long-Term Rate", "currency": "EUR"},
    "IRSTCI01GBM156N": {"label": "UK Policy Rate",          "currency": "GBP"},
    "IRSTCI01JPM156N": {"label": "Japan Policy Rate",       "currency": "JPY"},
}

# Rate differential pairs: (series_a, series_b) → instrument it affects
RATE_DIFF_PAIRS = {
    "EURUSD": ("IRLTLT01EZM156N", "DFF"),
    "GBPUSD": ("IRSTCI01GBM156N", "DFF"),
    "USDJPY": ("DFF", "IRSTCI01JPM156N"),
}

_CACHE: dict[str, tuple[datetime, float]] = {}
_TTL_HOURS = 6


class FREDClient:
    """Pulls macro data from St. Louis Fed FRED API."""

    def __init__(self) -> None:
        self.api_key = os.getenv("FRED_API_KEY", "")

    async def get_macro_environment(self, instruments: list[str] | None = None) -> dict:
        """
        Returns macro snapshot:
        {
          fed_funds_rate, yield_curve_spread, inflation_expectations,
          cpi_yoy, unemployment_rate,
          rate_differentials: { EURUSD: 0.45, GBPUSD: -0.12, ... },
          yield_curve_signal: NORMAL / FLAT / INVERTED,
          usd_bias: HAWKISH / DOVISH / NEUTRAL,
          recession_risk: LOW / MEDIUM / HIGH,
          key_events: [ "Fed meeting next week", "CPI release tomorrow" ],
        }
        """
        if not self.api_key:
            return self._estimated_environment()

        # Fetch key series concurrently
        import asyncio
        series_to_fetch = ["DFF", "T10Y2Y", "T10YIE", "CPIAUCSL", "UNRATE"]
        tasks = [self._get_latest(s) for s in series_to_fetch]
        values = await asyncio.gather(*tasks, return_exceptions=True)
        data = {
            s: v if not isinstance(v, Exception) else None
            for s, v in zip(series_to_fetch, values)
        }

        fed_rate       = data.get("DFF")
        yield_curve    = data.get("T10Y2Y")
        inflation_exp  = data.get("T10YIE")
        cpi            = data.get("CPIAUCSL")
        unemployment   = data.get("UNRATE")

        # Yield curve signal
        if yield_curve is not None:
            if yield_curve < -0.5:
                yc_signal = "INVERTED"
                recession_risk = "HIGH"
            elif yield_curve < 0:
                yc_signal = "FLAT"
                recession_risk = "MEDIUM"
            else:
                yc_signal = "NORMAL"
                recession_risk = "LOW"
        else:
            yc_signal      = "UNKNOWN"
            recession_risk = "UNKNOWN"

        # USD bias based on fed rate vs inflation
        usd_bias = "NEUTRAL"
        if fed_rate and inflation_exp:
            real_rate = fed_rate - inflation_exp
            if real_rate > 0.5:
                usd_bias = "HAWKISH"      # real rates positive → USD bullish
            elif real_rate < -0.5:
                usd_bias = "DOVISH"       # negative real rates → USD bearish

        # Rate differentials
        rate_diffs: dict[str, float] = {}
        if instruments:
            for sym in instruments:
                pair = RATE_DIFF_PAIRS.get(sym)
                if pair:
                    r_a = await self._get_latest(pair[0])
                    r_b = await self._get_latest(pair[1])
                    if r_a is not None and r_b is not None:
                        rate_diffs[sym] = round(r_a - r_b, 3)

        return {
            "fed_funds_rate":       fed_rate,
            "yield_curve_spread":   yield_curve,
            "inflation_expectations": inflation_exp,
            "unemployment_rate":    unemployment,
            "yield_curve_signal":   yc_signal,
            "usd_bias":             usd_bias,
            "recession_risk":       recession_risk,
            "rate_differentials":   rate_diffs,
            "data_source":          "FRED",
            "fetched_at":           datetime.now(timezone.utc).isoformat(),
        }

    async def get_rate_differential(self, instrument: str) -> Optional[float]:
        """Returns interest rate differential for a pair (positive = favours base)."""
        pair = RATE_DIFF_PAIRS.get(instrument)
        if not pair or not self.api_key:
            return None
        r_a = await self._get_latest(pair[0])
        r_b = await self._get_latest(pair[1])
        if r_a is not None and r_b is not None:
            return round(r_a - r_b, 3)
        return None

    # ── Internal ──────────────────────────────────────────────────────────────

    async def _get_latest(self, series_id: str) -> Optional[float]:
        """Fetch the most recent observation for a FRED series."""
        now = datetime.now(timezone.utc)
        cached = _CACHE.get(series_id)
        if cached and (now - cached[0]).total_seconds() < _TTL_HOURS * 3600:
            return cached[1]

        try:
            params = {
                "series_id":       series_id,
                "api_key":         self.api_key,
                "file_type":       "json",
                "sort_order":      "desc",
                "limit":           "5",
                "observation_start": (now - timedelta(days=90)).strftime("%Y-%m-%d"),
            }
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=10)
            ) as session:
                async with session.get(FRED_BASE, params=params) as resp:
                    resp.raise_for_status()
                    data = await resp.json()

            obs = [o for o in data.get("observations", []) if o.get("value") not in (".", "")]
            if not obs:
                return None

            val = float(obs[0]["value"])
            _CACHE[series_id] = (now, val)
            return val
        except Exception as e:
            logger.debug(f"[FRED] {series_id}: {e}")
            return None

    @staticmethod
    def _estimated_environment() -> dict:
        """Return estimated macro context when FRED key not available."""
        return {
            "fed_funds_rate":         5.25,
            "yield_curve_spread":     -0.3,
            "inflation_expectations": 2.4,
            "unemployment_rate":      3.9,
            "yield_curve_signal":     "FLAT",
            "usd_bias":               "HAWKISH",
            "recession_risk":         "MEDIUM",
            "rate_differentials":     {},
            "data_source":            "estimated (no FRED_API_KEY set)",
            "fetched_at":             datetime.now(timezone.utc).isoformat(),
        }
