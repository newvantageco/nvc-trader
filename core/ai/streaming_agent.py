"""
Streaming version of the Claude agent.
Yields SSE-compatible event dicts as Claude reasons and acts,
so the Brain dashboard can display the thinking in real-time.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import AsyncGenerator, Any

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

WATCHLIST = [
    "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD",
    "NZDUSD", "USDCHF", "EURJPY", "GBPJPY",
    "XAUUSD", "XAGUSD", "USOIL", "UKOIL", "NATGAS",
]

# Event types streamed to the Brain dashboard
# thinking   — Claude's text reasoning
# tool_call  — Claude is calling a tool
# tool_result— Tool returned a result
# trade      — A trade was executed
# score      — A confluence score was computed
# status     — System status update
# error      — Something went wrong
# done       — Cycle complete


class VantageStreamingAgent:
    """Runs an agent cycle and streams every step as SSE events."""

    def __init__(self) -> None:
        self.client          = anthropic.Anthropic()
        self.oanda           = OandaClient()
        self.circuit_breaker = CircuitBreaker()
        self.position_sizer  = PositionSizer()
        self.news_fetcher    = NewsFetcher()
        self.sentiment       = SentimentPipeline()
        self.ta_engine       = IndicatorEngine()
        self.calendar        = EconomicCalendar()
        self.db              = SupabaseClient()

    async def run_streaming(self, trigger: str = "stream") -> AsyncGenerator[dict, None]:
        yield _evt("status", {"message": f"Agent cycle started — trigger: {trigger}", "phase": "init"})

        # Refresh state
        account   = await self.oanda.get_account_info()
        positions = await self.oanda.get_positions()
        self.circuit_breaker.update(account)

        # Pre-load shared agent with current state so tools use live data
        from core.ai.claude_agent import VantageAgent
        self._agent = VantageAgent()
        self._agent._open_positions  = positions
        self._agent._account_metrics = account
        # Load real drawdown from DB — circuit breaker relies on this
        await self._agent.circuit_breaker.load_drawdown_from_db(self._agent.db)

        yield _evt("status", {
            "message": f"Account loaded — equity ${account.get('equity', 0):,.2f} | {len(positions)} open positions",
            "phase": "state_loaded",
            "account": account,
        })

        if self.circuit_breaker.is_hard_stopped():
            yield _evt("error", {"message": "HARD STOP — monthly drawdown limit hit. No trading."})
            return

        # Build context
        context = self._build_context(trigger, account, positions)
        messages: list[dict] = [{"role": "user", "content": context}]
        trades_executed: list[dict] = []
        iterations = 0

        yield _evt("status", {
            "message": "Claude beginning market analysis...",
            "phase":   "analysis_start",
            "watchlist": WATCHLIST,
        })

        # ── Agentic loop ──────────────────────────────────────────────────────
        while iterations < 25:
            iterations += 1
            yield _evt("status", {"message": f"Thinking... (step {iterations})", "phase": "thinking"})

            # P0-4: Wrap Claude API call — a network or auth failure must yield an error
            # event and halt gracefully, not crash the SSE generator silently.
            try:
                response = self.client.messages.create(
                    model="claude-opus-4-6",
                    max_tokens=8096,
                    system=TRADING_AGENT_SYSTEM_PROMPT,
                    tools=TRADING_TOOLS,
                    messages=messages,
                )
            except Exception as api_exc:
                yield _evt("error", {
                    "message": f"Claude API call failed at step {iterations}: {api_exc}",
                    "phase":   "api_error",
                    "fatal":   True,
                })
                logger.error(f"[STREAMING] Claude API error at step {iterations}: {api_exc}")
                return

            messages.append({"role": "assistant", "content": response.content})

            # Stream any text reasoning blocks
            for block in response.content:
                if hasattr(block, "text") and block.text:
                    # Stream text in chunks for real-time effect
                    yield _evt("thinking", {
                        "text": block.text,
                        "step": iterations,
                    })

            if response.stop_reason == "end_turn":
                final = " ".join(
                    b.text for b in response.content if hasattr(b, "text")
                )
                yield _evt("status", {
                    "message": "Analysis complete.",
                    "phase":   "complete",
                    "summary": final[:500],
                })
                break

            if response.stop_reason != "tool_use":
                break

            # Process tool calls
            tool_results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue

                yield _evt("tool_call", {
                    "tool":   block.name,
                    "inputs": _safe_inputs(block.input),
                    "step":   iterations,
                })

                # P0-4: Tool errors must surface as error events, not crash the generator.
                # Return an error dict so Claude sees "this tool failed" and can decide
                # what to do — rather than receiving stale/empty data silently.
                try:
                    result = await self._dispatch_tool(block.name, block.input)
                except Exception as tool_exc:
                    result = {"error": str(tool_exc), "tool": block.name}
                    yield _evt("error", {
                        "message": f"Tool {block.name} raised exception: {tool_exc}",
                        "tool":    block.name,
                        "step":    iterations,
                        "fatal":   False,
                    })
                    logger.error(f"[STREAMING] Tool {block.name} exception: {tool_exc}")

                if "error" in result:
                    yield _evt("error", {
                        "message": f"Tool {block.name} returned error: {result['error']}",
                        "tool":    block.name,
                        "step":    iterations,
                        "fatal":   False,
                    })

                # Enrich stream for key tools
                if block.name == "get_news_sentiment":
                    yield _evt("score", {
                        "type":       "sentiment",
                        "instrument": block.input.get("instrument"),
                        "score":      result.get("sentiment_score"),
                        "bias":       result.get("dominant_bias"),
                        "articles":   result.get("article_count"),
                    })

                if block.name == "get_technical_analysis":
                    yield _evt("score", {
                        "type":       "technical",
                        "instrument": block.input.get("instrument"),
                        "bias":       result.get("overall_bias"),
                        "ta_score":   result.get("ta_score"),
                    })

                if block.name == "execute_trade":
                    status = result.get("status")
                    if status == "FILLED":
                        trades_executed.append(result)
                        yield _evt("trade", {
                            "status":     "FILLED",
                            "instrument": block.input.get("instrument"),
                            "direction":  block.input.get("direction"),
                            "lot_size":   result.get("units"),
                            "fill_price": result.get("fill_price"),
                            "score":      block.input.get("score"),
                            "reason":     block.input.get("reason"),
                        })
                    else:
                        yield _evt("trade", {
                            "status":     status,
                            "instrument": block.input.get("instrument"),
                            "reason":     result.get("reason", "rejected"),
                        })

                yield _evt("tool_result", {
                    "tool":   block.name,
                    "status": "ok",
                    "preview": _preview(result),
                    "step":   iterations,
                })

                tool_results.append({
                    "type":        "tool_result",
                    "tool_use_id": block.id,
                    "content":     json.dumps(result, default=str),
                })

            messages.append({"role": "user", "content": tool_results})

        yield _evt("done", {
            "trades_executed": len(trades_executed),
            "trades":          trades_executed,
            "iterations":      iterations,
            "timestamp":       datetime.now(timezone.utc).isoformat(),
        })

    async def _dispatch_tool(self, name: str, inputs: dict) -> dict:
        """Route tool calls via VantageAgent (shared instance — reuse cached state)."""
        if not hasattr(self, "_agent"):
            from core.ai.claude_agent import VantageAgent
            self._agent = VantageAgent()
        # Refresh positions + metrics once per iteration (not per tool call)
        # They're already fetched at cycle start; individual calls use the cache.
        return await self._agent._dispatch_tool(name, inputs)

    def _build_context(self, trigger: str, account: dict, positions: list) -> str:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        return (
            f"VANTAGE STREAMING CYCLE — {now}\n"
            f"Trigger: {trigger}\n"
            f"Equity: ${account.get('equity', 0):,.2f}\n"
            f"Open positions: {len(positions)}/8\n\n"
            f"Watchlist: {', '.join(WATCHLIST)}\n\n"
            "Begin your analysis cycle. Analyse each instrument systematically. "
            "Show your full reasoning at each step. Execute any qualifying signals."
        )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _evt(type_: str, data: dict) -> dict:
    return {
        "type":      type_,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **data,
    }


def _safe_inputs(inputs: dict) -> dict:
    """Remove large fields from tool inputs for streaming."""
    skip = {"description", "body", "content"}
    return {k: v for k, v in inputs.items() if k not in skip}


def _preview(result: dict) -> str:
    """One-line preview of a tool result."""
    if "error" in result:
        return f"ERROR: {result['error']}"
    if "status" in result:
        return f"status={result['status']}"
    keys = list(result.keys())[:3]
    return ", ".join(f"{k}={str(result[k])[:20]}" for k in keys)
