'use client'

/**
 * NotificationBell
 *
 * Polls /trades?limit=10 and /cycles?limit=5 every 60s.
 * Shows a dropdown with recent trade fills and agent cycle completions.
 * Tracks "last seen" timestamp in localStorage to derive unread count.
 */

import { useState, useEffect, useRef, useCallback } from 'react'
import { Bell, X, TrendingUp, TrendingDown, Zap, CheckCheck } from 'lucide-react'
import { api } from '@/lib/api'
const LS_KEY   = 'nvc_notif_last_seen'

interface NVCNotification {
  id:         string
  type:       'fill' | 'cycle' | 'signal'
  title:      string
  body:       string
  created_at: string
  read:       boolean
}

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  const m = Math.floor(diff / 60000)
  if (m < 1)  return 'just now'
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h ago`
  return `${Math.floor(h / 24)}d ago`
}

const TYPE_ICON: Record<NVCNotification['type'], React.ElementType> = {
  fill:   CheckCheck,
  cycle:  Zap,
  signal: TrendingUp,
}

export default function NotificationBell() {
  const [open,          setOpen]          = useState(false)
  const [notifications, setNotifications] = useState<NVCNotification[]>([])
  const [unread,        setUnread]        = useState(0)
  const [loading,       setLoading]       = useState(false)
  const panelRef = useRef<HTMLDivElement>(null)

  const buildNotifications = useCallback(async (): Promise<NVCNotification[]> => {
    const [tradesRes, cyclesRes] = await Promise.allSettled([
      api.get<{ trades: Array<Record<string, unknown>> }>('/trades?limit=10').catch(() => ({ trades: [] })),
      api.get<{ cycles: Array<Record<string, unknown>> }>('/cycles?limit=5').catch(() => ({ cycles: [] })),
    ])

    const notifs: NVCNotification[] = []

    if (tradesRes.status === 'fulfilled') {
      const trades: Array<Record<string, unknown>> = tradesRes.value.trades || []
      for (const t of trades) {
        const dir = String(t.direction ?? '')
        const pnl = typeof t.pnl === 'number' ? t.pnl : null
        const fillStatus = typeof t.fill === 'object' && t.fill !== null
          ? String((t.fill as Record<string, unknown>).status ?? '')
          : ''
        const isFilled = String(t.status ?? '').toUpperCase() === 'FILLED' ||
                         fillStatus.toUpperCase() === 'FILLED'
        if (!isFilled) continue
        notifs.push({
          id:         String(t.id ?? t.trade_id ?? Math.random()),
          type:       'fill',
          title:      `${dir} ${t.instrument} filled`,
          body:       pnl !== null
            ? `P&L: ${pnl >= 0 ? '+' : ''}$${pnl.toFixed(2)}`
            : `Lot size: ${t.lot_size ?? '—'}`,
          created_at: String(t.created_at ?? new Date().toISOString()),
          read:       false,
        })
      }
    }

    if (cyclesRes.status === 'fulfilled') {
      const cycles: Array<Record<string, unknown>> = cyclesRes.value.cycles || []
      for (const c of cycles) {
        notifs.push({
          id:         String(c.cycle_id ?? Math.random()),
          type:       'cycle',
          title:      `Agent cycle complete`,
          body:       `${c.trades_executed ?? 0} trade${Number(c.trades_executed) !== 1 ? 's' : ''} · trigger: ${c.trigger ?? '—'}`,
          created_at: String(c.timestamp ?? new Date().toISOString()),
          read:       false,
        })
      }
    }

    // Sort newest first
    notifs.sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
    return notifs
  }, [])

  // Poll unread count every 60s
  useEffect(() => {
    let mounted = true
    async function poll() {
      try {
        const items = await buildNotifications()
        if (!mounted) return
        const lastSeen = Number(localStorage.getItem(LS_KEY) ?? 0)
        const count = items.filter(n => new Date(n.created_at).getTime() > lastSeen).length
        setUnread(count)
      } catch { /* silent */ }
    }
    poll()
    const t = setInterval(poll, 60_000)
    return () => { mounted = false; clearInterval(t) }
  }, [buildNotifications])

  // Close on click outside
  useEffect(() => {
    function outside(e: MouseEvent) {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) setOpen(false)
    }
    if (open) document.addEventListener('mousedown', outside)
    return () => document.removeEventListener('mousedown', outside)
  }, [open])

  async function handleOpen() {
    const next = !open
    setOpen(next)
    if (next) {
      setLoading(true)
      try {
        const items = await buildNotifications()
        const lastSeen = Number(localStorage.getItem(LS_KEY) ?? 0)
        setNotifications(items.map(n => ({
          ...n,
          read: new Date(n.created_at).getTime() <= lastSeen,
        })))
      } finally {
        setLoading(false)
      }
    }
  }

  function markAllRead() {
    localStorage.setItem(LS_KEY, String(Date.now()))
    setNotifications(n => n.map(x => ({ ...x, read: true })))
    setUnread(0)
  }

  return (
    <div className="relative" ref={panelRef}>
      {/* Bell button */}
      <button
        onClick={handleOpen}
        className="relative p-1.5 rounded transition-colors"
        style={{ color: 'var(--text-muted)' }}
        aria-label={`Notifications${unread > 0 ? ` (${unread} unread)` : ''}`}
      >
        <Bell size={15} />
        {unread > 0 && (
          <span
            className="absolute -top-0.5 -right-0.5 flex items-center justify-center rounded-full font-mono font-bold text-white leading-none"
            style={{ width: 15, height: 15, fontSize: 9, background: 'var(--bear)' }}
          >
            {unread > 9 ? '9+' : unread}
          </span>
        )}
      </button>

      {/* Panel */}
      {open && (
        <div
          className="absolute right-0 top-9 rounded-xl overflow-hidden shadow-2xl z-50"
          style={{
            width: 320,
            background: 'var(--bg-surface)',
            border: '1px solid var(--border-bright)',
          }}
        >
          {/* Header */}
          <div
            className="flex items-center justify-between px-4 py-3 border-b"
            style={{ borderColor: 'var(--border)' }}
          >
            <span className="text-xs font-semibold" style={{ color: 'var(--text-primary)' }}>
              Activity Feed
            </span>
            <div className="flex items-center gap-2">
              {unread > 0 && (
                <button
                  onClick={markAllRead}
                  className="flex items-center gap-1 text-xs transition-opacity hover:opacity-70"
                  style={{ color: 'var(--text-muted)' }}
                >
                  <CheckCheck size={11} />
                  Mark all read
                </button>
              )}
              <button onClick={() => setOpen(false)} style={{ color: 'var(--text-muted)' }}>
                <X size={14} />
              </button>
            </div>
          </div>

          {/* List */}
          <div className="overflow-y-auto" style={{ maxHeight: 360 }}>
            {loading && (
              <div className="p-4 space-y-3">
                {[...Array(4)].map((_, i) => (
                  <div key={i} className="flex gap-3">
                    <div className="skeleton w-8 h-8 rounded flex-shrink-0" />
                    <div className="flex-1 space-y-1.5">
                      <div className="skeleton" style={{ height: 11, width: '60%' }} />
                      <div className="skeleton" style={{ height: 10, width: '40%' }} />
                    </div>
                  </div>
                ))}
              </div>
            )}

            {!loading && notifications.length === 0 && (
              <div className="py-12 text-center">
                <Bell size={28} style={{ color: 'var(--border)', margin: '0 auto 8px' }} />
                <p className="text-xs" style={{ color: 'var(--text-muted)' }}>No activity yet</p>
              </div>
            )}

            {!loading && notifications.map(n => {
              const Icon = TYPE_ICON[n.type]
              return (
                <div
                  key={n.id}
                  className="flex gap-3 px-4 py-3 border-b transition-colors"
                  style={{
                    borderColor:  'var(--border)',
                    background:   n.read ? 'transparent' : 'var(--accent-dim)',
                  }}
                >
                  <div
                    className="flex-shrink-0 w-8 h-8 rounded flex items-center justify-center"
                    style={{
                      background: n.read ? 'var(--bg-elevated)' : 'var(--bg-surface)',
                      border:     `1px solid ${n.read ? 'var(--border)' : 'var(--border-bright)'}`,
                    }}
                  >
                    <Icon size={13} style={{ color: n.read ? 'var(--text-muted)' : 'var(--accent)' }} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p
                      className="text-xs leading-snug font-mono"
                      style={{ color: n.read ? 'var(--text-secondary)' : 'var(--text-primary)', fontWeight: n.read ? 400 : 600 }}
                    >
                      {n.title}
                    </p>
                    <p className="text-[10px] mt-0.5 font-mono truncate" style={{ color: 'var(--text-muted)' }}>
                      {n.body}
                    </p>
                    <p className="text-[10px] mt-1 font-mono" style={{ color: 'var(--text-muted)' }}>
                      {timeAgo(n.created_at)}
                    </p>
                  </div>
                  {!n.read && (
                    <span
                      className="flex-shrink-0 self-start mt-1.5 rounded-full"
                      style={{ width: 5, height: 5, background: 'var(--accent)' }}
                    />
                  )}
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
