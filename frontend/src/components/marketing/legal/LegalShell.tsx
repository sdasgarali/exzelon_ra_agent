import type { ReactNode } from 'react'
import { marketingFontVars } from '@/lib/marketing-fonts'
import LegalRail from './LegalRail'
import styles from './legal.module.css'
import type { LegalSection } from './types'

interface LegalShellProps {
  eyebrow: string
  title: string
  standfirst: string
  effective: string
  updated: string
  sections: LegalSection[]
  children: ReactNode
  closing?: ReactNode
}

/** Page frame shared by /privacy and /terms so both stay visually identical. */
export default function LegalShell({
  eyebrow,
  title,
  standfirst,
  effective,
  updated,
  sections,
  children,
  closing,
}: LegalShellProps) {
  return (
    <div className={`${styles.legal} ${marketingFontVars}`}>
      <header className={styles.masthead}>
        <div className={styles.mastheadInner}>
          <span className={styles.eyebrow}>{eyebrow}</span>
          <h1 className={styles.title}>{title}</h1>
          <p className={styles.standfirst}>{standfirst}</p>
          <div className={styles.dates}>
            <span className={styles.dateChip}>Effective {effective}</span>
            <span className={styles.dateChip}>Updated {updated}</span>
          </div>
        </div>
      </header>

      <div className={styles.shell}>
        <LegalRail sections={sections} />
        <main className={styles.doc}>{children}</main>
      </div>

      {closing ? <div className={styles.closing}>{closing}</div> : null}
    </div>
  )
}

/** One numbered section of a legal document. */
export function LegalSectionBlock({
  id,
  num,
  title,
  children,
}: {
  id: string
  num: number
  title: string
  children: ReactNode
}) {
  return (
    <section id={id} className={styles.section}>
      <div className={styles.secHead}>
        <span className={styles.secNum}>{String(num).padStart(2, '0')}</span>
        <h2 className={styles.secTitle}>{title}</h2>
      </div>
      {children}
    </section>
  )
}

/**
 * A fact that must be supplied by the operator rather than guessed. Rendered
 * conspicuously on purpose: an invented privacy address would route real
 * data-subject requests nowhere.
 */
export function Pending({ children }: { children: ReactNode }) {
  return (
    <span className={styles.pending} title="To be supplied before this document is relied upon">
      {children}
    </span>
  )
}

export function Note({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className={styles.note}>
      <span className={styles.noteLabel}>{label}</span>
      {children}
    </div>
  )
}

export function TableWrap({ children }: { children: ReactNode }) {
  return <div className={styles.tableWrap}>{children}</div>
}
