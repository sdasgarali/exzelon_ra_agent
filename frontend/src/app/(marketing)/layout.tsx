import { Archivo } from 'next/font/google'
import Navbar from '@/components/marketing/Navbar'
import Footer from '@/components/marketing/Footer'

// Archivo — a grotesque with real weight range, closer to the geometry of the
// NeuraLeads wordmark than Inter is. Scoped to the marketing surface via the
// `font-archivo` class so the app UI keeps Inter.
const archivo = Archivo({
  subsets: ['latin'],
  display: 'swap',
  variable: '--font-archivo',
})

const jsonLd = {
  '@context': 'https://schema.org',
  '@type': 'SoftwareApplication',
  name: 'NeuraLeads',
  applicationCategory: 'BusinessApplication',
  operatingSystem: 'Web',
  description: 'AI-powered sales outreach automation platform with lead sourcing, email campaigns, CRM deals, and analytics.',
  offers: {
    '@type': 'AggregateOffer',
    lowPrice: '49',
    highPrice: '199',
    priceCurrency: 'USD',
    offerCount: 3,
  },
}

export default function MarketingLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className={`${archivo.variable} font-archivo marketing-gradient-bg min-h-screen`}>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
      />
      <Navbar />
      <main>{children}</main>
      <Footer />
    </div>
  )
}
