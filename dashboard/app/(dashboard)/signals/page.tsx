'use client'

import { useEffect, useState, useMemo } from 'react'
import { Search, Copy, Check, Activity } from 'lucide-react'
import StatusBadge from '@/components/StatusBadge'
import EmptyState from '@/components/EmptyState'

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

const API = process.env.NEXT_PUBLIC_API_URL || 'https://nvc-trader.fly.dev'

const INSTRUMENTS = ['EURUSD','GBPUSD','USDJPY','XAUUSD','USOIL','USDCAD','AUDUSD','GBPJPY']

function ScoreBar({ score }: { score: number }) {
  const pct   = Math.round(score * 100)
  const color = score >= 0.75 ? '#10b981' : score >= 0.60 ? '#f59e0b' : '#475569'
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1.5 rounded-full" style={{ background: 'var(--border)' }}>
        <div className="h-full rounded-full transition-all duration-500"
             style={{ width: `${pct}%`, background: color }} />
      </div>
      <span className="font-mono text-xs w-8 text-right" style={{ color }}>{pct}%</span>
    </div>
  )
}

function SkeletonRow() {
  return (
    <tr className="border-b" style={{ borderColor: 'var(--border)' }}>
      {[80, 70, 50, 120, 40, 60, 160].map((w, i) => (
        <td key={i} className="px-4 py-2.5">
          <div className="skeleton" style={{ height: 12, width: w }} />
        </td>
      ))}
    </tr>
  )
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false)
  return (
    <button
      onClick={() => { navigator.clipboard.writeText(text); setCopied(true); setTimeout(() => setCopied(false), 1500) }}
      className="flex-shrink-0 opacity-40 hover:opacity-100 transition-opacity"
      style={{ color: 'var(--text-muted)' }}
      title="Copy"
    >
      {copied ? <Check size={11} style={{ color: 'var(--bull)' }} /> : <Copy size={11} />}
    </button>
  )
}

