import { create } from 'zustand'

export interface Signal {
  instrument: string
  direction: 'BUY' | 'SELL'
  score: number
  timestamp: string
  reason: string
}

export interface Position {
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

export interface AccountMetrics {
  equity: number
  balance: number
  margin: number
  free_margin: number
  unrealised_pl: number
  daily_drawdown_pct: number
  weekly_drawdown_pct: number
  monthly_drawdown_pct: number
  currency: string
  system_status: string
  broker: string
  circuit_breaker?: {
    size_multiplier: number
    trading_allowed: boolean
    weekly_limit_hit: boolean
    hard_stop: boolean
  }
}

export type ToastType = 'success' | 'error' | 'warning' | 'info'

export interface Toast {
  id: string
  type: ToastType
  title: string
  message?: string
}

interface NVCStore {
  connected: boolean
  wsReconnects: number
  agentStatus: 'active' | 'paused' | 'emergency_stop'
  lastCycle: string | null
  signals: Signal[]
  positions: Position[]
  account: AccountMetrics | null
  toasts: Toast[]

  setConnected: (v: boolean) => void
  incReconnects: () => void
  setAgentStatus: (v: 'active' | 'paused' | 'emergency_stop') => void
  addSignal: (s: Signal) => void
  setPositions: (p: Position[]) => void
  setAccount: (a: AccountMetrics) => void
  setLastCycle: (t: string) => void
  addToast: (t: Omit<Toast, 'id'>) => void
  removeToast: (id: string) => void
}

export const useNVCStore = create<NVCStore>(set => ({
  connected: false,
  wsReconnects: 0,
  agentStatus: 'active',
  lastCycle: null,
  signals: [],
  positions: [],
  account: null,
  toasts: [],

  setConnected:   connected  => set({ connected }),
  incReconnects:  ()         => set(s => ({ wsReconnects: s.wsReconnects + 1 })),
  setAgentStatus: agentStatus => set({ agentStatus }),
  addSignal:      signal     => set(s => ({ signals: [...s.signals.slice(-99), signal] })),
  setPositions:   positions  => set({ positions }),
  setAccount:     account    => set({ account }),
  setLastCycle:   lastCycle  => set({ lastCycle }),

  addToast: (t) => {
    const id = `${Date.now()}-${Math.random()}`
    set(s => ({ toasts: [...s.toasts.slice(-4), { ...t, id }] }))
  },
  removeToast: (id) => set(s => ({ toasts: s.toasts.filter(t => t.id !== id) })),
}))
