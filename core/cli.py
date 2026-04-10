"""
NVC Trader — Terminal CLI
Usage: python -m core.cli [COMMAND] [OPTIONS]

Commands:
  status      System health overview
  account     Broker account metrics
  positions   All open positions
  signals     Recent signals from DB
  scan        Run a live signal scan (no trade execution)
  run         Trigger a full Claude agent cycle
  sentiment   Get live sentiment for an instrument
  ta          Technical analysis for an instrument
  backtest    Run a backtest simulation
  logs        Tail Fly.io logs
  deploy      Deploy to Fly.io
  secrets     Show configured env var status (no values)
"""

import asyncio
import os
import sys
from datetime import datetime, timezone

import httpx
import typer
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.live import Live
from rich.spinner import Spinner
from rich.columns import Columns
from rich.rule import Rule

app     = typer.Typer(help="NVC Trader — Autonomous Trading Intelligence CLI", add_completion=False)
console = Console()

API_URL  = os.environ.get("NVC_API_URL", "https://nvc-trader-engine.fly.dev")
FLY_APP  = "nvc-trader-engine"


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _api(path: str, method: str = "GET", json: dict | None = None) -> dict:
    try:
        with httpx.Client(timeout=30, base_url=API_URL) as client:
            if method == "POST":
                r = client.post(path, json=json or {})
            else:
                r = client.get(path)
            r.raise_for_status()
            return r.json()
    except httpx.ConnectError:
        console.print(f"[red]Cannot connect to {API_URL}[/red]")
        console.print("[dim]Set NVC_API_URL or run the engine locally with: uvicorn core.api.main:app[/dim]")
        raise typer.Exit(1)
    except httpx.HTTPStatusError as e:
        console.print(f"[red]API error {e.response.status_code}: {e.response.text[:200]}[/red]")
        raise typer.Exit(1)


def _color_pnl(value: float) -> str:
    if value > 0:
        return f"[green]+{value:.2f}[/green]"
    if value < 0:
        return f"[red]{value:.2f}[/red]"
    return f"[dim]0.00[/dim]"


def _color_dir(direction: str) -> str:
    return "[green]BUY[/green]" if direction == "BUY" else "[red]SELL[/red]"


def _score_bar(score: float) -> str:
    filled = int(score * 20)
    bar    = "█" * filled + "░" * (20 - filled)
    color  = "green" if score >= 0.75 else "yellow" if score >= 0.60 else "dim"
    return f"[{color}]{bar}[/{color}] [{color}]{score:.0%}[/{color}]"


def _header():
    console.print()
    console.print(Panel(
        "[bold amber1]NVC TERMINAL[/bold amber1]  [dim]New Vantage Co · Autonomous Trading Intelligence[/dim]",
        border_style="dark_orange3",
        padding=(0, 2),
    ))


# ─── status ───────────────────────────────────────────────────────────────────

@app.command()
def status():
    """Full system health overview."""
    _header()
    with console.status("[bold]Checking system health...[/bold]"):
        try:
            health   = _api("/health")
            account  = _api("/account")
            positions = _api("/positions")
            signals  = _api("/signals?limit=5")
        except typer.Exit:
            return

    # Health panel
    engine_status = account.get("system_status", "unknown").upper()
    status_color  = "green" if engine_status == "DEMO" else "bright_green" if engine_status == "LIVE" else "red"

    t = Table(show_header=False, box=box.SIMPLE, padding=(0, 2))
    t.add_column(style="dim", width=22)
    t.add_column()
    t.add_row("Engine Status",    f"[{status_color}]● {engine_status}[/{status_color}]")
    t.add_row("API Version",      health.get("version", "—"))
    t.add_row("Server Time",      health.get("time", "—"))
    t.add_row("Broker",           account.get("broker", "OANDA"))
    t.add_row("Open Positions",   f"{len(positions.get('positions', []))}/8")
    t.add_row("Recent Signals",   str(len(signals.get("signals", []))))
    console.print(Panel(t, title="[bold]System Status[/bold]", border_style="dark_orange3"))

    # Account metrics
    console.print(_account_panel(account))
    console.print()


# ─── account ──────────────────────────────────────────────────────────────────

