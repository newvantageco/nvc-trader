"""
Growth Plan — Staged Daily Profit Target System.

Implements the stepped growth model:
  Stage 1: $10–20/day   (break-even + first profit)
  Stage 2: $30–40/day   (unlock after 14 consecutive qualifying days)
  Stage 3: $50–60/day
  Stage 4: $70–80/day
  Stage 5: $90–100/day

Stage advancement rules:
  - Must hit the LOWER bound of the current stage's target for 14 of the last 21 days
  - Must NOT have a daily loss > 3% of account on more than 3 of those 21 days
  - Once advanced, the new minimum lot multiplier is applied automatically

How we make $10–20/day on a $100 account:
  OANDA micro lots: 1,000 units EURUSD ≈ $0.10/pip
  Strategy: 3:1 RR setups (10-pip SL, 30-pip TP)
  With 10,000 units ($1/pip):
    - One 30-pip win = $3
    - Need 4–6 qualified setups/day, hit 60–65% = 3–4 wins = $9–12
    - Occasionally hit 60-pip days on trending sessions = $18–20

  To ensure profitability:
    - EdgeFilter grade A+ or higher only (7+/8 conditions)
    - 3:1 minimum RR → even at 45% win rate, expectancy is positive
    - Session filter: London open + NY session only (better moves)

This module:
  - Tracks daily P&L from Supabase
  - Computes which stage we're in
  - Recommends the position multiplier and daily trade limit
  - Generates stage advancement reports
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from dataclasses import dataclass
from typing import Optional
from loguru import logger


@dataclass
class Stage:
    number:         int
    name:           str
    daily_min:      float   # USD — lower bound of target range
    daily_max:      float   # USD — upper bound
    lot_multiplier: float   # scale factor on base position size
    min_rr:         float   # minimum risk:reward required
    edge_grade:     str     # minimum EdgeFilter grade (A, A+, A++)
    qualifying_days: int    # days needed to advance
    max_bad_days:   int     # max loss days > 3% before failing qualification


STAGES: list[Stage] = [
    Stage(1, "Bootstrap",   10,  20,  1.0, 2.0, "A",   14, 3),
    Stage(2, "Growing",     30,  40,  2.0, 2.5, "A+",  14, 2),
    Stage(3, "Scaling",     50,  60,  3.0, 2.5, "A+",  14, 2),
    Stage(4, "Established", 70,  80,  4.5, 3.0, "A++", 21, 1),
    Stage(5, "Peak",        90, 100,  6.0, 3.0, "A++", 21, 1),
]


class GrowthPlan:
    """Tracks progress through the staged profit plan."""

    def __init__(self) -> None:
        self._stage_override: int | None = None

    def get_current_stage(self, daily_pnl_history: list[dict]) -> Stage:
        """
        Determine current stage from 21-day P&L history.
        daily_pnl_history: list of {date: str, pnl: float, account_equity: float}
        """
        if self._stage_override is not None:
            return STAGES[self._stage_override - 1]

        if not daily_pnl_history:
            return STAGES[0]

        # Start from highest stage and work down
        for stage in reversed(STAGES):
            if self._qualifies_for_stage(stage, daily_pnl_history):
                return stage

        return STAGES[0]

    def get_trading_params(
        self,
        stage: Stage,
        account_balance: float = 100.0,
    ) -> dict:
        """
        Returns the recommended trading parameters for this stage.
        All sizes based on OANDA micro lots (1000 units min).
        """
        # Base unit calculation for $100 with 1% risk
        # $1 risk / 10-pip stop = $0.10/pip = 1000 units of EURUSD
        base_units  = 1000      # 1,000 units = 0.01 micro lots
        risk_units  = int(base_units * stage.lot_multiplier)
        pip_value   = risk_units * 0.0001   # rough USD/pip for major pairs

        # Daily trade limit: stop when we hit the top of the stage range
        daily_target_min = stage.daily_min
        daily_target_max = stage.daily_max

        return {
            "stage":              stage.number,
            "stage_name":         stage.name,
            "daily_target_min":   daily_target_min,
            "daily_target_max":   daily_target_max,
            "lot_multiplier":     stage.lot_multiplier,
            "position_units":     risk_units,
            "pip_value_approx":   round(pip_value, 4),
            "min_rr":             stage.min_rr,
            "min_edge_grade":     stage.edge_grade,
            "risk_per_trade_pct": 1.0,       # always 1%
            "risk_per_trade_usd": round(account_balance * 0.01, 2),
            "daily_stop_loss_usd": round(account_balance * 0.03, 2),  # 3% max daily loss
            "max_open_trades":    min(stage.number + 2, 6),   # max 4 trades stage 1
            "note": (
                f"Stage {stage.number}: target ${daily_target_min}–${daily_target_max}/day. "
                f"Use {risk_units:,} units (~${pip_value:.2f}/pip). "
                f"Min RR {stage.min_rr}:1. Only take {stage.edge_grade}+ setups."
            ),
        }

    def check_stage_advancement(
        self,
        daily_pnl_history: list[dict],
    ) -> dict:
        """
        Check if ready to advance to the next stage.
        Returns: { ready: bool, current_stage, next_stage, days_qualifying, days_needed, blockers }
        """
        current = self.get_current_stage(daily_pnl_history)
        next_idx = current.number   # stages are 1-indexed
        if next_idx >= len(STAGES):
            return {
                "ready":         False,
                "current_stage": current.number,
                "next_stage":    None,
                "message":       "Already at maximum stage — maintain and optimise",
            }

        next_stage = STAGES[next_idx]
        recent = daily_pnl_history[-21:]

        qualifying = sum(
            1 for d in recent
            if d.get("pnl", 0) >= current.daily_min
        )
        bad_days = sum(
            1 for d in recent
            if d.get("pnl", 0) < 0 and
               abs(d.get("pnl", 0)) > d.get("account_equity", 100) * 0.03
        )

        blockers = []
        if qualifying < current.qualifying_days:
            blockers.append(
                f"Need {current.qualifying_days} qualifying days ≥${current.daily_min}/day "
                f"({qualifying} so far in last 21 days)"
            )
        if bad_days > current.max_bad_days:
            blockers.append(
                f"Too many large loss days: {bad_days} (max {current.max_bad_days})"
            )

        ready = len(blockers) == 0

        return {
            "ready":           ready,
            "current_stage":   current.number,
            "current_name":    current.name,
            "next_stage":      next_stage.number,
            "next_name":       next_stage.name,
            "days_qualifying": qualifying,
            "days_needed":     current.qualifying_days,
            "bad_days":        bad_days,
            "max_bad_days":    current.max_bad_days,
            "blockers":        blockers,
            "message": (
                f"Ready to advance to Stage {next_stage.number}!" if ready
                else f"Need {current.qualifying_days - qualifying} more qualifying days to advance"
            ),
        }

    def compute_apy(
        self,
        daily_pnl_history: list[dict],
        account_balance: float,
    ) -> dict:
        """
        Annualised percentage yield from recent P&L history.
        Uses last 30 days of data (or all available if < 30).
        """
        if not daily_pnl_history or account_balance <= 0:
            return {"apy_pct": 0, "avg_daily_pct": 0, "trading_days": 0}

        recent = daily_pnl_history[-30:]
        total_pnl    = sum(d.get("pnl", 0) for d in recent)
        trading_days = len(recent)
        avg_daily_pct = (total_pnl / account_balance / trading_days * 100) if trading_days > 0 else 0

        # APY: compound daily return × 252 trading days
        daily_return = 1 + (total_pnl / account_balance / max(trading_days, 1))
        apy          = ((daily_return ** 252) - 1) * 100

        return {
            "apy_pct":          round(min(apy, 99999), 1),   # cap at 99,999%
            "avg_daily_pct":    round(avg_daily_pct, 2),
            "avg_daily_usd":    round(total_pnl / trading_days, 2),
            "total_pnl_period": round(total_pnl, 2),
            "trading_days":     trading_days,
        }

    # ── Internal ──────────────────────────────────────────────────────────────

    def _qualifies_for_stage(self, stage: Stage, history: list[dict]) -> bool:
        """True if historical P&L shows this stage has been consistently achieved."""
        if stage.number == 1:
            return True   # always at least stage 1

        recent = history[-21:]
        qualifying = sum(1 for d in recent if d.get("pnl", 0) >= stage.daily_min)
        bad_days   = sum(
            1 for d in recent
            if d.get("pnl", 0) < 0 and
               abs(d.get("pnl", 0)) > d.get("account_equity", 100) * 0.03
        )

        return qualifying >= stage.qualifying_days and bad_days <= stage.max_bad_days
