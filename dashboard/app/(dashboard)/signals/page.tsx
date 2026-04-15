'use client'

import { useEffect, useState, useMemo, useCallback } from 'react'
import { Search, Copy, Check, Activity, ChevronDown, ChevronUp, Wifi, WifiOff } from 'lucide-react'
import StatusBadge from '@/components/StatusBadge'
import EmptyState from '@/components/EmptyState'
import { useRealtimeTrades, type SignalChange } from '@/lib/hooks/useRealtimeTrades'
import { api } from '@/lib/api'

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

const PAGE_SIZE = 30

export default function SignalsPage() {
  const [signals,      setSignals]      = useState<Signal[]>([])
  const [loading,      setLoading]      = useState(true)
  const [loadingMore,  setLoadingMore]  = useState(false)
  const [hasMore,      setHasMore]      = useState(true)
  const [offset,       setOffset]       = useState(0)
  const [expanded,     setExpanded]     = useState<Set<string>>(new Set())
  const [search,       setSearch]       = useState('')
  const [dirFilter,    setDirFilter]    = useState<'ALL' | 'BUY' | 'SELL'>('ALL')
  const [symFilter,    setSymFilter]    = useState('ALL')
  const [statusFilter, setStatusFilter] = useState<'ALL' | 'FILLED' | 'PENDING'>('ALL')

  // ── Supabase Realtime — live signal/fill updates ──────────────────────────
  const { isConnected: rtConnected } = useRealtimeTrades({
    onSignal: useCallback((change: SignalChange) => {
      if (change.eventType === 'INSERT') {
        setSignals(prev => [change.new as unknown as Signal, ...prev].slice(0, 200))
      } else if (change.eventType === 'UPDATE') {
        setSignals(prev => prev.map(s =>
          s.id === change.new.id ? { ...s, ...(change.new as unknown as Signal) } : s
        ))
      }
    }, []),
  })

  // ── Initial load ─────────────────────────────────────────────────────────
  useEffect(() => {
    api.get<{ signals?: Signal[] }>(`/signals?limit=${PAGE_SIZE}&offset=0`)
      .then(d => {
        const rows = d.signals || []
        setSignals(rows)
        setOffset(rows.length)
        setHasMore(rows.length === PAGE_SIZE)
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  // ── Polling fallback (slower when Realtime is connected) ──────────────────
  useEffect(() => {
    const interval = rtConnected ? 5 * 60_000 : 15_000
    const t = setInterval(() => {
      api.get<{ signals?: Signal[] }>(`/signals?limit=${PAGE_SIZE}&offset=0`)
        .then(d => {
          const rows = d.signals || []
          setSignals(prev => {
            const ids = new Set(prev.map(s => s.id))
            const fresh = rows.filter((s: Signal) => !ids.has(s.id))
            return [...fresh, ...prev]
          })
        })
        .catch(() => {})
    }, interval)
    return () => clearInterval(t)
  }, [rtConnected])

  // ── Load more ──────────────────────────────────────────────────────────────
  const loadMore = useCallback(async () => {
    if (loadingMore || !hasMore) return
    setLoadingMore(true)
    try {
      const d = await api.get<{ signals?: Signal[] }>(`/signals?limit=${PAGE_SIZE}&offset=${offset}`)
      const rows: Signal[] = d.signals || []
      setSignals(prev => {
        const ids = new Set(prev.map(s => s.id))
        return [...prev, ...rows.filter(s => !ids.has(s.id))]
      })
      setOffset(prev => prev + rows.length)
      setHasMore(rows.length === PAGE_SIZE)
    } catch { /* silent */ }
    finally { setLoadingMore(false) }
  }, [offset, hasMore, loadingMore])

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
        <div className="flex items-center gap-2">
          {/* Realtime connection indicator */}
          <span
            className="flex items-center gap-1.5 text-[10px] font-mono px-2 py-1 rounded"
            style={{
              background: 'var(--bg-elevated)',
              color:      rtConnected ? 'var(--bull)' : 'var(--text-muted)',
              border:     `1px solid ${rtConnected ? 'rgba(46,168,74,0.3)' : 'var(--border)'}`,
            }}
            title={rtConnected ? 'Supabase Realtime connected — signals stream live' : 'Polling every 15s'}
          >
            {rtConnected
              ? <><span className="w-1.5 h-1.5 rounded-full animate-pulse" style={{ background: 'var(--bull)' }} /> LIVE</>
              : <><WifiOff size={10} /> POLL</>
            }
          </span>
          <span className="font-mono text-xs px-2 py-1 rounded"
                style={{ background: 'var(--bg-elevated)', color: 'var(--text-secondary)' }}>
            {filtered.length} / {signals.length}
          </span>
        </div>
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

      <div className="flex-1 overflow-auto">
        <div>
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
                : filtered.map(s => {
                  const isOpen = expanded.has(s.id)
                  const toggle = () => setExpanded(prev => {
                    const next = new Set(prev)
                    isOpen ? next.delete(s.id) : next.add(s.id)
                    return next
                  })
                  return (
                    <>
                      <tr
                        key={s.id}
                        onClick={toggle}
                        className="cursor-pointer border-b hover:bg-opacity-50 transition-colors"
                        style={{
                          borderColor: 'var(--border)',
                          background:  isOpen ? 'var(--bg-elevated)' : 'transparent',
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
                          <span className="flex items-center gap-1.5">
                            <span className="truncate">{s.reason?.slice(0, 60)}{s.reason && s.reason.length > 60 ? '…' : ''}</span>
                            {isOpen
                              ? <ChevronUp size={11} className="flex-shrink-0" style={{ color: 'var(--accent)' }} />
                              : <ChevronDown size={11} className="flex-shrink-0" style={{ color: 'var(--text-muted)' }} />}
                          </span>
                        </td>
                      </tr>

                      {/* Expanded reasoning row */}
                      {isOpen && (
                        <tr key={`${s.id}-exp`} style={{ background: 'var(--bg-elevated)' }}>
                          <td colSpan={7} className="px-6 pb-4 pt-2">
                            <div className="flex items-center justify-between mb-2">
                              <span className="text-[10px] font-semibold tracking-wider uppercase"
                                    style={{ color: 'var(--text-muted)' }}>
                                Claude Reasoning · {s.instrument} · {s.created_at?.slice(0,19).replace('T',' ')} UTC
                              </span>
                              <div className="flex items-center gap-2">
                                <span className="text-[10px] font-mono" style={{ color: 'var(--text-muted)' }}>
                                  Score: {(s.score * 100).toFixed(1)}% · Lots: {s.lot_size}
                                  {s.fill?.fill_price ? ` · Fill: ${s.fill.fill_price.toFixed(5)}` : ''}
                                </span>
                                {s.reason && <CopyButton text={s.reason} />}
                              </div>
                            </div>
                            <pre
                              className="text-xs leading-relaxed p-3 rounded overflow-auto"
                              style={{
                                background:  'var(--bg-base)',
                                color:       'var(--text-secondary)',
                                border:      '1px solid var(--border)',
                                borderLeft:  '2px solid var(--accent)',
                                fontFamily:  'var(--font-mono)',
                                whiteSpace:  'pre-wrap',
                                wordBreak:   'break-word',
                                maxHeight:   240,
                              }}
                            >
                              {s.reason || 'No reasoning logged for this signal.'}
                            </pre>
                          </td>
                        </tr>
                      )}
                    </>
                  )
                })
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

          {/* Load more */}
          {!loading && hasMore && filtered.length > 0 && (
            <div className="flex justify-center py-4">
              <button
                onClick={loadMore}
                disabled={loadingMore}
                className="flex items-center gap-2 px-4 py-2 rounded text-xs font-mono font-semibold transition-opacity disabled:opacity-50"
                style={{
                  background: 'var(--bg-elevated)',
                  color:      'var(--text-secondary)',
                  border:     '1px solid var(--border)',
                }}
              >
                {loadingMore ? (
                  <><span className="animate-spin">⟳</span> Loading…</>
                ) : (
                  <>Load more · {signals.length} loaded</>
                )}
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
