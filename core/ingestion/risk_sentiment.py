"""
Risk Sentiment Proxy via Equity Markets.

Tesla (TSLA) and S&P 500 (SPX) are used as leading indicators of global
risk appetite — they move before FX markets react.

Why Tesla specifically:
  - Highest-beta large-cap: amplifies risk-on/off moves more than any index
  - Elon Musk effect: macro announcements + geopolitical stance move it first
  - Retail crowding: retail overweight TSLA → TSLA direction = retail mood
  - 5-day TSLA return >+5% = strong risk-on → AUD/NZD/CAD outperform, USD weakens
  - 5-day TSLA return <-5% = risk-off → JPY/CHF/XAU rally, commodity pairs fall

JP Morgan (JPM) specifically:
  - World's largest FX dealer (~10% of all FX volume)
  - JPM moves when banks are healthy → signals credit conditions are benign
  - JPM crash = credit stress = risk-off = USD/JPY/CHF bid

Data source: Yahoo Finance public API (no auth required).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Optional
import aiohttp
from loguru import logger

# Tickers to track
RISK_TICKERS = {
    "TSLA":  {"weight": 0.45, "role": "risk_barometer",   "name": "Tesla"},
    "^GSPC": {"weight": 0.35, "role": "broad_market",     "name": "S&P 500"},
    "JPM":   {"weight": 0.20, "role": "credit_conditions", "name": "JP Morgan Chase"},
}

# Cache: ticker → (fetched_at, data)
_CACHE: dict[str, tuple[datetime, dict]] = {}
_TTL_SECONDS = 300  # 5 min


# FX pairs whose direction correlates with risk appetite
RISK_ON_PAIRS  = {"AUDUSD", "NZDUSD", "USDCAD", "GBPUSD"}   # risk-on = these go UP (except USDCAD)
RISK_OFF_PAIRS = {"USDJPY", "USDCHF", "XAUUSD"}              # risk-off = these go UP


class RiskSentimentReader:
    """
    Fetches real-time risk appetite score from TSLA, SPX, and JPM.
    Outputs a score and directional bias usable by the confluence engine.
    """

    async def get_risk_appetite(self) -> dict:
        """
        Returns:
        {
            risk_appetite:     "HIGH" | "LOW" | "NEUTRAL",
            score:             0.0 – 1.0   (0.0 = extreme risk-off, 1.0 = extreme risk-on)
            tsla_5d_return:    float (%)
            spx_5d_return:     float (%)
            jpm_5d_return:     float (%)
            signal_for_pair:   dict[instrument → "aligned" | "counter" | "neutral"]
            note:              human-readable summary
            source:            "live" | "cache" | "fallback"
        }
        """
        results = await asyncio.gather(
            *[self._fetch_ticker(ticker) for ticker in RISK_TICKERS],
            return_exceptions=True,
        )

        ticker_data: dict[str, dict] = {}
        for ticker, result in zip(RISK_TICKERS, results):
            if isinstance(result, dict):
                ticker_data[ticker] = result

        if not ticker_data:
            return self._fallback()

        # Weighted composite score: each ticker's 5d return mapped to [0, 1]
        composite = 0.0
        total_weight = 0.0
        returns: dict[str, float] = {}

        for ticker, info in RISK_TICKERS.items():
            data = ticker_data.get(ticker)
            if not data:
                continue
            ret = data.get("return_5d", 0.0)
            returns[ticker] = ret

            # Map return to score: -10% → 0.0, 0% → 0.5, +10% → 1.0
            score = max(0.0, min(1.0, (ret + 10.0) / 20.0))
            composite += score * info["weight"]
            total_weight += info["weight"]

        if total_weight == 0:
            return self._fallback()

        composite /= total_weight
        composite = round(composite, 4)

        # Classify
        if composite >= 0.65:
            appetite = "HIGH"
        elif composite <= 0.35:
            appetite = "LOW"
        else:
            appetite = "NEUTRAL"

        # Per-instrument signal alignment
        signal_for_pair: dict[str, str] = {}
        for pair in {**{p: True for p in RISK_ON_PAIRS}, **{p: True for p in RISK_OFF_PAIRS}}:
            if pair in RISK_ON_PAIRS:
                if appetite == "HIGH":
                    signal_for_pair[pair] = "aligned_BUY" if pair != "USDCAD" else "aligned_SELL"
                elif appetite == "LOW":
                    signal_for_pair[pair] = "aligned_SELL" if pair != "USDCAD" else "aligned_BUY"
                else:
                    signal_for_pair[pair] = "neutral"
            else:  # risk-off pairs
                if appetite == "LOW":
                    signal_for_pair[pair] = "aligned_BUY"
                elif appetite == "HIGH":
                    signal_for_pair[pair] = "aligned_SELL"
                else:
                    signal_for_pair[pair] = "neutral"

        tsla_ret = returns.get("TSLA", 0.0)
        spx_ret  = returns.get("^GSPC", 0.0)
        jpm_ret  = returns.get("JPM", 0.0)

        note = (
            f"TSLA {tsla_ret:+.1f}% / SPX {spx_ret:+.1f}% / JPM {jpm_ret:+.1f}% "
            f"→ risk appetite {appetite} (score {composite:.2f})"
        )
        logger.debug(f"[RiskSentiment] {note}")

        return {
            "risk_appetite":    appetite,
            "score":            composite,
            "tsla_5d_return":   round(tsla_ret, 2),
            "spx_5d_return":    round(spx_ret, 2),
            "jpm_5d_return":    round(jpm_ret, 2),
            "signal_for_pair":  signal_for_pair,
            "note":             note,
            "source":           "live",
        }

    async def get_jpm_outlook(self) -> dict:
        """
        Returns JP Morgan's implied market view from their stock price action:
        - JPM rising  → banks pricing in benign credit, healthy economy
        - JPM falling → credit stress, tightening conditions, risk-off
        Also includes hard-coded 2026 JPM analyst FX price targets (public record).
        """
        jpm_data = await self._fetch_ticker("JPM")
        ret = jpm_data.get("return_5d", 0.0) if jpm_data else 0.0

        credit_signal = "BENIGN" if ret > 2.0 else "STRESSED" if ret < -2.0 else "NEUTRAL"

        return {
            "jpm_5d_return":  round(ret, 2),
            "credit_signal":  credit_signal,
            # JPM 2026 published FX targets (public analyst notes, Q1 2026)
            "fx_targets": {
                "EURUSD": {"target": 1.20, "bias": "BUY",  "note": "ECB/Fed divergence unwind"},
                "GBPUSD": {"target": 1.36, "bias": "BUY",  "note": "BoE dovish lag to correct"},
                "USDJPY": {"target": 164,  "bias": "SELL", "note": "BoJ normalisation trajectory"},
                "XAUUSD": {"target": 3200, "bias": "BUY",  "note": "Central bank accumulation"},
            },
            "note": f"JPM stock {ret:+.1f}% 5d → credit conditions {credit_signal}",
        }

    # ── Internal ──────────────────────────────────────────────────────────────

    async def _fetch_ticker(self, ticker: str) -> dict:
        now = datetime.now(timezone.utc)
        cached = _CACHE.get(ticker)
        if cached and (now - cached[0]).total_seconds() < _TTL_SECONDS:
            return cached[1]

        url = (
            f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
            f"?interval=1d&range=7d"
        )
        try:
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=10),
                headers={"User-Agent": "Mozilla/5.0 (compatible; NVC-Trader/1.0)"},
            ) as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        return {}
                    data = await resp.json()

            chart   = data.get("chart", {})
            result  = (chart.get("result") or [{}])[0]
            closes  = (result.get("indicators", {})
                             .get("quote", [{}])[0]
                             .get("close", []))

            # Filter out None values
            closes = [c for c in closes if c is not None]
            if len(closes) < 2:
                return {}

            ret_5d = round((closes[-1] - closes[0]) / closes[0] * 100, 3)
            ret_1d = round((closes[-1] - closes[-2]) / closes[-2] * 100, 3)

            result_data = {
                "ticker":      ticker,
                "last_close":  round(closes[-1], 4),
                "return_5d":   ret_5d,
                "return_1d":   ret_1d,
                "fetched_at":  now.isoformat(),
            }
            _CACHE[ticker] = (now, result_data)
            return result_data

        except Exception as e:
            logger.debug(f"[RiskSentiment] {ticker}: {e}")
            return {}

    @staticmethod
    def _fallback() -> dict:
        return {
            "risk_appetite":   "NEUTRAL",
            "score":           0.5,
            "tsla_5d_return":  0.0,
            "spx_5d_return":   0.0,
            "jpm_5d_return":   0.0,
            "signal_for_pair": {},
            "note":            "Risk sentiment unavailable — defaulting to NEUTRAL",
            "source":          "fallback",
        }
