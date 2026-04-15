/** @type {import('next').NextConfig} */
const nextConfig = {
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || 'https://nvc-trader.fly.dev',
    NEXT_PUBLIC_WS_URL:  process.env.NEXT_PUBLIC_WS_URL  || 'wss://nvc-trader.fly.dev/ws',
  },

  // ── HTTP security headers ──────────────────────────────────────────────────
  async headers() {
    const apiOrigin = process.env.NEXT_PUBLIC_API_URL || 'https://nvc-trader.fly.dev'
    const wsOrigin  = (process.env.NEXT_PUBLIC_WS_URL  || 'wss://nvc-trader.fly.dev/ws')
      .replace(/^wss?:/, 'wss:')

    return [
      {
        source: '/(.*)',
        headers: [
          // Prevent clickjacking
          { key: 'X-Frame-Options',           value: 'DENY' },
          // Prevent MIME-type sniffing
          { key: 'X-Content-Type-Options',    value: 'nosniff' },
          // Don't leak referer to cross-origin requests
          { key: 'Referrer-Policy',           value: 'strict-origin-when-cross-origin' },
          // Force HTTPS for 1 year (only meaningful in production)
          { key: 'Strict-Transport-Security', value: 'max-age=31536000; includeSubDomains' },
          // Restrict powerful browser features
          {
            key:   'Permissions-Policy',
            value: 'camera=(), microphone=(), geolocation=(), payment=()',
          },
          // Content-Security-Policy
          {
            key: 'Content-Security-Policy',
            value: [
              "default-src 'self'",
              // Next.js requires unsafe-eval in dev; tighten in a future pass if needed
              "script-src 'self' 'unsafe-eval' 'unsafe-inline'",
              "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
              "font-src 'self' https://fonts.gstatic.com",
              `connect-src 'self' ${apiOrigin} ${wsOrigin} https://*.supabase.co wss://*.supabase.co`,
              // YouTube thumbnails used in Research page
              "img-src 'self' data: https://i.ytimg.com https://img.youtube.com",
              "frame-src 'none'",
              "object-src 'none'",
              "base-uri 'self'",
            ].join('; '),
          },
        ],
      },
    ]
  },
}

export default nextConfig
