import { affordableHint, parseMaxLeads, stopMessage } from '../lead-sourcing'

describe('parseMaxLeads', () => {
  it('treats blank as the workspace default', () => {
    expect(parseMaxLeads('', 5000)).toEqual({ value: null, error: null })
    expect(parseMaxLeads('   ', 5000)).toEqual({ value: null, error: null })
  })

  it('accepts whole numbers within the limit', () => {
    expect(parseMaxLeads('1', 5000)).toEqual({ value: 1, error: null })
    expect(parseMaxLeads(' 250 ', 5000)).toEqual({ value: 250, error: null })
    expect(parseMaxLeads('5000', 5000)).toEqual({ value: 5000, error: null })
  })

  it('rejects zero, decimals, text and values over the limit', () => {
    expect(parseMaxLeads('0', 5000).error).toBe('Enter at least 1.')
    expect(parseMaxLeads('2.5', 5000).error).toBe('Enter a whole number.')
    expect(parseMaxLeads('-3', 5000).error).toBe('Enter a whole number.')
    expect(parseMaxLeads('abc', 5000).error).toBe('Enter a whole number.')
    expect(parseMaxLeads('5001', 5000).error).toBe('At most 5,000 per run.')
  })
})

describe('affordableHint', () => {
  it('is hidden when credits are not enforced', () => {
    expect(affordableHint(null)).toBeNull()
    expect(affordableHint(undefined)).toBeNull()
  })

  it('says how many leads the balance covers', () => {
    expect(affordableHint(240)).toContain('about 240 leads')
    expect(affordableHint(1)).toContain('about 1 lead ')
  })

  it('warns when out of credits', () => {
    expect(affordableHint(0)).toBe('You are out of credits. Top up to run lead sourcing.')
  })
})

describe('stopMessage', () => {
  it('explains a credit stop', () => {
    expect(stopMessage({ records_success: 37, requested_max_leads: 100, stopped_reason: 'credits_exhausted' }))
      .toBe('Stopped: out of credits — 37 of 100 leads saved. Top up to continue.')
    expect(stopMessage({ records_success: 12, requested_max_leads: null, stopped_reason: 'credits_exhausted' }))
      .toBe('Stopped: out of credits — 12 leads saved. Top up to continue.')
  })

  it('explains a reached cap', () => {
    expect(stopMessage({ records_success: 25, requested_max_leads: 25, stopped_reason: 'max_leads_reached' }))
      .toBe('Reached your limit of 25 leads.')
  })

  it('is null for a run that finished normally', () => {
    expect(stopMessage({ records_success: 9, stopped_reason: null })).toBeNull()
    expect(stopMessage({})).toBeNull()
  })
})
