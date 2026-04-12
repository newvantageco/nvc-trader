"""
Circuit breaker — halts trading when drawdown limits are hit.
All thresholds are read from environment variables.

Drawdown is computed from account_snapshots in DB — NOT from OANDA's reported
daily_drawdown_pct (which is always 0.0 until we build proper history).
"""

import os
from datetime import datetime, timedelta, timezone
from loguru import logger


class CircuitBreaker:
    """
    Monitors account metrics and enforces hard stops.
    Called on every agent cycle before any trading is permitted.
    """

    def __init__(self) -> None:
        self.max_daily_dd   = float(os.environ.get("MAX_DAILY_DRAWDOWN_PCT",   2.0))  # R1: halt at 2%
        self.max_weekly_dd  = float(os.environ.get("MAX_WEEKLY_DRAWDOWN_PCT",  5.0))  # R5: halve sizes at 5%
        self.max_monthly_dd = float(os.environ.get("MAX_MONTHLY_DRAWDOWN_PCT", 10.0)) # R7: hard stop at 10%
        self._metrics: dict = {}
        self._computed_dd: dict = {"daily": 0.0, "weekly": 0.0, "monthly": 0.0}
        self._hard_stop    = False

    def update(self, metrics: dict) -> None:
        self._metrics = metrics
        self._evaluate()

    async def load_drawdown_from_db(self, db) -> None:
        """
        Compute real drawdown from account_snapshots history.
        OANDA's reported daily_drawdown_pct is always 0 — we need to derive it
        ourselves from the equity curve stored in account_snapshots.
        """
        try:
            # Fetch last 30 days of hourly snapshots (max ~720 rows)
            snapshots = await db.select(
                "account_snapshots", order_by="-timestamp", limit=744
            )
            if not snapshots:
                logger.debug("[CircuitBreaker] No account snapshots yet — drawdown = 0")
                return

            now   = datetime.now(timezone.utc)
            equities = [(s.get("timestamp", ""), float(s.get("equity", 0))) for s in snapshots]
            equities.sort(key=lambda x: x[0])  # oldest first

            def _max_drawdown_since(hours: int) -> float:
                cutoff = (now - timedelta(hours=hours)).isoformat()
                window = [eq for ts, eq in equities if ts >= cutoff]
                if len(window) < 2:
                    return 0.0
                peak = max(window)
                trough = min(window[window.index(peak):]) if peak in window else window[-1]
                return round((peak - trough) / peak * 100, 2) if peak > 0 else 0.0

            self._computed_dd = {
                "daily":   _max_drawdown_since(24),
                "weekly":  _max_drawdown_since(168),
                "monthly": _max_drawdown_since(720),
            }

            logger.info(
                f"[CircuitBreaker] Drawdown — "
                f"daily={self._computed_dd['daily']:.2f}% "
                f"weekly={self._computed_dd['weekly']:.2f}% "
                f"monthly={self._computed_dd['monthly']:.2f}%"
            )
            self._evaluate()

        except Exception as exc:
            logger.error(f"[CircuitBreaker] Failed to compute drawdown: {exc}")

    def _evaluate(self) -> None:
        # Use snapshot-computed drawdown if available; fall back to metrics dict
        daily_dd   = max(
            self._computed_dd.get("daily",   0.0),
            self._metrics.get("daily_drawdown_pct",   0.0),
        )
        weekly_dd  = max(
            self._computed_dd.get("weekly",  0.0),
            self._metrics.get("weekly_drawdown_pct",  0.0),
        )
        monthly_dd = max(
            self._computed_dd.get("monthly", 0.0),
            self._metrics.get("monthly_drawdown_pct", 0.0),
        )

        if monthly_dd >= self.max_monthly_dd:
            self._hard_stop = True
            logger.critical(
                f"[CIRCUIT BREAKER] MONTHLY HARD STOP — drawdown {monthly_dd:.2f}% >= {self.max_monthly_dd}%"
            )
        elif weekly_dd >= self.max_weekly_dd:
            logger.error(
                f"[CIRCUIT BREAKER] WEEKLY LIMIT — drawdown {weekly_dd:.2f}% >= {self.max_weekly_dd}%"
            )
        elif daily_dd >= self.max_daily_dd:
            logger.warning(
                f"[CIRCUIT BREAKER] DAILY LIMIT — drawdown {daily_dd:.2f}% >= {self.max_daily_dd}% — pausing"
            )

    def is_hard_stopped(self) -> bool:
        return self._hard_stop

    def is_daily_limit_hit(self) -> bool:
        computed = self._computed_dd.get("daily", 0.0)
        reported = self._metrics.get("daily_drawdown_pct", 0.0)
        return max(computed, reported) >= self.max_daily_dd

    def is_weekly_limit_hit(self) -> bool:
        """R5: weekly loss >= 5% → halve all position sizes."""
        return self._computed_dd.get("weekly", 0.0) >= self.max_weekly_dd

    def size_multiplier(self) -> float:
        """
        Returns a multiplier (0.0–1.0) to apply on top of Van Tharp sizing.
        R1: daily >= 2%  → 0.0 (no new trades)
        R5: weekly >= 5% → 0.5 (half size)
        R6: computed by agent from consecutive losses (not tracked here)
        """
        if self.is_daily_limit_hit() or self._hard_stop:
            return 0.0
        if self.is_weekly_limit_hit():
            return 0.5
        return 1.0

    def status(self) -> dict:
        mult = self.size_multiplier()
        return {
            "hard_stop":            self._hard_stop,
            "daily_limit_hit":      self.is_daily_limit_hit(),
            "weekly_limit_hit":     self.is_weekly_limit_hit(),
            "size_multiplier":      mult,
            "daily_drawdown_pct":   self._computed_dd.get("daily",   0.0),
            "weekly_drawdown_pct":  self._computed_dd.get("weekly",  0.0),
            "monthly_drawdown_pct": self._computed_dd.get("monthly", 0.0),
            "max_daily_dd":         self.max_daily_dd,
            "max_weekly_dd":        self.max_weekly_dd,
            "max_monthly_dd":       self.max_monthly_dd,
            "trading_allowed":      mult > 0.0,
        }
