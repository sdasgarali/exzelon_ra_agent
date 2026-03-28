import Link from 'next/link'
import Logo from './Logo'

const footerLinks = {
  Product: [
    { label: 'Features', href: '/features' },
    { label: 'Pricing', href: '/pricing' },
    { label: 'Compare', href: '/compare' },
    { label: 'Dashboard', href: '/dashboard' },
  ],
  'Use Cases': [
    { label: 'Sales Teams', href: '/features#campaigns' },
    { label: 'Lead Generation', href: '/features#lead-sourcing' },
    { label: 'Email Outreach', href: '/features#outreach' },
    { label: 'CRM Integration', href: '/features#crm' },
  ],
  Resources: [
    { label: 'API Documentation', href: '/dashboard' },
    { label: 'Help Center', href: '/features' },
    { label: 'Status', href: '/' },
  ],
  Company: [
    { label: 'About', href: '/' },
    { label: 'Contact', href: '/' },
    { label: 'Privacy Policy', href: '/' },
    { label: 'Terms of Service', href: '/' },
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
                    <Link
                      href={link.href}
                      className="text-slate-500 hover:text-slate-300 transition-colors text-sm"
                    >
                      {link.label}
                    </Link>
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
            <Link href="/" className="text-slate-600 hover:text-slate-400 transition-colors text-sm">
              Privacy
            </Link>
            <Link href="/" className="text-slate-600 hover:text-slate-400 transition-colors text-sm">
              Terms
            </Link>
          </div>
        </div>
      </div>
    </footer>
  )
}
