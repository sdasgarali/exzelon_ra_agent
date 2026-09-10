'use client'

import { useEffect, useState } from 'react'
import { ChevronDown } from 'lucide-react'
import styles from './legal.module.css'
import type { LegalSection } from './types'

/**
 * Sticky contents rail for a legal document. Tracks the section on screen and
 * collapses into a toggle on narrow viewports. The document body itself stays
 * server rendered — only navigation needs to be interactive.
 */
export default function LegalRail({ sections }: { sections: LegalSection[] }) {
  const [activeId, setActiveId] = useState<string>(sections[0]?.id ?? '')
  const [open, setOpen] = useState(false)

  useEffect(() => {
    if (typeof IntersectionObserver === 'undefined') return

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) setActiveId(entry.target.id)
        })
      },
      { rootMargin: '-15% 0px -75% 0px', threshold: 0 }
    )

    const nodes = sections
      .map((s) => document.getElementById(s.id))
      .filter((n): n is HTMLElement => n !== null)

    nodes.forEach((n) => observer.observe(n))
    return () => observer.disconnect()
  }, [sections])

  return (
    <nav className={`${styles.rail} ${open ? styles.railOpen : ''}`} aria-label="Contents">
      <button
        type="button"
        className={styles.tocToggle}
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        Contents
        <ChevronDown
          className={`${styles.tocChevron} ${open ? styles.tocChevronOpen : ''}`}
          aria-hidden="true"
        />
      </button>

      <h2 className={styles.railHeading}>Contents</h2>

      <ol className={styles.railList}>
        {sections.map((s, i) => (
          <li key={s.id}>
            <a
              href={`#${s.id}`}
              className={`${styles.railLink} ${activeId === s.id ? styles.railLinkActive : ''}`}
              aria-current={activeId === s.id ? 'true' : undefined}
              onClick={() => setOpen(false)}
            >
              <span className={styles.railNum}>{String(i + 1).padStart(2, '0')}</span>
              <span>{s.title}</span>
            </a>
          </li>
        ))}
      </ol>
    </nav>
  )
}