export default function SignalsPage() {
  const [signals,   setSignals]   = useState<Signal[]>([])
  const [loading,   setLoading]   = useState(true)
  const [selected,  setSelected]  = useState<Signal | null>(null)
  const [search,    setSearch]    = useState('')
  const [dirFilter, setDirFilter] = useState<'ALL' | 'BUY' | 'SELL'>('ALL')
  const [symFilter, setSymFilter] = useState('ALL')
  const [statusFilter, setStatusFilter] = useState<'ALL' | 'FILLED' | 'PENDING'>('ALL')

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

  const filtered = useMemo(() => signals.filter(s => {
    if (dirFilter !== 'ALL' && s.direction !== dirFilter) return false
    if (symFilter !== 'ALL' && s.instrument !== symFilter) return false
    if (statusFilter === 'FILLED' && s.fill?.status !== 'FILLED') return false
    if (statusFilter === 'PENDING' && s.fill?.status === 'FILLED') return false
    if (search) {
      const q = search.toLowerCase()
      return s.instrument.toLowerCase().includes(q) || s.reason?.toLowerCase().includes(q)
    }
    return true
  }), [signals, dirFilter, symFilter, statusFilter, search])

  return (
    <div className="flex flex-col h-full overflow-hidden" style={{ background: 'var(--bg-base)' }}>

      {/* Header */}
      <div className="px-6 py-3 border-b flex items-center justify-between flex-shrink-0"
           style={{ borderColor: 'var(--border)', background: 'var(--bg-surface)' }}>
        <div>
          <h1 className="font-semibold text-sm" style={{ color: 'var(--text-primary)' }}>Signal History</h1>
          <p className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>All Claude-generated trade signals</p>
        </div>
        <span className="font-mono text-xs px-2 py-1 rounded"
              style={{ background: 'var(--bg-elevated)', color: 'var(--text-secondary)' }}>
          {filtered.length} / {signals.length}
        </span>
      </div>

      {/* Filter bar */}
      <div className="px-4 py-2 border-b flex items-center gap-2 flex-shrink-0 flex-wrap"
           style={{ borderColor: 'var(--border)', background: 'var(--bg-surface)' }}>

        {/* Search */}
        <div className="flex items-center gap-1.5 px-2 py-1 rounded flex-1 min-w-32 max-w-48"
             style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border)' }}>
          <Search size={11} style={{ color: 'var(--text-muted)' }} />
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search…"
            className="bg-transparent outline-none text-xs flex-1"
            style={{ color: 'var(--text-primary)', fontFamily: 'var(--font-mono)' }}
          />
        </div>

        {/* Direction chips */}
        {(['ALL','BUY','SELL'] as const).map(d => (
          <button key={d} onClick={() => setDirFilter(d)}
            className="px-2.5 py-1 rounded text-xs font-mono font-semibold transition-all"
            style={{
              background: dirFilter === d
                ? d === 'BUY' ? 'rgba(16,185,129,0.2)' : d === 'SELL' ? 'rgba(239,68,68,0.2)' : 'var(--bg-elevated)'
                : 'transparent',
              color: dirFilter === d
                ? d === 'BUY' ? 'var(--bull)' : d === 'SELL' ? 'var(--bear)' : 'var(--text-primary)'
                : 'var(--text-muted)',
              border: `1px solid ${dirFilter === d ? 'var(--border-bright)' : 'transparent'}`,
            }}>
            {d}
          </button>
        ))}

        <div className="w-px h-4" style={{ background: 'var(--border)' }} />

        {/* Symbol filter */}
        <select
          value={symFilter}
          onChange={e => setSymFilter(e.target.value)}
          className="text-xs font-mono px-2 py-1 rounded outline-none"
          style={{
            background: 'var(--bg-elevated)', color: 'var(--text-secondary)',
            border: '1px solid var(--border)',
          }}>
          <option value="ALL">All Instruments</option>
          {INSTRUMENTS.map(s => <option key={s} value={s}>{s}</option>)}
        </select>

        {/* Status filter */}
        {(['ALL','FILLED','PENDING'] as const).map(st => (
          <button key={st} onClick={() => setStatusFilter(st)}
            className="px-2.5 py-1 rounded text-xs font-mono transition-all"
            style={{
              background: statusFilter === st ? 'var(--bg-elevated)' : 'transparent',
              color: statusFilter === st ? 'var(--text-primary)' : 'var(--text-muted)',
              border: `1px solid ${statusFilter === st ? 'var(--border-bright)' : 'transparent'}`,
            }}>
            {st}
          </button>
        ))}
      </div>

      <div className="flex flex-1 overflow-hidden">
        {/* Signal table */}
        <div className="flex-1 overflow-auto">
          <table className="w-full text-xs font-mono">
            <thead className="sticky top-0 z-10" style={{ background: 'var(--bg-base)' }}>
              <tr style={{ borderBottom: '1px solid var(--border)', color: 'var(--text-muted)' }}>
                <th className="text-left px-4 py-2">Time</th>
                <th className="text-left px-4 py-2">Instrument</th>
                <th className="text-left px-4 py-2">Dir</th>
                <th className="px-4 py-2 w-36">Score</th>
                <th className="text-right px-4 py-2">Lots</th>
                <th className="text-left px-4 py-2">Status</th>
                <th className="text-left px-4 py-2">Reason</th>
              </tr>
            </thead>
            <tbody>
              {loading
                ? [...Array(10)].map((_, i) => <SkeletonRow key={i} />)
                : filtered.map(s => (
                  <tr
                    key={s.id}
                    onClick={() => setSelected(prev => prev?.id === s.id ? null : s)}
                    className="cursor-pointer border-b hover:bg-opacity-50 transition-colors"
                    style={{
                      borderColor: 'var(--border)',
                      background: selected?.id === s.id ? 'var(--bg-elevated)' : 'transparent',
                    }}
                  >
                    <td className="px-4 py-2" style={{ color: 'var(--text-muted)' }}>
                      {s.created_at?.slice(11, 19)}
                      <span className="ml-1 text-xs opacity-50">{s.created_at?.slice(0, 10)}</span>
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
                      {s.fill?.status
                        ? <StatusBadge status={s.fill.status} />
                        : <span style={{ color: 'var(--text-muted)' }}>—</span>}
                    </td>
                    <td className="px-4 py-2 truncate max-w-xs" style={{ color: 'var(--text-muted)' }}>
                      {s.reason?.slice(0, 70)}
                    </td>
                  </tr>
                ))
              }
            </tbody>
          </table>
          {!loading && filtered.length === 0 && (
            <EmptyState
              icon={Activity}
              title="No signals found"
              body={signals.length > 0 ? 'No signals match your current filters.' : 'Agent hasn\'t generated any signals yet. Signals appear after the first cycle.'}
              compact
            />
          )}
        </div>

        {/* Detail panel */}
        {selected && (
          <div className="w-88 flex-shrink-0 border-l overflow-auto"
               style={{ borderColor: 'var(--border)', background: 'var(--bg-surface)', width: 340 }}>
            <div className="px-4 py-3 border-b flex items-center justify-between sticky top-0"
                 style={{ borderColor: 'var(--border)', background: 'var(--bg-surface)' }}>
              <span className="text-xs font-semibold tracking-wider uppercase"
                    style={{ color: 'var(--text-secondary)' }}>Signal Detail</span>
              <button onClick={() => setSelected(null)}
                      style={{ color: 'var(--text-muted)' }}
                      className="hover:opacity-70 transition-opacity">✕</button>
            </div>

            <div className="p-4 flex flex-col gap-4">
              {/* Key metrics */}
              <div className="grid grid-cols-2 gap-2">
                {[
                  { k: 'Instrument', v: selected.instrument, bold: true },
                  { k: 'Direction',  v: selected.direction,
                    color: selected.direction === 'BUY' ? 'var(--bull)' : 'var(--bear)' },
                  { k: 'Score',      v: `${(selected.score * 100).toFixed(1)}%`,
                    color: selected.score >= 0.75 ? 'var(--bull)' : selected.score >= 0.6 ? 'var(--accent)' : 'var(--bear)' },
                  { k: 'Lot Size',   v: String(selected.lot_size) },
                  { k: 'Fill Price', v: selected.fill?.fill_price?.toFixed(5) || '—' },
                ].map(({ k, v, color, bold }) => (
                  <div key={k} className="p-2 rounded"
                       style={{ background: 'var(--bg-elevated)' }}>
                    <div className="text-xs mb-0.5" style={{ color: 'var(--text-muted)' }}>{k}</div>
                    <div className="text-xs font-mono font-semibold"
                         style={{ color: color || (bold ? 'var(--text-primary)' : 'var(--text-secondary)') }}>
                      {v}
                    </div>
                  </div>
                ))}
                {/* Status badge as its own cell */}
                <div className="p-2 rounded" style={{ background: 'var(--bg-elevated)' }}>
                  <div className="text-xs mb-1" style={{ color: 'var(--text-muted)' }}>Status</div>
                  {selected.fill?.status
                    ? <StatusBadge status={selected.fill.status} />
                    : <span className="text-xs font-mono" style={{ color: 'var(--text-muted)' }}>—</span>}
                </div>
              </div>

              {/* Signal ID */}
              <div>
                <div className="text-xs mb-1" style={{ color: 'var(--text-muted)' }}>Signal ID</div>
                <div className="flex items-center gap-1.5">
                  <code className="text-xs font-mono truncate" style={{ color: 'var(--text-muted)' }}>
                    {selected.signal_id || selected.id}
                  </code>
                  <CopyButton text={selected.signal_id || selected.id} />
                </div>
              </div>

              {/* Time */}
              <div>
                <div className="text-xs mb-0.5" style={{ color: 'var(--text-muted)' }}>Generated at</div>
                <div className="text-xs font-mono" style={{ color: 'var(--text-secondary)' }}>
                  {selected.created_at?.replace('T', ' ').slice(0, 19)} UTC
                </div>
              </div>

              {/* Reasoning */}
              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <div className="text-xs font-semibold tracking-wider uppercase"
                       style={{ color: 'var(--text-muted)' }}>Claude Reasoning</div>
                  {selected.reason && <CopyButton text={selected.reason} />}
                </div>
                <pre
                  className="text-xs leading-relaxed p-3 rounded overflow-auto"
                  style={{
                    background:  'var(--bg-elevated)',
                    color:       'var(--text-secondary)',
                    border:      '1px solid var(--border)',
                    borderLeft:  '2px solid var(--accent)',
                    fontFamily:  'var(--font-mono)',
                    whiteSpace:  'pre-wrap',
                    wordBreak:   'break-word',
                    maxHeight:   280,
                  }}
                >
                  {selected.reason || 'No reasoning logged for this signal.'}
                </pre>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
