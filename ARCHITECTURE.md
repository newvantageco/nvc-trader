# New Vantage Co — NVC Trader
## Full System Architecture Blueprint

> **Mission:** A news-reactive, multi-instrument algorithmic trading platform for MetaTrader 5,
> combining real-time global news sentiment, social media signals, and technical analysis
> to trade Forex and Commodities — built to Bloomberg Terminal depth, Trade212 clarity,
> and Robinhood-grade execution logic.

---

## 1. System Overview

```
╔══════════════════════════════════════════════════════════════════════╗
║                    NVC VANTAGE TERMINAL (UI)                         ║
║           Next.js 14 · Bloomberg Dark · Real-time WebSocket          ║
╚══════════════════════╦═══════════════════════════════════════════════╝
                       ║ WebSocket / REST
╔══════════════════════╩═══════════════════════════════════════════════╗
║                    NVC CORE ENGINE (Python)                           ║
║  ┌───────────────┐  ┌────────────────┐  ┌──────────────────────────┐ ║
║  │ News/Sentiment│  │ Technical      │  │ Risk Manager             │ ║
║  │ Engine        │  │ Analysis Engine│  │ · Kelly Criterion        │ ║
║  │ (FinBERT+GPT) │  │ (ta-lib)       │  │ · Max drawdown limits    │ ║
║  └──────┬────────┘  └───────┬────────┘  └────────────┬─────────────┘ ║
║         └──────────────┬────┘                        │               ║
║                  ┌─────▼─────────────────────────────▼─────────────┐ ║
║                  │          SIGNAL CONFLUENCE ENGINE                │ ║
║                  │   Score = (Sentiment × 0.35) +                  │ ║
║                  │           (Technical × 0.40) +                  │ ║
║                  │           (Momentum × 0.15) +                   │ ║
║                  │           (Macro × 0.10)                        │ ║
║                  └────────────────────┬────────────────────────────┘ ║
╚═══════════════════════════════════════╬══════════════════════════════╝
                                        ║ ZeroMQ TCP socket
╔═══════════════════════════════════════╩══════════════════════════════╗
║              MT5 EXPERT ADVISOR (MQL5)                               ║
║  · Receives JSON signal packets via ZeroMQ                           ║
║  · Executes BUY/SELL/CLOSE with SL/TP                                ║
║  · Reports fill prices back to Core Engine                           ║
╚══════════════════════════════════════════════════════════════════════╝

╔══════════════════════════════════════════════════════════════════════╗
║                        DATA LAYER                                    ║
║  ┌──────────────┐ ┌─────────────┐ ┌──────────┐ ┌─────────────────┐  ║
║  │ News APIs    │ │ Social      │ │ Economic │ │ Price Feeds     │  ║
║  │ · NewsAPI    │ │ · Twitter/X │ │ Calendar │ │ · MT5 native    │  ║
║  │ · GNews      │ │ · Reddit    │ │ · ForexF │ │ · Yahoo Finance │  ║
║  │ · Reuters    │ │ · StockTwits│ │ · Invest │ │ · Alpha Vantage │  ║
║  │ · AP News    │ │             │ │   .com   │ │                 │  ║
║  │ · FT RSS     │ │             │ │          │ │                 │  ║
║  └──────────────┘ └─────────────┘ └──────────┘ └─────────────────┘  ║
╚══════════════════════════════════════════════════════════════════════╝
```

---

## 2. Instruments Traded

### Forex (Currency Pairs)
| Tier | Pairs |
|------|-------|
| Major | EUR/USD, GBP/USD, USD/JPY, AUD/USD, USD/CAD, NZD/USD, USD/CHF |
| Minor | EUR/GBP, EUR/JPY, GBP/JPY, AUD/JPY, EUR/AUD, GBP/AUD |
| Emerging | USD/TRY, USD/ZAR, USD/BRL (lower allocation, higher volatility) |

### Commodities (CFDs on MT5)
| Category | Instruments |
|----------|-------------|
| Precious Metals | XAUUSD (Gold), XAGUSD (Silver), XPTUSD (Platinum) |
| Energy | USOIL (WTI Crude), UKOIL (Brent Crude), NATGAS |
| Agriculture | CORN, WHEAT, SOYBEAN, SUGAR (seasonal bias logic) |

---

## 3. Tech Stack