@app.command()
def account():
    """Broker account metrics — equity, drawdown, margin."""
    _header()
    with console.status("[bold]Fetching account...[/bold]"):
        data = _api("/account")
    console.print(_account_panel(data))
    console.print()


def _account_panel(data: dict) -> Panel:
    equity    = data.get("equity", 0.0)
    balance   = data.get("balance", 0.0)
    daily_dd  = data.get("daily_drawdown_pct", 0.0)
    week_dd   = data.get("weekly_drawdown_pct", 0.0)
    free_m    = data.get("free_margin", 0.0)
    unreal    = data.get("unrealised_pl", 0.0)

    dd_color  = "green" if daily_dd < 1.5 else "yellow" if daily_dd < 2.5 else "red"

    t = Table(show_header=False, box=box.SIMPLE, padding=(0, 2))
    t.add_column(style="dim", width=22)
    t.add_column(style="bold")
    t.add_row("Balance",          f"[white]${balance:>12,.2f}[/white]")
    t.add_row("Equity",           f"[white]${equity:>12,.2f}[/white]")
    t.add_row("Free Margin",      f"[dim]${free_m:>12,.2f}[/dim]")
    t.add_row("Unrealised P&L",   _color_pnl(unreal))
    t.add_row("Daily Drawdown",   f"[{dd_color}]-{daily_dd:.2f}%[/{dd_color}]  (limit 3.00%)")
    t.add_row("Weekly Drawdown",  f"[dim]-{week_dd:.2f}%[/dim]  (limit 6.00%)")
    return Panel(t, title="[bold]Account Metrics[/bold]", border_style="dark_orange3")


# ─── positions ────────────────────────────────────────────────────────────────

@app.command()
def positions():
    """All currently open positions."""
    _header()
    with console.status("[bold]Fetching positions...[/bold]"):
        data = _api("/positions")

    pos_list = data.get("positions", [])
    if not pos_list:
        console.print("[dim]No open positions.[/dim]")
        console.print()
        return

    t = Table(box=box.ROUNDED, border_style="dark_orange3", show_lines=True)
    t.add_column("Instrument", style="bold white",  width=12)
    t.add_column("Dir",                             width=6)
    t.add_column("Lots",        justify="right",    width=7)
    t.add_column("Entry",       justify="right",    width=10)
    t.add_column("Current",     justify="right",    width=10)
    t.add_column("SL",          justify="right",    width=10)
    t.add_column("TP",          justify="right",    width=10)
    t.add_column("P&L",         justify="right",    width=10)
    t.add_column("Ticket",      justify="right",    width=12, style="dim")

    total_pnl = 0.0
    for p in pos_list:
        pnl = p.get("profit", 0.0)
        total_pnl += pnl
        t.add_row(
            p.get("instrument", ""),
            _color_dir(p.get("direction", "")),
            f"{p.get('lot_size', 0):.2f}",
            f"{p.get('entry_price', 0):.5f}",
            f"{p.get('current_price', 0):.5f}",
            f"[red]{p.get('stop_loss', 0):.5f}[/red]",
            f"[green]{p.get('take_profit', 0):.5f}[/green]",
            _color_pnl(pnl),
            str(p.get("ticket", "")),
        )

    console.print(t)
    console.print(f"\n  Total Unrealised P&L: {_color_pnl(total_pnl)}\n")


# ─── signals ──────────────────────────────────────────────────────────────────

@app.command()
def signals(limit: int = typer.Option(20, help="Number of signals to show")):
    """Recent signals from the database."""
    _header()
    with console.status("[bold]Fetching signals...[/bold]"):
        data = _api(f"/signals?limit={limit}")

    sig_list = data.get("signals", [])
    if not sig_list:
        console.print("[dim]No signals yet. Run: python -m core.cli run[/dim]\n")
        return

    t = Table(box=box.ROUNDED, border_style="dark_orange3", show_lines=True)
    t.add_column("Time",       width=18, style="dim")
    t.add_column("Instrument", width=10, style="bold")
    t.add_column("Dir",        width=6)
    t.add_column("Score",      width=26)
    t.add_column("Lots",       width=6, justify="right")
    t.add_column("Reason",     min_width=30)

    for s in sig_list:
        ts = s.get("created_at", "")[:19].replace("T", " ")
        t.add_row(
            ts,
            s.get("instrument", ""),
            _color_dir(s.get("direction", "")),
            _score_bar(s.get("score", 0)),
            str(s.get("lot_size", "")),
            f"[dim]{s.get('reason', '')[:60]}[/dim]",
        )

    console.print(t)
    console.print()


