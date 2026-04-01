import type { DriveStep } from 'driver.js'

export const dashboardTourSteps: DriveStep[] = [
  {
    element: '[data-tour="sidebar"]',
    popover: {
      title: 'Navigation Sidebar',
      description: 'This is your main navigation. All tools are organized by workflow stage — from lead sourcing to closing deals.',
      side: 'right',
      align: 'start',
    },
  },
  {
    element: '[data-tour="nav-mailboxes"]',
    popover: {
      title: 'Step 1: Mailboxes',
      description: 'Start here. Add your email accounts (Gmail, Outlook, SMTP) that will be used for sending outreach emails.',
      side: 'right',
      align: 'start',
    },
  },
  {
    element: '[data-tour="nav-leads"]',
    popover: {
      title: 'Step 2: Leads',
      description: 'View and manage job postings sourced from Indeed, LinkedIn, Glassdoor and more. These are your target companies.',
      side: 'right',
      align: 'start',
    },
  },
  {
    element: '[data-tour="nav-contacts"]',
    popover: {
      title: 'Step 3: Contacts',
      description: 'Decision-makers discovered from your leads. Each contact has an email, title, and priority level.',
      side: 'right',
      align: 'start',
    },
  },
  {
    element: '[data-tour="nav-validation"]',
    popover: {
      title: 'Step 4: Validation',
      description: 'Verify email addresses before sending. Valid emails mean fewer bounces and better deliverability.',
      side: 'right',
      align: 'start',
    },
  },
  {
    element: '[data-tour="nav-campaigns"]',
    popover: {
      title: 'Step 5: Campaigns',
      description: 'Create multi-step email sequences with A/B testing, smart scheduling, and automatic follow-ups.',
      side: 'right',
      align: 'start',
    },
  },
  {
    element: '[data-tour="nav-inbox"]',
    popover: {
      title: 'Unified Inbox',
      description: 'All replies land here. AI categorizes responses as interested, not interested, OOO, or referral.',
      side: 'right',
      align: 'start',
    },
  },
  {
    element: '[data-tour="nav-deals"]',
    popover: {
      title: 'Step 6: Deals',
      description: 'Track interested prospects through your sales pipeline — from first contact to closed deal.',
      side: 'right',
      align: 'start',
    },
  },
  {
    element: '[data-tour="quick-actions"]',
    popover: {
      title: 'Quick Actions',
      description: 'Run pipeline stages directly from the dashboard — source leads, enrich contacts, validate emails, and export for outreach.',
      side: 'bottom',
      align: 'center',
    },
  },
  {
    element: '[data-tour="help-button"]',
    popover: {
      title: 'Need Help?',
      description: 'Click this button anytime to replay this guided tour. Welcome aboard!',
      side: 'left',
      align: 'end',
    },
  },
]
