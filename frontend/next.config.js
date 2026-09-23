/** @type {import('next').NextConfig} */

// Security headers applied to every rendered page. The HTML app shell previously
// had no Content-Security-Policy — only the API did (QA finding RA-QA-005).
// NOTE: 'unsafe-inline'/'unsafe-eval' are still required by the current Next.js
// build; tightening script-src to a nonce-based policy is a follow-up.

// In production the web app and the API are one origin behind nginx, so
// "connect-src 'self' https:" covers every XHR. Locally they are two origins over
// plain http (:3000 -> :8000), which that policy blocks. Widen connect-src to the
// dev API origin only when NODE_ENV is not production — the shipped policy is
// byte-for-byte unchanged.
const isDev = process.env.NODE_ENV !== 'production'
const devConnectSrc = isDev
  ? ' http://localhost:8000 http://127.0.0.1:8000 ws://localhost:3000 ws://127.0.0.1:3000'
  : ''

const securityHeaders = [
  { key: 'X-Frame-Options', value: 'SAMEORIGIN' },
  { key: 'X-Content-Type-Options', value: 'nosniff' },
  { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
  { key: 'Strict-Transport-Security', value: 'max-age=31536000; includeSubDomains' },
  { key: 'Permissions-Policy', value: 'camera=(), microphone=(), geolocation=()' },
  {
    key: 'Content-Security-Policy',
    value: [
      "default-src 'self'",
      "script-src 'self' 'unsafe-inline' 'unsafe-eval'",
      "style-src 'self' 'unsafe-inline'",
      "img-src 'self' data: https:",
      "font-src 'self' data:",
      `connect-src 'self' https:${devConnectSrc}`,
      "frame-ancestors 'self'",
      "base-uri 'self'",
      "form-action 'self'",
    ].join('; '),
  },
]

const nextConfig = {
  reactStrictMode: true,
  output: 'standalone',
  async headers() {
    return [
      {
        source: '/:path*',
        headers: securityHeaders,
      },
    ]
  },
}

module.exports = nextConfig
