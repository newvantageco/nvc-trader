'use client'

/**
 * TradingCharts
 *
 * Recharts-powered analytics suite for the analytics page.
 * Three charts adapted from SightSync CampaignCharts:
 *   1. Area chart   — daily P&L over selected period
 *   2. Bar chart    — trades executed per instrument
 *   3. Donut chart  — win/loss/neutral outcome split
 *
 * Fetches from /analytics and /trades endpoints.
 * Range picker: 7d / 30d / 90d.
 */

import { useState, useEffect, useCallback } from 'react'
import dynamic from 'next/dynamic'
import {
  AreaChart, Area, BarChart, Bar, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts'
import { TrendingUp, BarChart3, PieChart as PieIcon } from 'lucide-react'

const API = process.env.NEXT_PUBLIC_API_URL || 'https://nvc-trader.fly.dev'

type Range = '7d' | '30d' | '90d'

interface TradeRow {
  created_at:  string
  pnl?:        number
  instrument?: string
  direction?:  string
  status?:     string
  fill?:       { status?: string; fill_price?: number }
}

interface DailyPoint { date: string; pnl: number; trades: number }

function buildDailyPoints(trades: TradeRow[], days: number): DailyPoint[] {
  const cutoff = Date.now() - days * 86400_000
  const map    = new Map<string, DailyPoint>()
  for (const t of trades) {
    const ts = new Date(t.created_at).getTime()
    if (ts < cutoff) continue
    const key = new Date(t.created_at).toISOString().slice(0, 10)
    const existing = map.get(key) ?? { date: key, pnl: 0, trades: 0 }
    existing.pnl    += typeof t.pnl === 'number' ? t.pnl : 0
    existing.trades += 1
    map.set(key, existing)
  }
  return Array.from(map.values()).sort((a, b) => a.date.localeCompare(b.date))
}

function buildInstrumentBar(trades: TradeRow[], days: number): Array<{ name: string; trades: number; pnl: number }> {
  const cutoff = Date.now() - days * 86400_000
  const map    = new Map<string, { trades: number; pnl: number }>()
  for (const t of trades) {
    if (new Date(t.created_at).getTime() < cutoff) continue
    const sym = t.instrument ?? 'OTHER'
    const existing = map.get(sym) ?? { trades: 0, pnl: 0 }
    existing.trades += 1
    existing.pnl    += typeof t.pnl === 'number' ? t.pnl : 0
    map.set(sym, existing)
  }
  return Array.from(map.entries())
    .map(([name, v]) => ({ name, ...v }))
    .sort((a, b) => b.trades - a.trades)
    .slice(0, 12)
}

function buildPie(trades: TradeRow[], days: number) {
  const cutoff = Date.now() - days * 86400_000
  let wins = 0, losses = 0, neutral = 0
  for (const t of trades) {
    if (new Date(t.created_at).getTime() < cutoff) continue
    const pnl = typeof t.pnl === 'number' ? t.pnl : null
    if (pnl === null) { neutral++; continue }
    if (pnl > 0) wins++
    else if (pnl < 0) losses++
    else neutral++
  }
  return [
    { name: 'Wins',    value: wins,    color: 'var(--bull)' },
    { name: 'Losses',  value: losses,  color: 'var(--bear)' },
    { name: 'Neutral', value: neutral, color: 'var(--text-muted)' },
  ].filter(p => p.value > 0)
}

function ChartTooltip({ active, payload, label }: {
  active?: boolean
  payload?: Array<{ name: string; value: number; color: string }>
  label?: string
}) {
  if (!active || !payload?.length) return null
  return (
    <div
      className="rounded-lg p-3 text-xs font-mono shadow-xl"
      style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border-bright)' }}
    >
      {label && <p className="font-semibold mb-2" style={{ color: 'var(--text-muted)' }}>{label}</p>}
      {payload.map(p => (
        <div key={p.name} className="flex items-center gap-2 py-0.5">
          <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: p.color || 'var(--accent)' }} />
          <span style={{ color: 'var(--text-secondary)' }}>{p.name}:</span>
          <span className="font-semibold ml-auto pl-3" style={{ color: 'var(--text-primary)' }}>
            {typeof p.value === 'number' && p.name.toLowerCase().includes('p')
              ? `${p.value >= 0 ? '+' : ''}$${p.value.toFixed(2)}`
              : p.value}
          </span>
        </div>
      ))}
    </div>
  )
}

