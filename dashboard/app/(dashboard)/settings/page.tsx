'use client'

import { useEffect, useState } from 'react'
import { useNVCStore } from '@/lib/store'

const API = process.env.NEXT_PUBLIC_API_URL || 'https://nvc-trader.fly.dev'

const WATCHLIST = ['EURUSD','GBPUSD','USDJPY','AUDUSD','USDCAD','NZDUSD','USDCHF','EURJPY','GBPJPY','XAUUSD','XAGUSD','USOIL','UKOIL','NATGAS']

interface Settings {
  max_risk_pct:         number
  max_daily_dd_pct:     number
  max_weekly_dd_pct:    number
  max_open_trades:      number
  signal_threshold:     number
  enabled_instruments:  string[]
  agent_interval_min:   number
}

const DEFAULTS: Settings = {
  max_risk_pct: 1.0, max_daily_dd_pct: 2.0, max_weekly_dd_pct: 5.0,
  max_open_trades: 8, signal_threshold: 0.60, enabled_instruments: WATCHLIST.slice(),
  agent_interval_min: 15,
}

const BOUNDS = {
  max_risk_pct:       { min: 0.1,  max: 3.0,  step: 0.1  },
  max_daily_dd_pct:   { min: 1.0,  max: 10.0, step: 0.5  },
  max_weekly_dd_pct:  { min: 2.0,  max: 20.0, step: 1.0  },
  max_open_trades:    { min: 1,    max: 20,   step: 1    },
  signal_threshold:   { min: 0.50, max: 0.95, step: 0.01 },
  agent_interval_min: { min: 5,    max: 60,   step: 5    },
}

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

function NumInput({ field, value, onChange }: {
  field: keyof typeof BOUNDS; value: number; onChange: (v: number) => void
}) {
  const { min, max, step } = BOUNDS[field]
  const invalid = value < min || value > max || isNaN(value)
  return (
    <input
      type="number" value={value} min={min} max={max} step={step}
      onChange={e => onChange(parseFloat(e.target.value))}
      className="w-24 px-2 py-1 rounded text-xs font-mono text-right"
      style={{
        background:  'var(--bg-elevated)',
        color:       invalid ? 'var(--bear)' : 'var(--text-primary)',
        border:      `1px solid ${invalid ? 'rgba(239,68,68,0.6)' : 'var(--border)'}`,
      }}
      aria-invalid={invalid}
    />
  )
}

