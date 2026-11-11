import type { Metadata } from 'next'

// The page itself is a client component, so its metadata lives here.
export const metadata: Metadata = {
  title: 'Log in',
  alternates: { canonical: '/login' },
}

export default function Layout({ children }: { children: React.ReactNode }) {
  return children
}