### Backend — Core Engine
```
Language:       Python 3.12
Sentiment NLP:  FinBERT (ProsusAI/finbert) — financial-domain BERT
                GPT-4o (OpenAI) — complex geopolitical interpretation
NER:            spaCy + custom gazetteer (country → currency mapping)
Technical:      ta-lib, pandas-ta, numpy
Social Media:   tweepy (X/Twitter), praw (Reddit), stocktwits REST
News Feeds:     newsapi-python, feedparser (RSS), aiohttp (async)
Economic Data:  investpy, pandas-datareader, FRED API
ZeroMQ Bridge:  pyzmq (PUSH/PULL pattern → MT5 EA)
Scheduling:     APScheduler (news polls every 60s, TA every 5min)
Database:       PostgreSQL (Supabase) + Redis (signal cache / locks)
API Server:     FastAPI + WebSocket (feeds dashboard)
Backtesting:    backtesting.py + MT5 Strategy Tester via Python API
```

### MT5 Expert Advisor
```
Language:       MQL5
Pattern:        ZeroMQ PULL socket listener
Signal Format:  JSON { instrument, direction, entry, sl, tp, size, reason, score }
Execution:      OrderSend() with market orders + pending limit fallback
Reporting:      ZeroMQ PUSH back to Python (fills, errors)
```

### Dashboard — NVC Terminal
```
Framework:      Next.js 14 (App Router)
Language:       TypeScript
Charts:         TradingView Lightweight Charts v4
Real-time:      WebSocket (socket.io)
State:          Zustand
Styling:        Tailwind CSS + CSS variables (Bloomberg dark theme)
Auth:           Clerk or NextAuth.js
Hosting:        Vercel
```

### Infrastructure
```
Database:       Supabase (PostgreSQL)
Cache:          Upstash Redis
Secrets:        Vercel env vars / .env.local
Monitoring:     Sentry
Logging:        Structured JSON → Supabase logs table
VPS (Python):   Hostinger VPS (Ubuntu 22.04, 8GB RAM, 4 vCPU)
MT5:            Runs on Windows VPS (separate, broker-specific)
```

---

## 4. Sentiment → Signal Pipeline

```
News Article / Tweet / Reddit Post
           │
           ▼
    ┌──────────────────────────────────┐
    │  NER: Extract Entities           │
    │  · Country: "United States"      │
    │  · Event: "Fed rate decision"    │
    │  · Commodity: "crude oil"        │
    └──────────────┬───────────────────┘
                   │
           ┌───────▼───────────┐
           │ FinBERT Sentiment  │
           │ positive / neutral │
           │ / negative + score │
           └───────┬────────────┘
                   │
           ┌───────▼──────────────────────────────────┐
           │  Country → Currency Mapping               │
           │  "United States" negative → USD bearish   │
           │  "Saudi Arabia supply cut" → OIL bullish  │
           │  "UK inflation surprise" → GBP volatile   │
           └───────┬──────────────────────────────────┘
                   │
           ┌───────▼──────────────────────────────────┐
           │  Recency Weighting                        │
           │  score × e^(-λt) — decay over 4 hours    │
           │  Breaking news: λ=0.3, Economic: λ=0.1   │
           └───────┬──────────────────────────────────┘
                   │
           ┌───────▼──────────────────────────────────┐
           │  Aggregated Sentiment Score per Asset     │
           │  Rolling 2hr window, source-weighted      │
           │  (Reuters > Reddit > StockTwits)          │
           └──────────────────────────────────────────┘
```

---

## 5. Technical Analysis Engine

For each instrument on each timeframe (M15, H1, H4, D1):

```python
Indicators computed:
  · RSI(14) — momentum
  · EMA(9), EMA(21), EMA(200) — trend
  · MACD(12,26,9) — momentum crossover
  · Bollinger Bands(20,2) — volatility/mean reversion
  · ATR(14) — dynamic SL/TP sizing
  · Volume Profile — institutional levels
  · Stochastic(14,3,3) — overbought/oversold confirmation
  · Pivot Points (classic + fibonacci) — key S/R levels

Pattern recognition:
  · Engulfing candles
  · Inside bars (breakout setups)
  · Double top/bottom
  · Head & shoulders
  · Flag/pennant continuation

Multi-timeframe confluence:
  · Signal must align on at least 2/4 timeframes
  · D1 trend direction must not oppose entry
```

---

## 6. Signal Confluence Engine

```
Final Score = (Sentiment × 0.35) + (TA × 0.40) + (Momentum × 0.15) + (Macro × 0.10)

Thresholds:
  Score ≥ 0.75  → STRONG signal → full position size
  Score 0.60–0.74 → MEDIUM signal → half position size
  Score < 0.60  → NO TRADE

Macro layer (0.10 weight):
  · Interest rate differential between currency pair countries
  · GDP growth momentum (3-month rolling)
  · Inflation trajectory (CPI trend)
  · Unemployment trends
  · Political stability score (news-derived, 30-day window)

Volatility filter:
  · VIX > 30: reduce all position sizes by 50%
  · News blackout: 30min before + 15min after high-impact events (Non-Farm, CPI, FOMC)
```

