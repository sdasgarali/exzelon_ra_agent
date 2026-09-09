/**
 * NeuraLeads marketing logo.
 *
 * Thin wrapper over the shared <BrandLogo> so the marketing surfaces keep their
 * existing `size` / `variant` API. Marketing chrome (navbar, footer) always sits
 * on the dark navy ground, so the white-wordmark variant is used.
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
      on="dark"
      height={size}
      className={className}
    />
  )
}
