"""
OANDA Order Book & Open Position Ratio (OPR) Reader.

OANDA exposes two public endpoints that reveal crowd positioning:

1. /v3/instruments/{pair}/orderBook
   Bucketed pending orders (buy limits, sell limits, buy stops, sell stops)
   around the current price. Shows WHERE institutional orders are clustered.

2. /v3/instruments/{pair}/positionBook
   Long vs short position ratio AT each price level.
   The majority of retail traders are wrong at extremes — fade the crowd.

Signals derived:
  - Order walls: large order clusters = support/resistance
  - Long/short ratio: >65% one side = potential reversal zone
  - Divergence from price: price falling but longs increasing = capitulation risk
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Optional
import aiohttp
from loguru import logger

OANDA_BASE = "https://api-fxpractice.oanda.com"   # swap to api-fxtrade for live

# Our symbols → OANDA instrument format
SYMBOL_MAP: dict[str, str] = {
    "EURUSD": "EUR_USD", "GBPUSD": "GBP_USD", "USDJPY": "USD_JPY",
    "AUDUSD": "AUD_USD", "USDCAD": "USD_CAD", "NZDUSD": "NZD_USD",
    "USDCHF": "USD_CHF", "EURJPY": "EUR_JPY", "GBPJPY": "GBP_JPY",
    "XAUUSD": "XAU_USD", "XAGUSD": "XAG_USD",
    "USOIL":  "WTICO_USD", "UKOIL": "BCO_USD",
}

_CACHE: dict[str, tuple[datetime, dict]] = {}
_TTL_SECONDS = 60


class OrderBookReader:
    """Reads OANDA order book and position book data."""

    def __init__(self) -> None:
        self.api_key = os.getenv("OANDA_API_KEY", "")
        self._headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type":  "application/json",
        }

    async def get_order_flow(self, instrument: str) -> dict:
        """
        Returns combined order book + position book analysis:
        {
          instrument,
          long_pct, short_pct,           # % of traders net long/short
          sentiment_signal,              # CROWDED_LONG / CROWDED_SHORT / BALANCED
          top_resistance_levels,         # price levels with heavy sell orders/longs
          top_support_levels,            # price levels with heavy buy orders/shorts
          order_wall_above,              # nearest significant sell wall price
          order_wall_below,              # nearest significant buy wall price
          contrarian_bias,               # FADE_LONGS / FADE_SHORTS / NEUTRAL
          retail_long_pct,               # raw long%
          retail_short_pct,              # raw short%
        }
        """
        now = datetime.now(timezone.utc)
        cached = _CACHE.get(instrument)
        if cached and (now - cached[0]).total_seconds() < _TTL_SECONDS:
            return cached[1]

        oanda_sym = SYMBOL_MAP.get(instrument)
        if not oanda_sym or not self.api_key:
            return self._fallback(instrument)

        try:
            pos_data  = await self._fetch_position_book(oanda_sym)
            ord_data  = await self._fetch_order_book(oanda_sym)
            result    = self._analyse(instrument, pos_data, ord_data)
            _CACHE[instrument] = (now, result)
            return result
        except Exception as e:
            logger.warning(f"[OrderBook] {instrument}: {e}")
            return self._fallback(instrument)

    # ── Fetchers ──────────────────────────────────────────────────────────────

    async def _fetch_position_book(self, oanda_sym: str) -> dict:
        url = f"{OANDA_BASE}/v3/instruments/{oanda_sym}/positionBook"
        async with aiohttp.ClientSession() as s:
            async with s.get(url, headers=self._headers,
                             timeout=aiohttp.ClientTimeout(total=10)) as r:
                r.raise_for_status()
                return await r.json()

    async def _fetch_order_book(self, oanda_sym: str) -> dict:
        url = f"{OANDA_BASE}/v3/instruments/{oanda_sym}/orderBook"
        async with aiohttp.ClientSession() as s:
            async with s.get(url, headers=self._headers,
                             timeout=aiohttp.ClientTimeout(total=10)) as r:
                r.raise_for_status()
                return await r.json()

    # ── Analysis ──────────────────────────────────────────────────────────────

    def _analyse(self, instrument: str, pos_data: dict, ord_data: dict) -> dict:
        # Position book: aggregate long vs short %
        pos_buckets  = pos_data.get("positionBook", {}).get("buckets", [])
        total_long   = sum(float(b.get("longCountPercent",  0)) for b in pos_buckets)
        total_short  = sum(float(b.get("shortCountPercent", 0)) for b in pos_buckets)
        total        = total_long + total_short
        long_pct     = round(total_long  / total * 100, 1) if total else 50.0
        short_pct    = round(total_short / total * 100, 1) if total else 50.0

        # Sentiment signal
        if long_pct >= 65:
            sentiment  = "CROWDED_LONG"
            contrarian = "FADE_LONGS"   # retail crowded long → price likely falls
        elif short_pct >= 65:
            sentiment  = "CROWDED_SHORT"
            contrarian = "FADE_SHORTS"  # retail crowded short → price likely rises
        else:
            sentiment  = "BALANCED"
            contrarian = "NEUTRAL"

        # Order book: find walls (top 5 price levels by combined order %)
        ord_buckets   = ord_data.get("orderBook", {}).get("buckets", [])
        current_price = float(ord_data.get("orderBook", {}).get("price", 0) or 0)

        sell_walls = sorted(
            [(float(b["price"]), float(b.get("shortCountPercent", 0)))
             for b in ord_buckets if float(b.get("shortCountPercent", 0)) > 1.0],
            key=lambda x: -x[1]
        )[:3]

        buy_walls = sorted(
            [(float(b["price"]), float(b.get("longCountPercent", 0)))
             for b in ord_buckets if float(b.get("longCountPercent", 0)) > 1.0],
            key=lambda x: -x[1]
        )[:3]

        order_wall_above = min((p for p, _ in sell_walls if p > current_price),
                               default=None)
        order_wall_below = max((p for p, _ in buy_walls  if p < current_price),
                               default=None)

        return {
            "instrument":        instrument,
            "long_pct":          long_pct,
            "short_pct":         short_pct,
            "sentiment_signal":  sentiment,
            "contrarian_bias":   contrarian,
            "order_wall_above":  order_wall_above,
            "order_wall_below":  order_wall_below,
            "top_sell_walls":    [{"price": p, "pct": round(v, 2)} for p, v in sell_walls],
            "top_buy_walls":     [{"price": p, "pct": round(v, 2)} for p, v in buy_walls],
            "retail_long_pct":   long_pct,
            "retail_short_pct":  short_pct,
            "note": (
                f"{long_pct:.0f}% long / {short_pct:.0f}% short — "
                f"{'contrarian SELL signal' if contrarian == 'FADE_LONGS' else 'contrarian BUY signal' if contrarian == 'FADE_SHORTS' else 'no clear contrarian edge'}"
            ),
        }

    @staticmethod
    def _fallback(instrument: str) -> dict:
        return {
            "instrument":       instrument,
            "long_pct":         50.0,
            "short_pct":        50.0,
            "sentiment_signal": "UNKNOWN",
            "contrarian_bias":  "NEUTRAL",
            "order_wall_above": None,
            "order_wall_below": None,
            "top_sell_walls":   [],
            "top_buy_walls":    [],
            "retail_long_pct":  50.0,
            "retail_short_pct": 50.0,
            "note":             "Order book unavailable",
        }
