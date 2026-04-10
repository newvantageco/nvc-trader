'use client'

import { useEffect, useState } from 'react'
import Sidebar from '@/components/Sidebar'

interface Signal {
  id: string
  signal_id: string
  instrument: string
  direction: 'BUY' | 'SELL'
  lot_size: number
  score: number
  reason: string
  fill: { status: string; fill_price: number } | null
  created_at: string
}

const API = process.env.NEXT_PUBLIC_API_URL || 'https://nvc-trader-engine.fly.dev'

function ScoreBar({ score }: { score: number }) {
  const pct   = Math.round(score * 100)
  const color = score >= 0.75 ? '#10b981' : score >= 0.60 ? '#f59e0b' : '#475569'
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1.5 rounded-full" style={{ background: 'var(--border)' }}>
        <div className="h-full rounded-full" style={{ width: `${pct}%`, background: color }} />
      </div>
      <span className="font-mono text-xs w-8 text-right" style={{ color }}>{pct}%</span>
    </div>
  )
}

export default function SignalsPage() {
  const [signals, setSignals]   = useState<Signal[]>([])
  const [loading, setLoading]   = useState(true)
  const [selected, setSelected] = useState<Signal | null>(null)

  useEffect(() => {
    fetch(`${API}/signals?limit=100`)
      .then(r => r.json())
      .then(d => { setSignals(d.signals || []); setLoading(false) })
      .catch(() => setLoading(false))

    const t = setInterval(() => {
      fetch(`${API}/signals?limit=100`)
        .then(r => r.json())
        .then(d => setSignals(d.signals || []))
        .catch(() => {})
    }, 15_000)
    return () => clearInterval(t)
  }, [])

  return (
    <div className="flex min-h-screen" style={{ background: 'var(--bg-base)' }}>
      <Sidebar />
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Header */}
        <div className="px-6 py-4 border-b flex items-center justify-between"
             style={{ borderColor: 'var(--border)', background: 'var(--bg-surface)' }}>
          <div>
            <h1 className="font-semibold text-sm" style={{ color: 'var(--text-primary)' }}>Signal History</h1>
            <p className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>All Claude-generated trade signals</p>
          </div>
          <span className="font-mono text-xs px-2 py-1 rounded"
                style={{ background: 'var(--bg-elevated)', color: 'var(--text-secondary)' }}>
            {signals.length} signals
          </span>
        </div>

        <div className="flex flex-1 overflow-hidden">
          {/* Signal list */}
          <div className="flex-1 overflow-auto">
            {loading && (
              <div className="p-6 text-xs" style={{ color: 'var(--text-muted)' }}>Loading...</div>
            )}
            <table className="w-full text-xs font-mono">
              <thead>
                <tr style={{ borderBottom: '1px solid var(--border)', color: 'var(--text-muted)' }}>
                  <th className="text-left px-4 py-2">Time</th>
                  <th className="text-left px-4 py-2">Instrument</th>
                  <th className="text-left px-4 py-2">Direction</th>
                  <th className="px-4 py-2 w-40">Score</th>
                  <th className="text-right px-4 py-2">Lots</th>
                  <th className="text-left px-4 py-2">Status</th>
                  <th className="text-left px-4 py-2">Reason</th>
                </tr>
              </thead>
              <tbody>
                {signals.map(s => (
                  <tr
                    key={s.id}
                    onClick={() => setSelected(s)}
                    className="cursor-pointer border-b"
                    style={{
                      borderColor: 'var(--border)',
                      background: selected?.id === s.id ? 'var(--bg-elevated)' : 'transparent',
                    }}
                  >
                    <td className="px-4 py-2" style={{ color: 'var(--text-muted)' }}>
                      {s.created_at?.slice(0, 19).replace('T', ' ')}
                    </td>
                    <td className="px-4 py-2 font-semibold" style={{ color: 'var(--text-primary)' }}>
                      {s.instrument}
                    </td>
                    <td className="px-4 py-2">
                      <span className="px-1.5 py-0.5 rounded text-xs font-bold"
                            style={{
                              background: s.direction === 'BUY' ? 'rgba(16,185,129,0.15)' : 'rgba(239,68,68,0.15)',
                              color: s.direction === 'BUY' ? 'var(--bull)' : 'var(--bear)',
                            }}>
                        {s.direction}
                      </span>
                    </td>
                    <td className="px-4 py-2">
                      <ScoreBar score={s.score} />
                    </td>
                    <td className="px-4 py-2 text-right" style={{ color: 'var(--text-secondary)' }}>
                      {s.lot_size}
                    </td>
                    <td className="px-4 py-2">
                      {s.fill?.status === 'FILLED'
                        ? <span style={{ color: 'var(--bull)' }}>✓ FILLED</span>
                        : <span style={{ color: 'var(--text-muted)' }}>{s.fill?.status || '—'}</span>}
                    </td>
                    <td className="px-4 py-2 truncate max-w-xs" style={{ color: 'var(--text-muted)' }}>
                      {s.reason?.slice(0, 70)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Detail panel */}
          {selected && (
            <div className="w-80 flex-shrink-0 border-l overflow-auto p-4"
                 style={{ borderColor: 'var(--border)', background: 'var(--bg-surface)' }}>
              <div className="flex items-center justify-between mb-4">
                <span className="text-xs font-semibold" style={{ color: 'var(--text-secondary)' }}>SIGNAL DETAIL</span>
                <button onClick={() => setSelected(null)} style={{ color: 'var(--text-muted)' }}>✕</button>
              </div>
              <div className="flex flex-col gap-3 text-xs font-mono">
                {[
                  ['Instrument', selected.instrument],
                  ['Direction',  selected.direction],
                  ['Score',      `${(selected.score * 100).toFixed(1)}%`],
                  ['Lot Size',   String(selected.lot_size)],
                  ['Fill Price', selected.fill?.fill_price?.toString() || '—'],
                  ['Status',     selected.fill?.status || '—'],
                  ['Signal ID',  selected.signal_id?.slice(0, 20) + '...'],
                ].map(([k, v]) => (
                  <div key={k}>
                    <div style={{ color: 'var(--text-muted)' }}>{k}</div>
                    <div style={{ color: 'var(--text-primary)' }}>{v}</div>
                  </div>
                ))}
                <div>
                  <div style={{ color: 'var(--text-muted)' }}>Claude Reasoning</div>
                  <div className="mt-1 p-2 rounded text-xs leading-relaxed"
                       style={{ background: 'var(--bg-elevated)', color: 'var(--text-secondary)' }}>
                    {selected.reason || 'No reasoning logged'}
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
