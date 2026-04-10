"""
NVC Trader Backtest Engine.
Simulates the signal generation + execution logic on historical data.
Uses a simplified rule-based proxy (TA-only) since historical FinBERT scores
are not available; sentiment is modelled from volatility regimes.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd
import pandas_ta as ta
from loguru import logger

from backtest.data_loader import load_ohlcv


@dataclass
class BacktestTrade:
    instrument:   str
    direction:    str
    entry_time:   Any
    entry_price:  float
    stop_loss:    float
    take_profit:  float
    lot_size:     float
    exit_time:    Any     = None
    exit_price:   float   = 0.0
    pnl_pips:     float   = 0.0
    pnl_usd:      float   = 0.0
    status:       str     = "open"   # open / closed_tp / closed_sl / closed_end


@dataclass
class BacktestResult:
    instrument:       str
    timeframe:        str
    days:             int
    starting_cash:    float
    final_equity:     float
    total_return_pct: float
    sharpe_ratio:     float
    max_drawdown_pct: float
    win_rate_pct:     float
    profit_factor:    float
    total_trades:     int
    winning_trades:   int
    losing_trades:    int
    trades:           list[BacktestTrade] = field(default_factory=list)
    equity_curve:     list[float]         = field(default_factory=list)


PIP_SIZE = {
    "EURUSD": 0.0001, "GBPUSD": 0.0001, "AUDUSD": 0.0001,
    "NZDUSD": 0.0001, "USDCAD": 0.0001, "USDCHF": 0.0001,
    "USDJPY": 0.01,   "EURJPY": 0.01,   "GBPJPY": 0.01,
    "XAUUSD": 0.01,   "XAGUSD": 0.001,
    "USOIL":  0.01,   "UKOIL":  0.01,   "NATGAS": 0.001,
}
PIP_VALUE = {k: 10.0 for k in PIP_SIZE}


async def run_backtest(
    instrument:    str   = "EURUSD",
    timeframe:     str   = "H1",
    days:          int   = 365,
    starting_cash: float = 10_000.0,
    risk_pct:      float = 1.0,
    sl_atr_mult:   float = 1.5,
    tp_atr_mult:   float = 2.5,
    min_score:     float = 0.60,
) -> dict:
    """Run a full backtest and return a result dict."""

    logger.info(f"[BACKTEST] {instrument} {timeframe} — {days} days @ ${starting_cash:,.0f}")

    df = await load_ohlcv(instrument, timeframe, days)
    result = _simulate(
        df, instrument, starting_cash, risk_pct, sl_atr_mult, tp_atr_mult, min_score
    )

    return {
        "instrument":       result.instrument,
        "timeframe":        result.timeframe,
        "days":             result.days,
        "starting_cash":    result.starting_cash,
        "final_equity":     round(result.final_equity, 2),
        "total_return_pct": round(result.total_return_pct, 2),
        "sharpe_ratio":     round(result.sharpe_ratio, 3),
        "max_drawdown_pct": round(result.max_drawdown_pct, 2),
        "win_rate_pct":     round(result.win_rate_pct, 2),
        "profit_factor":    round(result.profit_factor, 3),
        "total_trades":     result.total_trades,
        "winning_trades":   result.winning_trades,
        "losing_trades":    result.losing_trades,
        "equity_curve":     result.equity_curve[::4],   # sample every 4th for compactness
    }


def _simulate(
    df: pd.DataFrame,
    instrument: str,
    cash: float,
    risk_pct: float,
    sl_atr_mult: float,
    tp_atr_mult: float,
    min_score: float,
) -> BacktestResult:

    # ── Compute indicators ─────────────────────────────────────────────────────
    c, h, l = df["close"], df["high"], df["low"]

    ema9   = ta.ema(c, length=9)
    ema21  = ta.ema(c, length=21)
    ema200 = ta.ema(c, length=200)
    rsi    = ta.rsi(c, length=14)
    atr    = ta.atr(h, l, c, length=14)
    macd_df = ta.macd(c, fast=12, slow=26, signal=9)

    pip_size  = PIP_SIZE.get(instrument, 0.0001)
    pip_value = PIP_VALUE.get(instrument, 10.0)

    equity          = cash
    equity_curve    = [cash]
    trades: list[BacktestTrade] = []
    open_trade: BacktestTrade | None = None
    peak_equity     = cash
    max_dd          = 0.0

    for i in range(200, len(df)):
        row    = df.iloc[i]
        price  = float(row["close"])
        high_i = float(row["high"])
        low_i  = float(row["low"])

        # Manage open trade
        if open_trade:
            hit_sl = hit_tp = False
            if open_trade.direction == "BUY":
                hit_sl = low_i  <= open_trade.stop_loss
                hit_tp = high_i >= open_trade.take_profit
            else:
                hit_sl = high_i >= open_trade.stop_loss
                hit_tp = low_i  <= open_trade.take_profit

            if hit_tp or hit_sl or i == len(df) - 1:
                exit_p  = open_trade.take_profit if hit_tp else open_trade.stop_loss if hit_sl else price
                sl_dist = abs(open_trade.entry_price - open_trade.stop_loss)
                if open_trade.direction == "BUY":
                    pnl_pips = (exit_p - open_trade.entry_price) / pip_size
                else:
                    pnl_pips = (open_trade.entry_price - exit_p) / pip_size
                pnl_usd = pnl_pips * pip_value * open_trade.lot_size

                open_trade.exit_time  = df.index[i]
                open_trade.exit_price = exit_p
                open_trade.pnl_pips   = round(pnl_pips, 1)
                open_trade.pnl_usd    = round(pnl_usd, 2)
                open_trade.status     = "closed_tp" if hit_tp else "closed_sl" if hit_sl else "closed_end"
                equity += pnl_usd
                trades.append(open_trade)
                open_trade = None

        # Look for new signal
        if open_trade is None:
            score, direction = _compute_signal(
                i, ema9, ema21, ema200, rsi, atr, macd_df, c
            )
            if score >= min_score and direction != "NEUTRAL":
                curr_atr   = float(atr.iloc[i]) if not pd.isna(atr.iloc[i]) else pip_size * 20
                sl_dist    = curr_atr * sl_atr_mult
                tp_dist    = curr_atr * tp_atr_mult

                if direction == "BUY":
                    sl = price - sl_dist
                    tp = price + tp_dist
                else:
                    sl = price + sl_dist
                    tp = price - tp_dist

                # Position sizing (1% risk)
                sl_pips  = sl_dist / pip_size
                risk_usd = equity * (risk_pct / 100)
                lot_size = max(0.01, min(risk_usd / (sl_pips * pip_value), 5.0))
                lot_size = round(lot_size, 2)

                open_trade = BacktestTrade(
                    instrument   = instrument,
                    direction    = direction,
                    entry_time   = df.index[i],
                    entry_price  = price,
                    stop_loss    = round(sl, 5),
                    take_profit  = round(tp, 5),
                    lot_size     = lot_size,
                )

        equity_curve.append(round(equity, 2))
        peak_equity = max(peak_equity, equity)
        dd = (peak_equity - equity) / peak_equity * 100
        max_dd = max(max_dd, dd)

    # ── Stats ──────────────────────────────────────────────────────────────────
    closed  = [t for t in trades if t.status != "open"]
    winners = [t for t in closed if t.pnl_usd > 0]
    losers  = [t for t in closed if t.pnl_usd <= 0]

    gross_profit = sum(t.pnl_usd for t in winners)
    gross_loss   = abs(sum(t.pnl_usd for t in losers))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else 9.99

    win_rate = len(winners) / len(closed) * 100 if closed else 0.0

    # Sharpe (annualised, using daily equity changes)
    eq_series = pd.Series(equity_curve)
    daily_ret = eq_series.pct_change().dropna()
    sharpe = (daily_ret.mean() / daily_ret.std() * (252 ** 0.5)) if daily_ret.std() > 0 else 0.0

    return BacktestResult(
        instrument       = instrument,
        timeframe        = "H1",
        days             = days,
        starting_cash    = cash,
        final_equity     = equity,
        total_return_pct = (equity - cash) / cash * 100,
        sharpe_ratio     = float(sharpe),
        max_drawdown_pct = max_dd,
        win_rate_pct     = win_rate,
        profit_factor    = profit_factor,
        total_trades     = len(closed),
        winning_trades   = len(winners),
        losing_trades    = len(losers),
        trades           = closed[-200:],
        equity_curve     = equity_curve,
    )


def _compute_signal(
    i: int, ema9, ema21, ema200, rsi, atr, macd_df, close
) -> tuple[float, str]:
    """Simplified TA-only signal for backtesting (no live sentiment)."""
    try:
        e9  = float(ema9.iloc[i])
        e21 = float(ema21.iloc[i])
        e200 = float(ema200.iloc[i])
        r   = float(rsi.iloc[i])
        c   = float(close.iloc[i])

        if any(pd.isna(v) for v in [e9, e21, e200, r]):
            return 0.0, "NEUTRAL"

        macd_line = float(macd_df["MACD_12_26_9"].iloc[i])
        macd_sig  = float(macd_df["MACDs_12_26_9"].iloc[i])
        prev_macd = float(macd_df["MACD_12_26_9"].iloc[i-1])
        prev_sig  = float(macd_df["MACDs_12_26_9"].iloc[i-1])

        bull_score = 0.0
        bear_score = 0.0

        # EMA trend
        if e9 > e21 and c > e200:
            bull_score += 0.35
        elif e9 < e21 and c < e200:
            bear_score += 0.35

        # RSI
        if 45 < r < 68:
            bull_score += 0.25
        elif 32 < r < 55:
            bear_score += 0.25

        # MACD cross
        if prev_macd < prev_sig and macd_line > macd_sig:
            bull_score += 0.25
        elif prev_macd > prev_sig and macd_line < macd_sig:
            bear_score += 0.25

        # MACD above zero
        if macd_line > 0:
            bull_score += 0.15
        else:
            bear_score += 0.15

        if bull_score > bear_score + 0.15 and bull_score >= 0.55:
            return bull_score, "BUY"
        if bear_score > bull_score + 0.15 and bear_score >= 0.55:
            return bear_score, "SELL"
        return max(bull_score, bear_score), "NEUTRAL"

    except Exception:
        return 0.0, "NEUTRAL"


if __name__ == "__main__":
    result = asyncio.run(run_backtest("EURUSD", days=365))
    print(result)
