'use client'

/**
 * Numeric, operator-based company-size filter used on the Leads and Clients
 * pages. Emits an operator (<, ≤, >, ≥, =, ≠, Between) + one or two employee-
 * count values, plus an "include unknown" toggle for companies with no known
 * size. See backend `effective_size_expr` / `size_operator_clause`.
 */

export interface SizeFilterValue {
  op: string          // '' (any) | eq | ne | lt | lte | gt | gte | between
  v1: string          // primary value (kept as string for controlled input)
  v2: string          // upper bound, only used when op === 'between'
  includeUnknown: boolean
}

export const EMPTY_SIZE_FILTER: SizeFilterValue = { op: '', v1: '', v2: '', includeUnknown: false }

const OPERATORS: { value: string; label: string }[] = [
  { value: '', label: 'Any size' },
  { value: 'eq', label: '= (equals)' },
  { value: 'ne', label: '≠ (not equal)' },
  { value: 'lt', label: '< (less than)' },
  { value: 'lte', label: '≤ (at most)' },
  { value: 'gt', label: '> (more than)' },
  { value: 'gte', label: '≥ (at least)' },
  { value: 'between', label: 'Between' },
]

/** True when the filter is complete enough to send to the API. */
export function sizeFilterActive(v: SizeFilterValue): boolean {
  if (!v.op || v.v1 === '') return false
  if (v.op === 'between' && v.v2 === '') return false
  return true
}

/** Build the query params for the API from a filter value. */
export function sizeFilterParams(v: SizeFilterValue): Record<string, string | number | boolean> {
  if (!sizeFilterActive(v)) return {}
  const params: Record<string, string | number | boolean> = {
    company_size_op: v.op,
    company_size_value: Number(v.v1),
  }
  if (v.op === 'between') params.company_size_value2 = Number(v.v2)
  if (v.includeUnknown) params.company_size_include_unknown = true
  return params
}

export interface SizeFilterProps {
  value: SizeFilterValue
  onChange: (v: SizeFilterValue) => void
  className?: string
}

export function SizeFilter({ value, onChange, className = '' }: SizeFilterProps) {
  const set = (patch: Partial<SizeFilterValue>) => onChange({ ...value, ...patch })

  return (
    <div className={`flex flex-wrap items-center gap-2 ${className}`}>
      <select
        aria-label="Company size operator"
        value={value.op}
        onChange={(e) => set({ op: e.target.value, v2: e.target.value === 'between' ? value.v2 : '' })}
        className="input w-full sm:w-40"
      >
        {OPERATORS.map((o) => (
          <option key={o.value || 'any'} value={o.value}>{o.label}</option>
        ))}
      </select>

      {value.op && (
        <input
          type="number"
          min={0}
          inputMode="numeric"
          aria-label={value.op === 'between' ? 'Minimum employees' : 'Employee count'}
          placeholder={value.op === 'between' ? 'min' : 'employees'}
          value={value.v1}
          onChange={(e) => set({ v1: e.target.value })}
          className="input w-full sm:w-24"
        />
      )}

      {value.op === 'between' && (
        <>
          <span className="text-sm text-gray-400">and</span>
          <input
            type="number"
            min={0}
            inputMode="numeric"
            aria-label="Maximum employees"
            placeholder="max"
            value={value.v2}
            onChange={(e) => set({ v2: e.target.value })}
            className="input w-full sm:w-24"
          />
        </>
      )}

      {value.op && (
        <label className="flex items-center gap-1.5 whitespace-nowrap text-xs text-gray-600">
          <input
            type="checkbox"
            checked={value.includeUnknown}
            onChange={(e) => set({ includeUnknown: e.target.checked })}
            className="h-4 w-4 rounded border-gray-300"
          />
          Incl. unknown
        </label>
      )}
    </div>
  )
}
