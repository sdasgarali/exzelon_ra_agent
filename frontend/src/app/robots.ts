import type { MetadataRoute } from 'next'

const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL || 'https://neuraleads.ai'

// Served at /robots.txt. The app shell, the API and the one-time token pages are
// not useful search results; the marketing site and auth entry points are.
export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: '*',
      allow: '/',
      disallow: ['/dashboard', '/api/', '/verify', '/reset-password', '/forgot-password', '/t/', '/unsub/', '/mcp'],
    },
    sitemap: `${SITE_URL}/sitemap.xml`,
    host: SITE_URL,
  }
}
