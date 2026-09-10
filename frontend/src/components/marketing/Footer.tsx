import Link from 'next/link'
import Logo from './Logo'

const footerLinks = {
  Product: [
    { label: 'Features', href: '/features' },
    { label: 'Pricing', href: '/pricing' },
    { label: 'Compare', href: '/compare' },
    { label: 'Documentation', href: '/documentation' },
    { label: 'Dashboard', href: '/dashboard' },
  ],
  'Use Cases': [
    { label: 'Lead Generation', href: '/features#lead-sourcing' },
    { label: 'Email Outreach', href: '/features#campaigns' },
    { label: 'Deliverability', href: '/features#warmup' },
    { label: 'CRM Integration', href: '/features#crm' },
  ],
  Resources: [
    { label: 'Documentation', href: '/documentation' },
    { label: 'API Reference', href: '/api/docs', external: true },
    { label: 'Service Status', href: '/status' },
  ],
  Company: [
    { label: 'About', href: '/about' },
    { label: 'Contact', href: '/contact' },
    { label: 'Privacy Policy', href: '/privacy' },
    { label: 'Terms of Service', href: '/terms' },
  ],
}

export default function Footer() {
  return (
    <footer className="border-t border-white/5 bg-navy-900">
      <div className="max-w-7xl mx-auto px-6 py-16">
        <div className="grid grid-cols-2 md:grid-cols-5 gap-8">
          {/* Brand */}
          <div className="col-span-2 md:col-span-1">
            <Link href="/" className="mb-4 inline-block">
              <Logo size={30} />
            </Link>
            <p className="text-slate-500 text-sm leading-relaxed">
              AI-powered outreach automation. From lead sourcing to closed deals.
            </p>
          </div>

          {/* Link columns */}
          {Object.entries(footerLinks).map(([category, links]) => (
            <div key={category}>
              <h3 className="text-white font-semibold text-sm mb-4">{category}</h3>
              <ul className="space-y-2.5">
                {links.map((link) => (
                  <li key={link.label}>
                    {'external' in link && link.external ? (
                      // Served by the API, not the Next router — a <Link> would
                      // try to client-navigate and 404.
                      <a
                        href={link.href}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-slate-500 hover:text-slate-300 transition-colors text-sm"
                      >
                        {link.label}
                      </a>
                    ) : (
                      <Link
                        href={link.href}
                        className="text-slate-500 hover:text-slate-300 transition-colors text-sm"
                      >
                        {link.label}
                      </Link>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        {/* Bottom bar */}
        <div className="mt-16 pt-8 border-t border-white/5 flex flex-col md:flex-row items-center justify-between gap-4">
          <p className="text-slate-600 text-sm">
            &copy; {new Date().getFullYear()} NeuraLeads. All rights reserved.
          </p>
          <div className="flex items-center gap-6">
            <Link href="/privacy" className="text-slate-600 hover:text-slate-400 transition-colors text-sm">
              Privacy
            </Link>
            <Link href="/terms" className="text-slate-600 hover:text-slate-400 transition-colors text-sm">
              Terms
            </Link>
          </div>
        </div>
      </div>
    </footer>
  )
}
