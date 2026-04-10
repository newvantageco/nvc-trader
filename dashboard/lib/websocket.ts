import { useNVCStore } from './store'

const WS_URL = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8000/ws'

export function connectWebSocket(): WebSocket {
  const ws = new WebSocket(WS_URL)
  const store = useNVCStore.getState()

  ws.onopen = () => {
    console.log('[NVC WS] Connected')
  }

  ws.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data)
      handleMessage(msg, store)
    } catch (e) {
      console.warn('[NVC WS] Parse error', e)
    }
  }

  ws.onerror = (e) => console.warn('[NVC WS] Error', e)

  // Reconnect on close
  ws.onclose = () => {
    console.log('[NVC WS] Disconnected — reconnecting in 3s...')
    setTimeout(() => connectWebSocket(), 3000)
  }

  // Heartbeat
  setInterval(() => {
    if (ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'ping' }))
    }
  }, 30000)

  return ws
}

function handleMessage(msg: Record<string, unknown>, store: ReturnType<typeof useNVCStore.getState>) {
  switch (msg.type) {
    case 'cycle_complete':
    case 'manual_cycle':
    case 'breaking_news_cycle': {
      const data = msg.data as Record<string, unknown>
      store.setLastCycle(new Date().toISOString())
      const trades = data?.trades as Array<Record<string, unknown>> ?? []
      trades.forEach(t => {
        const signal = t?.signal as Record<string, unknown>
        if (signal) {
          store.addSignal({
            instrument: signal.instrument as string,
            direction: signal.direction as 'BUY' | 'SELL',
            score: signal.score as number,
            timestamp: signal.timestamp as string,
            reason: signal.reason as string,
          })
        }
      })
      break
    }

    case 'positions_update':
      store.setPositions((msg.data as { positions: [] }).positions)
      break

    case 'account_update':
      store.setAccount(msg.data as Parameters<typeof store.setAccount>[0])
      break
  }
}
