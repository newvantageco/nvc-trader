'use client'

import { useState, useTransition } from 'react'
import { signIn } from 'next-auth/react'
import { useRouter } from 'next/navigation'

export default function LoginPage() {
  const [email,    setEmail]    = useState('')
  const [password, setPassword] = useState('')
  const [error,    setError]    = useState('')
  const [pending,  startTransition] = useTransition()
  const router = useRouter()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    startTransition(async () => {
      const result = await signIn('credentials', {
        email,
        password,
        redirect: false,
      })
      if (result?.error) {
        setError('Invalid credentials')
      } else {
        router.push('/')
        router.refresh()
      }
    })
  }

  return (
    <div
      className="min-h-screen flex items-center justify-center"
      style={{ background: 'var(--bg-base)' }}
    >
      {/* Ambient glow */}
      <div
        className="fixed inset-0 pointer-events-none"
        style={{
          background: 'radial-gradient(ellipse 60% 40% at 50% 50%, rgba(245,158,11,0.04) 0%, transparent 70%)',
        }}
      />

      <div className="w-full max-w-sm relative">

        {/* Logo */}
        <div className="text-center mb-10">
          <div
            className="text-3xl font-mono font-bold tracking-[0.3em] mb-1"
            style={{ color: 'var(--accent)' }}
          >
            NVC
          </div>
          <div className="text-xs tracking-[0.25em] uppercase" style={{ color: 'var(--text-muted)' }}>
            Vantage Terminal
          </div>
          <div className="mt-1 text-xs" style={{ color: 'var(--text-muted)' }}>
            New Vantage Co · Autonomous Trading Intelligence
          </div>
        </div>

        {/* Card */}
        <div
          className="p-8 rounded border"
          style={{ background: 'var(--bg-surface)', borderColor: 'var(--border)' }}
        >
          <h1 className="text-sm font-semibold mb-6" style={{ color: 'var(--text-primary)' }}>
            Sign in to your terminal
          </h1>

          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            <div>
              <label className="block text-xs mb-1.5" style={{ color: 'var(--text-muted)' }}>
                Email address
              </label>
              <input
                type="email"
                value={email}
                onChange={e => setEmail(e.target.value)}
                required
                className="w-full px-3 py-2 rounded text-sm font-mono"
                style={{
                  background:   'var(--bg-elevated)',
                  border:       '1px solid var(--border)',
                  color:        'var(--text-primary)',
                  outline:      'none',
                }}
                onFocus={e => (e.target.style.borderColor = 'var(--accent)')}
                onBlur={e  => (e.target.style.borderColor = 'var(--border)')}
              />
            </div>

            <div>
              <label className="block text-xs mb-1.5" style={{ color: 'var(--text-muted)' }}>
                Password
              </label>
              <input
                type="password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                required
                placeholder="Enter your password"
                className="w-full px-3 py-2 rounded text-sm font-mono"
                style={{
                  background:   'var(--bg-elevated)',
                  border:       '1px solid var(--border)',
                  color:        'var(--text-primary)',
                  outline:      'none',
                }}
                onFocus={e => (e.target.style.borderColor = 'var(--accent)')}
                onBlur={e  => (e.target.style.borderColor = 'var(--border)')}
              />
            </div>

            {error && (
              <div
                className="text-xs px-3 py-2 rounded"
                style={{ background: 'rgba(239,68,68,0.1)', color: 'var(--bear)', border: '1px solid rgba(239,68,68,0.2)' }}
              >
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={pending}
              className="w-full py-2.5 rounded text-sm font-semibold mt-1 transition-opacity"
              style={{
                background: 'var(--accent)',
                color:      '#000',
                opacity:    pending ? 0.6 : 1,
                cursor:     pending ? 'not-allowed' : 'pointer',
              }}
            >
              {pending ? 'Signing in...' : 'Access Terminal'}
            </button>
          </form>
        </div>

        {/* Footer */}
        <div className="text-center mt-6 text-xs" style={{ color: 'var(--text-muted)' }}>
          Authorised access only · NVC Trading System v1.0
        </div>
      </div>
    </div>
  )
}
