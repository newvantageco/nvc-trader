'use client'

import { useEffect, useState } from 'react'
import {
  TrendingUp, DollarSign, Cpu, Server, Globe,
  BarChart2, Target, CheckCircle, AlertTriangle,
  ArrowUpRight, Clock, Zap, Lock
} from 'lucide-react'

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

interface AdminData {
  performance: {
    account_balance: number
    apy_pct: number
    avg_daily_usd: number
    avg_daily_pct: number
    total_trades: number
    trading_days: number
    total_cycles: number
  }
  growth: {
    current_stage: number
    stage_name: string
    daily_target: string
    advancement: {
      ready: boolean
      days_qualifying: number
      days_needed: number
      bad_days: number
      message: string
      blockers: string[]
    }
    params: {
      note: string
      min_edge_grade: string
      min_rr: number
      max_open_trades: number
      position_units: number
      pip_value_approx: number
    }
    all_stages: Array<{
      stage: number
      name: string
      daily_target: string
      monthly_gross: string
      monthly_net: string
      margin_range: string
      is_current: boolean
    }>
  }
  costs: {
    monthly: Record<string, number>
    daily_total: number
    cost_breakdown: Array<{ name: string; monthly: number; pct: number }>
  }
  profitability: {
    monthly_gross: number
    monthly_costs: number
    monthly_net: number
    profit_margin_pct: number
    breakeven_daily_usd: number
    target_margin_pct: number
    at_target_margin: boolean
    note: string
  }
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function StatCard({
  label, value, sub, icon: Icon, accent = false, warn = false
}: {
  label: string; value: string; sub?: string
  icon: React.ComponentType<any>
  accent?: boolean; warn?: boolean
}) {
  const col = accent ? 'var(--accent)' : warn ? 'var(--bear)' : 'var(--bull)'
  return (
    <div
      className="p-4 rounded border flex flex-col gap-2"
      style={{ background: 'var(--bg-surface)', borderColor: 'var(--border)' }}
    >
      <div className="flex items-center justify-between">
        <span className="text-xs uppercase tracking-wider" style={{ color: 'var(--text-muted)' }}>
          {label}
        </span>
        <Icon size={14} style={{ color: col }} />
      </div>
      <div className="text-2xl font-mono font-bold" style={{ color: col }}>{value}</div>
      {sub && <div className="text-xs font-mono" style={{ color: 'var(--text-muted)' }}>{sub}</div>}
    </div>
  )
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function SectionHeader({ title, icon: Icon }: {
  title: string
  icon: React.ComponentType<any>
}) {
  return (
    <div className="flex items-center gap-2 mb-4">
      <Icon size={15} style={{ color: 'var(--accent)' }} />
      <span className="text-sm font-semibold uppercase tracking-wider" style={{ color: 'var(--accent)' }}>
        {title}
      </span>
    </div>
  )
}

export default function AdminPage() {
  const [data, setData] = useState<AdminData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    fetch(`${API_URL}/admin/overview`)
      .then(r => r.json())
      .then(d => { setData(d); setLoading(false) })
      .catch(e => { setError(e.message); setLoading(false) })
  }, [])

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full" style={{ color: 'var(--text-muted)' }}>
        <div className="flex items-center gap-2 text-xs font-mono">
          <div className="w-1.5 h-1.5 rounded-full animate-pulse" style={{ background: 'var(--accent)' }} />
          Loading admin data...
        </div>
      </div>
    )
  }

  if (error || !data) {
    return (
      <div className="flex items-center justify-center h-full" style={{ color: 'var(--bear)' }}>
        <div className="text-xs font-mono">Error: {error || 'No data'}</div>
      </div>
    )
  }

  const { performance: perf, growth, costs, profitability: profit } = data
  const marginColor = profit.profit_margin_pct >= 60 ? 'var(--bull)' :
                      profit.profit_margin_pct >= 40 ? 'var(--accent)' : 'var(--bear)'

  return (
    <div
      className="h-full overflow-y-auto p-5 flex flex-col gap-6"
      style={{ background: 'var(--bg-base)', color: 'var(--text-primary)' }}
    >
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-sm font-semibold" style={{ color: 'var(--accent)' }}>
            Admin — Platform Overview
          </h1>
          <p className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>
            APY, costs, profit margin, growth stage — full visibility
          </p>
        </div>
        <div
          className="flex items-center gap-1.5 px-2 py-1 rounded text-xs font-mono"
          style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)', color: 'var(--text-muted)' }}
        >
          <Lock size={11} />
          Operator only
        </div>
      </div>

      {/* ── KPI row ── */}
      <div className="grid grid-cols-4 gap-3">
        <StatCard
          label="Account Balance"
          value={`$${perf.account_balance.toFixed(2)}`}
          sub={`${perf.trading_days} trading days tracked`}
          icon={DollarSign}
          accent
        />
        <StatCard
          label="APY"
          value={perf.apy_pct > 0 ? `${perf.apy_pct.toLocaleString()}%` : '—'}
          sub={`${perf.avg_daily_pct > 0 ? perf.avg_daily_pct.toFixed(2) + '%/day avg' : 'No closed trades yet'}`}
          icon={TrendingUp}
        />
        <StatCard
          label="Avg Daily P&L"
          value={perf.avg_daily_usd > 0 ? `$${perf.avg_daily_usd.toFixed(2)}` : '—'}
          sub={`vs $${costs.daily_total.toFixed(2)}/day cost`}
          icon={BarChart2}
          accent={perf.avg_daily_usd > costs.daily_total}
          warn={perf.avg_daily_usd > 0 && perf.avg_daily_usd <= costs.daily_total}
        />
        <StatCard
          label="Profit Margin"
          value={profit.profit_margin_pct > 0 ? `${profit.profit_margin_pct.toFixed(1)}%` : '—'}
          sub={`Target: ${profit.target_margin_pct}%`}
          icon={profit.at_target_margin ? CheckCircle : Target}
          accent={profit.at_target_margin}
          warn={profit.profit_margin_pct > 0 && !profit.at_target_margin}
        />
      </div>

      <div className="grid grid-cols-3 gap-5">

        {/* ── Growth Stage ── */}
        <div
          className="col-span-1 p-4 rounded border flex flex-col gap-4"
          style={{ background: 'var(--bg-surface)', borderColor: 'var(--border)' }}
        >
          <SectionHeader title="Growth Stage" icon={Zap} />

          {/* Current stage badge */}
          <div
            className="rounded p-3 flex flex-col gap-1 border"
            style={{ background: 'rgba(245,158,11,0.05)', borderColor: 'rgba(245,158,11,0.2)' }}
          >
            <div className="flex items-center justify-between">
              <span className="text-xs font-mono" style={{ color: 'var(--text-muted)' }}>
                Current
              </span>
              <span
                className="text-xs px-1.5 py-0.5 rounded font-mono"
                style={{ background: 'var(--accent)', color: '#000' }}
              >
                Stage {growth.current_stage}
              </span>
            </div>
            <div className="text-lg font-mono font-bold" style={{ color: 'var(--accent)' }}>
              {growth.daily_target}/day
            </div>
            <div className="text-xs" style={{ color: 'var(--text-muted)' }}>
              {growth.stage_name}
            </div>
          </div>

          {/* Advancement progress */}
          <div className="flex flex-col gap-1.5">
            <div className="flex items-center justify-between">
              <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
                Qualifying days
              </span>
              <span className="text-xs font-mono" style={{ color: 'var(--text-primary)' }}>
                {growth.advancement.days_qualifying}/{growth.advancement.days_needed}
              </span>
            </div>
            <div
              className="h-1.5 rounded-full overflow-hidden"
              style={{ background: 'var(--bg-elevated)' }}
            >
              <div
                className="h-full rounded-full transition-all duration-700"
                style={{
                  width: `${Math.min(growth.advancement.days_qualifying / growth.advancement.days_needed * 100, 100)}%`,
                  background: growth.advancement.ready ? 'var(--bull)' : 'var(--accent)',
                }}
              />
            </div>
            {growth.advancement.ready ? (
              <div className="flex items-center gap-1 text-xs" style={{ color: 'var(--bull)' }}>
                <CheckCircle size={11} />
                Ready to advance!
              </div>
            ) : (
              <div className="text-xs" style={{ color: 'var(--text-muted)' }}>
                {growth.advancement.message}
              </div>
            )}
          </div>

          {/* Trading params */}
          <div
            className="rounded p-3 flex flex-col gap-1.5"
            style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border)' }}
          >
            <div className="text-xs font-semibold mb-1" style={{ color: 'var(--text-muted)' }}>
              Current Parameters
            </div>
            {[
              ['Min grade',      growth.params.min_edge_grade],
              ['Min RR',         `${growth.params.min_rr}:1`],
              ['Max positions',  `${growth.params.max_open_trades}`],
              ['Position size',  `${growth.params.position_units.toLocaleString()} units`],
              ['Pip value',      `~$${growth.params.pip_value_approx}/pip`],
            ].map(([k, v]) => (
              <div key={k} className="flex items-center justify-between">
                <span className="text-xs" style={{ color: 'var(--text-muted)' }}>{k}</span>
                <span className="text-xs font-mono" style={{ color: 'var(--text-primary)' }}>{v}</span>
              </div>
            ))}
          </div>

          {/* All stage roadmap */}
          <div className="flex flex-col gap-1">
            <div className="text-xs font-semibold mb-1" style={{ color: 'var(--text-muted)' }}>
              Roadmap
            </div>
            {growth.all_stages.map(s => (
              <div
                key={s.stage}
                className="flex items-center justify-between rounded px-2 py-1.5"
                style={{
                  background: s.is_current ? 'rgba(245,158,11,0.08)' : 'transparent',
                  border: `1px solid ${s.is_current ? 'rgba(245,158,11,0.3)' : 'transparent'}`,
                }}
              >
                <div className="flex items-center gap-2">
                  <span
                    className="text-xs font-mono w-5 text-center"
                    style={{ color: s.is_current ? 'var(--accent)' : 'var(--text-muted)' }}
                  >
                    S{s.stage}
                  </span>
                  <span className="text-xs" style={{ color: s.is_current ? 'var(--text-primary)' : 'var(--text-muted)' }}>
                    {s.daily_target}/day
                  </span>
                </div>
                <span className="text-xs font-mono" style={{ color: 'var(--text-muted)' }}>
                  {s.margin_range}
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* ── Cost Breakdown ── */}
        <div
          className="col-span-1 p-4 rounded border flex flex-col gap-4"
          style={{ background: 'var(--bg-surface)', borderColor: 'var(--border)' }}
        >
          <SectionHeader title="True Cost to Run" icon={Server} />

          <div className="flex flex-col gap-2">
            {costs.cost_breakdown.filter(c => c.monthly > 0).map(c => (
              <div key={c.name} className="flex flex-col gap-1">
                <div className="flex items-center justify-between">
                  <span className="text-xs" style={{ color: 'var(--text-secondary)' }}>{c.name}</span>
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-mono" style={{ color: 'var(--text-muted)' }}>
                      {c.pct}%
                    </span>
                    <span className="text-xs font-mono w-14 text-right" style={{ color: 'var(--text-primary)' }}>
                      ${c.monthly.toFixed(2)}/mo
                    </span>
                  </div>
                </div>
                <div
                  className="h-1 rounded-full overflow-hidden"
                  style={{ background: 'var(--bg-elevated)' }}
                >
                  <div
                    className="h-full rounded-full"
                    style={{ width: `${c.pct}%`, background: 'var(--accent)' }}
                  />
                </div>
              </div>
            ))}
          </div>

          {/* Totals */}
          <div
            className="rounded p-3 flex flex-col gap-2 border"
            style={{ background: 'var(--bg-elevated)', borderColor: 'var(--border)' }}
          >
            {[
              ['Monthly total',    `$${(costs.monthly.total ?? costs.daily_total * 30).toFixed(2)}`],
              ['Daily cost',       `$${costs.daily_total.toFixed(2)}`],
              ['Break-even/day',   `$${profit.breakeven_daily_usd.toFixed(2)}`],
              ['65% margin needs', `$${(profit.breakeven_daily_usd / 0.35).toFixed(2)}/day`],
            ].map(([k, v]) => (
              <div key={k} className="flex items-center justify-between">
                <span className="text-xs" style={{ color: 'var(--text-muted)' }}>{k}</span>
                <span className="text-xs font-mono font-semibold" style={{ color: 'var(--accent)' }}>{v}</span>
              </div>
            ))}
          </div>

          {/* Free services note */}
          <div
            className="rounded p-3"
            style={{ background: 'rgba(16,185,129,0.05)', border: '1px solid rgba(16,185,129,0.15)' }}
          >
            <div className="text-xs font-semibold mb-1.5" style={{ color: 'var(--bull)' }}>
              Free tier services
            </div>
            {['Vercel (hosting)', 'Supabase (DB)', 'NewsAPI (free tier)', 'FRED API (Fed data)'].map(s => (
              <div key={s} className="flex items-center gap-1.5 text-xs" style={{ color: 'var(--text-muted)' }}>
                <CheckCircle size={10} style={{ color: 'var(--bull)' }} />
                {s}
              </div>
            ))}
          </div>
        </div>

        {/* ── Profitability ── */}
        <div
          className="col-span-1 p-4 rounded border flex flex-col gap-4"
          style={{ background: 'var(--bg-surface)', borderColor: 'var(--border)' }}
        >
          <SectionHeader title="Profitability" icon={BarChart2} />

          {/* Margin gauge */}
          <div className="flex flex-col gap-2">
            <div className="flex items-center justify-between">
              <span className="text-xs" style={{ color: 'var(--text-muted)' }}>Profit margin</span>
              <span className="text-2xl font-mono font-bold" style={{ color: marginColor }}>
                {profit.profit_margin_pct > 0 ? `${profit.profit_margin_pct.toFixed(1)}%` : '—'}
              </span>
            </div>
            <div
              className="h-3 rounded-full overflow-hidden relative"
              style={{ background: 'var(--bg-elevated)' }}
            >
              {/* Target line at 65% */}
              <div
                className="absolute top-0 bottom-0 w-0.5"
                style={{ left: '65%', background: 'var(--accent)', opacity: 0.5, zIndex: 1 }}
              />
              <div
                className="h-full rounded-full transition-all duration-1000"
                style={{
                  width:      `${Math.min(profit.profit_margin_pct, 100)}%`,
                  background: marginColor,
                }}
              />
            </div>
            <div className="flex items-center justify-between text-xs" style={{ color: 'var(--text-muted)' }}>
              <span>0%</span>
              <span style={{ color: 'var(--accent)' }}>65% target</span>
              <span>100%</span>
            </div>
          </div>

          {/* Monthly breakdown */}
          <div
            className="rounded p-3 flex flex-col gap-2 border"
            style={{ background: 'var(--bg-elevated)', borderColor: 'var(--border)' }}
          >
            <div className="text-xs font-semibold mb-0.5" style={{ color: 'var(--text-muted)' }}>
              Monthly projection
            </div>
            {[
              ['Gross revenue',   `$${profit.monthly_gross.toFixed(2)}`, 'var(--text-primary)'],
              ['Platform costs',  `−$${profit.monthly_costs.toFixed(2)}`, 'var(--bear)'],
              ['Net profit',      `$${profit.monthly_net.toFixed(2)}`,
               profit.monthly_net >= 0 ? 'var(--bull)' : 'var(--bear)'],
            ].map(([k, v, c]) => (
              <div key={k} className="flex items-center justify-between border-t pt-1.5" style={{ borderColor: 'var(--border)' }}>
                <span className="text-xs" style={{ color: 'var(--text-muted)' }}>{k}</span>
                <span className="text-xs font-mono font-semibold" style={{ color: c as string }}>{v}</span>
              </div>
            ))}
          </div>

          {/* Note */}
          <div
            className="text-xs leading-relaxed p-3 rounded"
            style={{
              background: 'var(--bg-elevated)',
              color: 'var(--text-muted)',
              border: '1px solid var(--border)',
            }}
          >
            {profit.note}
          </div>

          {/* Cycle stats */}
          <div
            className="rounded p-3 flex flex-col gap-1.5 border"
            style={{ background: 'var(--bg-elevated)', borderColor: 'var(--border)' }}
          >
            <div className="text-xs font-semibold mb-0.5" style={{ color: 'var(--text-muted)' }}>
              System activity
            </div>
            {[
              ['Agent cycles',  perf.total_cycles.toLocaleString()],
              ['Closed trades', perf.total_trades.toLocaleString()],
              ['Trading days',  perf.trading_days.toLocaleString()],
            ].map(([k, v]) => (
              <div key={k} className="flex items-center justify-between">
                <span className="text-xs" style={{ color: 'var(--text-muted)' }}>{k}</span>
                <span className="text-xs font-mono" style={{ color: 'var(--text-primary)' }}>{v}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
