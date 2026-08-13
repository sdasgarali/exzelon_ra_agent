import { roleLabel, roleBadgeColor, BUILTIN_ROLE_LABELS } from '../roles'

describe('roleLabel', () => {
  test('maps renamed built-ins to their display labels', () => {
    expect(roleLabel('bdm')).toBe('BDM')
    expect(roleLabel('recruiter')).toBe('Recruiter')
    expect(roleLabel('super_admin')).toBe('Super Admin')
    expect(roleLabel('admin')).toBe('Admin')
  })

  test('title-cases unknown custom keys', () => {
    expect(roleLabel('bdm_lead')).toBe('Bdm Lead')
    expect(roleLabel('senior_recruiter')).toBe('Senior Recruiter')
  })

  test('prefers an API-supplied label when provided', () => {
    expect(roleLabel('bdm_lead', [{ key: 'bdm_lead', label: 'BDM Lead' }])).toBe('BDM Lead')
  })

  test('returns empty string for nullish key', () => {
    expect(roleLabel(null)).toBe('')
    expect(roleLabel(undefined)).toBe('')
  })

  test('no legacy operator/viewer labels remain', () => {
    expect(BUILTIN_ROLE_LABELS).not.toHaveProperty('operator')
    expect(BUILTIN_ROLE_LABELS).not.toHaveProperty('viewer')
  })
})

describe('roleBadgeColor', () => {
  test('returns a class string for built-ins and a default for custom', () => {
    expect(roleBadgeColor('bdm')).toContain('blue')
    expect(roleBadgeColor('recruiter')).toContain('gray')
    expect(roleBadgeColor('some_custom_role')).toEqual(expect.any(String))
    expect(roleBadgeColor(null)).toEqual(expect.any(String))
  })
})
