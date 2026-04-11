'use client'

import { useEffect, useState } from 'react'
import Sidebar from '@/components/Sidebar'

const API = process.env.NEXT_PUBLIC_API_URL || 'https://nvc-trader-engine.fly.dev'

const WATCHLIST = ['EURUSD','GBPUSD','USDJPY','AUDUSD','USDCAD','NZDUSD','USDCHF','EURJPY','GBPJPY','XAUUSD','XAGUSD','USOIL','UKOIL','NATGAS']

function Row({ label, desc, children }: { label: string; desc?: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between py-3 border-b"
         style={{ borderColor: 'var(--border)' }}>
      <div>
        <div className="text-xs font-semibold" style={{ color: 'var(--text-primary)' }}>{label}</div>
        {desc && <div className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>{desc}</div>}
      </div>
      <div>{children}</div>
    </div>
  )
}

function NumInput({ value, onChange, min, max, step = 0.1 }: {
  value: number; onChange: (v: number) => void; min: number; max: number; step?: number
}) {
  return (
    <input
      type="number" value={value} min={min} max={max} step={step}
      onChange={e => onChange(parseFloat(e.target.value))}
      className="w-24 px-2 py-1 rounded text-xs font-mono text-right"
      style={{ background: 'var(--bg-elevated)', color: 'var(--text-primary)', border: '1px solid var(--border)' }}
    />
  )
}

export default function SettingsPage() {
  const [settings, setSettings] = useState({
    max_risk_pct:       1.0,
    max_daily_dd_pct:   3.0,
    max_weekly_dd_pct:  6.0,
    max_open_trades:    8,
    signal_threshold:   0.60,
    enabled_instruments: WATCHLIST.slice(),
    agent_interval_min:  15,
  })
  const [saved, setSaved] = useState(false)
  const [status, setStatus] = useState<{ system_status?: string; broker?: string } | null>(null)

  useEffect(() => {
    fetch(`${API}/account`)
      .then(r => r.json())
      .then(d => setStatus(d))
      .catch(() => {})
  }, [])

  const toggle = (sym: string) => {
    setSettings(s => ({
      ...s,
      enabled_instruments: s.enabled_instruments.includes(sym)
        ? s.enabled_instruments.filter(x => x !== sym)
        : [...s.enabled_instruments, sym],
    }))
  }

  const save = async () => {
    await fetch(`${API}/settings`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(settings),
    }).catch(() => {})
    setSaved(true)
    setTimeout(() => setSaved(false), 2000)
  }

  return (
    <div className="flex min-h-screen" style={{ background: 'var(--bg-base)' }}>
      <Sidebar />
      <div className="flex-1 overflow-auto">
        <div className="px-6 py-4 border-b flex items-center justify-between"
             style={{ borderColor: 'var(--border)', background: 'var(--bg-surface)' }}>
          <div>
            <h1 className="font-semibold text-sm" style={{ color: 'var(--text-primary)' }}>Settings</h1>
            <p className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>Risk parameters · Instrument selection</p>
          </div>
          <button
            onClick={save}
            className="px-4 py-1.5 rounded text-xs font-semibold transition-colors"
            style={{ background: saved ? 'var(--bull)' : 'var(--accent)', color: '#000' }}
          >
            {saved ? '✓ Saved' : 'Save Changes'}
          </button>
        </div>

        <div className="p-6 max-w-2xl">

          {/* System status */}
          {status && (
            <div className="mb-6 p-3 rounded border text-xs font-mono"
                 style={{ borderColor: 'var(--border)', background: 'var(--bg-surface)' }}>
              <span style={{ color: 'var(--text-muted)' }}>Broker: </span>
              <span style={{ color: 'var(--text-primary)' }}>{status.broker}</span>
              <span className="mx-3" style={{ color: 'var(--border-bright)' }}>|</span>
              <span style={{ color: 'var(--text-muted)' }}>Mode: </span>
              <span style={{
                color: status.system_status === 'live' ? 'var(--bear)' : 'var(--bull)',
                fontWeight: 'bold',
              }}>
                {(status.system_status || 'unknown').toUpperCase()}
              </span>
            </div>
          )}

          {/* Risk section */}
          <div className="mb-6">
            <div className="text-xs font-semibold tracking-wider mb-2" style={{ color: 'var(--text-muted)' }}>
              RISK MANAGEMENT
            </div>
            <Row label="Max risk per trade" desc="% of account equity at risk on a single trade">
              <NumInput value={settings.max_risk_pct} onChange={v => setSettings(s => ({ ...s, max_risk_pct: v }))} min={0.1} max={3.0} />
            </Row>
            <Row label="Daily drawdown limit %" desc="System pauses all trading when hit">
              <NumInput value={settings.max_daily_dd_pct} onChange={v => setSettings(s => ({ ...s, max_daily_dd_pct: v }))} min={1} max={10} />
            </Row>
            <Row label="Weekly drawdown limit %" desc="Review mode threshold">
              <NumInput value={settings.max_weekly_dd_pct} onChange={v => setSettings(s => ({ ...s, max_weekly_dd_pct: v }))} min={2} max={20} />
            </Row>
            <Row label="Max open trades" desc="Hard ceiling on simultaneous positions">
              <NumInput value={settings.max_open_trades} onChange={v => setSettings(s => ({ ...s, max_open_trades: v }))} min={1} max={20} step={1} />
            </Row>
            <Row label="Signal threshold" desc="Minimum confluence score to execute a trade">
              <NumInput value={settings.signal_threshold} onChange={v => setSettings(s => ({ ...s, signal_threshold: v }))} min={0.50} max={0.95} step={0.01} />
            </Row>
            <Row label="Agent interval (minutes)" desc="How often Claude runs a full analysis cycle">
              <NumInput value={settings.agent_interval_min} onChange={v => setSettings(s => ({ ...s, agent_interval_min: v }))} min={5} max={60} step={5} />
            </Row>
          </div>

          {/* Instrument toggles */}
          <div>
            <div className="text-xs font-semibold tracking-wider mb-2" style={{ color: 'var(--text-muted)' }}>
              INSTRUMENTS  ({settings.enabled_instruments.length} enabled)
            </div>
            <div className="grid grid-cols-4 gap-2">
              {WATCHLIST.map(sym => {
                const on = settings.enabled_instruments.includes(sym)
                return (
                  <button
                    key={sym}
                    onClick={() => toggle(sym)}
                    className="py-1.5 rounded border text-xs font-mono font-semibold transition-colors"
                    style={{
                      borderColor: on ? 'var(--accent)' : 'var(--border)',
                      background:  on ? 'rgba(245,158,11,0.1)' : 'var(--bg-surface)',
                      color:        on ? 'var(--accent)' : 'var(--text-muted)',
                    }}
                  >
                    {sym}
                  </button>
                )
              })}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
