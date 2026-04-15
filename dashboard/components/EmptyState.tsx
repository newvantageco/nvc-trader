'use client'

import Link from 'next/link'
import type { LucideIcon } from 'lucide-react'

interface EmptyStateProps {
  icon: LucideIcon
  title: string
  body: string
  action?: {
    label: string
    href?: string
    onClick?: () => void
  }
  /** Override card padding/max-width for inline use */
  compact?: boolean
}

export default function EmptyState({ icon: Icon, title, body, action, compact }: EmptyStateProps) {
  return (
    <div
      className={`flex flex-col items-center text-center ${compact ? 'py-8' : 'py-16'}`}
    >
      <div
        className="flex items-center justify-center rounded-full mb-4 flex-shrink-0"
        style={{
          width:      compact ? 40 : 52,
          height:     compact ? 40 : 52,
          background: 'var(--bg-elevated)',
          border:     '1px solid var(--border)',
        }}
      >
        <Icon size={compact ? 18 : 22} style={{ color: 'var(--text-muted)' }} />
      </div>

      <div
        className="font-semibold text-sm mb-1"
        style={{ color: 'var(--text-secondary)' }}
      >
        {title}
      </div>
      <div
        className="text-xs max-w-xs leading-relaxed"
        style={{ color: 'var(--text-muted)' }}
      >
        {body}
      </div>

      {action && (
        <div className="mt-5">
          {action.href ? (
            <Link
              href={action.href}
              className="px-4 py-2 rounded text-xs font-semibold transition-opacity hover:opacity-80"
              style={{ background: 'var(--bg-elevated)', color: 'var(--accent)', border: '1px solid var(--border)' }}
            >
              {action.label}
            </Link>
          ) : (
            <button
              onClick={action.onClick}
              className="px-4 py-2 rounded text-xs font-semibold transition-opacity hover:opacity-80"
              style={{ background: 'var(--bg-elevated)', color: 'var(--accent)', border: '1px solid var(--border)' }}
            >
              {action.label}
            </button>
          )}
        </div>
      )}
    </div>
  )
}
