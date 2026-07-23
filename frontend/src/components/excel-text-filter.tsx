'use client'

import { useState, useEffect, useRef } from 'react'

// ── Text-filter operator model (mirrors the backend app/utils/text_filter.py) ──
export type TextOp = 'equals' | 'not_equals' | 'begins' | 'not_begins' | 'ends' | 'not_ends' | 'contains' | 'not_contains' | 'word'

export interface TextCondition {
  op: TextOp
  val: string
  op2?: TextOp | ''
  val2?: string
  conj?: 'and' | 'or'
}

const OP_LABELS: { op: TextOp; label: string }[] = [
  { op: 'equals', label: 'Equals…' },
  { op: 'not_equals', label: 'Does Not Equal…' },
  { op: 'begins', label: 'Begins With…' },
  { op: 'not_begins', label: 'Does Not Begin With…' },
  { op: 'ends', label: 'Ends With…' },
  { op: 'not_ends', label: 'Does Not End With…' },
  { op: 'contains', label: 'Contains…' },
  { op: 'not_contains', label: 'Does Not Contain…' },
  { op: 'word', label: 'Whole Word…' },
]
const OP_LABEL: Record<TextOp, string> = Object.fromEntries(OP_LABELS.map(o => [o.op, o.label.replace('…', '')])) as Record<TextOp, string>

/** True when a condition would actually filter (its first clause is complete). */
export function textConditionActive(c?: TextCondition | null): boolean {
  return !!(c && c.op && c.val && c.val.trim())
}

/** Serialize a condition to `<field>_op`, `<field>_val` (+ `_op2/_val2/_conj`) query params. */
export function textConditionParams(field: string, c?: TextCondition | null): Record<string, string> {
  if (!textConditionActive(c)) return {}
  const cond = c as TextCondition
  const p: Record<string, string> = { [`${field}_op`]: cond.op, [`${field}_val`]: cond.val.trim() }
  if (cond.op2 && cond.val2 && cond.val2.trim()) {
    p[`${field}_op2`] = cond.op2
    p[`${field}_val2`] = cond.val2.trim()
    p[`${field}_conj`] = cond.conj || 'and'
  }
  return p
}

type GroupedOptions = { category: string; items: string[] }[]

export interface ExcelTextFilterProps {
  label: string
  /** Distinct values for the checklist. Omit for unbounded fields (e.g. Company Name). */
  options?: string[] | GroupedOptions
  grouped?: boolean
  selected: string[]
  onChange: (vals: string[]) => void
  textCondition: TextCondition | null
  onTextConditionChange: (c: TextCondition | null) => void
  /** Called after any change (e.g. to reset pagination). */
  onAfterChange?: () => void
  className?: string
}

