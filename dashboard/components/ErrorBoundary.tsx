'use client'

import { Component, type ReactNode, type ErrorInfo } from 'react'
import { AlertTriangle, RefreshCw } from 'lucide-react'

interface Props {
  children:  ReactNode
  fallback?: ReactNode
  onError?:  (error: Error, info: ErrorInfo) => void
}

interface State {
  error: Error | null
}

/**
 * ErrorBoundary — catches React render errors in a subtree.
 *
 * Wrap around components that can throw (charts with bad data,
 * dynamic imports, third-party widgets):
 *
 *   <ErrorBoundary>
 *     <TradingCharts />
 *   </ErrorBoundary>
 *
 * Use the `fallback` prop for a custom UI, or omit for the default.
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('[ErrorBoundary]', error, info.componentStack)
    this.props.onError?.(error, info)
  }

  reset = () => this.setState({ error: null })

  render() {
    if (this.state.error) {
      if (this.props.fallback) return this.props.fallback
      return (
        <div
          className="flex flex-col items-center justify-center gap-3 p-6 rounded border font-mono"
          style={{
            background:   'var(--bg-surface)',
            borderColor:  'rgba(229,72,62,0.25)',
            color:        'var(--text-muted)',
            minHeight:    120,
          }}
        >
          <AlertTriangle size={16} style={{ color: 'var(--bear)' }} />
          <div className="text-center">
            <p className="text-xs font-semibold mb-0.5" style={{ color: 'var(--text-secondary)' }}>
              Component error
            </p>
            <p className="text-[10px]">{this.state.error.message}</p>
          </div>
          <button
            onClick={this.reset}
            className="flex items-center gap-1.5 px-2.5 py-1 rounded text-[10px] transition-opacity hover:opacity-80"
            style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border)', color: 'var(--text-secondary)' }}
          >
            <RefreshCw size={10} />
            Retry
          </button>
        </div>
      )
    }
    return this.props.children
  }
}

export default ErrorBoundary
