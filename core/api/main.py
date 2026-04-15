"""
NVC Core Engine — FastAPI server.
Exposes REST + WebSocket endpoints for the dashboard and external triggers.
"""

import asyncio
import json
import os
import queue
import threading
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncGenerator

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from loguru import logger
from pydantic import BaseModel

from core.ai.claude_agent import VantageAgent
from core.api.ws_manager import WSManager
from core.db.supabase_client import SupabaseClient

ws_manager = WSManager()
scheduler = AsyncIOScheduler()
db = SupabaseClient()
agent = VantageAgent()


def _validate_env() -> None:
    """
    P0: Crash hard at startup if critical env vars are missing.
    Silent mock fallback in production would execute trades against fake data.
    """
    missing: list[str] = []

    if not os.environ.get("ANTHROPIC_API_KEY"):
        missing.append("ANTHROPIC_API_KEY")

    is_live = os.environ.get("OANDA_LIVE", "false").lower() == "true"
    if is_live:
        if not os.environ.get("OANDA_API_KEY"):
            missing.append("OANDA_API_KEY")
        if not os.environ.get("OANDA_ACCOUNT_ID"):
            missing.append("OANDA_ACCOUNT_ID")

    if missing:
        msg = (
            f"[STARTUP] FATAL — missing required env vars: {', '.join(missing)}\n"
            f"  OANDA_LIVE={'true' if is_live else 'false'}\n"
            f"  Set these vars and restart. Refusing to start with missing credentials."
        )
        logger.critical(msg)
        raise RuntimeError(msg)

    logger.info(
        f"[STARTUP] Env validation passed — "
        f"OANDA mode={'LIVE' if is_live else 'demo/practice'}"
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup — validate env before anything else
    _validate_env()
    logger.info("[API] NVC Core Engine starting...")

    # Restore trading mode from DB (survives restarts)
    try:
        mode_rows = await db.select("settings", {"key": "trading_mode"})
        if mode_rows:
            saved_mode = mode_rows[0].get("value", {}).get("mode", "demo")
            if saved_mode == "live":
                agent.zmq.switch_mode(True)
                logger.info("[STARTUP] Restored trading mode: LIVE")
            else:
                logger.info("[STARTUP] Trading mode: DEMO (default)")
    except Exception as _e:
        logger.warning(f"[STARTUP] Could not restore trading mode: {_e}")

    scheduler.add_job(run_scheduled_cycle,  "cron", minute="*/15")  # Every 15 min
    scheduler.add_job(run_news_scan,         "cron", minute="*/2")   # News scan every 2 min
    scheduler.add_job(run_account_snapshot,  "cron", minute=0)       # Hourly snapshots
    scheduler.add_job(run_live_push,         "interval", seconds=30) # Live account/positions push
    scheduler.start()
    logger.info("[API] Scheduler started — agent 15min | news 2min | snapshots hourly | live push 30s")
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

_ALLOWED_ORIGINS = [
    # Vercel production + preview deployments
    "https://dashboard-nvc-labs.vercel.app",
    "https://nvc-labs.vercel.app",
    # Vercel preview pattern — allow all *.vercel.app subdomains for the project
    # (Next.js deploy previews get unique subdomains like dashboard-abc123-nvc-labs.vercel.app)
]

# Also allow all *.vercel.app previews and localhost in dev
_ORIGIN_REGEX = r"https://dashboard.*\.vercel\.app|http://localhost(:\d+)?"

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_origin_regex=_ORIGIN_REGEX,
    allow_credentials=False,   # dashboard uses NextAuth server-side; no cookies sent to engine
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)


# ─── Scheduled Jobs ────────────────────────────────────────────────────────────

async def run_scheduled_cycle():
    logger.info("[SCHEDULER] Triggering agent cycle")
    result = await agent.run_cycle(trigger="scheduled_15min")
    await ws_manager.broadcast({"type": "cycle_complete", "data": result})


HIGH_IMPACT_KEYWORDS = [
    "rate decision", "nfp", "cpi", "inflation", "fed", "ecb", "opec",
    "war", "sanctions", "recession", "rate hike", "rate cut", "gdp",
    "unemployment", "boe", "bank of japan", "boj", "rba", "fomc",
]


