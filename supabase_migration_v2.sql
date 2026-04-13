-- NVC Trader — Schema Migration v2
-- Run this in the Supabase SQL editor (Dashboard → SQL Editor → New Query)
-- Safe to run multiple times (uses IF NOT EXISTS / IF column not exists pattern)

-- ─── agent_cycles: add missing columns ────────────────────────────────────────
alter table agent_cycles
  add column if not exists tool_calls     jsonb,
  add column if not exists summary        text,
  add column if not exists circuit_breaker jsonb;

-- ─── account_snapshots: add missing columns ────────────────────────────────────
alter table account_snapshots
  add column if not exists timestamp       timestamptz default now(),
  add column if not exists margin_used     numeric(12,2),
  add column if not exists free_margin     numeric(12,2),
  add column if not exists unrealised_pl   numeric(12,2),
  add column if not exists system_status   text,
  add column if not exists daily_drawdown  numeric(5,3),
  add column if not exists weekly_drawdown numeric(5,3),
  add column if not exists monthly_drawdown numeric(5,3);

-- ─── news_events: add missing columns ─────────────────────────────────────────
alter table news_events
  add column if not exists weight     numeric(4,3) default 0.75,
  add column if not exists fetched_at timestamptz  default now();

-- ─── trades: relax status constraint to allow 'modified' ──────────────────────
alter table trades drop constraint if exists trades_status_check;
alter table trades
  add constraint trades_status_check
  check (status in ('open', 'closed', 'cancelled', 'modified'));

-- ─── trades: add missing columns for close/modify logging ─────────────────────
alter table trades
  add column if not exists close_reason  text,
  add column if not exists close_result  text,
  add column if not exists modify_reason text;

-- ─── Additional indexes ────────────────────────────────────────────────────────
create index if not exists idx_account_snapshots_ts on account_snapshots(timestamp desc);
create index if not exists idx_news_fetched on news_events(fetched_at desc);
create index if not exists idx_cycles_cycle_id on agent_cycles(cycle_id);
