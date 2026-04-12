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

# Legacy COT — Futures Only, current year.
# This is the ONLY single file that covers BOTH FX currencies AND commodities.
# f_disagg.txt (what was here before) only covers physical commodities — no FX.
CFTC_CSV_URL = "https://www.cftc.gov/dea/newcot/f_year.txt"

# Legacy COT column layout (0-indexed after CSV split):
#  [0]  Market name + exchange
#  [1]  As_of_Date YYMMDD
#  [2]  Report_Date MM/DD/YYYY
#  [3]  Contract code
#  [4]  Market code
#  [5]  Open_Interest_All
#  [6]  NonComm_Positions_Long_All    ← hedge fund LONG
#  [7]  NonComm_Positions_Short_All   ← hedge fund SHORT
#  [8]  NonComm_Positions_Spreading
#  [9]  Comm_Positions_Long_All       ← commercial LONG
#  [10] Comm_Positions_Short_All      ← commercial SHORT
#  [11] Tot_Rept_Positions_Long_All
#  [12] Tot_Rept_Positions_Short_All
#  [13] NonRept_Positions_Long_All    ← retail LONG
#  [14] NonRept_Positions_Short_All   ← retail SHORT

# Map our symbols to search strings in the CFTC market name field.
# Partial match: "EURO FX" matches "EURO FX - CHICAGO MERCANTILE EXCHANGE"
SYMBOL_TO_CFTC: dict[str, str] = {
    "EURUSD":  "EURO FX",
    "GBPUSD":  "BRITISH POUND STERLING",
    "USDJPY":  "JAPANESE YEN",
    "AUDUSD":  "AUSTRALIAN DOLLAR",
    "USDCAD":  "CANADIAN DOLLAR",
    "NZDUSD":  "NEW ZEALAND DOLLAR",
    "USDCHF":  "SWISS FRANC",
    "XAUUSD":  "GOLD - COMMODITY EXCHANGE",   # avoid matching GOLD (MINI)
    "XAGUSD":  "SILVER - COMMODITY EXCHANGE",
    "USOIL":   "CRUDE OIL, LIGHT SWEET",
    "UKOIL":   "BRENT CRUDE OIL",
    "NATGAS":  "NATURAL GAS (NYMEX)",
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
                parts = line.split(",")
                if len(parts) >= 11:   # need at least up to column [10]
                    rows.append(parts)

        if not rows:
            logger.debug(f"[COT] No rows matched for {instrument} (search: '{cftc_name}')")
            return self._empty(instrument)

        # File is oldest-first; take last row = most recent
        row  = rows[-1]
        prev = rows[-2] if len(rows) >= 2 else None

        try:
            report_date = row[2].strip()

            # Legacy COT column indices (f_year.txt):
            #  [5] Open Interest
            #  [6] Non-Commercial Long   (hedge funds)
            #  [7] Non-Commercial Short
            #  [9] Commercial Long       (banks/producers — "smart money")
            # [10] Commercial Short
            oi        = _int(row[5])
            nc_long   = _int(row[6])
            nc_short  = _int(row[7])
            nc_net    = nc_long - nc_short
            comm_long  = _int(row[9])  if len(row) > 9  else 0
            comm_short = _int(row[10]) if len(row) > 10 else 0
            comm_net   = comm_long - comm_short

            nc_net_pct = round(nc_net / oi * 100, 1) if oi else 0.0

            # Week-over-week change in hedge fund net
            net_change = 0
            if prev:
                prev_nc_net = _int(prev[6]) - _int(prev[7])
                net_change  = nc_net - prev_nc_net

            # Historical percentile — rank current net against all rows in file
            # Gives us the research-backed <20th / >80th percentile thresholds
            all_nets = [_int(r[6]) - _int(r[7]) for r in rows if len(r) > 7]
            if len(all_nets) >= 4:
                sorted_nets = sorted(all_nets)
                rank = sorted_nets.index(min(all_nets, key=lambda x: abs(x - nc_net)))
                percentile = round(rank / len(sorted_nets) * 100, 1)
            else:
                percentile = 50.0

            # Crowding: abs(net) as fraction of 30% of OI
            crowd_raw = abs(nc_net) / max(oi * 0.3, 1)
            crowding  = min(int(crowd_raw * 100), 100)

            # Consecutive weeks in same direction
            weeks_of_data = 0
            direction = "long" if nc_net > 0 else "short"
            for r in reversed(rows):
                r_net = _int(r[6]) - _int(r[7])
                if (direction == "long" and r_net > 0) or (direction == "short" and r_net < 0):
                    weeks_of_data += 1
                else:
                    break

            # Signal: use percentile thresholds (research standard)
            # <20th percentile = extreme short → contrarian BUY signal
            # >80th percentile = extreme long  → contrarian SELL signal
            if percentile >= 80:
                signal = "EXTREME_LONG"
            elif percentile >= 60:
                signal = "BULLISH"
            elif percentile <= 20:
                signal = "EXTREME_SHORT"
            elif percentile <= 40:
                signal = "BEARISH"
            else:
                signal = "NEUTRAL"

            # If extreme AND unwinding → strongest contrarian signal
            if signal in ("EXTREME_LONG", "EXTREME_SHORT") and abs(net_change) > 2000:
                unwinding = (
                    (signal == "EXTREME_LONG"  and net_change < 0) or
                    (signal == "EXTREME_SHORT" and net_change > 0)
                )
                if unwinding:
                    signal = f"{signal}_UNWINDING"

            logger.debug(
                f"[COT] {instrument}: net={nc_net:+,} ({nc_net_pct:+.1f}% OI) "
                f"pctile={percentile:.0f} signal={signal} weeks={weeks_of_data}"
            )

            return {
                "instrument":           instrument,
                "report_date":          report_date,
                "noncomm_long":         nc_long,
                "noncomm_short":        nc_short,
                "noncomm_net":          nc_net,
                "noncomm_net_pct_oi":   nc_net_pct,
                "noncomm_percentile":   percentile,   # <20 = extreme short; >80 = extreme long
                "comm_long":            comm_long,
                "comm_short":           comm_short,
                "comm_net":             comm_net,
                "open_interest":        oi,
                "net_change_week":      net_change,
                "weeks_of_data":        weeks_of_data,
                "positioning_signal":   signal,
                "crowding_score":       crowding,
            }
        except (IndexError, ValueError) as e:
            logger.warning(f"[COT] Parse error for {instrument}: {e} (row has {len(row)} cols)")
            return self._empty(instrument)

    @staticmethod
    def _empty(instrument: str) -> dict:
        return {
            "instrument":           instrument,
            "report_date":          None,
            "noncomm_long":         0,
            "noncomm_short":        0,
            "noncomm_net":          0,
            "noncomm_net_pct_oi":   0.0,
            "noncomm_percentile":   50.0,   # unknown — treat as neutral
            "comm_long":            0,
            "comm_short":           0,
            "comm_net":             0,
            "open_interest":        0,
            "net_change_week":      0,
            "weeks_of_data":        0,
            "positioning_signal":   "UNKNOWN",
            "crowding_score":       0,
        }


def _int(val: str) -> int:
    try:
        return int(val.strip().replace(",", ""))
    except (ValueError, AttributeError):
        return 0
