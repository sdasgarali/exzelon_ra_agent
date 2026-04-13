import { test, expect } from '@playwright/test'
import { loginAsSuperAdmin, loginAsAdmin, getAdminEmail } from './helpers/auth'
import { takeScreenshot } from './helpers/screenshots'

test.describe.serial('User Management — Super Admin', () => {
  // 0. Ensure admin@exzelon.com is set to 'admin' role (repair from previous test runs)
  test('0. Ensure admin user has admin role (setup)', async ({ page }) => {
    await loginAsSuperAdmin(page)
    await page.goto('/dashboard/users', { waitUntil: 'networkidle' })
    await expect(page.getByRole('heading', { name: 'User Management' })).toBeVisible({ timeout: 15000 })

    const table = page.locator('table')
    await expect(table).toBeVisible({ timeout: 15000 })

    // Find the admin user row by email
    const adminEmail = getAdminEmail()
    const adminRow = table.locator('tbody tr').filter({ hasText: adminEmail })
    const adminRowCount = await adminRow.count()

    if (adminRowCount > 0) {
      // Check if the role badge already says 'admin'
      const roleBadge = adminRow.first().locator('span.rounded-full').first()
      const roleText = (await roleBadge.textContent())?.trim().toLowerCase() || ''

      if (roleText !== 'admin') {
        // Need to fix the role — click Edit on this row
        const editBtn = adminRow.first().locator('button', { hasText: 'Edit' })
        if (await editBtn.count() > 0) {
          await editBtn.first().click()
          const modal = page.locator('.fixed.inset-0').filter({ has: page.getByText('Edit User') })
          await expect(modal).toBeVisible({ timeout: 10000 })
          const roleSelect = modal.locator('select')
          await roleSelect.selectOption('admin')
          const updateBtn = modal.getByRole('button', { name: /^Update$/i })
          await updateBtn.click()
          await expect(modal).not.toBeVisible({ timeout: 15000 })
        }
      }
    }
  })

  test('1. User list loads with all users visible in table', async ({ page }) => {
    await loginAsSuperAdmin(page)

    // Navigate to User Management page
    await page.goto('/dashboard/users', { waitUntil: 'networkidle' })

    // Verify page heading
    await expect(page.getByRole('heading', { name: 'User Management' })).toBeVisible({ timeout: 15000 })

    // Wait for the table to render (loading spinner should disappear)
    const table = page.locator('table')
    await expect(table).toBeVisible({ timeout: 15000 })

    // Verify table headers are present
    await expect(table.locator('th', { hasText: 'Name' })).toBeVisible()
    await expect(table.locator('th', { hasText: 'Email' })).toBeVisible()
    await expect(table.locator('th', { hasText: 'Role' })).toBeVisible()
    await expect(table.locator('th', { hasText: 'Status' })).toBeVisible()

    // Verify at least one data row exists (not the loading or empty state)
    const dataRows = table.locator('tbody tr').filter({ hasNot: page.locator('text=Loading users') })
    const rowCount = await dataRows.count()
    expect(rowCount).toBeGreaterThanOrEqual(1)

    // Verify "No users found." is NOT shown
    await expect(page.getByText('No users found.')).not.toBeVisible()

    await takeScreenshot(page, 'users_list_sa')
  })

  test('2. Create new user via Add User modal', async ({ page }) => {
    await loginAsSuperAdmin(page)

    await page.goto('/dashboard/users', { waitUntil: 'networkidle' })
    await expect(page.getByRole('heading', { name: 'User Management' })).toBeVisible({ timeout: 15000 })

    // Wait for the table to fully load (wait for a data row)
    const table = page.locator('table')
    await expect(table).toBeVisible({ timeout: 15000 })
    await page.waitForTimeout(2000) // Allow table data to settle

    // Click "Add User" button
    const addUserBtn = page.getByRole('button', { name: /add user/i })
    await expect(addUserBtn).toBeVisible({ timeout: 10000 })
    await addUserBtn.click()

    // Verify the modal opens with "Create User" title
    const modal = page.locator('.fixed.inset-0').filter({ has: page.getByText('Create User') })
    await expect(modal).toBeVisible({ timeout: 10000 })

    // Generate a unique test email using timestamp
    const timestamp = Date.now()
    const testEmail = `e2e.test.user.${timestamp}@test.com`
    const testName = `E2E Test User ${timestamp}`
    const testPassword = 'TestPass123!@#'

    // Fill out the form
    // Email field
    const emailInput = modal.locator('input[type="email"]')
    await emailInput.fill(testEmail)

    // Password field
    const passwordInput = modal.locator('input[type="password"]')
    await passwordInput.fill(testPassword)

    // Full Name field
    const nameInput = modal.locator('input[type="text"]').first()
    await nameInput.fill(testName)

    // Role select — choose 'operator'
    const roleSelect = modal.locator('select')
    await roleSelect.selectOption('operator')

    await takeScreenshot(page, 'users_create_form_filled')

    // Submit the form by clicking the "Create" button inside the modal
    const createBtn = modal.getByRole('button', { name: /^Create$/i })
    await createBtn.click()

    // Wait for success message to appear
    const successAlert = page.locator('.bg-green-50, [class*="bg-green"]').filter({ hasText: /created successfully/i })
    await expect(successAlert).toBeVisible({ timeout: 15000 })

    // Verify the modal closed
    await expect(modal).not.toBeVisible({ timeout: 5000 })

    // Verify the new user appears in the table
    await expect(page.getByRole('cell', { name: testEmail })).toBeVisible({ timeout: 10000 })

    await takeScreenshot(page, 'users_create_success')
  })

  test('3. Change user role via Edit modal', async ({ page }) => {
    await loginAsSuperAdmin(page)

    await page.goto('/dashboard/users', { waitUntil: 'networkidle' })
    await expect(page.getByRole('heading', { name: 'User Management' })).toBeVisible({ timeout: 15000 })

    // Wait for table data to load
    const table = page.locator('table')
    await expect(table).toBeVisible({ timeout: 15000 })

    // Find a user row that has an Edit button and is NOT the admin user or a super_admin
    // Target E2E test users (created by test 2) or any non-admin, non-SA user
    const adminEmail = getAdminEmail()
    const allRows = table.locator('tbody tr')
    const rowCount = await allRows.count()
    let targetEditBtn = null
    let targetRowIndex = -1

    for (let i = 0; i < rowCount; i++) {
      const row = allRows.nth(i)
      const rowText = await row.textContent() || ''
      const hasEdit = await row.locator('button', { hasText: 'Edit' }).count()
      // Skip admin@exzelon.com and super_admin rows
      if (hasEdit > 0 && !rowText.includes(adminEmail) && !rowText.includes('super admin')) {
        targetEditBtn = row.locator('button', { hasText: 'Edit' })
        targetRowIndex = i
        break
      }
    }

    expect(targetEditBtn).not.toBeNull()

    // Click the target Edit button
    await targetEditBtn!.click()

    // Verify the Edit User modal opens
    const modal = page.locator('.fixed.inset-0').filter({ has: page.getByText('Edit User') })
    await expect(modal).toBeVisible({ timeout: 10000 })

    // Get current role value and change it
    const roleSelect = modal.locator('select')
    const currentRole = await roleSelect.inputValue()

    // Pick a different role to demonstrate the change
    const newRole = currentRole === 'operator' ? 'viewer' : 'operator'
    await roleSelect.selectOption(newRole)

    await takeScreenshot(page, 'users_edit_role_change')

    // Click the "Update" button
    const updateBtn = modal.getByRole('button', { name: /^Update$/i })
    await updateBtn.click()

    // Wait for success message
    const successAlert = page.locator('.bg-green-50, [class*="bg-green"]').filter({ hasText: /updated successfully/i })
    await expect(successAlert).toBeVisible({ timeout: 15000 })

    // Verify modal closed
    await expect(modal).not.toBeVisible({ timeout: 5000 })

    await takeScreenshot(page, 'users_edit_role_success')

    // Revert the role change — find the same user row again (table may have re-rendered)
    const revertRow = allRows.nth(targetRowIndex)
    const revertEditBtn = revertRow.locator('button', { hasText: 'Edit' })
    if (await revertEditBtn.count() > 0) {
      await revertEditBtn.click()
      const revertModal = page.locator('.fixed.inset-0').filter({ has: page.getByText('Edit User') })
      await expect(revertModal).toBeVisible({ timeout: 10000 })
      const revertSelect = revertModal.locator('select')
      await revertSelect.selectOption(currentRole)
      const revertBtn = revertModal.getByRole('button', { name: /^Update$/i })
      await revertBtn.click()
      await expect(revertModal).not.toBeVisible({ timeout: 15000 })
    }
  })

  test('4. User roles displayed as colored badges in the table', async ({ page }) => {
    await loginAsSuperAdmin(page)

    await page.goto('/dashboard/users', { waitUntil: 'networkidle' })
    await expect(page.getByRole('heading', { name: 'User Management' })).toBeVisible({ timeout: 15000 })

    const table = page.locator('table')
    await expect(table).toBeVisible({ timeout: 15000 })

    // Wait for data rows to load
    const dataRows = table.locator('tbody tr')
    await expect(dataRows.first()).toBeVisible({ timeout: 15000 })

    // Role badges use the class pattern: inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium
    const roleBadges = table.locator('tbody span.rounded-full.text-xs.font-medium')
    const badgeCount = await roleBadges.count()
    expect(badgeCount).toBeGreaterThanOrEqual(1)

    // Verify badges contain valid role text (role.replace('_', ' '))
    const validRoles = ['super admin', 'admin', 'operator', 'viewer']
    for (let i = 0; i < Math.min(badgeCount, 5); i++) {
      const text = await roleBadges.nth(i).textContent()
      const normalizedText = text?.trim().toLowerCase() || ''
      // Check if badge text matches one of the valid roles
      const isValidRole = validRoles.some((role) => normalizedText === role)
      // Also match status badges (Active/Inactive) which use the same class
      const isStatusBadge = normalizedText === 'active' || normalizedText === 'inactive'
      expect(isValidRole || isStatusBadge).toBeTruthy()
    }

    // Verify role-specific badge color classes exist in the DOM
    // super_admin: bg-red-100
    // admin: bg-purple-100
    // operator: bg-blue-100
    // viewer: bg-gray-100
    const superAdminBadge = table.locator('span.rounded-full', { hasText: 'super admin' })
    if (await superAdminBadge.count() > 0) {
      const classes = await superAdminBadge.first().getAttribute('class')
      expect(classes).toContain('bg-red-')
    }

    const adminBadge = table.locator('span.rounded-full', { hasText: /^admin$/i })
    if (await adminBadge.count() > 0) {
      const classes = await adminBadge.first().getAttribute('class')
      expect(classes).toContain('bg-purple-')
    }

    await takeScreenshot(page, 'users_role_badges')
  })
})

