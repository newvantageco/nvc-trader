"""
CFTC Commitment of Traders (COT) Report Fetcher.

The COT is published every Friday for the preceding Tuesday's data.
It shows NET positions of:
  - Commercial traders (hedgers / large banks / producers)
  - Non-commercial traders (hedge funds / large speculators)
  - Non-reportable (retail)

Non-commercial NET position is the hedge fund signal:
  - Large NET LONG  → institutional bullish bias
  - Large NET SHORT → institutional bearish bias
  - Extreme readings + reversal = contrarian signal (crowded trade unwinding)

Data source: CFTC public data + quandl-style CSV download (no key needed).
"""

from __future__ import annotations

import asyncio
import io
from datetime import datetime, timezone, timedelta
from typing import Optional
import aiohttp
from loguru import logger

# CFTC disaggregated futures-only report (includes Forex + Commodities)
CFTC_CSV_URL = "https://www.cftc.gov/dea/newcot/f_disagg.txt"

# Map our symbols to CFTC market names in the report
SYMBOL_TO_CFTC: dict[str, str] = {
    "EURUSD":  "EURO FX",
    "GBPUSD":  "BRITISH POUND STERLING",
    "USDJPY":  "JAPANESE YEN",
    "AUDUSD":  "AUSTRALIAN DOLLAR",
    "USDCAD":  "CANADIAN DOLLAR",
    "NZDUSD":  "NEW ZEALAND DOLLAR",
    "USDCHF":  "SWISS FRANC",
    "XAUUSD":  "GOLD",
    "XAGUSD":  "SILVER",
    "USOIL":   "CRUDE OIL, LIGHT SWEET",
    "UKOIL":   "BRENT CRUDE OIL",
    "NATGAS":  "NATURAL GAS",
}

# Cache: symbol → (timestamp, result)
_CACHE: dict[str, tuple[datetime, dict]] = {}
_CACHE_TTL_HOURS = 12   # COT is weekly; 12h cache is fine


class COTFetcher:
    """Downloads and parses CFTC COT data for Forex and Commodities."""

    async def get_positioning(self, instrument: str) -> dict:
        """
        Returns COT positioning for an instrument:
        {
          instrument, report_date,
          noncomm_long, noncomm_short, noncomm_net,
          noncomm_net_pct_oi,         # net as % of open interest
          comm_long, comm_short, comm_net,
          open_interest,
          net_change_week,            # change in net from previous week
          positioning_signal,         # BULLISH / BEARISH / NEUTRAL / EXTREME_LONG / EXTREME_SHORT
          crowding_score,             # 0-100 (100 = maximum crowding)
          weeks_of_data,              # how many weeks in the same direction
        }
        """
        now = datetime.now(timezone.utc)
        cached = _CACHE.get(instrument)
        if cached and (now - cached[0]).total_seconds() < _CACHE_TTL_HOURS * 3600:
            return cached[1]

        try:
            raw = await self._fetch_csv()
            result = self._parse(instrument, raw)
            _CACHE[instrument] = (now, result)
            return result
        except Exception as e:
            logger.warning(f"[COT] Failed for {instrument}: {e}")
            return self._empty(instrument)

    async def get_multi(self, instruments: list[str]) -> dict[str, dict]:
        tasks = [self.get_positioning(sym) for sym in instruments]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return {
            sym: r if not isinstance(r, Exception) else self._empty(sym)
            for sym, r in zip(instruments, results)
        }

    # ── Internal ──────────────────────────────────────────────────────────────

    async def _fetch_csv(self) -> str:
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30)
        ) as session:
            async with session.get(CFTC_CSV_URL) as resp:
                resp.raise_for_status()
                return await resp.text(encoding="latin-1")

    def _parse(self, instrument: str, csv_text: str) -> dict:
        cftc_name = SYMBOL_TO_CFTC.get(instrument, "").upper()
        if not cftc_name:
            return self._empty(instrument)

        rows: list[list[str]] = []
        for line in csv_text.splitlines():
            if cftc_name in line.upper():
                rows.append(line.split(","))

        if not rows:
            return self._empty(instrument)

        # Most recent row first (file is usually newest-last, so take last)
        row = rows[-1]
        prev = rows[-2] if len(rows) >= 2 else None

        try:
            report_date = row[2].strip()

            # Columns vary by report but standard disaggregated layout:
            # [12] = Prod/Merch Long  [13] = Prod/Merch Short
            # [16] = Managed Money Long [17] = Managed Money Short
            # [7]  = Non-Commercial Long [8] = Non-Commercial Short
            # [9]  = Non-Commercial Spreading
            # [5]  = Open Interest
            oi          = _int(row[5])
            nc_long     = _int(row[7])
            nc_short    = _int(row[8])
            nc_net      = nc_long - nc_short
            comm_long   = _int(row[12]) if len(row) > 12 else 0
            comm_short  = _int(row[13]) if len(row) > 13 else 0
            comm_net    = comm_long - comm_short

            nc_net_pct  = round(nc_net / oi * 100, 1) if oi else 0.0

            # Week-over-week change
            net_change = 0
            if prev:
                prev_nc_long  = _int(prev[7])
                prev_nc_short = _int(prev[8])
                prev_nc_net   = prev_nc_long - prev_nc_short
                net_change    = nc_net - prev_nc_net

            # Crowding: how extreme is the position vs a ±100k net range
            crowd_raw    = abs(nc_net) / max(oi * 0.3, 1)
            crowding     = min(int(crowd_raw * 100), 100)

            # Signal logic
            if nc_net_pct > 20:
                signal = "EXTREME_LONG"
            elif nc_net_pct > 8:
                signal = "BULLISH"
            elif nc_net_pct < -20:
                signal = "EXTREME_SHORT"
            elif nc_net_pct < -8:
                signal = "BEARISH"
            else:
                signal = "NEUTRAL"

            # If extreme AND reversing, that's a contrarian signal
            if signal in ("EXTREME_LONG", "EXTREME_SHORT") and abs(net_change) > 5000:
                direction_of_change = "unwinding" if (
                    (signal == "EXTREME_LONG"  and net_change < 0) or
                    (signal == "EXTREME_SHORT" and net_change > 0)
                ) else "extending"
                if direction_of_change == "unwinding":
                    signal = f"{signal}_UNWINDING"

            return {
                "instrument":        instrument,
                "report_date":       report_date,
                "noncomm_long":      nc_long,
                "noncomm_short":     nc_short,
                "noncomm_net":       nc_net,
                "noncomm_net_pct_oi": nc_net_pct,
                "comm_long":         comm_long,
                "comm_short":        comm_short,
                "comm_net":          comm_net,
                "open_interest":     oi,
                "net_change_week":   net_change,
                "positioning_signal": signal,
                "crowding_score":    crowding,
            }
        except (IndexError, ValueError) as e:
            logger.debug(f"[COT] Parse error for {instrument}: {e}")
            return self._empty(instrument)

    @staticmethod
    def _empty(instrument: str) -> dict:
        return {
            "instrument":         instrument,
            "report_date":        None,
            "noncomm_long":       0,
            "noncomm_short":      0,
            "noncomm_net":        0,
            "noncomm_net_pct_oi": 0.0,
            "comm_long":          0,
            "comm_short":         0,
            "comm_net":           0,
            "open_interest":      0,
            "net_change_week":    0,
            "positioning_signal": "UNKNOWN",
            "crowding_score":     0,
        }


def _int(val: str) -> int:
    try:
        return int(val.strip().replace(",", ""))
    except (ValueError, AttributeError):
        return 0
