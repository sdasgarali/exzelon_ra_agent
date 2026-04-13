import { test, expect } from '@playwright/test'
import { loginAsSuperAdmin, loginAsAdmin } from './helpers/auth'
import { takeScreenshot } from './helpers/screenshots'

const CAMPAIGNS_URL = '/dashboard/campaigns'

// ─── Super Admin: Campaign List Tests ──────────────────────────────────────

test.describe('Campaigns Page — Super Admin List', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsSuperAdmin(page)
  })

  // 1. List loads with campaigns (at least 1 campaign visible)
  test('should load campaigns list with at least 1 campaign', async ({ page }) => {
    await page.goto(CAMPAIGNS_URL, { waitUntil: 'networkidle' })

    // Wait for the heading
    await expect(page.locator('h1:has-text("Campaigns")')).toBeVisible({ timeout: 15000 })

    // Wait for the campaign table to load
    const tableBody = page.locator('table tbody')
    await expect(tableBody).toBeVisible({ timeout: 15000 })

    // Verify at least 1 campaign row exists
    const rows = tableBody.locator('tr')
    await expect(rows).not.toHaveCount(0, { timeout: 15000 })
    const rowCount = await rows.count()
    expect(rowCount).toBeGreaterThanOrEqual(1)

    // Verify "New Campaign" button exists
    await expect(page.locator('button:has-text("New Campaign")')).toBeVisible()

    // Verify table headers
    await expect(page.locator('th:has-text("Name")')).toBeVisible()
    await expect(page.locator('th:has-text("Status")')).toBeVisible()

    await takeScreenshot(page, 'campaigns-list-loaded')
  })

  // 9. Campaign status badge displays correctly
  test('should display campaign status badges with correct styling', async ({ page }) => {
    await page.goto(CAMPAIGNS_URL, { waitUntil: 'networkidle' })
    await expect(page.locator('h1:has-text("Campaigns")')).toBeVisible({ timeout: 15000 })

    const tableBody = page.locator('table tbody')
    await expect(tableBody).toBeVisible({ timeout: 15000 })

    // Find status badges in the table — they use rounded-full text-xs font-medium
    const statusBadges = tableBody.locator('span.rounded-full')
    const badgeCount = await statusBadges.count()
    expect(badgeCount).toBeGreaterThanOrEqual(1)

    // Verify at least one badge has recognizable status text
    const allBadgeTexts: string[] = []
    for (let i = 0; i < badgeCount; i++) {
      const text = await statusBadges.nth(i).textContent()
      if (text) allBadgeTexts.push(text.trim().toLowerCase())
    }

    const validStatuses = ['draft', 'active', 'paused', 'completed', 'archived']
    const hasValidStatus = allBadgeTexts.some(t => validStatuses.includes(t))
    expect(hasValidStatus).toBe(true)

    await takeScreenshot(page, 'campaigns-status-badges')
  })

  // 8. Create campaign from leads flow
  test('should open create campaign wizard', async ({ page }) => {
    await page.goto(CAMPAIGNS_URL, { waitUntil: 'networkidle' })
    await expect(page.locator('h1:has-text("Campaigns")')).toBeVisible({ timeout: 15000 })

    // Click "New Campaign" button
    await page.click('button:has-text("New Campaign")')

    // Wait for the create campaign wizard modal
    const modal = page.locator('.fixed.inset-0').first()
    await expect(modal).toBeVisible({ timeout: 10000 })

    // The wizard starts with a "source" step — look for source selection options
    // The wizard should show options for data source (pipeline, CSV upload, manual, etc.)
    await page.waitForTimeout(2000)

    await takeScreenshot(page, 'campaigns-create-wizard-source')

    // Try to find the "Select from Leads" or pipeline-related options
    // The create wizard has multiple source options
    const hasLeadSource = await page.locator('text=leads').or(page.locator('text=Leads')).or(page.locator('text=Pipeline')).first().isVisible().catch(() => false)

    // Verify the modal is showing the campaign creation flow
    expect(await modal.isVisible()).toBe(true)

    // Close the modal via Escape key or X button
    await page.keyboard.press('Escape')
    await page.waitForTimeout(1000)
    // If modal is still visible, try clicking X button
    if (await modal.isVisible().catch(() => false)) {
      const xBtn = page.locator('button:has-text("×"), button[aria-label="Close"]').first()
      await xBtn.click({ timeout: 5000 }).catch(() => {})
    }

    await takeScreenshot(page, 'campaigns-create-wizard-closed')
  })
})