---

## 7. Risk Management Rules

```
Per-Trade Rules:
  · Max risk per trade: 1.0% of account equity
  · SL: 1.5× ATR(14) from entry
  · TP: 2.5× ATR(14) from entry (minimum 1:1.5 R:R)
  · Position size: computed via Kelly Criterion (capped at full-Kelly × 0.5)

Portfolio Rules:
  · Max open trades: 8 simultaneously
  · Max correlated exposure: Cannot hold EUR/USD + GBP/USD > 3% combined risk
  · Max daily drawdown: 3% — system pauses all trading for 24hrs
  · Max weekly drawdown: 6% — system enters review mode
  · Max monthly drawdown: 10% — full stop, human review required

Execution Rules:
  · Market orders only during active sessions (London 08:00–17:00, NY 13:00–22:00 UTC)
  · No trading Sunday 21:00–Monday 00:00 UTC (thin liquidity)
  · Minimum spread filter: Do not enter if spread > 2× average 30-day spread
  · Slippage protection: Cancel if fill > 3 pips from signal price
```

---

## 8. News Sources & Data Feeds

### Tier 1 — High Trust (weight: 1.0)
| Source | Feed Type | Latency |
|--------|-----------|---------|
| Reuters | RSS + API | < 30s |
| Associated Press | RSS | < 60s |
| Financial Times | RSS | < 60s |
| Bloomberg (free tier) | RSS | < 60s |
| CNBC | RSS | < 60s |

### Tier 2 — Medium Trust (weight: 0.7)
| Source | Feed Type | Latency |
|--------|-----------|---------|
| BBC News | RSS | < 2min |
| The Guardian | RSS | < 2min |
| Al Jazeera | RSS | < 2min |
| Seeking Alpha | RSS | < 5min |
| Zero Hedge | RSS | < 5min |

### Tier 3 — Social (weight: 0.4)
| Source | API | Notes |
|--------|-----|-------|
| Twitter/X | API v2 (Premium) | Forex traders, $EURUSD etc |
| Reddit | PRAW (r/Forex, r/investing, r/wallstreetbets) | Sentiment crowd |
| StockTwits | REST API | Financial-specific social |

### Economic Calendar
| Source | Data |
|--------|------|
| ForexFactory (scrape) | Event times, impact level, forecast vs actual |
| Investing.com API | Central bank decisions, GDP, CPI, NFP |
| FRED (Federal Reserve) | US macro data |

---

## 9. Country → Currency Mapping (NER Layer)

```python
COUNTRY_CURRENCY_MAP = {
    # Major economies
    "United States": ["USD", "DXY"],
    "Eurozone": ["EUR"],
    "United Kingdom": ["GBP"],
    "Japan": ["JPY"],
    "Australia": ["AUD"],
    "Canada": ["CAD"],
    "New Zealand": ["NZD"],
    "Switzerland": ["CHF"],
    # Commodity-linked
    "Saudi Arabia": ["OIL", "USD"],
    "Russia": ["OIL", "NATGAS"],
    "Ukraine": ["WHEAT", "CORN"],
    "Brazil": ["SOYBEAN", "SUGAR", "BRL"],
    "China": ["COPPER", "IRON"],
    "South Africa": ["XAUUSD", "XPTUSD", "ZAR"],
    # Event-type → asset
    "Fed": ["USD"],
    "ECB": ["EUR"],
    "BOE": ["GBP"],
    "BOJ": ["JPY"],
    "OPEC": ["USOIL", "UKOIL"],
}

EVENT_IMPACT_MAP = {
    "interest rate decision": 1.0,
    "non-farm payroll": 0.9,
    "CPI": 0.85,
    "GDP": 0.80,
    "trade war": 0.75,
    "sanctions": 0.70,
    "election": 0.65,
    "natural disaster": 0.50,
}
```

---

## 10. ZeroMQ Signal Protocol (Python ↔ MT5)

### Python → MT5 (PUSH)
```json
{
  "signal_id": "uuid4",
  "timestamp": "2026-04-10T14:32:00Z",
  "instrument": "EURUSD",
  "direction": "BUY",
  "entry_type": "MARKET",
  "entry_price": 1.09245,
  "stop_loss": 1.08890,
  "take_profit": 1.09780,
  "lot_size": 0.12,
  "score": 0.82,
  "reason": "ECB hawkish surprise + RSI momentum + EMA crossover H4",
  "source_events": ["ECB rate hold above forecast", "EUR/USD RSI breakout 60"],
  "expiry": "2026-04-10T16:32:00Z"
}
```

