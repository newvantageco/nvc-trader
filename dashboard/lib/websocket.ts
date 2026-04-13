import { useNVCStore } from './store'

const WS_URL = process.env.NEXT_PUBLIC_WS_URL || 'wss://nvc-trader.fly.dev/ws'

let heartbeatTimer: ReturnType<typeof setInterval> | null = null

// Track which risk alerts have already fired this session to prevent toast spam
// on every 30s account_update broadcast.
const _firedAlerts = new Set<string>()

export function connectWebSocket(): WebSocket {
  const ws    = new WebSocket(WS_URL)
  const store = useNVCStore.getState()

  ws.onopen = () => {
    console.log('[NVC WS] Connected')
    const isReconnect = store.wsReconnects > 0
    store.setConnected(true)
    if (isReconnect) {
      store.addToast({ type: 'info', title: 'Reconnected', message: 'Live feed restored' })
    }

    // Heartbeat
    if (heartbeatTimer) clearInterval(heartbeatTimer)
    heartbeatTimer = setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'ping' }))
      }
    }, 30_000)
  }

  ws.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data)
      handleMessage(msg, useNVCStore.getState())
    } catch (e) {
      console.warn('[NVC WS] Parse error', e)
    }
  }

  ws.onerror = () => {
    console.warn('[NVC WS] Error')
    useNVCStore.getState().setConnected(false)
  }

  ws.onclose = () => {
    console.log('[NVC WS] Disconnected — reconnecting in 3s...')
    if (heartbeatTimer) { clearInterval(heartbeatTimer); heartbeatTimer = null }
    useNVCStore.getState().setConnected(false)
    useNVCStore.getState().incReconnects()
    setTimeout(() => connectWebSocket(), 3_000)
  }

  return ws
}

function handleMessage(
  msg: Record<string, unknown>,
  store: ReturnType<typeof useNVCStore.getState>
) {
  switch (msg.type) {
    case 'cycle_complete':
    case 'manual_cycle':
    case 'breaking_news_cycle': {
      const data   = msg.data as Record<string, unknown>
      store.setLastCycle(new Date().toISOString())

      const trades = (data?.trades as Array<Record<string, unknown>>) ?? []
      const filled = trades.filter(t => t?.status === 'FILLED')

      // Toast for every filled trade — tastytrade style
      filled.forEach(t => {
        const sig = t?.signal as Record<string, unknown>
        const dir = sig?.direction ?? t?.direction ?? '?'
        const sym = sig?.instrument ?? t?.instrument ?? '?'
        store.addToast({
          type:    'success',
          title:   `Trade Filled — ${dir} ${sym}`,
          message: `@ ${String(t?.fill_price ?? 'market')} · ${String(t?.lot_size ?? '')} units`,
        })
      })

      // Feed signals into store
      trades.forEach(t => {
        const signal = t?.signal as Record<string, unknown>
        if (signal) {
          store.addSignal({
            instrument: signal.instrument as string,
            direction:  signal.direction  as 'BUY' | 'SELL',
            score:      signal.score      as number,
            timestamp:  signal.timestamp  as string,
            reason:     signal.reason     as string,
          })
        }
      })
      break
    }

    case 'positions_update':
      store.setPositions((msg.data as { positions: [] }).positions)
      break

    case 'account_update': {
      const data = msg.data as Parameters<typeof store.setAccount>[0]
      store.setAccount(data)

      // ── Risk alerts — fire once per threshold crossing, not every 30s ──────
      const dailyDD   = data?.daily_drawdown_pct  ?? 0
      const weeklyDD  = data?.weekly_drawdown_pct ?? 0
      const cb        = (data as unknown as Record<string, unknown>)?.circuit_breaker as Record<string, unknown> | undefined

      // R1: daily ≥ 2% → flat for the day
      if (dailyDD >= 2 && !_firedAlerts.has('daily_2pct')) {
        _firedAlerts.add('daily_2pct')
        store.addToast({
          type:    'error',
          title:   '⛔ Daily Limit Hit',
          message: `Daily DD ${dailyDD.toFixed(2)}% — agent halted for today (R1)`,
        })
      } else if (dailyDD >= 1.5 && !_firedAlerts.has('daily_1.5pct')) {
        _firedAlerts.add('daily_1.5pct')
        store.addToast({
          type:    'warning',
          title:   '⚠️ Drawdown Warning',
          message: `Daily DD at ${dailyDD.toFixed(2)}% — sizes reduced 50% (R2)`,
        })
      } else if (dailyDD < 1.0) {
        // Reset so the alert can fire again tomorrow
        _firedAlerts.delete('daily_2pct')
        _firedAlerts.delete('daily_1.5pct')
      }

      // R5: weekly ≥ 5% → halve all sizes
      if (weeklyDD >= 5 && !_firedAlerts.has('weekly_5pct')) {
        _firedAlerts.add('weekly_5pct')
        store.addToast({
          type:    'warning',
          title:   '⚠️ Weekly Limit — Half Size',
          message: `Weekly DD ${weeklyDD.toFixed(2)}% — all positions halved this week (R5)`,
        })
      } else if (weeklyDD < 3) {
        _firedAlerts.delete('weekly_5pct')
      }

      // R7: hard stop (monthly ≥ 10%)
      if (cb?.hard_stop && !_firedAlerts.has('hard_stop')) {
        _firedAlerts.add('hard_stop')
        store.addToast({
          type:    'error',
          title:   '🛑 HARD STOP — Monthly Limit',
          message: 'Monthly drawdown limit hit. Agent paused for 5 business days (R7).',
        })
      }

      break
    }
  }
}
