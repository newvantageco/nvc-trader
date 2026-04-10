import { create } from 'zustand'

interface Signal {
  instrument: string
  direction: 'BUY' | 'SELL'
  score: number
  timestamp: string
  reason: string
}

interface Position {
  ticket: number
  instrument: string
  direction: 'BUY' | 'SELL'
  lot_size: number
  entry_price: number
  current_price: number
  stop_loss: number
  take_profit: number
  profit: number
}

interface AccountMetrics {
  equity: number
  balance: number
  daily_drawdown_pct: number
  system_status: string
}

interface NVCStore {
  connected: boolean
  agentStatus: 'active' | 'paused' | 'emergency_stop'
  lastCycle: string | null
  signals: Signal[]
  positions: Position[]
  account: AccountMetrics | null
  setConnected: (v: boolean) => void
  setAgentStatus: (v: 'active' | 'paused' | 'emergency_stop') => void
  addSignal: (s: Signal) => void
  setPositions: (p: Position[]) => void
  setAccount: (a: AccountMetrics) => void
  setLastCycle: (t: string) => void
}

export const useNVCStore = create<NVCStore>(set => ({
  connected: false,
  agentStatus: 'active',
  lastCycle: null,
  signals: [],
  positions: [],
  account: null,
  setConnected: connected => set({ connected }),
  setAgentStatus: agentStatus => set({ agentStatus }),
  addSignal: signal => set(s => ({ signals: [...s.signals.slice(-99), signal] })),
  setPositions: positions => set({ positions }),
  setAccount: account => set({ account }),
  setLastCycle: lastCycle => set({ lastCycle }),
}))
