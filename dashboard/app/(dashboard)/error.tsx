'use client'

import { useEffect } from 'react'
import { AlertTriangle, RefreshCw } from 'lucide-react'

interface Props {
  error: Error & { digest?: string }
  reset: () => void
}

export default function DashboardError({ error, reset }: Props) {
  useEffect(() => {
    // Log to console in dev; wire to Sentry in production
    console.error('[DashboardError]', error)
  }, [error])

  return (
    <div
      className="flex flex-col items-center justify-center h-full gap-4 font-mono"
      style={{ background: 'var(--bg-base)', color: 'var(--text-secondary)' }}
    >
      <div
        className="flex items-center justify-center w-10 h-10 rounded-lg"
        style={{ background: 'rgba(229,72,62,0.1)', border: '1px solid rgba(229,72,62,0.25)' }}
      >
        <AlertTriangle size={18} style={{ color: 'var(--bear)' }} />
      </div>

      <div className="text-center">
        <p className="text-xs font-semibold mb-1" style={{ color: 'var(--text-primary)' }}>
          Something went wrong
        </p>
        <p className="text-[11px]" style={{ color: 'var(--text-muted)' }}>
          {error.message || 'An unexpected error occurred'}
        </p>
        {error.digest && (
          <p className="text-[10px] mt-1" style={{ color: 'var(--text-muted)' }}>
            ref: {error.digest}
          </p>
        )}
      </div>

      <button
        onClick={reset}
        className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs transition-opacity hover:opacity-80"
        style={{
          background: 'var(--bg-elevated)',
          border:     '1px solid var(--border)',
          color:      'var(--text-secondary)',
        }}
      >
        <RefreshCw size={11} />
        Try again
      </button>
    </div>
  )
}
