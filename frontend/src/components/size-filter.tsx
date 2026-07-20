'use client'

/**
 * Numeric, operator-based range filter used on the Leads and Clients pages
 * (company size, salary). Emits an operator (<, ≤, >, ≥, =, ≠, Between) + one
 * or two values, plus an "include unknown" toggle. See the backend helpers
 * `size_operator_clause` / `salary_operator_clause`.
 */

export interface NumericFilterValue {
  op: string          // '' (any) | eq | ne | lt | lte | gt | gte | between
  v1: string          // primary value (kept as string for controlled input)
  v2: string          // upper bound, only used when op === 'between'
  includeUnknown: boolean
}
/** @deprecated alias kept for existing imports */
export type SizeFilterValue = NumericFilterValue

export const EMPTY_NUMERIC_FILTER: NumericFilterValue = { op: '', v1: '', v2: '', includeUnknown: false }
export const EMPTY_SIZE_FILTER = EMPTY_NUMERIC_FILTER

/** True when the filter is complete enough to send to the API. */
export function numericFilterActive(v: NumericFilterValue): boolean {
  if (!v.op || v.v1 === '') return false
  if (v.op === 'between' && v.v2 === '') return false
  return true
}
export const sizeFilterActive = numericFilterActive

/** Build query params for a given backend field prefix (e.g. 'company_size', 'salary'). */
export function numericFilterParams(prefix: string, v: NumericFilterValue): Record<string, string | number | boolean> {
  if (!numericFilterActive(v)) return {}
  const params: Record<string, string | number | boolean> = {
    [`${prefix}_op`]: v.op,
    [`${prefix}_value`]: Number(v.v1),
  }
  if (v.op === 'between') params[`${prefix}_value2`] = Number(v.v2)
  if (v.includeUnknown) params[`${prefix}_include_unknown`] = true
  return params
}
export const sizeFilterParams = (v: NumericFilterValue) => numericFilterParams('company_size', v)
export const salaryFilterParams = (v: NumericFilterValue) => numericFilterParams('salary', v)

export interface NumericFilterProps {
  value: NumericFilterValue
  onChange: (v: NumericFilterValue) => void
  className?: string
  /** aria label prefix, e.g. "Company size" or "Salary" */
  label?: string
  /** placeholder for the single-value input, e.g. "employees" or "amount" */
  placeholder?: string
  /** first dropdown option, e.g. "Any size" or "Any salary" */
  anyLabel?: string
}

export function NumericFilter({
  value, onChange, className = '',
  label = 'Value', placeholder = 'value', anyLabel = 'Any',
}: NumericFilterProps) {
  const set = (patch: Partial<NumericFilterValue>) => onChange({ ...value, ...patch })

  const operators: { value: string; label: string }[] = [
    { value: '', label: anyLabel },
    { value: 'eq', label: '= (equals)' },
    { value: 'ne', label: '≠ (not equal)' },
    { value: 'lt', label: '< (less than)' },
    { value: 'lte', label: '≤ (at most)' },
    { value: 'gt', label: '> (more than)' },
    { value: 'gte', label: '≥ (at least)' },
    { value: 'between', label: 'Between' },
  ]

  return (
    <div className={`flex flex-wrap items-center gap-2 ${className}`}>
      <select
        aria-label={`${label} operator`}
        value={value.op}
        onChange={(e) => set({ op: e.target.value, v2: e.target.value === 'between' ? value.v2 : '' })}
        className="input w-full sm:w-40"
      >
        {operators.map((o) => (
          <option key={o.value || 'any'} value={o.value}>{o.label}</option>
        ))}
      </select>

      {value.op && (
        <input
          type="number"
          min={0}
          inputMode="numeric"
          aria-label={value.op === 'between' ? `Minimum ${label}` : label}
          placeholder={value.op === 'between' ? 'min' : placeholder}
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
            aria-label={`Maximum ${label}`}
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

/** Company-size preset of {@link NumericFilter} (keeps existing call sites working). */
export function SizeFilter(props: Omit<NumericFilterProps, 'label' | 'placeholder' | 'anyLabel'>) {
  return <NumericFilter label="Company size" placeholder="employees" anyLabel="Any size" {...props} />
}
