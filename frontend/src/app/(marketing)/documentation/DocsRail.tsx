'use client'

import { useEffect, useState } from 'react'
import { ChevronDown } from 'lucide-react'
import type { DocSection } from './sections'
import styles from './handbook.module.css'

interface DocsRailProps {
  sections: DocSection[]
}

/**
 * Sticky contents rail for the handbook. Tracks which section is on screen and
 * collapses into a toggle on narrow viewports. Content itself stays server
 * rendered — only the navigation needs to be interactive.
 */
export default function DocsRail({ sections }: DocsRailProps) {
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
    <nav className={`${styles.rail} ${open ? styles.railOpen : ''}`} aria-label="Handbook contents">
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
        {sections.map((s) => (
          <li key={s.id}>
            <a
              href={`#${s.id}`}
              className={`${styles.railLink} ${activeId === s.id ? styles.railLinkActive : ''}`}
              aria-current={activeId === s.id ? 'true' : undefined}
              onClick={() => setOpen(false)}
            >
              <span className={styles.railNum}>{s.num}</span>
              <span>{s.title}</span>
            </a>
          </li>
        ))}
      </ol>

      <p className={styles.railFoot}>
        Nothing on this page exposes credentials, infrastructure or internal system addresses.
      </p>
    </nav>
  )
}