# ─── scan ─────────────────────────────────────────────────────────────────────

@app.command()
def scan(
    instrument: str = typer.Argument(None, help="Single instrument, or all if omitted"),
):
    """Live signal scan — shows scores without executing trades."""
    _header()

    WATCHLIST = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD",
                 "XAUUSD", "USOIL", "UKOIL", "XAGUSD", "NATGAS"]
    targets = [instrument.upper()] if instrument else WATCHLIST

    async def _run():
        from core.signals.signal_generator import SignalGenerator
        gen = SignalGenerator()

        console.print(f"\n[bold]Scanning {len(targets)} instruments...[/bold]\n")
        results = await gen.scan_watchlist(targets)

        t = Table(box=box.ROUNDED, border_style="dark_orange3", show_lines=True)
        t.add_column("Instrument", style="bold", width=12)
        t.add_column("Score",      width=28)
        t.add_column("Dir",        width=7)
        t.add_column("TA",         width=8, justify="right")
        t.add_column("Sentiment",  width=8, justify="right")
        t.add_column("Momentum",   width=8, justify="right")
        t.add_column("Blackout",   width=8)
        t.add_column("Tradeable",  width=10)

        for r in results:
            bd = r.get("breakdown", {})
            t.add_row(
                r["instrument"],
                _score_bar(r["score"]),
                _color_dir(r["direction"]) if r["direction"] != "NEUTRAL" else "[dim]—[/dim]",
                f"{bd.get('ta', 0):.0%}",
                f"{bd.get('sentiment', 0):.0%}",
                f"{bd.get('momentum', 0):.0%}",
                "[red]YES[/red]" if r.get("blackout") else "[dim]No[/dim]",
                "[green bold]✓ YES[/green bold]" if r.get("tradeable") else "[dim]No[/dim]",
            )
        console.print(t)
        console.print()

    asyncio.run(_run())


# ─── run ──────────────────────────────────────────────────────────────────────

@app.command()
def run(
    trigger: str = typer.Option("manual-cli", help="Trigger label for the cycle"),
    local:   bool = typer.Option(False,  help="Run agent locally (not via API)"),
):
    """Trigger a full Claude agent cycle — scans markets and executes trades."""
    _header()

    if local:
        async def _local():
            from core.ai.claude_agent import VantageAgent
            console.print("[bold yellow]Running agent cycle locally...[/bold yellow]\n")
            agent  = VantageAgent()
            result = await agent.run_cycle(trigger=f"cli:{trigger}")
            _print_cycle_result(result)
        asyncio.run(_local())
    else:
        console.print(f"[bold]Triggering agent cycle on {API_URL}...[/bold]\n")
        with console.status("[bold amber1]Claude is analysing markets...[/bold amber1]"):
            result = _api(f"/agent/run?trigger={trigger}", method="POST")
        _print_cycle_result(result)


def _print_cycle_result(result: dict):
    status = result.get("status", "unknown")
    trades = result.get("trades", [])
    iters  = result.get("iterations", 0)

    color = "green" if status == "completed" else "red"
    console.print(f"  Status:     [{color}]{status.upper()}[/{color}]")
    console.print(f"  Iterations: {iters} tool calls")
    console.print(f"  Trades:     {len(trades)} executed")

    if trades:
        console.print()
        for t in trades:
            sig = t.get("signal", {})
            console.print(
                f"  [bold green]✓ TRADE[/bold green]  "
                f"{_color_dir(sig.get('direction', ''))} "
                f"[white]{sig.get('instrument', '')}[/white]  "
                f"lot={sig.get('lot_size', '')}  "
                f"score={sig.get('score', 0):.0%}  "
                f"[dim]{sig.get('reason', '')[:60]}[/dim]"
            )
    console.print()


# ─── sentiment ────────────────────────────────────────────────────────────────

