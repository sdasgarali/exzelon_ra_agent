import type { Metadata } from 'next'

// The page itself is a client component, so its metadata lives here.
export const metadata: Metadata = {
  title: 'Reset your password',
  alternates: { canonical: '/forgot-password' },
  robots: { index: false, follow: true },
}

export default function Layout({ children }: { children: React.ReactNode }) {
  return children
}
