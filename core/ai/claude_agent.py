"""
NVC VANTAGE — Claude Autonomous Trading Agent

The primary intelligence layer. Claude reasons about market conditions,
decides on trades, and executes them via tool calls. Runs on a schedule
and can also be triggered by high-impact news events.
"""

import json
import asyncio
from datetime import datetime, timezone
from typing import Any

import anthropic
from loguru import logger

from core.ai.tools import TRADING_TOOLS
from core.ai.prompts import TRADING_AGENT_SYSTEM_PROMPT
from core.bridge.oanda_client import OandaClient
from core.risk.circuit_breaker import CircuitBreaker
from core.risk.position_sizer import PositionSizer
from core.ingestion.news_fetcher import NewsFetcher
from core.sentiment.finbert_pipeline import SentimentPipeline
from core.technical.indicator_engine import IndicatorEngine
from core.ingestion.economic_calendar import EconomicCalendar
from core.db.supabase_client import SupabaseClient
from core.ingestion.cot_fetcher import COTFetcher
from core.ingestion.order_book import OrderBookReader
from core.ingestion.fred_client import FREDClient
from core.ingestion.research_fetcher import ResearchFetcher
from core.execution.smart_executor import SmartExecutor
from core.planning.portfolio_optimizer import PortfolioOptimizer


WATCHLIST = [
    "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD",
    "NZDUSD", "USDCHF", "EURJPY", "GBPJPY",
    "XAUUSD", "XAGUSD", "USOIL", "UKOIL", "NATGAS",
]


