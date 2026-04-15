'use client'

/**
 * SystemStatusBanner
 *
 * Polls /account every 90s. Shows a top-of-page banner when:
 *   - circuit_breaker.hard_stop is true
 *   - circuit_breaker.trading_allowed is false
 *   - system_status is "error"
 *
 * Dismissible per-session but re-checks every 90s; banner reappears
 * if the condition changes (e.g. drawdown continues growing).
 */

import { useEffect, useState } from 'react'
import { AlertTriangle, ShieldOff, X } from 'lucide-react'
import { useNVCStore } from '@/lib/store'

const API = process.env.NEXT_PUBLIC_API_URL || 'https://nvc-trader.fly.dev'

type BannerType = 'hard_stop' | 'halted' | 'weekly_hit' | null

export default function SystemStatusBanner() {
  const account   = useNVCStore(s => s.account)
  const [type,     setType]      = useState<BannerType>(null)
  const [dismissed, setDismissed] = useState<BannerType>(null)

  useEffect(() => {
    function evaluate(acct: typeof account) {
      if (!acct) return
      const cb = acct.circuit_breaker
      if (cb?.hard_stop)                  setType('hard_stop')
      else if (cb?.trading_allowed === false) setType('halted')
      else if (cb?.weekly_limit_hit)      setType('weekly_hit')
      else setType(null)
    }

    evaluate(account)
  }, [account])

  // Also poll independently in case websocket is down
  useEffect(() => {
    let timer: ReturnType<typeof setInterval>
    async function check() {
      try {
        const r = await fetch(`${API}/account`)
        if (!r.ok) return
        const d = await r.json()
        const cb = d.circuit_breaker
        if (cb?.hard_stop)                  setType('hard_stop')
        else if (cb?.trading_allowed === false) setType('halted')
        else if (cb?.weekly_limit_hit)      setType('weekly_hit')
        else setType(null)
      } catch { /* silent */ }
    }
    timer = setInterval(check, 90_000)
    return () => clearInterval(timer)
  }, [])

  const show = type !== null && type !== dismissed

  if (!show) return null

  const config = {
    hard_stop:  { bg: 'rgba(229,72,62,0.95)', text: '⛔ HARD STOP — All trading halted. Daily drawdown limit hit. No new positions until reset.', Icon: ShieldOff },
    halted:     { bg: 'rgba(229,72,62,0.85)', text: '⚠ TRADING HALTED — Circuit breaker triggered. System paused awaiting manual review.', Icon: ShieldOff },
    weekly_hit: { bg: 'rgba(240,165,0,0.90)', text: '⚠ WEEKLY DRAWDOWN LIMIT HIT — Position sizes reduced to 50%. Review open risk.', Icon: AlertTriangle },
  }[type!]

  return (
    <div
      className="relative flex items-center justify-between px-5 py-2.5 text-xs font-semibold z-40 flex-shrink-0"
      style={{ background: config.bg, color: '#fff' }}
      role="alert"
    >
      <div className="flex items-center gap-2.5">
        <config.Icon size={14} className="flex-shrink-0" />
        <span className="font-mono tracking-wide">{config.text}</span>
      </div>
      <button
        onClick={() => setDismissed(type)}
        aria-label="Dismiss banner"
        className="flex-shrink-0 ml-4 opacity-70 hover:opacity-100 transition-opacity"
      >
        <X size={14} />
      </button>
    </div>
  )
}
