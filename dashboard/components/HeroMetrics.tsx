'use client'

import { useNVCStore } from '@/lib/store'
import { TrendingUp, TrendingDown, Shield, ShieldOff, Activity } from 'lucide-react'
import AnimatedNumber from '@/components/AnimatedNumber'

interface MetricCardProps {
  label: string
  value: string
  sub?: string
  color?: string
  icon?: React.ReactNode
  bg?: string
}

function MetricCard({ label, value, sub, color, icon, bg }: MetricCardProps) {
  return (
    <div
      className="flex items-center gap-3 px-4 py-3 rounded-lg flex-1 min-w-0"
      style={{
        background: bg || 'var(--bg-card)',
        border: '1px solid var(--border)',
      }}
    >
      {icon && (
        <div
          className="w-8 h-8 rounded flex items-center justify-center flex-shrink-0"
          style={{ background: 'var(--bg-elevated)' }}
        >
          {icon}
        </div>
      )}
      <div className="min-w-0">
        <div className="section-label mb-0.5">{label}</div>
        <div
          className="font-mono font-bold text-lg leading-none truncate"
          style={{ color: color || 'var(--text-primary)' }}
        >
          {value}
        </div>
        {sub && (
          <div className="font-mono text-[10px] mt-0.5 truncate" style={{ color: 'var(--text-muted)' }}>
            {sub}
          </div>
        )}
      </div>
    </div>
  )
}

function SkeletonCard() {
  return (
    <div className="flex items-center gap-3 px-4 py-3 rounded-lg flex-1"
         style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}>
      <div className="skeleton w-8 h-8 rounded flex-shrink-0" />
      <div className="flex-1">
        <div className="skeleton mb-1.5" style={{ width: 56, height: 10 }} />
        <div className="skeleton" style={{ width: 88, height: 20 }} />
      </div>
    </div>
  )
}

export default function HeroMetrics() {
  const account = useNVCStore(s => s.account)

  if (!account) {
    return (
      <div className="flex gap-3 px-4 py-3">
        <SkeletonCard /><SkeletonCard /><SkeletonCard />
      </div>
    )
  }

  const {
    equity, balance, unrealised_pl,
    daily_drawdown_pct: dd,
    weekly_drawdown_pct: wdd = 0,
    currency = 'USD',
    circuit_breaker: cb,
  } = account

  const fmt = (n: number) => n.toLocaleString('en', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  const pl = unrealised_pl ?? 0
  const plPositive = pl >= 0

  // Circuit breaker state
  const cbHard = cb?.hard_stop
  const cbHalt = !cb?.trading_allowed
  const cbWarn = cb?.weekly_limit_hit

  let cbLabel = 'ACTIVE'
  let cbColor = 'var(--bull)'
  let cbSub   = `DD ${dd.toFixed(2)}% / ${wdd.toFixed(2)}% wk`
  let cbBg    = 'var(--bg-card)'

  if (cbHard || cbHalt) {
    cbLabel = cbHard ? 'HARD STOP' : 'HALTED'
    cbColor = 'var(--bear)'
    cbBg    = 'rgba(229,72,62,0.06)'
  } else if (cbWarn) {
    cbLabel = 'HALF SIZE'
    cbColor = 'var(--accent)'
  } else if (dd >= 1.5) {
    cbLabel = 'WARNING'
    cbColor = 'var(--accent)'
  }

  return (
    <div className="flex gap-3 px-4 py-3 flex-shrink-0">
      {/* Equity */}
      {/* Equity — animated number */}
      <div
        className="stagger-item flex items-center gap-3 px-4 py-3 rounded-lg flex-1 min-w-0"
        style={{ '--stagger-i': 0, background: 'var(--bg-card)', border: '1px solid var(--border)' } as React.CSSProperties}
      >
        <div className="w-8 h-8 rounded flex items-center justify-center flex-shrink-0"
             style={{ background: 'var(--bg-elevated)' }}>
          <Activity size={15} style={{ color: 'var(--accent)' }} />
        </div>
        <div className="min-w-0">
          <div className="section-label mb-0.5">Account Equity</div>
          <div className="font-mono font-bold text-lg leading-none truncate"
               style={{ color: 'var(--text-primary)' }}>
            <AnimatedNumber value={equity} decimals={2} suffix={` ${currency}`} />
          </div>
          <div className="font-mono text-[10px] mt-0.5 truncate" style={{ color: 'var(--text-muted)' }}>
            Balance <AnimatedNumber value={balance} decimals={2} />
          </div>
        </div>
      </div>

      {/* Float P&L — animated */}
      <div
        className="stagger-item flex items-center gap-3 px-4 py-3 rounded-lg flex-1 min-w-0"
        style={{
          '--stagger-i': 1,
          background: plPositive ? 'rgba(46,168,74,0.04)' : 'rgba(229,72,62,0.04)',
          border: '1px solid var(--border)',
        } as React.CSSProperties}
      >
        <div className="w-8 h-8 rounded flex items-center justify-center flex-shrink-0"
             style={{ background: 'var(--bg-elevated)' }}>
          {plPositive
            ? <TrendingUp  size={15} style={{ color: 'var(--bull)' }} />
            : <TrendingDown size={15} style={{ color: 'var(--bear)' }} />}
        </div>
        <div className="min-w-0">
          <div className="section-label mb-0.5">Float P&L</div>
          <div className="font-mono font-bold text-lg leading-none truncate"
               style={{ color: plPositive ? 'var(--bull)' : 'var(--bear)' }}>
            {plPositive ? '+' : ''}
            <AnimatedNumber value={pl} decimals={2} suffix={` ${currency}`} />
          </div>
          <div className="font-mono text-[10px] mt-0.5 truncate" style={{ color: 'var(--text-muted)' }}>
            Daily DD <AnimatedNumber value={dd} decimals={2} suffix="%" />
          </div>
        </div>
      </div>

      {/* Circuit Breaker */}
      <div className="stagger-item" style={{ '--stagger-i': 2, flex: 1, minWidth: 0 } as React.CSSProperties}>
        <MetricCard
          label="Circuit Breaker"
          value={cbLabel}
          sub={cbSub}
          color={cbColor}
          icon={
            cbHard || cbHalt
              ? <ShieldOff size={15} style={{ color: 'var(--bear)' }} />
              : <Shield size={15} style={{ color: cbColor }} />
          }
          bg={cbBg}
        />
      </div>
    </div>
  )
}
