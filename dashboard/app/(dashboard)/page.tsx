'use client'

import { useEffect, useState } from 'react'
import dynamic from 'next/dynamic'
import { connectWebSocket } from '@/lib/websocket'
import { useNVCStore } from '@/lib/store'
import HeroMetrics from '@/components/HeroMetrics'
import OpportunityFeed from '@/components/OpportunityFeed'
import PositionTable from '@/components/PositionTable'
import EconomicCalendar from '@/components/EconomicCalendar'
import AgentStatus from '@/components/AgentStatus'
import MarketSessionBar from '@/components/MarketSessionBar'
import AgentCycleProgress from '@/components/AgentCycleProgress'

const PriceStrip = dynamic(() => import('@/components/PriceStrip'), { ssr: false })

function Clock() {
  const [time, setTime] = useState('')
  const [date, setDate] = useState('')

  useEffect(() => {
    const tick = () => {
      const now = new Date()
      setTime(now.toLocaleTimeString('en-GB', {
        timeZone: 'UTC', hour12: false,
        hour: '2-digit', minute: '2-digit', second: '2-digit',
      }))
      setDate(now.toLocaleDateString('en-GB', {
        timeZone: 'UTC', day: '2-digit', month: 'short',
      }))
    }
    tick()
    const t = setInterval(tick, 1000)
    return () => clearInterval(t)
  }, [])

  return (
    <div className="flex flex-col items-end leading-none font-mono flex-shrink-0">
      <span className="font-bold text-xs" style={{ color: 'var(--text-primary)' }}>{time}</span>
      <span className="text-[10px] mt-0.5" style={{ color: 'var(--text-muted)' }}>{date} UTC</span>
    </div>
  )
}

function ModeTag() {
  const isDemoMode = process.env.NEXT_PUBLIC_DEMO_MODE !== 'false'
  return (
    <span
      className="font-mono text-[9px] font-bold px-2 py-0.5 rounded"
      style={{
        background: isDemoMode ? 'rgba(240,165,0,0.12)' : 'rgba(229,72,62,0.12)',
        color:      isDemoMode ? 'var(--accent)'         : 'var(--bear)',
        border:     isDemoMode ? '1px solid rgba(240,165,0,0.25)' : '1px solid rgba(229,72,62,0.25)',
        letterSpacing: '0.08em',
      }}
    >
      {isDemoMode ? 'DEMO' : 'LIVE'}
    </span>
  )
}

export default function Terminal() {
  const { setConnected, positions } = useNVCStore()
  const [tab, setTab] = useState<'feed' | 'positions'>('feed')

  useEffect(() => {
    const ws = connectWebSocket()
    setConnected(true)
    return () => {
      ws.close()
      setConnected(false)
    }
  }, [])

  // Auto-switch to positions tab when there are open positions
  useEffect(() => {
    if (positions.length > 0 && tab === 'feed') {
      // Don't force switch — just badge the tab
    }
  }, [positions.length])

  return (
    <div className="flex flex-col h-full" style={{ background: 'var(--bg-base)' }}>

      {/* ── Topbar ──────────────────────────────────────────────────────────── */}
      <header
        className="flex items-center justify-between px-4 border-b flex-shrink-0"
        style={{ borderColor: 'var(--border)', background: 'var(--bg-surface)', height: 48 }}
      >
        {/* Left: price strip */}
        <div className="flex-1 overflow-hidden mr-4 hidden md:block">
          <PriceStrip />
        </div>

        {/* Right: mode + clock + agent */}
        <div className="flex items-center gap-4 ml-auto flex-shrink-0">
          <ModeTag />
          <div className="w-px h-5" style={{ background: 'var(--border)' }} />
          <Clock />
          <div className="w-px h-5" style={{ background: 'var(--border)' }} />
          <AgentStatus />
        </div>
      </header>

      {/* ── Session bar ─────────────────────────────────────────────────────── */}
      <MarketSessionBar />

      {/* ── Hero metrics ────────────────────────────────────────────────────── */}
      <HeroMetrics />

      {/* ── Agent cycle progress (only visible when cycle is running/recent) ── */}
      <AgentCycleProgress />

      {/* ── Divider ─────────────────────────────────────────────────────────── */}
      <div className="flex-shrink-0" style={{ borderBottom: '1px solid var(--border)' }} />

      {/* ── Body: feed + right panel ─────────────────────────────────────────── */}
      <div className="flex flex-1 overflow-hidden">

        {/* Left: tabs → feed or positions */}
        <div className="flex flex-col flex-1 overflow-hidden">

          {/* Tab bar */}
          <div
            className="flex items-center gap-1 px-4 py-2 flex-shrink-0 border-b"
            style={{ borderColor: 'var(--border)' }}
          >
            <button
              onClick={() => setTab('feed')}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium transition-colors"
              style={{
                background: tab === 'feed' ? 'var(--accent-dim)' : 'transparent',
                color:      tab === 'feed' ? 'var(--accent)'     : 'var(--text-muted)',
                border:     tab === 'feed' ? '1px solid rgba(240,165,0,0.2)' : '1px solid transparent',
              }}
            >
              Market Scan
            </button>
            <button
              onClick={() => setTab('positions')}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium transition-colors relative"
              style={{
                background: tab === 'positions' ? 'var(--accent-dim)' : 'transparent',
                color:      tab === 'positions' ? 'var(--accent)'     : 'var(--text-muted)',
                border:     tab === 'positions' ? '1px solid rgba(240,165,0,0.2)' : '1px solid transparent',
              }}
            >
              Positions
              {positions.length > 0 && (
                <span
                  className="ml-1 text-[9px] font-bold px-1.5 py-0.5 rounded"
                  style={{
                    background: 'var(--bull-dim)',
                    color: 'var(--bull)',
                    border: '1px solid rgba(46,168,74,0.3)',
                  }}
                >
                  {positions.length}
                </span>
              )}
            </button>
          </div>

          {/* Tab content */}
          <div className="flex-1 overflow-hidden">
            {tab === 'feed' ? (
              <OpportunityFeed />
            ) : (
              <div className="p-4 overflow-auto h-full">
                {positions.length === 0 ? (
                  <div className="text-center py-16 font-mono text-xs" style={{ color: 'var(--text-muted)' }}>
                    No open positions
                  </div>
                ) : (
                  <PositionTable />
                )}
              </div>
            )}
          </div>
        </div>

        {/* Right sidebar: calendar — hidden on mobile */}
        <div
          className="w-72 flex-shrink-0 border-l flex flex-col hidden md:flex"
          style={{ borderColor: 'var(--border)', background: 'var(--bg-surface)' }}
        >
          <div className="px-4 py-2.5 border-b flex-shrink-0" style={{ borderColor: 'var(--border)' }}>
            <span className="section-label">Upcoming Events</span>
          </div>
          <div className="flex-1 overflow-auto">
            <EconomicCalendar />
          </div>
        </div>
      </div>
    </div>
  )
}