export default function SettingsPage() {
  const addToast = useNVCStore(s => s.addToast)
  const [settings, setSettings] = useState<Settings>(DEFAULTS)
  const [saving,   setSaving]   = useState(false)
  const [saveState, setSaveState] = useState<'idle' | 'saved' | 'error'>('idle')
  const [status,   setStatus]   = useState<{ system_status?: string; broker?: string } | null>(null)

  useEffect(() => {
    fetch(`${API}/settings`)
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d && Object.keys(d).length) setSettings({ ...DEFAULTS, ...d }) })
      .catch(() => {})

    fetch(`${API}/account`)
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d) setStatus(d) })
      .catch(() => {})
  }, [])

  const hasErrors = Object.keys(BOUNDS).some(k => {
    const key  = k as keyof typeof BOUNDS
    const val  = settings[key as keyof Settings] as number
    const { min, max } = BOUNDS[key]
    return isNaN(val) || val < min || val > max
  })

  const save = async () => {
    if (hasErrors) {
      addToast({ type: 'error', title: 'Invalid settings', message: 'Fix highlighted values before saving' })
      return
    }
    setSaving(true)
    try {
      const r = await fetch(`${API}/settings`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(settings),
      })
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      setSaveState('saved')
      addToast({ type: 'success', title: 'Settings saved', message: 'Risk parameters updated' })
      setTimeout(() => setSaveState('idle'), 2500)
    } catch (err) {
      setSaveState('error')
      addToast({ type: 'error', title: 'Save failed', message: 'Could not reach the engine' })
      setTimeout(() => setSaveState('idle'), 3000)
    } finally {
      setSaving(false)
    }
  }

  const toggle = (sym: string) => setSettings(s => ({
    ...s,
    enabled_instruments: s.enabled_instruments.includes(sym)
      ? s.enabled_instruments.filter(x => x !== sym)
      : [...s.enabled_instruments, sym],
  }))

  const btnLabel = saving ? 'Saving…' : saveState === 'saved' ? '✓ Saved' : saveState === 'error' ? '✗ Failed' : 'Save Changes'
  const btnColor = saveState === 'saved' ? 'var(--bull)' : saveState === 'error' ? 'var(--bear)' : hasErrors ? 'var(--text-muted)' : 'var(--accent)'

  return (
    <div className="flex flex-col h-full overflow-auto" style={{ background: 'var(--bg-base)' }}>

      {/* Header */}
      <div className="px-6 py-3 border-b flex items-center justify-between flex-shrink-0"
           style={{ borderColor: 'var(--border)', background: 'var(--bg-surface)' }}>
        <div>
          <h1 className="font-semibold text-sm" style={{ color: 'var(--text-primary)' }}>Settings</h1>
          <p className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>Risk parameters · Instrument selection</p>
        </div>
        <button
          onClick={save}
          disabled={saving || hasErrors}
          className="px-4 py-1.5 rounded text-xs font-semibold transition-colors disabled:opacity-50"
          style={{ background: btnColor, color: '#000' }}
          aria-label="Save settings"
        >
          {btnLabel}
        </button>
      </div>

      <div className="p-6 max-w-2xl">

        {/* System status */}
        {status && (
          <div className="mb-6 p-3 rounded border text-xs font-mono"
               style={{ borderColor: 'var(--border)', background: 'var(--bg-surface)' }}>
            <span style={{ color: 'var(--text-muted)' }}>Broker: </span>
            <span style={{ color: 'var(--text-primary)' }}>{status.broker ?? '—'}</span>
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
          <div className="text-xs font-semibold tracking-wider mb-2 uppercase"
               style={{ color: 'var(--text-muted)' }}>Risk Management</div>
          <Row label="Max risk per trade" desc="% of account equity at risk on a single trade">
            <NumInput field="max_risk_pct" value={settings.max_risk_pct}
              onChange={v => setSettings(s => ({ ...s, max_risk_pct: v }))} />
          </Row>
          <Row label="Daily drawdown limit %" desc="System pauses all trading when hit">
            <NumInput field="max_daily_dd_pct" value={settings.max_daily_dd_pct}
              onChange={v => setSettings(s => ({ ...s, max_daily_dd_pct: v }))} />
          </Row>
          <Row label="Weekly drawdown limit %" desc="Review mode threshold">
            <NumInput field="max_weekly_dd_pct" value={settings.max_weekly_dd_pct}
              onChange={v => setSettings(s => ({ ...s, max_weekly_dd_pct: v }))} />
          </Row>
          <Row label="Max open trades" desc="Hard ceiling on simultaneous positions">
            <NumInput field="max_open_trades" value={settings.max_open_trades}
              onChange={v => setSettings(s => ({ ...s, max_open_trades: v }))} />
          </Row>
          <Row label="Signal threshold" desc="Minimum confluence score to execute (0.50–0.95)">
            <NumInput field="signal_threshold" value={settings.signal_threshold}
              onChange={v => setSettings(s => ({ ...s, signal_threshold: v }))} />
          </Row>
          <Row label="Agent interval (minutes)" desc="How often Claude runs a full analysis cycle">
            <NumInput field="agent_interval_min" value={settings.agent_interval_min}
              onChange={v => setSettings(s => ({ ...s, agent_interval_min: v }))} />
          </Row>
        </div>

        {/* Instrument toggles */}
        <div>
          <div className="text-xs font-semibold tracking-wider mb-2 uppercase"
               style={{ color: 'var(--text-muted)' }}>
            Instruments ({settings.enabled_instruments.length} enabled)
          </div>
          <div className="grid grid-cols-4 gap-2">
            {WATCHLIST.map(sym => {
              const on = settings.enabled_instruments.includes(sym)
              return (
                <button
                  key={sym}
                  onClick={() => toggle(sym)}
                  aria-pressed={on}
                  aria-label={`${on ? 'Disable' : 'Enable'} ${sym}`}
                  className="py-1.5 rounded border text-xs font-mono font-semibold transition-all"
                  style={{
                    borderColor: on ? 'var(--accent)' : 'var(--border)',
                    background:  on ? 'rgba(245,158,11,0.1)' : 'var(--bg-surface)',
                    color:       on ? 'var(--accent)'         : 'var(--text-muted)',
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
  )
}
