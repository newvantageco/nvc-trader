'use client'

import { useEffect } from 'react'
import { CheckCircle, AlertTriangle, XCircle, Info, X } from 'lucide-react'
import { useNVCStore, Toast } from '@/lib/store'

const ICONS = {
  success: CheckCircle,
  error:   XCircle,
  warning: AlertTriangle,
  info:    Info,
}

const COLORS = {
  success: { border: 'rgba(16,185,129,0.4)',  icon: 'var(--bull)',    bg: 'rgba(16,185,129,0.08)'  },
  error:   { border: 'rgba(239,68,68,0.4)',   icon: 'var(--bear)',   bg: 'rgba(239,68,68,0.08)'   },
  warning: { border: 'rgba(245,158,11,0.4)',  icon: 'var(--accent)', bg: 'rgba(245,158,11,0.08)'  },
  info:    { border: 'rgba(148,163,184,0.3)', icon: 'var(--text-secondary)', bg: 'rgba(148,163,184,0.06)' },
}

const AUTO_DISMISS_MS = 5000

function ToastItem({ toast }: { toast: Toast }) {
  const removeToast = useNVCStore(s => s.removeToast)
  const Icon   = ICONS[toast.type]
  const colors = COLORS[toast.type]

  useEffect(() => {
    const t = setTimeout(() => removeToast(toast.id), AUTO_DISMISS_MS)
    return () => clearTimeout(t)
  }, [toast.id, removeToast])

  return (
    <div
      className="flex items-start gap-3 px-3 py-2.5 rounded pointer-events-auto"
      style={{
        background:  colors.bg,
        border:      `1px solid ${colors.border}`,
        backdropFilter: 'blur(8px)',
        minWidth: 240,
        maxWidth: 320,
        animation: 'toastIn 200ms ease-out',
      }}
    >
      <Icon size={14} style={{ color: colors.icon, flexShrink: 0, marginTop: 1 }} />
      <div className="flex-1 min-w-0">
        <div className="text-xs font-semibold font-mono leading-snug"
             style={{ color: 'var(--text-primary)' }}>
          {toast.title}
        </div>
        {toast.message && (
          <div className="text-xs mt-0.5 font-mono leading-snug"
               style={{ color: 'var(--text-secondary)' }}>
            {toast.message}
          </div>
        )}
      </div>
      <button
        onClick={() => removeToast(toast.id)}
        className="flex-shrink-0 opacity-50 hover:opacity-100 transition-opacity"
        style={{ color: 'var(--text-muted)' }}
      >
        <X size={11} />
      </button>
    </div>
  )
}

export default function ToastContainer() {
  const toasts = useNVCStore(s => s.toasts)
  if (toasts.length === 0) return null

  return (
    <div
      className="fixed bottom-4 right-4 flex flex-col gap-2 z-50 pointer-events-none"
      style={{ fontFamily: 'var(--font-mono)' }}
    >
      {toasts.map(t => <ToastItem key={t.id} toast={t} />)}
    </div>
  )
}
