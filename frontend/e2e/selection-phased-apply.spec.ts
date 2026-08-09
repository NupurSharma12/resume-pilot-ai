// Selection mechanics (Select All / Clear All / individual toggles) and
// phased apply (apply a subset now, keep selecting more later, applied
// suggestions stay visibly distinct). Deterministic: seeded plan + a
// mocked /apply response (see mockApply.ts), no live LLM call.
import { test, expect } from '@playwright/test'
import { fixtureTailoringPlan, seedResumeSession } from './fixtures/session'
import { mockApplyEndpoint } from './helpers/mockApply'

test.describe('Selection behavior', () => {
  test.beforeEach(async ({ page }) => {
    await seedResumeSession(page)
    await page.goto('/tailored-resume')
    await expect(page.getByRole('heading', { name: 'Review Suggestions' })).toBeVisible()
  })

  test('Select All selects every suggestion, Clear All clears every selection', async ({
    page,
  }) => {
    const checkboxes = page.getByRole('checkbox')
    const total = await checkboxes.count()

    await page.getByRole('button', { name: 'Clear All' }).click()
    await expect(page.getByText(`0 of ${total} selected`)).toBeVisible()
    for (let i = 0; i < total; i++) {
      await expect(checkboxes.nth(i)).not.toBeChecked()
    }

    await page.getByRole('button', { name: 'Select All' }).click()
    await expect(page.getByText(`${total} of ${total} selected`)).toBeVisible()
    for (let i = 0; i < total; i++) {
      await expect(checkboxes.nth(i)).toBeChecked()
    }
  })

  test('toggling one suggestion does not affect the others', async ({ page }) => {
    const checkboxes = page.getByRole('checkbox')
    const total = await checkboxes.count()
    await page.getByRole('button', { name: 'Select All' }).click()
    await expect(page.getByText(`${total} of ${total} selected`)).toBeVisible()

    await checkboxes.first().uncheck()

    await expect(page.getByText(`${total - 1} of ${total} selected`)).toBeVisible()
    for (let i = 1; i < total; i++) {
      await expect(checkboxes.nth(i)).toBeChecked()
    }
  })

  test('re-previewing after changing the selection reflects only the new selection', async ({
    page,
  }) => {
    await mockApplyEndpoint(page, fixtureTailoringPlan.plan_id)

    await page.getByRole('button', { name: 'Clear All' }).click()
    await page.getByRole('checkbox').first().check()
    await page.getByRole('button', { name: 'Preview Changes' }).click()
    await expect(page.getByText('Add TypeScript')).toBeVisible()
    await page.getByRole('button', { name: 'Back to Suggestions' }).click()

    // Change the selection, then preview again.
    await page.getByRole('checkbox').first().uncheck()
    await page.getByRole('checkbox').nth(1).check()
    await page.getByRole('button', { name: 'Preview Changes' }).click()

    await expect(page.getByText('Add Flask')).toBeVisible()
    await expect(page.getByText('Add TypeScript')).not.toBeVisible()
  })
})

test.describe('Phased apply behavior', () => {
  test.beforeEach(async ({ page }) => {
    await seedResumeSession(page)
    await mockApplyEndpoint(page, fixtureTailoringPlan.plan_id)
    await page.goto('/tailored-resume')
    await expect(page.getByRole('heading', { name: 'Review Suggestions' })).toBeVisible()
  })

  test('applying a subset marks it Applied and greys it out, distinct from pending suggestions', async ({
    page,
  }) => {
    await page.getByRole('button', { name: 'Clear All' }).click()
    await page.getByRole('checkbox').first().check()

    await page.getByRole('button', { name: 'Preview Changes' }).click()
    await page.getByRole('button', { name: 'Apply Now' }).click()
    await expect(page.getByText('Final Resume Preview')).toBeVisible()

    // Back on the review stage, the applied suggestion is locked and
    // labeled; the others remain normal, editable, pending suggestions.
    const appliedBadges = page.getByText('Applied', { exact: true })
    await expect(appliedBadges.first()).toBeVisible()

    const appliedCheckbox = page.getByRole('checkbox').first()
    await expect(appliedCheckbox).toBeDisabled()
    await expect(appliedCheckbox).toBeChecked()

    const pendingCheckbox = page.getByRole('checkbox').nth(1)
    await expect(pendingCheckbox).toBeEnabled()
  })

  test('continuing to select and applying a second phase keeps the first phase marked Applied', async ({
    page,
  }) => {
    await page.getByRole('button', { name: 'Clear All' }).click()
    await page.getByRole('checkbox').first().check()
    await page.getByRole('button', { name: 'Preview Changes' }).click()
    await page.getByRole('button', { name: 'Apply Now' }).click()
    await expect(page.getByText('Applied changes (1)')).toBeVisible()

    // Phase 2: select one more pending suggestion and apply again.
    await page.getByRole('checkbox').nth(1).check()
    await page.getByRole('button', { name: 'Preview Changes' }).click()
    // The already-applied suggestion is called out separately from the
    // newly selected one in this phase's preview.
    await expect(page.getByText(/already applied/i)).toBeVisible()
    await expect(page.getByText(/new in this preview/i)).toBeVisible()

    await page.getByRole('button', { name: 'Apply Now' }).click()
    await expect(page.getByText('Applied changes (2)')).toBeVisible()

    const checkboxes = page.getByRole('checkbox')
    await expect(checkboxes.first()).toBeDisabled()
    await expect(checkboxes.nth(1)).toBeDisabled()
  })

  test('Undo reverts an applied suggestion back to a normal pending selection', async ({
    page,
  }) => {
    await page.getByRole('button', { name: 'Clear All' }).click()
    await page.getByRole('checkbox').first().check()
    await page.getByRole('button', { name: 'Preview Changes' }).click()
    await page.getByRole('button', { name: 'Apply Now' }).click()
    await expect(page.getByText('Applied', { exact: true }).first()).toBeVisible()

    await page.getByRole('button', { name: 'Undo' }).click()

    await expect(page.getByText('Applied', { exact: true })).toHaveCount(0)
    await expect(page.getByRole('checkbox').first()).toBeEnabled()
    await expect(page.getByRole('checkbox').first()).not.toBeChecked()
  })
})
