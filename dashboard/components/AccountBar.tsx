'use client'

import { useNVCStore } from '@/lib/store'

export default function AccountBar() {
  const { account } = useNVCStore()

  const equity = account?.equity ?? 0
  const dailyDD = account?.daily_drawdown_pct ?? 0

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
              style={{ color: dailyDD > 2 ? 'var(--bear)' : dailyDD > 1 ? 'var(--accent)' : 'var(--bull)' }}>
          -{dailyDD.toFixed(2)}%
        </span>
      </div>
    </div>
  )
}