async def run_news_scan():
    """
    Quick news scan every 2 minutes.
    Writes all new articles to news_events table (the table exists but was never populated).
    Triggers a full agent cycle if a high-impact event is detected.
    """
    from core.ingestion.news_fetcher import NewsFetcher
    fetcher  = NewsFetcher()
    breaking = await fetcher.fetch_breaking_news(minutes=5)

    # Upsert articles — news scan runs every 2 min with a 5-min lookback window,
    # so the same article appears in 2-3 consecutive scans. Use upsert on url
    # to avoid the 23505 duplicate key violations that were flooding the logs.
    for article in breaking[:20]:  # cap at 20 to avoid DB spam
        url = article.get("url", "")[:1000]
        if not url:
            continue
        await db.upsert("news_events", {
            "title":        article.get("title", "")[:500],
            "source":       article.get("source", ""),
            "url":          url,
            "published_at": article["published_at"].isoformat()
                            if hasattr(article.get("published_at"), "isoformat")
                            else str(article.get("published_at", "")),
            "weight":       article.get("weight", 0.7),
            "fetched_at":   datetime.now(timezone.utc).isoformat(),
        }, on_conflict="url")

    if breaking:
        high_impact = [a for a in breaking if any(
            kw in a["title"].lower() for kw in HIGH_IMPACT_KEYWORDS
        )]
        if high_impact:
            logger.info(f"[NEWS SCAN] Breaking news detected: {high_impact[0]['title']}")
            result = await agent.run_cycle(trigger=f"breaking:{high_impact[0]['title'][:60]}")
            await ws_manager.broadcast({"type": "breaking_news_cycle", "data": result})


async def run_account_snapshot():
    """
    P0-2: Write hourly account snapshot to Supabase.
    Required for accurate drawdown tracking — without this, restarts lose all history.
    """
    try:
        from core.bridge.oanda_client import OandaClient
        oanda   = OandaClient()
        account = await oanda.get_account_info()
        snapshot = {
            "timestamp":        datetime.now(timezone.utc).isoformat(),
            "balance":          account.get("balance", 0),
            "equity":           account.get("equity", 0),
            "margin_used":      account.get("margin", 0),
            "free_margin":      account.get("free_margin", 0),
            "unrealised_pl":    account.get("unrealised_pl", 0),
            "daily_drawdown":   account.get("daily_drawdown_pct", 0),
            "weekly_drawdown":  account.get("weekly_drawdown_pct", 0),
            "monthly_drawdown": account.get("monthly_drawdown_pct", 0),
            "system_status":    account.get("system_status", "unknown"),
        }
        await db.insert("account_snapshots", snapshot)
        logger.info(
            f"[SNAPSHOT] Hourly snapshot written — "
            f"equity=${snapshot['equity']:,.2f} | margin={snapshot['margin_used']:,.2f}"
        )
        await ws_manager.broadcast({"type": "account_snapshot", "data": snapshot})
    except Exception as exc:
        logger.error(f"[SNAPSHOT] Failed to write account snapshot: {exc}")


async def run_live_push():
    """
    Broadcast fresh account + positions to all WebSocket clients every 30 seconds.
    Keeps the dashboard live between agent cycles without waiting 15 min.
    """
    if not ws_manager.has_connections():
        return  # nobody watching — skip the OANDA call
    try:
        from core.bridge.oanda_client import OandaClient
        oanda = OandaClient()
        account, positions = await asyncio.gather(
            oanda.get_account_info(),
            oanda.get_positions(),
            return_exceptions=True,
        )
        if not isinstance(account, Exception):
            # Merge circuit-breaker computed drawdowns into the account snapshot.
            # OANDA always returns weekly/monthly drawdown as 0.0 — we derive the
            # real values from equity history via circuit_breaker.load_drawdown_from_db().
            cb = agent.circuit_breaker.status()
            account["daily_drawdown_pct"]   = cb["daily_drawdown_pct"]
            account["weekly_drawdown_pct"]  = cb["weekly_drawdown_pct"]
            account["monthly_drawdown_pct"] = cb.get("monthly_drawdown_pct", 0.0)
            account["circuit_breaker"]      = {
                "size_multiplier":  cb["size_multiplier"],
                "trading_allowed":  cb["trading_allowed"],
                "weekly_limit_hit": cb["weekly_limit_hit"],
                "hard_stop":        cb["hard_stop"],
            }
            await ws_manager.broadcast({"type": "account_update",   "data": account})
        if not isinstance(positions, Exception):
            await ws_manager.broadcast({"type": "positions_update", "data": {"positions": positions}})
    except Exception as exc:
        logger.debug(f"[LIVE PUSH] Failed: {exc}")


