'use client'

/**
 * AgentCycleProgress
 *
 * Shows a collapsible progress card whenever an agent cycle is in flight.
 * Polls /cycles?limit=1 every 5s while running, slows to 30s at rest.
 *
 * Adapted from SightSync CampaignProgressWidget — no Supabase Realtime needed.
 * Uses polling + dead reckoning since the trading backend is REST-only.
 */

import { useEffect, useRef, useState, useCallback } from 'react'
import { Zap, CheckCircle2, X, RefreshCw } from 'lucide-react'
import { api } from '@/lib/api'

interface Cycle {
  cycle_id:        string
  timestamp:       string
  status:          string   // 'running' | 'complete' | 'error'
  trigger:         string
  trades_executed: number
  instruments_scanned?: number
  duration_sec?:   number
  error_msg?:      string
}

interface Stage {
  label:  string
  sub:    string
  done:   boolean
  active: boolean
  error?: boolean
}

function stagesFromCycle(cycle: Cycle | null): Stage[] {
  if (!cycle) return []
  const s = cycle.status
  return [
    {
      label:  'Market Scan',
      sub:    `${cycle.instruments_scanned ?? '—'} instruments analysed`,
      done:   s !== 'running',
      active: s === 'running',
    },
    {
      label:  'Claude Analysis',
      sub:    'Confluence scoring · signal generation',
      done:   s === 'complete',
      active: false,
    },
    {
      label:  'Order Execution',
      sub:    `${cycle.trades_executed} trade${cycle.trades_executed !== 1 ? 's' : ''} placed`,
      done:   s === 'complete',
      active: false,
      error:  s === 'error',
    },
  ]
}

