'use client'

import { useNVCStore } from '@/lib/store'

export default function AccountBar() {
  const { account } = useNVCStore()

  if (!account) {
    return (
      <div className="flex items-center gap-6">
        {[0, 1].map(i => (
          <div key={i} className="flex flex-col items-center gap-1">
            <div className="skeleton" style={{ width: 40, height: 10 }} />
            <div className="skeleton" style={{ width: 64, height: 14 }} />
          </div>
        ))}
      </div>
    )
  }

  const { equity, daily_drawdown_pct: dd } = account

  return (
    <div className="flex items-center gap-6 font-mono text-xs">
      <div className="flex flex-col items-center">
        <span style={{ color: 'var(--text-muted)' }}>EQUITY</span>
        <span className="font-semibold" style={{ color: 'var(--text-primary)' }}>
          ${equity.toLocaleString('en', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
        </span>
      </div>
      <div className="flex flex-col items-center">
        <span style={{ color: 'var(--text-muted)' }}>DAILY DD</span>
        <span className="font-semibold"
              style={{ color: dd > 2 ? 'var(--bear)' : dd > 1 ? 'var(--accent)' : 'var(--bull)' }}>
          -{dd.toFixed(2)}%
        </span>
      </div>
    </div>
  )
}