# ─── REST Endpoints ────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "time": datetime.now(timezone.utc).isoformat(), "version": "1.0.0"}


@app.post("/agent/run")
async def trigger_agent(trigger: str = "manual"):
    """
    Trigger an agent cycle.
    Returns 202 immediately — result is broadcast via WebSocket when done.
    Claude Opus can take 30-90s; keeping the HTTP request open causes Fly proxy 503s.
    """
    async def _run():
        try:
            result = await agent.run_cycle(trigger=f"manual:{trigger}")
            await ws_manager.broadcast({"type": "manual_cycle", "data": result})
        except Exception as exc:
            logger.exception(f"[AGENT] Background cycle failed: {exc}")
            await ws_manager.broadcast({"type": "agent_error", "data": {"error": str(exc)}})

    asyncio.create_task(_run())
    return {"status": "accepted", "message": "Cycle started — result will arrive via WebSocket"}


@app.get("/agent/stream")
async def stream_agent(trigger: str = "manual-stream"):
    """
    Server-Sent Events stream of a live Claude agent cycle.
    The dashboard Brain page connects here to watch Claude think in real-time.
    """
    async def event_generator() -> AsyncGenerator[str, None]:
        from core.ai.streaming_agent import VantageStreamingAgent
        streaming = VantageStreamingAgent()
        async for event in streaming.run_streaming(trigger=trigger):
            data = json.dumps(event, default=str)
            yield f"data: {data}\n\n"
        yield "data: {\"type\": \"done\"}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control":               "no-cache",
            "X-Accel-Buffering":           "no",
            "Access-Control-Allow-Origin": "*",
        },
    )


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


@app.get("/trades")
async def get_trades(limit: int = 500):
    trades = await db.select("trades", order_by="-created_at", limit=limit)
    return {"trades": trades}


@app.delete("/positions/{ticket}/close")
async def close_position(ticket: str):
    from core.bridge.oanda_client import OandaClient
    client = OandaClient()
    result = await client.close_position(int(ticket), reason="manual_close")
    return result


@app.get("/account")
async def get_account():
    from core.bridge.oanda_client import OandaClient
    client = OandaClient()
    metrics = await client.get_account_info()
    return metrics


@app.get("/prices")
async def get_prices(symbols: str = "GBPUSD,EURUSD,XAUUSD,USDJPY,USOIL"):
    """Live bid/ask for a comma-separated list of instruments."""
    from core.bridge.oanda_client import OandaClient
    client = OandaClient()
    instruments = [s.strip() for s in symbols.split(",") if s.strip()]
    import asyncio
    prices = await asyncio.gather(
        *[client.get_price(sym) for sym in instruments],
        return_exceptions=True,
    )
    result = {}
    for sym, p in zip(instruments, prices):
        if isinstance(p, Exception):
            result[sym] = {"bid": 0.0, "ask": 0.0, "spread": 0.0}
        else:
            result[sym] = p
    return result


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
async def get_analytics(days: int = 30):
    """Full performance analytics from PerformanceTracker (real P&L, Kelly, Sharpe)."""
    from core.analysis.performance_tracker import PerformanceTracker
    tracker = PerformanceTracker(db)
    stats   = await tracker.get_stats(lookback_days=days)
    # Also include total signal count for dashboard
    signals = await db.select("signals", limit=1000)
    stats["total_signals"] = len(signals)
    return stats


@app.get("/performance")
async def get_performance(days: int = 30):
    """Alias for /analytics — returns trade performance stats."""
    return await get_analytics(days=days)


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


