import { test, expect } from '@playwright/test'
import { loginAsSuperAdmin, loginAsAdmin } from './helpers/auth'
import { takeScreenshot } from './helpers/screenshots'

test.describe.serial('Deals — Super Admin', () => {
  test('1. Kanban board loads with all 7 stage columns', async ({ page }) => {
    await loginAsSuperAdmin(page)
    await page.goto('/dashboard/deals', { waitUntil: 'networkidle' })

    // Wait for loading to finish (loading spinner says "Loading deals...")
    await page.waitForSelector('text=Loading deals...', { state: 'hidden', timeout: 30000 }).catch(() => {})

    // Verify the page title
    await expect(page.getByRole('heading', { name: 'Deals' })).toBeVisible({ timeout: 15000 })

    // Verify all 7 stage column headers are visible
    const stageNames = ['New Lead', 'Contacted', 'Qualified', 'Proposal', 'Negotiation', 'Won', 'Lost']
    for (const stageName of stageNames) {
      const stageHeader = page.locator('h3', { hasText: stageName }).first()
      await expect(stageHeader).toBeVisible({ timeout: 15000 })
    }

    await takeScreenshot(page, 'deals_kanban_stages')
  })

  test('2. Deal stats summary is visible with key metrics', async ({ page }) => {
    await loginAsSuperAdmin(page)
    await page.goto('/dashboard/deals', { waitUntil: 'networkidle' })
    await page.waitForSelector('text=Loading deals...', { state: 'hidden', timeout: 30000 }).catch(() => {})

    // Verify stats cards are present — look for the stat labels
    await expect(page.getByText('Pipeline Value')).toBeVisible({ timeout: 15000 })
    await expect(page.getByText('Total Deals')).toBeVisible({ timeout: 15000 })
    await expect(page.getByText('Win Rate')).toBeVisible({ timeout: 15000 })
    await expect(page.getByText('Avg Deal Size')).toBeVisible({ timeout: 15000 })
    await expect(page.getByText('Weighted Forecast')).toBeVisible({ timeout: 15000 })

    await takeScreenshot(page, 'deals_stats_summary')
  })

  test('3. Deal cards are visible in stage columns', async ({ page }) => {
    await loginAsSuperAdmin(page)
    await page.goto('/dashboard/deals', { waitUntil: 'networkidle' })
    await page.waitForSelector('text=Loading deals...', { state: 'hidden', timeout: 30000 }).catch(() => {})

    // Deal cards are rendered inside the kanban columns — they have a draggable attribute
    // and contain deal name, value, and probability
    const dealCards = page.locator('[draggable="true"]')
    const count = await dealCards.count()
    expect(count).toBeGreaterThan(0)

    // Verify at least one deal card contains a currency value (formatted as $X.XK or $X)
    const firstCard = dealCards.first()
    await expect(firstCard).toBeVisible()
    const cardText = await firstCard.textContent()
    expect(cardText).toBeTruthy()
    // Each deal card shows a percentage (probability)
    expect(cardText).toMatch(/\d+%/)

    await takeScreenshot(page, 'deals_cards_visible')
  })

  test('4. Deal detail view opens when clicking a deal card', async ({ page }) => {
    await loginAsSuperAdmin(page)
    await page.goto('/dashboard/deals', { waitUntil: 'networkidle' })
    await page.waitForSelector('text=Loading deals...', { state: 'hidden', timeout: 30000 }).catch(() => {})

    // Click the first deal card
    const dealCards = page.locator('[draggable="true"]')
    await expect(dealCards.first()).toBeVisible({ timeout: 15000 })

    // Get the deal name from the card before clicking
    const dealNameOnCard = await dealCards.first().locator('p.font-medium').first().textContent()

    await dealCards.first().click()

    // The detail drawer slides in from the right — it has a fixed panel with deal info
    // Wait for the drawer to appear (the deal name as an h2 heading)
    const drawerHeading = page.locator('h2.text-xl.font-bold')
    await expect(drawerHeading).toBeVisible({ timeout: 15000 })

    // Verify the drawer shows deal details
    await expect(page.getByText('Value', { exact: true })).toBeVisible()
    await expect(page.getByText('Probability', { exact: true })).toBeVisible()
    await expect(page.getByText('Stage', { exact: true }).first()).toBeVisible()

    // Verify Activity Timeline section is present
    await expect(page.getByText('Activity Timeline')).toBeVisible()

    // Verify Delete button is visible in the drawer
    await expect(page.getByText('Delete')).toBeVisible()

    await takeScreenshot(page, 'deals_detail_drawer')

    // Close the drawer by clicking the backdrop
    await page.locator('.fixed.inset-0.bg-black\\/50').click()

    // Verify the drawer closed
    await expect(drawerHeading).not.toBeVisible({ timeout: 5000 })
  })

  test('5. Create new deal via modal', async ({ page }) => {
    await loginAsSuperAdmin(page)
    await page.goto('/dashboard/deals', { waitUntil: 'networkidle' })
    await page.waitForSelector('text=Loading deals...', { state: 'hidden', timeout: 30000 }).catch(() => {})

    // Click "New Deal" button
    const newDealBtn = page.locator('button', { hasText: 'New Deal' })
    await expect(newDealBtn).toBeVisible({ timeout: 15000 })
    await newDealBtn.click()

    // Verify the create modal appears
    const modalHeading = page.locator('h2', { hasText: 'New Deal' })
    await expect(modalHeading).toBeVisible({ timeout: 10000 })

    await takeScreenshot(page, 'deals_create_modal_open')

    // Fill in the deal form
    const dealName = `E2E Test Deal ${Date.now()}`

    // Deal Name
    const nameInput = page.locator('input[placeholder*="Acme Corp"]')
    await nameInput.fill(dealName)

    // Value
    const valueInputs = page.locator('input[type="number"]')
    // The first number input in the modal is Value ($)
    await valueInputs.first().fill('15000')

    // Probability (second number input)
    await valueInputs.nth(1).fill('75')

    // Notes
    const notesTextarea = page.locator('textarea')
    await notesTextarea.fill('Created by Playwright E2E test')

    await takeScreenshot(page, 'deals_create_modal_filled')

    // Click "Create Deal" button
    const createBtn = page.locator('button', { hasText: 'Create Deal' })
    await expect(createBtn).toBeEnabled()
    await createBtn.click()

    // Wait for the modal to close (indicates success)
    await expect(modalHeading).not.toBeVisible({ timeout: 15000 })

    // Verify the new deal appears somewhere in the kanban board
    await page.waitForTimeout(2000) // Allow pipeline to refresh
    const newDealCard = page.getByText(dealName)
    await expect(newDealCard).toBeVisible({ timeout: 15000 })

    await takeScreenshot(page, 'deals_create_success')
  })
})

test.describe.serial('Deals — Admin', () => {
  test('6. Kanban board loads for admin with deals visible', async ({ page }) => {
    await loginAsAdmin(page)
    await page.goto('/dashboard/deals', { waitUntil: 'networkidle' })
    await page.waitForSelector('text=Loading deals...', { state: 'hidden', timeout: 30000 }).catch(() => {})

    // Verify the page title
    await expect(page.getByRole('heading', { name: 'Deals' })).toBeVisible({ timeout: 15000 })

    // Verify at least some stage columns are visible
    const stageHeaders = page.locator('h3.font-medium.text-sm')
    const stageCount = await stageHeaders.count()
    expect(stageCount).toBeGreaterThanOrEqual(7)

    // Verify deal cards are present
    const dealCards = page.locator('[draggable="true"]')
    const cardCount = await dealCards.count()
    expect(cardCount).toBeGreaterThan(0)

    // Verify stats section is visible
    await expect(page.getByText('Pipeline Value')).toBeVisible({ timeout: 15000 })
    await expect(page.getByText('Total Deals')).toBeVisible({ timeout: 15000 })

    await takeScreenshot(page, 'deals_admin_kanban')
  })
})
