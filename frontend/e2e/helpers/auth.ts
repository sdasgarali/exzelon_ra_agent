import { Page, expect } from '@playwright/test'
import * as fs from 'fs'
import * as path from 'path'
import * as dotenv from 'dotenv'

// Load credentials from .env.test
const envPath = path.resolve(__dirname, '../../.env.test')
if (fs.existsSync(envPath)) {
  dotenv.config({ path: envPath })
}

const SA_EMAIL = process.env.SA_EMAIL || ''
const SA_PASSWORD = process.env.SA_PASSWORD || ''
const ADMIN_EMAIL = process.env.ADMIN_EMAIL || ''
const ADMIN_PASSWORD = process.env.ADMIN_PASSWORD || ''

// Track login timestamps to throttle and avoid rate limiting (5/min)
let lastLoginTime = 0
const MIN_LOGIN_INTERVAL_MS = 13000 // ~13s between logins = max 4.6/min, safely under 5/min

async function throttleLogin() {
  const now = Date.now()
  const elapsed = now - lastLoginTime
  if (elapsed < MIN_LOGIN_INTERVAL_MS && lastLoginTime > 0) {
    const wait = MIN_LOGIN_INTERVAL_MS - elapsed
    await new Promise(resolve => setTimeout(resolve, wait))
  }
  lastLoginTime = Date.now()
}

export async function loginAsSuperAdmin(page: Page) {
  await doLogin(page, SA_EMAIL, SA_PASSWORD)
}

export async function loginAsAdmin(page: Page) {
  await doLogin(page, ADMIN_EMAIL, ADMIN_PASSWORD)
}

async function doLogin(page: Page, email: string, password: string) {
  await throttleLogin()
  await page.goto('/login', { waitUntil: 'networkidle' })
  await page.fill('input[type="email"]', email)
  await page.fill('input[type="password"]', password)
  await page.click('button[type="submit"]')
  // Wait for redirect to dashboard (use regex pattern for reliability)
  await page.waitForURL(/\/dashboard/, { timeout: 30000 })
  // Wait for sidebar to render (confirms auth loaded)
  await page.waitForSelector('nav[aria-label="Main navigation"]', { timeout: 15000 })
}

export async function loginWithCredentials(page: Page, email: string, password: string) {
  await page.goto('/login', { waitUntil: 'networkidle' })
  await page.fill('input[type="email"]', email)
  await page.fill('input[type="password"]', password)
  await page.click('button[type="submit"]')
}

export async function logout(page: Page) {
  // Click profile button at bottom of sidebar to open dropdown
  const profileBtn = page.locator('nav[aria-label="Main navigation"]').locator('..').locator('button').last()
  await profileBtn.click()
  // Wait for dropdown and click Sign out
  const signOutBtn = page.getByText('Sign out')
  await signOutBtn.waitFor({ state: 'visible', timeout: 5000 })
  await signOutBtn.click()
  // Wait for redirect to login
  await page.waitForURL('**/login', { timeout: 15000 })
}

export function getSAEmail() { return SA_EMAIL }
export function getAdminEmail() { return ADMIN_EMAIL }
