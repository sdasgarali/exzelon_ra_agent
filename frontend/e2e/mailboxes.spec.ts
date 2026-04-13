import { test, expect } from '@playwright/test'
import { loginAsSuperAdmin } from './helpers/auth'
import { takeScreenshot } from './helpers/screenshots'

/**
 * Mailboxes Page E2E Tests
 *
 * Tests the /dashboard/mailboxes page which displays 5 mailboxes
 * in a table with health scores, daily limits, warmup status,
 * and connection indicators.
 */

test.describe('Mailboxes — Super Admin', () => {
  test('1 — List loads with 5 mailboxes', async ({ page }) => {
    await loginAsSuperAdmin(page)
    await page.goto('/dashboard/mailboxes', { waitUntil: 'networkidle' })

    // Wait for the mailboxes table to render
    const tableBody = page.locator('table tbody')
    await tableBody.waitFor({ state: 'visible', timeout: 20000 })

    // Wait for rows to appear (not loading state)
    const rows = tableBody.locator('tr')
    await rows.first().waitFor({ state: 'visible', timeout: 15000 })

    // Count the mailbox rows — expecting 5
    const rowCount = await rows.count()
    expect(rowCount).toBe(5)

    // Verify each row has an email address displayed
    for (let i = 0; i < rowCount; i++) {
      const emailCell = rows.nth(i).locator('td').nth(1) // Email is the second column (after checkbox)
      const emailText = await emailCell.textContent()
      expect(emailText).toBeTruthy()
      expect(emailText!.length).toBeGreaterThan(0)
    }

    await takeScreenshot(page, 'mailboxes-01-list-loaded')
  })

  test('2 — Health score badges visible', async ({ page }) => {
    await loginAsSuperAdmin(page)
    await page.goto('/dashboard/mailboxes', { waitUntil: 'networkidle' })

    // Wait for the table to render
    await page.locator('table tbody tr').first().waitFor({ state: 'visible', timeout: 20000 })

    // Health scores are loaded asynchronously via deliverabilityApi.mailboxHealth()
    // Wait for health data to populate — look for health grade badges (A+, A, B, C, D)
    // or the progress bar elements that show health scores
    // The health column renders either a grade badge or a "-" placeholder
    await page.waitForTimeout(5000) // Allow async health data to load

    // Look for health score progress bars (div with bg-green-500, bg-yellow-500, etc.)
    const healthBars = page.locator('table tbody .rounded-full.overflow-hidden .h-full.rounded-full')
    const healthBarCount = await healthBars.count()

    // Look for health grade badges (span elements with grade text like A+, A, B, C, D, F)
    const gradeBadges = page.locator('table tbody span').filter({ hasText: /^[A-F]\+?$/ })
    const gradeCount = await gradeBadges.count()

    // At least some mailboxes should have health data loaded
    // (either progress bars or grade badges)
    const totalHealthIndicators = healthBarCount + gradeCount
    expect(totalHealthIndicators).toBeGreaterThanOrEqual(1)

    await takeScreenshot(page, 'mailboxes-02-health-scores')
  })

  test('3 — Daily limit and sent counters shown', async ({ page }) => {
    await loginAsSuperAdmin(page)
    await page.goto('/dashboard/mailboxes', { waitUntil: 'networkidle' })

    // Wait for the table rows
    await page.locator('table tbody tr').first().waitFor({ state: 'visible', timeout: 20000 })

    // The "Today" column shows "{sent} / {limit}" format (e.g., "0 / 30")
    // Look for the pattern "X / Y" in the table rows
    const todayColumn = page.locator('table tbody tr').first().locator('td').nth(5) // Today is the 6th column
    const todayText = await todayColumn.textContent()
    expect(todayText).toBeTruthy()
    // Should contain the "/" separator between sent and limit
    expect(todayText).toMatch(/\d+\s*\/\s*\d+/)

    // Also check for the progress bar within the Today column
    const progressBar = todayColumn.locator('.bg-gray-200.rounded-full')
    await expect(progressBar).toBeVisible()

    // Verify the "Outreach" column (7th column) shows a number
    const outreachColumn = page.locator('table tbody tr').first().locator('td').nth(6)
    const outreachText = await outreachColumn.textContent()
    expect(outreachText).toBeTruthy()
    // Should contain at least a number (outreach emails sent count)
    expect(outreachText).toMatch(/\d+/)

    // Check all 5 rows have the daily limit counters
    const allRows = page.locator('table tbody tr')
    const allRowCount = await allRows.count()
    for (let i = 0; i < allRowCount; i++) {
      const cell = allRows.nth(i).locator('td').nth(5)
      const text = await cell.textContent()
      expect(text).toMatch(/\d+\s*\/\s*\d+/)
    }

    await takeScreenshot(page, 'mailboxes-03-daily-limits')
  })

  test('4 — DNS/Connection status indicators visible', async ({ page }) => {
    await loginAsSuperAdmin(page)
    await page.goto('/dashboard/mailboxes', { waitUntil: 'networkidle' })

    // Wait for the table rows to render
    await page.locator('table tbody tr').first().waitFor({ state: 'visible', timeout: 20000 })

    // The connection status column shows badges: "Successful", "Failed", or "Testing..."
    // These are rendered as colored pill badges in the Connection column
    // Look for connection status badges across all rows
    const successBadges = page.locator('table tbody span', { hasText: 'Successful' })
    const failedBadges = page.locator('table tbody span', { hasText: 'Failed' })
    const testingBadges = page.locator('table tbody span', { hasText: 'Testing' })
    const untestedIndicators = page.locator('table tbody span', { hasText: 'Untested' })

    const successCount = await successBadges.count()
    const failedCount = await failedBadges.count()
    const testingCount = await testingBadges.count()
    const untestedCount = await untestedIndicators.count()

    // At least some mailboxes should have a connection status indicator
    const totalStatusIndicators = successCount + failedCount + testingCount + untestedCount
    // We expect connection status for the mailboxes — at least one should have been tested
    expect(totalStatusIndicators).toBeGreaterThanOrEqual(1)

    // Verify the Connection column header exists
    const connectionHeader = page.locator('thead th', { hasText: /Connection/i })
    await expect(connectionHeader).toBeVisible()

    await takeScreenshot(page, 'mailboxes-04-connection-status')
  })

  test('5 — Warmup status visible on mailbox rows', async ({ page }) => {
    await loginAsSuperAdmin(page)
    await page.goto('/dashboard/mailboxes', { waitUntil: 'networkidle' })

    // Wait for the table rows to render
    await page.locator('table tbody tr').first().waitFor({ state: 'visible', timeout: 20000 })

    // The "Status" column (4th column) shows warmup status badges:
    // "Inactive", "Warming Up", "Cold Ready", "Active", "Paused", "Blacklisted", "Recovering"
    const warmupStatuses = [
      'Inactive',
      'Warming Up',
      'Cold Ready',
      'Active',
      'Paused',
      'Blacklisted',
      'Recovering',
    ]

    // Count how many warmup status badges are visible
    let totalWarmupBadges = 0
    for (const status of warmupStatuses) {
      const badges = page.locator('table tbody span.rounded-full', { hasText: status })
      totalWarmupBadges += await badges.count()
    }

    // All 5 mailboxes should have a warmup status badge
    expect(totalWarmupBadges).toBeGreaterThanOrEqual(5)

    // Verify the Status column header exists with warmup tooltip
    const statusHeader = page.locator('thead th', { hasText: /Status/i })
    await expect(statusHeader).toBeVisible()

    // Verify the first row has a warmup status badge with the expected CSS classes
    const firstRowStatusCell = page.locator('table tbody tr').first().locator('td').nth(3)
    const statusBadge = firstRowStatusCell.locator('span.rounded-full')
    await expect(statusBadge).toBeVisible()
    const statusText = await statusBadge.textContent()
    expect(warmupStatuses).toContain(statusText!.trim())

    // Check for warmup email count indicator (shows "X warmup" text below outreach count)
    // This appears only if warmup_emails_sent > 0
    const warmupCountLabels = page.locator('table tbody', { hasText: /warmup/i })
    // Just verify the page has rendered — warmup count may or may not appear depending on data
    await expect(warmupCountLabels).toBeVisible()

    await takeScreenshot(page, 'mailboxes-05-warmup-status')
  })
})
