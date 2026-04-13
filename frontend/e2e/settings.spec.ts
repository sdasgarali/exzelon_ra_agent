import { test, expect } from '@playwright/test'
import { loginAsSuperAdmin, loginAsAdmin } from './helpers/auth'
import { takeScreenshot } from './helpers/screenshots'

test.describe.serial('Settings — Super Admin', () => {
  test('1. Settings page loads with tab navigation', async ({ page }) => {
    await loginAsSuperAdmin(page)
    await page.goto('/dashboard/settings', { waitUntil: 'networkidle' })

    // Wait for loading to finish
    await page.waitForSelector('text=Loading settings...', { state: 'hidden', timeout: 30000 }).catch(() => {})

    // Verify the page title
    await expect(page.getByRole('heading', { name: 'Settings' })).toBeVisible({ timeout: 15000 })

    // Verify the tab navigation bar is present
    const tabNav = page.locator('nav.flex.space-x-4')
    await expect(tabNav).toBeVisible({ timeout: 15000 })

    // Verify key tabs are visible
    const expectedTabs = [
      '1. Job Filters',
      '2. Job Source APIs',
      '3. AI/LLM',
      '4. Contacts',
      '5. Validation',
      '6. Outreach',
      '7. Business Rules',
      '8. Deliverability',
    ]

    for (const tabLabel of expectedTabs) {
      await expect(tabNav.getByText(tabLabel, { exact: false })).toBeVisible()
    }

    await takeScreenshot(page, 'settings_tabs_loaded')
  })

  test('2. Navigate between tabs and verify content changes', async ({ page }) => {
    await loginAsSuperAdmin(page)
    await page.goto('/dashboard/settings', { waitUntil: 'networkidle' })
    await page.waitForSelector('text=Loading settings...', { state: 'hidden', timeout: 30000 }).catch(() => {})

    const tabNav = page.locator('nav.flex.space-x-4')
    await expect(tabNav).toBeVisible({ timeout: 15000 })

    // The first tab (Job Filters) should be active by default — verify its content
    await expect(page.getByText('Job Filters', { exact: false }).first()).toBeVisible()
    await expect(page.getByText('Target States')).toBeVisible({ timeout: 10000 })

    await takeScreenshot(page, 'settings_tab_jobfilters')

    // Click the "3. AI/LLM" tab
    await tabNav.getByText('3. AI/LLM').click()
    await page.waitForTimeout(1000)

    // Verify AI tab content loaded — look for AI Provider label
    await expect(page.getByText('AI Provider', { exact: true })).toBeVisible({ timeout: 10000 })

    await takeScreenshot(page, 'settings_tab_ai')

    // Click the "7. Business Rules" tab
    await tabNav.getByText('7. Business Rules').click()
    await page.waitForTimeout(1000)

    // Verify Business Rules content loaded
    await expect(page.getByText('Daily Send Limit')).toBeVisible({ timeout: 10000 })
    await expect(page.getByText('Cooldown Period (Days)')).toBeVisible({ timeout: 10000 })

    await takeScreenshot(page, 'settings_tab_business')

    // Click the "8. Deliverability" tab
    await tabNav.getByText('8. Deliverability').click()
    await page.waitForTimeout(1000)

    await takeScreenshot(page, 'settings_tab_deliverability')
  })

  test('3. Modify a business rule setting and save', async ({ page }) => {
    await loginAsSuperAdmin(page)
    await page.goto('/dashboard/settings', { waitUntil: 'networkidle' })
    await page.waitForSelector('text=Loading settings...', { state: 'hidden', timeout: 30000 }).catch(() => {})

    const tabNav = page.locator('nav.flex.space-x-4')
    await expect(tabNav).toBeVisible({ timeout: 15000 })

    // Navigate to Business Rules tab
    await tabNav.getByText('7. Business Rules').click()
    await page.waitForTimeout(1000)

    // Wait for the Daily Send Limit input to be visible
    await expect(page.getByText('Daily Send Limit')).toBeVisible({ timeout: 10000 })

    // Find the Daily Send Limit input — it is the first number input under the "Outreach Limits" heading
    const dailySendLimitLabel = page.locator('label', { hasText: 'Daily Send Limit' })
    const dailySendLimitInput = dailySendLimitLabel.locator('..').locator('input[type="number"]')
    await expect(dailySendLimitInput).toBeVisible()

    // Read the current value
    const currentValue = await dailySendLimitInput.inputValue()
    const currentNum = parseInt(currentValue) || 30

    // Change to a new value (toggle between 30 and 35)
    const newValue = currentNum === 35 ? 30 : 35
    await dailySendLimitInput.fill('')
    await dailySendLimitInput.fill(String(newValue))

    await takeScreenshot(page, 'settings_business_modified')

    // Click "Save Business Rules"
    const saveBtn = page.locator('button', { hasText: 'Save Business Rules' })
    await expect(saveBtn).toBeVisible()
    await saveBtn.click()

    // Wait for success feedback (green success banner)
    const successBanner = page.locator('.bg-green-50.text-green-600')
    await expect(successBanner).toBeVisible({ timeout: 15000 })

    await takeScreenshot(page, 'settings_business_saved')
  })

  test('4. Settings persist after page refresh', async ({ page }) => {
    await loginAsSuperAdmin(page)
    await page.goto('/dashboard/settings', { waitUntil: 'networkidle' })
    await page.waitForSelector('text=Loading settings...', { state: 'hidden', timeout: 30000 }).catch(() => {})

    const tabNav = page.locator('nav.flex.space-x-4')
    await expect(tabNav).toBeVisible({ timeout: 15000 })

    // Navigate to Business Rules tab
    await tabNav.getByText('7. Business Rules').click()
    await page.waitForTimeout(1000)

    // Read the Daily Send Limit value
    const dailySendLimitLabel = page.locator('label', { hasText: 'Daily Send Limit' })
    const dailySendLimitInput = dailySendLimitLabel.locator('..').locator('input[type="number"]')
    await expect(dailySendLimitInput).toBeVisible({ timeout: 10000 })
    const valueBefore = await dailySendLimitInput.inputValue()

    // Set a specific known value
    const testValue = '42'
    await dailySendLimitInput.fill('')
    await dailySendLimitInput.fill(testValue)

    // Save
    const saveBtn = page.locator('button', { hasText: 'Save Business Rules' })
    await saveBtn.click()
    const successBanner = page.locator('.bg-green-50.text-green-600')
    await expect(successBanner).toBeVisible({ timeout: 15000 })

    await takeScreenshot(page, 'settings_persist_before_refresh')

    // Refresh the page
    await page.reload({ waitUntil: 'networkidle' })
    await page.waitForSelector('text=Loading settings...', { state: 'hidden', timeout: 30000 }).catch(() => {})

    // Navigate back to Business Rules tab
    const tabNavAfter = page.locator('nav.flex.space-x-4')
    await expect(tabNavAfter).toBeVisible({ timeout: 15000 })
    await tabNavAfter.getByText('7. Business Rules').click()
    await page.waitForTimeout(1000)

    // Verify the value persisted
    const dailySendLimitAfter = page.locator('label', { hasText: 'Daily Send Limit' }).locator('..').locator('input[type="number"]')
    await expect(dailySendLimitAfter).toBeVisible({ timeout: 10000 })
    const valueAfter = await dailySendLimitAfter.inputValue()
    expect(valueAfter).toBe(testValue)

    await takeScreenshot(page, 'settings_persist_after_refresh')

    // Restore original value to keep tests idempotent
    await dailySendLimitAfter.fill('')
    await dailySendLimitAfter.fill(valueBefore || '30')
    const saveBtnAfter = page.locator('button', { hasText: 'Save Business Rules' })
    await saveBtnAfter.click()
    await expect(page.locator('.bg-green-50.text-green-600')).toBeVisible({ timeout: 15000 })
  })
})

test.describe.serial('Settings — Admin', () => {
  test('5. Settings page loads with tabs for admin', async ({ page }) => {
    await loginAsAdmin(page)
    await page.goto('/dashboard/settings', { waitUntil: 'networkidle' })
    await page.waitForSelector('text=Loading settings...', { state: 'hidden', timeout: 30000 }).catch(() => {})

    // Verify the page title
    await expect(page.getByRole('heading', { name: 'Settings' })).toBeVisible({ timeout: 15000 })

    // Verify the tab navigation bar is present
    const tabNav = page.locator('nav.flex.space-x-4')
    await expect(tabNav).toBeVisible({ timeout: 15000 })

    // Admin should see at least some tabs (depends on permissions)
    const tabButtons = tabNav.locator('button')
    const tabCount = await tabButtons.count()
    expect(tabCount).toBeGreaterThan(0)

    // Verify the subtitle text is visible
    await expect(page.getByText('Configure all providers, API keys, and business rules')).toBeVisible()

    await takeScreenshot(page, 'settings_admin_tabs')
  })
})
