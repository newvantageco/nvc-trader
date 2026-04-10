'use client'

import { useEffect, useRef } from 'react'
import { useNVCStore } from '@/lib/store'

export default function SignalTape() {
  const { signals } = useNVCStore()
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (ref.current) ref.current.scrollLeft = ref.current.scrollWidth
  }, [signals])

  if (!signals.length) {
    return (
      <div className="text-xs font-mono" style={{ color: 'var(--text-muted)' }}>
        Waiting for signals...
      </div>
    )
  }

  return (
    <div ref={ref} className="flex gap-3 overflow-x-auto pb-1 scrollbar-hide">
      {signals.slice(-20).map((s, i) => (
        <div
          key={i}
          className="flex-shrink-0 flex items-center gap-2 px-3 py-1.5 rounded border font-mono text-xs"
          style={{
            borderColor: s.direction === 'BUY' ? 'var(--bull)' : 'var(--bear)',
            background: s.direction === 'BUY' ? 'rgba(16,185,129,0.08)' : 'rgba(239,68,68,0.08)',
          }}
        >
          <span
            className="font-bold text-xs px-1.5 py-0.5 rounded"
            style={{
              background: s.direction === 'BUY' ? 'var(--bull)' : 'var(--bear)',
              color: '#fff',
            }}
          >
            {s.direction}
          </span>
          <span style={{ color: 'var(--text-primary)' }}>{s.instrument}</span>
          <span style={{ color: 'var(--text-secondary)' }}>
            {(s.score * 100).toFixed(0)}%
          </span>
          <span style={{ color: 'var(--text-muted)' }}>
            {new Date(s.timestamp).toLocaleTimeString('en', { hour: '2-digit', minute: '2-digit' })}
          </span>
        </div>
      ))}
    </div>
  )
}
