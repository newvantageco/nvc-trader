'use client'

import { useEffect, useState } from 'react'
import { api } from '@/lib/api'

interface Props {
  instrument: string
}

interface SentimentData {
  score: number        // -1.0 to +1.0
  normalised: number  // 0.0 to 1.0
  bias: string
  article_count: number
}

export default function SentimentGauge({ instrument }: Props) {
  const [data, setData] = useState<SentimentData | null>(null)

  useEffect(() => {
    const load = () =>
      api.get<SentimentData>(`/sentiment/${instrument}`)
        .then(d => setData(d))
        .catch(() => {})

    load()
    const interval = setInterval(load, 60_000)
    return () => clearInterval(interval)
  }, [instrument])

  const score = data?.score ?? 0
  const bias = data?.bias ?? 'neutral'
  const barWidth = Math.abs(score) * 100
  const isBull = bias === 'bullish'
  const isBear = bias === 'bearish'

  return (
    <div className="flex items-center gap-2 font-mono text-xs">
      <span className="w-14 text-right" style={{ color: 'var(--text-primary)' }}>
        {instrument}
      </span>

      {/* Bar chart */}
      <div className="flex-1 flex items-center gap-1">
        {/* Bear side */}
        <div className="flex-1 flex justify-end">
          {isBear && (
            <div
              className="h-2 rounded-l"
              style={{ width: `${barWidth}%`, background: 'var(--bear)' }}
            />
          )}
        </div>

        {/* Center line */}
        <div className="w-px h-3" style={{ background: 'var(--border-bright)' }} />

        {/* Bull side */}
        <div className="flex-1">
          {isBull && (
            <div
              className="h-2 rounded-r"
              style={{ width: `${barWidth}%`, background: 'var(--bull)' }}
            />
          )}
        </div>
      </div>

      <span
        className="w-12 text-xs font-semibold"
        style={{
          color: isBull ? 'var(--bull)' : isBear ? 'var(--bear)' : 'var(--neutral)',
        }}
      >
        {score >= 0 ? '+' : ''}{(score * 100).toFixed(0)}
      </span>
    </div>
  )
}
