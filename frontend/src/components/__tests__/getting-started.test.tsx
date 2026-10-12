import { render, screen, fireEvent } from '@testing-library/react'

const mockPush = jest.fn()
jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush, replace: jest.fn(), back: jest.fn(), prefetch: jest.fn() }),
}))

import { GettingStarted } from '../getting-started'

function status(done: Partial<Record<string, boolean>>) {
  const steps = {
    has_mailboxes: false, has_leads: false, has_contacts: false,
    has_valid_contacts: false, has_active_campaign: false, has_deals: false,
    ...done,
  }
  const completed = Object.values(steps).filter(Boolean).length
  return {
    is_dismissed: false,
    steps,
    completed_count: completed,
    total_steps: 6,
    completion_percentage: Math.round((completed / 6) * 100),
    should_show_onboarding: true,
  }
}

describe('GettingStarted deep links (U5)', () => {
  beforeEach(() => mockPush.mockReset())

  test('step 3 (enrich) goes to the Leads page, where Contact Enrich lives', () => {
    render(<GettingStarted status={status({ has_mailboxes: true, has_leads: true })} onDismiss={jest.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: /Enrich Contacts/ }))
    expect(mockPush).toHaveBeenCalledWith('/dashboard/leads')
  })

  test('step 4 (validate) goes to the Validation page', () => {
    render(
      <GettingStarted
        status={status({ has_mailboxes: true, has_leads: true, has_contacts: true })}
        onDismiss={jest.fn()}
      />,
    )
    fireEvent.click(screen.getByRole('button', { name: /Validate Emails/ }))
    expect(mockPush).toHaveBeenCalledWith('/dashboard/validation')
  })

  test('step 2 (source) still goes to Pipelines', () => {
    render(<GettingStarted status={status({ has_mailboxes: true })} onDismiss={jest.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: /Run Sourcing/ }))
    expect(mockPush).toHaveBeenCalledWith('/dashboard/pipelines')
  })
})
