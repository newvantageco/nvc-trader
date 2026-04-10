'use client'

import { useEffect, useState } from 'react'
import { format } from 'date-fns'

interface CalendarEvent {
  title: string
  currency: string
  impact: string
  time: string
  forecast?: string
  previous?: string
}

export default function EconomicCalendar() {
  const [events, setEvents] = useState<CalendarEvent[]>([])

  useEffect(() => {
    const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
    fetch(`${API}/calendar?hours=24`)
      .then(r => r.json())
      .then(d => setEvents(d.events || []))
      .catch(() => {})
  }, [])

  const impactColor = (impact: string) => {
    if (impact === 'high') return 'var(--bear)'
    if (impact === 'medium') return 'var(--accent)'
    return 'var(--neutral)'
  }

  return (
    <div className="flex flex-col gap-1.5 font-mono text-xs">
      {events.length === 0 && (
        <div style={{ color: 'var(--text-muted)' }}>No events in next 24h</div>
      )}
      {events.map((e, i) => (
        <div
          key={i}
          className="p-2 rounded border"
          style={{
            borderColor: impactColor(e.impact),
            background: 'var(--bg-elevated)',
          }}
        >
          <div className="flex items-center justify-between mb-1">
            <span className="font-semibold" style={{ color: 'var(--text-primary)' }}>
              {e.currency}
            </span>
            <span style={{ color: 'var(--text-muted)' }}>
              {format(new Date(e.time), 'HH:mm')} UTC
            </span>
          </div>
          <div style={{ color: 'var(--text-secondary)' }} className="truncate">
            {e.title}
          </div>
          {(e.forecast || e.previous) && (
            <div className="flex gap-3 mt-1" style={{ color: 'var(--text-muted)' }}>
              {e.forecast && <span>F: {e.forecast}</span>}
              {e.previous && <span>P: {e.previous}</span>}
            </div>
          )}
        </div>
      ))}
    </div>
  )
}
