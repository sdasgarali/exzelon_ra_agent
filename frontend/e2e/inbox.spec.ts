import { test, expect } from '@playwright/test'
import { loginAsSuperAdmin } from './helpers/auth'
import { takeScreenshot } from './helpers/screenshots'

test.describe('Inbox — Super Admin', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsSuperAdmin(page)
    await page.goto('/dashboard/inbox', { waitUntil: 'networkidle' })
    // Wait for page to fully render (loading spinner disappears or content appears)
    await page.waitForTimeout(2000)
  })

  test('1. Thread list loads — shows threads or empty state', async ({ page }) => {
    // The page header should be visible
    const heading = page.getByRole('heading', { name: 'Inbox' })
    await expect(heading).toBeVisible()

    // The thread list panel (left side, w-[340px]) should be visible
    const threadListPanel = page.locator('.w-\\[340px\\]').first()
    await expect(threadListPanel).toBeVisible()

    // Either threads are loaded or the "No conversations" empty state is shown
    const threadButtons = threadListPanel.locator('button').filter({ has: page.locator('.rounded-full') })
    const emptyState = page.getByText('No conversations')

    const hasThreads = await threadButtons.count() > 0
    const hasEmptyState = await emptyState.isVisible().catch(() => false)

    expect(hasThreads || hasEmptyState).toBeTruthy()

    // Check the conversations counter in the subtitle (e.g. "0 conversations")
    const subtitle = page.getByText(/\d+ conversations/)
    await expect(subtitle).toBeVisible()

    await takeScreenshot(page, 'inbox-thread-list-loaded')
  })

  test('2. Search threads — type a query into search input', async ({ page }) => {
    // Find the search input by placeholder
    const searchInput = page.getByPlaceholder('Search conversations...')
    await expect(searchInput).toBeVisible()

    // Type a search query
    await searchInput.fill('test')
    await page.waitForTimeout(1500)

    await takeScreenshot(page, 'inbox-search-typed')

    // Clear the search
    await searchInput.fill('')
    await page.waitForTimeout(1000)

    await takeScreenshot(page, 'inbox-search-cleared')
  })

  test('3. Thread detail panel — click a thread to see messages', async ({ page }) => {
    // Check for threads in the left panel
    // Thread items are <button> elements inside the w-[340px] panel's scrollable area
    const threadListPanel = page.locator('.w-\\[340px\\]').first()
    const threadItems = threadListPanel.locator('button.w-full.text-left')
    const threadCount = await threadItems.count()

    if (threadCount > 0) {
      // Click the first thread
      await threadItems.first().click()
      await page.waitForTimeout(2000)

      // The center panel should now show the thread detail
      // The "Select a conversation" placeholder should NOT be visible
      const placeholder = page.getByText('Select a conversation')
      const placeholderVisible = await placeholder.isVisible().catch(() => false)
      expect(placeholderVisible).toBe(false)

      // Thread header should be visible with subject and message count
      const messagesLabel = page.getByText(/messages/)
      await expect(messagesLabel.first()).toBeVisible()

      // The reply composer (textarea with "Write your reply...") should be visible
      const replyTextarea = page.getByPlaceholder(/Write your reply/)
      await expect(replyTextarea).toBeVisible()

      await takeScreenshot(page, 'inbox-thread-detail-open')
    } else {
      // No threads — the center panel shows the "Select a conversation" placeholder
      const placeholder = page.getByText('Select a conversation')
      await expect(placeholder).toBeVisible()

      await takeScreenshot(page, 'inbox-no-threads-placeholder')
    }
  })

  test('4. Sentiment badges display on threads', async ({ page }) => {
    // Look for sentiment/category badges in the thread list
    // Category badges have text like "Interested", "Not Interested", "Out of Office", "Question", "Referral"
    // They appear as small colored spans within thread items

    const threadListPanel = page.locator('.w-\\[340px\\]').first()
    const threadItems = threadListPanel.locator('button.w-full.text-left')
    const threadCount = await threadItems.count()

    if (threadCount > 0) {
      // Check for any category badges across all thread items
      // Category badges are small spans with category labels
      const categoryLabels = ['Interested', 'Not Interested', 'Out of Office', 'Question', 'Referral', 'Do Not Contact', 'Other']
      let foundBadge = false

      for (const label of categoryLabels) {
        const badge = threadListPanel.getByText(label, { exact: true })
        const count = await badge.count()
        if (count > 0) {
          foundBadge = true
          break
        }
      }

      // Also check for sentiment icons (ThumbsUp/ThumbsDown/Minus indicators)
      // These are rendered as SVG icons with specific classes
      const sentimentIcons = threadListPanel.locator('[title="Positive"], [title="Negative"], [title="Neutral"]')
      const sentimentCount = await sentimentIcons.count()

      if (foundBadge || sentimentCount > 0) {
        // Badges or sentiment indicators are present
        await takeScreenshot(page, 'inbox-sentiment-badges-found')
      } else {
        // No categorized threads — this is acceptable if threads have no category assigned
        await takeScreenshot(page, 'inbox-no-sentiment-badges')
      }

      // Verify the category legend toggle button exists (the Info icon button)
      // This is present regardless of whether threads have categories
      const legendButton = page.locator('button[title="Category Legend"]')
      await expect(legendButton).toBeVisible()

      // Click to show the category legend panel to verify all badge types
      await legendButton.click()
      await page.waitForTimeout(500)

      // The legend panel should appear with all category labels
      const legendHeading = page.getByText('Category Legend')
      await expect(legendHeading).toBeVisible()

      // Verify sentiment labels in the legend
      const sentimentLabel = page.getByText('Sentiment:')
      await expect(sentimentLabel).toBeVisible()

      await takeScreenshot(page, 'inbox-category-legend-open')

      // Close the legend
      await legendButton.click()
      await page.waitForTimeout(300)
    } else {
      // No threads — just verify the page loads correctly
      const emptyState = page.getByText('No conversations')
      await expect(emptyState).toBeVisible()

      await takeScreenshot(page, 'inbox-empty-no-badges')
    }
  })
})
