'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { LayoutDashboard, TrendingUp, BarChart3, Settings, Activity, Brain } from 'lucide-react'

const NAV = [
  { href: '/',           label: 'Terminal',  icon: LayoutDashboard },
  { href: '/signals',    label: 'Signals',   icon: Activity },
  { href: '/markets',    label: 'Markets',   icon: TrendingUp },
  { href: '/analytics',  label: 'Analytics', icon: BarChart3 },
  { href: '/brain',      label: 'Brain',     icon: Brain },
  { href: '/settings',   label: 'Settings',  icon: Settings },
]

export default function Sidebar() {
  const pathname = usePathname()
  return (
    <aside
      className="w-14 flex-shrink-0 flex flex-col items-center py-4 gap-1 border-r"
      style={{ background: 'var(--bg-surface)', borderColor: 'var(--border)' }}
    >
      {/* Logo mark */}
      <div className="mb-4 font-mono font-bold text-xs"
           style={{ color: 'var(--accent)', letterSpacing: '0.15em' }}>
        NVC
      </div>

      {NAV.map(({ href, label, icon: Icon }) => {
        const active = pathname === href
        return (
          <Link
            key={href}
            href={href}
            title={label}
            className="w-10 h-10 flex items-center justify-center rounded transition-colors"
            style={{
              background:  active ? 'var(--bg-elevated)' : 'transparent',
              color:       active ? 'var(--accent)'      : 'var(--text-muted)',
              borderLeft:  active ? `2px solid var(--accent)` : '2px solid transparent',
            }}
          >
            <Icon size={18} />
          </Link>
        )
      })}
    </aside>
  )
}
