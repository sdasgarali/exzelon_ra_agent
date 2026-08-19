import type { Metadata, Viewport } from 'next'
import { Inter } from 'next/font/google'
import './globals.css'
import { Providers } from './providers'

const inter = Inter({ subsets: ['latin'] })

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  // Do not cap zoom — capping fails WCAG 2.2 AA 1.4.4 (Resize Text). Allow up to 5x.
  maximumScale: 5,
  userScalable: true,
}

export const metadata: Metadata = {
  metadataBase: new URL(process.env.NEXT_PUBLIC_SITE_URL || 'https://ra.partnerwithus.tech'),
  title: {
    default: 'NeuraLeads — AI-Powered Sales Outreach Platform',
    template: '%s | NeuraLeads',
  },
  description: 'AI-powered outreach automation with 10 lead sources, 7 contact providers, and 4 AI engines. Full pipeline from lead sourcing to closed deals at 70% less cost.',
  keywords: ['cold email software', 'email outreach platform', 'sales automation', 'B2B lead generation', 'self-hosted outreach', 'neuraleads', 'AI cold email', 'outreach automation'],
  openGraph: {
    title: 'NeuraLeads — AI-Powered Sales Outreach Platform',
    description: 'Full-pipeline outreach automation. 10 lead sources. 7 contact providers. 4 AI engines. 70% less cost than competitors.',
    type: 'website',
    siteName: 'NeuraLeads',
  },
  twitter: {
    card: 'summary_large_image',
    title: 'NeuraLeads — AI-Powered Sales Outreach Platform',
    description: 'Full-pipeline outreach automation at 70% less cost than competitors.',
  },
  robots: {
    index: true,
    follow: true,
  },
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body className={inter.className}>
        <Providers>
          {children}
        </Providers>
      </body>
    </html>
  )
}
