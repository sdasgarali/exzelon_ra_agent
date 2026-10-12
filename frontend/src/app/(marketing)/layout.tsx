import { Archivo } from 'next/font/google'
import Navbar from '@/components/marketing/Navbar'
import Footer from '@/components/marketing/Footer'
import { fetchSiteInfo, SITE_INFO_FALLBACK } from '@/lib/site-info'

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

export default async function MarketingLayout({ children }: { children: React.ReactNode }) {
  // Published support address for the footer; the fallback keeps it on screen if the API is down.
  const supportEmail = await fetchSiteInfo()
    .then((i) => i.support_email || SITE_INFO_FALLBACK.support_email)
    .catch(() => SITE_INFO_FALLBACK.support_email)
  return (
    <div className={`${archivo.variable} light-only font-archivo marketing-gradient-bg min-h-screen`}>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
      />
      <Navbar />
      <main>{children}</main>
      <Footer supportEmail={supportEmail} />
    </div>
  )
}
