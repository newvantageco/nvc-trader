'use client'

import { useEffect, useRef, useState, useCallback } from 'react'
import { signOut } from 'next-auth/react'
import {
  Brain, Cpu, Activity, TrendingUp, TrendingDown,
  Zap, AlertTriangle, CheckCircle, Clock, LogOut,
  ChevronRight, BarChart2, Wifi, WifiOff
} from 'lucide-react'

// ── Types ─────────────────────────────────────────────────────────────────────

interface StreamEvent {
  type:      string
  timestamp: string
  [key: string]: unknown
}

interface ThinkingBlock {
  id:   string
  step: number
  text: string
  ts:   string
}

interface ToolCallBlock {
  id:         string
  tool:       string
  inputs:     Record<string, unknown>
  step:       number
  ts:         string
  resultPreview?: string
}

interface ScoreBlock {
  id:         string
  type:       'sentiment' | 'technical'
  instrument: string
  score?:     number
  bias?:      string
  ta_score?:  number
  ts:         string
}

interface TradeBlock {
  id:         string
  status:     string
  instrument: string
  direction?: string
  lot_size?:  number
  fill_price?: number
  score?:     number
  reason?:    string
  ts:         string
}

// ── Helpers ───────────────────────────────────────────────────────────────────

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

let _uid = 0
const uid = () => `${Date.now()}-${++_uid}`

function fmt(ts: string) {
  return new Date(ts).toLocaleTimeString('en-GB', { hour12: false })
}

