'use client'

import { useEffect, useRef, useState, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import {
  Search, LayoutDashboard, Activity, TrendingUp, BarChart3,
  BookOpen, Brain, ShieldCheck, Settings, Zap, RefreshCw,
  XCircle, Command,
} from 'lucide-react'
import { useNVCStore } from '@/lib/store'
import { api, errorMessage } from '@/lib/api'

const INSTRUMENTS = [
  'EURUSD','GBPUSD','USDJPY','AUDUSD','USDCAD','NZDUSD','USDCHF',
  'EURJPY','GBPJPY','XAUUSD','XAGUSD','USOIL','UKOIL','NATGAS',
]

const PAGES = [
  { href: '/',          label: 'Overview',  icon: LayoutDashboard },
  { href: '/signals',   label: 'Signals',   icon: Activity        },
  { href: '/markets',   label: 'Markets',   icon: TrendingUp      },
  { href: '/analytics', label: 'Analytics', icon: BarChart3       },
  { href: '/research',  label: 'Research',  icon: BookOpen        },
  { href: '/brain',     label: 'Brain',     icon: Brain           },
  { href: '/admin',     label: 'Admin',     icon: ShieldCheck     },
  { href: '/settings',  label: 'Settings',  icon: Settings        },
]

interface Action {
  id: string
  label: string
  sub?: string
  icon: React.ReactNode
  run: () => void | Promise<void>
}

interface CommandPaletteProps {
  open: boolean
  onClose: () => void
}

function Shortcut({ keys }: { keys: string[] }) {
  return (
    <span className="flex items-center gap-0.5">
      {keys.map((k, i) => (
        <kbd
          key={i}
          className="inline-flex items-center justify-center rounded font-mono"
          style={{
            fontSize:    '9px',
            padding:     '1px 4px',
            background:  'var(--bg-base)',
            border:      '1px solid var(--border)',
            color:       'var(--text-muted)',
            lineHeight:  '1.5',
          }}
        >
          {k}
        </kbd>
      ))}
    </span>
  )
}

export default function CommandPalette({ open, onClose }: CommandPaletteProps) {
  const router    = useRouter()
  const addToast  = useNVCStore(s => s.addToast)
  const [query,   setQuery]   = useState('')
  const [cursor,  setCursor]  = useState(0)
  const inputRef  = useRef<HTMLInputElement>(null)
  const listRef   = useRef<HTMLDivElement>(null)
  const debounce  = useRef<ReturnType<typeof setTimeout> | null>(null)
  const [dq, setDq] = useState('')

  // Debounce query
  useEffect(() => {
    if (debounce.current) clearTimeout(debounce.current)
    debounce.current = setTimeout(() => setDq(query), 140)
    return () => { if (debounce.current) clearTimeout(debounce.current) }
  }, [query])

  // Focus input on open
  useEffect(() => {
    if (open) {
      setTimeout(() => inputRef.current?.focus(), 50)
      setQuery('')
      setCursor(0)
    }
  }, [open])

  // Close on Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  const navigate = useCallback((href: string) => {
    router.push(href)
    onClose()
  }, [router, onClose])

  const triggerCycle = useCallback(async (instrument?: string) => {
    onClose()
    try {
      const body = instrument
        ? { trigger: `manual_${instrument}`, instrument }
        : { trigger: 'manual_palette' }
      await api.post('/trigger', body)
      addToast({ type: 'success', title: 'Agent cycle triggered',
        message: instrument ? `Analysing ${instrument}…` : 'Full market scan started' })
    } catch (err) {
      addToast({ type: 'error', title: 'Trigger failed', message: errorMessage(err) })
    }
  }, [addToast, onClose])

  const QUICK_ACTIONS: Action[] = [
    {
      id: 'run-cycle',
      label: 'Run Agent Cycle',
      sub: 'Full market scan · all instruments',
      icon: <Zap size={13} style={{ color: 'var(--accent)' }} />,
      run: () => triggerCycle(),
    },
    {
      id: 'go-overview',
      label: 'Dashboard Overview',
      sub: 'Equity · positions · live scan',
      icon: <LayoutDashboard size={13} style={{ color: 'var(--text-muted)' }} />,
      run: () => navigate('/'),
    },
    {
      id: 'go-brain',
      label: 'Open Brain Log',
      sub: 'Claude reasoning · cycle history',
      icon: <Brain size={13} style={{ color: 'var(--text-muted)' }} />,
      run: () => navigate('/brain'),
    },
    {
      id: 'go-admin',
      label: 'Admin Overview',
      sub: 'Account · risk · performance',
      icon: <ShieldCheck size={13} style={{ color: 'var(--text-muted)' }} />,
      run: () => navigate('/admin'),
    },
  ]

  // Build filtered items
  const q = dq.trim().toLowerCase()

  const instrumentItems: Action[] = INSTRUMENTS
    .filter(s => !q || s.toLowerCase().includes(q))
    .map(sym => ({
      id: `instr-${sym}`,
      label: sym,
      sub: 'Trigger agent scan for this pair',
      icon: <RefreshCw size={11} style={{ color: 'var(--accent)' }} />,
      run: () => triggerCycle(sym),
    }))

  const pageItems: Action[] = PAGES
    .filter(p => !q || p.label.toLowerCase().includes(q))
    .map(p => ({
      id: `page-${p.href}`,
      label: p.label,
      sub: p.href === '/' ? '/' : p.href,
      icon: <p.icon size={13} style={{ color: 'var(--text-muted)' }} />,
      run: () => navigate(p.href),
    }))

  const quickActions = QUICK_ACTIONS.filter(
    a => !q || a.label.toLowerCase().includes(q) || (a.sub?.toLowerCase().includes(q) ?? false)
  )

  type Section = { title: string; items: Action[] }
  const sections: Section[] = []
  if (quickActions.length)   sections.push({ title: 'Quick Actions',  items: quickActions })
  if (instrumentItems.length) sections.push({ title: 'Instruments',   items: instrumentItems })
  if (pageItems.length)      sections.push({ title: 'Navigation',     items: pageItems })

  const allItems = sections.flatMap(s => s.items)
  const safeCursor = Math.min(cursor, allItems.length - 1)

  const handleKey = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setCursor(c => Math.min(c + 1, allItems.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setCursor(c => Math.max(c - 1, 0))
    } else if (e.key === 'Enter') {
      e.preventDefault()
      allItems[safeCursor]?.run()
    } else if (e.key === 'Tab') {
      e.preventDefault()
      setCursor(c => (c + 1) % Math.max(allItems.length, 1))
    }
  }

  // Scroll active item into view
  useEffect(() => {
    const el = listRef.current?.querySelector<HTMLElement>('[data-active="true"]')
    el?.scrollIntoView({ block: 'nearest' })
  }, [safeCursor])

  // Reset cursor on query change
  useEffect(() => { setCursor(0) }, [dq])

  if (!open) return null

  let globalIdx = 0

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center pt-[15vh]"
      style={{ background: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(2px)' }}
      onMouseDown={e => { if (e.target === e.currentTarget) onClose() }}
    >
      <div
        className="w-full max-w-lg rounded-xl overflow-hidden shadow-2xl"
        style={{
          background: 'var(--bg-surface)',
          border:     '1px solid var(--border-bright)',
          maxHeight:  'min(70vh, 520px)',
          display:    'flex',
          flexDirection: 'column',
        }}
      >
        {/* Search bar */}
        <div
          className="flex items-center gap-3 px-4 py-3 border-b flex-shrink-0"
          style={{ borderColor: 'var(--border)' }}
        >
          <Search size={15} style={{ color: 'var(--text-muted)', flexShrink: 0 }} />
          <input
            ref={inputRef}
            value={query}
            onChange={e => setQuery(e.target.value)}
            onKeyDown={handleKey}
            placeholder="Search instruments, actions, pages…"
            className="flex-1 bg-transparent outline-none text-sm font-mono"
            style={{ color: 'var(--text-primary)', caretColor: 'var(--accent)' }}
            autoComplete="off"
            spellCheck={false}
          />
          {query && (
            <button onClick={() => setQuery('')} style={{ color: 'var(--text-muted)' }}>
              <XCircle size={13} />
            </button>
          )}
          <Shortcut keys={['Esc']} />
        </div>

        {/* Results */}
        <div ref={listRef} className="overflow-y-auto flex-1" style={{ overscrollBehavior: 'contain' }}>
          {allItems.length === 0 ? (
            <div className="px-4 py-10 text-center text-xs font-mono" style={{ color: 'var(--text-muted)' }}>
              No results for &ldquo;{query}&rdquo;
            </div>
          ) : (
            sections.map(section => (
              <div key={section.title}>
                <div
                  className="px-4 pt-3 pb-1 text-[10px] font-semibold tracking-wider uppercase"
                  style={{ color: 'var(--text-muted)' }}
                >
                  {section.title}
                </div>
                {section.items.map(item => {
                  const idx    = globalIdx++
                  const active = idx === safeCursor
                  return (
                    <button
                      key={item.id}
                      data-active={active}
                      onClick={() => item.run()}
                      onMouseEnter={() => setCursor(idx)}
                      className="w-full flex items-center gap-3 px-4 py-2.5 text-left transition-colors"
                      style={{
                        background: active ? 'var(--accent-dim)' : 'transparent',
                        borderLeft: active ? '2px solid var(--accent)' : '2px solid transparent',
                      }}
                    >
                      <span className="flex-shrink-0 w-5 flex items-center justify-center">
                        {item.icon}
                      </span>
                      <span className="flex-1 min-w-0">
                        <span
                          className="block text-xs font-semibold font-mono truncate"
                          style={{ color: active ? 'var(--accent)' : 'var(--text-primary)' }}
                        >
                          {item.label}
                        </span>
                        {item.sub && (
                          <span
                            className="block text-[10px] truncate"
                            style={{ color: 'var(--text-muted)' }}
                          >
                            {item.sub}
                          </span>
                        )}
                      </span>
                      {active && (
                        <span className="text-[9px] font-mono flex-shrink-0" style={{ color: 'var(--text-muted)' }}>
                          ↵
                        </span>
                      )}
                    </button>
                  )
                })}
              </div>
            ))
          )}
        </div>

        {/* Footer */}
        <div
          className="flex items-center gap-4 px-4 py-2 border-t flex-shrink-0"
          style={{ borderColor: 'var(--border)', background: 'var(--bg-elevated)' }}
        >
          <div className="flex items-center gap-1.5 text-[10px] font-mono" style={{ color: 'var(--text-muted)' }}>
            <Shortcut keys={['↑', '↓']} />
            <span>navigate</span>
          </div>
          <div className="flex items-center gap-1.5 text-[10px] font-mono" style={{ color: 'var(--text-muted)' }}>
            <Shortcut keys={['↵']} />
            <span>select</span>
          </div>
          <div className="flex items-center gap-1.5 text-[10px] font-mono" style={{ color: 'var(--text-muted)' }}>
            <Shortcut keys={['Tab']} />
            <span>cycle</span>
          </div>
          <div className="ml-auto flex items-center gap-1 text-[10px] font-mono" style={{ color: 'var(--text-muted)' }}>
            <Command size={9} />
            <span>K to open</span>
          </div>
        </div>
      </div>
    </div>
  )
}