@app.get("/admin/overview")
async def admin_overview():
    """
    Admin dashboard: APY, true platform cost breakdown, profit margin,
    growth stage, and operational health.
    """
    from core.risk.growth_plan import GrowthPlan, STAGES

    # ── P&L history ──────────────────────────────────────────────────────────
    trades    = await db.select("trades")
    closed    = [t for t in trades if t.get("status") == "closed"]
    cycles    = await db.select("agent_cycles")

    # Build daily P&L from closed trades
    daily_pnl: dict[str, float] = {}
    for t in closed:
        day = (t.get("closed_at") or t.get("created_at") or "")[:10]
        if day:
            daily_pnl[day] = daily_pnl.get(day, 0) + float(t.get("pnl") or 0)

    history = [
        {"date": d, "pnl": round(p, 2), "account_equity": 100.0}
        for d, p in sorted(daily_pnl.items())
    ]

    # ── Account balance ───────────────────────────────────────────────────────
    from core.bridge.oanda_client import OandaClient
    oanda   = OandaClient()
    account = await oanda.get_account_info()
    balance = account.get("equity", 100.0)

    # ── Growth plan ───────────────────────────────────────────────────────────
    gp      = GrowthPlan()
    stage   = gp.get_current_stage(history)
    params  = gp.get_trading_params(stage, balance)
    apy     = gp.compute_apy(history, balance)
    advance = gp.check_stage_advancement(history)

    # ── True cost model (monthly) ─────────────────────────────────────────────
    # Cycle frequency: 56 cycles/day during trading hours × 30 days
    cycles_per_month  = 1680
    # Anthropic Claude Sonnet 4.6 pricing: $3/M input, $15/M output
    input_tokens_m    = cycles_per_month * 6000 / 1_000_000   # 6k avg input
    output_tokens_m   = cycles_per_month * 1500 / 1_000_000   # 1.5k avg output
    anthropic_cost    = round(input_tokens_m * 3 + output_tokens_m * 15, 2)
    fly_cost          = 61.00    # performance-2x machine
    vercel_cost       = 0.00     # free tier
    supabase_cost     = 0.00     # free tier
    newsapi_cost      = 0.00     # free tier
    fred_cost         = 0.00     # free
    domain_cost       = 1.00     # ~$12/year

    total_monthly_cost = round(anthropic_cost + fly_cost + vercel_cost +
                               supabase_cost + newsapi_cost + fred_cost + domain_cost, 2)
    daily_cost         = round(total_monthly_cost / 30, 2)

    # ── Profit margin ─────────────────────────────────────────────────────────
    avg_daily_gross = apy.get("avg_daily_usd", 0)
    margin_pct      = 0.0
    if avg_daily_gross > daily_cost:
        margin_pct = round((avg_daily_gross - daily_cost) / avg_daily_gross * 100, 1)

    # Monthly projection
    monthly_gross = avg_daily_gross * 30
    monthly_net   = round(monthly_gross - total_monthly_cost, 2)

    # Break-even point
    breakeven_daily = daily_cost
    breakeven_monthly = total_monthly_cost

    # Stage targets vs costs
    stage_targets = []
    for s in STAGES:
        s_monthly_gross_min = s.daily_min * 30
        s_monthly_gross_max = s.daily_max * 30
        s_net_min           = round(s_monthly_gross_min - total_monthly_cost, 2)
        s_net_max           = round(s_monthly_gross_max - total_monthly_cost, 2)
        s_margin_min        = round(s_net_min / s_monthly_gross_min * 100, 1) if s_monthly_gross_min > 0 else 0
        s_margin_max        = round(s_net_max / s_monthly_gross_max * 100, 1) if s_monthly_gross_max > 0 else 0
        stage_targets.append({
            "stage":              s.number,
            "name":               s.name,
            "daily_target":       f"${s.daily_min}–${s.daily_max}",
            "monthly_gross":      f"${s_monthly_gross_min:,.0f}–${s_monthly_gross_max:,.0f}",
            "monthly_net":        f"${s_net_min:,.0f}–${s_net_max:,.0f}",
            "margin_range":       f"{s_margin_min:.0f}%–{s_margin_max:.0f}%",
            "is_current":         s.number == stage.number,
        })

    return {
        "timestamp":           datetime.now(timezone.utc).isoformat(),
        # ── Performance ─────────────────────────────────────────────────────
        "performance": {
            "account_balance":  balance,
            "currency":         account.get("currency", "USD"),
            "apy_pct":          apy.get("apy_pct", 0),
            "avg_daily_usd":    avg_daily_gross,
            "avg_daily_pct":    apy.get("avg_daily_pct", 0),
            "total_trades":     len(closed),
            "trading_days":     apy.get("trading_days", 0),
            "total_cycles":     len(cycles),
        },
        # ── Growth stage ────────────────────────────────────────────────────
        "growth": {
            "current_stage":    stage.number,
            "stage_name":       stage.name,
            "daily_target":     f"${stage.daily_min}–${stage.daily_max}",
            "advancement":      advance,
            "params":           params,
            "all_stages":       stage_targets,
        },
        # ── Cost model ──────────────────────────────────────────────────────
        "costs": {
            "monthly": {
                "anthropic_api":  anthropic_cost,
                "fly_io":         fly_cost,
                "vercel":         vercel_cost,
                "supabase":       supabase_cost,
                "newsapi":        newsapi_cost,
                "fred_api":       fred_cost,
                "domain":         domain_cost,
                "total":          total_monthly_cost,
            },
            "daily_total":    daily_cost,
            "cost_breakdown": [
                {"name": "Fly.io (backend)",    "monthly": fly_cost,         "pct": round(fly_cost / total_monthly_cost * 100)},
                {"name": "Anthropic API",        "monthly": anthropic_cost,   "pct": round(anthropic_cost / total_monthly_cost * 100)},
                {"name": "Domain",               "monthly": domain_cost,      "pct": round(domain_cost / total_monthly_cost * 100)},
                {"name": "Vercel / Supabase",    "monthly": 0,                "pct": 0},
                {"name": "Data feeds (free)",    "monthly": 0,                "pct": 0},
            ],
        },
        # ── Profitability ────────────────────────────────────────────────────
        "profitability": {
            "monthly_gross":       round(monthly_gross, 2),
            "monthly_costs":       total_monthly_cost,
            "monthly_net":         monthly_net,
            "profit_margin_pct":   margin_pct,
            "breakeven_daily_usd": breakeven_daily,
            "breakeven_monthly":   breakeven_monthly,
            "target_margin_pct":   65.0,
            "at_target_margin":    margin_pct >= 60.0,
            "note": (
                f"Need >${daily_cost:.2f}/day gross to break even. "
                f"Need >${daily_cost / 0.35:.2f}/day gross for 65% margin. "
                f"Currently at {margin_pct:.0f}% margin."
            ),
        },
    }


