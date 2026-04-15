'use client'

import { useEffect, useState, useCallback } from 'react'
import { RefreshCw, Calendar } from 'lucide-react'
import EmptyState from '@/components/EmptyState'
import { api, silentFetch } from '@/lib/api'

const WATCHLIST = ['EURUSD','GBPUSD','USDJPY','AUDUSD','USDCAD','NZDUSD','USDCHF','EURJPY','GBPJPY','XAUUSD','XAGUSD','USOIL','UKOIL','NATGAS']

interface SentimentData {
  score: number
  bias: string
  article_count: number
  normalised: number
}

interface CalEvent {
  impact: string
  currency: string
  title: string
  time: string
  forecast?: string
  previous?: string
}

function SentBar({ score }: { score: number }) {
  const pct  = Math.abs(score) * 100
  const bull = score > 0
  const color = bull ? 'var(--bull)' : 'var(--bear)'
  return (
    <div className="flex items-center gap-1 w-full">
      <div className="flex-1 flex justify-end">
        {!bull && <div className="h-2 rounded-l transition-all duration-500" style={{ width: `${pct}%`, background: color }} />}
      </div>
      <div className="w-px h-3 flex-shrink-0" style={{ background: 'var(--border-bright)' }} />
      <div className="flex-1">
        {bull && <div className="h-2 rounded-r transition-all duration-500" style={{ width: `${pct}%`, background: color }} />}
      </div>
    </div>
  )
}

function SkeletonSentRow() {
  return (
    <tr className="border-b" style={{ borderColor: 'var(--border)' }}>
      <td className="py-2 pr-6"><div className="skeleton" style={{ width: 70, height: 12 }} /></td>
      <td className="py-2 px-2"><div className="skeleton" style={{ width: '100%', height: 8 }} /></td>
      <td className="py-2 px-4"><div className="skeleton" style={{ width: 30, height: 12 }} /></td>
      <td className="py-2 px-4"><div className="skeleton" style={{ width: 50, height: 12 }} /></td>
      <td className="py-2 px-4"><div className="skeleton" style={{ width: 20, height: 12 }} /></td>
    </tr>
  )
}

