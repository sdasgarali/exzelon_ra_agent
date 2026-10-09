// Generated palette references — see gen-mono-theme.js / globals.css.
const SHADES = ["50","100","200","300","400","500","600","700","800","900","950"]
const cssVarPalette = (name) =>
  Object.fromEntries(SHADES.map((s) => [s, `rgb(var(--c-${name}-${s}) / <alpha-value>)`]))

/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: 'class',
  content: [
    './src/pages/**/*.{js,ts,jsx,tsx,mdx}',
    './src/components/**/*.{js,ts,jsx,tsx,mdx}',
    './src/app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        // Minimal black & white theme: these palettes resolve through CSS variables
        // (globals.css). The app gets neutrals; the .light-only marketing surface
        // gets the original colors. Status palettes (red/green/amber/...) are untouched.
        gray: cssVarPalette('gray'),
        slate: cssVarPalette('slate'),
        zinc: cssVarPalette('zinc'),
        blue: cssVarPalette('blue'),
        indigo: cssVarPalette('indigo'),
        violet: cssVarPalette('violet'),
        purple: cssVarPalette('purple'),
        fuchsia: cssVarPalette('fuchsia'),
        pink: cssVarPalette('pink'),
        sky: cssVarPalette('sky'),
        cyan: cssVarPalette('cyan'),
        teal: cssVarPalette('teal'),
        primary: cssVarPalette('primary'),
        navy: cssVarPalette('navy'),

        // Brand palette, sampled from the NeuraLeads master lockup. Used by the
        // marketing surface. Four roles, each with a job:
        //   brand  = the flow / primary action   ink    = type
        //   signal = rejected at a gate          paper  = ground
        brand: {
          50: '#EFEFFE',
          100: '#DEDEFC',
          200: '#BFBFF8',
          400: '#7A7BEC',
          DEFAULT: '#4B4CE3',
          500: '#4B4CE3',
          600: '#3B3CCB',
          700: '#2E2FA3',
          900: '#1B1B63',
        },
        ink: {
          DEFAULT: '#0B172E',
          900: '#0B172E',
          800: '#16233D',
          700: '#2B3752',
          500: '#5A6580',
          300: '#969DB0',
        },
        signal: {
          DEFAULT: '#DA3510',
          500: '#DA3510',
          600: '#B62A0B',
          100: '#FCE6E0',
        },
        paper: {
          DEFAULT: '#FBFBFD',
          0: '#FFFFFF',
          100: '#F3F3F8',
          200: '#E7E8F0',
        },
      },
      fontFamily: {
        // Marketing surface only — applied via the (marketing) layout wrapper so
        // the app UI keeps Inter.
        archivo: ['var(--font-archivo)', 'ui-sans-serif', 'system-ui', 'sans-serif'],
      },
      keyframes: {
        slideIn: {
          from: { transform: 'translateX(calc(100% + 1rem))' },
          to: { transform: 'translateX(0)' },
        },
        fadeOut: {
          from: { opacity: '1' },
          to: { opacity: '0' },
        },
        marquee: {
          '0%': { transform: 'translateX(0%)' },
          '100%': { transform: 'translateX(-50%)' },
        },
        'glow-pulse': {
          '0%, 100%': { opacity: '0.4' },
          '50%': { opacity: '0.8' },
        },
      },
      animation: {
        slideIn: 'slideIn 200ms ease-out',
        fadeOut: 'fadeOut 200ms ease-in',
        marquee: 'marquee 30s linear infinite',
        'glow-pulse': 'glow-pulse 3s ease-in-out infinite',
      },
    },
  },
  plugins: [],
}
