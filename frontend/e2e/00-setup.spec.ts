import { test, expect } from '@playwright/test'
import { loginAsSuperAdmin, getAdminEmail } from './helpers/auth'

/**
 * Global setup test — runs FIRST (alphabetically before auth.spec.ts).
 * Ensures the admin@exzelon.com user has the 'admin' role, repairing
 * any corruption from previous test runs that may have demoted the user.
 */
test.describe('Global Setup', () => {
  test('Ensure admin user has admin role', async ({ page }) => {
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
})