export default function MarketsPage() {
  const [sentiments,    setSentiments]    = useState<Record<string, SentimentData>>({})
  const [calendar,      setCalendar]      = useState<{ events: CalEvent[]; blackouts: unknown[] }>({ events: [], blackouts: [] })
  const [loadingSent,   setLoadingSent]   = useState(true)
  const [loadingCal,    setLoadingCal]    = useState(true)
  const [refreshingSent, setRefreshingSent] = useState(false)
  const [refreshingCal,  setRefreshingCal]  = useState(false)
  const [lastSentRefresh, setLastSentRefresh] = useState<Date | null>(null)

  const fetchSentiments = useCallback(async (silent = false) => {
    if (silent) setRefreshingSent(true)
    const results: Record<string, SentimentData> = {}
    await Promise.allSettled(
      WATCHLIST.map(async sym => {
        const d = await silentFetch<SentimentData>(`/sentiment/${sym}`)
        if (d) results[sym] = d
      })
    )
    setSentiments(results)
    setLoadingSent(false)
    setRefreshingSent(false)
    setLastSentRefresh(new Date())
  }, [])

  const fetchCalendar = useCallback(async (silent = false) => {
    if (silent) setRefreshingCal(true)
    try {
      const d = await api.get<{ events: CalEvent[]; blackouts: unknown[] }>('/calendar?hours=24')
      setCalendar(d)
    } catch {}
    setLoadingCal(false)
    setRefreshingCal(false)
  }, [])

  useEffect(() => {
    fetchSentiments()
    fetchCalendar()
    // Sentiment auto-refreshes every 60s, calendar every 5min
    const t1 = setInterval(() => fetchSentiments(true), 60_000)
    const t2 = setInterval(() => fetchCalendar(true), 300_000)
    return () => { clearInterval(t1); clearInterval(t2) }
  }, [fetchSentiments, fetchCalendar])

  return (
    <div className="flex flex-col h-full overflow-hidden" style={{ background: 'var(--bg-base)' }}>

      {/* Header */}
      <div className="px-6 py-3 border-b flex items-center justify-between flex-shrink-0"
           style={{ borderColor: 'var(--border)', background: 'var(--bg-surface)' }}>
        <div>
          <h1 className="font-semibold text-sm" style={{ color: 'var(--text-primary)' }}>Markets</h1>
          <p className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>
            Live sentiment · 14 instruments · FinBERT + NewsAPI
          </p>
        </div>
        <div className="flex items-center gap-2">
          {lastSentRefresh && (
            <span className="text-xs font-mono" style={{ color: 'var(--text-muted)' }}>
              {lastSentRefresh.toLocaleTimeString()}
            </span>
          )}
          <button
            onClick={() => fetchSentiments(true)}
            disabled={refreshingSent}
            className="flex items-center gap-1.5 px-2.5 py-1.5 rounded text-xs transition-opacity disabled:opacity-40"
            style={{ background: 'var(--bg-elevated)', color: 'var(--text-secondary)', border: '1px solid var(--border)' }}
            aria-label="Refresh sentiment data"
          >
            <RefreshCw size={11} className={refreshingSent ? 'animate-spin' : ''} />
            Refresh
          </button>
        </div>
      </div>

      <div className="flex flex-1 overflow-hidden">

        {/* Sentiment table */}
        <div className="flex-1 overflow-auto p-6">
          <div className="text-xs font-semibold tracking-wider mb-3 uppercase"
               style={{ color: 'var(--text-muted)' }}>
            Sentiment Radar · last 4h · FinBERT
          </div>

          <table className="w-full text-xs font-mono">
            <thead className="sticky top-0" style={{ background: 'var(--bg-base)' }}>
              <tr style={{ color: 'var(--text-muted)', borderBottom: '1px solid var(--border)' }}>
                <th className="text-left py-2 pr-6">Instrument</th>
                <th className="py-2 w-48 text-center">◀ BEAR &nbsp; | &nbsp; BULL ▶</th>
                <th className="py-2 px-4 text-right">Score</th>
                <th className="py-2 px-4 text-left">Bias</th>
                <th className="py-2 px-4 text-right">Articles</th>
              </tr>
            </thead>
            <tbody>
              {loadingSent
                ? WATCHLIST.map(sym => <SkeletonSentRow key={sym} />)
                : WATCHLIST.map(sym => {
                  const d     = sentiments[sym]
                  const score = d?.score ?? 0
                  const bias  = d?.bias  ?? 'neutral'
                  const color = bias === 'bullish' ? 'var(--bull)' : bias === 'bearish' ? 'var(--bear)' : 'var(--neutral)'
                  return (
                    <tr key={sym} className="border-b" style={{ borderColor: 'var(--border)' }}>
                      <td className="py-2 pr-6 font-semibold" style={{ color: 'var(--text-primary)' }}>{sym}</td>
                      <td className="py-2 px-2">
                        {d ? <SentBar score={score} /> : <span style={{ color: 'var(--text-muted)' }}>—</span>}
                      </td>
                      <td className="py-2 px-4 text-right font-bold" style={{ color }}>
                        {score >= 0 ? '+' : ''}{(score * 100).toFixed(0)}
                      </td>
                      <td className="py-2 px-4 uppercase text-xs font-semibold tracking-wider" style={{ color }}>
                        {bias}
                      </td>
                      <td className="py-2 px-4 text-right" style={{ color: 'var(--text-muted)' }}>
                        {d?.article_count ?? '—'}
                      </td>
                    </tr>
                  )
                })
              }
            </tbody>
          </table>
        </div>

        {/* Calendar sidebar */}
        <div className="w-72 flex-shrink-0 border-l flex flex-col"
             style={{ borderColor: 'var(--border)', background: 'var(--bg-surface)' }}>
          <div className="px-4 py-3 border-b flex items-center justify-between flex-shrink-0"
               style={{ borderColor: 'var(--border)' }}>
            <span className="text-xs font-semibold tracking-wider uppercase"
                  style={{ color: 'var(--text-muted)' }}>
              Economic Calendar · 24h
            </span>
            <button
              onClick={() => fetchCalendar(true)}
              disabled={refreshingCal}
              className="opacity-60 hover:opacity-100 transition-opacity disabled:opacity-30"
              aria-label="Refresh calendar"
            >
              <RefreshCw size={11} style={{ color: 'var(--text-muted)' }}
                         className={refreshingCal ? 'animate-spin' : ''} />
            </button>
          </div>

          <div className="flex-1 overflow-auto p-3">
            {loadingCal ? (
              <div className="flex flex-col gap-2">
                {[...Array(5)].map((_, i) => (
                  <div key={i} className="p-2 rounded border"
                       style={{ borderColor: 'var(--border)', background: 'var(--bg-elevated)' }}>
                    <div className="skeleton mb-1.5" style={{ width: 40, height: 10 }} />
                    <div className="skeleton" style={{ width: '80%', height: 10 }} />
                  </div>
                ))}
              </div>
            ) : calendar.events.length === 0 ? (
              <EmptyState
                icon={Calendar}
                title="No events"
                body="No high-impact events in the next 24 hours."
                compact
              />
            ) : (
              calendar.events.map((e, i) => {
                const impactColor = e.impact === 'high' ? 'var(--bear)' : e.impact === 'medium' ? 'var(--accent)' : 'var(--text-muted)'
                return (
                  <div key={i} className="p-2 rounded border mb-2 font-mono text-xs"
                       style={{ borderColor: impactColor, background: 'var(--bg-elevated)' }}>
                    <div className="flex justify-between mb-1">
                      <span className="font-bold" style={{ color: impactColor }}>{e.currency}</span>
                      <span style={{ color: 'var(--text-muted)' }}>
                        {new Date(e.time).toLocaleTimeString('en', { hour: '2-digit', minute: '2-digit' })} UTC
                      </span>
                    </div>
                    <div style={{ color: 'var(--text-secondary)' }} className="truncate">{e.title}</div>
                    {(e.forecast || e.previous) && (
                      <div className="flex gap-3 mt-1" style={{ color: 'var(--text-muted)' }}>
                        {e.forecast && <span>F: {e.forecast}</span>}
                        {e.previous && <span>P: {e.previous}</span>}
                      </div>
                    )}
                  </div>
                )
              })
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
