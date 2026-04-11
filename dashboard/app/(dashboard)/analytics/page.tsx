'use client'

import { useEffect, useState } from 'react'
import Sidebar from '@/components/Sidebar'

const API = process.env.NEXT_PUBLIC_API_URL || 'https://nvc-trader-engine.fly.dev'

interface Metrics {
  total_trades: number
  winning_trades: number
  losing_trades: number
  win_rate: number
  total_pnl: number
  avg_win: number
  avg_loss: number
  profit_factor: number
  sharpe_ratio: number
  max_drawdown_pct: number
  total_signals: number
  by_instrument: Record<string, { trades: number; pnl: number; win_rate: number }>
}

function StatCard({ label, value, sub, color }: { label: string; value: string; sub?: string; color?: string }) {
  return (
    <div className="p-4 rounded border" style={{ borderColor: 'var(--border)', background: 'var(--bg-surface)' }}>
      <div className="text-xs tracking-wider mb-1" style={{ color: 'var(--text-muted)' }}>{label}</div>
      <div className="text-xl font-mono font-bold" style={{ color: color || 'var(--text-primary)' }}>{value}</div>
      {sub && <div className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>{sub}</div>}
    </div>
  )
}

export default function AnalyticsPage() {
  const [metrics, setMetrics] = useState<Metrics | null>(null)
  const [cycles,  setCycles]  = useState<Array<{ cycle_id: string; timestamp: string; trades_executed: number; trigger: string }>>([])

  useEffect(() => {
    fetch(`${API}/analytics`)
      .then(r => r.json())
      .then(d => setMetrics(d))
      .catch(() => {})

    fetch(`${API}/cycles`)
      .then(r => r.json())
      .then(d => setCycles(d.cycles || []))
      .catch(() => {})
  }, [])

  const wr = metrics?.win_rate ? (metrics.win_rate * 100).toFixed(1) : '—'
  const pf = metrics?.profit_factor?.toFixed(2) ?? '—'
  const sr = metrics?.sharpe_ratio?.toFixed(2) ?? '—'
  const dd = metrics?.max_drawdown_pct?.toFixed(2) ?? '—'

  return (
    <div className="flex min-h-screen" style={{ background: 'var(--bg-base)' }}>
      <Sidebar />
      <div className="flex-1 overflow-auto">
        <div className="px-6 py-4 border-b"
             style={{ borderColor: 'var(--border)', background: 'var(--bg-surface)' }}>
          <h1 className="font-semibold text-sm" style={{ color: 'var(--text-primary)' }}>Analytics</h1>
          <p className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>Performance metrics · Trade history</p>
        </div>

        <div className="p-6">
          {/* KPI grid */}
          <div className="grid grid-cols-4 gap-3 mb-6">
            <StatCard label="WIN RATE"      value={`${wr}%`}        sub={`${metrics?.winning_trades || 0}W / ${metrics?.losing_trades || 0}L`} color={parseFloat(wr) > 50 ? 'var(--bull)' : 'var(--bear)'} />
            <StatCard label="PROFIT FACTOR" value={pf}              sub="target >1.5" color={parseFloat(pf) > 1.5 ? 'var(--bull)' : 'var(--accent)'} />
            <StatCard label="SHARPE RATIO"  value={sr}              sub="annualised" color={parseFloat(sr) > 1 ? 'var(--bull)' : 'var(--accent)'} />
            <StatCard label="MAX DRAWDOWN"  value={`-${dd}%`}       sub="from peak"  color="var(--bear)" />
            <StatCard label="TOTAL P&L"     value={`$${(metrics?.total_pnl || 0).toFixed(2)}`} color={(metrics?.total_pnl || 0) >= 0 ? 'var(--bull)' : 'var(--bear)'} />
            <StatCard label="AVG WIN"       value={`$${(metrics?.avg_win || 0).toFixed(2)}`}    color="var(--bull)" />
            <StatCard label="AVG LOSS"      value={`$${(metrics?.avg_loss || 0).toFixed(2)}`}   color="var(--bear)" />
            <StatCard label="TOTAL SIGNALS" value={String(metrics?.total_signals || 0)} sub="all generated" />
          </div>

          {/* Per-instrument */}
          {metrics?.by_instrument && Object.keys(metrics.by_instrument).length > 0 && (
            <div className="mb-6">
              <div className="text-xs font-semibold tracking-wider mb-3" style={{ color: 'var(--text-muted)' }}>
                PER INSTRUMENT
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
                  {Object.entries(metrics.by_instrument).map(([sym, d]) => (
                    <tr key={sym} className="border-b" style={{ borderColor: 'var(--border)' }}>
                      <td className="py-2 pr-6 font-semibold" style={{ color: 'var(--text-primary)' }}>{sym}</td>
                      <td className="py-2 pr-6 text-right" style={{ color: 'var(--text-secondary)' }}>{d.trades}</td>
                      <td className="py-2 pr-6 text-right"
                          style={{ color: d.win_rate > 0.5 ? 'var(--bull)' : 'var(--bear)' }}>
                        {(d.win_rate * 100).toFixed(0)}%
                      </td>
                      <td className="py-2 text-right font-semibold"
                          style={{ color: d.pnl >= 0 ? 'var(--bull)' : 'var(--bear)' }}>
                        {d.pnl >= 0 ? '+' : ''}${d.pnl.toFixed(2)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Agent cycle log */}
          <div>
            <div className="text-xs font-semibold tracking-wider mb-3" style={{ color: 'var(--text-muted)' }}>
              AGENT CYCLE LOG
            </div>
            <table className="w-full text-xs font-mono">
              <thead>
                <tr style={{ color: 'var(--text-muted)', borderBottom: '1px solid var(--border)' }}>
                  <th className="text-left py-2 pr-6">Time</th>
                  <th className="text-left py-2 pr-6">Trigger</th>
                  <th className="text-right py-2">Trades</th>
                </tr>
              </thead>
              <tbody>
                {cycles.map(c => (
                  <tr key={c.cycle_id} className="border-b" style={{ borderColor: 'var(--border)' }}>
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
            {cycles.length === 0 && (
              <div className="text-xs py-4" style={{ color: 'var(--text-muted)' }}>No cycles yet.</div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