function SectionHeader({ icon: Icon, title }: { icon: React.ElementType; title: string }) {
  return (
    <div className="flex items-center gap-2 mb-3">
      <Icon size={12} style={{ color: 'var(--accent)' }} />
      <span className="text-[10px] font-semibold tracking-wider uppercase" style={{ color: 'var(--text-muted)' }}>
        {title}
      </span>
    </div>
  )
}

export default function TradingCharts() {
  const [range,   setRange]   = useState<Range>('30d')
  const [trades,  setTrades]  = useState<TradeRow[]>([])
  const [loading, setLoading] = useState(true)
  const [error,   setError]   = useState(false)

  const days = range === '7d' ? 7 : range === '30d' ? 30 : 90

  const load = useCallback(async () => {
    setLoading(true)
    setError(false)
    try {
      const r = await fetch(`${API}/trades?limit=500`)
      if (!r.ok) throw new Error('fetch failed')
      const d = await r.json()
      setTrades(d.trades || [])
    } catch {
      setError(true)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const dailyPoints     = buildDailyPoints(trades, days)
  const instrumentBars  = buildInstrumentBar(trades, days)
  const pieData         = buildPie(trades, days)
  const totalPnl        = dailyPoints.reduce((s, p) => s + p.pnl, 0)
  const totalTrades     = dailyPoints.reduce((s, p) => s + p.trades, 0)

  const axisProps = {
    tick:      { fontSize: 10, fill: 'var(--text-muted)', fontFamily: 'var(--font-mono)' },
    tickLine:  false as const,
    axisLine:  false as const,
  }
  const gridProps = { strokeDasharray: '3 3', stroke: 'var(--border)', vertical: false }

  const RangePicker = () => (
    <div
      className="flex items-center gap-0.5 p-0.5 rounded"
      style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border)' }}
    >
      {(['7d', '30d', '90d'] as Range[]).map(r => (
        <button
          key={r}
          onClick={() => setRange(r)}
          className="px-2.5 py-1 text-xs font-mono rounded transition-all"
          style={{
            background: range === r ? 'var(--bg-surface)' : 'transparent',
            color:      range === r ? 'var(--text-primary)' : 'var(--text-muted)',
            border:     range === r ? '1px solid var(--border-bright)' : '1px solid transparent',
          }}
        >
          {r}
        </button>
      ))}
    </div>
  )

  if (error) return (
    <div
      className="flex flex-col items-center justify-center py-16 text-center rounded-lg border"
      style={{ borderColor: 'var(--border)', borderStyle: 'dashed' }}
    >
      <TrendingUp size={24} style={{ color: 'var(--border)', marginBottom: 8 }} />
      <p className="text-sm font-mono" style={{ color: 'var(--text-muted)' }}>Failed to load trade data</p>
    </div>
  )

  if (loading) return (
    <div className="space-y-4">
      {[220, 200].map((h, i) => (
        <div key={i} className="skeleton rounded-lg" style={{ height: h }} />
      ))}
    </div>
  )

  if (trades.length === 0) return (
    <div
      className="flex flex-col items-center justify-center py-16 text-center rounded-lg border"
      style={{ borderColor: 'var(--border)', borderStyle: 'dashed' }}
    >
      <TrendingUp size={24} style={{ color: 'var(--border)', marginBottom: 8 }} />
      <p className="text-sm font-mono" style={{ color: 'var(--text-muted)' }}>No trade history yet</p>
      <p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>Charts appear after first trades execute</p>
    </div>
  )

  return (
    <div className="space-y-4">
      {/* Controls */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4 text-xs font-mono">
          <div>
            <span style={{ color: 'var(--text-muted)' }}>Net P&L: </span>
            <span style={{ color: totalPnl >= 0 ? 'var(--bull)' : 'var(--bear)', fontWeight: 700 }}>
              {totalPnl >= 0 ? '+' : ''}${totalPnl.toFixed(2)}
            </span>
          </div>
          <div>
            <span style={{ color: 'var(--text-muted)' }}>Trades: </span>
            <span style={{ color: 'var(--text-primary)', fontWeight: 600 }}>{totalTrades}</span>
          </div>
        </div>
        <RangePicker />
      </div>

      {/* Daily P&L Area chart */}
      {dailyPoints.length > 0 && (
        <div
          className="p-4 rounded-lg border"
          style={{ borderColor: 'var(--border)', background: 'var(--bg-surface)' }}
        >
          <SectionHeader icon={TrendingUp} title={`Daily P&L — last ${range}`} />
          <ResponsiveContainer width="100%" height={200}>
            <AreaChart data={dailyPoints} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
              <defs>
                <linearGradient id="pnlGradPos" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%"  stopColor="#2ea84a" stopOpacity={0.2} />
                  <stop offset="95%" stopColor="#2ea84a" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="pnlGradNeg" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%"  stopColor="#e5483e" stopOpacity={0.2} />
                  <stop offset="95%" stopColor="#e5483e" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid {...gridProps} />
              <XAxis dataKey="date" {...axisProps} interval="preserveStartEnd"
                tickFormatter={d => d.slice(5)} />
              <YAxis {...axisProps} tickFormatter={v => `$${v}`} />
              <Tooltip content={<ChartTooltip />} />
              <Area
                type="monotone"
                dataKey="pnl"
                name="P&L"
                stroke={totalPnl >= 0 ? '#2ea84a' : '#e5483e'}
                fill={totalPnl >= 0 ? 'url(#pnlGradPos)' : 'url(#pnlGradNeg)'}
                strokeWidth={2}
                dot={false}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Instrument bar + pie in 2-col */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {/* Trades per instrument */}
        {instrumentBars.length > 0 && (
          <div
            className="p-4 rounded-lg border"
            style={{ borderColor: 'var(--border)', background: 'var(--bg-surface)' }}
          >
            <SectionHeader icon={BarChart3} title="Trades by instrument" />
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={instrumentBars} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
                <CartesianGrid {...gridProps} />
                <XAxis dataKey="name" {...axisProps} />
                <YAxis {...axisProps} allowDecimals={false} />
                <Tooltip content={<ChartTooltip />} />
                <Bar dataKey="trades" name="Trades" fill="var(--accent)" radius={[3, 3, 0, 0]} maxBarSize={28} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}

        {/* Win / loss donut */}
        {pieData.length > 0 && (
          <div
            className="p-4 rounded-lg border"
            style={{ borderColor: 'var(--border)', background: 'var(--bg-surface)' }}
          >
            <SectionHeader icon={PieIcon} title="Outcome split" />
            <div className="flex items-center gap-4">
              <ResponsiveContainer width="100%" height={200}>
                <PieChart>
                  <Pie
                    data={pieData}
                    cx="45%"
                    cy="50%"
                    innerRadius={52}
                    outerRadius={78}
                    paddingAngle={2}
                    dataKey="value"
                  >
                    {pieData.map((entry, i) => (
                      <Cell key={i} fill={entry.color} />
                    ))}
                  </Pie>
                  <Tooltip formatter={(v) => [v]} />
                </PieChart>
              </ResponsiveContainer>
              <div className="flex-shrink-0 space-y-2 pr-4">
                {pieData.map(p => (
                  <div key={p.name} className="flex items-center gap-2">
                    <span className="w-2.5 h-2.5 rounded-sm flex-shrink-0" style={{ background: p.color }} />
                    <span className="text-xs font-mono" style={{ color: 'var(--text-secondary)' }}>{p.name}</span>
                    <span className="text-xs font-mono font-bold ml-auto pl-2" style={{ color: 'var(--text-primary)' }}>
                      {p.value}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
