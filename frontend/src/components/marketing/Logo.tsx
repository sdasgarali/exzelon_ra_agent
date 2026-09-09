/**
 * NeuraLeads marketing logo.
 *
 * Thin wrapper over the shared <BrandLogo> so the marketing surfaces keep their
 * existing `size` / `variant` API.
 *
 * Uses the all-white lockup: marketing chrome sits on the navy ground on the
 * inner pages and on the brand-indigo hero drench on the homepage. The two-tone
 * artwork's indigo "Leads" vanishes against indigo, so mono-white is the only
 * variant safe across both.
 */
import BrandLogo from '@/components/brand-logo'

interface LogoProps {
  /** Rendered height in px. */
  size?: number
  className?: string
  variant?: 'icon' | 'full'
}

export default function Logo({ size = 32, className = '', variant = 'full' }: LogoProps) {
  return (
    <BrandLogo
      variant={variant === 'icon' ? 'mark' : 'lockup'}
      on="brand"
      height={size}
      className={className}
    />
  )
}