@app.command()
def sentiment(instrument: str = typer.Argument(..., help="e.g. EURUSD, XAUUSD")):
    """Live sentiment score for an instrument."""
    _header()
    with console.status(f"[bold]Fetching sentiment for {instrument.upper()}...[/bold]"):
        data = _api(f"/sentiment/{instrument.upper()}")

    score = data.get("score", 0.0)
    bias  = data.get("bias", "neutral").upper()
    count = data.get("article_count", 0)

    bias_color = "green" if bias == "BULLISH" else "red" if bias == "BEARISH" else "dim"

    t = Table(show_header=False, box=box.SIMPLE, padding=(0, 2))
    t.add_column(style="dim", width=20)
    t.add_column()
    t.add_row("Instrument",    f"[bold]{instrument.upper()}[/bold]")
    t.add_row("Bias",          f"[{bias_color}]{bias}[/{bias_color}]")
    t.add_row("Score",         f"[bold]{score:+.3f}[/bold]  [-1.0 bearish → +1.0 bullish]")
    t.add_row("Article Count", str(count))
    console.print(Panel(t, title="[bold]Sentiment Analysis[/bold]", border_style="dark_orange3"))

    events = data.get("top_events", [])
    if events:
        console.print("\n[bold]Top driving events:[/bold]")
        for ev in events[:5]:
            s = ev.get("score", 0)
            c = "green" if s > 0 else "red"
            console.print(f"  [{c}]{s:+.2f}[/{c}]  [dim]{ev.get('source','').upper()}[/dim]  {ev.get('title','')[:80]}")
    console.print()


# ─── ta ───────────────────────────────────────────────────────────────────────

@app.command()
def ta(instrument: str = typer.Argument(..., help="e.g. EURUSD, XAUUSD")):
    """Multi-timeframe technical analysis for an instrument."""
    _header()

    async def _run():
        from core.technical.indicator_engine import IndicatorEngine
        engine = IndicatorEngine()
        console.print(f"[bold]Analysing {instrument.upper()} across M15 / H1 / H4 / D1...[/bold]\n")
        result = await engine.analyse(instrument.upper())

        overall = result.get("overall_bias", "neutral")
        score   = result.get("ta_score", 0.5)
        bias_c  = "green" if overall == "bullish" else "red" if overall == "bearish" else "dim"

        console.print(f"  Overall Bias:  [{bias_c}]{overall.upper()}[/{bias_c}]")
        console.print(f"  TA Score:      {_score_bar(score)}")
        console.print()

        for tf, data in result.get("timeframes", {}).items():
            if "error" in data:
                console.print(f"  [red]{tf}: error — {data['error']}[/red]")
                continue

            ema  = data.get("ema", {})
            rsi  = data.get("rsi", {})
            macd = data.get("macd", {})
            pats = data.get("patterns", [])

            rsi_val = rsi.get("value", 0) or 0
            rsi_c   = "green" if 45 < rsi_val < 70 else "red" if rsi_val < 35 else "yellow"
            trend_c = "green" if ema.get("ema9_above_21") else "red"

            console.print(f"  [bold]{tf}[/bold]")
            console.print(f"    Price:   {data.get('price', 0):.5f}")
            console.print(f"    Trend:   [{trend_c}]EMA9 {'>' if ema.get('ema9_above_21') else '<'} EMA21[/{trend_c}]  "
                          f"Price {'above' if ema.get('price_above_200') else 'below'} EMA200")
            console.print(f"    RSI:     [{rsi_c}]{rsi_val:.1f}[/{rsi_c}]  momentum={rsi.get('momentum', 0):+.1f}")
            console.print(f"    ATR:     {data.get('atr', 0):.5f}")
            if pats:
                console.print(f"    [yellow]Patterns: {', '.join(pats)}[/yellow]")
            console.print()

    asyncio.run(_run())


# ─── backtest ─────────────────────────────────────────────────────────────────

@app.command()
def backtest(
    instrument: str = typer.Option("EURUSD", help="Instrument to backtest"),
    days:       int = typer.Option(365,      help="Days of history"),
    cash:       int = typer.Option(10000,    help="Starting equity"),
):
    """Run a backtest simulation on historical data."""
    _header()
    console.print(f"[bold]Backtesting {instrument} over {days} days (${cash:,} starting equity)[/bold]\n")

    async def _run():
        from backtest.backtest_runner import run_backtest
        result = await run_backtest(instrument=instrument, days=days, starting_cash=cash)
        _print_backtest_result(result)

    asyncio.run(_run())