@app.get("/account/snapshots")
async def get_account_snapshots(limit: int = 168):
    """Return equity curve for the last N snapshots (default 168 = 1 week of hourly)."""
    snapshots = await db.select("account_snapshots", order_by="-timestamp", limit=limit)
    snapshots.reverse()  # oldest first for chart rendering
    return {"snapshots": snapshots}


@app.post("/settings")
async def save_settings(settings: dict):
    """Persist risk settings to DB and apply to live circuit breaker."""
    await db.upsert("settings", {"key": "risk_params", "value": settings,
                                  "updated_at": datetime.now(timezone.utc).isoformat()},
                    on_conflict="key")
    # Apply risk limits to the live circuit breaker immediately (no restart required)
    cb = agent.circuit_breaker
    if "max_daily_dd_pct" in settings:
        cb.max_daily_dd = float(settings["max_daily_dd_pct"])
    if "max_weekly_dd_pct" in settings:
        cb.max_weekly_dd = float(settings["max_weekly_dd_pct"])
    if "max_monthly_dd_pct" in settings:
        cb.max_monthly_dd = float(settings["max_monthly_dd_pct"])
    return {"status": "saved"}


@app.get("/admin/trading-mode")
async def get_trading_mode():
    """Return current trading mode (demo/live) and account info."""
    row = await db.select("settings", {"key": "trading_mode"})
    current = "live" if agent.zmq.is_live else "demo"
    stored  = row[0].get("value", {}).get("mode", "demo") if row else "demo"
    return {
        "mode":          current,
        "is_live":       agent.zmq.is_live,
        "account_id":    agent.zmq.account_id,
        "base_url":      agent.zmq.base_url,
        "last_switched": row[0].get("updated_at") if row else None,
    }