### MT5 → Python (PUSH — fill report)
```json
{
  "signal_id": "uuid4",
  "ticket": 123456789,
  "status": "FILLED",
  "fill_price": 1.09248,
  "fill_time": "2026-04-10T14:32:01Z",
  "slippage_pips": 0.3
}
```

---

## 11. Dashboard — NVC Terminal UI

### Pages
```
/ (Terminal Home)
  ├── Live Signal Feed (scrolling tape — Bloomberg-style)
  ├── Open Positions (P&L in real-time)
  ├── Account Equity Curve (TradingView chart)
  └── System Status (engine health, data feed status)

/signals
  ├── Signal history (all trades with reasoning)
  ├── Score breakdown per signal
  └── News events that triggered signals

/markets
  ├── Watchlist (Forex + Commodities)
  ├── Sentiment gauge per instrument (-100 to +100)
  └── Economic calendar (next 48hrs highlighted)

/analytics
  ├── Win rate by instrument, time-of-day, session
  ├── Sharpe ratio, max drawdown, profit factor
  ├── News source accuracy (which sources predicted best)
  └── Monthly P&L breakdown

/settings
  ├── Risk parameters (% per trade, max drawdown)
  ├── Instruments toggle (enable/disable per asset)
  ├── Signal threshold adjustment
  └── News source weights
```

### Design Language
```
Background:     #0a0e14 (Bloomberg near-black)
Surface:        #111827 (card backgrounds)
Accent:         #f59e0b (amber — NVC brand, Bloomberg-inspired)
Success:        #10b981 (green — profit)
Danger:         #ef4444 (red — loss)
Text Primary:   #f1f5f9
Text Secondary: #94a3b8
Font:           JetBrains Mono (data) + Inter (UI labels)
Charts:         TradingView Lightweight Charts (dark theme)
```

---

## 12. Legal & Compliance Framework

### UK / EU (MiFID II)
- [ ] Register NVC as a company (Companies House UK)
- [ ] If trading client funds: FCA authorisation required (AR or direct)
- [ ] If personal trading only: no FCA licence needed
- [ ] Best execution documentation (record all order routing decisions)
- [ ] Trade reporting: all trades logged with timestamp, price, reason
- [ ] Algorithm change log: version-controlled, documented rationale

### US (CFTC / NFA)
- [ ] If US persons involved: NFA registration as CTA/CPO
- [ ] CFTC Part 4 exemptions may apply for <15 clients
- [ ] For personal use: no registration needed
- [ ] Never guarantee returns in any marketing material