def _print_backtest_result(r: dict):
    t = Table(show_header=False, box=box.SIMPLE, padding=(0, 2))
    t.add_column(style="dim", width=24)
    t.add_column(style="bold")
    t.add_row("Final Equity",    f"${r.get('final_equity', 0):,.2f}")
    t.add_row("Total Return",    _color_pnl(r.get("total_return_pct", 0)) + "%")
    t.add_row("Sharpe Ratio",    f"{r.get('sharpe_ratio', 0):.2f}")
    t.add_row("Max Drawdown",    f"[red]-{r.get('max_drawdown_pct', 0):.2f}%[/red]")
    t.add_row("Win Rate",        f"{r.get('win_rate_pct', 0):.1f}%")
    t.add_row("Profit Factor",   f"{r.get('profit_factor', 0):.2f}")
    t.add_row("Total Trades",    str(r.get("total_trades", 0)))
    t.add_row("Winning Trades",  str(r.get("winning_trades", 0)))
    t.add_row("Losing Trades",   str(r.get("losing_trades", 0)))
    console.print(Panel(t, title="[bold]Backtest Results[/bold]", border_style="dark_orange3"))
    console.print()


# ─── logs ─────────────────────────────────────────────────────────────────────

@app.command()
def logs(
    tail: int  = typer.Option(50,    help="Number of lines"),
    live: bool = typer.Option(False, help="Stream live logs"),
):
    """Tail Fly.io logs for the running engine."""
    if live:
        os.execlp("fly", "fly", "logs", "--app", FLY_APP)
    else:
        os.execlp("fly", "fly", "logs", "--app", FLY_APP, "-n", str(tail))


# ─── deploy ───────────────────────────────────────────────────────────────────

@app.command()
def deploy():
    """Deploy the core engine to Fly.io."""
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    os.execlp("fly", "fly", "deploy", "--app", FLY_APP, "--dockerfile", "Dockerfile.fly", "--remote-only")


# ─── secrets ──────────────────────────────────────────────────────────────────

@app.command()
def secrets():
    """Show which env vars are configured (values hidden)."""
    _header()

    REQUIRED = [
        ("ANTHROPIC_API_KEY",        "Claude AI brain"),
        ("OANDA_API_KEY",            "OANDA broker execution"),
        ("OANDA_ACCOUNT_ID",         "OANDA account number"),
        ("SUPABASE_URL",             "Database"),
        ("SUPABASE_SERVICE_ROLE_KEY","Database auth"),
        ("NEWS_API_KEY",             "NewsAPI.org"),
    ]
    OPTIONAL = [
        ("TWITTER_BEARER_TOKEN",     "Twitter/X sentiment"),
        ("REDDIT_CLIENT_ID",         "Reddit sentiment"),
        ("OANDA_LIVE",               "Live trading flag (default: false)"),
        ("ALPHA_VANTAGE_API_KEY",    "Additional market data"),
        ("SENTRY_DSN",               "Error monitoring"),
    ]

    def _row(name: str, desc: str, required: bool) -> tuple:
        val = os.environ.get(name, "")
        if val:
            status = "[green]✓ SET[/green]"
        elif required:
            status = "[red]✗ MISSING[/red]"
        else:
            status = "[dim]— optional[/dim]"
        return name, desc, status

    t = Table(box=box.ROUNDED, border_style="dark_orange3")
    t.add_column("Variable",    style="white",    width=32)
    t.add_column("Purpose",     style="dim",       width=35)
    t.add_column("Status",                         width=14)

    console.print("\n[bold]Required[/bold]")
    for name, desc in REQUIRED:
        t.add_row(*_row(name, desc, required=True))
    console.print(t)

    t2 = Table(box=box.ROUNDED, border_style="dim")
    t2.add_column("Variable",    style="dim",    width=32)
    t2.add_column("Purpose",     style="dim",    width=35)
    t2.add_column("Status",                      width=14)
    console.print("\n[bold dim]Optional[/bold dim]")
    for name, desc in OPTIONAL:
        t2.add_row(*_row(name, desc, required=False))
    console.print(t2)

    console.print("\n[dim]Set via: fly secrets set KEY=value --app nvc-trader-engine[/dim]\n")


# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app()
