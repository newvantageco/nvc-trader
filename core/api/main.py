"""
NVC Core Engine — FastAPI server.
Exposes REST + WebSocket endpoints for the dashboard and external triggers.
"""

import asyncio
import json
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from pydantic import BaseModel

from core.ai.claude_agent import VantageAgent
from core.api.ws_manager import WSManager
from core.db.supabase_client import SupabaseClient

ws_manager = WSManager()
scheduler = AsyncIOScheduler()
db = SupabaseClient()
agent = VantageAgent()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("[API] NVC Core Engine starting...")
    scheduler.add_job(run_scheduled_cycle, "cron", minute="*/15")   # Every 15 min
    scheduler.add_job(run_news_scan, "cron", minute="*/2")           # News scan every 2 min
    scheduler.start()
    logger.info("[API] Scheduler started — agent runs every 15 minutes")
    yield
    # Shutdown
    scheduler.shutdown()
    logger.info("[API] Shutdown complete")


app = FastAPI(
    title="NVC Vantage Core Engine",
    version="1.0.0",
    description="New Vantage Co — Autonomous Trading Intelligence",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Scheduled Jobs ────────────────────────────────────────────────────────────

async def run_scheduled_cycle():
    logger.info("[SCHEDULER] Triggering agent cycle")
    result = await agent.run_cycle(trigger="scheduled_15min")
    await ws_manager.broadcast({"type": "cycle_complete", "data": result})


async def run_news_scan():
    """Quick news scan — trigger full cycle if breaking news detected."""
    from core.ingestion.news_fetcher import NewsFetcher
    fetcher = NewsFetcher()
    breaking = await fetcher.fetch_breaking_news(minutes=5)
    if breaking:
        high_impact = [a for a in breaking if any(
            kw in a["title"].lower() for kw in
            ["rate decision", "nfp", "cpi", "inflation", "fed", "ecb", "opec", "war", "sanctions"]
        )]
        if high_impact:
            logger.info(f"[NEWS SCAN] Breaking news detected: {high_impact[0]['title']}")
            result = await agent.run_cycle(trigger=f"breaking:{high_impact[0]['title'][:60]}")
            await ws_manager.broadcast({"type": "breaking_news_cycle", "data": result})


# ─── REST Endpoints ────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "time": datetime.now(timezone.utc).isoformat(), "version": "1.0.0"}


@app.post("/agent/run")
async def trigger_agent(trigger: str = "manual"):
    """Manually trigger an agent cycle."""
    result = await agent.run_cycle(trigger=f"manual:{trigger}")
    await ws_manager.broadcast({"type": "manual_cycle", "data": result})
    return result


@app.get("/signals")
async def get_signals(limit: int = 50):
    signals = await db.select("signals")
    return {"signals": signals[:limit]}


@app.get("/positions")
async def get_positions():
    from core.bridge.oanda_client import OandaClient
    client = OandaClient()
    positions = await client.get_positions()
    return {"positions": positions}


@app.get("/account")
async def get_account():
    from core.bridge.oanda_client import OandaClient
    client = OandaClient()
    metrics = await client.get_account_info()
    return metrics


@app.get("/cycles")
async def get_cycles(limit: int = 20):
    cycles = await db.select("agent_cycles")
    return {"cycles": cycles[:limit]}


@app.get("/calendar")
async def get_calendar(hours: float = 48.0):
    from core.ingestion.economic_calendar import EconomicCalendar
    cal = EconomicCalendar()
    events = await cal.get_events(hours_ahead=hours)
    blackouts = cal.compute_blackouts(events)
    return {"events": events, "blackouts": blackouts}


@app.get("/sentiment/{instrument}")
async def get_sentiment(instrument: str):
    from core.ingestion.news_fetcher import NewsFetcher
    from core.sentiment.finbert_pipeline import SentimentPipeline
    fetcher = NewsFetcher()
    pipeline = SentimentPipeline()
    articles = await fetcher.fetch_for_instrument(instrument, hours=4)
    scored = pipeline.score_articles(articles)
    agg = pipeline.aggregate(scored)
    return {"instrument": instrument, **agg}


# ─── Analytics ────────────────────────────────────────────────────────────────

@app.get("/analytics")
async def get_analytics():
    """Aggregated performance metrics from the trades table."""
    trades = await db.select("trades")
    closed = [t for t in trades if t.get("status") == "closed"]

    if not closed:
        return {
            "total_trades": 0, "winning_trades": 0, "losing_trades": 0,
            "win_rate": 0.0, "total_pnl": 0.0, "avg_win": 0.0,
            "avg_loss": 0.0, "profit_factor": 0.0, "sharpe_ratio": 0.0,
            "max_drawdown_pct": 0.0, "total_signals": len(await db.select("signals")),
            "by_instrument": {},
        }

    winners = [t for t in closed if (t.get("pnl") or 0) > 0]
    losers  = [t for t in closed if (t.get("pnl") or 0) <= 0]
    gross_p = sum(t.get("pnl", 0) for t in winners)
    gross_l = abs(sum(t.get("pnl", 0) for t in losers))

    by_instrument: dict = {}
    for t in closed:
        sym = t.get("instrument", "")
        if sym not in by_instrument:
            by_instrument[sym] = {"trades": 0, "pnl": 0.0, "wins": 0}
        by_instrument[sym]["trades"] += 1
        by_instrument[sym]["pnl"]    += t.get("pnl", 0)
        if (t.get("pnl") or 0) > 0:
            by_instrument[sym]["wins"] += 1

    by_instrument_out = {
        k: {"trades": v["trades"], "pnl": round(v["pnl"], 2),
            "win_rate": v["wins"] / v["trades"] if v["trades"] else 0}
        for k, v in by_instrument.items()
    }

    signals = await db.select("signals")
    return {
        "total_trades":    len(closed),
        "winning_trades":  len(winners),
        "losing_trades":   len(losers),
        "win_rate":        len(winners) / len(closed) if closed else 0,
        "total_pnl":       round(sum(t.get("pnl", 0) for t in closed), 2),
        "avg_win":         round(gross_p / len(winners), 2) if winners else 0,
        "avg_loss":        round(gross_l / len(losers), 2) if losers else 0,
        "profit_factor":   round(gross_p / gross_l, 3) if gross_l else 9.99,
        "sharpe_ratio":    0.0,
        "max_drawdown_pct": 0.0,
        "total_signals":   len(signals),
        "by_instrument":   by_instrument_out,
    }


@app.get("/portfolio")
async def get_portfolio():
    """Portfolio exposure report."""
    from core.risk.portfolio_manager import PortfolioManager
    from core.bridge.oanda_client import OandaClient
    oanda    = OandaClient()
    pm       = PortfolioManager()
    account  = await oanda.get_account_info()
    positions = await oanda.get_positions()
    report   = pm.get_exposure_report(positions, account.get("equity", 10000))
    return report


@app.get("/scan")
async def scan_markets():
    """Run a live signal scan across the full watchlist."""
    from core.signals.signal_generator import SignalGenerator
    from core.ai.claude_agent import WATCHLIST
    gen     = SignalGenerator()
    results = await gen.scan_watchlist(WATCHLIST)
    return {"signals": results, "count": len(results)}


@app.post("/settings")
async def save_settings(settings: dict):
    """Persist risk settings to DB."""
    await db.insert("settings", {"key": "risk_params", "value": settings,
                                  "updated_at": datetime.now(timezone.utc).isoformat()})
    return {"status": "saved"}


@app.get("/settings")
async def get_settings():
    rows = await db.select("settings", {"key": "risk_params"})
    if rows:
        return rows[0].get("value", {})
    return {
        "max_risk_pct": 1.0, "max_daily_dd_pct": 3.0,
        "signal_threshold": 0.60, "max_open_trades": 8,
    }


# ─── WebSocket ─────────────────────────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            if msg.get("type") == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