class TradingModeRequest(BaseModel):
    mode: str   # "demo" or "live"


@app.post("/admin/trading-mode")
async def set_trading_mode(req: TradingModeRequest):
    """
    Hot-switch between demo and live trading.
    DEMO → uses api-fxpractice.oanda.com + OANDA_API_KEY_DEMO
    LIVE → uses api-fxtrade.oanda.com    + OANDA_API_KEY_LIVE
    Takes effect immediately — no restart required.
    """
    if req.mode not in ("demo", "live"):
        raise HTTPException(400, "mode must be 'demo' or 'live'")

    go_live = req.mode == "live"

    # Hard safety: refuse to go live if OANDA_API_KEY_LIVE is not set
    if go_live:
        import os as _os
        live_key = _os.environ.get("OANDA_API_KEY_LIVE") or _os.environ.get("OANDA_API_KEY", "")
        live_acct = _os.environ.get("OANDA_ACCOUNT_ID_LIVE") or _os.environ.get("OANDA_ACCOUNT_ID", "")
        if not live_key or not live_acct:
            raise HTTPException(400, "OANDA_API_KEY_LIVE and OANDA_ACCOUNT_ID_LIVE must be set before going live")

    result = agent.zmq.switch_mode(go_live)

    # Persist mode to DB so it survives agent restarts (reload on next startup)
    await db.upsert("settings",
        {"key": "trading_mode", "value": {"mode": req.mode},
         "updated_at": datetime.now(timezone.utc).isoformat()},
        on_conflict="key")

    logger.warning(f"[ADMIN] Trading mode changed: {result}")
    return {"status": "switched", **result}


@app.get("/risk-sentiment")
async def get_risk_sentiment():
    """Real-time risk appetite from TSLA, SPX, and JP Morgan equity price action."""
    from core.ingestion.risk_sentiment import RiskSentimentReader
    reader   = RiskSentimentReader()
    appetite, jpm = await asyncio.gather(
        reader.get_risk_appetite(),
        reader.get_jpm_outlook(),
    )
    return {**appetite, "jpm_outlook": jpm}


