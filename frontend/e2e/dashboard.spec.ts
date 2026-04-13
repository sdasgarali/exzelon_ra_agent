import { test, expect } from '@playwright/test'
import { loginAsSuperAdmin, loginAsAdmin } from './helpers/auth'
import { takeScreenshot } from './helpers/screenshots'

test.describe.serial('Dashboard — Super Admin View', () => {
  test('1. SA: Dashboard stats cards render with numeric values', async ({ page }) => {
    await loginAsSuperAdmin(page)

    // Wait for the KPI cards grid to appear
    const statsGrid = page.locator('.grid.grid-cols-1.md\\:grid-cols-2.lg\\:grid-cols-4').first()
    await expect(statsGrid).toBeVisible({ timeout: 30000 })

    // Each StatCard uses glass-card class with a text-2xl font-bold value
    const statValues = statsGrid.locator('.glass-card .text-2xl.font-bold')
    const count = await statValues.count()
    expect(count).toBeGreaterThanOrEqual(4)

    // Verify each card has a numeric (or zero) value
    for (let i = 0; i < Math.min(count, 4); i++) {
      const text = await statValues.nth(i).textContent()
      expect(text).toBeTruthy()
      // Value should be a number (possibly with commas for thousands)
      expect(text!.trim()).toMatch(/^[\d,]+$/)
    }

    // Verify the expected card titles are present
    await expect(statsGrid.getByText('Companies Identified')).toBeVisible()
    await expect(statsGrid.getByText('Total Contacts')).toBeVisible()
    await expect(statsGrid.getByText('Valid Emails')).toBeVisible()
    await expect(statsGrid.getByText('Emails Sent')).toBeVisible()

    await takeScreenshot(page, 'dashboard_stats_sa')
  })

  test('2. SA: Navigation sidebar has all expected links', async ({ page }) => {
    await loginAsSuperAdmin(page)

    const sidebar = page.locator('nav[aria-label="Main navigation"]')
    await expect(sidebar).toBeVisible()

    // Core navigation items that SA should see
    const expectedItems = [
      'Dashboard',
      'Mailboxes',
      'Warmup Engine',
      'Pipelines',
      'Leads',
      'Clients',
      'Contacts',
      'Validation',
      'ICP Wizard',
      'Email Templates',
      'Campaigns',
      'Outreach',
      'Email Preview',
      'Inbox',
      'Deals',
      'Analytics',
      'Visitors',
      'Automation',
      'Activity Log',
      'User Management',
      'Roles & Permissions',
      'Tenant Management',
      'Billing',
      'Data Backups',
      'Settings',
    ]

    for (const itemName of expectedItems) {
      await expect(
        sidebar.getByText(itemName, { exact: true }),
        `Expected nav item "${itemName}" to be visible for Super Admin`
      ).toBeVisible()
    }

    await takeScreenshot(page, 'dashboard_nav_sa_all_links')
  })
})

test.describe.serial('Dashboard — Admin View', () => {
  test('3. Admin: Dashboard stats cards render with numeric values', async ({ page }) => {
    await loginAsAdmin(page)

    // Wait for the KPI cards grid to appear
    const statsGrid = page.locator('.grid.grid-cols-1.md\\:grid-cols-2.lg\\:grid-cols-4').first()
    await expect(statsGrid).toBeVisible({ timeout: 30000 })

    // Each StatCard uses glass-card class with a text-2xl font-bold value
    const statValues = statsGrid.locator('.glass-card .text-2xl.font-bold')
    const count = await statValues.count()
    expect(count).toBeGreaterThanOrEqual(4)

    // Verify each card has a numeric value
    for (let i = 0; i < Math.min(count, 4); i++) {
      const text = await statValues.nth(i).textContent()
      expect(text).toBeTruthy()
      expect(text!.trim()).toMatch(/^[\d,]+$/)
    }

    await takeScreenshot(page, 'dashboard_stats_admin')
  })

  test('4. Admin: SA-only nav items are hidden', async ({ page }) => {
    await loginAsAdmin(page)

    const sidebar = page.locator('nav[aria-label="Main navigation"]')
    await expect(sidebar).toBeVisible()

    // These SA-only items must NOT be visible for admin
    await expect(
      sidebar.getByText('Activity Log', { exact: true }),
      'Activity Log should be hidden for Admin'
    ).not.toBeVisible()

    await expect(
      sidebar.getByText('Roles & Permissions', { exact: true }),
      'Roles & Permissions should be hidden for Admin'
    ).not.toBeVisible()

    await expect(
      sidebar.getByText('Tenant Management', { exact: true }),
      'Tenant Management should be hidden for Admin'
    ).not.toBeVisible()

    // Verify admin DOES see common items (sanity check)
    await expect(sidebar.getByText('Dashboard', { exact: true })).toBeVisible()
    await expect(sidebar.getByText('Leads', { exact: true })).toBeVisible()
    await expect(sidebar.getByText('Campaigns', { exact: true })).toBeVisible()
    await expect(sidebar.getByText('Contacts', { exact: true })).toBeVisible()
    await expect(sidebar.getByText('Settings', { exact: true })).toBeVisible()

    await takeScreenshot(page, 'dashboard_nav_admin_restricted')
  })
})
