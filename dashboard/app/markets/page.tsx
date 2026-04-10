'use client'

import { useEffect, useState } from 'react'
import Sidebar from '@/components/Sidebar'

const WATCHLIST = ['EURUSD','GBPUSD','USDJPY','AUDUSD','USDCAD','NZDUSD','USDCHF','EURJPY','GBPJPY','XAUUSD','XAGUSD','USOIL','UKOIL','NATGAS']
const API = process.env.NEXT_PUBLIC_API_URL || 'https://nvc-trader-engine.fly.dev'

interface SentimentData {
  score: number
  bias: string
  article_count: number
  normalised: number
}

function SentBar({ score }: { score: number }) {
  const pct   = Math.abs(score) * 100
  const bull  = score > 0
  const color = bull ? 'var(--bull)' : 'var(--bear)'
  return (
    <div className="flex items-center gap-1 w-full">
      <div className="flex-1 flex justify-end">
        {!bull && <div className="h-2 rounded-l" style={{ width: `${pct}%`, background: color }} />}
      </div>
      <div className="w-px h-3 flex-shrink-0" style={{ background: 'var(--border-bright)' }} />
      <div className="flex-1">
        {bull && <div className="h-2 rounded-r" style={{ width: `${pct}%`, background: color }} />}
      </div>
    </div>
  )
}

export default function MarketsPage() {
  const [sentiments, setSentiments] = useState<Record<string, SentimentData>>({})
  const [calendar, setCalendar]     = useState<{ events: unknown[]; blackouts: unknown[] }>({ events: [], blackouts: [] })

  useEffect(() => {
    async function fetchAll() {
      const results: Record<string, SentimentData> = {}
      await Promise.allSettled(
        WATCHLIST.map(async sym => {
          const r = await fetch(`${API}/sentiment/${sym}`)
          if (r.ok) results[sym] = await r.json()
        })
      )
      setSentiments(results)
    }
    fetchAll()
    const t = setInterval(fetchAll, 60_000)
    return () => clearInterval(t)
  }, [])

  useEffect(() => {
    fetch(`${API}/calendar?hours=24`)
      .then(r => r.json())
      .then(d => setCalendar(d))
      .catch(() => {})
  }, [])

  return (
    <div className="flex min-h-screen" style={{ background: 'var(--bg-base)' }}>
      <Sidebar />
      <div className="flex-1 flex flex-col overflow-hidden">
        <div className="px-6 py-4 border-b"
             style={{ borderColor: 'var(--border)', background: 'var(--bg-surface)' }}>
          <h1 className="font-semibold text-sm" style={{ color: 'var(--text-primary)' }}>Markets</h1>
          <p className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>Live sentiment radar · 14 instruments</p>
        </div>

        <div className="flex flex-1 overflow-hidden">
          {/* Sentiment table */}
          <div className="flex-1 overflow-auto p-6">
            <div className="text-xs font-semibold tracking-wider mb-3" style={{ color: 'var(--text-muted)' }}>
              SENTIMENT RADAR  ·  last 4 hours · FinBERT + News + Social
            </div>

            <table className="w-full text-xs font-mono">
              <thead>
                <tr style={{ color: 'var(--text-muted)', borderBottom: '1px solid var(--border)' }}>
                  <th className="text-left py-2 pr-6">Instrument</th>
                  <th className="py-2 w-48 text-center">◀ BEAR  |  BULL ▶</th>
                  <th className="py-2 px-4 text-right">Score</th>
                  <th className="py-2 px-4 text-left">Bias</th>
                  <th className="py-2 px-4 text-right">Articles</th>
                </tr>
              </thead>
              <tbody>
                {WATCHLIST.map(sym => {
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
                })}
              </tbody>
            </table>
          </div>

          {/* Calendar sidebar */}
          <div className="w-72 flex-shrink-0 border-l overflow-auto p-4"
               style={{ borderColor: 'var(--border)', background: 'var(--bg-surface)' }}>
            <div className="text-xs font-semibold tracking-wider mb-3"
                 style={{ color: 'var(--text-muted)' }}>ECONOMIC CALENDAR · 24H</div>

            {(calendar.events as Array<{ impact: string; currency: string; title: string; time: string; forecast?: string; previous?: string }>).map((e, i) => {
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
            })}
            {calendar.events.length === 0 && (
              <div style={{ color: 'var(--text-muted)' }} className="text-xs">No events in next 24h</div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