@app.get("/research/feed")
async def get_research_feed(category: str = "all"):
    """
    Aggregate recent videos from curated financial YouTube channels via public RSS.
    No API key required — YouTube exposes channel feeds at:
    https://www.youtube.com/feeds/videos.xml?channel_id=CHANNEL_ID
    """
    import asyncio
    import xml.etree.ElementTree as ET
    from datetime import datetime, timezone

    CHANNELS = [
        # ── Macro / Economics ──────────────────────────────────────────────
        {"id": "UCVSjbClvXbwbIOC7q3mbG7w", "name": "Economics Explained",   "category": "macro"},
        {"id": "UCASM3bXaJaRpRILvBmPWlGQ", "name": "Patrick Boyle",          "category": "macro"},
        {"id": "UCXmhU5mYwPfAdJMEMRE4JMA", "name": "Real Vision Finance",    "category": "macro"},
        {"id": "UCbmNph6atAoGfqLoCL_duAg", "name": "Ticker Symbol: YOU",     "category": "macro"},
        # ── Financial News ─────────────────────────────────────────────────
        {"id": "UCIALMKvObZNtJ6AmdCLP7Lg", "name": "Bloomberg Markets",      "category": "news"},
        {"id": "UCrp_UI8XtuYfpiqluWLD7Lw", "name": "CNBC Television",        "category": "news"},
        {"id": "UCHv-vDRWQn0Sn2lR-TGp8og", "name": "Financial Times",        "category": "news"},
        # ── Forex ──────────────────────────────────────────────────────────
        {"id": "UCt2QkDRE5f9vCh_S4iH3fGA", "name": "ForexSignals TV",        "category": "forex"},
        {"id": "UCkyLJh7gIbTe9OXn0c6ZBQQ", "name": "Rayner Teo",             "category": "forex"},
        {"id": "UCMjlDOf0UO9wSX41AkJ_keg", "name": "No Nonsense Forex",      "category": "forex"},
        # ── Gold / Commodities ─────────────────────────────────────────────
        {"id": "UCJ5YzMpKKmOiAEJcvYAaeMQ", "name": "Kitco News",             "category": "gold"},
        {"id": "UCnExV-tTiKbFBEiTJGUkWNA", "name": "Gold Silver Pros",       "category": "gold"},
    ]

    ns = {
        "atom":   "http://www.w3.org/2005/Atom",
        "yt":     "http://www.youtube.com/xml/schemas/2015",
        "media":  "http://search.yahoo.com/mrss/",
    }

    async def fetch_channel(ch: dict) -> list[dict]:
        url = f"https://www.youtube.com/feeds/videos.xml?channel_id={ch['id']}"
        try:
            async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
                r = await client.get(url, headers={"User-Agent": "Mozilla/5.0 (compatible; NVCBot/1.0)"})
                if r.status_code != 200:
                    return []
            root = ET.fromstring(r.text)
            videos = []
            for entry in root.findall("atom:entry", ns)[:5]:
                vid_id = entry.findtext("yt:videoId", namespaces=ns) or ""
                title  = entry.findtext("atom:title", namespaces=ns) or ""
                pub    = entry.findtext("atom:published", namespaces=ns) or ""
                thumb  = f"https://img.youtube.com/vi/{vid_id}/mqdefault.jpg" if vid_id else ""
                views_el = entry.find("media:group/media:community/media:statistics", ns)
                views = int(views_el.get("views", 0)) if views_el is not None else 0
                videos.append({
                    "video_id":    vid_id,
                    "title":       title,
                    "channel":     ch["name"],
                    "category":    ch["category"],
                    "published":   pub,
                    "thumbnail":   thumb,
                    "url":         f"https://www.youtube.com/watch?v={vid_id}",
                    "views":       views,
                })
            return videos
        except Exception:
            return []

    tasks = [fetch_channel(ch) for ch in CHANNELS]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    all_videos: list[dict] = []
    for r in results:
        if isinstance(r, list):
            all_videos.extend(r)

    # Filter by category
    if category != "all":
        all_videos = [v for v in all_videos if v["category"] == category]

    # Sort by published date descending
    def parse_dt(v: dict) -> datetime:
        try:
            return datetime.fromisoformat(v["published"].replace("Z", "+00:00"))
        except Exception:
            return datetime.min.replace(tzinfo=timezone.utc)

    all_videos.sort(key=parse_dt, reverse=True)

    return {"videos": all_videos[:40], "total": len(all_videos)}


@app.get("/settings")
async def get_settings():
    rows = await db.select("settings", {"key": "risk_params"})
    if rows:
        return rows[0].get("value", {})
    return {
        "max_risk_pct": 1.0, "max_daily_dd_pct": 2.0,
        "max_weekly_dd_pct": 5.0, "max_monthly_dd_pct": 10.0,
        "signal_threshold": 0.60, "max_open_trades": 8,
    }


# ─── WebSocket ─────────────────────────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        # Send current state immediately on connect — client shouldn't wait for next cycle
        from core.bridge.oanda_client import OandaClient
        oanda = OandaClient()
        account_data, positions_data = await asyncio.gather(
            oanda.get_account_info(),
            oanda.get_positions(),
            return_exceptions=True,
        )
        if not isinstance(account_data, Exception):
            cb = agent.circuit_breaker.status()
            account_data["daily_drawdown_pct"]   = cb["daily_drawdown_pct"]
            account_data["weekly_drawdown_pct"]  = cb["weekly_drawdown_pct"]
            account_data["monthly_drawdown_pct"] = cb.get("monthly_drawdown_pct", 0.0)
            account_data["circuit_breaker"]      = {
                "size_multiplier":  cb["size_multiplier"],
                "trading_allowed":  cb["trading_allowed"],
                "weekly_limit_hit": cb["weekly_limit_hit"],
                "hard_stop":        cb["hard_stop"],
            }
            await websocket.send_text(json.dumps({
                "type": "account_update", "data": account_data
            }, default=str))
        if not isinstance(positions_data, Exception):
            await websocket.send_text(json.dumps({
                "type": "positions_update", "data": {"positions": positions_data}
            }, default=str))

        # Keep-alive loop — handles ping/pong and stays open
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            if msg.get("type") == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception as exc:
        logger.warning(f"[WS] Connection error: {exc}")
        ws_manager.disconnect(websocket)
