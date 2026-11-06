import { render, screen } from '@testing-library/react'
import React from 'react'

let mockPlan: any = null
let mockLoading = false
let mockUser: any = null

jest.mock('@/hooks/use-plan-features', () => ({
  usePlanFeatures: () => ({ plan: mockPlan, isLoading: mockLoading }),
}))
jest.mock('@/lib/store', () => ({
  useAuthStore: () => ({ user: mockUser }),
}))

import { UpgradeButton } from '../upgrade-button'

const free = { key: 'free', label: 'Free', upgrade_to: 'pro', upgrade_label: 'Pro' }
const max = { key: 'max', label: 'Max', upgrade_to: null, upgrade_label: null }

describe('UpgradeButton', () => {
  beforeEach(() => {
    mockLoading = false
    mockPlan = free
    mockUser = { role: 'admin' }
  })

  test('workspace admin on Free sees Upgrade, linking to the plan picker', () => {
    render(<UpgradeButton />)
    expect(screen.getByRole('link', { name: /Upgrade/ })).toHaveAttribute('href', '/dashboard/billing#plans')
  })

  test('custom role based on admin also sees it', () => {
    mockUser = { role: 'sales_lead', base_role: 'admin' }
    render(<UpgradeButton variant="sidebar" />)
    expect(screen.getByRole('link', { name: /Upgrade plan/ })).toBeInTheDocument()
  })

  test.each([
    ['super admin', { role: 'super_admin' }, free],
    ['recruiter', { role: 'recruiter' }, free],
    ['bdm', { role: 'bdm' }, free],
    ['admin on Max', { role: 'admin' }, max],
  ])('hidden for %s', (_label, user, plan) => {
    mockUser = user
    mockPlan = plan
    const { container } = render(<UpgradeButton />)
    expect(container).toBeEmptyDOMElement()
  })

  test('hidden while the plan is loading', () => {
    mockLoading = true
    const { container } = render(<UpgradeButton />)
    expect(container).toBeEmptyDOMElement()
  })

  test('collapsed sidebar keeps an accessible name', () => {
    render(<UpgradeButton variant="sidebar" collapsed />)
    expect(screen.getByRole('link', { name: 'Upgrade plan' })).toBeInTheDocument()
  })
})
