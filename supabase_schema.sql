-- NVC Trader — Supabase Database Schema
-- Run this in the Supabase SQL editor

-- ─── Signals ──────────────────────────────────────────────────────────────────
create table if not exists signals (
  id            uuid primary key default gen_random_uuid(),
  signal_id     text unique not null,
  instrument    text not null,
  direction     text not null check (direction in ('BUY', 'SELL')),
  entry_type    text default 'MARKET',
  stop_loss     numeric(10,5),
  take_profit   numeric(10,5),
  lot_size      numeric(8,2),
  score         numeric(4,3),
  reason        text,
  agent         text default 'claude-vantage',
  fill          jsonb,
  created_at    timestamptz default now()
);

-- ─── Trades (filled positions) ────────────────────────────────────────────────
create table if not exists trades (
  id            uuid primary key default gen_random_uuid(),
  ticket        bigint unique,
  signal_id     text references signals(signal_id),
  instrument    text not null,
  direction     text not null,
  lot_size      numeric(8,2),
  entry_price   numeric(10,5),
  exit_price    numeric(10,5),
  stop_loss     numeric(10,5),
  take_profit   numeric(10,5),
  pnl           numeric(10,2),
  pnl_pips      numeric(8,1),
  status        text default 'open' check (status in ('open', 'closed', 'cancelled')),
  opened_at     timestamptz,
  closed_at     timestamptz,
  created_at    timestamptz default now()
);

-- ─── Agent Cycles ─────────────────────────────────────────────────────────────
create table if not exists agent_cycles (
  id              uuid primary key default gen_random_uuid(),
  cycle_id        text unique not null,
  trigger         text,
  trades_executed integer default 0,
  trades          jsonb,
  message_count   integer,
  duration_ms     integer,
  timestamp       timestamptz default now()
);

-- ─── News Events ──────────────────────────────────────────────────────────────
create table if not exists news_events (
  id            uuid primary key default gen_random_uuid(),
  title         text not null,
  source        text,
  url           text,
  instruments   text[],            -- affected instruments
  sentiment     numeric(4,3),      -- -1.0 to +1.0
  sentiment_label text,
  impact        text,
  published_at  timestamptz,
  ingested_at   timestamptz default now()
);

-- ─── Account Snapshots ────────────────────────────────────────────────────────
create table if not exists account_snapshots (
  id                    uuid primary key default gen_random_uuid(),
  balance               numeric(12,2),
  equity                numeric(12,2),
  daily_drawdown_pct    numeric(5,3),
  weekly_drawdown_pct   numeric(5,3),
  monthly_drawdown_pct  numeric(5,3),
  open_trades           integer,
  snapshotted_at        timestamptz default now()
);

-- ─── Position Modifications ───────────────────────────────────────────────────
create table if not exists position_modifications (
  id        uuid primary key default gen_random_uuid(),
  ticket    bigint,
  new_sl    numeric(10,5),
  new_tp    numeric(10,5),
  reason    text,
  result    jsonb,
  created_at timestamptz default now()
);

create table if not exists position_closes (
  id        uuid primary key default gen_random_uuid(),
  ticket    bigint,
  reason    text,
  result    jsonb,
  created_at timestamptz default now()
);

-- ─── Indexes ──────────────────────────────────────────────────────────────────
create index if not exists idx_signals_instrument on signals(instrument);
create index if not exists idx_signals_created on signals(created_at desc);
create index if not exists idx_trades_instrument on trades(instrument);
create index if not exists idx_trades_status on trades(status);
create index if not exists idx_news_published on news_events(published_at desc);
create index if not exists idx_cycles_timestamp on agent_cycles(timestamp desc);

-- ─── RLS (Row Level Security — enable for production) ─────────────────────────
-- alter table signals enable row level security;
-- alter table trades enable row level security;
