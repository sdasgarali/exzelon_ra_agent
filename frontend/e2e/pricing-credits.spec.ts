import { test, expect, Page } from '@playwright/test'
import { loginAsAdmin, loginAsSuperAdmin } from './helpers/auth'

/**
 * Credit & pricing system (Phases 0-5). The admin fixture is expected to belong
 * to a MAX-plan tenant; the numbers asserted here come from PLAN_MATRIX.
 */

async function apiGet(page: Page, path: string) {
  return page.evaluate(async (p) => {
    // Same key + dual storage as lib/store.ts (localStorage when "remember me", else session).
    const raw = localStorage.getItem('auth-storage') ?? sessionStorage.getItem('auth-storage') ?? '{}'
    const token = JSON.parse(raw)?.state?.token || ''
    const r = await fetch('http://localhost:8000/api/v1' + p, { headers: { Authorization: `Bearer ${token}` } })
    return { status: r.status, body: await r.json().catch(() => null) }
  }, path)
}

test.describe('Public pricing page', () => {
  test('advertises Free / Pro / Max / Custom and no retired tiers', async ({ page }) => {
    await page.goto('/pricing', { waitUntil: 'networkidle' })
    const body = page.locator('body')
    for (const name of ['Free', 'Pro', 'Max', 'Custom']) {
      await expect(page.getByText(name, { exact: true }).first()).toBeVisible()
    }
    await expect(body).toContainText('$0')
    await expect(body).toContainText('$99')
    await expect(body).toContainText('$299')
    await expect(body).not.toContainText('$49')
    await expect(body).not.toContainText(/14-day trial/i)
  })
})

test.describe('Plan usage — Max tenant admin', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsAdmin(page)
  })

  test('dashboard shows the usage meters with the plan badge', async ({ page }) => {
    await page.goto('/dashboard', { waitUntil: 'networkidle' })
    const heading = page.getByRole('heading', { name: /Usage this month/i })
    await expect(heading).toBeVisible({ timeout: 20000 })
    await expect(heading).toContainText('Max')
    await expect(page.locator('[aria-label$=" used"]').first()).toBeVisible()
  })

  test('billing page shows the Max plan, its limits and the custom-plan builder', async ({ page }) => {
    await page.goto('/dashboard/billing', { waitUntil: 'networkidle' })
    await expect(page.getByRole('heading', { name: /Max plan/i })).toBeVisible({ timeout: 20000 })
    await expect(page.getByText('$299/month')).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Plan limits' })).toBeVisible()

    await page.getByRole('button', { name: /Build a custom plan/i }).click()
    await expect(page.getByRole('heading', { name: 'Build your plan' })).toBeVisible()
  })

  test('usage + credit APIs agree with the plan', async ({ page }) => {
    await page.goto('/dashboard', { waitUntil: 'networkidle' })
    const usage = await apiGet(page, '/billing/usage')
    expect(usage.status).toBe(200)
    expect(JSON.stringify(usage.body)).toContain('"max"')

    const balance = await apiGet(page, '/credits/balance')
    expect(balance.status).toBe(200)

    const prices = await apiGet(page, '/credits/price-list')
    expect(prices.status).toBe(200)
  })
})

/**
 * One user, one workspace (2026-09-23): a customer admin manages neither users nor
 * lines of business — only super admin does.
 */
test.describe('Single-user workspace — customer admin', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsAdmin(page)
  })

  test('sees no LOB selector and no Lines of Business nav item', async ({ page }) => {
    const nav = page.locator('nav[aria-label="Main navigation"]:visible').first()
    await expect(nav.getByRole('link', { name: 'Lines of Business' })).toHaveCount(0)
    await expect(page.getByRole('button', { name: /line of business|all lobs|select lob/i })).toHaveCount(0)
  })

  test('is sent home from /dashboard/lob', async ({ page }) => {
    await page.goto('/dashboard/lob')
    await page.waitForURL(/\/dashboard\/?$/, { timeout: 15000 })
  })

  test('has no Add User button', async ({ page }) => {
    await page.goto('/dashboard/users', { waitUntil: 'networkidle' })
    await expect(page.getByRole('heading', { name: 'User Management' })).toBeVisible({ timeout: 15000 })
    await expect(page.getByRole('button', { name: 'Add User' })).toHaveCount(0)
  })

  test('billing shows no seat or LOB limits', async ({ page }) => {
    await page.goto('/dashboard/billing', { waitUntil: 'networkidle' })
    await expect(page.getByRole('heading', { name: 'Plan limits' })).toBeVisible({ timeout: 20000 })
    await expect(page.getByText('Team seats')).toHaveCount(0)
    await expect(page.getByText('Lines of business')).toHaveCount(0)
  })
})

test.describe('Single-user workspace — super admin', () => {
  test('keeps Lines of Business and Add User', async ({ page }) => {
    await loginAsSuperAdmin(page)
    const nav = page.locator('nav[aria-label="Main navigation"]:visible').first()
    await expect(nav.getByRole('link', { name: 'Lines of Business' })).toBeVisible()
    await page.goto('/dashboard/users', { waitUntil: 'networkidle' })
    await expect(page.getByRole('button', { name: 'Add User' })).toBeVisible({ timeout: 15000 })
  })
})

test('public pricing page sells no seats or lines of business', async ({ page }) => {
  await page.goto('/pricing', { waitUntil: 'networkidle' })
  await expect(page.locator('body')).not.toContainText('Team seats')
  await expect(page.locator('body')).not.toContainText('Lines of business')
})
