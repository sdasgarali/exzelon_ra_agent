/**
 * NeuraMail Logo
 *
 * Concept: An envelope shape whose flap is formed by 3 neural nodes
 * connected by synapse lines — merging "Neural" (AI/brain) with "Mail" (email).
 *
 * - Top node = brain/intelligence
 * - Envelope body = email/outreach
 * - Inner neural connections = AI working inside your email
 *
 * Works at all sizes from 20px favicon to 200px hero mark.
 */

interface LogoProps {
  size?: number
  className?: string
  variant?: 'icon' | 'full'
}

export default function Logo({ size = 32, className = '', variant = 'full' }: LogoProps) {
  const iconId = `neura-grad-${size}`

  const icon = (
    <svg
      width={size}
      height={size}
      viewBox="0 0 40 40"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={variant === 'icon' ? className : ''}
      aria-label="NeuraMail logo"
    >
      <defs>
        <linearGradient id={iconId} x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#38bdf8" />
          <stop offset="50%" stopColor="#818cf8" />
          <stop offset="100%" stopColor="#c084fc" />
        </linearGradient>
      </defs>

      {/* Gradient rounded square background */}
      <rect width="40" height="40" rx="10" fill={`url(#${iconId})`} />

      {/* Envelope body */}
      <rect x="7" y="15" width="26" height="17" rx="2.5" fill="none" stroke="white" strokeWidth="1.8" opacity="0.9" />

      {/* Neural flap — V-shape connecting 3 nodes */}
      <path d="M7.5 16.5 L20 9 L32.5 16.5" fill="none" stroke="white" strokeWidth="1.8" strokeLinejoin="round" strokeLinecap="round" />

      {/* Primary neural nodes (flap vertices) */}
      <circle cx="20" cy="9" r="2.8" fill="white" />
      <circle cx="8.5" cy="16" r="2" fill="white" opacity="0.85" />
      <circle cx="31.5" cy="16" r="2" fill="white" opacity="0.85" />

      {/* Inner neural network — subtle connections inside envelope */}
      <circle cx="15" cy="23" r="1.3" fill="white" opacity="0.35" />
      <circle cx="25" cy="21" r="1.3" fill="white" opacity="0.35" />
      <circle cx="20" cy="27" r="1.3" fill="white" opacity="0.35" />
      <line x1="15" y1="23" x2="25" y2="21" stroke="white" strokeWidth="0.8" opacity="0.25" />
      <line x1="15" y1="23" x2="20" y2="27" stroke="white" strokeWidth="0.8" opacity="0.25" />
      <line x1="25" y1="21" x2="20" y2="27" stroke="white" strokeWidth="0.8" opacity="0.25" />

      {/* Synapse lines from top node to inner network */}
      <line x1="20" y1="12" x2="15" y2="23" stroke="white" strokeWidth="0.6" opacity="0.15" />
      <line x1="20" y1="12" x2="25" y2="21" stroke="white" strokeWidth="0.6" opacity="0.15" />
    </svg>
  )

  if (variant === 'icon') return icon

  return (
    <div className={`flex items-center gap-2.5 ${className}`}>
      {icon}
      <span className="font-bold text-xl text-white tracking-tight">
        Neura<span className="text-primary-400">Mail</span>
      </span>
    </div>
  )
}
