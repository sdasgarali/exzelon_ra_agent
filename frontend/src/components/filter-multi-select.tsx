'use client'

import { useState, useEffect, useRef } from 'react'

export interface FilterMultiSelectProps {
  label: string
  options: { id: string; label: string }[]
  selected: string[]
  onChange: (ids: string[]) => void
  className?: string
}

export function FilterMultiSelect({ label, options, selected, onChange, className = '' }: FilterMultiSelectProps) {
  const [open, setOpen] = useState(false)
  const [searchText, setSearchText] = useState('')
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  const filtered = searchText
    ? options.filter(o => o.label.toLowerCase().includes(searchText.toLowerCase()))
    : options

  const toggle = (id: string) => {
    onChange(selected.includes(id) ? selected.filter(v => v !== id) : [...selected, id])
  }

  return (
    <div ref={ref} className={`relative ${className}`}>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className={`w-full text-left flex items-center justify-between text-xs border rounded px-2 py-1.5 transition-colors ${
          selected.length > 0
            ? 'border-blue-400 bg-blue-50 dark:bg-blue-900/30 dark:border-blue-600 text-blue-700 dark:text-blue-300'
            : 'border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700'
        }`}
      >
        <span className="truncate">
          {selected.length === 0 ? `All ${label}` : `${label} (${selected.length})`}
        </span>
        <span className="text-gray-400 ml-1 text-[10px]">{open ? '\u25B2' : '\u25BC'}</span>
      </button>
      {open && (
        <div className="absolute z-50 mt-1 w-full bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-600 rounded-lg shadow-lg max-h-64 overflow-y-auto min-w-[200px]">
          <div className="flex gap-2 px-3 py-1.5 border-b bg-gray-50 dark:bg-gray-700 sticky top-0 z-10">
            <button type="button" onClick={() => onChange(options.map(o => o.id))} className="text-xs text-blue-600 hover:underline">Select All</button>
            <button type="button" onClick={() => onChange([])} className="text-xs text-gray-500 hover:underline">Clear</button>
          </div>
          <div className="px-3 py-1.5 border-b sticky top-[33px] bg-white dark:bg-gray-800 z-10">
            <input
              type="text"
              placeholder="Search..."
              value={searchText}
              onChange={(e) => setSearchText(e.target.value)}
              className="w-full text-xs border border-gray-200 dark:border-gray-600 rounded px-2 py-1 focus:outline-none focus:border-blue-400 bg-white dark:bg-gray-700 text-gray-800 dark:text-gray-200"
            />
          </div>
          {filtered.map(opt => (
            <label key={opt.id} className="flex items-center gap-2 px-3 py-1.5 hover:bg-gray-50 dark:hover:bg-gray-700 cursor-pointer text-xs">
              <input
                type="checkbox"
                checked={selected.includes(opt.id)}
                onChange={() => toggle(opt.id)}
                className="w-3.5 h-3.5 rounded border-gray-300 text-blue-600"
              />
              <span className="truncate">{opt.label}</span>
            </label>
          ))}
          {options.length === 0 && <div className="px-3 py-2 text-xs text-gray-400">No options available</div>}
          {options.length > 0 && filtered.length === 0 && <div className="px-3 py-2 text-xs text-gray-400">No matches for &ldquo;{searchText}&rdquo;</div>}
        </div>
      )}
    </div>
  )
}
