/**
 * lib/api.ts — Shared API fetch utility for NVC Trading dashboard
 *
 * Replaces repetitive try/catch fetch blocks across all pages.
 * Adapted from SightSync lib/api/errors.ts + notifications.ts patterns.
 *
 * Usage:
 *   const data = await api.get<SignalList>('/signals?limit=20')
 *   const result = await api.post('/trigger', { trigger: 'manual' })
 */

const BASE = process.env.NEXT_PUBLIC_API_URL || 'https://nvc-trader.fly.dev'

// ── Error types ──────────────────────────────────────────────────────────────

export class APIError extends Error {
  constructor(
    public status:  number,
    public code:    string,
    message:        string,
  ) {
    super(message)
    this.name = 'APIError'
  }
}

// Stripe-style error codes — matches FastAPI error responses from the engine
export const API_ERROR_CODES = {
  NOT_FOUND:         'not_found',
  UNAUTHORIZED:      'unauthorized',
  VALIDATION_ERROR:  'validation_error',
  CIRCUIT_BREAKER:   'circuit_breaker_active',
  INSUFFICIENT_CREDITS: 'insufficient_credits',
  BROKER_ERROR:      'broker_error',
  RATE_LIMITED:      'rate_limited',
  SERVER_ERROR:      'server_error',
  NETWORK_ERROR:     'network_error',
} as const

export type APIErrorCode = typeof API_ERROR_CODES[keyof typeof API_ERROR_CODES]

function parseErrorCode(status: number, body: Record<string, unknown>): APIErrorCode {
  if (body.code) return body.code as APIErrorCode
  if (status === 401 || status === 403) return 'unauthorized'
  if (status === 404) return 'not_found'
  if (status === 422) return 'validation_error'
  if (status === 429) return 'rate_limited'
  if (status >= 500) return 'server_error'
  return 'server_error'
}

// ── Core fetch ───────────────────────────────────────────────────────────────

export async function apiFetch<T = unknown>(
  path:    string,
  init?:   RequestInit,
): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${BASE}${path}`, {
      ...init,
      headers: {
        'Content-Type': 'application/json',
        ...(init?.headers ?? {}),
      },
    })
  } catch (err) {
    throw new APIError(0, 'network_error', err instanceof Error ? err.message : 'Network error')
  }

  if (!response.ok) {
    const body = await response.json().catch(() => ({})) as Record<string, unknown>
    const code = parseErrorCode(response.status, body)
    const msg  = (body.detail ?? body.message ?? body.error ?? `HTTP ${response.status}`) as string
    throw new APIError(response.status, code, msg)
  }

  return response.json() as Promise<T>
}

// ── Convenience methods ──────────────────────────────────────────────────────

export const api = {
  get<T = unknown>(path: string): Promise<T> {
    return apiFetch<T>(path)
  },

  post<T = unknown>(path: string, body?: unknown): Promise<T> {
    return apiFetch<T>(path, {
      method:  'POST',
      body:    body !== undefined ? JSON.stringify(body) : undefined,
    })
  },

  patch<T = unknown>(path: string, body?: unknown): Promise<T> {
    return apiFetch<T>(path, {
      method: 'PATCH',
      body:   body !== undefined ? JSON.stringify(body) : undefined,
    })
  },

  delete<T = unknown>(path: string): Promise<T> {
    return apiFetch<T>(path, { method: 'DELETE' })
  },
}

// ── Human-readable error messages ───────────────────────────────────────────

export function errorMessage(err: unknown): string {
  if (err instanceof APIError) {
    if (err.code === 'circuit_breaker_active') return 'Trading halted — circuit breaker active'
    if (err.code === 'insufficient_credits')   return 'Anthropic API credits depleted — top up at console.anthropic.com'
    if (err.code === 'unauthorized')           return 'Not authorised — check API key'
    if (err.code === 'network_error')          return 'Cannot reach the engine — check backend connectivity'
    return err.message
  }
  if (err instanceof Error) return err.message
  return 'Unknown error'
}

// ── Silent fetch (returns null on error, no throw) ───────────────────────────

export async function silentFetch<T = unknown>(path: string): Promise<T | null> {
  try {
    return await api.get<T>(path)
  } catch {
    return null
  }
}
