'use client'

import { useEffect, useState, useCallback } from 'react'
import { RefreshCw, TrendingUp, Download, Activity, BarChart3 } from 'lucide-react'
import dynamic from 'next/dynamic'
import EmptyState from '@/components/EmptyState'
import TradingCharts from '@/components/TradingCharts'

const EquityChart = dynamic(() => import('@/components/EquityChart'), { ssr: false })

const API = process.env.NEXT_PUBLIC_API_URL || 'https://nvc-trader.fly.dev'

interface Metrics {
  total_trades: number
  winning_trades: number
  losing_trades: number
  win_rate: number
  net_pnl_usd: number
  avg_win_usd: number
  avg_loss_usd: number
  profit_factor: number
  sharpe_ratio: number
  expectancy_per_trade: number
  max_consecutive_losses: number
  kelly_fraction: number
  recommended_risk_pct: number
  best_instrument: string | null
  worst_instrument: string | null
  assessment: string
  total_signals: number
  by_instrument: Record<string, { trades: number; total_pnl: number; win_rate: number; trade_count: number }>
}

interface Snapshot {
  timestamp: string
  equity: number
  balance: number
}

// ── Skeleton block ─────────────────────────────────────────────────────────────
function Skeleton({ w = '100%', h = 16 }: { w?: string | number; h?: number }) {
  return (
    <div className="skeleton" style={{ width: w, height: h }} />
  )
}

function StatCard({
  label, value, sub, color, loading,
}: {
  label: string; value: string; sub?: string; color?: string; loading?: boolean
}) {
  return (
    <div className="p-4 rounded border flex flex-col gap-1"
         style={{ borderColor: 'var(--border)', background: 'var(--bg-surface)' }}>
      <div className="text-xs tracking-wider" style={{ color: 'var(--text-muted)' }}>{label}</div>
      {loading
        ? <Skeleton h={24} w="60%" />
        : <div className="text-xl font-mono font-bold" style={{ color: color || 'var(--text-primary)' }}>{value}</div>
      }
      {sub && !loading && (
        <div className="text-xs" style={{ color: 'var(--text-muted)' }}>{sub}</div>
      )}
    </div>
  )
}

