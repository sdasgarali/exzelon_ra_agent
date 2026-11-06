import {
  clearPendingUpgrade, parseUpgradePlan, readPendingUpgrade, savePendingUpgrade,
  upgradeFromSearch, upgradeUrl,
} from '../pending-upgrade'
import { planHref } from '@/components/marketing/PricingCards'

describe('pending upgrade', () => {
  beforeEach(() => window.localStorage.clear())

  test('only pro and max are accepted', () => {
    expect(parseUpgradePlan('PRO')).toBe('pro')
    expect(parseUpgradePlan('max')).toBe('max')
    expect(parseUpgradePlan('free')).toBeNull()
    expect(parseUpgradePlan('custom')).toBeNull()
    expect(parseUpgradePlan(null)).toBeNull()
  })

  test('reads plan and billing from a query string', () => {
    expect(upgradeFromSearch('?plan=pro&billing=annual')).toEqual({ plan: 'pro', annual: true })
    expect(upgradeFromSearch('?plan=max')).toEqual({ plan: 'max', annual: false })
    expect(upgradeFromSearch('?billing=annual')).toBeNull()
  })

  test('save → read round-trips, clear removes it', () => {
    savePendingUpgrade('max', true)
    expect(readPendingUpgrade()).toMatchObject({ plan: 'max', annual: true })
    clearPendingUpgrade()
    expect(readPendingUpgrade()).toBeNull()
  })

  test('expires after 7 days', () => {
    savePendingUpgrade('pro', false)
    expect(readPendingUpgrade(Date.now() + 8 * 24 * 3600 * 1000)).toBeNull()
    expect(window.localStorage.getItem('nl_pending_upgrade')).toBeNull()
  })

  test('corrupt storage is ignored', () => {
    window.localStorage.setItem('nl_pending_upgrade', '{not json')
    expect(readPendingUpgrade()).toBeNull()
  })

  test('upgrade url points at the billing plan picker', () => {
    expect(upgradeUrl('pro', false)).toBe('/dashboard/billing?upgrade=pro&billing=monthly#plans')
  })
})

describe('pricing card links', () => {
  test('paid tiers carry the plan and billing period to signup', () => {
    expect(planHref('pro', '/signup', false)).toBe('/signup?plan=pro&billing=monthly')
    expect(planHref('max', '/signup', true)).toBe('/signup?plan=max&billing=annual')
  })

  test('free and custom links are unchanged', () => {
    expect(planHref('free', '/signup', true)).toBe('/signup')
    expect(planHref('custom', '/contact?topic=custom-plan', false)).toBe('/contact?topic=custom-plan')
  })
})
