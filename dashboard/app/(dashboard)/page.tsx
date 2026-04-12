'use client'

import { useEffect, useState } from 'react'
import dynamic from 'next/dynamic'
import SignalTape from '@/components/SignalTape'
import PositionTable from '@/components/PositionTable'
import SentimentGauge from '@/components/SentimentGauge'
import AccountBar from '@/components/AccountBar'
import AgentStatus from '@/components/AgentStatus'
import EconomicCalendar from '@/components/EconomicCalendar'
import MarketSessionBar from '@/components/MarketSessionBar'
import { useNVCStore } from '@/lib/store'
import { connectWebSocket } from '@/lib/websocket'

// Price strip is client-only (live ticks)
const PriceStrip = dynamic(() => import('@/components/PriceStrip'), { ssr: false })

const WATCHLIST = ['EURUSD', 'GBPUSD', 'USDJPY', 'XAUUSD', 'USOIL']

function DualClock() {
  const [gmt, setGmt]  = useState('')
  const [est, setEst]  = useState('')

  useEffect(() => {
    const tick = () => {
      const now = new Date()
      setGmt(now.toLocaleTimeString('en-GB', { timeZone: 'UTC',           hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' }))
      setEst(now.toLocaleTimeString('en-GB', { timeZone: 'America/New_York', hour12: false, hour: '2-digit', minute: '2-digit' }))
    }
    tick()
    const t = setInterval(tick, 1000)
    return () => clearInterval(t)
  }, [])

  return (
    <div className="flex items-center gap-3 font-mono text-xs flex-shrink-0">
      <div className="flex flex-col items-end leading-none">
        <span style={{ color: 'var(--text-muted)', fontSize: 9 }} className="tracking-widest">GMT</span>
        <span className="font-bold mt-0.5" style={{ color: 'var(--text-primary)' }}>{gmt}</span>
      </div>
      <div className="w-px h-6" style={{ background: 'var(--border)' }} />
      <div className="flex flex-col items-end leading-none">
        <span style={{ color: 'var(--text-muted)', fontSize: 9 }} className="tracking-widest">EST</span>
        <span className="font-bold mt-0.5" style={{ color: 'var(--text-muted)' }}>{est}</span>
      </div>
    </div>
  )
}

export default function Terminal() {
  const { setConnected } = useNVCStore()

  useEffect(() => {
    const ws = connectWebSocket()
    setConnected(true)
    return () => {
      ws.close()
      setConnected(false)
    }
  }, [])

  return (
    <div className="flex flex-col h-full" style={{ background: 'var(--bg-base)' }}>

      {/* ── Row 1: identity + prices + account + clocks ─────────────────────── */}
      <header
        className="flex items-center justify-between px-4 border-b flex-shrink-0"
        style={{ borderColor: 'var(--border)', background: 'var(--bg-surface)', height: 44 }}
      >
        {/* Left: brand */}
        <div className="flex items-center gap-3 flex-shrink-0">
          <span className="font-mono font-bold text-sm tracking-widest" style={{ color: 'var(--accent)' }}>
            NVC
          </span>
          <div className="w-px h-5" style={{ background: 'var(--border)' }} />
          <span className="font-mono text-xs tracking-widest uppercase" style={{ color: 'var(--text-muted)' }}>
            Vantage Terminal
          </span>
        </div>

        {/* Centre: live price strip */}
        <div className="flex-1 flex justify-center overflow-hidden">
          <PriceStrip />
        </div>

        {/* Right: account + clock + agent */}
        <div className="flex items-center gap-4 flex-shrink-0">
          <div className="hidden md:flex">
            <AccountBar />
          </div>
          <div className="w-px h-6" style={{ background: 'var(--border)' }} />
          <DualClock />
          <div className="w-px h-6" style={{ background: 'var(--border)' }} />
          <AgentStatus />
        </div>
      </header>

      {/* ── Row 2: market session bar ──────────────────────────────────────── */}
      <MarketSessionBar />

      {/* ── Body ─────────────────────────────────────────────────────────── */}
      <div className="flex flex-1 overflow-hidden">

        {/* Main panel */}
        <div className="flex flex-col flex-1 overflow-hidden">

          {/* Signal tape */}
          <div className="border-b px-3 pt-2 pb-2 flex-shrink-0" style={{ borderColor: 'var(--border)' }}>
            <div className="flex items-center gap-2 mb-1.5">
              <span className="w-1.5 h-1.5 rounded-full animate-pulse" style={{ background: 'var(--bull)' }} />
              <span className="text-xs font-mono font-semibold tracking-widest uppercase"
                    style={{ color: 'var(--text-muted)' }}>
                Live Signal Feed
              </span>
            </div>
            <SignalTape />
          </div>

          {/* Positions */}
          <div className="flex-1 overflow-auto p-3">
            <div className="text-xs font-mono font-semibold tracking-widest uppercase mb-2"
                 style={{ color: 'var(--text-muted)' }}>
              Open Positions
            </div>
            <PositionTable />
          </div>
        </div>

        {/* Right sidebar */}
        <div className="w-72 flex-shrink-0 border-l flex flex-col hidden md:flex"
          style={{ borderColor: 'var(--border)', background: 'var(--bg-surface)' }}>

          {/* Sentiment */}
          <div className="p-3 border-b flex-shrink-0" style={{ borderColor: 'var(--border)' }}>
            <div className="text-xs font-mono font-semibold tracking-widest uppercase mb-2"
                 style={{ color: 'var(--text-muted)' }}>
              Sentiment Radar
            </div>
            <div className="flex flex-col gap-2">
              {WATCHLIST.map(sym => (
                <SentimentGauge key={sym} instrument={sym} />
              ))}
            </div>
          </div>

          {/* Calendar */}
          <div className="flex-1 overflow-auto p-3">
            <div className="text-xs font-mono font-semibold tracking-widest uppercase mb-2"
                 style={{ color: 'var(--text-muted)' }}>
              Economic Calendar
            </div>
            <EconomicCalendar />
          </div>
        </div>
      </div>

      {/* ── Footer ────────────────────────────────────────────────────────── */}
      <footer
        className="px-4 py-1 border-t flex items-center justify-between flex-shrink-0"
        style={{ borderColor: 'var(--border)', background: 'var(--bg-surface)' }}
      >
        <span className="font-mono text-xs" style={{ color: 'var(--text-muted)' }}>
          New Vantage Co · NVC/1.0
        </span>
        <span className="font-mono text-xs" style={{ color: 'var(--text-muted)' }}>
          claude-opus-4-6 · FinBERT · OANDA v20
        </span>
        <span className="font-mono text-xs" style={{ color: 'var(--text-muted)' }}>
          Past performance ≠ future results · Capital at risk
        </span>
      </footer>
    </div>
  )
}
