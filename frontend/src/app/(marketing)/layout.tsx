import Navbar from '@/components/marketing/Navbar'
import Footer from '@/components/marketing/Footer'

const jsonLd = {
  '@context': 'https://schema.org',
  '@type': 'SoftwareApplication',
  name: 'NeuraMail',
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
    <div className="marketing-gradient-bg min-h-screen">
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
