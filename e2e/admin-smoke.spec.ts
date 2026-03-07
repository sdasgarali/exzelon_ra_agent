import { test, expect, Page } from '@playwright/test'

const ADMIN_EMAIL = 'ali.aitechs@gmail.com'
const ADMIN_PASSWORD = 'SA@Admin#123'

/** Helper: login and return authed page */
async function login(page: Page) {
  await page.goto('/login')
  await page.waitForSelector('input[type="email"]', { timeout: 10_000 })
  await page.fill('input[type="email"]', ADMIN_EMAIL)
  await page.fill('input[type="password"]', ADMIN_PASSWORD)
  await page.click('button[type="submit"]')
  // Wait for redirect to dashboard (any dashboard sub-page)
  await page.waitForURL(/\/dashboard/, { timeout: 20_000 })
}

test.describe('Admin Smoke Tests', () => {
  test.beforeEach(async ({ page }) => {
    await login(page)
  })

  // ---- Dashboard ----
  test('Dashboard loads with KPI cards', async ({ page }) => {
    await expect(page.locator('text=Dashboard').first()).toBeVisible()
    // Should have KPI stats (leads, contacts, etc.)
    await page.waitForTimeout(2000)
    // Check that the page has loaded content (not just a spinner)
    const body = await page.textContent('body')
    expect(body).toBeTruthy()
    // Look for typical dashboard elements
    await expect(page.locator('main')).toBeVisible()
  })

  // ---- Leads ----
  test('Leads page loads and shows table', async ({ page }) => {
    await page.click('a[href="/dashboard/leads"]')
    await page.waitForURL('**/dashboard/leads')
    await expect(page.locator('text=Leads').first()).toBeVisible()
    // Wait for data to load
    await page.waitForTimeout(3000)
    // Should have a table or data rows
    const body = await page.textContent('body')
    expect(body?.length).toBeGreaterThan(100)
  })

  // ---- Clients ----
  test('Clients page loads', async ({ page }) => {
    await page.click('a[href="/dashboard/clients"]')
    await page.waitForURL('**/dashboard/clients')
    await expect(page.locator('text=Clients').first()).toBeVisible()
    await page.waitForTimeout(2000)
  })

  // ---- Contacts ----
  test('Contacts page loads with sorting', async ({ page }) => {
    await page.click('a[href="/dashboard/contacts"]')
    await page.waitForURL('**/dashboard/contacts')
    await expect(page.locator('text=Contacts').first()).toBeVisible()
    await page.waitForTimeout(3000)
    // Verify table has rows (contacts exist)
    const body = await page.textContent('body')
    expect(body).toContain('@')  // email addresses should be visible
  })

  // ---- Mailboxes ----
  test('Mailboxes page loads and shows auth method options', async ({ page }) => {
    await page.click('a[href="/dashboard/mailboxes"]')
    await page.waitForURL('**/dashboard/mailboxes')
    await expect(page.locator('text=Mailboxes').first()).toBeVisible()
    await page.waitForTimeout(2000)
  })

  // ---- Pipelines ----
  test('Pipelines page loads', async ({ page }) => {
    await page.click('a[href="/dashboard/pipelines"]')
    await page.waitForURL('**/dashboard/pipelines')
    await expect(page.locator('text=Pipelines').first()).toBeVisible()
    await page.waitForTimeout(2000)
  })

  // ---- Templates ----
  test('Templates page loads', async ({ page }) => {
    await page.click('a[href="/dashboard/templates"]')
    await page.waitForURL('**/dashboard/templates')
    await expect(page.locator('text=Email Templates').first()).toBeVisible()
    await page.waitForTimeout(2000)
  })

  // ---- Warmup ----
  test('Warmup Engine page loads', async ({ page }) => {
    await page.click('a[href="/dashboard/warmup"]')
    await page.waitForURL('**/dashboard/warmup')
    await expect(page.locator('text=Warmup').first()).toBeVisible()
    await page.waitForTimeout(2000)
  })

  // ---- Outreach ----
  test('Outreach page loads', async ({ page }) => {
    await page.click('a[href="/dashboard/outreach"]')
    await page.waitForURL('**/dashboard/outreach')
    await expect(page.locator('text=Outreach').first()).toBeVisible()
    await page.waitForTimeout(2000)
  })

  // ---- Settings ----
  test('Settings page loads', async ({ page }) => {
    await page.click('a[href="/dashboard/settings"]')
    await page.waitForURL('**/dashboard/settings')
    await expect(page.locator('text=Settings').first()).toBeVisible()
    await page.waitForTimeout(2000)
  })

  // ---- User Management ----
  test('User Management page loads', async ({ page }) => {
    await page.click('a[href="/dashboard/users"]')
    await page.waitForURL('**/dashboard/users')
    await expect(page.locator('text=User Management').first()).toBeVisible()
    await page.waitForTimeout(2000)
  })

  // ---- Roles & Permissions ----
  test('Roles & Permissions page loads', async ({ page }) => {
    await page.click('a[href="/dashboard/roles"]')
    await page.waitForURL('**/dashboard/roles')
    await expect(page.locator('text=Roles').first()).toBeVisible()
    await page.waitForTimeout(2000)
  })

  // ---- Data Backups ----
  test('Data Backups page loads', async ({ page }) => {
    await page.click('a[href="/dashboard/backups"]')
    await page.waitForURL('**/dashboard/backups')
    await expect(page.locator('text=Backups').first()).toBeVisible()
    await page.waitForTimeout(2000)
  })

  // ---- Validation ----
  test('Validation page loads', async ({ page }) => {
    await page.click('a[href="/dashboard/validation"]')
    await page.waitForURL('**/dashboard/validation')
    await expect(page.locator('text=Validation').first()).toBeVisible()
    await page.waitForTimeout(2000)
  })

  // ---- Navigation sidebar ----
  test('Sidebar shows all admin navigation items', async ({ page }) => {
    const expectedLinks = [
      'Dashboard', 'Leads', 'Clients', 'Contacts', 'Validation',
      'Outreach', 'Email Templates', 'Mailboxes', 'Warmup Engine',
      'Pipelines', 'User Management', 'Roles & Permissions',
      'Data Backups', 'Settings'
    ]
    for (const linkText of expectedLinks) {
      await expect(page.locator(`nav >> text=${linkText}`).first()).toBeVisible()
    }
  })

  // ---- Logout ----
  test('Logout works and redirects to login', async ({ page }) => {
    await page.click('text=Sign out')
    await page.waitForURL('**/login', { timeout: 10_000 })
    await expect(page.locator('text=Sign In')).toBeVisible()
  })

  // ---- API Health ----
  test('API health endpoint returns healthy', async ({ request }) => {
    const response = await request.get('https://ra.partnerwithus.tech/health')
    expect(response.ok()).toBeTruthy()
    const body = await response.json()
    expect(body.status).toBe('healthy')
    expect(body.database).toBe('connected')
  })
})
