/** Credit ledger helpers shared by the credit history page and its tests. */

export interface LedgerItem {
  usage_id: number
  usage_type: string
  label: string
  category: string
  credits_used: number
  description: string | null
  reference_id: string | null
  recorded_at: string | null
}

const fmt = (n: number) =>
  Number.isInteger(n) ? n.toLocaleString() : n.toLocaleString(undefined, { maximumFractionDigits: 2 })

/** Charges are stored positive and grants negative; show grants as +N. */
export function formatLedgerCredits(credits: number): string {
  return credits < 0 ? `+${fmt(-credits)}` : `−${fmt(credits)}`
}

function csvEscape(v: unknown): string {
  const s = v == null ? '' : String(v)
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
}

export function ledgerToCsv(items: LedgerItem[]): string {
  const header = ['date', 'action', 'category', 'credits', 'description', 'reference']
  const rows = items.map((i) => [
    i.recorded_at ?? '', i.label, i.category, -i.credits_used, i.description ?? '', i.reference_id ?? '',
  ].map(csvEscape).join(','))
  return [header.join(','), ...rows].join('\n')
}

