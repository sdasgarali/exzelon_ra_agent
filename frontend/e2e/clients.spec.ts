import { test, expect } from '@playwright/test'
import { loginAsSuperAdmin, loginAsAdmin } from './helpers/auth'
import { takeScreenshot } from './helpers/screenshots'

// ── Super Admin Tests ──────────────────────────────────────────────────────────

test.describe('Clients Page - Super Admin', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsSuperAdmin(page)
    await page.goto('/dashboard/clients', { waitUntil: 'networkidle' })
    // Wait for table to render (loading state clears)
    await page.waitForSelector('table', { timeout: 30000 })
    await page.waitForFunction(
      () => !document.querySelector('td')?.textContent?.includes('Loading clients'),
      { timeout: 30000 }
    )
  })

  test('1 - List loads with clients (table rows visible)', async ({ page }) => {
    // Verify the page heading
    const heading = page.locator('h1', { hasText: 'Clients' })
    await expect(heading).toBeVisible()

    // Verify the table exists and has data rows
    const table = page.locator('table')
    await expect(table).toBeVisible()

    const dataRows = table.locator('tbody tr')
    const rowCount = await dataRows.count()
    expect(rowCount).toBeGreaterThan(0)

    // Verify the subtitle shows the total count
    const subtitle = page.locator('p.text-gray-500.text-sm')
    await expect(subtitle).toBeVisible()
    const subtitleText = await subtitle.textContent()
    expect(subtitleText).toMatch(/\d+.*companies/)

    // Verify the pagination results summary is visible
    const resultsText = page.locator('text=/of \\d+ results/')
    await expect(resultsText).toBeVisible()

    await takeScreenshot(page, 'clients-list-loaded')
  })

  test('2 - Search by client name filters results', async ({ page }) => {
    // Grab the total before search
    const subtitleBefore = await page.locator('p.text-gray-500.text-sm').first().textContent()
    const totalBefore = parseInt(subtitleBefore?.match(/(\d+)/)?.[1] || '0', 10)

    // Type a search term into the search input
    const searchInput = page.locator('input[placeholder*="Search by"]')
    await expect(searchInput).toBeVisible()
    await searchInput.fill('Health')

    // Wait for debounce (300ms) + network response
    await page.waitForTimeout(1000)
    await page.waitForFunction(
      () => !document.querySelector('td')?.textContent?.includes('Loading clients'),
      { timeout: 15000 }
    )

    // Verify results are filtered
    const subtitleAfter = await page.locator('p.text-gray-500.text-sm').first().textContent()
    const totalAfter = parseInt(subtitleAfter?.match(/(\d+)/)?.[1] || '0', 10)

    // The filtered count should be less than or equal to the original total
    expect(totalAfter).toBeLessThanOrEqual(totalBefore)
    expect(totalAfter).toBeGreaterThan(0)

    // Verify table still has rows
    const dataRows = page.locator('table tbody tr')
    const rowCount = await dataRows.count()
    expect(rowCount).toBeGreaterThan(0)

    await takeScreenshot(page, 'clients-search-filtered')
  })

  test('3 - Filter by state (if state filter exists)', async ({ page }) => {
    // The clients page has a state filter dropdown populated from backend filter options
    // It renders as a <select> with "All States" as the default option
    const stateSelect = page.locator('select').filter({ hasText: 'All States' }).first()
    const stateFilterExists = await stateSelect.isVisible().catch(() => false)

    if (stateFilterExists) {
      // Get all options to find a valid state
      const options = stateSelect.locator('option')
      const optionCount = await options.count()

      if (optionCount > 1) {
        // Select the second option (first non-default state)
        const secondOption = await options.nth(1).getAttribute('value')
        if (secondOption) {
          await stateSelect.selectOption(secondOption)

          // Wait for table to reload
          await page.waitForTimeout(500)
          await page.waitForFunction(
            () => !document.querySelector('td')?.textContent?.includes('Loading clients'),
            { timeout: 15000 }
          )

          // Verify table has rows (or shows no results)
          const dataRows = page.locator('table tbody tr')
          const rowCount = await dataRows.count()
          expect(rowCount).toBeGreaterThanOrEqual(1) // At least 1 row (could be "no results" row)

          await takeScreenshot(page, 'clients-filter-state')
        }
      } else {
        // No state options available from backend; screenshot current state
        await takeScreenshot(page, 'clients-no-state-options')
      }
    } else {
      // State filter not rendered (no location_states from backend)
      // This is acceptable; the filter only renders when options exist
      await takeScreenshot(page, 'clients-no-state-filter')
    }
  })

  test('4 - Pagination works (click Next)', async ({ page }) => {
    // Verify pagination controls are visible
    const paginationText = page.locator('text=/Page \\d+ of \\d+/')
    await expect(paginationText).toBeVisible()

    // Verify we are on page 1
    const pageText = await paginationText.textContent()
    expect(pageText).toContain('Page 1 of')

    // Extract total pages to confirm there are multiple pages
    const totalPagesMatch = pageText?.match(/Page 1 of (\d+)/)
    const totalPages = parseInt(totalPagesMatch?.[1] || '1', 10)
    expect(totalPages).toBeGreaterThan(1)

    // Click the "Next" button
    const nextButton = page.locator('button', { hasText: 'Next' })
    await expect(nextButton).toBeVisible()
    await expect(nextButton).toBeEnabled()
    await nextButton.click()

    // Wait for table to reload
    await page.waitForTimeout(500)
    await page.waitForFunction(
      () => !document.querySelector('td')?.textContent?.includes('Loading clients'),
      { timeout: 15000 }
    )

    // Verify page number changed to 2
    const updatedPageText = await paginationText.textContent()
    expect(updatedPageText).toContain('Page 2 of')

    // Verify table still has data rows on page 2
    const dataRows = page.locator('table tbody tr')
    const rowCount = await dataRows.count()
    expect(rowCount).toBeGreaterThan(0)

    await takeScreenshot(page, 'clients-pagination-page2')
  })
})

// ── Admin Tests ────────────────────────────────────────────────────────────────

test.describe('Clients Page - Admin', () => {
  test('5 - Admin can view clients list with data', async ({ page }) => {
    await loginAsAdmin(page)
    await page.goto('/dashboard/clients', { waitUntil: 'networkidle' })
    await page.waitForSelector('table', { timeout: 30000 })
    await page.waitForFunction(
      () => !document.querySelector('td')?.textContent?.includes('Loading clients'),
      { timeout: 30000 }
    )

    // Verify the page heading
    const heading = page.locator('h1', { hasText: 'Clients' })
    await expect(heading).toBeVisible()

    // Verify table has data rows
    const dataRows = page.locator('table tbody tr')
    const rowCount = await dataRows.count()
    expect(rowCount).toBeGreaterThan(0)

    // Verify the subtitle shows client count
    const subtitle = page.locator('p.text-gray-500.text-sm')
    await expect(subtitle).toBeVisible()
    const subtitleText = await subtitle.textContent()
    expect(subtitleText).toMatch(/\d+.*companies/)

    await takeScreenshot(page, 'clients-admin-list')
  })
})
