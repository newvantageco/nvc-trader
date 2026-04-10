"""
Blackout manager — prevents trading around high-impact news events.
Also enforces weekend/thin-liquidity restrictions.
"""

from __future__ import annotations
from datetime import datetime, timezone

from loguru import logger


# Instruments affected by each currency
CURRENCY_INSTRUMENTS: dict[str, list[str]] = {
    "USD": ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "NZDUSD", "USDCHF", "XAUUSD", "USOIL"],
    "EUR": ["EURUSD", "EURJPY"],
    "GBP": ["GBPUSD", "GBPJPY"],
    "JPY": ["USDJPY", "EURJPY", "GBPJPY"],
    "AUD": ["AUDUSD"],
    "CAD": ["USDCAD"],
    "NZD": ["NZDUSD"],
    "CHF": ["USDCHF"],
}

BLACKOUT_BEFORE_MINUTES = 30
BLACKOUT_AFTER_MINUTES  = 15


class BlackoutManager:
    """
    Determines whether a given instrument can be traded right now.
    Checks: news event blackouts + weekend restrictions.
    """

    def is_blocked(
        self,
        instrument: str,
        blackout_windows: list[dict],
        at: datetime | None = None,
    ) -> tuple[bool, str]:
        """
        Returns (blocked: bool, reason: str).
        blackout_windows come from EconomicCalendar.compute_blackouts().
        """
        if at is None:
            at = datetime.now(timezone.utc)

        # Weekend restriction: Sun 21:00 – Mon 00:00 UTC
        if self._is_weekend_restricted(at):
            return True, "Weekend liquidity restriction (Sun 21:00–Mon 00:00 UTC)"

        # Check event blackouts
        for window in blackout_windows:
            try:
                start = datetime.fromisoformat(window["start"])
                end   = datetime.fromisoformat(window["end"])
                currency = window.get("currency", "")
            except Exception:
                continue

            # Does this blackout affect our instrument?
            affected = CURRENCY_INSTRUMENTS.get(currency, [])
            if instrument not in affected and currency not in instrument:
                continue

            if start <= at <= end:
                event = window.get("event", "high-impact event")
                return True, f"Blackout: {event} ({currency}) until {end.strftime('%H:%M UTC')}"

        return False, ""

    def get_blocked_instruments(
        self, blackout_windows: list[dict], at: datetime | None = None
    ) -> dict[str, str]:
        """Return {instrument: reason} for all currently blocked instruments."""
        if at is None:
            at = datetime.now(timezone.utc)
        from core.ai.claude_agent import WATCHLIST
        blocked = {}
        for instrument in WATCHLIST:
            is_blocked, reason = self.is_blocked(instrument, blackout_windows, at)
            if is_blocked:
                blocked[instrument] = reason
        return blocked

    @staticmethod
    def _is_weekend_restricted(at: datetime) -> bool:
        """Block trading Sun 21:00 UTC – Mon 00:00 UTC (thin liquidity gap)."""
        weekday = at.weekday()  # 0=Mon, 6=Sun
        hour    = at.hour
        if weekday == 6 and hour >= 21:   # Sunday after 21:00
            return True
        if weekday == 0 and hour == 0:    # Monday midnight
            return True
        return False