export function ExcelTextFilter({
  label, options, grouped, selected, onChange, textCondition, onTextConditionChange,
  onAfterChange, className = '',
}: ExcelTextFilterProps) {
  const [open, setOpen] = useState(false)
  const [searchText, setSearchText] = useState('')
  const [showOps, setShowOps] = useState(false)
  const [custom, setCustom] = useState(false)
  const [draft, setDraft] = useState<TextCondition>({ op: 'contains', val: '', op2: 'contains', val2: '', conj: 'and' })
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const onDoc = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false) }
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [])

  // Seed the editor from the active condition whenever the menu opens.
  useEffect(() => {
    if (open && textCondition) {
      setDraft({ op: textCondition.op, val: textCondition.val, op2: textCondition.op2 || 'contains', val2: textCondition.val2 || '', conj: textCondition.conj || 'and' })
      setCustom(!!(textCondition.op2 && textCondition.val2))
      setShowOps(true)
    }
  }, [open]) // eslint-disable-line react-hooks/exhaustive-deps

  const allItems: string[] = grouped
    ? (options as GroupedOptions | undefined)?.flatMap(g => g.items) ?? []
    : ((options as string[] | undefined) ?? [])
  const hasChecklist = !!options
  const bySearch = (items: string[]) => (searchText ? items.filter(i => i.toLowerCase().includes(searchText.toLowerCase())) : items)

  const active = selected.length > 0 || textConditionActive(textCondition)
  const summary = () => {
    const parts: string[] = []
    if (selected.length) parts.push(`${selected.length} selected`)
    if (textConditionActive(textCondition)) parts.push(`${OP_LABEL[textCondition!.op]} "${textCondition!.val}"`)
    return parts.length ? `${label}: ${parts.join(' + ')}` : `All ${label}`
  }

  const after = () => onAfterChange?.()
  const toggle = (val: string) => { onChange(selected.includes(val) ? selected.filter(v => v !== val) : [...selected, val]); after() }
  const toggleCategory = (items: string[]) => {
    const allSel = items.length > 0 && items.every(i => selected.includes(i))
    onChange(allSel ? selected.filter(v => !items.includes(v)) : Array.from(new Set([...selected, ...items])))
    after()
  }

  const applyOp = (op: TextOp) => {
    setDraft(d => ({ ...d, op }))
    setCustom(false)
  }
  const commit = () => {
    if (!draft.val.trim()) { onTextConditionChange(null); after(); return }
    const next: TextCondition = custom && draft.val2 && draft.val2.trim()
      ? { op: draft.op, val: draft.val, op2: draft.op2, val2: draft.val2, conj: draft.conj }
      : { op: draft.op, val: draft.val }
    onTextConditionChange(next)
    after()
    setOpen(false)
  }
  const clearText = () => { onTextConditionChange(null); setDraft({ op: 'contains', val: '', op2: 'contains', val2: '', conj: 'and' }); setCustom(false); after() }

  const opSelect = (value: TextOp | '', onSel: (v: TextOp) => void) => (
    <select value={value} onChange={(e) => onSel(e.target.value as TextOp)}
      className="text-xs border border-gray-200 dark:border-gray-600 rounded px-1.5 py-1 bg-white dark:bg-gray-700 text-gray-800 dark:text-gray-200">
      {OP_LABELS.map(o => <option key={o.op} value={o.op}>{o.label.replace('…', '')}</option>)}
    </select>
  )

  return (
    <div ref={ref} className={`relative ${className}`}>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        title={active ? summary() : undefined}
        className={`input w-full text-left flex items-center justify-between ${active ? 'border-blue-400 bg-blue-50 dark:bg-blue-900/30 dark:border-blue-600' : ''}`}
      >
        <span className="truncate text-sm">{active ? summary() : `All ${label}`}</span>
        <span className="text-gray-400 ml-1">{open ? '▲' : '▼'}</span>
      </button>

      {open && (
        <div className="absolute z-50 mt-1 w-full bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-600 rounded-lg shadow-lg max-h-[70vh] overflow-y-auto min-w-0 sm:min-w-[240px]">
          {/* ── Text Filters (Excel operator menu) ── */}
          <div className="border-b">
            <button type="button" onClick={() => setShowOps(s => !s)}
              className="w-full flex items-center justify-between px-3 py-2 text-xs font-semibold text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700">
              <span>Text Filters</span>
              <span className="text-gray-400">{showOps ? '▼' : '▶'}</span>
            </button>
            {showOps && (
              <div className="px-3 pb-2 space-y-1.5">
                {!custom ? (
                  <div className="flex flex-wrap gap-1">
                    {OP_LABELS.map(o => (
                      <button key={o.op} type="button" onClick={() => applyOp(o.op)}
                        className={`text-[11px] px-1.5 py-0.5 rounded border ${draft.op === o.op ? 'border-blue-400 bg-blue-50 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300' : 'border-gray-200 dark:border-gray-600 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700'}`}>
                        {o.label.replace('…', '')}
                      </button>
                    ))}
                    <button type="button" onClick={() => setCustom(true)}
                      className="text-[11px] px-1.5 py-0.5 rounded border border-gray-200 dark:border-gray-600 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700">
                      Custom Filter…
                    </button>
                  </div>
                ) : (
                  <div className="flex items-center gap-1">
                    <span className="text-[11px] text-gray-500">Where</span>
                    {opSelect(draft.op, (v) => setDraft(d => ({ ...d, op: v })))}
                  </div>
                )}

                {/* value input(s) */}
                {!custom ? (
                  <div className="flex gap-1">
                    <input autoFocus type="text" value={draft.val}
                      onChange={(e) => setDraft(d => ({ ...d, val: e.target.value }))}
                      onKeyDown={(e) => { if (e.key === 'Enter') commit() }}
                      placeholder={`${OP_LABEL[draft.op]}…`}
                      className="flex-1 text-xs border border-gray-200 dark:border-gray-600 rounded px-2 py-1 bg-white dark:bg-gray-700 text-gray-800 dark:text-gray-200" />
                    <button type="button" onClick={commit} className="text-xs px-2 py-1 rounded bg-blue-600 text-white hover:bg-blue-700">Apply</button>
                  </div>
                ) : (
                  <div className="space-y-1">
                    <input type="text" value={draft.val} onChange={(e) => setDraft(d => ({ ...d, val: e.target.value }))}
                      placeholder="value" className="w-full text-xs border border-gray-200 dark:border-gray-600 rounded px-2 py-1 bg-white dark:bg-gray-700 text-gray-800 dark:text-gray-200" />
                    <div className="flex items-center gap-3 text-[11px] text-gray-600 dark:text-gray-300">
                      <label className="flex items-center gap-1"><input type="radio" checked={draft.conj !== 'or'} onChange={() => setDraft(d => ({ ...d, conj: 'and' }))} />And</label>
                      <label className="flex items-center gap-1"><input type="radio" checked={draft.conj === 'or'} onChange={() => setDraft(d => ({ ...d, conj: 'or' }))} />Or</label>
                    </div>
                    <div className="flex items-center gap-1">
                      {opSelect(draft.op2 || 'contains', (v) => setDraft(d => ({ ...d, op2: v })))}
                    </div>
                    <input type="text" value={draft.val2} onChange={(e) => setDraft(d => ({ ...d, val2: e.target.value }))}
                      placeholder="value" className="w-full text-xs border border-gray-200 dark:border-gray-600 rounded px-2 py-1 bg-white dark:bg-gray-700 text-gray-800 dark:text-gray-200" />
                    <div className="flex gap-1">
                      <button type="button" onClick={commit} className="text-xs px-2 py-1 rounded bg-blue-600 text-white hover:bg-blue-700">Apply</button>
                      <button type="button" onClick={() => setCustom(false)} className="text-xs px-2 py-1 rounded border border-gray-200 dark:border-gray-600 text-gray-600 dark:text-gray-300">Back</button>
                    </div>
                  </div>
                )}
                {textConditionActive(textCondition) && (
                  <button type="button" onClick={clearText} className="text-[11px] text-gray-500 hover:underline">Clear text filter</button>
                )}
              </div>
            )}
          </div>

          {/* ── Checklist ── */}
          {hasChecklist && (
            <>
              <div className="flex gap-2 px-3 py-2 border-b bg-gray-50 dark:bg-gray-700 sticky top-0 z-10">
                <button type="button" onClick={() => { onChange([...allItems]); after() }} className="text-xs text-blue-600 hover:underline">Select All</button>
                <button type="button" onClick={() => { onChange([]); after() }} className="text-xs text-gray-500 hover:underline">Clear</button>
              </div>
              <div className="px-3 py-2 border-b bg-white dark:bg-gray-800">
                <input type="text" placeholder="Search…" value={searchText} onChange={(e) => setSearchText(e.target.value)}
                  className="w-full text-sm border border-gray-200 dark:border-gray-600 rounded px-2 py-1 focus:outline-none focus:border-blue-400 bg-white dark:bg-gray-700 text-gray-800 dark:text-gray-200" />
              </div>
              {grouped ? (
                (options as GroupedOptions).map(group => {
                  const filtered = bySearch(group.items)
                  if (filtered.length === 0) return null
                  const allCat = group.items.length > 0 && group.items.every(i => selected.includes(i))
                  const someCat = group.items.some(i => selected.includes(i))
                  return (
                    <div key={group.category}>
                      <label className="flex items-center gap-2 px-3 py-1.5 bg-gray-50 dark:bg-gray-700 border-b cursor-pointer">
                        <input type="checkbox" checked={allCat} ref={(el) => { if (el) el.indeterminate = someCat && !allCat }}
                          onChange={() => toggleCategory(group.items)} className="w-3.5 h-3.5 rounded border-gray-300 text-blue-600" />
                        <span className="text-xs font-semibold text-gray-600 dark:text-gray-300 uppercase">{group.category}</span>
                        <span className="text-xs text-gray-400 ml-auto">{group.items.filter(i => selected.includes(i)).length}/{group.items.length}</span>
                      </label>
                      {filtered.map(opt => (
                        <label key={opt} className="flex items-center gap-2 px-3 py-1.5 pl-7 hover:bg-gray-50 dark:hover:bg-gray-700 cursor-pointer text-sm">
                          <input type="checkbox" checked={selected.includes(opt)} onChange={() => toggle(opt)} className="w-3.5 h-3.5 rounded border-gray-300 text-blue-600" />
                          {opt}
                        </label>
                      ))}
                    </div>
                  )
                })
              ) : (
                bySearch(allItems).map(opt => (
                  <label key={opt} className="flex items-center gap-2 px-3 py-1.5 hover:bg-gray-50 dark:hover:bg-gray-700 cursor-pointer text-sm">
                    <input type="checkbox" checked={selected.includes(opt)} onChange={() => toggle(opt)} className="w-3.5 h-3.5 rounded border-gray-300 text-blue-600" />
                    {opt}
                  </label>
                ))
              )}
              {allItems.length === 0 && <div className="px-3 py-2 text-xs text-gray-400">No options available</div>}
              {allItems.length > 0 && bySearch(allItems).length === 0 && <div className="px-3 py-2 text-xs text-gray-400">No matches for &ldquo;{searchText}&rdquo;</div>}
            </>
          )}
        </div>
      )}
    </div>
  )
}