export default function AnalyticsPage() {
  const [metrics,   setMetrics]   = useState<Metrics | null>(null)
  const [snapshots, setSnapshots] = useState<Snapshot[]>([])
  const [cycles,    setCycles]    = useState<Array<{ cycle_id: string; timestamp: string; trades_executed: number; trigger: string }>>([])
  const [loading,   setLoading]   = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null)
  const [trades, setTrades] = useState<Array<Record<string, unknown>>>([])

  const exportCSV = useCallback(() => {
    if (!trades.length && !metrics) return
    const rows = trades.length ? trades : []
    const headers = rows.length
      ? Object.keys(rows[0])
      : ['instrument', 'direction', 'pnl', 'status', 'created_at']
    const csv = [
      headers.join(','),
      ...rows.map(r => headers.map(h => JSON.stringify(r[h] ?? '')).join(','))
    ].join('\n')
    const blob = new Blob([csv], { type: 'text/csv' })
    const url  = URL.createObjectURL(blob)
    const a    = document.createElement('a')
    a.href     = url
    a.download = `nvc-trades-${new Date().toISOString().slice(0,10)}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }, [trades, metrics])

  const loadData = useCallback(async (silent = false) => {
    if (!silent) setLoading(true)
    else setRefreshing(true)

    await Promise.allSettled([
      fetch(`${API}/analytics`)
        .then(r => r.ok ? r.json() : null)
        .then(d => { if (d) setMetrics(d) }),

      fetch(`${API}/account/snapshots?limit=168`)
        .then(r => r.ok ? r.json() : { snapshots: [] })
        .then(d => setSnapshots(d.snapshots || [])),

      fetch(`${API}/cycles?limit=50`)
        .then(r => r.ok ? r.json() : { cycles: [] })
        .then(d => setCycles(d.cycles || [])),

      fetch(`${API}/trades?limit=500`)
        .then(r => r.ok ? r.json() : { trades: [] })
        .then(d => setTrades(d.trades || []))
        .catch(() => {}),
    ])

    setLoading(false)
    setRefreshing(false)
    setLastRefresh(new Date())
  }, [])

  useEffect(() => { loadData() }, [loadData])

  const wr  = metrics?.win_rate ? (metrics.win_rate * 100).toFixed(1) : '—'
  const pf  = metrics?.profit_factor?.toFixed(2) ?? '—'
  const sr  = metrics?.sharpe_ratio?.toFixed(2) ?? '—'
  const exp = metrics?.expectancy_per_trade != null ? `$${metrics.expectancy_per_trade.toFixed(2)}` : '—'
  const kly = metrics?.kelly_fraction != null ? (metrics.kelly_fraction * 100).toFixed(1) : '—'

  return (
    <div className="flex flex-col h-full overflow-auto" style={{ background: 'var(--bg-base)' }}>

      {/* Header */}
      <div className="px-6 py-3 border-b flex items-center justify-between flex-shrink-0"
           style={{ borderColor: 'var(--border)', background: 'var(--bg-surface)' }}>
        <div>
          <h1 className="font-semibold text-sm" style={{ color: 'var(--text-primary)' }}>Analytics</h1>
          <p className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>
            Performance · Equity curve · Trade history
          </p>
        </div>
        <div className="flex items-center gap-2">
          {lastRefresh && (
            <span className="text-xs font-mono hidden sm:block" style={{ color: 'var(--text-muted)' }}>
              {lastRefresh.toLocaleTimeString()}
            </span>
          )}
          <button
            onClick={exportCSV}
            disabled={loading}
            className="flex items-center gap-1.5 px-2.5 py-1.5 rounded text-xs transition-opacity disabled:opacity-40"
            style={{ background: 'var(--bg-elevated)', color: 'var(--text-secondary)', border: '1px solid var(--border)' }}
            aria-label="Export trades as CSV"
          >
            <Download size={11} />
            <span className="hidden sm:inline">Export CSV</span>
          </button>
          <button
            onClick={() => loadData(true)}
            disabled={refreshing}
            className="flex items-center gap-1.5 px-2.5 py-1.5 rounded text-xs transition-opacity disabled:opacity-40"
            style={{ background: 'var(--bg-elevated)', color: 'var(--text-secondary)', border: '1px solid var(--border)' }}
          >
            <RefreshCw size={11} className={refreshing ? 'animate-spin' : ''} />
            <span className="hidden sm:inline">Refresh</span>
          </button>
        </div>
      </div>

      <div className="p-6 flex flex-col gap-6">

        {/* Equity Curve */}
        <div className="rounded border p-4"
             style={{ borderColor: 'var(--border)', background: 'var(--bg-surface)' }}>
          <div className="flex items-center gap-2 mb-3">
            <TrendingUp size={13} style={{ color: 'var(--accent)' }} />
            <span className="text-xs font-semibold tracking-wider uppercase"
                  style={{ color: 'var(--text-muted)' }}>
              Equity Curve + Drawdown
            </span>
            <span className="text-xs font-mono ml-auto" style={{ color: 'var(--text-muted)' }}>
              {snapshots.length > 0
                ? `${snapshots.length} snapshots · $${snapshots[snapshots.length - 1]?.equity?.toFixed(2) ?? '—'}`
                : 'awaiting data'}
            </span>
          </div>
          {loading
            ? <Skeleton h={220} />
            : <EquityChart snapshots={snapshots} height={220} />
          }
        </div>

        {/* KPI grid */}
        <div>
          <div className="text-xs font-semibold tracking-wider mb-3 uppercase"
               style={{ color: 'var(--text-muted)' }}>
            Performance Metrics
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <StatCard loading={loading} label="WIN RATE"        value={`${wr}%`}  sub={`${metrics?.winning_trades || 0}W / ${metrics?.losing_trades || 0}L`} color={parseFloat(wr) > 50 ? 'var(--bull)' : 'var(--bear)'} />
            <StatCard loading={loading} label="PROFIT FACTOR"   value={pf}        sub="target >1.5" color={parseFloat(pf) > 1.5 ? 'var(--bull)' : 'var(--accent)'} />
            <StatCard loading={loading} label="SHARPE RATIO"    value={sr}        sub="annualised"  color={parseFloat(sr) > 1 ? 'var(--bull)' : 'var(--accent)'} />
            <StatCard loading={loading} label="EXPECTANCY"      value={exp}       sub="per trade"   color={(metrics?.expectancy_per_trade || 0) > 0 ? 'var(--bull)' : 'var(--bear)'} />
            <StatCard loading={loading} label="NET P&L"         value={`$${(metrics?.net_pnl_usd || 0).toFixed(2)}`} color={(metrics?.net_pnl_usd || 0) >= 0 ? 'var(--bull)' : 'var(--bear)'} />
            <StatCard loading={loading} label="AVG WIN"         value={`$${(metrics?.avg_win_usd || 0).toFixed(2)}`} color="var(--bull)" />
            <StatCard loading={loading} label="AVG LOSS"        value={`$${(metrics?.avg_loss_usd || 0).toFixed(2)}`} color="var(--bear)" />
            <StatCard loading={loading} label="KELLY FRACTION"  value={`${kly}%`} sub={`rec. ${metrics?.recommended_risk_pct?.toFixed(2) || '1.00'}% risk`} color="var(--accent)" />
            <StatCard loading={loading} label="MAX CONSEC LOSS" value={String(metrics?.max_consecutive_losses || 0)} sub="reduce size at 3+" color={(metrics?.max_consecutive_losses || 0) >= 3 ? 'var(--bear)' : 'var(--text-primary)'} />
            <StatCard loading={loading} label="BEST PAIR"       value={metrics?.best_instrument || '—'}  color="var(--bull)" />
            <StatCard loading={loading} label="WORST PAIR"      value={metrics?.worst_instrument || '—'} color="var(--bear)" />
            <StatCard loading={loading} label="TOTAL SIGNALS"   value={String(metrics?.total_signals || 0)} sub="all generated" />
          </div>

          {/* Assessment banner */}
          {!loading && metrics?.assessment && (
            <div className="mt-3 px-4 py-3 rounded border text-xs font-mono"
                 style={{ borderColor: 'var(--border)', background: 'var(--bg-elevated)', color: 'var(--text-secondary)', lineHeight: 1.6 }}>
              {metrics.assessment}
            </div>
          )}
        </div>

        {/* Recharts trading charts — daily P&L, instrument bars, outcome donut */}
        <div>
          <div className="text-xs font-semibold tracking-wider mb-3 uppercase"
               style={{ color: 'var(--text-muted)' }}>
            Trade Charts
          </div>
          <TradingCharts />
        </div>

        {/* Per-instrument */}
        {!loading && metrics?.by_instrument && Object.keys(metrics.by_instrument).length > 0 && (
          <div>
            <div className="text-xs font-semibold tracking-wider mb-3 uppercase"
                 style={{ color: 'var(--text-muted)' }}>
              Per Instrument
            </div>
            <table className="w-full text-xs font-mono">
              <thead>
                <tr style={{ color: 'var(--text-muted)', borderBottom: '1px solid var(--border)' }}>
                  <th className="text-left py-2 pr-6">Instrument</th>
                  <th className="text-right py-2 pr-6">Trades</th>
                  <th className="text-right py-2 pr-6">Win Rate</th>
                  <th className="text-right py-2">P&L</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(metrics.by_instrument)
                  .sort(([, a], [, b]) => b.total_pnl - a.total_pnl)
                  .map(([sym, d]) => (
                  <tr key={sym} className="border-b" style={{ borderColor: 'var(--border)' }}>
                    <td className="py-2 pr-6 font-semibold" style={{ color: 'var(--text-primary)' }}>{sym}</td>
                    <td className="py-2 pr-6 text-right" style={{ color: 'var(--text-secondary)' }}>{d.trade_count}</td>
                    <td className="py-2 pr-6 text-right"
                        style={{ color: d.win_rate > 0.5 ? 'var(--bull)' : 'var(--bear)' }}>
                      {(d.win_rate * 100).toFixed(0)}%
                    </td>
                    <td className="py-2 text-right font-semibold"
                        style={{ color: d.total_pnl >= 0 ? 'var(--bull)' : 'var(--bear)' }}>
                      {d.total_pnl >= 0 ? '+' : ''}${d.total_pnl.toFixed(2)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Agent cycle log */}
        <div>
          <div className="text-xs font-semibold tracking-wider mb-3 uppercase"
               style={{ color: 'var(--text-muted)' }}>
            Agent Cycle Log
          </div>
          {loading ? (
            <div className="flex flex-col gap-2">
              {[...Array(5)].map((_, i) => <Skeleton key={i} h={28} />)}
            </div>
          ) : (
            <table className="w-full text-xs font-mono">
              <thead>
                <tr style={{ color: 'var(--text-muted)', borderBottom: '1px solid var(--border)' }}>
                  <th className="text-left py-2 pr-6">Time</th>
                  <th className="text-left py-2 pr-6">Trigger</th>
                  <th className="text-right py-2">Trades</th>
                </tr>
              </thead>
              <tbody>
                {cycles.map((c, i) => (
                  <tr key={c.cycle_id || i} className="border-b" style={{ borderColor: 'var(--border)' }}>
                    <td className="py-1.5 pr-6" style={{ color: 'var(--text-muted)' }}>
                      {c.timestamp?.slice(0, 19).replace('T', ' ')}
                    </td>
                    <td className="py-1.5 pr-6" style={{ color: 'var(--text-secondary)' }}>{c.trigger}</td>
                    <td className="py-1.5 text-right"
                        style={{ color: c.trades_executed > 0 ? 'var(--bull)' : 'var(--text-muted)' }}>
                      {c.trades_executed > 0 ? `+${c.trades_executed}` : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {!loading && cycles.length === 0 && (
            <EmptyState
              icon={Activity}
              title="No cycles recorded yet"
              body="Agent runs every 15 minutes. Cycle data will appear here after the first scheduled run."
              compact
            />
          )}
        </div>
      </div>
    </div>
  )
}