function ScoreBar({ value, max = 1 }: { value: number; max?: number }) {
  const pct  = Math.min(Math.abs(value / max) * 100, 100)
  const bull = value > 0
  return (
    <div className="flex items-center gap-2">
      <div
        className="h-1.5 rounded-full flex-1 overflow-hidden"
        style={{ background: 'var(--bg-elevated)' }}
      >
        <div
          className="h-full rounded-full transition-all duration-700"
          style={{
            width:      `${pct}%`,
            background: bull ? 'var(--bull)' : 'var(--bear)',
          }}
        />
      </div>
      <span
        className="text-xs font-mono w-10 text-right"
        style={{ color: bull ? 'var(--bull)' : 'var(--bear)' }}
      >
        {value > 0 ? '+' : ''}{(value * 100).toFixed(0)}
      </span>
    </div>
  )
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export default function BrainPage() {
  const [connected,     setConnected]     = useState(false)
  const [running,       setRunning]       = useState(false)
  const [phase,         setPhase]         = useState('idle')
  const [iterations,    setIterations]    = useState(0)
  const [tradesCount,   setTradesCount]   = useState(0)

  const [thinking,      setThinking]      = useState<ThinkingBlock[]>([])
  const [toolCalls,     setToolCalls]     = useState<ToolCallBlock[]>([])
  const [scores,        setScores]        = useState<ScoreBlock[]>([])
  const [trades,        setTrades]        = useState<TradeBlock[]>([])
  const [statusLog,     setStatusLog]     = useState<{ id: string; msg: string; ts: string }[]>([])

  const esRef         = useRef<EventSource | null>(null)
  const thinkingRef   = useRef<HTMLDivElement>(null)
  const toolsRef      = useRef<HTMLDivElement>(null)

  // Auto-scroll thinking panel
  useEffect(() => {
    thinkingRef.current?.scrollTo({ top: thinkingRef.current.scrollHeight, behavior: 'smooth' })
  }, [thinking])

  useEffect(() => {
    toolsRef.current?.scrollTo({ top: toolsRef.current.scrollHeight, behavior: 'smooth' })
  }, [toolCalls])

  const handleEvent = useCallback((raw: string) => {
    let evt: StreamEvent
    try { evt = JSON.parse(raw) } catch { return }

    const ts = evt.timestamp as string ?? new Date().toISOString()

    switch (evt.type) {
      case 'status':
        setPhase((evt.phase as string) ?? 'running')
        setStatusLog(prev => [...prev.slice(-49), { id: uid(), msg: evt.message as string, ts }])
        break

      case 'thinking':
        setIterations(evt.step as number ?? 0)
        setThinking(prev => [...prev, { id: uid(), step: evt.step as number, text: evt.text as string, ts }])
        break

      case 'tool_call':
        setToolCalls(prev => [...prev, {
          id:     uid(),
          tool:   evt.tool as string,
          inputs: evt.inputs as Record<string, unknown> ?? {},
          step:   evt.step as number,
          ts,
        }])
        break

      case 'tool_result':
        // Attach preview to most recent matching tool call
        setToolCalls(prev => {
          const copy = [...prev]
          const idx  = copy.map(t => t.tool).lastIndexOf(evt.tool as string)
          if (idx !== -1) copy[idx] = { ...copy[idx], resultPreview: evt.preview as string }
          return copy
        })
        break

      case 'score':
        setScores(prev => [...prev.slice(-39), {
          id:         uid(),
          type:       evt.type2 as 'sentiment' | 'technical' ?? (evt as unknown as ScoreBlock).type,
          instrument: evt.instrument as string,
          score:      evt.score as number,
          bias:       evt.bias as string,
          ta_score:   evt.ta_score as number,
          ts,
        }])
        break

      case 'trade':
        setTrades(prev => [...prev, {
          id:         uid(),
          status:     evt.status as string,
          instrument: evt.instrument as string,
          direction:  evt.direction as string,
          lot_size:   evt.lot_size as number,
          fill_price: evt.fill_price as number,
          score:      evt.score as number,
          reason:     evt.reason as string,
          ts,
        }])
        if ((evt.status as string) === 'FILLED') setTradesCount(c => c + 1)
        break

      case 'done':
        setRunning(false)
        setPhase('done')
        setTradesCount((evt.trades_executed as number) ?? 0)
        break

      case 'error':
        setStatusLog(prev => [...prev.slice(-49), { id: uid(), msg: `ERROR: ${evt.message}`, ts }])
        setRunning(false)
        setPhase('error')
        break
    }
  }, [])

  const startStream = useCallback(() => {
    if (esRef.current) { esRef.current.close(); esRef.current = null }

    // Reset state
    setThinking([])
    setToolCalls([])
    setScores([])
    setTrades([])
    setStatusLog([])
    setIterations(0)
    setTradesCount(0)
    setRunning(true)
    setPhase('init')

    const es = new EventSource(`${API_URL}/agent/stream?trigger=brain-manual`)
    esRef.current = es

    es.onopen    = ()  => setConnected(true)
    es.onerror   = ()  => { setConnected(false); setRunning(false) }
    es.onmessage = (e) => handleEvent(e.data)
  }, [handleEvent])

  const stopStream = useCallback(() => {
    esRef.current?.close()
    esRef.current = null
    setRunning(false)
    setConnected(false)
    setPhase('stopped')
  }, [])

  useEffect(() => () => esRef.current?.close(), [])

  // ── Derived ────────────────────────────────────────────────────────────────

  const latestStatus = statusLog[statusLog.length - 1]?.msg ?? 'Idle — ready'

  const recentScores = scores.slice(-8)

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <div className="flex flex-col h-full" style={{ background: 'var(--bg-base)', color: 'var(--text-primary)' }}>

      {/* ── Top bar ── */}
      <div
        className="flex items-center justify-between px-4 py-2 border-b flex-shrink-0"
        style={{ borderColor: 'var(--border)', background: 'var(--bg-surface)' }}
      >
        <div className="flex items-center gap-3">
          <Brain size={18} style={{ color: 'var(--accent)' }} />
          <span className="font-mono text-sm font-semibold" style={{ color: 'var(--accent)' }}>
            BRAIN — Live Reasoning Engine
          </span>
          <span
            className="text-xs px-2 py-0.5 rounded font-mono"
            style={{
              background: running ? 'rgba(16,185,129,0.1)' : 'var(--bg-elevated)',
              color:      running ? 'var(--bull)'           : 'var(--text-muted)',
              border:     `1px solid ${running ? 'rgba(16,185,129,0.3)' : 'var(--border)'}`,
            }}
          >
            {phase.toUpperCase()}
          </span>
        </div>

        <div className="flex items-center gap-3">
          {/* Connection indicator */}
          {connected
            ? <Wifi size={14} style={{ color: 'var(--bull)' }} />
            : <WifiOff size={14} style={{ color: 'var(--text-muted)' }} />
          }

          <span className="text-xs font-mono" style={{ color: 'var(--text-muted)' }}>
            step {iterations} · {tradesCount} trade{tradesCount !== 1 ? 's' : ''}
          </span>

          {!running ? (
            <button
              onClick={startStream}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-semibold transition-opacity"
              style={{ background: 'var(--accent)', color: '#000' }}
            >
              <Zap size={12} />
              Run Cycle
            </button>
          ) : (
            <button
              onClick={stopStream}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-semibold"
              style={{ background: 'rgba(239,68,68,0.15)', color: 'var(--bear)', border: '1px solid rgba(239,68,68,0.3)' }}
            >
              Stop
            </button>
          )}

          <button
            onClick={() => signOut({ callbackUrl: '/login' })}
            className="flex items-center gap-1 px-2 py-1.5 rounded text-xs transition-opacity"
            style={{ color: 'var(--text-muted)' }}
            title="Sign out"
          >
            <LogOut size={13} />
          </button>
        </div>
      </div>

      {/* ── Status ticker ── */}
      <div
        className="flex items-center gap-2 px-4 py-1.5 border-b flex-shrink-0 overflow-hidden"
        style={{ borderColor: 'var(--border)', background: 'var(--bg-surface)' }}
      >
        {running && (
          <div className="w-1.5 h-1.5 rounded-full animate-pulse" style={{ background: 'var(--accent)' }} />
        )}
        <span className="text-xs font-mono truncate" style={{ color: 'var(--text-muted)' }}>
          {latestStatus}
        </span>
      </div>

      {/* ── Main 3-column grid ── */}
      <div className="flex-1 grid overflow-hidden" style={{ gridTemplateColumns: '1fr 320px 280px' }}>

        {/* ── Column 1: Thinking stream ── */}
        <div className="flex flex-col border-r overflow-hidden" style={{ borderColor: 'var(--border)' }}>
          <div
            className="flex items-center gap-2 px-4 py-2 border-b flex-shrink-0"
            style={{ borderColor: 'var(--border)' }}
          >
            <Cpu size={13} style={{ color: 'var(--accent)' }} />
            <span className="text-xs font-semibold uppercase tracking-wider" style={{ color: 'var(--text-muted)' }}>
              Claude Reasoning
            </span>
          </div>

          <div ref={thinkingRef} className="flex-1 overflow-y-auto p-4 flex flex-col gap-3">
            {thinking.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-full gap-3 opacity-30">
                <Brain size={32} style={{ color: 'var(--accent)' }} />
                <span className="text-xs font-mono" style={{ color: 'var(--text-muted)' }}>
                  Press "Run Cycle" to watch Claude think
                </span>
              </div>
            ) : (
              thinking.map(block => (
                <div key={block.id} className="flex flex-col gap-1">
                  <div className="flex items-center gap-2">
                    <span
                      className="text-xs font-mono px-1.5 py-0.5 rounded"
                      style={{ background: 'rgba(245,158,11,0.1)', color: 'var(--accent)', border: '1px solid rgba(245,158,11,0.2)' }}
                    >
                      step {block.step}
                    </span>
                    <span className="text-xs" style={{ color: 'var(--text-muted)' }}>{fmt(block.ts)}</span>
                  </div>
                  <div
                    className="text-xs leading-relaxed font-mono whitespace-pre-wrap rounded p-3"
                    style={{
                      background:   'var(--bg-surface)',
                      color:        'var(--text-primary)',
                      border:       '1px solid var(--border)',
                      borderLeft:   '2px solid var(--accent)',
                    }}
                  >
                    {block.text}
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* ── Column 2: Tool calls + Trades ── */}
        <div className="flex flex-col border-r overflow-hidden" style={{ borderColor: 'var(--border)' }}>

          {/* Tool calls section */}
          <div
            className="flex items-center gap-2 px-3 py-2 border-b flex-shrink-0"
            style={{ borderColor: 'var(--border)' }}
          >
            <Activity size={13} style={{ color: 'var(--accent)' }} />
            <span className="text-xs font-semibold uppercase tracking-wider" style={{ color: 'var(--text-muted)' }}>
              Tool Calls
            </span>
          </div>

          <div ref={toolsRef} className="flex-1 overflow-y-auto p-3 flex flex-col gap-2" style={{ maxHeight: '55%' }}>
            {toolCalls.length === 0 ? (
              <div className="text-xs font-mono text-center py-6 opacity-30" style={{ color: 'var(--text-muted)' }}>
                No tool calls yet
              </div>
            ) : (
              toolCalls.slice(-20).map(tc => (
                <div
                  key={tc.id}
                  className="rounded p-2.5 flex flex-col gap-1"
                  style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)' }}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-1.5">
                      <ChevronRight size={11} style={{ color: 'var(--accent)' }} />
                      <span className="text-xs font-mono font-semibold" style={{ color: 'var(--accent)' }}>
                        {tc.tool}
                      </span>
                    </div>
                    <div className="flex items-center gap-1.5">
                      {tc.resultPreview && (
                        <CheckCircle size={10} style={{ color: 'var(--bull)' }} />
                      )}
                      <span className="text-xs" style={{ color: 'var(--text-muted)' }}>{fmt(tc.ts)}</span>
                    </div>
                  </div>

                  {/* Key inputs */}
                  {Object.keys(tc.inputs).length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-0.5">
                      {Object.entries(tc.inputs).slice(0, 3).map(([k, v]) => (
                        <span
                          key={k}
                          className="text-xs px-1.5 py-0.5 rounded font-mono"
                          style={{ background: 'var(--bg-elevated)', color: 'var(--text-secondary)' }}
                        >
                          {k}={String(v).slice(0, 16)}
                        </span>
                      ))}
                    </div>
                  )}

                  {tc.resultPreview && (
                    <div className="text-xs font-mono truncate mt-0.5" style={{ color: 'var(--bull)' }}>
                      ↳ {tc.resultPreview}
                    </div>
                  )}
                </div>
              ))
            )}
          </div>

          {/* Divider */}
          <div className="border-t" style={{ borderColor: 'var(--border)' }} />

          {/* Trades section */}
          <div
            className="flex items-center gap-2 px-3 py-2 border-b flex-shrink-0"
            style={{ borderColor: 'var(--border)' }}
          >
            <Zap size={13} style={{ color: 'var(--accent)' }} />
            <span className="text-xs font-semibold uppercase tracking-wider" style={{ color: 'var(--text-muted)' }}>
              Executions
            </span>
            {tradesCount > 0 && (
              <span
                className="ml-auto text-xs font-mono px-1.5 py-0.5 rounded"
                style={{ background: 'rgba(16,185,129,0.1)', color: 'var(--bull)' }}
              >
                {tradesCount} filled
              </span>
            )}
          </div>

          <div className="overflow-y-auto p-3 flex flex-col gap-2" style={{ maxHeight: '45%' }}>
            {trades.length === 0 ? (
              <div className="text-xs font-mono text-center py-6 opacity-30" style={{ color: 'var(--text-muted)' }}>
                No executions this cycle
              </div>
            ) : (
              trades.map(t => (
                <div
                  key={t.id}
                  className="rounded p-2.5"
                  style={{
                    background: t.status === 'FILLED'
                      ? 'rgba(16,185,129,0.05)'
                      : 'rgba(239,68,68,0.05)',
                    border: `1px solid ${t.status === 'FILLED' ? 'rgba(16,185,129,0.2)' : 'rgba(239,68,68,0.2)'}`,
                  }}
                >
                  <div className="flex items-center justify-between mb-1">
                    <div className="flex items-center gap-1.5">
                      {t.direction === 'BUY'
                        ? <TrendingUp size={12} style={{ color: 'var(--bull)' }} />
                        : <TrendingDown size={12} style={{ color: 'var(--bear)' }} />
                      }
                      <span className="text-xs font-mono font-semibold" style={{ color: 'var(--text-primary)' }}>
                        {t.instrument}
                      </span>
                      <span
                        className="text-xs font-mono"
                        style={{ color: t.direction === 'BUY' ? 'var(--bull)' : 'var(--bear)' }}
                      >
                        {t.direction}
                      </span>
                    </div>
                    <span
                      className="text-xs font-mono px-1.5 py-0.5 rounded"
                      style={{
                        background: t.status === 'FILLED' ? 'rgba(16,185,129,0.1)' : 'rgba(239,68,68,0.1)',
                        color:      t.status === 'FILLED' ? 'var(--bull)'           : 'var(--bear)',
                      }}
                    >
                      {t.status}
                    </span>
                  </div>

                  {t.fill_price && (
                    <div className="text-xs font-mono" style={{ color: 'var(--text-muted)' }}>
                      @ {t.fill_price.toFixed(5)}
                      {t.lot_size ? ` · ${t.lot_size.toLocaleString()} units` : ''}
                    </div>
                  )}

                  {t.score !== undefined && (
                    <div className="mt-1">
                      <ScoreBar value={t.score - 0.5} max={0.5} />
                    </div>
                  )}

                  {t.reason && (
                    <div className="text-xs mt-1 truncate" style={{ color: 'var(--text-muted)' }}>
                      {t.reason}
                    </div>
                  )}
                </div>
              ))
            )}
          </div>
        </div>

        {/* ── Column 3: Scores + Status log ── */}
        <div className="flex flex-col overflow-hidden">

          {/* Confluence scores */}
          <div
            className="flex items-center gap-2 px-3 py-2 border-b flex-shrink-0"
            style={{ borderColor: 'var(--border)' }}
          >
            <BarChart2 size={13} style={{ color: 'var(--accent)' }} />
            <span className="text-xs font-semibold uppercase tracking-wider" style={{ color: 'var(--text-muted)' }}>
              Signal Scores
            </span>
          </div>

          <div className="overflow-y-auto p-3 flex flex-col gap-2" style={{ maxHeight: '55%' }}>
            {recentScores.length === 0 ? (
              <div className="text-xs font-mono text-center py-6 opacity-30" style={{ color: 'var(--text-muted)' }}>
                Awaiting analysis
              </div>
            ) : (
              recentScores.map(s => {
                const val = s.type === 'sentiment' ? (s.score ?? 0) - 0.5 : (s.ta_score ?? 0) - 0.5
                const biasColor = s.bias === 'BULLISH' ? 'var(--bull)' : s.bias === 'BEARISH' ? 'var(--bear)' : 'var(--text-muted)'
                return (
                  <div
                    key={s.id}
                    className="rounded p-2.5 flex flex-col gap-1.5"
                    style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)' }}
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-mono font-semibold" style={{ color: 'var(--text-primary)' }}>
                        {s.instrument}
                      </span>
                      <div className="flex items-center gap-1.5">
                        <span
                          className="text-xs px-1.5 py-0.5 rounded font-mono"
                          style={{ background: 'var(--bg-elevated)', color: 'var(--text-muted)' }}
                        >
                          {s.type === 'sentiment' ? 'SENT' : 'TA'}
                        </span>
                        {s.bias && (
                          <span className="text-xs font-mono" style={{ color: biasColor }}>
                            {s.bias}
                          </span>
                        )}
                      </div>
                    </div>
                    <ScoreBar value={val} max={0.5} />
                  </div>
                )
              })
            )}
          </div>

          {/* Divider */}
          <div className="border-t flex-shrink-0" style={{ borderColor: 'var(--border)' }} />

          {/* Status log */}
          <div
            className="flex items-center gap-2 px-3 py-2 border-b flex-shrink-0"
            style={{ borderColor: 'var(--border)' }}
          >
            <Clock size={13} style={{ color: 'var(--accent)' }} />
            <span className="text-xs font-semibold uppercase tracking-wider" style={{ color: 'var(--text-muted)' }}>
              System Log
            </span>
          </div>

          <div className="flex-1 overflow-y-auto p-3 flex flex-col gap-1">
            {statusLog.length === 0 ? (
              <div className="text-xs font-mono text-center py-4 opacity-30" style={{ color: 'var(--text-muted)' }}>
                No events
              </div>
            ) : (
              statusLog.slice(-30).map(s => (
                <div key={s.id} className="flex items-start gap-2">
                  <span
                    className="text-xs font-mono flex-shrink-0"
                    style={{ color: 'var(--text-muted)' }}
                  >
                    {fmt(s.ts)}
                  </span>
                  <span
                    className="text-xs font-mono leading-relaxed"
                    style={{
                      color: s.msg.startsWith('ERROR') ? 'var(--bear)' : 'var(--text-secondary)',
                    }}
                  >
                    {s.msg}
                  </span>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
