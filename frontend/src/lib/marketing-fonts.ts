import { IBM_Plex_Mono, Source_Serif_4 } from 'next/font/google'

// Supporting faces for long-form marketing surfaces (handbook, legal pages).
// Archivo comes from the (marketing) layout; these add the two other roles:
// a mono for labels, counters and data, and a serif for lead paragraphs.
//
// Declared once and shared so the same face is not fetched twice under two
// different CSS variable names. Self-hosted by next/font — the app CSP does not
// permit a remote font CDN.

export const plexMono = IBM_Plex_Mono({
  subsets: ['latin'],
  weight: ['400', '500'],
  display: 'swap',
  variable: '--font-plex-mono',
})

export const sourceSerif = Source_Serif_4({
  subsets: ['latin'],
  weight: ['400', '600'],
  display: 'swap',
  variable: '--font-source-serif',
})

/** Convenience: both font variables, ready to drop on a wrapper element. */
export const marketingFontVars = `${plexMono.variable} ${sourceSerif.variable}`
