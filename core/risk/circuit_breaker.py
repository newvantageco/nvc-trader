"""
Circuit breaker — halts trading when drawdown limits are hit.
All thresholds are read from environment variables.
"""

import os
from datetime import datetime, timezone
from loguru import logger


class CircuitBreaker:
    """
    Monitors account metrics and enforces hard stops.
    Called on every agent cycle before any trading is permitted.
    """

    def __init__(self) -> None:
        self.max_daily_dd = float(os.environ.get("MAX_DAILY_DRAWDOWN_PCT", 3.0))
        self.max_weekly_dd = float(os.environ.get("MAX_WEEKLY_DRAWDOWN_PCT", 6.0))
        self.max_monthly_dd = float(os.environ.get("MAX_MONTHLY_DRAWDOWN_PCT", 10.0))
        self._metrics: dict = {}
        self._hard_stop = False
        self._pause_until: datetime | None = None

    def update(self, metrics: dict) -> None:
        self._metrics = metrics
        self._evaluate()

    def _evaluate(self) -> None:
        daily_dd = self._metrics.get("daily_drawdown_pct", 0.0)
        weekly_dd = self._metrics.get("weekly_drawdown_pct", 0.0)
        monthly_dd = self._metrics.get("monthly_drawdown_pct", 0.0)

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
        return self._metrics.get("daily_drawdown_pct", 0.0) >= self.max_daily_dd

    def status(self) -> dict:
        return {
            "hard_stop": self._hard_stop,
            "daily_limit_hit": self.is_daily_limit_hit(),
            "daily_drawdown_pct": self._metrics.get("daily_drawdown_pct", 0.0),
            "max_daily_dd": self.max_daily_dd,
        }
