'use client'

import { useEffect, useState } from 'react'
import SignalTape from '@/components/SignalTape'
import PositionTable from '@/components/PositionTable'
import SentimentGauge from '@/components/SentimentGauge'
import AccountBar from '@/components/AccountBar'
import AgentStatus from '@/components/AgentStatus'
import EconomicCalendar from '@/components/EconomicCalendar'
import { useNVCStore } from '@/lib/store'
import { connectWebSocket } from '@/lib/websocket'

const WATCHLIST = ['EURUSD', 'GBPUSD', 'USDJPY', 'XAUUSD', 'USOIL']

export default function Terminal() {
  const { setConnected } = useNVCStore()
  const [clock, setClock] = useState('')

  useEffect(() => {
    const ws = connectWebSocket()
    setConnected(true)
    const tick = setInterval(() => {
      setClock(new Date().toUTCString().slice(17, 25) + ' UTC')
    }, 1000)
    return () => {
      ws.close()
      clearInterval(tick)
      setConnected(false)
    }
  }, [])

  return (
    <div className="min-h-screen flex flex-col" style={{ background: 'var(--bg-base)' }}>

      {/* ── Top Bar ───────────────────────────────────────────────────────── */}
      <header className="flex items-center justify-between px-4 py-2 border-b"
              style={{ borderColor: 'var(--border)', background: 'var(--bg-surface)' }}>
        <div className="flex items-center gap-3">
          <span className="font-mono font-bold text-amber-400 text-sm tracking-widest">
            NVC TERMINAL
          </span>
          <span className="text-xs px-2 py-0.5 rounded"
                style={{ background: 'var(--accent-dim)', color: 'var(--accent)' }}>
            VANTAGE v1.0
          </span>
        </div>
        <AccountBar />
        <div className="flex items-center gap-4 text-xs" style={{ color: 'var(--text-muted)' }}>
          <span className="font-mono">{clock}</span>
          <AgentStatus />
        </div>
      </header>

      {/* ── Main Grid ─────────────────────────────────────────────────────── */}
      <div className="flex flex-1 overflow-hidden">

        {/* Left — Signals + Positions */}
        <div className="flex flex-col flex-1 overflow-hidden">
          {/* Signal tape */}
          <div className="border-b p-3 flex-shrink-0"
               style={{ borderColor: 'var(--border)' }}>
            <div className="flex items-center gap-2 mb-2">
              <span className="dot-live" />
              <span className="text-xs font-semibold tracking-wider"
                    style={{ color: 'var(--text-secondary)' }}>
                LIVE SIGNAL FEED
              </span>
            </div>
            <SignalTape />
          </div>

          {/* Open positions */}
          <div className="flex-1 overflow-auto p-3">
            <div className="text-xs font-semibold tracking-wider mb-2"
                 style={{ color: 'var(--text-secondary)' }}>
              OPEN POSITIONS
            </div>
            <PositionTable />
          </div>
        </div>

        {/* Right Panel — Sentiment + Calendar */}
        <div className="w-72 flex-shrink-0 border-l flex flex-col"
             style={{ borderColor: 'var(--border)', background: 'var(--bg-surface)' }}>

          {/* Sentiment gauges */}
          <div className="p-3 border-b" style={{ borderColor: 'var(--border)' }}>
            <div className="text-xs font-semibold tracking-wider mb-3"
                 style={{ color: 'var(--text-secondary)' }}>
              SENTIMENT RADAR
            </div>
            <div className="flex flex-col gap-2">
              {WATCHLIST.map(sym => (
                <SentimentGauge key={sym} instrument={sym} />
              ))}
            </div>
          </div>

          {/* Economic calendar */}
          <div className="flex-1 overflow-auto p-3">
            <div className="text-xs font-semibold tracking-wider mb-2"
                 style={{ color: 'var(--text-secondary)' }}>
              ECONOMIC CALENDAR
            </div>
            <EconomicCalendar />
          </div>
        </div>
      </div>

      {/* ── Bottom Status Bar ─────────────────────────────────────────────── */}
      <footer className="px-4 py-1.5 border-t flex items-center justify-between text-xs"
              style={{ borderColor: 'var(--border)', background: 'var(--bg-surface)', color: 'var(--text-muted)' }}>
        <span>New Vantage Co © 2026</span>
        <span className="font-mono">claude-opus-4-6 · FinBERT · MT5 ZMQ</span>
        <span>⚠ Past performance does not guarantee future results</span>
      </footer>
    </div>
  )
}
