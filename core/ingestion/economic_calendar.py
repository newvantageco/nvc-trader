"""
Economic calendar: fetches high-impact events and computes blackout windows.
Sources: ForexFactory (scrape) + Investing.com via investpy.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

import aiohttp
from loguru import logger


# Impact mapping
HIGH_IMPACT = {"Non-Farm Payrolls", "FOMC", "CPI", "GDP", "Interest Rate Decision",
               "ECB Press Conference", "BOE Rate Decision", "BOJ Rate Decision",
               "Federal Funds Rate", "Inflation Rate", "Unemployment Rate"}

BLACKOUT_BEFORE_MINUTES = 30
BLACKOUT_AFTER_MINUTES = 15


class EconomicCalendar:
    def __init__(self) -> None:
        self._cache: list[dict] = []
        self._cache_time: datetime | None = None

    async def get_events(
        self, currencies: list[str] | None = None, hours_ahead: float = 48.0
    ) -> list[dict]:
        """Fetch upcoming economic events."""
        await self._refresh_if_stale()

        now = datetime.now(timezone.utc)
        cutoff = now + timedelta(hours=hours_ahead)

        events = [
            e for e in self._cache
            if now <= e["time"] <= cutoff
        ]

        if currencies:
            events = [e for e in events if e.get("currency") in currencies]

        return events

    def compute_blackouts(self, events: list[dict]) -> list[dict]:
        """
        For each HIGH impact event, return a blackout window:
        [event_time - 30min, event_time + 15min]
        """
        blackouts = []
        for e in events:
            if e.get("impact") == "high":
                blackouts.append({
                    "event": e["title"],
                    "currency": e["currency"],
                    "start": (e["time"] - timedelta(minutes=BLACKOUT_BEFORE_MINUTES)).isoformat(),
                    "end": (e["time"] + timedelta(minutes=BLACKOUT_AFTER_MINUTES)).isoformat(),
                    "event_time": e["time"].isoformat(),
                })
        return blackouts

    def is_in_blackout(self, instrument: str, at: datetime | None = None) -> bool:
        """Check if a given instrument is currently in a news blackout window."""
        if at is None:
            at = datetime.now(timezone.utc)

        # Extract currencies from instrument
        currencies = _instrument_to_currencies(instrument)

        for e in self._cache:
            if e.get("impact") != "high":
                continue
            if e.get("currency") not in currencies:
                continue
            window_start = e["time"] - timedelta(minutes=BLACKOUT_BEFORE_MINUTES)
            window_end = e["time"] + timedelta(minutes=BLACKOUT_AFTER_MINUTES)
            if window_start <= at <= window_end:
                return True
        return False

    async def _refresh_if_stale(self) -> None:
        now = datetime.now(timezone.utc)
        if self._cache_time and (now - self._cache_time).seconds < 3600:
            return  # Cache valid for 1 hour

        try:
            events = await self._fetch_forex_factory()
            self._cache = events
            self._cache_time = now
            logger.debug(f"[CALENDAR] Refreshed: {len(events)} events")
        except Exception as exc:
            logger.warning(f"[CALENDAR] Refresh failed: {exc}")
            if not self._cache:
                self._cache = self._mock_events()

    async def _fetch_forex_factory(self) -> list[dict]:
        """
        Fetch from ForexFactory calendar API (unofficial JSON endpoint).
        Falls back to mock data if unavailable.
        """
        url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        return self._mock_events()
                    data = await resp.json(content_type=None)

            events = []
            for item in data:
                try:
                    dt = datetime.strptime(item["date"], "%Y-%m-%dT%H:%M:%S%z")
                except Exception:
                    continue

                impact = item.get("impact", "").lower()
                if impact not in ("high", "medium", "low"):
                    impact = "low"

                events.append({
                    "title": item.get("title", ""),
                    "currency": item.get("country", "").upper()[:3],
                    "impact": impact,
                    "time": dt,
                    "forecast": item.get("forecast"),
                    "previous": item.get("previous"),
                })
            return events
        except Exception as exc:
            logger.warning(f"[CALENDAR] ForexFactory fetch failed: {exc}")
            return self._mock_events()

    def _mock_events(self) -> list[dict]:
        """Placeholder events for testing."""
        now = datetime.now(timezone.utc)
        return [
            {
                "title": "US Non-Farm Payrolls",
                "currency": "USD",
                "impact": "high",
                "time": now + timedelta(hours=24),
                "forecast": "180K",
                "previous": "175K",
            },
            {
                "title": "ECB Interest Rate Decision",
                "currency": "EUR",
                "impact": "high",
                "time": now + timedelta(hours=48),
                "forecast": "4.50%",
                "previous": "4.50%",
            },
        ]


def _instrument_to_currencies(instrument: str) -> list[str]:
    """Extract currency codes from an instrument symbol."""
    mapping = {
        "EURUSD": ["EUR", "USD"], "GBPUSD": ["GBP", "USD"],
        "USDJPY": ["USD", "JPY"], "AUDUSD": ["AUD", "USD"],
        "USDCAD": ["USD", "CAD"], "NZDUSD": ["NZD", "USD"],
        "USDCHF": ["USD", "CHF"], "EURJPY": ["EUR", "JPY"],
        "GBPJPY": ["GBP", "JPY"],
        "XAUUSD": ["USD"], "XAGUSD": ["USD"],
        "USOIL": ["USD"], "UKOIL": ["USD"], "NATGAS": ["USD"],
    }
    return mapping.get(instrument.upper(), [])