export default function AgentCycleProgress() {
  const [cycle,     setCycle]     = useState<Cycle | null>(null)
  const [dismissed, setDismissed] = useState<string | null>(null)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const fetchCycle = useCallback(async () => {
    try {
      const d = await api.get<{ cycles?: Cycle[] }>('/cycles?limit=1')
      const latest: Cycle | undefined = d.cycles?.[0]
      if (!latest) return

      // Only show if the cycle started within the last 5 minutes
      const age = Date.now() - new Date(latest.timestamp).getTime()
      if (age > 5 * 60 * 1000 && latest.status !== 'running') {
        setCycle(null)
        return
      }
      setCycle(latest)
    } catch { /* silent */ }
  }, [])

  useEffect(() => {
    fetchCycle()

    function schedule() {
      if (intervalRef.current) clearInterval(intervalRef.current)
      const running = cycle?.status === 'running'
      intervalRef.current = setInterval(fetchCycle, running ? 5_000 : 30_000)
    }
    schedule()
    return () => { if (intervalRef.current) clearInterval(intervalRef.current) }
  }, [fetchCycle, cycle?.status])

  if (!cycle) return null
  if (dismissed === cycle.cycle_id) return null

  const running  = cycle.status === 'running'
  const errored  = cycle.status === 'error'
  const done     = cycle.status === 'complete'
  const stages   = stagesFromCycle(cycle)

  const borderColor = errored ? 'rgba(229,72,62,0.4)'
    : done    ? 'rgba(46,168,74,0.3)'
    : 'rgba(240,165,0,0.3)'

  const bgColor = errored ? 'rgba(229,72,62,0.05)'
    : done    ? 'rgba(46,168,74,0.04)'
    : 'rgba(240,165,0,0.04)'

  return (
    <div
      className="mx-4 mt-3 rounded-lg overflow-hidden flex-shrink-0 transition-all duration-300"
      style={{ border: `1px solid ${borderColor}`, background: bgColor }}
    >
      {/* Header */}
      <div
        className="flex items-center justify-between px-4 py-2.5 border-b"
        style={{ borderColor }}
      >
        <div className="flex items-center gap-2">
          {done ? (
            <CheckCircle2 size={13} style={{ color: 'var(--bull)' }} />
          ) : errored ? (
            <X size={13} style={{ color: 'var(--bear)' }} />
          ) : (
            <RefreshCw size={13} className="animate-spin" style={{ color: 'var(--accent)' }} />
          )}
          <span className="text-xs font-semibold font-mono" style={{ color: 'var(--text-primary)' }}>
            {done ? 'Cycle complete' : errored ? 'Cycle error' : 'Agent running…'}
          </span>
          {/* Live / connecting dot */}
          <span
            className={`inline-flex items-center gap-1 text-[10px] font-mono px-1.5 py-0.5 rounded`}
            style={{
              background: running ? 'var(--accent-dim)' : 'var(--bg-elevated)',
              color:      running ? 'var(--accent)' : 'var(--text-muted)',
              border:     `1px solid ${running ? 'rgba(240,165,0,0.25)' : 'var(--border)'}`,
            }}
          >
            {running && <span className="w-1.5 h-1.5 rounded-full animate-pulse" style={{ background: 'var(--accent)' }} />}
            {running ? 'LIVE' : done ? 'DONE' : 'ERROR'}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[10px] font-mono" style={{ color: 'var(--text-muted)' }}>
            {cycle.trigger}
          </span>
          <button onClick={() => setDismissed(cycle.cycle_id)} style={{ color: 'var(--text-muted)' }}>
            <X size={12} />
          </button>
        </div>
      </div>

      {/* Stages */}
      <div className="flex items-center gap-0 px-4 py-3">
        {stages.map((stage, i) => {
          const isLast = i === stages.length - 1
          return (
            <div key={stage.label} className="flex items-center gap-1.5 flex-1">
              {/* Node */}
              <div className="flex flex-col items-center flex-shrink-0">
                <div
                  className="w-6 h-6 rounded flex items-center justify-center"
                  style={{
                    background: stage.done  ? 'rgba(46,168,74,0.15)'
                      : stage.active        ? 'rgba(240,165,0,0.15)'
                      : stage.error         ? 'rgba(229,72,62,0.15)'
                      : 'var(--bg-elevated)',
                    border: `1px solid ${
                      stage.done   ? 'rgba(46,168,74,0.4)'
                      : stage.active ? 'rgba(240,165,0,0.4)'
                      : stage.error  ? 'rgba(229,72,62,0.4)'
                      : 'var(--border)'
                    }`,
                  }}
                >
                  {stage.done ? (
                    <CheckCircle2 size={11} style={{ color: 'var(--bull)' }} />
                  ) : stage.active ? (
                    <span className="w-2 h-2 rounded-full animate-pulse" style={{ background: 'var(--accent)' }} />
                  ) : stage.error ? (
                    <X size={11} style={{ color: 'var(--bear)' }} />
                  ) : (
                    <span className="w-1.5 h-1.5 rounded-full" style={{ background: 'var(--border)' }} />
                  )}
                </div>
              </div>

              {/* Label */}
              <div className="min-w-0 flex-1">
                <p className="text-[10px] font-semibold font-mono truncate"
                   style={{ color: stage.done || stage.active ? 'var(--text-primary)' : 'var(--text-muted)' }}>
                  {stage.label}
                </p>
                <p className="text-[9px] font-mono truncate" style={{ color: 'var(--text-muted)' }}>
                  {stage.sub}
                </p>
              </div>

              {/* Connector */}
              {!isLast && (
                <div
                  className="flex-shrink-0 mx-1"
                  style={{ width: 16, height: 1, background: stage.done ? 'var(--bull)' : 'var(--border)' }}
                />
              )}
            </div>
          )
        })}
      </div>

      {/* Error message */}
      {errored && cycle.error_msg && (
        <div className="px-4 pb-3">
          <p className="text-[10px] font-mono" style={{ color: 'var(--bear)' }}>
            {cycle.error_msg}
          </p>
        </div>
      )}

      {/* Duration */}
      {done && cycle.duration_sec && (
        <div className="px-4 pb-3">
          <p className="text-[10px] font-mono" style={{ color: 'var(--text-muted)' }}>
            Completed in {cycle.duration_sec}s · {cycle.trades_executed} trade{cycle.trades_executed !== 1 ? 's' : ''} executed
          </p>
        </div>
      )}
    </div>
  )
}
