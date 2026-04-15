'use client'

import { useState, useRef, useEffect } from 'react'
import { X } from 'lucide-react'
import { useNVCStore } from '@/lib/store'
import { api, errorMessage } from '@/lib/api'

function usePrevious<T>(value: T) {
  const ref = useRef<T>(value)
  useEffect(() => { ref.current = value })
  return ref.current
}

function PnlCell({ profit }: { profit: number }) {
  const prev    = usePrevious(profit)
  const [flash, setFlash] = useState<'bull' | 'bear' | null>(null)

  useEffect(() => {
    if (prev === undefined || profit === prev) return
    setFlash(profit > prev ? 'bull' : 'bear')
    const t = setTimeout(() => setFlash(null), 600)
    return () => clearTimeout(t)
  }, [profit, prev])

  return (
    <td
      className={`py-2 text-right font-semibold ${flash ? `flash-${flash}` : ''}`}
      style={{ color: profit >= 0 ? 'var(--bull)' : 'var(--bear)' }}
    >
      {profit >= 0 ? '+' : ''}{profit.toFixed(2)}
    </td>
  )
}

export default function PositionTable() {
  const { positions } = useNVCStore()
  const addToast = useNVCStore(s => s.addToast)
  const [closing, setClosing] = useState<Set<number>>(new Set())

  const handleClose = async (ticket: number, instrument: string) => {
    setClosing(prev => new Set(prev).add(ticket))
    try {
      const data = await api.delete<{ status: string; reason?: string }>(`/positions/${ticket}/close`)
      if (data.status === 'CLOSED' || data.status === 'CLOSE_DRY_RUN') {
        addToast({ type: 'success', title: 'Position closed', message: `${instrument} #${ticket}` })
      } else {
        addToast({ type: 'error', title: 'Close failed', message: data.reason || 'Unknown error' })
      }
    } catch (err) {
      addToast({ type: 'error', title: 'Close failed', message: errorMessage(err) })
    } finally {
      setClosing(prev => {
        const next = new Set(prev)
        next.delete(ticket)
        return next
      })
    }
  }

  if (!positions.length) {
    return (
      <div className="text-xs font-mono text-center py-8"
           style={{ color: 'var(--text-muted)' }}>
        No open positions
      </div>
    )
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full font-mono text-xs min-w-[640px]">
        <thead>
          <tr style={{ color: 'var(--text-muted)', borderBottom: '1px solid var(--border)' }}>
            <th className="text-left py-1.5 pr-4">Instrument</th>
            <th className="text-left py-1.5 pr-4">Dir</th>
            <th className="text-right py-1.5 pr-4">Lots</th>
            <th className="text-right py-1.5 pr-4">Entry</th>
            <th className="text-right py-1.5 pr-4">Current</th>
            <th className="text-right py-1.5 pr-4">SL</th>
            <th className="text-right py-1.5 pr-4">TP</th>
            <th className="text-right py-1.5 pr-4">P&L</th>
            <th className="py-1.5 w-8" />
          </tr>
        </thead>
        <tbody>
          {positions.map((p, i) => {
            const isClosing = closing.has(p.ticket)
            return (
              <tr
                key={p.ticket ?? i}
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
                <PnlCell profit={p.profit} />
                <td className="py-2 pl-2">
                  <button
                    onClick={() => handleClose(p.ticket, p.instrument)}
                    disabled={isClosing}
                    aria-label={`Close ${p.instrument} position`}
                    className="w-6 h-6 flex items-center justify-center rounded transition-opacity disabled:opacity-40 hover:opacity-80"
                    style={{ background: 'rgba(239,68,68,0.15)', color: 'var(--bear)' }}
                  >
                    {isClosing
                      ? <span className="text-xs animate-spin">⟳</span>
                      : <X size={11} />
                    }
                  </button>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
