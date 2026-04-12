'use client'

import { Wifi, WifiOff } from 'lucide-react'
import { useNVCStore } from '@/lib/store'

export default function AgentStatus() {
  const { agentStatus, lastCycle, connected, wsReconnects } = useNVCStore()

  const dotClass = agentStatus === 'active' ? 'dot-live'
    : agentStatus === 'paused' ? 'dot-paused' : 'dot-stop'

  return (
    <div className="flex items-center gap-2.5">
      {/* WS connection indicator */}
      <span title={connected
          ? `Connected${wsReconnects > 0 ? ` (${wsReconnects} reconnects)` : ''}`
          : 'Disconnected — reconnecting…'}>
        {connected
          ? <Wifi size={12} style={{ color: 'var(--bull)' }} />
          : <WifiOff size={12} style={{ color: 'var(--bear)', animation: 'pulse 1s infinite' }} />
        }
      </span>

      <span className={dotClass} />

      <span className="uppercase tracking-wider"
            style={{ color: connected ? 'var(--text-secondary)' : 'var(--text-muted)' }}>
        VANTAGE {agentStatus}
      </span>

      {lastCycle && (
        <span style={{ color: 'var(--text-muted)' }}>
          · {new Date(lastCycle).toLocaleTimeString('en-GB', { hour12: false })}
        </span>
      )}
    </div>
  )
}
