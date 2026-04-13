"""
Claude tool definitions for the NVC trading agent.
These are passed to the Anthropic API as tools the agent can call.
"""

from typing import Any

TRADING_TOOLS: list[dict[str, Any]] = [
    {
        "name": "get_news_sentiment",
        "description": (
            "Retrieve aggregated news and social media sentiment for a trading instrument. "
            "Returns sentiment scores from Reuters, AP, FT, Twitter, Reddit, and StockTwits, "
            "weighted by source credibility and time-decay. Also returns the top news events "
            "driving the sentiment in the past 4 hours."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "instrument": {
                    "type": "string",
                    "description": "The trading instrument symbol (e.g. EURUSD, XAUUSD, USOIL)",
                },
                "lookback_hours": {
                    "type": "number",
                    "description": "How many hours back to aggregate sentiment. Default 4.",
                    "default": 4,
                },
            },
            "required": ["instrument"],
        },
    },
    {
        "name": "get_technical_analysis",
        "description": (
            "Get multi-timeframe technical analysis for an instrument. "
            "Returns RSI, EMA (9/21/200), MACD, Bollinger Bands, ATR, Stochastic, "
            "pivot points, and detected candlestick patterns across M15, H1, H4, D1 timeframes. "
            "Also returns an overall TA bias (bullish/bearish/neutral) and strength score."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "instrument": {
                    "type": "string",
                    "description": "The trading instrument symbol",
                },
                "timeframes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Timeframes to analyse. Default: ['M15', 'H1', 'H4', 'D1']",
                },
            },
            "required": ["instrument"],
        },
    },
    {
        "name": "get_economic_calendar",
        "description": (
            "Check upcoming high-impact economic events for the next 48 hours. "
            "Returns event name, time, currency affected, impact level (low/medium/high), "
            "forecast vs previous values. Use this to identify trading blackout periods."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "currencies": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Currency codes to filter events for (e.g. ['USD', 'EUR', 'GBP']). Empty = all.",
                },
                "hours_ahead": {
                    "type": "number",
                    "description": "How many hours ahead to look. Default 48.",
                    "default": 48,
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_open_positions",
        "description": (
            "Retrieve all currently open trading positions on MT5. "
            "Returns ticket, instrument, direction, entry price, current price, "
            "unrealised P&L, SL, TP, lot size, and open time for each position."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "get_account_metrics",
        "description": (
            "Get current account health metrics: balance, equity, margin, free margin, "
            "daily P&L, daily drawdown %, weekly drawdown %, total open risk %, "
            "and system status (active/paused/emergency_stop)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "get_price_data",
        "description": (
            "Get current market price data for an instrument: bid, ask, spread in pips, "
            "24h high/low, and the last 20 OHLCV candles for a given timeframe."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "instrument": {
                    "type": "string",
                    "description": "The trading instrument symbol",
                },
                "timeframe": {
                    "type": "string",
                    "description": "Candle timeframe for OHLCV data (M1, M5, M15, H1, H4, D1)",
                    "default": "H1",
                },
            },
            "required": ["instrument"],
        },
    },
    {
        "name": "execute_trade",
        "description": (
            "Execute a trade on MT5 via the ZeroMQ bridge. "
            "Sends a signal packet to the Expert Advisor which executes the order. "
            "Returns the fill price, ticket number, and execution timestamp. "
            "IMPORTANT: Always ensure score >= 0.60 and daily drawdown < 3% before calling this."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "instrument": {
                    "type": "string",
                    "description": "Trading instrument (e.g. EURUSD, XAUUSD)",
                },
                "direction": {
                    "type": "string",
                    "enum": ["BUY", "SELL"],
                    "description": "Trade direction",
                },
                "lot_size": {
                    "type": "number",
                    "description": "Position size in lots (e.g. 0.10). Must respect 1% risk rule.",
                },
                "stop_loss": {
                    "type": "number",
                    "description": "Stop loss price level",
                },
                "take_profit": {
                    "type": "number",
                    "description": "Take profit price level",
                },
                "score": {
                    "type": "number",
                    "description": "Signal confluence score (0.0–1.0). Must be >= 0.60.",
                },
                "reason": {
                    "type": "string",
                    "description": "Human-readable explanation of why this trade is being placed (logged for audit)",
                },
            },
            "required": ["instrument", "direction", "lot_size", "stop_loss", "take_profit", "score", "reason"],
        },
    },
    {
        "name": "close_position",
        "description": "Close an open position by its MT5 ticket number.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ticket": {
                    "type": "integer",
                    "description": "MT5 position ticket number",
                },
                "reason": {
                    "type": "string",
                    "description": "Reason for closing (logged for audit)",
                },
            },
            "required": ["ticket", "reason"],
        },
    },
    {
        "name": "modify_position",
        "description": "Modify the stop-loss and/or take-profit of an open position (trailing stop, move to breakeven, etc.).",
        "input_schema": {
            "type": "object",
            "properties": {
                "ticket": {
                    "type": "integer",
                    "description": "MT5 position ticket number",
                },
                "new_stop_loss": {
                    "type": "number",
                    "description": "New stop loss price (null to leave unchanged)",
                },
                "new_take_profit": {
                    "type": "number",
                    "description": "New take profit price (null to leave unchanged)",
                },
                "reason": {
                    "type": "string",
                    "description": "Reason for modification",
                },
            },
            "required": ["ticket", "reason"],
        },
    },

    # ── Intelligence tools (new) ──────────────────────────────────────────────

    {
        "name": "get_order_flow",
        "description": (
            "Get institutional and retail positioning data for an instrument. "
            "Returns: OANDA order book (where buy/sell orders are clustered by price level), "
            "retail long/short ratio (contrarian signal — crowd is usually wrong at extremes), "
            "CFTC COT report (hedge fund non-commercial net positioning, weekly), "
            "order walls above/below current price, crowding score, and positioning signal. "
            "Use this to identify if institutional money is positioned FOR or AGAINST your trade, "
            "and whether retail is dangerously crowded on one side."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "instrument": {
                    "type": "string",
                    "description": "Trading instrument symbol (e.g. EURUSD, XAUUSD)",
                },
            },
            "required": ["instrument"],
        },
    },

    {
        "name": "get_macro_environment",
        "description": (
            "Get the global macro environment that drives long-term currency and commodity trends. "
            "Returns: Fed Funds Rate, yield curve spread (2Y vs 10Y — inverted = recession risk), "
            "inflation expectations, USD bias (HAWKISH/DOVISH), recession risk level, "
            "and interest rate differentials between currency pairs. "
            "Use this to understand the dominant macro regime: risk-on, risk-off, dollar strength, etc."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "instruments": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Instruments to compute rate differentials for. Optional.",
                },
            },
            "required": [],
        },
    },

    {
        "name": "get_institutional_research",
        "description": (
            "Get the latest research, speeches, and reports from central banks, IMF, BIS, "
            "and top financial research institutions. "
            "Returns: Federal Reserve speeches (hawkish/dovish signals), ECB/BoE/BoJ stances, "
            "IMF and BIS macro outlook, FX analyst research, tone classification per item. "
            "Use this to understand what the smartest institutions in the world are signalling "
            "about rate paths, recession risk, and currency outlooks."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "currencies": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Filter by currency codes (e.g. ['USD', 'EUR']). Empty = all.",
                },
                "hours": {
                    "type": "number",
                    "description": "How many hours back to search. Default 24.",
                    "default": 24,
                },
            },
            "required": [],
        },
    },

    {
        "name": "get_risk_sentiment",
        "description": (
            "Get real-time global risk appetite from Tesla (TSLA), S&P 500 (SPX), and "
            "JP Morgan Chase (JPM) equity price action. "
            "TSLA is the highest-beta risk barometer: TSLA +5% 5d = strong risk-on = AUD/NZD/GBP outperform, USD weakens. "
            "TSLA -5% 5d = risk-off = JPY/CHF/Gold rally. "
            "JPM stock signals credit conditions: JPM rising = banks healthy = benign credit = risk-on. "
            "Also returns JP Morgan's published 2026 FX price targets (EURUSD 1.20, USDJPY 164, XAUUSD 3200). "
            "Use this in Step 3 (Positioning) alongside COT data for a complete crowd/institutional picture."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },

    {
        "name": "get_portfolio_analysis",
        "description": (
            "Run portfolio-level financial planning and risk analysis. "
            "Returns: optimal position sizing via Kelly Criterion (given win rate and avg win/loss), "
            "Monte Carlo P&L projection (500 simulations, 30-day horizon with percentile outcomes), "
            "Value at Risk at 95% confidence, maximum expected drawdown, and ruin probability. "
            "Use this before scaling up position sizes or when deciding overall capital allocation."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "account_balance": {
                    "type": "number",
                    "description": "Current account balance in USD",
                },
                "win_rate": {
                    "type": "number",
                    "description": "Historical win rate (0.0–1.0). Use 0.55 if unknown.",
                    "default": 0.55,
                },
                "avg_win_pips": {
                    "type": "number",
                    "description": "Average winning trade size in pips. Default 30.",
                    "default": 30,
                },
                "avg_loss_pips": {
                    "type": "number",
                    "description": "Average losing trade size in pips. Default 15.",
                    "default": 15,
                },
                "trades_per_day": {
                    "type": "number",
                    "description": "Estimated number of trades per day. Default 3.",
                    "default": 3,
                },
            },
            "required": ["account_balance"],
        },
    },

    {
        "name": "get_market_regime",
        "description": (
            "Classify the current market regime for an instrument. "
            "Returns: TRENDING_BULLISH, TRENDING_BEARISH, RANGING, CRISIS, EXHAUSTED, or BREAKOUT. "
            "Also returns ATR ratio (10d/30d), autocorrelation (>+0.2=trending, ~0=ranging), "
            "ADX, and EMA alignment. "
            "MANDATORY: call this first for every instrument before analysis. "
            "CRISIS regime (ATR ratio > 1.8): reduce all sizes to 0.3×, manage existing only. "
            "EXHAUSTED: trend ending — close trend trades, do not add. "
            "RANGING: use mean reversion entries, NOT momentum breakouts. "
            "TRENDING: use momentum entries, trail stops aggressively."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "instrument": {
                    "type": "string",
                    "description": "Trading instrument symbol",
                },
                "ohlcv": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "OHLCV candle data. If not provided, will be fetched automatically.",
                },
            },
            "required": ["instrument"],
        },
    },

    {
        "name": "check_edge_filter",
        "description": (
            "Run the 8-condition Edge Filter on a potential trade setup. "
            "This is the final quality gate before execution — only A/A+/A++ setups should be traded. "
            "Returns: grade (A++/A+/A/FAIL), score (0-8 conditions met), "
            "recommended position size (fraction of max), recommended RR ratio, "
            "and which specific conditions passed or failed. "
            "Special setups detected: INSTITUTIONAL_DIVERGENCE (hedge funds vs retail opposite sides), "
            "BREAKOUT, NEWS_AFTERMATH. These get bonus scoring. "
            "NEVER execute a trade that scores FAIL on the edge filter — regardless of your confidence."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "instrument":   {"type": "string", "description": "Instrument symbol"},
                "direction":    {"type": "string", "enum": ["BUY", "SELL"]},
                "ta_score":     {"type": "number", "description": "Technical analysis score 0.0–1.0"},
                "sentiment":    {"type": "object", "description": "Sentiment result from get_news_sentiment"},
                "order_flow":   {"type": "object", "description": "Order flow result from get_order_flow"},
                "macro":        {"type": "object", "description": "Macro result from get_macro_environment"},
                "regime":       {"type": "object", "description": "Regime result from get_market_regime"},
                "spread_pips":  {"type": "number", "description": "Current spread in pips (optional)"},
                "news_event_minutes_ago": {
                    "type": "number",
                    "description": "Minutes since last high-impact news event (optional)",
                },
            },
            "required": ["instrument", "direction", "ta_score", "sentiment", "order_flow", "macro", "regime"],
        },
    },

    {
        "name": "get_performance_stats",
        "description": (
            "Get real trading performance statistics from closed trades. "
            "Returns: win_rate, avg_win_usd, avg_loss_usd, profit_factor, expectancy_per_trade, "
            "max_consecutive_losses, Sharpe ratio, Kelly fraction, recommended_risk_pct, "
            "best/worst instrument, daily P&L series, and a plain-English assessment. "
            "Call this at the start of each cycle to calibrate position sizing. "
            "Use recommended_risk_pct instead of a fixed 1% when sufficient trade history exists (≥20 trades). "
            "If profit_factor < 1.0 or max_consecutive_losses ≥ 5, reduce position sizes immediately."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "lookback_days": {
                    "type": "integer",
                    "description": "Days of history to analyse. Default 30.",
                    "default": 30,
                },
            },
            "required": [],
        },
    },

    {
        "name": "calculate_position_size",
        "description": (
            "Calculate the correct lot size using the Van Tharp fixed-fractional method "
            "with regime, conviction, AND circuit breaker multipliers. "
            "ALWAYS call this before execute_trade — it enforces all risk rules automatically. "
            "Base risk: 1% of equity. "
            "Regime multipliers: TRENDING=1.0×, RANGING=0.7×, CRISIS/VOLATILE=0.3×. "
            "Conviction multipliers: 4-5 factors aligned=1.3×, 3 factors=1.0×, 2 factors=0.6×. "
            "Circuit breaker (automatic): daily DD>=2% returns lot_size=0 (BLOCKED). "
            "Weekly DD>=5% (Rule R5) halves all sizes automatically. "
            "Hard ceiling: never exceeds 2% risk regardless of multipliers. "
            "Returns: lot_size (use this directly), risk_usd, risk_pct, instruction."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "instrument":      {"type": "string", "description": "Instrument symbol (e.g. EURUSD)"},
                "entry_price":     {"type": "number", "description": "Proposed entry price"},
                "stop_loss":       {"type": "number", "description": "Stop loss price"},
                "account_equity":  {"type": "number", "description": "Current account equity in USD"},
                "regime": {
                    "type": "string",
                    "description": "Current regime from get_market_regime",
                    "enum": ["TRENDING_BULLISH", "TRENDING_BEARISH", "BREAKOUT", "RANGING", "EXHAUSTED", "VOLATILE", "CRISIS"],
                    "default": "RANGING",
                },
                "factors_aligned": {
                    "type": "integer",
                    "description": "Number of the 5 signal factors that align with this trade (0–5)",
                    "default": 3,
                },
                "druckenmiller_multiplier": {
                    "type": "number",
                    "description": (
                        "Conviction multiplier from get_trader_analysis.final_multiplier. "
                        "When provided, overrides the standard factors_aligned lookup. "
                        "Values: 1.5 (A++/Soros trap), 1.4 (Turtle S2), 1.3 (A+), 1.0 (A), 0.6 (below A)."
                    ),
                },
            },
            "required": ["instrument", "entry_price", "stop_loss", "account_equity"],
        },
    },

    {
        "name": "get_trader_analysis",
        "description": (
            "Run the Legendary Trader analysis pipeline on a specific setup. "
            "Applies all 7 historically proven trader methodologies in sequence:\n"
            "  1. LIVERMORE  — Is this a pivotal structural break (swing high/low)? Only enter at confirmed pivots.\n"
            "  2. SEYKOTA    — Does 150-day MA confirm the direction? Never fight the master trend.\n"
            "  3. TURTLES    — Is this a 20-day (System 1) or 55-day (System 2) channel breakout?\n"
            "  4. PTJ        — Does the setup offer ≥2:1 R:R? PTJ refuses worse setups.\n"
            "  5. SOROS      — Is the central bank defending an indefensible level? Policy trap = massive trade.\n"
            "  6. DRUCKENMILLER — What conviction multiplier should be applied to sizing?\n"
            "  7. SIMONS     — What is the pattern-frequency expectancy score (S/A/B-TIER)?\n\n"
            "Returns: verdict (ALL SYSTEMS GO / STRONG SETUP / MARGINAL / AVOID), "
            "green_lights (N/7 traders agree), final_multiplier (use in calculate_position_size), "
            "and detailed output from each strategy.\n\n"
            "WHEN TO CALL: after check_edge_filter passes. Pass the final_multiplier as "
            "druckenmiller_multiplier in calculate_position_size to scale correctly."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "instrument":   {"type": "string", "description": "Trading instrument symbol"},
                "direction":    {"type": "string", "enum": ["BUY", "SELL"]},
                "entry":        {"type": "number", "description": "Proposed entry price"},
                "stop_loss":    {"type": "number", "description": "Proposed stop loss price"},
                "take_profit":  {"type": "number", "description": "Proposed take profit price"},
                "atr":          {"type": "number", "description": "ATR value for the instrument"},
                "edge_score":   {"type": "integer", "description": "Edge filter score (0–8) from check_edge_filter"},
                "macro_score":  {"type": "number", "description": "Macro confidence score 0.0–1.0"},
                "active_patterns": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Pattern names already detected (e.g. ['london_breakout', 'institutional_divergence'])",
                },
            },
            "required": ["instrument", "direction", "entry", "stop_loss", "take_profit", "atr", "edge_score"],
        },
    },

    {
        "name": "get_execution_quality",
        "description": (
            "Get execution quality metrics: average slippage per instrument, "
            "spread conditions (is the current spread normal or spiked?), "
            "best session for trading a given instrument, and recent fill quality. "
            "Use this to decide WHEN and HOW to execute — avoid trading in poor conditions."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "instrument": {
                    "type": "string",
                    "description": "Instrument to check. Leave empty to get all instruments.",
                },
            },
            "required": [],
        },
    },
]
