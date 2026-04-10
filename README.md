# NVC Trader — New Vantage Co

> **Autonomous trading intelligence for MetaTrader 5.**
> Powered by Claude AI, FinBERT sentiment analysis, and real-time global news.

[![Python 3.12](https://img.shields.io/badge/python-3.12-blue)](https://python.org)
[![Next.js 14](https://img.shields.io/badge/nextjs-14-black)](https://nextjs.org)
[![MT5 EA](https://img.shields.io/badge/MetaTrader-5-blue)](https://www.metatrader5.com)
[![Claude AI](https://img.shields.io/badge/AI-Claude_Opus_4.6-orange)](https://anthropic.com)

---

## What Is This?

NVC Trader is a **fully autonomous algorithmic trading platform** that:

1. **Reads the world** — Monitors 15+ news sources, Twitter/X, and Reddit in real-time using FinBERT NLP
2. **Thinks with Claude** — Uses Claude Opus 4.6 as the primary trading brain, making fully reasoned BUY/SELL decisions with logged justifications
3. **Executes on MT5** — Sends signals to a MetaTrader 5 Expert Advisor via ZeroMQ, which executes the actual trades
4. **Shows everything** — Bloomberg-style dark terminal dashboard with live signal feed, positions, and analytics

**Instruments:** Forex (9 pairs) + Commodities (Gold, Silver, Oil, Gas)

---

## Architecture

```
Global News + Social Media
        ↓
  FinBERT Sentiment (Python)
        ↓
  Claude Opus 4.6 Agent ← Technical Analysis (pandas-ta)
        ↓                ← Economic Calendar
  Signal Decision        ← Risk Engine (Kelly Criterion)
        ↓
  ZeroMQ TCP Bridge
        ↓
  MT5 Expert Advisor (MQL5)
        ↓
  Trade Executed on Broker
        ↓
  NVC Terminal (Next.js Dashboard)
```

---

## Quickstart

### 1. Clone & Configure

```bash
git clone https://github.com/newvantageco/nvc-trader.git
cd nvc-trader
cp .env.example .env
# Fill in your API keys (see .env.example)
```

### 2. Start Core Engine

```bash
# With Docker (recommended)
docker compose up

# Or manually
pip install -r requirements.txt
python -m spacy download en_core_web_lg
uvicorn core.api.main:app --reload
```

### 3. Start Dashboard

```bash
cd dashboard
npm install
npm run dev
# Open http://localhost:3000
```

### 4. Install MT5 Expert Advisor

1. Copy `ea/NVC_Trader.mq5` to your MT5 `Experts/` folder
2. Install the [Darwinex ZeroMQ connector](https://github.com/darwinex/dwx-zeromq-connector) for MQL5
3. Compile and attach to a chart
4. Set `InpHost` to your Python engine's IP

---

## Claude AI Agent

The core intelligence lives in `core/ai/claude_agent.py`.

Claude runs on a **15-minute schedule** and also triggers on breaking news. Each cycle:

1. Checks account metrics + drawdown status
2. Scans the economic calendar for blackout periods
3. For each instrument in the watchlist, calls:
   - `get_technical_analysis` — RSI, MACD, EMA, patterns
   - `get_news_sentiment` — FinBERT-scored articles (time-decayed)
   - `get_economic_calendar` — upcoming high-impact events
4. Computes a confluence score (TA 40%, Sentiment 35%, Momentum 15%, Macro 10%)
5. Calls `execute_trade` if score ≥ 0.60
6. Logs full reasoning to database

Every decision — trade or no-trade — is **fully logged and explainable**.

---

## Risk Rules (Enforced in Code — Cannot Be Overridden)

| Rule | Value |
|------|-------|
| Max risk per trade | 1.0% of equity |
| Max daily drawdown | 3.0% — system pauses |
| Max weekly drawdown | 6.0% |
| Max monthly drawdown | 10.0% — hard stop |
| Max open trades | 8 |
| Min signal score | 0.60 |
| News blackout | 30min before / 15min after high-impact events |
| No trading | Sunday 21:00 – Monday 00:00 UTC |

---

## Project Structure

```
nvc-trader/
├── core/
│   ├── ai/              # Claude agent + tools + prompts
│   ├── ingestion/       # News fetcher, social media, economic calendar
│   ├── sentiment/       # FinBERT pipeline
│   ├── technical/       # Multi-timeframe TA engine
│   ├── risk/            # Position sizer, circuit breaker
│   ├── bridge/          # ZeroMQ MT5 bridge
│   ├── api/             # FastAPI server + WebSocket
│   └── db/              # Supabase client
├── ea/                  # MetaTrader 5 Expert Advisor (MQL5)
├── dashboard/           # Next.js Bloomberg-style terminal
├── backtest/            # Backtesting framework
├── compliance/          # Regulatory documentation
├── supabase_schema.sql  # Database schema
└── ARCHITECTURE.md      # Full system design document
```

---

## Legal Notice

This software is for **personal research and educational use**. Trading financial instruments carries significant risk of loss. Past performance does not guarantee future results.

If used to manage client funds, ensure compliance with all applicable regulations (FCA, CFTC, MiFID II).

---

*New Vantage Co — Precision Intelligence for Modern Markets*