### General
- [ ] Full audit trail: every signal, every trade, every decision logged
- [ ] No market manipulation (position sizing relative to market size)
- [ ] Risk disclosures on all client-facing material
- [ ] GDPR compliance for any user data stored
- [ ] Periodic performance reporting (if managing others' money)
- [ ] Backtesting disclaimer: past performance ≠ future results

---

## 13. Development Phases

### Phase 1 — Foundation (Weeks 1–4)
- [ ] Project scaffold (monorepo: `/core`, `/ea`, `/dashboard`)
- [ ] Supabase schema (signals, trades, events, positions, metrics)
- [ ] News ingestion pipeline (RSS + NewsAPI)
- [ ] MT5 EA skeleton with ZeroMQ PULL listener

### Phase 2 — Intelligence (Weeks 5–8)
- [ ] FinBERT sentiment pipeline
- [ ] NER entity extraction + country→currency mapping
- [ ] Economic calendar integration
- [ ] Social media listeners (Twitter, Reddit)

### Phase 3 — Technical Analysis (Weeks 9–12)
- [ ] Multi-timeframe TA engine
- [ ] Pattern recognition module
- [ ] Signal confluence scoring engine
- [ ] Signal backtesting (backtesting.py)

### Phase 4 — Risk Engine (Weeks 13–14)
- [ ] Position sizing calculator
- [ ] Portfolio correlation checks
- [ ] Drawdown circuit breakers
- [ ] News blackout scheduler

### Phase 5 — Dashboard (Weeks 15–18)
- [ ] Next.js terminal app scaffold
- [ ] Real-time WebSocket feed
- [ ] TradingView chart integration
- [ ] Signal feed + analytics pages

### Phase 6 — Backtesting & Go-Live (Weeks 19–24)
- [ ] MT5 Strategy Tester full backtest (5 years)
- [ ] Forward test on demo account (4 weeks)
- [ ] Performance review + parameter optimisation
- [ ] Compliance documentation
- [ ] Live deployment (demo first, then live)

---

## 14. Repository Structure

```
nvc-trading/
├── core/                         # Python engine
│   ├── ingestion/
│   │   ├── news_fetcher.py       # RSS + NewsAPI polling
│   │   ├── social_listener.py   # Twitter + Reddit
│   │   └── economic_calendar.py # ForexFactory + FRED
│   ├── sentiment/
│   │   ├── finbert_pipeline.py  # FinBERT sentiment scoring
│   │   ├── gpt_analyst.py       # GPT-4o for complex events
│   │   ├── ner_extractor.py     # spaCy NER + mapping
│   │   └── decay_weighting.py   # Time-decay scoring
│   ├── technical/
│   │   ├── indicator_engine.py  # ta-lib multi-timeframe
│   │   ├── pattern_detector.py  # Candlestick patterns
│   │   └── mtf_confluence.py    # Multi-timeframe logic
│   ├── signals/
│   │   ├── confluence_engine.py # Score aggregation
│   │   ├── signal_generator.py  # Final BUY/SELL decisions
│   │   └── blackout_manager.py  # News event blackouts
│   ├── risk/
│   │   ├── position_sizer.py    # Kelly Criterion
│   │   ├── portfolio_manager.py # Correlation + limits
│   │   └── circuit_breaker.py   # Drawdown stops
│   ├── bridge/
│   │   ├── zmq_publisher.py     # Signal → MT5
│   │   └── zmq_receiver.py      # Fill reports ← MT5
│   ├── api/
│   │   ├── main.py              # FastAPI app
│   │   ├── routes/              # REST + WebSocket endpoints
│   │   └── ws_manager.py        # WebSocket broadcast
│   └── db/
│       ├── supabase_client.py
│       └── models.py
│
├── ea/                           # MetaTrader 5 Expert Advisor
│   ├── NVC_Trader.mq5           # Main EA file
│   ├── ZMQ_Receiver.mqh         # ZeroMQ include
│   └── RiskManager.mqh          # MT5-side risk checks
│
├── dashboard/                    # Next.js terminal
│   ├── app/
│   │   ├── page.tsx             # Terminal home
│   │   ├── signals/page.tsx
│   │   ├── markets/page.tsx
│   │   ├── analytics/page.tsx
│   │   └── settings/page.tsx
│   ├── components/
│   │   ├── SignalTape.tsx        # Live signal feed
│   │   ├── PositionTable.tsx
│   │   ├── SentimentGauge.tsx
│   │   ├── EquityCurve.tsx       # TradingView chart
│   │   └── EconomicCalendar.tsx
│   └── lib/
│       ├── websocket.ts
│       └── api.ts
│
├── backtest/
│   ├── backtest_runner.py        # backtesting.py framework
│   ├── data_loader.py            # Historical price data
│   └── results/
│
├── compliance/
│   ├── trade_log_schema.md
│   ├── risk_disclosure.md
│   └── regulatory_checklist.md
│
├── docker-compose.yml            # Core engine + Redis + Postgres
├── .env.example
└── README.md
```

---

## 15. API Keys Required

| Service | Purpose | Cost |
|---------|---------|------|
| NewsAPI (Pro) | News articles | $449/mo |
| OpenAI (GPT-4o) | Complex analysis | Pay-per-use |
| Twitter/X API (Basic) | Social sentiment | $100/mo |
| Reddit API | Social sentiment | Free |
| Alpha Vantage (Premium) | Historical price data | $50/mo |
| FRED API | US macro data | Free |
| Supabase (Pro) | Database | $25/mo |
| Upstash Redis | Signal cache | $10/mo |
| Hostinger VPS | Python engine | ~$20/mo |
| Windows VPS (MT5) | EA hosting | ~$30/mo |

**Estimated running cost: ~$700–$1,000/month** (scalable down in development)

---

## 16. Key Differentiators vs Off-the-Shelf EAs

| Feature | Generic MT5 EA | NVC Trader |
|---------|---------------|------------|
| News awareness | None / basic filter | Real-time NLP on 15+ sources |
| Social sentiment | None | Twitter + Reddit + StockTwits |
| Signal reasoning | Black box | Full explanation per signal |
| Risk engine | Fixed lot size | Kelly Criterion + portfolio correlation |
| Geopolitical mapping | None | Country → Currency NER |
| Economic calendar | Basic filter | Full macro model integration |
| Dashboard | MT5 terminal only | Bloomberg-style web terminal |
| Backtesting | MT5 tester only | Python backtesting.py + MT5 |
| Multi-asset | Single pair | Forex + Commodities unified |

---

*New Vantage Co — Precision Intelligence for Modern Markets*
