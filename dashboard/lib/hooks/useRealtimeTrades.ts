/**
 * useRealtimeTrades — Supabase Realtime hook for live trade/signal updates
 * =========================================================================
 *
 * Subscribes to INSERT and UPDATE events on the `signals` and `trades`
 * tables in Supabase. The dashboard gets pushed changes instantly instead
 * of polling every 15s.
 *
 * Adapted from SightSync's useRealtimeCalls.ts.
 *
 * Usage:
 *   const { isConnected, lastSignal } = useRealtimeTrades({ onSignal, onTrade })
 *
 * Requirements:
 *   NEXT_PUBLIC_SUPABASE_URL + NEXT_PUBLIC_SUPABASE_ANON_KEY must be set
 *   in Vercel env vars.
 *
 *   Realtime must be enabled on the tables in Supabase:
 *     ALTER PUBLICATION supabase_realtime ADD TABLE signals;
 *     ALTER PUBLICATION supabase_realtime ADD TABLE trades;
 *
 * If env vars are missing, the hook is a no-op (polling fallback in the
 * page components handles data fetching).
 */

'use client'

import { useEffect, useRef, useState, useCallback } from 'react'

// ── Types ─────────────────────────────────────────────────────────────────────

export type RealtimeEvent = 'INSERT' | 'UPDATE' | 'DELETE'

export interface SignalRow {
  id:          string
  signal_id?:  string
  instrument:  string
  direction:   'BUY' | 'SELL' | 'NEUTRAL'
  score:       number
  lot_size:    number
  reason?:     string
  created_at:  string
  fill?: { status?: string; fill_price?: number } | null
}

export interface TradeRow {
  id:          string
  instrument:  string
  direction:   string
  lot_size:    number
  status:      string
  pnl?:        number
  created_at:  string
}

export interface SignalChange {
  eventType:  RealtimeEvent
  old:        Partial<SignalRow> | null
  new:        SignalRow
  receivedAt: string
}

export interface TradeChange {
  eventType:  RealtimeEvent
  old:        Partial<TradeRow> | null
  new:        TradeRow
  receivedAt: string
}

export interface UseRealtimeTradesOptions {
  maxSignals?: number
  onSignal?:   (change: SignalChange) => void
  onTrade?:    (change: TradeChange) => void
}

export interface UseRealtimeTradesResult {
  isConnected: boolean
  lastSignal:  SignalChange | null
  lastTrade:   TradeChange | null
}

// ── Supabase payload type (mirrors what Supabase sends for postgres_changes) ──

interface SupabasePayload {
  eventType: 'INSERT' | 'UPDATE' | 'DELETE'
  old:       Record<string, unknown> | null
  new:       Record<string, unknown>
}

interface SupabaseClient {
  channel: (name: string) => SupabaseChannel
  removeChannel: (ch: SupabaseChannel) => void
}

interface SupabaseChannel {
  on: (event: string, filter: Record<string, unknown>, cb: (p: SupabasePayload) => void) => SupabaseChannel
  subscribe: (cb: (status: string) => void) => SupabaseChannel
}

// ── Supabase client singleton ─────────────────────────────────────────────────

let _client: SupabaseClient | null = null

function getClient() {
  if (_client) return _client
  const url  = process.env.NEXT_PUBLIC_SUPABASE_URL
  const anon = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY
  if (!url || !anon) return null   // no-op if env vars not set
  // Dynamic import to avoid bundling supabase unless env is configured
  const { createClient } = require('@supabase/supabase-js')
  _client = createClient(url, anon, {
    auth:     { persistSession: false },
    realtime: { params: { eventsPerSecond: 10 } },
  })
  return _client
}

// ── Hook ──────────────────────────────────────────────────────────────────────

export function useRealtimeTrades({
  onSignal,
  onTrade,
}: UseRealtimeTradesOptions = {}): UseRealtimeTradesResult {
  const [isConnected, setIsConnected] = useState(false)
  const [lastSignal,  setLastSignal]  = useState<SignalChange | null>(null)
  const [lastTrade,   setLastTrade]   = useState<TradeChange | null>(null)

  const onSignalRef = useRef(onSignal)
  const onTradeRef  = useRef(onTrade)
  onSignalRef.current = onSignal
  onTradeRef.current  = onTrade

  useEffect(() => {
    const supabase = getClient()
    if (!supabase) return  // env vars not set — silently no-op

    const channel = supabase
      .channel('nvc-trading-live')
      // ── Signals table ───────────────────────────────────────────────────
      .on(
        'postgres_changes',
        { event: '*', schema: 'public', table: 'signals' },
        (payload: SupabasePayload) => {
          const change: SignalChange = {
            eventType:  payload.eventType as RealtimeEvent,
            old:        payload.old as unknown as Partial<SignalRow> | null,
            new:        payload.new as unknown as SignalRow,
            receivedAt: new Date().toISOString(),
          }
          setLastSignal(change)
          onSignalRef.current?.(change)
        }
      )
      // ── Trades table ────────────────────────────────────────────────────
      .on(
        'postgres_changes',
        { event: '*', schema: 'public', table: 'trades' },
        (payload: SupabasePayload) => {
          const change: TradeChange = {
            eventType:  payload.eventType as RealtimeEvent,
            old:        payload.old as unknown as Partial<TradeRow> | null,
            new:        payload.new as unknown as TradeRow,
            receivedAt: new Date().toISOString(),
          }
          setLastTrade(change)
          onTradeRef.current?.(change)
        }
      )
      .subscribe((status: string) => {
        setIsConnected(status === 'SUBSCRIBED')
      })

    return () => {
      supabase.removeChannel(channel)
      setIsConnected(false)
    }
  }, [])

  return { isConnected, lastSignal, lastTrade }
}
