import { textConditionParams, textConditionActive, TextCondition } from '../excel-text-filter'

describe('excel-text-filter helpers', () => {
  describe('textConditionActive', () => {
    it('is false for null / empty value', () => {
      expect(textConditionActive(null)).toBe(false)
      expect(textConditionActive({ op: 'contains', val: '' })).toBe(false)
      expect(textConditionActive({ op: 'contains', val: '   ' })).toBe(false)
    })
    it('is true for a complete first clause', () => {
      expect(textConditionActive({ op: 'contains', val: 'ins' })).toBe(true)
    })
  })

  describe('textConditionParams', () => {
    it('returns {} when inactive', () => {
      expect(textConditionParams('industry', null)).toEqual({})
      expect(textConditionParams('industry', { op: 'contains', val: '' })).toEqual({})
    })

    it('serializes a single condition and trims the value', () => {
      expect(textConditionParams('company', { op: 'begins', val: '  North ' })).toEqual({
        company_op: 'begins',
        company_val: 'North',
      })
    })

    it('serializes a custom (two-clause) condition with conjunction', () => {
      const c: TextCondition = { op: 'contains', val: 'manager', op2: 'ends', val2: 'Director', conj: 'or' }
      expect(textConditionParams('title', c)).toEqual({
        title_op: 'contains',
        title_val: 'manager',
        title_op2: 'ends',
        title_val2: 'Director',
        title_conj: 'or',
      })
    })

    it('drops an incomplete second clause and defaults conj to and', () => {
      const c: TextCondition = { op: 'equals', val: 'X', op2: 'contains', val2: '  ' }
      expect(textConditionParams('employment_type', c)).toEqual({
        employment_type_op: 'equals',
        employment_type_val: 'X',
      })
    })
  })
})
