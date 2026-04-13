import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: 0,
  workers: 1,
  reporter: [
    ['list'],
    ['json', { outputFile: 'e2e/test-results.json' }],
  ],
  use: {
    baseURL: 'https://ra.partnerwithus.tech',
    screenshot: 'on',
    trace: 'off',
    video: 'off',
    actionTimeout: 15000,
    navigationTimeout: 30000,
  },
  timeout: 60000,
  outputDir: 'e2e/screenshots',
  projects: [
    {
      name: 'chromium',
      use: {
        browserName: 'chromium',
        viewport: { width: 1440, height: 900 },
        ignoreHTTPSErrors: true,
      },
    },
  ],
})
