'use client'

interface StatusConfig {
  dot:    string   // CSS color for pulsing dot
  text:   string   // display label
  color:  string   // text color (CSS var or hex)
  bg:     string   // background color
  border: string   // border color
}

const STATUS_MAP: Record<string, StatusConfig> = {
  // Order fill statuses
  FILLED:    { dot: 'var(--bull)',    text: 'FILLED',    color: 'var(--bull)',         bg: 'rgba(46,168,74,0.12)',   border: 'rgba(46,168,74,0.3)'   },
  CANCELLED: { dot: 'var(--text-muted)', text: 'CANCELLED', color: 'var(--text-muted)', bg: 'var(--bg-elevated)',     border: 'var(--border)'         },
  REJECTED:  { dot: 'var(--bear)',    text: 'REJECTED',  color: 'var(--bear)',         bg: 'rgba(229,72,62,0.12)',   border: 'rgba(229,72,62,0.3)'   },
  PENDING:   { dot: 'var(--accent)',  text: 'PENDING',   color: 'var(--accent)',       bg: 'rgba(240,165,0,0.10)',   border: 'rgba(240,165,0,0.25)'  },
  PARTIAL:   { dot: 'var(--accent)',  text: 'PARTIAL',   color: 'var(--accent)',       bg: 'rgba(240,165,0,0.10)',   border: 'rgba(240,165,0,0.25)'  },
  EXPIRED:   { dot: 'var(--text-muted)', text: 'EXPIRED', color: 'var(--text-muted)', bg: 'var(--bg-elevated)',     border: 'var(--border)'         },

  // Signal edge grades
  'A++':     { dot: 'var(--grade-axx)', text: 'A++',    color: 'var(--grade-axx)',    bg: 'rgba(240,165,0,0.15)',   border: 'rgba(240,165,0,0.35)'  },
  'A+':      { dot: 'var(--grade-ax)',  text: 'A+',     color: 'var(--grade-ax)',     bg: 'rgba(99,220,99,0.12)',   border: 'rgba(99,220,99,0.3)'   },
  'A':       { dot: 'var(--grade-a)',   text: 'A',      color: 'var(--grade-a)',      bg: 'rgba(16,185,129,0.12)',  border: 'rgba(16,185,129,0.3)'  },
  'FAIL':    { dot: 'var(--text-muted)', text: 'FAIL',  color: 'var(--text-muted)',   bg: 'var(--bg-elevated)',     border: 'var(--border)'         },

  // Account / circuit breaker
  ACTIVE:    { dot: 'var(--bull)',    text: 'ACTIVE',    color: 'var(--bull)',         bg: 'rgba(46,168,74,0.08)',   border: 'rgba(46,168,74,0.2)'   },
  HALTED:    { dot: 'var(--bear)',    text: 'HALTED',    color: 'var(--bear)',         bg: 'rgba(229,72,62,0.12)',   border: 'rgba(229,72,62,0.3)'   },
  'HARD STOP': { dot: 'var(--bear)', text: 'HARD STOP', color: 'var(--bear)',         bg: 'rgba(229,72,62,0.15)',   border: 'rgba(229,72,62,0.4)'   },
  WARNING:   { dot: 'var(--accent)', text: 'WARNING',   color: 'var(--accent)',       bg: 'rgba(240,165,0,0.10)',   border: 'rgba(240,165,0,0.25)'  },
  'HALF SIZE': { dot: 'var(--accent)', text: 'HALF SIZE', color: 'var(--accent)',     bg: 'rgba(240,165,0,0.10)',   border: 'rgba(240,165,0,0.25)'  },

  // Broker mode
  DEMO:      { dot: 'var(--bull)',    text: 'DEMO',      color: 'var(--bull)',         bg: 'rgba(46,168,74,0.08)',   border: 'rgba(46,168,74,0.2)'   },
  LIVE:      { dot: 'var(--bear)',    text: 'LIVE',      color: 'var(--bear)',         bg: 'rgba(229,72,62,0.12)',   border: 'rgba(229,72,62,0.3)'   },
  PAPER:     { dot: 'var(--accent)',  text: 'PAPER',     color: 'var(--accent)',       bg: 'rgba(240,165,0,0.08)',   border: 'rgba(240,165,0,0.2)'   },

  // Agent cycle triggers
  SCHEDULED: { dot: 'var(--text-muted)', text: 'SCHEDULED', color: 'var(--text-muted)', bg: 'var(--bg-elevated)', border: 'var(--border)'         },
  MANUAL:    { dot: 'var(--accent)',  text: 'MANUAL',    color: 'var(--accent)',       bg: 'rgba(240,165,0,0.08)',   border: 'rgba(240,165,0,0.2)'   },

  // Direction
  BUY:       { dot: 'var(--bull)',    text: 'BUY',       color: 'var(--bull)',         bg: 'rgba(16,185,129,0.15)', border: 'rgba(16,185,129,0.3)'  },
  SELL:      { dot: 'var(--bear)',    text: 'SELL',      color: 'var(--bear)',         bg: 'rgba(239,68,68,0.15)',   border: 'rgba(239,68,68,0.3)'   },
  NEUTRAL:   { dot: 'var(--text-muted)', text: 'NEUTRAL', color: 'var(--text-muted)', bg: 'var(--bg-elevated)',     border: 'var(--border)'         },
}

const FALLBACK: StatusConfig = {
  dot: 'var(--text-muted)', text: '—', color: 'var(--text-muted)',
  bg: 'var(--bg-elevated)', border: 'var(--border)',
}

export function getStatusConfig(status: string): StatusConfig {
  return STATUS_MAP[status?.toUpperCase?.()] ?? STATUS_MAP[status] ?? FALLBACK
}

interface StatusBadgeProps {
  status: string
  /** Show label text (default true) */
  showLabel?: boolean
  /** Show dot indicator (default false) */
  showDot?: boolean
  className?: string
}

export function StatusBadge({ status, showLabel = true, showDot = false, className }: StatusBadgeProps) {
  const cfg = getStatusConfig(status)
  return (
    <span
      className={`inline-flex items-center gap-1 font-mono font-semibold rounded ${className ?? ''}`}
      style={{
        fontSize:        '10px',
        padding:         '2px 6px',
        background:      cfg.bg,
        color:           cfg.color,
        border:          `1px solid ${cfg.border}`,
        letterSpacing:   '0.06em',
        lineHeight:      '1.4',
      }}
    >
      {showDot && (
        <span
          className="inline-block rounded-full flex-shrink-0"
          style={{ width: 5, height: 5, background: cfg.dot }}
        />
      )}
      {showLabel && cfg.text}
    </span>
  )
}

/** Status badge with live-pulsing dot indicator */
export function LiveStatusBadge({ status, className }: { status: string; className?: string }) {
  const cfg = getStatusConfig(status)
  const isLive = ['ACTIVE', 'LIVE', 'DEMO', 'PENDING', 'MANUAL'].includes(status?.toUpperCase?.() ?? status)
  return (
    <span
      className={`inline-flex items-center gap-1.5 font-mono font-semibold rounded ${className ?? ''}`}
      style={{
        fontSize:      '10px',
        padding:       '2px 7px',
        background:    cfg.bg,
        color:         cfg.color,
        border:        `1px solid ${cfg.border}`,
        letterSpacing: '0.06em',
        lineHeight:    '1.4',
      }}
    >
      <span
        className={`inline-block rounded-full flex-shrink-0${isLive ? ' animate-pulse' : ''}`}
        style={{ width: 5, height: 5, background: cfg.dot }}
      />
      {cfg.text}
    </span>
  )
}

export default StatusBadge
