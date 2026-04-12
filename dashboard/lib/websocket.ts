import { useNVCStore } from './store'

const WS_URL = process.env.NEXT_PUBLIC_WS_URL || 'wss://nvc-trader.fly.dev/ws'

let heartbeatTimer: ReturnType<typeof setInterval> | null = null

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
      // Warn if daily drawdown crosses 2%
      if ((data?.daily_drawdown_pct ?? 0) >= 2) {
        store.addToast({
          type:    'warning',
          title:   'Drawdown Alert',
          message: `Daily DD at ${data.daily_drawdown_pct.toFixed(2)}% — approaching limit`,
        })
      }
      break
    }
  }
}
