import { formatLedgerCredits, ledgerToCsv, type LedgerItem } from '../credit-ledger'

const item = (over: Partial<LedgerItem> = {}): LedgerItem => ({
  usage_id: 1,
  usage_type: 'lead_sourced',
  label: 'Lead sourced',
  category: 'data',
  credits_used: 12,
  description: null,
  reference_id: null,
  recorded_at: '2026-10-12T10:00:00',
  ...over,
})

describe('formatLedgerCredits', () => {
  test('charges are shown as a deduction, grants as an addition', () => {
    expect(formatLedgerCredits(12)).toBe('−12')
    expect(formatLedgerCredits(-1000)).toBe('+1,000')
    expect(formatLedgerCredits(0.5)).toBe('−0.5')
  })
})

describe('ledgerToCsv', () => {
  test('writes a header, signed credits and escapes commas and quotes', () => {
    const csv = ledgerToCsv([
      item({ description: 'Run 7, "nightly"', reference_id: '7' }),
      item({ usage_id: 2, usage_type: 'topup_purchase', label: 'Credits purchased', category: 'grant', credits_used: -1000 }),
    ])
    const lines = csv.split('\n')
    expect(lines[0]).toBe('date,action,category,credits,description,reference')
    expect(lines[1]).toBe('2026-10-12T10:00:00,Lead sourced,data,-12,"Run 7, ""nightly""",7')
    expect(lines[2]).toBe('2026-10-12T10:00:00,Credits purchased,grant,1000,,')
  })
})