class VantageAgent:
    """
    Claude-powered autonomous trading agent.
    Orchestrates all data sources and executes trades via tool use.
    """

    def __init__(self) -> None:
        self.client = anthropic.Anthropic()
        self.zmq = OandaClient()   # OANDA REST for cloud; swap to ZMQPublisher for MT5
        self.circuit_breaker = CircuitBreaker()
        self.position_sizer = PositionSizer()
        self.news_fetcher = NewsFetcher()
        self.sentiment = SentimentPipeline()
        self.ta_engine = IndicatorEngine()
        self.calendar = EconomicCalendar()
        self.db              = SupabaseClient()
        self.cot             = COTFetcher()
        self.order_book      = OrderBookReader()
        self.fred            = FREDClient()
        self.research        = ResearchFetcher()
        self.smart_executor  = SmartExecutor()
        self.optimizer       = PortfolioOptimizer()
        self._open_positions: list[dict] = []
        self._account_metrics: dict = {}

    # ─── Main Entry Point ──────────────────────────────────────────────────────

    async def run_cycle(self, trigger: str = "scheduled") -> dict:
        """
        Execute one full agent cycle.
        Claude analyses all instruments and executes any valid signals.
        """
        cycle_id = f"cycle_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
        logger.info(f"[VANTAGE] Starting cycle {cycle_id} | trigger={trigger}")

        # Refresh shared state before handing to Claude
        await self._refresh_state()

        if self.circuit_breaker.is_hard_stopped():
            logger.warning("[VANTAGE] Circuit breaker HARD STOP — skipping cycle")
            return {"cycle_id": cycle_id, "status": "hard_stop", "trades": []}

        # Build initial context message for Claude
        context = self._build_context_message(trigger)

        messages = [{"role": "user", "content": context}]
        trades_executed = []
        iterations = 0
        max_iterations = 20  # safety ceiling on tool calls per cycle

        # ── Agentic loop ──────────────────────────────────────────────────────
        while iterations < max_iterations:
            iterations += 1
            logger.debug(f"[VANTAGE] Agent iteration {iterations}")

            response = self.client.messages.create(
                model="claude-opus-4-6",
                max_tokens=8096,
                system=TRADING_AGENT_SYSTEM_PROMPT,
                tools=TRADING_TOOLS,
                messages=messages,
            )

            # Append assistant response to conversation
            messages.append({"role": "assistant", "content": response.content})

            # Check stop reason
            if response.stop_reason == "end_turn":
                # Claude is done — extract final reasoning text
                final_text = self._extract_text(response.content)
                logger.info(f"[VANTAGE] Cycle complete: {final_text[:200]}...")
                break

            if response.stop_reason != "tool_use":
                logger.warning(f"[VANTAGE] Unexpected stop_reason: {response.stop_reason}")
                break

            # Process tool calls
            tool_results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue

                logger.info(f"[VANTAGE] Tool call: {block.name}({json.dumps(block.input)[:120]})")
                result = await self._dispatch_tool(block.name, block.input)

                # Track trades for return value
                if block.name == "execute_trade" and result.get("status") == "FILLED":
                    trades_executed.append(result)

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(result),
                })

            messages.append({"role": "user", "content": tool_results})

        # ── Log cycle to DB ───────────────────────────────────────────────────
        await self._log_cycle(cycle_id, trigger, trades_executed, messages)

        return {
            "cycle_id": cycle_id,
            "status": "completed",
            "trades": trades_executed,
            "iterations": iterations,
        }

    # ─── Tool Dispatcher ───────────────────────────────────────────────────────

    async def _dispatch_tool(self, name: str, inputs: dict) -> dict:
        """Route Claude's tool calls to the appropriate service."""
        try:
            match name:
                case "get_news_sentiment":
                    return await self._tool_news_sentiment(**inputs)
                case "get_technical_analysis":
                    return await self._tool_technical_analysis(**inputs)
                case "get_economic_calendar":
                    return await self._tool_economic_calendar(**inputs)
                case "get_open_positions":
                    return {"positions": self._open_positions}
                case "get_account_metrics":
                    return self._account_metrics
                case "get_price_data":
                    return await self._tool_price_data(**inputs)
                case "execute_trade":
                    return await self._tool_execute_trade(**inputs)
                case "close_position":
                    return await self._tool_close_position(**inputs)
                case "modify_position":
                    return await self._tool_modify_position(**inputs)
                case "get_order_flow":
                    return await self._tool_order_flow(**inputs)
                case "get_macro_environment":
                    return await self._tool_macro_environment(**inputs)
                case "get_institutional_research":
                    return await self._tool_institutional_research(**inputs)
                case "get_portfolio_analysis":
                    return await self._tool_portfolio_analysis(**inputs)
                case "get_execution_quality":
                    return await self._tool_execution_quality(**inputs)
                case _:
                    return {"error": f"Unknown tool: {name}"}
        except Exception as exc:
            logger.exception(f"[TOOL ERROR] {name}: {exc}")
            return {"error": str(exc)}

    # ─── Tool Implementations ──────────────────────────────────────────────────

    async def _tool_news_sentiment(
        self, instrument: str, lookback_hours: float = 4.0
    ) -> dict:
        articles = await self.news_fetcher.fetch_for_instrument(
            instrument, hours=lookback_hours
        )
        scored = self.sentiment.score_articles(articles)
        aggregated = self.sentiment.aggregate(scored, lookback_hours=lookback_hours)
        return {
            "instrument": instrument,
            "sentiment_score": aggregated["score"],       # -1.0 to +1.0
            "normalised_score": aggregated["normalised"], # 0.0 to 1.0
            "article_count": len(articles),
            "dominant_bias": aggregated["bias"],          # bullish/bearish/neutral
            "top_events": aggregated["top_events"][:5],
            "sources_breakdown": aggregated["sources"],
        }

    async def _tool_technical_analysis(
        self, instrument: str, timeframes: list[str] | None = None
    ) -> dict:
        if timeframes is None:
            timeframes = ["M15", "H1", "H4", "D1"]
        result = await self.ta_engine.analyse(instrument, timeframes)
        return result

    async def _tool_economic_calendar(
        self, currencies: list[str] | None = None, hours_ahead: float = 48.0
    ) -> dict:
        events = await self.calendar.get_events(
            currencies=currencies, hours_ahead=hours_ahead
        )
        # Annotate blackout windows
        blackouts = self.calendar.compute_blackouts(events)
        return {"events": events, "blackout_windows": blackouts}

    async def _tool_price_data(self, instrument: str, timeframe: str = "H1") -> dict:
        return await self.ta_engine.get_price_data(instrument, timeframe)

    async def _tool_execute_trade(
        self,
        instrument: str,
        direction: str,
        lot_size: float,
        stop_loss: float,
        take_profit: float,
        score: float,
        reason: str,
    ) -> dict:
        # Hard safety guards — these can never be overridden by Claude
        if score < 0.60:
            return {"status": "REJECTED", "reason": f"Score {score:.2f} below minimum 0.60"}

        if self.circuit_breaker.is_daily_limit_hit():
            return {"status": "REJECTED", "reason": "Daily drawdown limit reached"}

        if len(self._open_positions) >= 8:
            return {"status": "REJECTED", "reason": "Maximum open trades (8) reached"}

        # Validate lot size against risk rules
        validated_lot = self.position_sizer.validate_lot(
            instrument=instrument,
            lot_size=lot_size,
            stop_loss_price=stop_loss,
            account_equity=self._account_metrics.get("equity", 10000),
        )
        if not validated_lot["valid"]:
            return {"status": "REJECTED", "reason": validated_lot["reason"]}

        signal = {
            "signal_id": f"sig_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "instrument": instrument,
            "direction": direction,
            "entry_type": "MARKET",
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "lot_size": validated_lot["lot_size"],
            "score": score,
            "reason": reason,
            "expiry": None,
        }

        # Send to MT5 via ZeroMQ
        fill = await self.zmq.send_signal(signal)

        # Persist to DB
        await self.db.insert("signals", {**signal, "fill": fill, "agent": "claude-vantage"})

        logger.success(
            f"[TRADE EXECUTED] {direction} {instrument} "
            f"lot={validated_lot['lot_size']} score={score:.2f} fill={fill}"
        )
        return {"status": "FILLED", **fill, "signal": signal}

    async def _tool_close_position(self, ticket: int, reason: str) -> dict:
        result = await self.zmq.close_position(ticket, reason)
        await self.db.insert("position_closes", {"ticket": ticket, "reason": reason, "result": result})
        return result

    async def _tool_modify_position(
        self,
        ticket: int,
        reason: str,
        new_stop_loss: float | None = None,
        new_take_profit: float | None = None,
    ) -> dict:
        result = await self.zmq.modify_position(ticket, new_stop_loss, new_take_profit)
        await self.db.insert("position_modifications", {
            "ticket": ticket, "reason": reason,
            "new_sl": new_stop_loss, "new_tp": new_take_profit, "result": result,
        })
        return result

    async def _tool_order_flow(self, instrument: str) -> dict:
        """COT positioning + OANDA order book combined."""
        cot_data, ob_data = await asyncio.gather(
            self.cot.get_positioning(instrument),
            self.order_book.get_order_flow(instrument),
        )
        return {
            "instrument":          instrument,
            "cot_positioning":     cot_data,
            "order_book":          ob_data,
            "combined_signal": _combine_positioning(cot_data, ob_data),
        }

    async def _tool_macro_environment(
        self, instruments: list[str] | None = None
    ) -> dict:
        return await self.fred.get_macro_environment(instruments or [])

    async def _tool_institutional_research(
        self,
        currencies: list[str] | None = None,
        hours: int = 24,
    ) -> dict:
        items = await self.research.fetch_research(currencies=currencies, hours=hours)
        # Group by tone
        by_tone: dict[str, list] = {}
        for item in items:
            tone = item.get("tone", "NEUTRAL")
            by_tone.setdefault(tone, []).append(item)

        return {
            "total_items": len(items),
            "by_tone": {k: len(v) for k, v in by_tone.items()},
            "top_items": items[:10],
            "dominant_tone": max(by_tone, key=lambda k: len(by_tone[k])) if by_tone else "NEUTRAL",
        }

    async def _tool_portfolio_analysis(
        self,
        account_balance: float,
        win_rate: float = 0.55,
        avg_win_pips: float = 30.0,
        avg_loss_pips: float = 15.0,
        trades_per_day: float = 3.0,
    ) -> dict:
        pip_value = 10.0   # USD per pip per standard lot (approx)
        kelly = self.optimizer.kelly_position_size(
            win_rate=win_rate,
            avg_win_pips=avg_win_pips,
            avg_loss_pips=avg_loss_pips,
            account_balance=account_balance,
            pip_value=pip_value,
        )
        mc = self.optimizer.monte_carlo_projection(
            account_balance=account_balance,
            win_rate=win_rate,
            avg_win_usd=avg_win_pips * pip_value * kelly["optimal_lots"],
            avg_loss_usd=avg_loss_pips * pip_value * kelly["optimal_lots"],
            trades_per_day=trades_per_day,
        )
        return {
            "account_balance":  account_balance,
            "kelly_sizing":     kelly,
            "monte_carlo_30d":  mc,
            "recommendation":   (
                f"Optimal lot size: {kelly['optimal_lots']} | "
                f"50th percentile 30-day balance: ${mc['p50_balance']:,.0f} "
                f"({mc['expected_return_pct']:+.1f}%) | "
                f"Ruin probability: {mc['ruin_probability_pct']:.1f}%"
            ),
        }

    async def _tool_execution_quality(
        self, instrument: str | None = None
    ) -> dict:
        quality = self.smart_executor.get_execution_quality(instrument)
        session, liquidity = SmartExecutor._current_session_quality()
        return {
            "current_session":    session,
            "session_quality":    liquidity,
            "slippage_stats":     quality,
            "recommendation": (
                f"Current session: {session} ({liquidity} liquidity). "
                "Best for Forex: London/NY overlap 12:00–16:00 UTC. "
                "Best for commodities: NY session 13:00–21:00 UTC."
            ),
        }

    # ─── Helpers ───────────────────────────────────────────────────────────────

    async def _refresh_state(self) -> None:
        """Pull fresh account and position data before each cycle."""
        self._account_metrics = await self.zmq.get_account_info()
        self._open_positions = await self.zmq.get_positions()
        self.circuit_breaker.update(self._account_metrics)

    def _build_context_message(self, trigger: str) -> str:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        open_count = len(self._open_positions)
        equity = self._account_metrics.get("equity", "unknown")
        daily_dd = self._account_metrics.get("daily_drawdown_pct", 0.0)

        return (
            f"VANTAGE CYCLE — {now}\n"
            f"Trigger: {trigger}\n"
            f"Account equity: ${equity:,}\n"
            f"Daily drawdown: {daily_dd:.2f}%\n"
            f"Open positions: {open_count}/8\n\n"
            f"Watchlist: {', '.join(WATCHLIST)}\n\n"
            "Please begin your analysis cycle. Start by checking the economic calendar "
            "for blackout periods, then systematically analyse each instrument on the watchlist. "
            "Execute any valid trades that meet the minimum score threshold. "
            "Manage any open positions that need attention (trailing stops, breakeven, close). "
            "Provide a full summary of your reasoning and actions at the end."
        )

    def _extract_text(self, content: list) -> str:
        return " ".join(
            block.text for block in content if hasattr(block, "text")
        )

    async def _log_cycle(
        self,
        cycle_id: str,
        trigger: str,
        trades: list,
        messages: list,
    ) -> None:
        try:
            await self.db.insert("agent_cycles", {
                "cycle_id": cycle_id,
                "trigger": trigger,
                "trades_executed": len(trades),
                "trades": json.dumps(trades),
                "message_count": len(messages),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
        except Exception as exc:
            logger.warning(f"[DB] Failed to log cycle: {exc}")


# ─── News-triggered Cycle ──────────────────────────────────────────────────────

async def run_news_triggered_cycle(news_event: dict) -> dict:
    """
    Called immediately when a high-impact news event is detected.
    Passes the breaking event as additional context to Claude.
    """
    agent = VantageAgent()
    trigger = f"breaking_news:{news_event.get('headline', 'unknown')[:60]}"
    return await agent.run_cycle(trigger=trigger)


# ─── Scheduled Runner ─────────────────────────────────────────────────────────

async def main():
    """Run a single agent cycle (used by APScheduler)."""
    agent = VantageAgent()
    result = await agent.run_cycle(trigger="scheduled")
    logger.info(f"[VANTAGE] Cycle result: {result['status']} | trades={result['trades']}")
    return result


if __name__ == "__main__":
    asyncio.run(main())


# ─── Module-level helpers ──────────────────────────────────────────────────────

def _combine_positioning(cot: dict, ob: dict) -> dict:
    """
    Synthesise a unified signal from COT institutional positioning
    and OANDA retail order book data.

    Logic:
      - If hedge funds are LONG (COT) AND retail is CROWDED_SHORT → STRONG_BUY
      - If hedge funds are SHORT (COT) AND retail is CROWDED_LONG → STRONG_SELL
      - If both signals agree → CONFIRMED
      - If they disagree → MIXED (use as caution flag)
    """
    cot_signal = cot.get("positioning_signal", "NEUTRAL")
    ob_signal  = ob.get("contrarian_bias", "NEUTRAL")

    # Normalize
    cot_bullish  = cot_signal in ("BULLISH", "EXTREME_LONG")
    cot_bearish  = cot_signal in ("BEARISH", "EXTREME_SHORT", "EXTREME_LONG_UNWINDING", "EXTREME_SHORT_UNWINDING")
    ob_bullish   = ob_signal == "FADE_SHORTS"   # retail crowded short → fade = buy
    ob_bearish   = ob_signal == "FADE_LONGS"    # retail crowded long  → fade = sell

    if cot_bullish and ob_bullish:
        signal    = "STRONG_BUY"
        confidence = 0.85
    elif cot_bearish and ob_bearish:
        signal    = "STRONG_SELL"
        confidence = 0.85
    elif cot_bullish or ob_bullish:
        signal    = "MODERATE_BUY"
        confidence = 0.60
    elif cot_bearish or ob_bearish:
        signal    = "MODERATE_SELL"
        confidence = 0.60
    else:
        signal    = "NEUTRAL"
        confidence = 0.50

    return {
        "signal":          signal,
        "confidence":      confidence,
        "cot_signal":      cot_signal,
        "retail_signal":   ob_signal,
        "crowding_score":  cot.get("crowding_score", 0),
        "noncomm_net_pct": cot.get("noncomm_net_pct_oi", 0),
        "retail_long_pct": ob.get("retail_long_pct", 50),
        "note": (
            f"Hedge funds: {cot_signal} ({cot.get('noncomm_net_pct_oi', 0):+.1f}% OI) | "
            f"Retail: {ob_signal} ({ob.get('retail_long_pct', 50):.0f}% long)"
        ),
    }
