'use client'

import { useState, useEffect, useRef } from 'react'
import { api } from '@/lib/api'
const SYMBOLS = ['GBPUSD', 'EURUSD', 'XAUUSD', 'USDJPY', 'USOIL']

interface Price {
  bid: number
  ask: number
  spread: number
}

function usePrevBid(sym: string, bid: number) {
  const ref = useRef<Record<string, number>>({})
  const prev = ref.current[sym]
  useEffect(() => { ref.current[sym] = bid })
  return prev
}

function Tick({ sym, p }: { sym: string; p: Price | null }) {
  const prevBid = usePrevBid(sym, p?.bid ?? 0)
  const [dir, setDir] = useState<'up' | 'down' | null>(null)

  useEffect(() => {
    if (!p || prevBid === undefined || p.bid === prevBid) return
    setDir(p.bid > prevBid ? 'up' : 'down')
    const t = setTimeout(() => setDir(null), 600)
    return () => clearTimeout(t)
  }, [p?.bid])

  if (!p) return (
    <div className="flex flex-col items-center px-3 border-r" style={{ borderColor: 'var(--border)' }}>
      <span className="text-xs font-mono font-semibold" style={{ color: 'var(--text-muted)' }}>{sym}</span>
      <div className="skeleton" style={{ width: 56, height: 12, marginTop: 2 }} />
    </div>
  )

  const color = dir === 'up' ? 'var(--bull)' : dir === 'down' ? 'var(--bear)' : 'var(--text-primary)'

  return (
    <div
      className={`flex flex-col items-center px-3 border-r ${dir ? `flash-${dir === 'up' ? 'bull' : 'bear'}` : ''}`}
      style={{ borderColor: 'var(--border)' }}
    >
      <span className="text-xs font-mono font-bold tracking-wider" style={{ color: 'var(--text-muted)' }}>{sym}</span>
      <span
        className="font-mono font-bold leading-none"
        style={{ fontSize: 11, color, letterSpacing: '0.02em' }}
      >
        {p.bid.toFixed(sym === 'USDJPY' ? 3 : sym === 'XAUUSD' || sym === 'USOIL' ? 2 : 5)}
      </span>
      <span className="font-mono" style={{ fontSize: 9, color: 'var(--text-muted)' }}>
        {p.spread.toFixed(1)}p
      </span>
    </div>
  )
}

export default function PriceStrip() {
  const [prices, setPrices] = useState<Record<string, Price | null>>({})

  useEffect(() => {
    const load = () =>
      api.get<Record<string, Price | null>>(`/prices?symbols=${SYMBOLS.join(',')}`)
        .then(d => setPrices(d))
        .catch(() => {})

    load()
    const t = setInterval(load, 5_000)
    return () => clearInterval(t)
  }, [])

  return (
    <div className="flex items-center h-full">
      {SYMBOLS.map(sym => (
        <Tick key={sym} sym={sym} p={prices[sym] ?? null} />
      ))}
    </div>
  )
}
