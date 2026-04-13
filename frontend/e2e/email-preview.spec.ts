import { test, expect } from '@playwright/test'
import { loginAsSuperAdmin, loginAsAdmin } from './helpers/auth'
import { takeScreenshot } from './helpers/screenshots'

// ─── Super Admin Tests ──────────────────────────────────────────────

test.describe('Email Preview — Super Admin', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsSuperAdmin(page)
    await page.goto('/dashboard/email-preview', { waitUntil: 'networkidle' })
    // Wait for page to fully render (loading spinner disappears or content appears)
    await page.waitForTimeout(2000)
  })

  test('1. Draft list loads — shows drafts or empty state', async ({ page }) => {
    // The left panel (w-[320px]) should be visible
    const leftPanel = page.locator('.w-\\[320px\\]').first()
    await expect(leftPanel).toBeVisible()

    // Either draft cards are present or the "No drafts found" empty state is shown
    const draftCards = page.locator('.w-\\[320px\\] .cursor-pointer')
    const emptyState = page.getByText('No drafts found')

    const hasDrafts = await draftCards.count() > 0
    const hasEmptyState = await emptyState.isVisible().catch(() => false)

    expect(hasDrafts || hasEmptyState).toBeTruthy()

    await takeScreenshot(page, 'email-preview-draft-list-loaded')
  })

  test('2. Status filter dropdown works', async ({ page }) => {
    // Find the status filter select element by its "All statuses" default option
    const statusSelect = page.locator('select').filter({ hasText: 'All statuses' })
    await expect(statusSelect).toBeVisible()

    // Select "Pending" status
    await statusSelect.selectOption('pending')

    // Wait for the filter to take effect (API call)
    await page.waitForTimeout(1500)

    // Verify the select now has "pending" selected
    const selectedValue = await statusSelect.inputValue()
    expect(selectedValue).toBe('pending')

    await takeScreenshot(page, 'email-preview-status-filter-pending')

    // Reset back to "All statuses"
    await statusSelect.selectOption('')
    await page.waitForTimeout(1000)

    await takeScreenshot(page, 'email-preview-status-filter-reset')
  })

  test('3. Source filter dropdown works', async ({ page }) => {
    // Find the source filter select element by its "All sources" default option
    const sourceSelect = page.locator('select').filter({ hasText: 'All sources' })
    await expect(sourceSelect).toBeVisible()

    // Select "Campaign" source
    await sourceSelect.selectOption('campaign')

    // Wait for the filter to take effect
    await page.waitForTimeout(1500)

    // Verify the select now has "campaign" selected
    const selectedValue = await sourceSelect.inputValue()
    expect(selectedValue).toBe('campaign')

    await takeScreenshot(page, 'email-preview-source-filter-campaign')

    // Reset back to "All sources"
    await sourceSelect.selectOption('')
    await page.waitForTimeout(1000)

    await takeScreenshot(page, 'email-preview-source-filter-reset')
  })

  test('4. Select draft — preview panel shows content', async ({ page }) => {
    // Check if drafts exist
    const draftCards = page.locator('.w-\\[320px\\] .cursor-pointer')
    const draftCount = await draftCards.count()

    if (draftCount > 0) {
      // Click the first draft card
      await draftCards.first().click()
      await page.waitForTimeout(1500)

      // The center panel should now show email content (From:, To:, subject, body)
      const fromLabel = page.getByText('From:')
      const toLabel = page.getByText('To:')
      await expect(fromLabel.first()).toBeVisible()
      await expect(toLabel.first()).toBeVisible()

      // The "Select a draft to preview" placeholder should NOT be visible
      const placeholder = page.getByText('Select a draft to preview')
      await expect(placeholder).not.toBeVisible()

      await takeScreenshot(page, 'email-preview-draft-selected')
    } else {
      // Empty state — the center panel shows the placeholder message
      const placeholder = page.getByText('Select a draft to preview')
      await expect(placeholder).toBeVisible()

      await takeScreenshot(page, 'email-preview-no-drafts-placeholder')
    }
  })

  test('5. Checkboxes visible on draft cards (SA only)', async ({ page }) => {
    const draftCards = page.locator('.w-\\[320px\\] .cursor-pointer')
    const draftCount = await draftCards.count()

    if (draftCount > 0) {
      // Super Admin should see checkboxes on draft cards
      // Checkboxes are input[type="checkbox"] inside the draft card area
      const checkboxes = page.locator('.w-\\[320px\\] input[type="checkbox"]')
      const checkboxCount = await checkboxes.count()

      // There should be at least one checkbox (per-draft) and possibly one "Select all"
      expect(checkboxCount).toBeGreaterThan(0)

      await takeScreenshot(page, 'email-preview-sa-checkboxes-visible')
    } else {
      // No drafts — the "Select all" checkbox only shows when filteredDrafts.length > 0
      // so no checkboxes should be visible in empty state
      const checkboxes = page.locator('.w-\\[320px\\] input[type="checkbox"]')
      const checkboxCount = await checkboxes.count()
      expect(checkboxCount).toBe(0)

      await takeScreenshot(page, 'email-preview-sa-no-drafts-no-checkboxes')
    }
  })

  test('6. Select all checkbox works', async ({ page }) => {
    const draftCards = page.locator('.w-\\[320px\\] .cursor-pointer')
    const draftCount = await draftCards.count()

    if (draftCount > 0) {
      // The "Select all" checkbox is the one inside the label with "Select all" text
      const selectAllLabel = page.locator('label').filter({ hasText: 'Select all' })
      await expect(selectAllLabel).toBeVisible()

      // Click the "Select all" label/checkbox
      await selectAllLabel.click()
      await page.waitForTimeout(500)

      // After selecting all, the per-draft checkboxes should all be checked
      const draftCheckboxes = page.locator('.w-\\[320px\\] .cursor-pointer input[type="checkbox"]')
      const checkedCount = await draftCheckboxes.count()

      if (checkedCount > 0) {
        for (let i = 0; i < checkedCount; i++) {
          await expect(draftCheckboxes.nth(i)).toBeChecked()
        }
      }

      await takeScreenshot(page, 'email-preview-select-all-checked')

      // Click again to deselect all
      await selectAllLabel.click()
      await page.waitForTimeout(500)

      await takeScreenshot(page, 'email-preview-select-all-unchecked')
    } else {
      // No drafts — skip
      test.skip()
    }
  })

  test('7. Delete Selected button appears when items selected', async ({ page }) => {
    const draftCards = page.locator('.w-\\[320px\\] .cursor-pointer')
    const draftCount = await draftCards.count()

    if (draftCount > 0) {
      // Initially, "Delete Selected" button should NOT be visible
      const deleteBtn = page.getByRole('button', { name: /Delete Selected/i })
      await expect(deleteBtn).not.toBeVisible()

      // Select a draft via its checkbox (click the checkbox inside the first draft card)
      const firstCheckbox = page.locator('.w-\\[320px\\] .cursor-pointer input[type="checkbox"]').first()
      await firstCheckbox.click()
      await page.waitForTimeout(500)

      // Now "Delete Selected" button should appear (SA only)
      await expect(deleteBtn).toBeVisible()

      // Verify it shows the count
      const btnText = await deleteBtn.textContent()
      expect(btnText).toContain('Delete Selected')

      await takeScreenshot(page, 'email-preview-delete-selected-visible')

      // Uncheck to clean up
      await firstCheckbox.click()
      await page.waitForTimeout(500)

      // Button should disappear again
      await expect(deleteBtn).not.toBeVisible()

      await takeScreenshot(page, 'email-preview-delete-selected-hidden')
    } else {
      // No drafts — skip
      test.skip()
    }
  })
})

