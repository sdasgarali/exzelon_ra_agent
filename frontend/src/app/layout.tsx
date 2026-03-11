import type { Metadata } from 'next'
import { Inter } from 'next/font/google'
import './globals.css'
import { Providers } from './providers'

const inter = Inter({ subsets: ['latin'] })

export const metadata: Metadata = {
  metadataBase: new URL(process.env.NEXT_PUBLIC_SITE_URL || 'https://ra.partnerwithus.tech'),
  title: {
    default: 'NeuraMail — AI-Powered Sales Outreach Platform',
    template: '%s | NeuraMail',
  },
  description: 'AI-powered outreach automation with 10 lead sources, 7 contact providers, and 4 AI engines. Full pipeline from lead sourcing to closed deals at 70% less cost.',
  keywords: ['cold email software', 'email outreach platform', 'sales automation', 'B2B lead generation', 'self-hosted outreach', 'neuramail', 'AI cold email', 'outreach automation'],
  openGraph: {
    title: 'NeuraMail — AI-Powered Sales Outreach Platform',
    description: 'Full-pipeline outreach automation. 10 lead sources. 7 contact providers. 4 AI engines. 70% less cost than competitors.',
    type: 'website',
    siteName: 'NeuraMail',
  },
  twitter: {
    card: 'summary_large_image',
    title: 'NeuraMail — AI-Powered Sales Outreach Platform',
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
