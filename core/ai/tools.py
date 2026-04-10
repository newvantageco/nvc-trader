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
]
