"""
NVC VANTAGE — Claude Autonomous Trading Agent

The primary intelligence layer. Claude reasons about market conditions,
decides on trades, and executes them via tool calls. Runs on a schedule
and can also be triggered by high-impact news events.
"""

import json
import asyncio
from datetime import datetime, date, timezone
from decimal import Decimal
from typing import Any


class _SafeEncoder(json.JSONEncoder):
    """Handles datetime, date, Decimal and other non-serialisable types."""
    def default(self, obj: Any) -> Any:
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        if isinstance(obj, Decimal):
            return float(obj)
        try:
            return super().default(obj)
        except TypeError:
            return str(obj)

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
from core.ingestion.risk_sentiment import RiskSentimentReader
from core.signals.trader_strategies import LegendaryTraderAnalyser
from core.execution.smart_executor import SmartExecutor
from core.planning.portfolio_optimizer import PortfolioOptimizer
from core.analysis.regime_detector import RegimeDetector
from core.signals.edge_filter import EdgeFilter
from core.analysis.performance_tracker import PerformanceTracker


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
        self.risk_sentinel   = RiskSentimentReader()
        self.trader_analyser = LegendaryTraderAnalyser()
        self.smart_executor  = SmartExecutor()
        self.optimizer       = PortfolioOptimizer()
        self.regime          = RegimeDetector()
        self.edge_filter     = EdgeFilter()
        self.perf_tracker    = PerformanceTracker(self.db)
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

            response = await asyncio.to_thread(
                self.client.messages.create,
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
                    "content": json.dumps(result, cls=_SafeEncoder),
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
                case "get_risk_sentiment":
                    return await self._tool_risk_sentiment()
                case "get_trader_analysis":
                    return await self._tool_trader_analysis(**inputs)
                case "get_portfolio_analysis":
                    return await self._tool_portfolio_analysis(**inputs)
                case "get_performance_stats":
                    return await self._tool_performance_stats(**inputs)
                case "calculate_position_size":
                    return self._tool_calculate_position_size(**inputs)
                case "get_execution_quality":
                    return await self._tool_execution_quality(**inputs)
                case "get_market_regime":
                    return await self._tool_market_regime(**inputs)
                case "check_edge_filter":
                    return self._tool_edge_filter(**inputs)
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

        cb_mult = self.circuit_breaker.size_multiplier()
        if cb_mult == 0.0:
            return {"status": "REJECTED", "reason": "Circuit breaker active — daily drawdown or weekly halt. No new trades."}

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

        # Final live spread check — catches news spikes that occur between
        # edge filter evaluation and actual order submission
        spread_ok, spread_info = await self.smart_executor._check_spread(instrument, max_mult=2.5)
        if not spread_ok:
            return {
                "status": "REJECTED",
                "reason": f"Spread spike at execution time: {spread_info}. Wait for spread to normalise.",
            }

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

        # Send to OANDA — wait for full ACK before marking anything FILLED
        fill = await self.zmq.send_signal(signal)

        # P0-3: Only accept FILLED status when OANDA confirms with a real ticket.
        # dry_run has no ticket risk; any non-FILLED status means the order did NOT execute.
        ack_status = fill.get("status")
        if ack_status == "FILLED":
            is_dry_run = fill.get("mode") == "dry_run"
            ticket     = fill.get("ticket")

            if not is_dry_run and not ticket:
                # OANDA said FILLED but gave no ticket — treat as unconfirmed
                logger.error(
                    f"[TRADE ACK] OANDA returned FILLED but no ticket — rejecting to prevent double-execute. "
                    f"instrument={instrument} fill={fill}"
                )
                return {"status": "UNCONFIRMED", "reason": "OANDA FILLED but no ticket in response", "fill": fill}

            # Only persist to DB once we have confirmed ACK
            await self.db.insert("signals", {**signal, "fill": fill, "agent": "claude-vantage"})
            logger.success(
                f"[TRADE CONFIRMED] {direction} {instrument} "
                f"lot={validated_lot['lot_size']} score={score:.2f} "
                f"ticket={ticket} {'[DRY-RUN]' if is_dry_run else '[LIVE]'}"
            )
            return {"status": "FILLED", **fill, "signal": signal}

        # Order was rejected/cancelled/failed by broker — do NOT persist as FILLED
        logger.warning(
            f"[TRADE NOT FILLED] {direction} {instrument} "
            f"status={ack_status} reason={fill.get('reason', 'unknown')}"
        )
        return fill

    async def _tool_close_position(self, ticket: int, reason: str) -> dict:
        result = await self.zmq.close_position(ticket, reason)
        # Log close event into trades table as a status update
        await self.db.insert("trades", {
            "ticket": ticket, "status": "closed", "close_reason": reason,
            "close_result": json.dumps(result, cls=_SafeEncoder),
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        return result

    async def _tool_modify_position(
        self,
        ticket: int,
        reason: str,
        new_stop_loss: float | None = None,
        new_take_profit: float | None = None,
    ) -> dict:
        result = await self.zmq.modify_position(ticket, new_stop_loss, new_take_profit)
        # Log to trades table — no separate modifications table
        await self.db.insert("trades", {
            "ticket": ticket, "status": "modified",
            "stop_loss": new_stop_loss, "take_profit": new_take_profit,
            "modify_reason": reason,
            "created_at": datetime.now(timezone.utc).isoformat(),
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

    async def _tool_risk_sentiment(self) -> dict:
        """
        Fetches TSLA/SPX/JPM 5-day equity returns as a real-time risk appetite proxy.
        Also includes JP Morgan's published FX price targets for 2026.
        Use this in Step 3 (Positioning) to confirm risk-on/off environment.
        """
        appetite   = await self.risk_sentinel.get_risk_appetite()
        jpm        = await self.risk_sentinel.get_jpm_outlook()
        return {
            "risk_appetite":    appetite["risk_appetite"],
            "composite_score":  appetite["score"],
            "tsla_5d_return":   appetite["tsla_5d_return"],
            "spx_5d_return":    appetite["spx_5d_return"],
            "jpm_5d_return":    appetite["jpm_5d_return"],
            "signal_for_pairs": appetite["signal_for_pair"],
            "jpm_credit_signal": jpm["credit_signal"],
            "jpm_fx_targets":   jpm["fx_targets"],
            "note":             appetite["note"],
            "source":           appetite["source"],
        }

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

    async def _tool_market_regime(
        self, instrument: str, ohlcv: list | None = None
    ) -> dict:
        if ohlcv is None:
            try:
                # Need full OHLCV dataset (200+ candles) for ADX + autocorr.
                # _get_ohlcv is internal but returning the full DataFrame via
                # the TA engine's analyse call is the right approach.
                # We fetch H4 data — enough history, not too slow.
                import pandas as pd
                df = await self.ta_engine._get_ohlcv(instrument, "H4")
                ohlcv = df.to_dict("records") if isinstance(df, pd.DataFrame) else []
            except Exception as exc:
                logger.debug(f"[REGIME] OHLCV fetch failed for {instrument}: {exc}")
                ohlcv = []
        return await self.regime.detect(instrument, ohlcv)

    def _tool_edge_filter(
        self,
        instrument:  str,
        direction:   str,
        ta_score:    float,
        sentiment:   dict,
        order_flow:  dict,
        macro:       dict,
        regime:      dict,
        spread_pips: float | None = None,
        news_event_minutes_ago: int | None = None,
    ) -> dict:
        # Use circuit_breaker's DB-computed daily DD — OANDA always returns 0.0
        cb_dd = self.circuit_breaker.status()["daily_drawdown_pct"]

        # Pull cached H4 + D1 candles from TA engine (best-effort, no extra I/O)
        candles_h4: list[dict] | None = None
        candles_d1: list[dict] | None = None
        try:
            import pandas as pd
            cached_h4 = getattr(self.ta_engine, "_last_ohlcv_cache", {}).get(f"{instrument}_H4")
            if cached_h4 is not None and isinstance(cached_h4, pd.DataFrame):
                candles_h4 = cached_h4[["open", "high", "low", "close"]].to_dict("records")
            cached_d1 = getattr(self.ta_engine, "_last_ohlcv_cache", {}).get(f"{instrument}_D1")
            if cached_d1 is not None and isinstance(cached_d1, pd.DataFrame):
                candles_d1 = cached_d1[["open", "high", "low", "close"]].to_dict("records")
        except Exception:
            pass

        result = self.edge_filter.evaluate(
            instrument=instrument,
            direction=direction,
            ta_score=ta_score,
            sentiment=sentiment,
            order_flow=order_flow,
            macro=macro,
            regime=regime,
            account={
                "daily_drawdown_pct": cb_dd,
                "open_positions":     len(self._open_positions),
            },
            spread_pips=spread_pips,
            news_event_minutes_ago=news_event_minutes_ago,
            candles_h4=candles_h4,
            candles_d1=candles_d1,
        )
        return {
            "passes":            result.passes,
            "grade":             result.grade,
            "score":             result.score,
            "conditions":        result.conditions,
            "recommended_size":  result.recommended_size,
            "recommended_rr":    result.recommended_rr,
            "special_setup":     result.special_setup,
            "trader_signals":    result.trader_signals,
            "notes":             result.notes,
            "verdict": (
                f"{'✅ TRADE APPROVED' if result.passes else '❌ TRADE BLOCKED'} — "
                f"Grade {result.grade} ({result.score}/8 conditions). "
                + (f"Special: {result.special_setup}. " if result.special_setup else "")
                + (f"Size: {result.recommended_size:.0%}, RR: {result.recommended_rr}:1" if result.passes else "")
            ),
        }

    async def _tool_trader_analysis(
        self,
        instrument:       str,
        direction:        str,
        entry:            float,
        stop_loss:        float,
        take_profit:      float,
        atr:              float,
        edge_score:       int,
        macro_score:      float = 0.5,
        active_patterns:  list[str] | None = None,
    ) -> dict:
        """
        Runs all 7 legendary trader strategies against a live trade setup.
        Fetches H4 + D1 candles automatically for Livermore, Seykota, and Turtle checks.
        Returns verdict, green_lights/7, final_multiplier (for position sizing), and per-strategy detail.
        """
        # Fetch candle data for technical strategy checks
        candles_h4: list[dict] = []
        candles_d1: list[dict] = []
        try:
            import pandas as pd
            df_h4 = await self.ta_engine._get_ohlcv(instrument, "H4")
            if isinstance(df_h4, pd.DataFrame) and not df_h4.empty:
                candles_h4 = df_h4[["open", "high", "low", "close"]].to_dict("records")
        except Exception as exc:
            logger.debug(f"[TraderAnalysis] H4 fetch failed for {instrument}: {exc}")

        try:
            import pandas as pd
            df_d1 = await self.ta_engine._get_ohlcv(instrument, "D1")
            if isinstance(df_d1, pd.DataFrame) and not df_d1.empty:
                candles_d1 = df_d1[["open", "high", "low", "close"]].to_dict("records")
        except Exception as exc:
            logger.debug(f"[TraderAnalysis] D1 fetch failed for {instrument}: {exc}")

        macro_data = {}
        try:
            macro_data = await self.fred.get_macro_environment([instrument])
        except Exception as exc:
            logger.debug(f"[TraderAnalysis] Macro fetch failed: {exc}")

        result = self.trader_analyser.analyse(
            instrument=instrument,
            direction=direction,
            entry=entry,
            stop_loss=stop_loss,
            take_profit=take_profit,
            atr=atr,
            candles_h4=candles_h4,
            candles_d1=candles_d1,
            edge_score=edge_score,
            macro_score=macro_score,
            macro_data=macro_data,
            active_patterns=active_patterns,
        )

        logger.info(
            f"[TraderAnalysis] {instrument} {direction}: {result['verdict']} "
            f"| {result['green_lights']} | multiplier={result['final_multiplier']}"
        )
        return result

    async def _tool_performance_stats(self, lookback_days: int = 30) -> dict:
        return await self.perf_tracker.get_stats(lookback_days=lookback_days)

    def _tool_calculate_position_size(
        self,
        instrument:               str,
        entry_price:              float,
        stop_loss:                float,
        account_equity:           float,
        regime:                   str = "RANGING",
        factors_aligned:          int = 3,
        druckenmiller_multiplier: float | None = None,
    ) -> dict:
        # Always apply circuit breaker multiplier — agent cannot override this
        circuit_mult = self.circuit_breaker.size_multiplier()

        if circuit_mult == 0.0:
            return {
                "lot_size": 0.0,
                "risk_usd": 0.0,
                "risk_pct": 0.0,
                "circuit_mult": 0.0,
                "instruction": "BLOCKED by circuit breaker — daily or weekly drawdown limit hit. No new trades.",
            }

        result = self.position_sizer.calculate_lot(
            instrument=instrument,
            entry_price=entry_price,
            stop_loss=stop_loss,
            account_equity=account_equity,
            regime=regime,
            factors_aligned=factors_aligned,
            circuit_mult=circuit_mult,
            druckenmiller_multiplier=druckenmiller_multiplier,
        )

        cb_note = " [WEEKLY LIMIT: sizes halved]" if circuit_mult < 1.0 else ""
        druck_note = f" [Druckenmiller {druckenmiller_multiplier}× applied]" if druckenmiller_multiplier else ""
        result["instruction"] = (
            f"Use lot_size={result['lot_size']} in execute_trade.{cb_note}{druck_note} "
            f"Risk: ${result['risk_usd']:.2f} ({result['risk_pct']:.2f}% of equity). "
            f"Regime={result['regime_mult']}× | Conviction={result['conviction_mult']}× | Circuit={circuit_mult}×"
        )
        return result

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
        self._open_positions  = await self.zmq.get_positions()
        self.circuit_breaker.update(self._account_metrics)
        # Load real drawdown from DB snapshots — OANDA's reported value is always 0
        await self.circuit_breaker.load_drawdown_from_db(self.db)
        # Write a snapshot every cycle (15 min) so circuit breaker has fine-grained
        # equity history. Without this, intra-hour drops up to 2% go undetected.
        await self._write_cycle_snapshot()

    async def _write_cycle_snapshot(self) -> None:
        """
        Write a lightweight equity snapshot every agent cycle (every 15 min).
        The hourly cron in main.py writes full snapshots; this fills the gaps so
        circuit_breaker.load_drawdown_from_db() has ≤15 min granularity.
        """
        try:
            equity = self._account_metrics.get("equity", 0)
            if equity <= 0:
                return
            await self.db.insert("account_snapshots", {
                "timestamp":     datetime.now(timezone.utc).isoformat(),
                "balance":       self._account_metrics.get("balance", 0),
                "equity":        equity,
                "margin_used":   self._account_metrics.get("margin", 0),
                "free_margin":   self._account_metrics.get("free_margin", 0),
                "unrealised_pl": self._account_metrics.get("unrealised_pl", 0),
                "system_status": self._account_metrics.get("system_status", "agent_cycle"),
            })
        except Exception as exc:
            logger.debug(f"[SNAPSHOT] Cycle snapshot failed (non-critical): {exc}")

    def _build_context_message(self, trigger: str) -> str:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        open_count = len(self._open_positions)
        equity = self._account_metrics.get("equity", 0)
        balance = self._account_metrics.get("balance", 0)
        daily_dd = self._account_metrics.get("daily_drawdown_pct", 0.0)
        weekly_dd = self._account_metrics.get("weekly_drawdown_pct", 0.0)
        system_status = self._account_metrics.get("system_status", "OK")
        cb_status = self.circuit_breaker.status()

        # Pre-flight risk gate — encode hard stops directly in the context
        risk_warnings = []
        if daily_dd >= 2.0:
            risk_warnings.append("⛔ DAILY DRAWDOWN ≥ 2% — RULE R1: Close all positions, flat for rest of day. NO NEW ENTRIES.")
        elif daily_dd >= 1.5:
            risk_warnings.append("⚠️  Daily drawdown ≥ 1.5% — RULE R2: Reduce all new position sizes by 50%.")
        if weekly_dd >= 5.0:
            risk_warnings.append("⚠️  Weekly drawdown ≥ 5% — RULE R5: Halve all position sizes this week.")

        risk_block = "\n".join(risk_warnings) if risk_warnings else "✅ Risk limits clear"

        # Format open positions compactly
        pos_lines = []
        for p in self._open_positions:
            pos_lines.append(
                f"  • {p.get('instrument','?')} {p.get('direction','?')} "
                f"lot={p.get('lot_size','?')} pnl={p.get('unrealised_pnl',0):+.2f} "
                f"ticket={p.get('ticket','?')}"
            )
        pos_block = "\n".join(pos_lines) if pos_lines else "  (none)"

        return (
            f"═══════════════════════════════════════════\n"
            f"  VANTAGE CYCLE — {now}\n"
            f"  Trigger: {trigger}\n"
            f"═══════════════════════════════════════════\n\n"
            f"ACCOUNT STATUS\n"
            f"  Balance:        ${balance:,.2f}\n"
            f"  Equity:         ${equity:,.2f}\n"
            f"  Daily DD:       {daily_dd:.2f}%\n"
            f"  Weekly DD:      {weekly_dd:.2f}%\n"
            f"  Open positions: {open_count}/8\n"
            f"  System:         {system_status}\n\n"
            f"RISK STATUS\n"
            f"  {risk_block}\n\n"
            f"OPEN POSITIONS\n"
            f"{pos_block}\n\n"
            f"WATCHLIST\n"
            f"  {', '.join(WATCHLIST)}\n\n"
            f"INSTRUCTIONS\n"
            f"  Follow the 6-step framework in your system prompt exactly:\n"
            f"  1. Identify regime (get_market_regime)\n"
            f"  2. Macro analysis (get_macro_environment + get_institutional_research)\n"
            f"  3. Positioning (get_order_flow for candidates)\n"
            f"  4. Technical confirmation (get_technical_analysis)\n"
            f"  5. News filter (get_news_sentiment + get_economic_calendar)\n"
            f"  6. Trade/No-trade decision (≥3 factors aligned required)\n\n"
            f"  Priority: Manage open positions first. Then scan watchlist.\n"
            f"  End with the structured cycle summary as specified.\n"
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
            # Count tool calls per tool from the message history
            tool_calls: dict[str, int] = {}
            for msg in messages:
                content = msg.get("content", [])
                if isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "tool_use":
                            name = block.get("name", "unknown")
                            tool_calls[name] = tool_calls.get(name, 0) + 1
                        elif hasattr(block, "type") and block.type == "tool_use":
                            name = getattr(block, "name", "unknown")
                            tool_calls[name] = tool_calls.get(name, 0) + 1

            # Extract final reasoning text (last assistant message)
            summary = ""
            for msg in reversed(messages):
                if msg.get("role") == "assistant":
                    content = msg.get("content", [])
                    if isinstance(content, list):
                        texts = [b.text for b in content if hasattr(b, "text") and b.text]
                        if texts:
                            summary = " ".join(texts)[:1000]
                            break

            await self.db.insert("agent_cycles", {
                "cycle_id":        cycle_id,
                "trigger":         trigger,
                "trades_executed": len(trades),
                "trades":          json.dumps(trades,                    cls=_SafeEncoder),
                "message_count":   len(messages),
                "tool_calls":      json.dumps(tool_calls,                cls=_SafeEncoder),
                "summary":         summary,
                "circuit_breaker": json.dumps(self.circuit_breaker.status(), cls=_SafeEncoder),
                "timestamp":       datetime.now(timezone.utc).isoformat(),
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
