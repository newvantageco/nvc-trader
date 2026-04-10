'use client'

import { useNVCStore } from '@/lib/store'

export default function AgentStatus() {
  const { agentStatus, lastCycle } = useNVCStore()

  const dotClass = agentStatus === 'active' ? 'dot-live'
    : agentStatus === 'paused' ? 'dot-paused' : 'dot-stop'

  return (
    <div className="flex items-center gap-2">
      <span className={dotClass} />
      <span className="uppercase tracking-wider"
            style={{ color: 'var(--text-secondary)' }}>
        VANTAGE {agentStatus}
      </span>
      {lastCycle && (
        <span style={{ color: 'var(--text-muted)' }}>
          · last cycle {new Date(lastCycle).toLocaleTimeString()}
        </span>
      )}
    </div>
  )
}
