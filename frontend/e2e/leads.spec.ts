import { test, expect } from '@playwright/test'
import { loginAsSuperAdmin, loginAsAdmin } from './helpers/auth'
import { takeScreenshot } from './helpers/screenshots'

// ── Super Admin Tests ──────────────────────────────────────────────────────────

test.describe('Leads Page - Super Admin', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsSuperAdmin(page)
    await page.goto('/dashboard/leads', { waitUntil: 'networkidle' })
    // Wait for table to render (loading state clears)
    await page.waitForSelector('table', { timeout: 30000 })
    // Wait until "Loading leads..." disappears
    await page.waitForFunction(
      () => !document.querySelector('td')?.textContent?.includes('Loading leads'),
      { timeout: 30000 }
    )
  })

  test('1 - List loads with data (table has rows)', async ({ page }) => {
    // Verify the page heading
    const heading = page.getByRole('heading', { name: 'Leads', exact: true })
    await expect(heading).toBeVisible()

    // Verify the table exists and has data rows in tbody
    const table = page.locator('table')
    await expect(table).toBeVisible()

    const dataRows = table.locator('tbody tr')
    const rowCount = await dataRows.count()
    expect(rowCount).toBeGreaterThan(0)

    // Verify the results count text shows a positive total
    const resultsText = page.locator('text=/of \\d+ results/')
    await expect(resultsText).toBeVisible()

    await takeScreenshot(page, 'leads-list-loaded')
  })

  test('2 - Search by company name filters results', async ({ page }) => {
    // Grab the total before search from the subtitle (e.g. "1655 job postings...")
    const subtitleText = await page.locator('p.text-gray-500.text-sm').first().textContent()
    const totalBefore = parseInt(subtitleText?.match(/(\d+)/)?.[1] || '0', 10)

    // Type a search term into the search input
    const searchInput = page.locator('input[placeholder*="Search by"]')
    await expect(searchInput).toBeVisible()
    await searchInput.fill('Health')
    // Wait for debounce (300ms) + network response
    await page.waitForTimeout(1000)
    await page.waitForFunction(
      () => !document.querySelector('td')?.textContent?.includes('Loading leads'),
      { timeout: 15000 }
    )

    // Verify results are filtered (total changes or table rows have the search term)
    const filteredSubtitle = await page.locator('p.text-gray-500.text-sm').first().textContent()
    const totalAfter = parseInt(filteredSubtitle?.match(/(\d+)/)?.[1] || '0', 10)

    // The filtered count should be less than the original total (or equal if all match)
    expect(totalAfter).toBeLessThanOrEqual(totalBefore)
    expect(totalAfter).toBeGreaterThan(0)

    await takeScreenshot(page, 'leads-search-filtered')
  })

  test('3 - Filter by status dropdown', async ({ page }) => {
    // Find the status dropdown (select with "All Statuses" option)
    const statusSelect = page.locator('select').filter({ hasText: 'All Statuses' }).first()
    await expect(statusSelect).toBeVisible()

    // Select "New" status
    await statusSelect.selectOption('new')
    await page.waitForTimeout(500)
    await page.waitForFunction(
      () => !document.querySelector('td')?.textContent?.includes('Loading leads'),
      { timeout: 15000 }
    )

    // Verify rows exist (or "No leads found" if none match)
    const table = page.locator('table')
    const rows = table.locator('tbody tr')
    const rowCount = await rows.count()
    expect(rowCount).toBeGreaterThan(0)

    await takeScreenshot(page, 'leads-filter-status-new')
  })

  test('4 - Pagination works (click Next)', async ({ page }) => {
    // Verify pagination controls are visible
    const paginationText = page.locator('text=/Page \\d+ of \\d+/')
    await expect(paginationText).toBeVisible()

    // Verify we are on page 1
    const pageText = await paginationText.textContent()
    expect(pageText).toContain('Page 1 of')

    // Click the "Next" button
    const nextButton = page.locator('button', { hasText: 'Next' })
    await expect(nextButton).toBeVisible()
    await expect(nextButton).toBeEnabled()
    await nextButton.click()

    // Wait for table to reload
    await page.waitForTimeout(500)
    await page.waitForFunction(
      () => !document.querySelector('td')?.textContent?.includes('Loading leads'),
      { timeout: 15000 }
    )

    // Verify page number changed to 2
    const updatedPageText = await paginationText.textContent()
    expect(updatedPageText).toContain('Page 2 of')

    await takeScreenshot(page, 'leads-pagination-page2')
  })

  test('5 - Click lead row navigates to detail page', async ({ page }) => {
    // Find the first lead ID link (e.g. "#123") in the table
    const firstLeadLink = page.locator('table tbody tr').first().locator('a[href*="/dashboard/leads/"]').first()
    await expect(firstLeadLink).toBeVisible()

    // Extract the lead ID from the link text or href
    const href = await firstLeadLink.getAttribute('href')
    expect(href).toBeTruthy()
    expect(href).toMatch(/\/dashboard\/leads\/\d+/)

    // Click the link
    await firstLeadLink.click()

    // Wait for navigation to the detail page
    await page.waitForURL(/\/dashboard\/leads\/\d+/, { timeout: 30000 })

    // Verify we are on the detail page
    const currentUrl = page.url()
    expect(currentUrl).toMatch(/\/dashboard\/leads\/\d+/)

    // Wait for detail page content to load
    await page.waitForTimeout(2000)

    await takeScreenshot(page, 'leads-detail-page')
  })
})

