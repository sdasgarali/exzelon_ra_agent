'use client'

import { useEffect, useState, useCallback } from 'react'
import { useRouter } from 'next/navigation'

interface Shortcut {
  key: string
  ctrl?: boolean
  shift?: boolean
  description: string
  action: () => void
}

export function useKeyboardShortcuts() {
  const router = useRouter()
  const [helpOpen, setHelpOpen] = useState(false)

  const shortcuts: Shortcut[] = [
    { key: '?', shift: true, description: 'Show keyboard shortcuts', action: () => setHelpOpen(prev => !prev) },
    { key: 'Escape', description: 'Close dialog / help', action: () => setHelpOpen(false) },
    { key: 'd', ctrl: true, description: 'Go to Dashboard', action: () => router.push('/dashboard') },
    { key: 'l', ctrl: true, shift: true, description: 'Go to Leads', action: () => router.push('/dashboard/leads') },
    { key: 'o', ctrl: true, shift: true, description: 'Go to Outreach', action: () => router.push('/dashboard/outreach') },
    { key: 'p', ctrl: true, shift: true, description: 'Go to Pipelines', action: () => router.push('/dashboard/pipelines') },
  ]

  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    // Ignore when typing in inputs/textareas
    const target = e.target as HTMLElement
    if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable) {
      return
    }

    for (const shortcut of shortcuts) {
      const ctrlMatch = shortcut.ctrl ? (e.ctrlKey || e.metaKey) : !(e.ctrlKey || e.metaKey)
      const shiftMatch = shortcut.shift ? e.shiftKey : !e.shiftKey
      if (e.key === shortcut.key && ctrlMatch && shiftMatch) {
        e.preventDefault()
        shortcut.action()
        return
      }
    }
  }, [router])

  useEffect(() => {
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [handleKeyDown])

  return { helpOpen, setHelpOpen, shortcuts }
}
