"""
Trade Performance Tracker.

Reads closed trades from Supabase and computes real statistics for:
  - Kelly Criterion (needs win_rate + avg_win/loss)
  - Claude's self-assessment (am I improving or degrading?)
  - Dashboard analytics panel

Stats produced:
  win_rate, profit_factor, expectancy_per_r, sharpe_ratio,
  max_consecutive_losses, avg_win_pips, avg_loss_pips,
  best_instrument, worst_instrument, daily_pnl_series
"""

from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from typing import Optional
from loguru import logger


class PerformanceTracker:
    """Computes trading statistics from the closed trades in Supabase."""

    def __init__(self, db) -> None:
        self.db = db

    async def get_stats(self, lookback_days: int = 30) -> dict:
        """
        Returns full performance snapshot for the past N days.
        Falls back to zeros if no trades yet (system is new).
        """
        cutoff = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).isoformat()

        try:
            # Fetch closed signals (actual fills with P&L)
            signals = await self.db.select(
                "signals",
                order_by="-timestamp",
                limit=500,
            )
            # Filter to within lookback window
            signals = [
                s for s in signals
                if s.get("timestamp", "") >= cutoff
            ]
        except Exception as e:
            logger.warning(f"[Perf] Failed to fetch signals: {e}")
            signals = []

        if not signals:
            return self._empty_stats(lookback_days)

        # ── Parse P&L from fill data ──────────────────────────────────────────
        wins:   list[float] = []
        losses: list[float] = []
        by_instrument: dict[str, list[float]] = {}
        daily_pnl: dict[str, float] = {}

        for s in signals:
            fill_raw = s.get("fill") or s.get("close_result")
            pnl = self._extract_pnl(fill_raw)
            if pnl is None:
                continue

            instrument = s.get("instrument", "UNKNOWN")
            date_str   = (s.get("timestamp") or "")[:10]

            if pnl > 0:
                wins.append(pnl)
            elif pnl < 0:
                losses.append(abs(pnl))

            by_instrument.setdefault(instrument, []).append(pnl)
            daily_pnl[date_str] = daily_pnl.get(date_str, 0.0) + pnl

        total = len(wins) + len(losses)
        if total == 0:
            return self._empty_stats(lookback_days)

        # ── Core metrics ──────────────────────────────────────────────────────
        win_rate     = round(len(wins) / total, 3)
        avg_win      = round(sum(wins)   / len(wins),   2) if wins   else 0.0
        avg_loss     = round(sum(losses) / len(losses), 2) if losses else 0.0
        gross_profit = sum(wins)
        gross_loss   = sum(losses)
        profit_factor = round(gross_profit / gross_loss, 3) if gross_loss else float("inf")
        net_pnl      = round(gross_profit - gross_loss, 2)

        # Expectancy per R (how much do we make per $1 risked on average)
        # E = (win_rate × avg_win) - (loss_rate × avg_loss)
        expectancy   = round(win_rate * avg_win - (1 - win_rate) * avg_loss, 2)

        # Max consecutive losses
        max_consec_losses = self._max_consecutive_losses(wins, losses, signals)

        # Sharpe ratio (daily P&L series, annualised)
        sharpe = self._compute_sharpe(list(daily_pnl.values()))

        # Best / worst instruments
        inst_summary = {
            sym: {
                "total_pnl":  round(sum(pnls), 2),
                "trade_count": len(pnls),
                "win_rate":   round(sum(1 for p in pnls if p > 0) / len(pnls), 2),
            }
            for sym, pnls in by_instrument.items()
        }
        sorted_inst  = sorted(inst_summary.items(), key=lambda x: x[1]["total_pnl"])
        worst_inst   = sorted_inst[0][0]  if sorted_inst else None
        best_inst    = sorted_inst[-1][0] if sorted_inst else None

        # Kelly optimal fraction: f* = (bp - q) / b  where b = avg_win/avg_loss
        kelly_f = 0.0
        if avg_loss > 0:
            b = avg_win / avg_loss
            p = win_rate
            q = 1 - win_rate
            kelly_f = max(0.0, round((b * p - q) / b, 3))

        # Recommended risk% per trade (fractional Kelly at 25%)
        recommended_risk_pct = round(kelly_f * 0.25 * 100, 2)
        recommended_risk_pct = min(recommended_risk_pct, 2.0)   # hard cap 2%
        recommended_risk_pct = max(recommended_risk_pct, 0.25)  # floor 0.25%

        result = {
            "lookback_days":          lookback_days,
            "total_trades":           total,
            "winning_trades":         len(wins),
            "losing_trades":          len(losses),
            "win_rate":               win_rate,
            "avg_win_usd":            avg_win,
            "avg_loss_usd":           avg_loss,
            "profit_factor":          profit_factor,
            "net_pnl_usd":            net_pnl,
            "expectancy_per_trade":   expectancy,
            "max_consecutive_losses": max_consec_losses,
            "sharpe_ratio":           sharpe,
            "kelly_fraction":         kelly_f,
            "recommended_risk_pct":   recommended_risk_pct,
            "best_instrument":        best_inst,
            "worst_instrument":       worst_inst,
            "by_instrument":          inst_summary,
            "daily_pnl":              daily_pnl,
            "assessment":             self._assess(win_rate, profit_factor, max_consec_losses, expectancy),
        }

        logger.info(
            f"[Perf] {lookback_days}d: {total} trades "
            f"WR={win_rate:.1%} PF={profit_factor:.2f} "
            f"E={expectancy:+.2f} Sharpe={sharpe:.2f} Kelly={kelly_f:.3f}"
        )
        return result

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _extract_pnl(self, fill_raw) -> Optional[float]:
        """Extract realised P&L from a fill dict or JSON string."""
        if fill_raw is None:
            return None
        if isinstance(fill_raw, str):
            try:
                fill_raw = json.loads(fill_raw)
            except (json.JSONDecodeError, ValueError):
                return None
        if not isinstance(fill_raw, dict):
            return None

        # Try common field names
        for key in ("realised_pnl", "realized_pnl", "pl", "profit", "pnl", "gain"):
            val = fill_raw.get(key)
            if val is not None:
                try:
                    return float(val)
                except (TypeError, ValueError):
                    pass

        # OANDA fill format: tradesClosed[0].realizedPL
        trades_closed = fill_raw.get("tradesClosed") or fill_raw.get("trades_closed", [])
        if trades_closed and isinstance(trades_closed, list):
            total = 0.0
            for t in trades_closed:
                for key in ("realizedPL", "realized_pl", "pl"):
                    v = t.get(key)
                    if v is not None:
                        try:
                            total += float(v)
                            break
                        except (TypeError, ValueError):
                            pass
            if total != 0.0:
                return total

        return None

    def _max_consecutive_losses(self, wins, losses, signals) -> int:
        """Count the longest losing streak from ordered signals."""
        max_streak = 0
        streak     = 0
        for s in sorted(signals, key=lambda x: x.get("timestamp", "")):
            fill_raw = s.get("fill") or s.get("close_result")
            pnl = self._extract_pnl(fill_raw)
            if pnl is None:
                continue
            if pnl < 0:
                streak += 1
                max_streak = max(max_streak, streak)
            else:
                streak = 0
        return max_streak

    @staticmethod
    def _compute_sharpe(daily_pnls: list[float]) -> float:
        """Annualised Sharpe ratio from daily P&L series."""
        if len(daily_pnls) < 3:
            return 0.0
        import statistics
        mean  = statistics.mean(daily_pnls)
        stdev = statistics.stdev(daily_pnls)
        if stdev == 0:
            return 0.0
        daily_sharpe = mean / stdev
        return round(daily_sharpe * (252 ** 0.5), 2)   # annualise

    @staticmethod
    def _assess(win_rate: float, profit_factor: float, max_consec_losses: int, expectancy: float) -> str:
        """Plain English assessment for Claude to read."""
        issues = []
        strengths = []

        if win_rate < 0.40:
            issues.append(f"win rate {win_rate:.0%} is below 40% — either exits are too early or entries are poor quality")
        elif win_rate > 0.55:
            strengths.append(f"win rate {win_rate:.0%} is strong")

        if profit_factor < 1.0:
            issues.append(f"profit factor {profit_factor:.2f} < 1.0 — losing more than winning in aggregate")
        elif profit_factor >= 1.5:
            strengths.append(f"profit factor {profit_factor:.2f} is healthy (>1.5)")

        if max_consec_losses >= 5:
            issues.append(f"max consecutive losses = {max_consec_losses} — reduce size after 3 consecutive losses")

        if expectancy < 0:
            issues.append(f"negative expectancy ({expectancy:+.2f}) — system is not profitable at current win rate / RR")
        elif expectancy > 0:
            strengths.append(f"positive expectancy ({expectancy:+.2f} per trade)")

        if not issues and not strengths:
            return "Insufficient data for assessment."
        parts = []
        if strengths:
            parts.append("STRENGTHS: " + "; ".join(strengths))
        if issues:
            parts.append("ISSUES: " + "; ".join(issues))
        return " | ".join(parts)

    @staticmethod
    def _empty_stats(lookback_days: int) -> dict:
        return {
            "lookback_days":          lookback_days,
            "total_trades":           0,
            "winning_trades":         0,
            "losing_trades":          0,
            "win_rate":               0.0,
            "avg_win_usd":            0.0,
            "avg_loss_usd":           0.0,
            "profit_factor":          0.0,
            "net_pnl_usd":            0.0,
            "expectancy_per_trade":   0.0,
            "max_consecutive_losses": 0,
            "sharpe_ratio":           0.0,
            "kelly_fraction":         0.0,
            "recommended_risk_pct":   1.0,
            "best_instrument":        None,
            "worst_instrument":       None,
            "by_instrument":          {},
            "daily_pnl":              {},
            "assessment":             "No closed trades yet — system is new. Use default 1% risk until 20+ trades recorded.",
        }