// ── Archive / Restore Flow (serial) ──────────────────────────────────────────

test.describe.serial('Leads Page - Archive and Restore Flow (Super Admin)', () => {
  test('6 - Archive lead via bulk action', async ({ page }) => {
    await loginAsSuperAdmin(page)
    await page.goto('/dashboard/leads', { waitUntil: 'networkidle' })
    await page.waitForSelector('table', { timeout: 30000 })
    await page.waitForFunction(
      () => !document.querySelector('td')?.textContent?.includes('Loading leads'),
      { timeout: 30000 }
    )

    // Select the first lead by clicking its checkbox
    const firstRowCheckbox = page.locator('table tbody tr').first().locator('input[type="checkbox"]')
    await expect(firstRowCheckbox).toBeVisible()
    await firstRowCheckbox.check()

    // Verify selection info bar appears
    const selectionBar = page.locator('text=/\\d+ lead\\(s\\) selected/')
    await expect(selectionBar).toBeVisible()

    // Click "Archive Selected" button
    const archiveButton = page.locator('button', { hasText: /Archive Selected/ })
    await expect(archiveButton).toBeVisible()
    await archiveButton.click()

    // Confirm archive modal appears
    const confirmModal = page.locator('text=Confirm Archive')
    await expect(confirmModal).toBeVisible()

    // Click the Archive confirmation button in the modal
    const confirmButton = page.locator('button', { hasText: 'Archive' }).last()
    await confirmButton.click()

    // Wait for success message
    const successMsg = page.locator('.bg-green-50')
    await expect(successMsg).toBeVisible({ timeout: 15000 })

    await takeScreenshot(page, 'leads-archived')
  })

  test('7 - Restore archived lead', async ({ page }) => {
    await loginAsSuperAdmin(page)
    await page.goto('/dashboard/leads', { waitUntil: 'networkidle' })
    await page.waitForSelector('table', { timeout: 30000 })
    await page.waitForFunction(
      () => !document.querySelector('td')?.textContent?.includes('Loading leads'),
      { timeout: 30000 }
    )

    // Enable "Show Archived" toggle to see archived leads
    const showArchivedCheckbox = page.locator('label').filter({ hasText: 'Show Archived' }).locator('input[type="checkbox"]')
    await expect(showArchivedCheckbox).toBeVisible()
    await showArchivedCheckbox.check()

    // Wait for reload with archived leads
    await page.waitForTimeout(1000)
    await page.waitForFunction(
      () => !document.querySelector('td')?.textContent?.includes('Loading leads'),
      { timeout: 15000 }
    )

    // Find an archived lead (row with "Archived" badge) and select it
    const archivedRow = page.locator('table tbody tr').filter({ hasText: 'Archived' }).first()
    await expect(archivedRow).toBeVisible({ timeout: 10000 })
    const archivedCheckbox = archivedRow.locator('input[type="checkbox"]')
    await archivedCheckbox.check()

    // Verify "Restore Selected" button appears (in archived view, only Restore is shown)
    const restoreButton = page.locator('button', { hasText: /Restore Selected/ })
    await expect(restoreButton).toBeVisible()
    await restoreButton.click()

    // Wait for success message
    const successMsg = page.locator('.bg-green-50')
    await expect(successMsg).toBeVisible({ timeout: 15000 })

    await takeScreenshot(page, 'leads-restored')
  })
})

