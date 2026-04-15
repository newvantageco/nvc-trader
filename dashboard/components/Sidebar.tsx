'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import {
  LayoutDashboard, TrendingUp, BarChart3, Settings,
  Activity, Brain, ShieldCheck, BookOpen,
  Zap, Search,
} from 'lucide-react'
import { useNVCStore } from '@/lib/store'
import NotificationBell from '@/components/NotificationBell'

const NAV = [
  { href: '/',          label: 'Overview',   icon: LayoutDashboard, primary: true },
  { href: '/signals',   label: 'Signals',    icon: Activity,        primary: true },
  { href: '/markets',   label: 'Markets',    icon: TrendingUp,      primary: true },
  { href: '/analytics', label: 'Analytics',  icon: BarChart3,       primary: true },
  { href: '/research',  label: 'Research',   icon: BookOpen,        primary: false },
  { href: '/brain',     label: 'Brain',      icon: Brain,           primary: false },
  { href: '/admin',     label: 'Admin',      icon: ShieldCheck,     primary: false },
  { href: '/settings',  label: 'Settings',   icon: Settings,        primary: false },
]

function AgentDot() {
  const { agentStatus, connected } = useNVCStore()
  if (!connected) return <span className="dot-idle" />
  if (agentStatus === 'emergency_stop') return <span className="dot-stop" />
  if (agentStatus === 'paused') return <span className="dot-warn" />
  return <span className="dot-live" />
}

// Desktop: 200px sidebar with icon + label
export function DesktopSidebar({ onOpenPalette }: { onOpenPalette?: () => void }) {
  const pathname = usePathname()

  return (
    <aside
      className="hidden sm:flex flex-shrink-0 flex-col py-5 border-r"
      style={{
        width: 200,
        background: 'var(--bg-surface)',
        borderColor: 'var(--border)',
      }}
      aria-label="Main navigation"
    >
      {/* Brand */}
      <div className="px-5 mb-6 flex items-center gap-2.5">
        <div
          className="w-7 h-7 rounded flex items-center justify-center flex-shrink-0"
          style={{ background: 'var(--accent-dim)', border: '1px solid rgba(240,165,0,0.25)' }}
        >
          <Zap size={14} style={{ color: 'var(--accent)' }} />
        </div>
        <div>
          <div className="font-mono font-bold text-sm leading-none" style={{ color: 'var(--accent)', letterSpacing: '0.1em' }}>
            NVC
          </div>
          <div className="font-mono text-[9px] leading-none mt-0.5" style={{ color: 'var(--text-muted)', letterSpacing: '0.08em' }}>
            VANTAGE
          </div>
        </div>
      </div>

      {/* Primary nav */}
      <nav className="flex-1 px-3" role="navigation">
        <div className="section-label px-2 mb-2">Trading</div>
        {NAV.filter(n => n.primary).map(({ href, label, icon: Icon }) => {
          const active = pathname === href
          return (
            <Link
              key={href}
              href={href}
              aria-current={active ? 'page' : undefined}
              className="flex items-center gap-3 px-2 py-2 rounded mb-0.5 transition-colors"
              style={{
                background:  active ? 'var(--accent-dim)' : 'transparent',
                color:       active ? 'var(--accent)'     : 'var(--text-secondary)',
                borderLeft:  active ? '2px solid var(--accent)' : '2px solid transparent',
                fontWeight:  active ? 600 : 400,
              }}
            >
              <Icon size={15} aria-hidden="true" style={{ flexShrink: 0 }} />
              <span className="text-xs tracking-wide">{label}</span>
            </Link>
          )
        })}

        <div className="section-label px-2 mt-4 mb-2">Tools</div>
        {NAV.filter(n => !n.primary).map(({ href, label, icon: Icon }) => {
          const active = pathname === href
          return (
            <Link
              key={href}
              href={href}
              aria-current={active ? 'page' : undefined}
              className="flex items-center gap-3 px-2 py-2 rounded mb-0.5 transition-colors"
              style={{
                background:  active ? 'var(--accent-dim)' : 'transparent',
                color:       active ? 'var(--accent)'     : 'var(--text-muted)',
                borderLeft:  active ? '2px solid var(--accent)' : '2px solid transparent',
              }}
            >
              <Icon size={15} aria-hidden="true" style={{ flexShrink: 0 }} />
              <span className="text-xs tracking-wide">{label}</span>
            </Link>
          )
        })}
      </nav>

      {/* Cmd+K search trigger */}
      {onOpenPalette && (
        <div className="px-3 mb-3">
          <button
            onClick={onOpenPalette}
            className="w-full flex items-center gap-2 px-2.5 py-1.5 rounded text-xs transition-opacity hover:opacity-80"
            style={{
              background:  'var(--bg-elevated)',
              border:      '1px solid var(--border)',
              color:       'var(--text-muted)',
            }}
            aria-label="Open command palette (⌘K)"
          >
            <Search size={11} />
            <span className="flex-1 text-left font-mono text-[10px]">Search…</span>
            <kbd
              className="font-mono rounded"
              style={{ fontSize: 9, padding: '1px 4px', background: 'var(--bg-base)', border: '1px solid var(--border)' }}
            >
              ⌘K
            </kbd>
          </button>
        </div>
      )}

      {/* Agent status footer */}
      <div className="px-5 pb-1">
        <div
          className="flex items-center gap-2.5 px-3 py-2 rounded"
          style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border)' }}
        >
          <AgentDot />
          <div className="min-w-0 flex-1">
            <div className="text-xs font-semibold" style={{ color: 'var(--text-primary)' }}>
              Vantage AI
            </div>
            <div className="text-[10px] truncate" style={{ color: 'var(--text-muted)' }}>
              claude-opus-4-6
            </div>
          </div>
          <NotificationBell />
        </div>
      </div>
    </aside>
  )
}

// Mobile: bottom nav bar — 5 key items only
export function MobileNav() {
  const pathname = usePathname()
  const mobileNav = NAV.filter(n => ['/', '/signals', '/markets', '/analytics', '/settings'].includes(n.href))
  return (
    <nav
      className="sm:hidden fixed bottom-0 inset-x-0 flex items-center justify-around border-t z-50"
      style={{ background: 'var(--bg-surface)', borderColor: 'var(--border)', height: 56 }}
      role="navigation"
      aria-label="Mobile navigation"
    >
      {mobileNav.map(({ href, label, icon: Icon }) => {
        const active = pathname === href
        return (
          <Link
            key={href}
            href={href}
            aria-current={active ? 'page' : undefined}
            className="flex flex-col items-center justify-center gap-1 flex-1 py-2"
            style={{ color: active ? 'var(--accent)' : 'var(--text-muted)' }}
          >
            <Icon size={18} aria-hidden="true" />
            <span style={{ fontSize: 9, fontWeight: active ? 600 : 400, letterSpacing: '0.04em' }}>
              {label}
            </span>
          </Link>
        )
      })}
    </nav>
  )
}

export default function Sidebar() {
  return <DesktopSidebar />
}
