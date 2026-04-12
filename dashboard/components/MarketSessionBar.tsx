'use client'

import { useState, useEffect } from 'react'

interface Session {
  label: string
  short: string
  openUTC: number   // hour
  closeUTC: number  // hour
}

const SESSIONS: Session[] = [
  { label: 'Tokyo',    short: 'TYO', openUTC: 0,  closeUTC: 9  },
  { label: 'London',   short: 'LON', openUTC: 8,  closeUTC: 17 },
  { label: 'New York', short: 'NYK', openUTC: 13, closeUTC: 22 },
]

function isOpen(session: Session, utcH: number, utcM: number): boolean {
  const now = utcH + utcM / 60
  return now >= session.openUTC && now < session.closeUTC
}

function isOverlap(utcH: number, utcM: number): boolean {
  // London / NY overlap: 13:00–17:00 UTC
  const now = utcH + utcM / 60
  return now >= 13 && now < 17
}

function nextEvent(session: Session, utcH: number, utcM: number): { action: 'opens' | 'closes'; inMin: number } {
  const nowMin = utcH * 60 + utcM
  if (isOpen(session, utcH, utcM)) {
    return { action: 'closes', inMin: session.closeUTC * 60 - nowMin }
  }
  // handle overnight (Tokyo wraps past midnight)
  let openMin = session.openUTC * 60
  if (openMin <= nowMin) openMin += 24 * 60
  return { action: 'opens', inMin: openMin - nowMin }
}

function fmtMin(min: number): string {
  const h = Math.floor(min / 60)
  const m = min % 60
  return h > 0 ? `${h}h ${m}m` : `${m}m`
}

export default function MarketSessionBar() {
  const [now, setNow] = useState(new Date())

  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 60_000)
    return () => clearInterval(t)
  }, [])

  const utcH = now.getUTCHours()
  const utcM = now.getUTCMinutes()
  const overlap = isOverlap(utcH, utcM)

  // Find next event across all sessions for the countdown
  const events = SESSIONS.map(s => {
    const open = isOpen(s, utcH, utcM)
    const { action, inMin } = nextEvent(s, utcH, utcM)
    return { ...s, open, action, inMin }
  })

  // Soonest upcoming event
  const soonest = [...events].sort((a, b) => a.inMin - b.inMin)[0]

  return (
    <div
      className="flex items-center gap-0 border-b flex-shrink-0 overflow-x-auto"
      style={{
        background: 'var(--bg-surface)',
        borderColor: 'var(--border)',
        height: 28,
      }}
    >
      {/* Session chips */}
      <div className="flex items-center px-3 gap-4 flex-shrink-0">
        {events.map(s => (
          <div key={s.short} className="flex items-center gap-1.5 font-mono text-xs">
            <span
              className="w-1.5 h-1.5 rounded-full flex-shrink-0"
              style={{
                background: s.open ? 'var(--bull)' : 'var(--text-muted)',
                boxShadow: s.open ? '0 0 4px var(--bull)' : 'none',
              }}
            />
            <span
              className="font-semibold tracking-wider"
              style={{ color: s.open ? 'var(--text-primary)' : 'var(--text-muted)' }}
            >
              {s.short}
            </span>
            <span style={{ color: s.open ? 'var(--bull)' : 'var(--text-muted)' }}>
              {s.open ? 'OPEN' : 'CLOSED'}
            </span>
          </div>
        ))}
      </div>

      {/* Overlap indicator */}
      <div
        className="flex items-center gap-1.5 font-mono text-xs px-3 border-l"
        style={{ borderColor: 'var(--border)' }}
      >
        <span
          className="w-1.5 h-1.5 rounded-full flex-shrink-0"
          style={{
            background: overlap ? 'var(--accent)' : 'var(--text-muted)',
            boxShadow: overlap ? '0 0 4px var(--accent)' : 'none',
          }}
        />
        <span
          className="font-semibold tracking-wider"
          style={{ color: overlap ? 'var(--accent)' : 'var(--text-muted)' }}
        >
          LON/NY OVERLAP
        </span>
        {overlap && (
          <span style={{ color: 'var(--text-muted)' }}>
            ends {fmtMin(17 * 60 - (utcH * 60 + utcM))}
          </span>
        )}
      </div>

      {/* Countdown to next event */}
      <div
        className="flex items-center gap-1.5 font-mono text-xs px-3 border-l ml-auto flex-shrink-0"
        style={{ borderColor: 'var(--border)' }}
      >
        <span style={{ color: 'var(--text-muted)' }}>
          {soonest.short} {soonest.action} in
        </span>
        <span className="font-semibold" style={{ color: 'var(--accent)' }}>
          {fmtMin(soonest.inMin)}
        </span>
      </div>
    </div>
  )
}
