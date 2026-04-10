'use client'

import { useNVCStore } from '@/lib/store'

export default function PositionTable() {
  const { positions } = useNVCStore()

  if (!positions.length) {
    return (
      <div className="text-xs font-mono text-center py-8"
           style={{ color: 'var(--text-muted)' }}>
        No open positions
      </div>
    )
  }

  return (
    <table className="w-full font-mono text-xs">
      <thead>
        <tr style={{ color: 'var(--text-muted)', borderBottom: '1px solid var(--border)' }}>
          <th className="text-left py-1.5 pr-4">Instrument</th>
          <th className="text-left py-1.5 pr-4">Dir</th>
          <th className="text-right py-1.5 pr-4">Lots</th>
          <th className="text-right py-1.5 pr-4">Entry</th>
          <th className="text-right py-1.5 pr-4">Current</th>
          <th className="text-right py-1.5 pr-4">SL</th>
          <th className="text-right py-1.5 pr-4">TP</th>
          <th className="text-right py-1.5">P&L</th>
        </tr>
      </thead>
      <tbody>
        {positions.map((p, i) => (
          <tr
            key={i}
            className="border-b"
            style={{ borderColor: 'var(--border)' }}
          >
            <td className="py-2 pr-4 font-semibold" style={{ color: 'var(--text-primary)' }}>
              {p.instrument}
            </td>
            <td className="py-2 pr-4">
              <span
                className="px-1.5 py-0.5 rounded text-xs font-bold"
                style={{
                  background: p.direction === 'BUY' ? 'rgba(16,185,129,0.15)' : 'rgba(239,68,68,0.15)',
                  color: p.direction === 'BUY' ? 'var(--bull)' : 'var(--bear)',
                }}
              >
                {p.direction}
              </span>
            </td>
            <td className="py-2 pr-4 text-right" style={{ color: 'var(--text-secondary)' }}>
              {p.lot_size.toFixed(2)}
            </td>
            <td className="py-2 pr-4 text-right" style={{ color: 'var(--text-secondary)' }}>
              {p.entry_price.toFixed(5)}
            </td>
            <td className="py-2 pr-4 text-right" style={{ color: 'var(--text-primary)' }}>
              {p.current_price.toFixed(5)}
            </td>
            <td className="py-2 pr-4 text-right" style={{ color: 'var(--bear)' }}>
              {p.stop_loss.toFixed(5)}
            </td>
            <td className="py-2 pr-4 text-right" style={{ color: 'var(--bull)' }}>
              {p.take_profit.toFixed(5)}
            </td>
            <td
              className="py-2 text-right font-semibold"
              style={{ color: p.profit >= 0 ? 'var(--bull)' : 'var(--bear)' }}
            >
              {p.profit >= 0 ? '+' : ''}{p.profit.toFixed(2)}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
