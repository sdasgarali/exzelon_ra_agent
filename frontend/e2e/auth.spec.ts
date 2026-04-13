import { test, expect } from '@playwright/test'
import {
  loginAsSuperAdmin,
  loginAsAdmin,
  loginWithCredentials,
  logout,
  getSAEmail,
  getAdminEmail,
} from './helpers/auth'
import { takeScreenshot } from './helpers/screenshots'

test.describe.serial('Authentication — Login & Session', () => {
  test('1. Login with valid Super Admin credentials redirects to dashboard', async ({ page }) => {
    await loginAsSuperAdmin(page)

    // Verify we are on the dashboard
    await expect(page).toHaveURL(/\/dashboard/)

    // Verify the sidebar rendered (confirms auth state is loaded)
    const sidebar = page.locator('nav[aria-label="Main navigation"]')
    await expect(sidebar).toBeVisible()

    // Verify the dashboard nav link is active
    await expect(page.getByRole('link', { name: 'Dashboard' })).toBeVisible()

    await takeScreenshot(page, 'auth_login_sa_success')
  })

  test('2. Login with valid Admin credentials redirects to dashboard', async ({ page }) => {
    await loginAsAdmin(page)

    // Verify we are on the dashboard
    await expect(page).toHaveURL(/\/dashboard/)

    // Verify the sidebar rendered
    const sidebar = page.locator('nav[aria-label="Main navigation"]')
    await expect(sidebar).toBeVisible()

    await expect(page.getByRole('link', { name: 'Dashboard' })).toBeVisible()

    await takeScreenshot(page, 'auth_login_admin_success')
  })

  test('3. Login with wrong password shows error message', async ({ page }) => {
    // Use a non-existent email to avoid triggering account lockout on real accounts
    await loginWithCredentials(page, 'wrong_password_test@nonexistent.com', 'CompletelyWrongPassword!999')

    // Should stay on login page
    await expect(page).toHaveURL(/\/login/)

    // Wait for the error message to appear (red bg error div)
    const errorDiv = page.locator('.bg-red-50.text-red-600')
    await expect(errorDiv).toBeVisible({ timeout: 15000 })

    // Error message should contain something meaningful
    const errorText = await errorDiv.textContent()
    expect(errorText).toBeTruthy()
    expect(errorText!.length).toBeGreaterThan(0)

    await takeScreenshot(page, 'auth_login_wrong_password')
  })

  test('4. Login with non-existent email shows error message', async ({ page }) => {
    await loginWithCredentials(page, 'nonexistent_user_xyz@fakeemail.com', 'SomePassword123!')

    // Should stay on login page
    await expect(page).toHaveURL(/\/login/)

    // Wait for the error message to appear
    const errorDiv = page.locator('.bg-red-50.text-red-600')
    await expect(errorDiv).toBeVisible({ timeout: 15000 })

    const errorText = await errorDiv.textContent()
    expect(errorText).toBeTruthy()
    expect(errorText!.length).toBeGreaterThan(0)

    await takeScreenshot(page, 'auth_login_nonexistent_email')
  })

  test('5. Login with empty fields prevents form submission via required attribute', async ({ page }) => {
    await page.goto('/login', { waitUntil: 'networkidle' })

    // Both inputs have the "required" attribute
    const emailInput = page.locator('input[type="email"]')
    const passwordInput = page.locator('input[type="password"]')
    await expect(emailInput).toHaveAttribute('required', '')
    await expect(passwordInput).toHaveAttribute('required', '')

    // Click submit without filling anything
    await page.click('button[type="submit"]')

    // Should still be on login page (browser validation prevents submit)
    await expect(page).toHaveURL(/\/login/)

    // No error div should appear (browser handles validation natively)
    const errorDiv = page.locator('.bg-red-50.text-red-600')
    await expect(errorDiv).not.toBeVisible()

    await takeScreenshot(page, 'auth_login_empty_fields')
  })

  test('6. Logout redirects to login page', async ({ page }) => {
    // First login
    await loginAsSuperAdmin(page)
    await expect(page).toHaveURL(/\/dashboard/)

    // Perform logout
    await logout(page)

    // Verify redirect to login page
    await expect(page).toHaveURL(/\/login/)

    // Verify the login form is visible
    await expect(page.locator('input[type="email"]')).toBeVisible()
    await expect(page.locator('input[type="password"]')).toBeVisible()

    await takeScreenshot(page, 'auth_logout_redirect')
  })

  test('7. Session persistence — page refresh keeps user on dashboard', async ({ page }) => {
    // Use Admin to avoid rate-limiting SA (which just logged in/out in test 6)
    await loginAsAdmin(page)
    await expect(page).toHaveURL(/\/dashboard/)

    // Refresh the page
    await page.reload({ waitUntil: 'networkidle' })

    // Should still be on the dashboard (session token persists in Zustand/localStorage)
    await expect(page).toHaveURL(/\/dashboard/)

    // Sidebar should still be rendered
    const sidebar = page.locator('nav[aria-label="Main navigation"]')
    await expect(sidebar).toBeVisible({ timeout: 15000 })

    await takeScreenshot(page, 'auth_session_persistence')
  })
})

test.describe.serial('Authentication — Role-Based Navigation Visibility', () => {
  test('8a. Super Admin sees Activity Log, Tenant Management, and Roles & Permissions in nav', async ({ page }) => {
    await loginAsSuperAdmin(page)

    const sidebar = page.locator('nav[aria-label="Main navigation"]')
    await expect(sidebar).toBeVisible()

    // SA-only nav items should be visible
    await expect(sidebar.getByText('Activity Log')).toBeVisible()
    await expect(sidebar.getByText('Tenant Management')).toBeVisible()
    await expect(sidebar.getByText('Roles & Permissions')).toBeVisible()

    await takeScreenshot(page, 'auth_nav_sa_all_items')
  })

  test('8b. Admin does NOT see Activity Log, Tenant Management, or Roles & Permissions in nav', async ({ page }) => {
    await loginAsAdmin(page)

    const sidebar = page.locator('nav[aria-label="Main navigation"]')
    await expect(sidebar).toBeVisible()

    // SA-only nav items should NOT be visible for admin
    await expect(sidebar.getByText('Activity Log')).not.toBeVisible()
    await expect(sidebar.getByText('Tenant Management')).not.toBeVisible()
    await expect(sidebar.getByText('Roles & Permissions')).not.toBeVisible()

    // But admin should see common items
    await expect(sidebar.getByText('Dashboard')).toBeVisible()
    await expect(sidebar.getByText('Leads')).toBeVisible()
    await expect(sidebar.getByText('Settings')).toBeVisible()

    await takeScreenshot(page, 'auth_nav_admin_restricted')
  })
})
