'use client'

import { useEffect, useState, useCallback } from 'react'
import { TrendingUp, TrendingDown, Minus, RefreshCw, ChevronRight } from 'lucide-react'
import { useNVCStore } from '@/lib/store'
import { api, errorMessage } from '@/lib/api'

interface ScanResult {
  instrument: string
  score: number
  ta_score: number
  direction: 'BUY' | 'SELL' | 'NEUTRAL'
  tradeable: boolean
  edge_grade: string      // A++, A+, A, FAIL
  special_setup: string | null
  risk_app: string        // HIGH, NEUTRAL, LOW
  breakdown?: {
    ta: number
    sentiment: number
    momentum: number
    macro: number
  }
}

function gradeClass(grade: string): string {
  if (grade === 'A++') return 'grade-axx'
  if (grade === 'A+')  return 'grade-ax'
  if (grade === 'A')   return 'grade-a'
  return 'grade-fail'
}

function gradeColor(grade: string): string {
  if (grade === 'A++') return 'var(--grade-axx)'
  if (grade === 'A+')  return 'var(--grade-ax)'
  if (grade === 'A')   return 'var(--grade-a)'
  return 'var(--text-muted)'
}

function scoreBarColor(score: number): string {
  if (score >= 0.70) return 'var(--accent)'
  if (score >= 0.55) return 'var(--grade-a)'
  if (score >= 0.45) return 'var(--neutral)'
  return 'var(--bear)'
}

function DirectionIcon({ direction }: { direction: 'BUY' | 'SELL' | 'NEUTRAL' }) {
  if (direction === 'BUY')     return <TrendingUp  size={13} style={{ color: 'var(--bull)' }} />
  if (direction === 'SELL')    return <TrendingDown size={13} style={{ color: 'var(--bear)' }} />
  return <Minus size={13} style={{ color: 'var(--text-muted)' }} />
}

function SpecialBadge({ setup }: { setup: string | null }) {
  if (!setup) return null
  const labels: Record<string, string> = {
    INSTITUTIONAL_DIVERGENCE: 'INST ÷',
    BREAKOUT:                 'BREAKOUT',
    TURTLE_BREAKOUT_S2:       '🐢 S2',
    TURTLE_BREAKOUT_S1:       '🐢 S1',
    LIVERMORE_PIVOTAL:        'PIVOT',
    NEWS_AFTERMATH:           'NEWS+',
  }
  const label = labels[setup] || setup
  return (
    <span
      className="text-[9px] font-mono font-semibold px-1.5 py-0.5 rounded"
      style={{
        background: 'rgba(240,165,0,0.15)',
        color: 'var(--accent)',
        border: '1px solid rgba(240,165,0,0.25)',
        letterSpacing: '0.06em',
      }}
    >
      {label}
    </span>
  )
}

interface CardProps {
  result: ScanResult
  circuitOk: boolean
}

