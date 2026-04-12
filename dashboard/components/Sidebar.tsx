'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { LayoutDashboard, TrendingUp, BarChart3, Settings, Activity, Brain, ShieldCheck } from 'lucide-react'

const NAV = [
  { href: '/',           label: 'Terminal',  icon: LayoutDashboard },
  { href: '/signals',    label: 'Signals',   icon: Activity },
  { href: '/markets',    label: 'Markets',   icon: TrendingUp },
  { href: '/analytics',  label: 'Analytics', icon: BarChart3 },
  { href: '/brain',      label: 'Brain',     icon: Brain },
  { href: '/admin',      label: 'Admin',     icon: ShieldCheck },
  { href: '/settings',   label: 'Settings',  icon: Settings },
]

// Desktop: vertical icon rail (hidden on mobile)
export function DesktopSidebar() {
  const pathname = usePathname()
  return (
    <aside
      className="hidden sm:flex w-14 flex-shrink-0 flex-col items-center py-4 gap-1 border-r"
      style={{ background: 'var(--bg-surface)', borderColor: 'var(--border)' }}
      aria-label="Main navigation"
    >
      <div className="mb-4 font-mono font-bold text-xs"
           aria-label="NVC Trading"
           style={{ color: 'var(--accent)', letterSpacing: '0.15em' }}>
        NVC
      </div>

      <nav role="navigation">
        {NAV.map(({ href, label, icon: Icon }) => {
          const active = pathname === href
          return (
            <Link
              key={href}
              href={href}
              aria-label={label}
              aria-current={active ? 'page' : undefined}
              title={label}
              className="w-10 h-10 flex items-center justify-center rounded transition-colors mb-1"
              style={{
                background:  active ? 'var(--bg-elevated)' : 'transparent',
                color:       active ? 'var(--accent)'      : 'var(--text-muted)',
                borderLeft:  active ? '2px solid var(--accent)' : '2px solid transparent',
              }}
            >
              <Icon size={18} aria-hidden="true" />
            </Link>
          )
        })}
      </nav>
    </aside>
  )
}

// Mobile: bottom nav bar (visible only on mobile)
export function MobileNav() {
  const pathname = usePathname()
  // Only show the 5 most important nav items on mobile to avoid crowding
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
            aria-label={label}
            aria-current={active ? 'page' : undefined}
            className="flex flex-col items-center justify-center gap-0.5 flex-1 py-2"
            style={{ color: active ? 'var(--accent)' : 'var(--text-muted)' }}
          >
            <Icon size={20} aria-hidden="true" />
            <span className="text-[9px] font-medium tracking-wide">{label}</span>
          </Link>
        )
      })}
    </nav>
  )
}

// Default export kept for backward compatibility (desktop only)
export default function Sidebar() {
  return <DesktopSidebar />
}