test.describe.serial('User Management — Admin', () => {
  test('5. User list loads for admin user', async ({ page }) => {
    await loginAsAdmin(page)

    await page.goto('/dashboard/users', { waitUntil: 'networkidle' })

    // Admin should be able to access the page
    await expect(page.getByRole('heading', { name: 'User Management' })).toBeVisible({ timeout: 30000 })

    // Table should render with data
    const table = page.locator('table')
    await expect(table).toBeVisible({ timeout: 15000 })

    // Verify at least one row of data exists
    const dataRows = table.locator('tbody tr').filter({ hasNot: page.locator('text=Loading users') })
    const rowCount = await dataRows.count()
    expect(rowCount).toBeGreaterThanOrEqual(1)

    // Verify the "Add User" button is visible (admins can create users)
    const addUserBtn = page.getByRole('button', { name: /add user/i })
    await expect(addUserBtn).toBeVisible()

    await takeScreenshot(page, 'users_list_admin')
  })

  test('6. Admin cannot create super_admin users — role option restricted', async ({ page }) => {
    await loginAsAdmin(page)

    await page.goto('/dashboard/users', { waitUntil: 'networkidle' })
    await expect(page.getByRole('heading', { name: 'User Management' })).toBeVisible({ timeout: 15000 })

    // Wait for table to load
    const table = page.locator('table')
    await expect(table).toBeVisible({ timeout: 15000 })
    await page.waitForTimeout(2000)

    // Open the Add User modal
    const addUserBtn = page.getByRole('button', { name: /add user/i })
    await addUserBtn.click()

    // Verify modal opens
    const modal = page.locator('.fixed.inset-0').filter({ has: page.getByText('Create User') })
    await expect(modal).toBeVisible({ timeout: 10000 })

    // Check the role select dropdown — super_admin should NOT be an option for admin users
    const roleSelect = modal.locator('select')
    const options = roleSelect.locator('option')
    const optionCount = await options.count()

    const optionValues: string[] = []
    for (let i = 0; i < optionCount; i++) {
      const val = await options.nth(i).getAttribute('value')
      if (val) optionValues.push(val)
    }

    // Admin should only see: admin, operator, viewer (NOT super_admin)
    expect(optionValues).not.toContain('super_admin')
    expect(optionValues).toContain('admin')
    expect(optionValues).toContain('operator')
    expect(optionValues).toContain('viewer')

    // Also verify that editing a super_admin user's Edit button is disabled
    const closeBtn = modal.locator('button').filter({ has: page.locator('svg path') }).first()
    await closeBtn.click()
    await expect(modal).not.toBeVisible({ timeout: 5000 })

    // Check if super_admin rows have disabled Edit buttons
    const saRow = table.locator('tbody tr').filter({ hasText: 'super admin' })
    if (await saRow.count() > 0) {
      const editBtn = saRow.first().locator('button', { hasText: 'Edit' })
      if (await editBtn.count() > 0) {
        const isDisabled = await editBtn.first().isDisabled()
        expect(isDisabled).toBeTruthy()
      }
    }

    await takeScreenshot(page, 'users_admin_restricted_roles')
  })
})