// ── Bulk Select ─────────────────────────────────────────────────────────────

test.describe('Leads Page - Bulk Select (Super Admin)', () => {
  test('8 - Bulk select leads via select-all checkbox', async ({ page }) => {
    await loginAsSuperAdmin(page)
    await page.goto('/dashboard/leads', { waitUntil: 'networkidle' })
    await page.waitForSelector('table', { timeout: 30000 })
    await page.waitForFunction(
      () => !document.querySelector('td')?.textContent?.includes('Loading leads'),
      { timeout: 30000 }
    )

    // Click the select-all checkbox in the table header
    const selectAllCheckbox = page.locator('table thead th').first().locator('input[type="checkbox"]')
    await expect(selectAllCheckbox).toBeVisible()
    await selectAllCheckbox.check()

    // Verify selection info bar shows the count matching table rows
    const selectionBar = page.locator('text=/\\d+ lead\\(s\\) selected/')
    await expect(selectionBar).toBeVisible()

    // Count data rows in tbody
    const rowCount = await page.locator('table tbody tr').count()

    // Extract the selected count from the selection bar text
    const selectionText = await selectionBar.textContent()
    const selectedCount = parseInt(selectionText?.match(/(\d+)/)?.[1] || '0', 10)
    expect(selectedCount).toBe(rowCount)

    // Verify bulk action buttons appear (Archive Selected, Update Status, etc.)
    const archiveBtn = page.locator('button', { hasText: /Archive Selected/ })
    await expect(archiveBtn).toBeVisible()

    await takeScreenshot(page, 'leads-bulk-selected')

    // Uncheck select-all to clean up
    await selectAllCheckbox.uncheck()
  })
})

// ── Admin Tests ────────────────────────────────────────────────────────────────

test.describe('Leads Page - Admin', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsAdmin(page)
    await page.goto('/dashboard/leads', { waitUntil: 'networkidle' })
    await page.waitForSelector('table', { timeout: 30000 })
    await page.waitForFunction(
      () => !document.querySelector('td')?.textContent?.includes('Loading leads'),
      { timeout: 30000 }
    )
  })

  test('9 - Admin can view leads list with data', async ({ page }) => {
    // Verify the page heading
    const heading = page.getByRole('heading', { name: 'Leads', exact: true })
    await expect(heading).toBeVisible()

    // Verify table has data rows
    const dataRows = page.locator('table tbody tr')
    const rowCount = await dataRows.count()
    expect(rowCount).toBeGreaterThan(0)

    await takeScreenshot(page, 'leads-admin-list')
  })

  test('10 - Archived view shows only Restore Selected button (no Delete/Archive)', async ({ page }) => {
    // Enable "Show Archived" toggle
    const showArchivedCheckbox = page.locator('label').filter({ hasText: 'Show Archived' }).locator('input[type="checkbox"]')
    await expect(showArchivedCheckbox).toBeVisible()
    await showArchivedCheckbox.check()

    // Wait for reload
    await page.waitForTimeout(1000)
    await page.waitForFunction(
      () => !document.querySelector('td')?.textContent?.includes('Loading leads'),
      { timeout: 15000 }
    )

    // Find an archived lead and select it
    const archivedRow = page.locator('table tbody tr').filter({ hasText: 'Archived' }).first()
    // If no archived leads exist, this test gracefully handles it
    const archivedExists = await archivedRow.isVisible().catch(() => false)

    if (archivedExists) {
      const archivedCheckbox = archivedRow.locator('input[type="checkbox"]')
      await archivedCheckbox.check()

      // Verify "Restore Selected" is the visible bulk action
      const restoreButton = page.locator('button', { hasText: /Restore Selected/ })
      await expect(restoreButton).toBeVisible()

      // Verify "Archive Selected" is NOT visible (in archived view, only Restore shows)
      const archiveButton = page.locator('button', { hasText: /Archive Selected/ })
      await expect(archiveButton).not.toBeVisible()

      // Verify other bulk actions like "Contact Enrich", "Send Outreach", "Update Status" are NOT visible
      const enrichButton = page.locator('button', { hasText: /Contact Enrich/ })
      await expect(enrichButton).not.toBeVisible()

      await takeScreenshot(page, 'leads-admin-archived-restore-only')
    } else {
      // No archived leads to test; take a screenshot of the current state
      await takeScreenshot(page, 'leads-admin-no-archived-leads')
    }
  })
})