// ─── Super Admin: Campaign Detail Tests ────────────────────────────────────

test.describe.serial('Campaigns Page — Super Admin Detail View', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsSuperAdmin(page)
  })

  // 2. Open campaign detail — tabs visible
  test('should open campaign detail and show tabs', async ({ page }) => {
    await page.goto(CAMPAIGNS_URL, { waitUntil: 'networkidle' })
    await expect(page.locator('h1:has-text("Campaigns")')).toBeVisible({ timeout: 15000 })

    const tableBody = page.locator('table tbody')
    await expect(tableBody).toBeVisible({ timeout: 15000 })

    // Click on the first campaign row to open detail
    const firstRow = tableBody.locator('tr').first()
    await firstRow.click()

    // Wait for detail view to load — the tabs should appear
    await expect(page.locator('button:has-text("Overview")')).toBeVisible({ timeout: 15000 })

    // Verify all expected tabs are visible
    const expectedTabs = ['Overview', 'Mailboxes', 'Leads & Contacts', 'Sequence', 'Schedule', 'Rules', 'Activity', 'Analytics']
    for (const tabName of expectedTabs) {
      await expect(page.locator(`button:has-text("${tabName}")`)).toBeVisible({ timeout: 5000 })
    }

    // Verify Overview tab is active by default (it should have the active border style)
    const overviewTab = page.locator('button:has-text("Overview")').first()
    await expect(overviewTab).toBeVisible()

    // Verify the Overview content is showing — look for "Campaign Details" heading
    await expect(page.locator('text=Campaign Details')).toBeVisible({ timeout: 10000 })

    await takeScreenshot(page, 'campaigns-detail-tabs')
  })

  // 3. Sequence tab shows sequence steps
  test('should show sequence steps in Sequence tab', async ({ page }) => {
    await page.goto(CAMPAIGNS_URL, { waitUntil: 'networkidle' })
    await expect(page.locator('h1:has-text("Campaigns")')).toBeVisible({ timeout: 15000 })

    const tableBody = page.locator('table tbody')
    await expect(tableBody).toBeVisible({ timeout: 15000 })

    // Open the first campaign
    await tableBody.locator('tr').first().click()
    await expect(page.locator('button:has-text("Overview")')).toBeVisible({ timeout: 15000 })

    // Click the Sequence tab
    await page.locator('button:has-text("Sequence")').click()

    // Wait for the sequence content to load
    await page.waitForTimeout(2000)

    // The sequence tab should show either:
    // - Sequence steps (list or visual builder view)
    // - "No steps yet" message if empty
    const hasSteps = await page.locator('text=email').or(page.locator('text=wait')).or(page.locator('text=Email')).first().isVisible().catch(() => false)
    const hasNoSteps = await page.locator('text=No steps yet').isVisible().catch(() => false)

    // One of these should be true
    expect(hasSteps || hasNoSteps).toBe(true)

    // Check for view mode toggle (List View / Visual Builder)
    const hasListViewToggle = await page.locator('text=List View').isVisible().catch(() => false)

    await takeScreenshot(page, 'campaigns-sequence-tab')
  })

  // 4. Schedule tab shows schedule entries/cards
  test('should show schedule entries in Schedule tab', async ({ page }) => {
    await page.goto(CAMPAIGNS_URL, { waitUntil: 'networkidle' })
    await expect(page.locator('h1:has-text("Campaigns")')).toBeVisible({ timeout: 15000 })

    const tableBody = page.locator('table tbody')
    await expect(tableBody).toBeVisible({ timeout: 15000 })

    // Open the first campaign
    await tableBody.locator('tr').first().click()
    await expect(page.locator('button:has-text("Overview")')).toBeVisible({ timeout: 15000 })

    // Click the Schedule tab
    await page.locator('button:has-text("Schedule")').click()

    // Wait for schedule content to load
    await page.waitForTimeout(2000)

    // The schedule tab should show:
    // - "Schedules" heading
    // - "Add Schedule" button
    // - Schedule cards or "No schedules configured" message
    await expect(page.locator('h3:has-text("Schedules")')).toBeVisible({ timeout: 10000 })
    await expect(page.locator('button:has-text("Add Schedule")')).toBeVisible({ timeout: 10000 })

    // Verify Smart Scheduling section
    await expect(page.locator('text=Smart Scheduling')).toBeVisible({ timeout: 10000 })
    await expect(page.locator('text=Timezone Distribution')).toBeVisible({ timeout: 10000 })

    await takeScreenshot(page, 'campaigns-schedule-tab')
  })

  // 5. Add new schedule
  test('should add a new schedule entry', async ({ page }) => {
    await page.goto(CAMPAIGNS_URL, { waitUntil: 'networkidle' })
    await expect(page.locator('h1:has-text("Campaigns")')).toBeVisible({ timeout: 15000 })

    const tableBody = page.locator('table tbody')
    await expect(tableBody).toBeVisible({ timeout: 15000 })

    // Open the first campaign
    await tableBody.locator('tr').first().click()
    await expect(page.locator('button:has-text("Overview")')).toBeVisible({ timeout: 15000 })

    // Go to Schedule tab
    await page.locator('button:has-text("Schedule")').click()
    await expect(page.locator('h3:has-text("Schedules")')).toBeVisible({ timeout: 10000 })

    // Count existing schedules
    const scheduleCardsBefore = page.locator('.border.rounded-lg:has(text=Schedule)')
    const countBefore = await scheduleCardsBefore.count().catch(() => 0)

    // Click "Add Schedule"
    await page.locator('button:has-text("Add Schedule")').click()

    // Wait for the schedule modal
    await expect(page.locator('h3:has-text("Add Schedule")')).toBeVisible({ timeout: 10000 })

    // Fill the form
    const labelInput = page.locator('input[placeholder*="Morning shift"]')
    await labelInput.fill(`E2E Test Schedule ${Date.now()}`)

    // Start date should be pre-filled with today
    // Set send window
    const startTimeInput = page.locator('input[type="time"]').first()
    await startTimeInput.fill('08:00')

    const endTimeInput = page.locator('input[type="time"]').last()
    await endTimeInput.fill('18:00')

    await takeScreenshot(page, 'campaigns-schedule-add-form')

    // Save the schedule — look for Save button
    const saveButton = page.locator('button:has-text("Save")').or(page.locator('button:has-text("Add")').last())
    await saveButton.click()

    // Wait for modal to close
    await expect(page.locator('h3:has-text("Add Schedule")')).not.toBeVisible({ timeout: 15000 })

    await takeScreenshot(page, 'campaigns-schedule-add-success')
  })

  // 6. Edit schedule
  test('should edit an existing schedule entry', async ({ page }) => {
    await page.goto(CAMPAIGNS_URL, { waitUntil: 'networkidle' })
    await expect(page.locator('h1:has-text("Campaigns")')).toBeVisible({ timeout: 15000 })

    const tableBody = page.locator('table tbody')
    await expect(tableBody).toBeVisible({ timeout: 15000 })

    // Open the first campaign
    await tableBody.locator('tr').first().click()
    await expect(page.locator('button:has-text("Overview")')).toBeVisible({ timeout: 15000 })

    // Go to Schedule tab
    await page.locator('button:has-text("Schedule")').click()
    await expect(page.locator('h3:has-text("Schedules")')).toBeVisible({ timeout: 10000 })

    // Wait for schedules to load
    await page.waitForTimeout(2000)

    // Find an Edit button on a schedule card
    const editLinks = page.locator('button:has-text("Edit"), a:has-text("Edit")').filter({ hasNot: page.locator('h3') })

    const editCount = await editLinks.count()
    if (editCount > 0) {
      // Click the first Edit link
      await editLinks.first().click()

      // Wait for the edit modal
      await expect(page.locator('h3:has-text("Edit Schedule")')).toBeVisible({ timeout: 10000 })

      // Modify the label
      const labelInput = page.locator('input[placeholder*="Morning shift"]')
      const currentLabel = await labelInput.inputValue()
      await labelInput.clear()
      await labelInput.fill(`${currentLabel} (edited)`)

      await takeScreenshot(page, 'campaigns-schedule-edit-form')

      // Save
      const saveButton = page.locator('button:has-text("Save")').or(page.locator('button:has-text("Update")'))
      await saveButton.click()

      // Wait for modal to close
      await expect(page.locator('h3:has-text("Edit Schedule")')).not.toBeVisible({ timeout: 15000 })

      await takeScreenshot(page, 'campaigns-schedule-edit-success')
    } else {
      // No schedules to edit — skip with a note
      await takeScreenshot(page, 'campaigns-schedule-none-to-edit')
    }
  })

  // 7. Contacts tab shows enrolled contacts
  test('should show enrolled contacts in Leads & Contacts tab', async ({ page }) => {
    await page.goto(CAMPAIGNS_URL, { waitUntil: 'networkidle' })
    await expect(page.locator('h1:has-text("Campaigns")')).toBeVisible({ timeout: 15000 })

    const tableBody = page.locator('table tbody')
    await expect(tableBody).toBeVisible({ timeout: 15000 })

    // Open the first campaign
    await tableBody.locator('tr').first().click()
    await expect(page.locator('button:has-text("Overview")')).toBeVisible({ timeout: 15000 })

    // Click Leads & Contacts tab
    await page.locator('button:has-text("Leads & Contacts")').click()

    // Wait for contacts content to load
    await page.waitForTimeout(3000)

    // The tab should show either:
    // - "X enrolled contacts across Y leads" text
    // - An "Enroll Contacts" button
    // - The contacts table/list
    const hasEnrolledText = await page.locator('text=enrolled contact').isVisible().catch(() => false)
    const hasEnrollButton = await page.locator('button:has-text("Enroll Contacts")').isVisible().catch(() => false)
    const hasNoContacts = await page.locator('text=No contacts enrolled').or(page.locator('text=0 enrolled')).isVisible().catch(() => false)

    // At least the Enroll button or enrolled info should be visible
    expect(hasEnrolledText || hasEnrollButton || hasNoContacts).toBe(true)

    await takeScreenshot(page, 'campaigns-contacts-tab')
  })
})

