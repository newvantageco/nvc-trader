'use client'

import { useNVCStore } from '@/lib/store'

function Field({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="flex flex-col items-center leading-none">
      <span className="font-mono text-[9px] tracking-widest uppercase" style={{ color: 'var(--text-muted)' }}>
        {label}
      </span>
      <span className="font-mono font-bold text-xs mt-0.5" style={{ color: color || 'var(--text-primary)' }}>
        {value}
      </span>
    </div>
  )
}

function Divider() {
  return <div className="w-px h-6 flex-shrink-0" style={{ background: 'var(--border)' }} />
}

export default function AccountBar() {
  const { account } = useNVCStore()

  if (!account) {
    return (
      <div className="flex items-center gap-4">
        {[0, 1, 2, 3].map(i => (
          <div key={i} className="flex flex-col items-center gap-1">
            <div className="skeleton" style={{ width: 36, height: 9 }} />
            <div className="skeleton" style={{ width: 56, height: 12 }} />
          </div>
        ))}
      </div>
    )
  }

  const {
    balance,
    equity,
    margin,
    unrealised_pl,
    daily_drawdown_pct: dd,
    weekly_drawdown_pct: wdd = 0,
    currency = 'USD',
    circuit_breaker: cb,
  } = account

  const marginPct = equity > 0 ? (margin / equity) * 100 : 0
  const plColor   = (unrealised_pl ?? 0) >= 0 ? 'var(--bull)' : 'var(--bear)'
  const ddColor   = dd > 2 ? 'var(--bear)' : dd > 1 ? 'var(--accent)' : 'var(--bull)'
  const wddColor  = wdd > 5 ? 'var(--bear)' : wdd > 3 ? 'var(--accent)' : 'var(--text-primary)'

  const cbLabel = cb?.hard_stop
    ? 'HARD STOP'
    : cb?.weekly_limit_hit
    ? 'HALF SIZE'
    : cb && !cb.trading_allowed
    ? 'HALTED'
    : 'ACTIVE'
  const cbColor = cb?.hard_stop || (cb && !cb.trading_allowed)
    ? 'var(--bear)'
    : cb?.weekly_limit_hit
    ? 'var(--accent)'
    : 'var(--bull)'

  const fmt = (n: number) =>
    n.toLocaleString('en', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

  return (
    <div className="flex items-center gap-4">
      <Field label="Balance"    value={`${fmt(balance)} ${currency}`} />
      <Divider />
      <Field label="Equity"     value={`${fmt(equity)} ${currency}`} />
      <Divider />
      <Field label="Margin %"   value={`${marginPct.toFixed(1)}%`}  color={marginPct > 30 ? 'var(--bear)' : 'var(--text-primary)'} />
      <Divider />
      <Field label="Float P&L"  value={`${(unrealised_pl ?? 0) >= 0 ? '+' : ''}${fmt(unrealised_pl ?? 0)}`} color={plColor} />
      <Divider />
      <Field label="Daily DD"   value={`-${dd.toFixed(2)}%`}        color={ddColor} />
      <Divider />
      <Field label="Weekly DD"  value={`-${wdd.toFixed(2)}%`}       color={wddColor} />
      <Divider />
      <Field label="Circuit"    value={cbLabel}                      color={cbColor} />
    </div>
  )
}
