/* eslint-disable @next/next/no-img-element */
/**
 * NeuraLeads brand logo.
 *
 * Assets live in `public/brand/` and are the authoritative brand artwork
 * (transparent PNG, extracted from the master lockup):
 *   - logo-light.png  700x130  navy wordmark  -> sits on LIGHT backgrounds
 *   - logo-dark.png   700x130  white wordmark -> sits on DARK backgrounds
 *   - mark.png        256x256  indigo N mark  -> works on either
 *
 * Brand colors: indigo #4B4CE3, wordmark navy #0B172E.
 *
 * `on` describes the BACKGROUND the logo sits on, not the logo's own color.
 * `on="auto"` renders both variants and swaps them with Tailwind's `dark:`
 * class variant, so there is no hydration flash and no theme hook needed.
 *
 * Plain <img> (not next/image) is deliberate: production runs `next start` on
 * a VPS where `sharp` is not guaranteed, and these are already right-sized.
 */

type BrandVariant = 'lockup' | 'mark'

interface BrandLogoProps {
  /** 'lockup' = mark + NeuraLeads wordmark. 'mark' = square N only. */
  variant?: BrandVariant
  /**
   * Background the logo sits on. 'auto' swaps on the `dark` class.
   *
   * 'brand' = a brand-indigo ground, which needs the all-white lockup: the
   * two-tone artwork's indigo "Leads" disappears against the brand color.
   */
  on?: 'light' | 'dark' | 'brand' | 'auto'
  /** Rendered height in px; width is derived from the asset ratio. */
  height?: number
  className?: string
}

const ASSETS = {
  lockup: {
    light: '/brand/logo-light.png',
    dark: '/brand/logo-dark.png',
    brand: '/brand/logo-mono-white.png',
    w: 700,
    h: 130,
  },
  mark: {
    light: '/brand/mark.png',
    dark: '/brand/mark.png',
    brand: '/brand/mark.png',
    w: 256,
    h: 256,
  },
} as const

export function BrandLogo({
  variant = 'lockup',
  on = 'auto',
  height = 32,
  className = '',
}: BrandLogoProps) {
  const asset = ASSETS[variant]
  const width = Math.round((height * asset.w) / asset.h)

  // The mark is a single indigo artwork that reads on both grounds — never swap it.
  if (variant === 'mark' || on !== 'auto') {
    return (
      <img
        src={on === 'brand' ? asset.brand : on === 'dark' ? asset.dark : asset.light}
        width={width}
        height={height}
        alt="NeuraLeads"
        draggable={false}
        className={className}
      />
    )
  }

  return (
    <>
      <img
        src={asset.light}
        width={width}
        height={height}
        alt="NeuraLeads"
        draggable={false}
        className={`${className} dark:hidden`.trim()}
      />
      <img
        src={asset.dark}
        width={width}
        height={height}
        alt="NeuraLeads"
        draggable={false}
        aria-hidden="true"
        className={`${className} hidden dark:block`.trim()}
      />
    </>
  )
}

export default BrandLogo
