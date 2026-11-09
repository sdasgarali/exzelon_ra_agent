import {
  defaultLeadsLabel, fetchHint, jobsFieldLabel, nextDefaultMaxLeads, parseMaxLeads, stopMessage,
} from '../lead-sourcing'

describe('jobsFieldLabel', () => {
  it('shows the range', () => {
    expect(jobsFieldLabel(10, 5000)).toBe('How many jobs? (min 10 · max 5,000)')
  })
})

describe('parseMaxLeads', () => {
  it('accepts whole numbers in range', () => {
    expect(parseMaxLeads('10', 10, 5000)).toEqual({ value: 10, error: null })
    expect(parseMaxLeads(' 250 ', 10, 5000)).toEqual({ value: 250, error: null })
    expect(parseMaxLeads('5000', 10, 5000)).toEqual({ value: 5000, error: null })
  })

  it('requires a number', () => {
    expect(parseMaxLeads('', 10, 5000).error).toBe('Enter a number from 10 to 5,000.')
    expect(parseMaxLeads('   ', 10, 5000).value).toBeNull()
  })

  it('rejects anything outside the range or not whole', () => {
    for (const bad of ['9', '0', '5001', '2.5', '-3', 'abc']) {
      expect(parseMaxLeads(bad, 10, 5000)).toEqual({ value: null, error: 'Enter a number from 10 to 5,000.' })
    }
  })
})

describe('fetchHint', () => {
  it('explains the charge when credits are not enforced', () => {
    expect(fetchHint(null)).toContain('You pay 1 credit only for each new lead saved')
  })

  it('adds how many leads the balance covers', () => {
    expect(fetchHint(240)).toContain('Your credits cover 240 new leads.')
    expect(fetchHint(1)).toContain('Your credits cover 1 new lead.')
  })

  it('warns when out of credits', () => {
    expect(fetchHint(0)).toBe('You are out of credits. Top up to run lead sourcing.')
  })
})

describe('defaultLeadsLabel', () => {
  it('shows the saved default', () => {
    expect(defaultLeadsLabel(50)).toBe('Default: 50 jobs per run')
    expect(defaultLeadsLabel(1200)).toBe('Default: 1,200 jobs per run')
  })

  it('says when there is none', () => {
    expect(defaultLeadsLabel(null)).toBe('No default set')
    expect(defaultLeadsLabel(0)).toBe('No default set')
  })
})

describe('nextDefaultMaxLeads', () => {
  it('saves the number when ticked', () => {
    expect(nextDefaultMaxLeads(true, 40, null)).toBe(40)
    expect(nextDefaultMaxLeads(true, 40, 25)).toBe(40)
  })

  it('clears the default when unticked', () => {
    expect(nextDefaultMaxLeads(false, 40, 25)).toBeNull()
  })

  it('skips the write when nothing changes', () => {
    expect(nextDefaultMaxLeads(true, 25, 25)).toBeUndefined()
    expect(nextDefaultMaxLeads(false, 40, null)).toBeUndefined()
  })
})

describe('stopMessage', () => {
  it('explains a run that used its fetch budget', () => {
    expect(stopMessage({ records_success: 4, jobs_fetched: 10, stopped_reason: 'fetch_limit_reached' }))
      .toBe('Fetched 10 jobs → 4 new leads (4 credits). 6 were duplicates or filtered out — not charged.')
    expect(stopMessage({ records_success: 9, jobs_fetched: 10, stopped_reason: 'fetch_limit_reached' }))
      .toBe('Fetched 10 jobs → 9 new leads (9 credits). 1 was a duplicate or filtered out — not charged.')
  })

  it('explains a run that saved everything asked for', () => {
    expect(stopMessage({ records_success: 10, requested_max_leads: 10, stopped_reason: 'max_leads_reached' }))
      .toBe('Saved 10 new leads — the 10 you asked for (10 credits).')
  })

  it('explains a credit stop', () => {
    expect(stopMessage({ records_success: 1, stopped_reason: 'credits_exhausted' }))
      .toBe('Stopped: out of credits — 1 new lead saved (1 credit). Top up to continue.')
  })

  it('is null for a run without a number', () => {
    expect(stopMessage({ records_success: 9, stopped_reason: null })).toBeNull()
    expect(stopMessage({})).toBeNull()
  })
})
