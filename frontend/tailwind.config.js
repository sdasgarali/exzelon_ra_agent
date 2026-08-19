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
        primary: {
          50: '#f0f9ff',
          100: '#e0f2fe',
          200: '#bae6fd',
          300: '#7dd3fc',
          400: '#38bdf8',
          500: '#0ea5e9',
          // Darkened 600/700 for WCAG AA: white-on-primary-600 and text-primary-600
          // on white now meet 4.5:1 (was #0284c7 ≈ 3.8:1). Scale shifted to keep
          // hover (700) darker than base (600).
          600: '#0369a1',
          700: '#075985',
          800: '#0c4a6e',
          900: '#082f45',
        },
        navy: {
          900: '#0a0e27',
          800: '#111631',
          700: '#1a1f3d',
          600: '#232952',
        },
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
