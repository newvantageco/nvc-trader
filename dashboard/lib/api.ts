/**
 * lib/api.ts — Shared API fetch utility for NVC Trading dashboard
 *
 * Features:
 *  - 30s request timeout via AbortSignal.timeout
 *  - Retry with exponential backoff (3× for network errors and 5xx; never 4xx)
 *  - Stripe-style typed error codes matching FastAPI responses
 *  - Convenience wrappers: api.get/post/patch/delete
 *  - silentFetch — null on any error (fire-and-forget reads)
 *  - errorMessage — human-readable error for toast messages
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

export const API_ERROR_CODES = {
  NOT_FOUND:            'not_found',
  UNAUTHORIZED:         'unauthorized',
  VALIDATION_ERROR:     'validation_error',
  CIRCUIT_BREAKER:      'circuit_breaker_active',
  INSUFFICIENT_CREDITS: 'insufficient_credits',
  BROKER_ERROR:         'broker_error',
  RATE_LIMITED:         'rate_limited',
  SERVER_ERROR:         'server_error',
  NETWORK_ERROR:        'network_error',
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

// ── Retry config ─────────────────────────────────────────────────────────────

const RETRY_ATTEMPTS  = 3
const RETRY_BASE_MS   = 500   // 500ms → 1s → 2s
const REQUEST_TIMEOUT = 30_000 // 30s

function shouldRetry(err: unknown, attempt: number): boolean {
  if (attempt >= RETRY_ATTEMPTS) return false
  if (err instanceof APIError) {
    // Retry server errors and network errors; never retry client errors (4xx)
    return err.status === 0 || err.status >= 500
  }
  return false
}

function retryDelay(attempt: number): Promise<void> {
  return new Promise(resolve =>
    setTimeout(resolve, RETRY_BASE_MS * Math.pow(2, attempt))
  )
}

// ── Core fetch ───────────────────────────────────────────────────────────────

export async function apiFetch<T = unknown>(
  path:    string,
  init?:   RequestInit & { signal?: AbortSignal },
): Promise<T> {
  let lastErr: unknown

  for (let attempt = 0; attempt <= RETRY_ATTEMPTS; attempt++) {
    if (attempt > 0) await retryDelay(attempt - 1)

    // Build an AbortSignal that fires on timeout OR caller abort
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(new DOMException('Request timed out', 'TimeoutError')), REQUEST_TIMEOUT)
    // If caller passed a signal, mirror it into our controller
    init?.signal?.addEventListener('abort', () => controller.abort(init.signal!.reason), { once: true })
    const signal = controller.signal

    let response: Response
    try {
      response = await fetch(`${BASE}${path}`, {
        ...init,
        signal,
        headers: {
          'Content-Type': 'application/json',
          ...(init?.headers ?? {}),
        },
      })
    } catch (err) {
      clearTimeout(timer)
      const msg = err instanceof Error ? err.message : 'Network error'
      lastErr = new APIError(0, 'network_error', msg)
      if (!shouldRetry(lastErr, attempt)) throw lastErr
      continue
    } finally {
      clearTimeout(timer)
    }

    if (!response.ok) {
      const body = await response.json().catch(() => ({})) as Record<string, unknown>
      const code = parseErrorCode(response.status, body)
      const msg  = (body.detail ?? body.message ?? body.error ?? `HTTP ${response.status}`) as string
      lastErr = new APIError(response.status, code, msg)
      if (!shouldRetry(lastErr, attempt)) throw lastErr
      continue
    }

    return response.json() as Promise<T>
  }

  throw lastErr
}

// ── Convenience methods ──────────────────────────────────────────────────────

export const api = {
  get<T = unknown>(path: string, signal?: AbortSignal): Promise<T> {
    return apiFetch<T>(path, signal ? { signal } : undefined)
  },

  post<T = unknown>(path: string, body?: unknown): Promise<T> {
    return apiFetch<T>(path, {
      method: 'POST',
      body:   body !== undefined ? JSON.stringify(body) : undefined,
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