function OpportunityCard({ result, circuitOk }: CardProps) {
  const { instrument, score, ta_score, direction, tradeable, edge_grade, special_setup } = result
  const addToast = useNVCStore(s => s.addToast)
  const [executing, setExecuting] = useState(false)

  const canExecute = tradeable && circuitOk && direction !== 'NEUTRAL'

  const handleExecute = useCallback(async () => {
    if (!canExecute) return
    setExecuting(true)
    try {
      await api.post('/trigger', { trigger: `manual_${instrument}`, instrument })
      addToast({ type: 'success', title: 'Agent triggered', message: `Analysing ${instrument}...` })
    } catch (err) {
      addToast({ type: 'error', title: 'Trigger failed', message: errorMessage(err) })
    } finally {
      setExecuting(false)
    }
  }, [canExecute, instrument, addToast])

  const cardClass = [
    'card-opportunity',
    tradeable && direction === 'BUY'  ? 'bull-signal' : '',
    tradeable && direction === 'SELL' ? 'bear-signal' : '',
    tradeable                          ? 'tradeable'  : '',
  ].filter(Boolean).join(' ')

  return (
    <div className={cardClass} style={{ padding: '12px 14px' }}>
      {/* Row 1: instrument + grade + special */}
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className="font-mono font-bold text-sm" style={{ color: 'var(--text-primary)', letterSpacing: '0.04em' }}>
            {instrument}
          </span>
          {special_setup && <SpecialBadge setup={special_setup} />}
        </div>
        <span
          className={`font-mono font-bold text-[11px] px-2 py-0.5 rounded ${gradeClass(edge_grade)}`}
          style={{ letterSpacing: '0.06em' }}
        >
          {edge_grade || '—'}
        </span>
      </div>

      {/* Row 2: score bar */}
      <div className="score-bar mb-2.5">
        <div
          className="score-bar-fill"
          style={{
            width: `${score * 100}%`,
            background: scoreBarColor(score),
          }}
        />
      </div>

      {/* Row 3: metrics + action */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5">
            <DirectionIcon direction={direction} />
            <span
              className="font-mono text-xs font-semibold"
              style={{
                color: direction === 'BUY'  ? 'var(--bull)'
                     : direction === 'SELL' ? 'var(--bear)'
                     : 'var(--text-muted)',
              }}
            >
              {direction}
            </span>
          </div>
          <span className="font-mono text-xs" style={{ color: 'var(--text-muted)' }}>
            {(score * 100).toFixed(0)}% · TA {(ta_score * 100).toFixed(0)}%
          </span>
        </div>

        {/* Contextual action — only when edge passes + circuit OK */}
        {canExecute ? (
          <button
            className="btn-execute"
            onClick={handleExecute}
            disabled={executing}
            aria-label={`Trigger agent analysis for ${instrument}`}
          >
            {executing ? '...' : 'Analyse →'}
          </button>
        ) : tradeable && !circuitOk ? (
          <span
            className="text-[10px] font-mono"
            style={{ color: 'var(--bear)', letterSpacing: '0.06em' }}
          >
            CIRCUIT ✗
          </span>
        ) : (
          <span
            className="text-[10px] font-mono flex items-center gap-1"
            style={{ color: 'var(--text-muted)', letterSpacing: '0.06em' }}
          >
            MONITORING
          </span>
        )}
      </div>
    </div>
  )
}

function SkeletonCard() {
  return (
    <div className="card-opportunity" style={{ padding: '12px 14px' }}>
      <div className="flex items-center justify-between mb-2">
        <div className="skeleton" style={{ width: 72, height: 16 }} />
        <div className="skeleton" style={{ width: 36, height: 16 }} />
      </div>
      <div className="score-bar mb-2.5">
        <div className="score-bar-fill skeleton" style={{ width: '60%' }} />
      </div>
      <div className="flex items-center justify-between">
        <div className="skeleton" style={{ width: 100, height: 12 }} />
        <div className="skeleton" style={{ width: 56, height: 24 }} />
      </div>
    </div>
  )
}

export default function OpportunityFeed() {
  const [results, setResults]   = useState<ScanResult[]>([])
  const [loading, setLoading]   = useState(true)
  const [lastUpdate, setLast]   = useState<Date | null>(null)
  const account = useNVCStore(s => s.account)

  const circuitOk = !account?.circuit_breaker?.hard_stop &&
                    (account?.circuit_breaker?.trading_allowed !== false)

  const fetchScan = useCallback(async () => {
    try {
      const data = await api.get<{ signals?: ScanResult[] }>('/scan')
      const raw: ScanResult[] = data.signals || []

      // Sort: tradeable + high score first, then by score desc
      const sorted = [...raw].sort((a, b) => {
        if (a.tradeable !== b.tradeable) return a.tradeable ? -1 : 1
        return b.score - a.score
      })
      setResults(sorted)
      setLast(new Date())
    } catch {
      // silently fail — show stale data
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchScan()
    const t = setInterval(fetchScan, 60_000)
    return () => clearInterval(t)
  }, [fetchScan])

  const tradeable = results.filter(r => r.tradeable)
  const watching  = results.filter(r => !r.tradeable)

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2.5 border-b flex-shrink-0"
           style={{ borderColor: 'var(--border)' }}>
        <div className="flex items-center gap-2">
          <span className="section-label">Market Scan</span>
          {tradeable.length > 0 && (
            <span
              className="text-[10px] font-mono font-bold px-1.5 py-0.5 rounded"
              style={{ background: 'var(--accent-dim)', color: 'var(--accent)', border: '1px solid rgba(240,165,0,0.25)' }}
            >
              {tradeable.length} ready
            </span>
          )}
        </div>
        <div className="flex items-center gap-3">
          {lastUpdate && (
            <span className="text-[10px] font-mono" style={{ color: 'var(--text-muted)' }}>
              {lastUpdate.toLocaleTimeString('en', { hour: '2-digit', minute: '2-digit' })}
            </span>
          )}
          <button
            onClick={fetchScan}
            disabled={loading}
            aria-label="Refresh scan"
            className="btn-secondary flex items-center gap-1.5"
            style={{ padding: '4px 8px' }}
          >
            <RefreshCw size={11} className={loading ? 'animate-spin' : ''} />
            <span>Refresh</span>
          </button>
        </div>
      </div>

      {/* Feed */}
      <div className="flex-1 overflow-y-auto p-3 space-y-2">
        {loading ? (
          Array.from({ length: 6 }).map((_, i) => <SkeletonCard key={i} />)
        ) : results.length === 0 ? (
          <div className="text-center py-12 font-mono text-xs" style={{ color: 'var(--text-muted)' }}>
            No scan data — refresh to fetch
          </div>
        ) : (
          <>
            {/* Tradeable opportunities first */}
            {tradeable.length > 0 && (
              <>
                <div className="section-label px-1 pt-1 pb-1.5">
                  Opportunities ({tradeable.length})
                </div>
                {tradeable.map((r, i) => (
                  <div
                    key={r.instrument}
                    className="stagger-item"
                    style={{ '--stagger-i': i } as React.CSSProperties}
                  >
                    <OpportunityCard result={r} circuitOk={circuitOk} />
                  </div>
                ))}
              </>
            )}

            {/* Watching section */}
            {watching.length > 0 && (
              <>
                <div className="section-label px-1 pt-3 pb-1.5">
                  Monitoring ({watching.length})
                </div>
                {watching.map((r, i) => (
                  <div
                    key={r.instrument}
                    className="stagger-item"
                    style={{ '--stagger-i': tradeable.length + i } as React.CSSProperties}
                  >
                    <OpportunityCard result={r} circuitOk={circuitOk} />
                  </div>
                ))}
              </>
            )}
          </>
        )}
      </div>
    </div>
  )
}
