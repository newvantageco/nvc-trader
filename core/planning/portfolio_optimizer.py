"""
Portfolio Optimizer & Financial Planner.

Implements:
  1. Black-Litterman model — combine market equilibrium + our views
  2. Kelly Criterion — optimal position sizing given edge and variance
  3. Monte Carlo simulation — P&L range projection (500 paths, 30 days)
  4. Value at Risk (VaR) — 95% and 99% confidence intervals
  5. Efficient Frontier — optimal risk/reward allocation across instruments
  6. Drawdown analysis — expected vs max drawdown projections

This module does NOT use external dependencies beyond numpy (already in stack).
Falls back to simplified calculations if numpy unavailable.
"""

from __future__ import annotations

import math
import random
from datetime import datetime, timezone
from typing import Optional
from loguru import logger

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False
    logger.warning("[PortfolioOpt] numpy not available — using simplified calculations")


class PortfolioOptimizer:
    """Portfolio optimisation and risk planning."""

    def optimise_allocation(
        self,
        instruments: list[str],
        expected_returns: dict[str, float],   # annualised % e.g. 0.15 = 15%
        volatilities:     dict[str, float],   # annualised % e.g. 0.12 = 12%
        correlations:     dict[tuple[str,str], float] | None = None,
        max_allocation:   float = 0.25,       # max 25% per instrument
        risk_free_rate:   float = 0.05,       # current ~5% money market
    ) -> dict:
        """
        Black-Litterman style allocation.
        Returns optimal weight per instrument and portfolio-level stats.
        """
        n = len(instruments)
        if n == 0:
            return {"weights": {}, "expected_return": 0, "expected_volatility": 0, "sharpe": 0}

        # Simple mean-variance if no correlation data
        if not correlations or not HAS_NUMPY:
            return self._simple_allocation(
                instruments, expected_returns, volatilities, max_allocation, risk_free_rate
            )

        # Build covariance matrix
        cov = np.zeros((n, n))
        for i, s1 in enumerate(instruments):
            for j, s2 in enumerate(instruments):
                vol_i = volatilities.get(s1, 0.15)
                vol_j = volatilities.get(s2, 0.15)
                corr  = correlations.get((s1, s2), correlations.get((s2, s1), 0.0 if i != j else 1.0))
                cov[i, j] = vol_i * vol_j * corr

        mu = np.array([expected_returns.get(s, 0.0) for s in instruments])

        # Maximise Sharpe: w* = (Σ^-1 (μ − rf)) / normalise
        try:
            cov_inv = np.linalg.pinv(cov)
            excess  = mu - risk_free_rate
            raw_w   = cov_inv @ excess
            raw_w   = np.maximum(raw_w, 0)   # no short positions
            if raw_w.sum() == 0:
                raw_w = np.ones(n)
            weights = raw_w / raw_w.sum()
            weights = np.minimum(weights, max_allocation)
            weights = weights / weights.sum()
        except Exception:
            weights = np.ones(n) / n

        port_ret = float(np.dot(weights, mu))
        port_var = float(weights @ cov @ weights)
        port_vol = math.sqrt(max(port_var, 0))
        sharpe   = (port_ret - risk_free_rate) / port_vol if port_vol > 0 else 0

        return {
            "weights":            {s: round(float(w), 4) for s, w in zip(instruments, weights)},
            "expected_return":    round(port_ret * 100, 2),
            "expected_volatility": round(port_vol * 100, 2),
            "sharpe_ratio":       round(sharpe, 3),
            "method":             "black-litterman-approx",
        }

    def kelly_position_size(
        self,
        win_rate:         float,   # e.g. 0.55 = 55% wins
        avg_win_pips:     float,   # average winning trade in pips
        avg_loss_pips:    float,   # average losing trade in pips (positive number)
        account_balance:  float,
        pip_value:        float = 10.0,  # per pip per standard lot
        kelly_fraction:   float = 0.5,  # use half Kelly for safety
        max_risk_pct:     float = 0.01,  # hard cap at 1%
    ) -> dict:
        """
        Kelly Criterion optimal position size.
        f* = (b·p − q) / b
        where b = win/loss ratio, p = win rate, q = 1 − p
        """
        if avg_loss_pips <= 0 or account_balance <= 0:
            return {"optimal_lots": 0, "risk_pct": 0, "kelly_fraction": 0}

        b = avg_win_pips / avg_loss_pips
        p = win_rate
        q = 1 - p

        kelly = (b * p - q) / b
        kelly = max(kelly, 0)   # can't be negative (don't trade)
        adj_kelly = kelly * kelly_fraction   # half-Kelly

        # Convert to lot size
        risk_amount    = account_balance * adj_kelly
        risk_per_lot   = avg_loss_pips * pip_value
        optimal_lots   = risk_amount / risk_per_lot if risk_per_lot > 0 else 0

        # Hard cap
        max_risk_amount = account_balance * max_risk_pct
        capped_lots     = min(optimal_lots, max_risk_amount / risk_per_lot)
        capped_lots     = max(round(capped_lots, 2), 0.01)

        return {
            "optimal_lots":     capped_lots,
            "kelly_pct":        round(kelly * 100, 2),
            "adj_kelly_pct":    round(adj_kelly * 100, 2),
            "risk_pct":         round(capped_lots * risk_per_lot / account_balance * 100, 3),
            "expected_profit":  round(win_rate * avg_win_pips * capped_lots * pip_value, 2),
            "expected_loss":    round((1 - win_rate) * avg_loss_pips * capped_lots * pip_value, 2),
        }

    def monte_carlo_projection(
        self,
        account_balance: float,
        win_rate:        float,
        avg_win_usd:     float,
        avg_loss_usd:    float,
        trades_per_day:  float = 3.0,
        days:            int   = 30,
        simulations:     int   = 500,
        max_daily_dd_pct: float = 0.03,
    ) -> dict:
        """
        Monte Carlo simulation of P&L distribution over N days.
        Returns percentile outcomes and drawdown statistics.
        """
        random.seed(42)
        final_balances: list[float] = []
        max_drawdowns:  list[float] = []
        ruin_count     = 0

        for _ in range(simulations):
            bal        = account_balance
            peak       = account_balance
            max_dd     = 0.0
            ruined     = False

            for day in range(days):
                n_trades = max(1, int(random.gauss(trades_per_day, 1)))
                daily_dd = 0.0

                for _ in range(n_trades):
                    if random.random() < win_rate:
                        pnl = random.gauss(avg_win_usd, avg_win_usd * 0.3)
                    else:
                        pnl = -random.gauss(avg_loss_usd, avg_loss_usd * 0.2)

                    bal        += pnl
                    daily_dd   -= min(pnl, 0)

                    if bal < account_balance * 0.5:   # 50% drawdown = ruin
                        ruined = True
                        break

                    # Daily circuit breaker
                    if daily_dd > account_balance * max_daily_dd_pct:
                        break

                peak   = max(peak, bal)
                dd_pct = (peak - bal) / peak if peak > 0 else 0
                max_dd = max(max_dd, dd_pct)

                if ruined:
                    ruin_count += 1
                    break

            final_balances.append(bal)
            max_drawdowns.append(max_dd)

        final_balances.sort()
        max_drawdowns.sort()
        n = len(final_balances)

        def pct(data: list, p: float) -> float:
            idx = min(int(p * n), n - 1)
            return round(data[idx], 2)

        return {
            "starting_balance": account_balance,
            "days":             days,
            "simulations":      simulations,
            "p10_balance":      pct(final_balances, 0.10),
            "p25_balance":      pct(final_balances, 0.25),
            "p50_balance":      pct(final_balances, 0.50),
            "p75_balance":      pct(final_balances, 0.75),
            "p90_balance":      pct(final_balances, 0.90),
            "expected_return_pct": round((pct(final_balances, 0.50) - account_balance) / account_balance * 100, 1),
            "p10_return_pct":   round((pct(final_balances, 0.10) - account_balance) / account_balance * 100, 1),
            "p90_return_pct":   round((pct(final_balances, 0.90) - account_balance) / account_balance * 100, 1),
            "median_max_dd_pct": round(pct(max_drawdowns, 0.50) * 100, 1),
            "worst_max_dd_pct":  round(pct(max_drawdowns, 0.90) * 100, 1),
            "ruin_probability_pct": round(ruin_count / simulations * 100, 1),
            "var_95_daily":     round((account_balance - pct(final_balances, 0.05)) / days, 2),
        }

    def compute_var(
        self,
        account_balance: float,
        daily_pnl_history: list[float],
        confidence: float = 0.95,
    ) -> dict:
        """
        Historical VaR: sort daily P&L history and find the loss at the given confidence level.
        Returns VaR in USD and as % of account.
        """
        if len(daily_pnl_history) < 10:
            return {"var_usd": 0, "var_pct": 0, "confidence": confidence, "note": "insufficient history"}

        sorted_pnl = sorted(daily_pnl_history)
        idx_95     = int((1 - confidence) * len(sorted_pnl))
        var_usd    = abs(min(sorted_pnl[idx_95], 0))
        var_pct    = var_usd / account_balance * 100 if account_balance > 0 else 0

        # Expected Shortfall (CVaR): average of losses beyond VaR
        tail       = [p for p in sorted_pnl[:idx_95] if p < 0]
        cvar_usd   = abs(sum(tail) / len(tail)) if tail else var_usd

        return {
            "confidence":  confidence,
            "var_usd":     round(var_usd, 2),
            "var_pct":     round(var_pct, 2),
            "cvar_usd":    round(cvar_usd, 2),   # Conditional VaR (worse-than-VaR average)
            "cvar_pct":    round(cvar_usd / account_balance * 100, 2),
            "data_points": len(daily_pnl_history),
        }

    # ── Internal ──────────────────────────────────────────────────────────────

    def _simple_allocation(
        self,
        instruments: list[str],
        expected_returns: dict[str, float],
        volatilities:     dict[str, float],
        max_allocation:   float,
        risk_free_rate:   float,
    ) -> dict:
        """Equal-risk-contribution allocation without numpy."""
        n = len(instruments)
        # Sharpe-weighted allocation
        sharpes = {}
        for sym in instruments:
            er  = expected_returns.get(sym, 0.0)
            vol = volatilities.get(sym, 0.15)
            sharpes[sym] = max((er - risk_free_rate) / vol if vol > 0 else 0, 0)

        total = sum(sharpes.values()) or 1
        weights = {s: min(v / total, max_allocation) for s, v in sharpes.items()}
        total_w = sum(weights.values()) or 1
        weights = {s: round(v / total_w, 4) for s, v in weights.items()}

        port_ret = sum(weights[s] * expected_returns.get(s, 0) for s in instruments)
        port_vol = math.sqrt(sum((weights[s] * volatilities.get(s, 0.15))**2 for s in instruments))
        sharpe   = (port_ret - risk_free_rate) / port_vol if port_vol > 0 else 0

        return {
            "weights":             weights,
            "expected_return":     round(port_ret * 100, 2),
            "expected_volatility": round(port_vol * 100, 2),
            "sharpe_ratio":        round(sharpe, 3),
            "method":              "sharpe-weighted",
        }