// ─── Admin Tests ──────────────────────────────────────────────────────

test.describe('Email Preview — Admin', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsAdmin(page)
    await page.goto('/dashboard/email-preview', { waitUntil: 'networkidle' })
    await page.waitForTimeout(2000)
  })

  test('8. No checkboxes visible — Admin cannot bulk delete', async ({ page }) => {
    // Admin should NOT see any checkboxes on draft cards or "Select all"
    const draftCheckboxes = page.locator('.w-\\[320px\\] input[type="checkbox"]')
    const checkboxCount = await draftCheckboxes.count()

    // Admin should have zero checkboxes regardless of draft count
    expect(checkboxCount).toBe(0)

    // The "Select all" label should also not appear for Admin
    const selectAllLabel = page.locator('label').filter({ hasText: 'Select all' })
    const selectAllVisible = await selectAllLabel.isVisible().catch(() => false)
    expect(selectAllVisible).toBe(false)

    // The "Delete Selected" button should not be visible
    const deleteBtn = page.getByRole('button', { name: /Delete Selected/i })
    const deleteBtnVisible = await deleteBtn.isVisible().catch(() => false)
    expect(deleteBtnVisible).toBe(false)

    await takeScreenshot(page, 'email-preview-admin-no-checkboxes')
  })
})
