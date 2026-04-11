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
            "Classify the current market regime for an instrument using ADX, EMA alignment, and ATR. "
            "Returns: TRENDING_BULLISH, TRENDING_BEARISH, RANGING, VOLATILE, EXHAUSTED, or BREAKOUT. "
            "CRITICAL: check regime before every trade. "
            "Do NOT use trend-following entries in RANGING markets. "
            "Do NOT trade VOLATILE or EXHAUSTED regimes — wait for structure. "
            "BREAKOUT regime = enter immediately with momentum and tight initial stop."
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