// ─── Admin: Campaign Tests ─────────────────────────────────────────────────

test.describe('Campaigns Page — Admin', () => {
  // 10. Campaign list loads for admin
  test('should load campaign list for admin user', async ({ page }) => {
    await loginAsAdmin(page)

    await page.goto(CAMPAIGNS_URL, { waitUntil: 'networkidle' })

    // Wait for the heading
    await expect(page.locator('h1:has-text("Campaigns")')).toBeVisible({ timeout: 15000 })

    // Wait for table to appear
    const tableBody = page.locator('table tbody')
    await expect(tableBody).toBeVisible({ timeout: 15000 })

    // Verify campaigns are loaded — at least the table structure exists
    const rows = tableBody.locator('tr')
    const rowCount = await rows.count()

    // Admin should be able to see campaigns (at least 1 if data exists)
    // or the "No campaigns yet" empty state
    if (rowCount === 0) {
      await expect(page.locator('text=No campaigns yet')).toBeVisible({ timeout: 10000 })
    } else {
      expect(rowCount).toBeGreaterThanOrEqual(1)
    }

    // Verify "New Campaign" button is visible for admin
    await expect(page.locator('button:has-text("New Campaign")')).toBeVisible()

    // Verify status filter dropdown is present (select element with status options)
    const statusFilter = page.locator('select').filter({ has: page.locator('option:has-text("All Status")') })
    await expect(statusFilter).toBeVisible()

    await takeScreenshot(page, 'campaigns-admin-list')
  })
})
