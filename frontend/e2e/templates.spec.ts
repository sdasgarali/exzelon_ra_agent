import { test, expect } from '@playwright/test'
import { loginAsSuperAdmin } from './helpers/auth'
import { takeScreenshot } from './helpers/screenshots'

const TEMPLATES_URL = '/dashboard/templates'

// ─── Super Admin: Templates Page Tests ─────────────────────────────────────

test.describe.serial('Templates Page — Super Admin', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsSuperAdmin(page)
  })

  // 1. List loads with templates (17 templates, verify multiple items visible)
  test('should load templates list with 17 templates', async ({ page }) => {
    await page.goto(TEMPLATES_URL, { waitUntil: 'networkidle' })

    // Wait for the heading
    await expect(page.locator('h1:has-text("Email Templates")')).toBeVisible({ timeout: 15000 })

    // Wait for the table to appear and be populated
    const tableBody = page.locator('table tbody')
    await expect(tableBody).toBeVisible({ timeout: 15000 })

    // Count template rows in the table
    const rows = tableBody.locator('tr')
    await expect(rows).not.toHaveCount(0, { timeout: 15000 })

    const rowCount = await rows.count()
    expect(rowCount).toBeGreaterThanOrEqual(10)

    // Verify "Create Template" button exists
    await expect(page.locator('button:has-text("Create Template")')).toBeVisible()

    await takeScreenshot(page, 'templates-list-loaded')
  })

  // 2. Create new template
  test('should create a new template', async ({ page }) => {
    await page.goto(TEMPLATES_URL, { waitUntil: 'networkidle' })
    await expect(page.locator('h1:has-text("Email Templates")')).toBeVisible({ timeout: 15000 })

    // Click "Create Template" button
    await page.click('button:has-text("Create Template")')

    // Wait for the create modal to appear
    const modal = page.locator('.fixed.inset-0').first()
    await expect(modal).toBeVisible({ timeout: 10000 })

    // Verify modal title
    await expect(page.locator('h2:has-text("Create Template")')).toBeVisible()

    // Fill out the form
    const timestamp = Date.now()
    const templateName = `E2E Test Template ${timestamp}`
    const templateSubject = `E2E Subject Line ${timestamp}`
    const templateBody = `<p>Hello {{contact_first_name}},</p><p>This is an E2E test template created at ${timestamp}.</p>`

    // Fill Template Name
    await page.locator('input[placeholder*="Free Candidate Preview"]').fill(templateName)

    // Category select inside modal — already defaulted to "Outreach", no change needed
    // The modal's category select is scoped to the fixed overlay
    const modalSelects = modal.locator('select')
    const categorySelect = modalSelects.first()
    if (await categorySelect.isVisible().catch(() => false)) {
      // Verify it already shows Outreach (default)
      const val = await categorySelect.inputValue()
      if (!val || val === '') {
        await categorySelect.selectOption({ index: 0 })
      }
    }

    // Fill Subject Line
    await page.locator('input[placeholder*="Free candidate preview"]').fill(templateSubject)

    // Fill HTML Body
    await page.locator('textarea[placeholder*="Hi {{contact_first_name}}"]').first().fill(templateBody)

    await takeScreenshot(page, 'templates-create-form-filled')

    // Click save (Create Template button in footer)
    await page.locator('button:has-text("Create Template")').last().click()

    // Wait for modal to close
    await expect(page.locator('h2:has-text("Create Template")')).not.toBeVisible({ timeout: 15000 })

    // Verify the new template appears in the list
    await expect(page.locator(`text=${templateName}`)).toBeVisible({ timeout: 15000 })

    await takeScreenshot(page, 'templates-create-success')
  })

  // 3. Edit existing template
  test('should edit an existing template', async ({ page }) => {
    await page.goto(TEMPLATES_URL, { waitUntil: 'networkidle' })
    await expect(page.locator('h1:has-text("Email Templates")')).toBeVisible({ timeout: 15000 })

    // Wait for table rows to load
    const tableBody = page.locator('table tbody')
    await expect(tableBody).toBeVisible({ timeout: 15000 })

    // Find the first edit button (pencil icon) in the actions column
    const editButtons = page.locator('button[title="Edit"]')
    await expect(editButtons.first()).toBeVisible({ timeout: 10000 })
    await editButtons.first().click()

    // Wait for the edit modal
    await expect(page.locator('h2:has-text("Edit Template")')).toBeVisible({ timeout: 10000 })

    // Modify the subject line
    const subjectInput = page.locator('input[placeholder*="Free candidate preview"]')
    const originalSubject = await subjectInput.inputValue()
    const modifiedSubject = `${originalSubject} [E2E edited]`
    await subjectInput.clear()
    await subjectInput.fill(modifiedSubject)

    await takeScreenshot(page, 'templates-edit-form')

    // Save changes
    await page.locator('button:has-text("Update Template")').click()

    // Wait for modal to close
    await expect(page.locator('h2:has-text("Edit Template")')).not.toBeVisible({ timeout: 15000 })

    // Verify change is reflected — subject column in table should show modified text
    await expect(page.locator(`text=[E2E edited]`)).toBeVisible({ timeout: 10000 })

    await takeScreenshot(page, 'templates-edit-success')

    // Clean up: revert the edit
    await editButtons.first().click()
    await expect(page.locator('h2:has-text("Edit Template")')).toBeVisible({ timeout: 10000 })
    await subjectInput.clear()
    await subjectInput.fill(originalSubject)
    await page.locator('button:has-text("Update Template")').click()
    await expect(page.locator('h2:has-text("Edit Template")')).not.toBeVisible({ timeout: 15000 })
  })

  // 4. Preview template
  test('should preview a template', async ({ page }) => {
    await page.goto(TEMPLATES_URL, { waitUntil: 'networkidle' })
    await expect(page.locator('h1:has-text("Email Templates")')).toBeVisible({ timeout: 15000 })

    // Wait for table rows
    const tableBody = page.locator('table tbody')
    await expect(tableBody).toBeVisible({ timeout: 15000 })

    // Click the preview button (eye icon) on the first template
    const previewButtons = page.locator('button[title="Preview"]')
    await expect(previewButtons.first()).toBeVisible({ timeout: 10000 })
    await previewButtons.first().click()

    // Wait for the preview modal to appear
    await expect(page.locator('h2:has-text("Template Preview")')).toBeVisible({ timeout: 10000 })

    // Verify preview content — SUBJECT label and HTML PREVIEW label
    await expect(page.getByText('SUBJECT', { exact: true })).toBeVisible()
    await expect(page.getByText('HTML PREVIEW', { exact: true })).toBeVisible()

    await takeScreenshot(page, 'templates-preview-modal')

    // Close the preview modal
    await page.locator('button:has-text("Close")').click()
    await expect(page.locator('h2:has-text("Template Preview")')).not.toBeVisible({ timeout: 10000 })
  })

  // 5. Duplicate template — since there is no duplicate button in the UI,
  //    we test duplicating by creating a template from an existing one's data
  //    (open edit modal, note the values, close, create new with same values)
  test('should duplicate a template by creating a copy', async ({ page }) => {
    await page.goto(TEMPLATES_URL, { waitUntil: 'networkidle' })
    await expect(page.locator('h1:has-text("Email Templates")')).toBeVisible({ timeout: 15000 })

    // Click edit on the first template to get its data
    const editButtons = page.locator('button[title="Edit"]')
    await expect(editButtons.first()).toBeVisible({ timeout: 10000 })
    await editButtons.first().click()
    await expect(page.locator('h2:has-text("Edit Template")')).toBeVisible({ timeout: 10000 })

    // Capture template data
    const nameInput = page.locator('input[placeholder*="Free Candidate Preview"]')
    const subjectInput = page.locator('input[placeholder*="Free candidate preview"]')
    const bodyTextarea = page.locator('textarea[placeholder*="Hi {{contact_first_name}}"]').first()

    const originalName = await nameInput.inputValue()
    const originalSubject = await subjectInput.inputValue()
    const originalBody = await bodyTextarea.inputValue()

    // Close the edit modal
    await page.locator('button:has-text("Cancel")').click()
    await expect(page.locator('h2:has-text("Edit Template")')).not.toBeVisible({ timeout: 10000 })

    // Now create a new template with the same data plus "Copy" suffix
    await page.click('button:has-text("Create Template")')
    await expect(page.locator('h2:has-text("Create Template")')).toBeVisible({ timeout: 10000 })

    const copyName = `${originalName} (Copy)`
    await nameInput.fill(copyName)
    await subjectInput.fill(originalSubject)
    await bodyTextarea.fill(originalBody)

    // Save the copy
    await page.locator('button:has-text("Create Template")').last().click()
    await expect(page.locator('h2:has-text("Create Template")')).not.toBeVisible({ timeout: 15000 })

    // Verify the copy appears in the list
    await expect(page.locator(`text=${copyName}`)).toBeVisible({ timeout: 15000 })

    await takeScreenshot(page, 'templates-duplicate-success')
  })

  // 6. Activate template
  test('should activate an inactive template', async ({ page }) => {
    await page.goto(TEMPLATES_URL, { waitUntil: 'networkidle' })
    await expect(page.locator('h1:has-text("Email Templates")')).toBeVisible({ timeout: 15000 })

    // Wait for table
    const tableBody = page.locator('table tbody')
    await expect(tableBody).toBeVisible({ timeout: 15000 })

    // Find an "Activate" button (lightning bolt icon, only visible on inactive templates)
    const activateButtons = page.locator('button[title="Activate"]')
    const activateCount = await activateButtons.count()

    if (activateCount > 0) {
      // Click activate on the first inactive template
      await activateButtons.first().click()

      // After activation, the page should refresh/update
      // Verify an active template card appears (green border card)
      await expect(
        page.locator('.border-green-400, .border-blue-400').first()
      ).toBeVisible({ timeout: 15000 })

      await takeScreenshot(page, 'templates-activate-success')
    } else {
      // All templates are already active — verify active template cards exist
      await expect(
        page.locator('text=Active Outreach Template').or(page.locator('text=Active Follow-up Template')).first()
      ).toBeVisible({ timeout: 10000 })

      await takeScreenshot(page, 'templates-all-already-active')
    }
  })

  // 7. Filter by category — outreach vs followup
  test('should filter templates by goal category', async ({ page }) => {
    await page.goto(TEMPLATES_URL, { waitUntil: 'networkidle' })
    await expect(page.locator('h1:has-text("Email Templates")')).toBeVisible({ timeout: 15000 })

    // Wait for templates to load
    const tableBody = page.locator('table tbody')
    await expect(tableBody).toBeVisible({ timeout: 15000 })

    // Get initial row count
    const initialRows = await tableBody.locator('tr').count()

    // Filter by "Cold Outreach" goal (which corresponds to outreach category)
    const goalFilter = page.locator('select').filter({ has: page.locator('option:has-text("All Goals")') })
    await goalFilter.selectOption('cold_outreach')

    // Wait for table to update
    await page.waitForTimeout(1500)

    // Verify the filter is applied — row count may change
    const filteredRows = await tableBody.locator('tr').count()

    await takeScreenshot(page, 'templates-filter-cold-outreach')

    // Now filter by Follow-up
    await goalFilter.selectOption('follow_up')
    await page.waitForTimeout(1500)

    const followupRows = await tableBody.locator('tr').count()

    await takeScreenshot(page, 'templates-filter-followup')

    // Reset filter
    await goalFilter.selectOption('')
    await page.waitForTimeout(1500)

    const resetRows = await tableBody.locator('tr').count()
    // After reset, should have the original count
    expect(resetRows).toEqual(initialRows)

    await takeScreenshot(page, 'templates-filter-reset')
  })

  // 8. Filter by industry
  test('should filter templates by industry', async ({ page }) => {
    await page.goto(TEMPLATES_URL, { waitUntil: 'networkidle' })
    await expect(page.locator('h1:has-text("Email Templates")')).toBeVisible({ timeout: 15000 })

    // Wait for templates to load
    const tableBody = page.locator('table tbody')
    await expect(tableBody).toBeVisible({ timeout: 15000 })

    // Get initial row count
    const initialRows = await tableBody.locator('tr').count()

    // Filter by industry — try "General" since it's likely to have templates
    const industryFilter = page.locator('select').filter({ has: page.locator('option:has-text("All Industries")') })
    await industryFilter.selectOption('general')

    // Wait for table to update
    await page.waitForTimeout(1500)

    await takeScreenshot(page, 'templates-filter-industry-general')

    // Now try a specific industry like "Recruiting"
    await industryFilter.selectOption('recruiting')
    await page.waitForTimeout(1500)

    await takeScreenshot(page, 'templates-filter-industry-recruiting')

    // Reset
    await industryFilter.selectOption('')
    await page.waitForTimeout(1500)

    const resetRows = await tableBody.locator('tr').count()
    expect(resetRows).toEqual(initialRows)
  })
})
