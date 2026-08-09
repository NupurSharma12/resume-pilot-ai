// GitHub-style diff comparator behavior -- both the per-suggestion
// "Preview Change" (pure client-side, no network at all) and the combined
// multi-suggestion "Preview Changes" panel (backed by a mocked /apply
// response, see mockApply.ts). Deterministic: no live LLM call anywhere
// in this file.
import { test, expect } from '@playwright/test'
import { fixtureTailoringPlan, seedResumeSession } from './fixtures/session'
import { mockApplyEndpoint } from './helpers/mockApply'

test.describe('Comparator: per-suggestion Preview Change', () => {
  test.beforeEach(async ({ page }) => {
    await seedResumeSession(page)
    await page.goto('/tailored-resume')
    await expect(page.getByRole('heading', { name: 'Review Suggestions' })).toBeVisible()
  })

  test('shows only the changed hunk -- an append splits into unchanged context plus a green addition', async ({
    page,
  }) => {
    const card = page.locator('li').filter({ hasText: 'Add TypeScript' })
    await card.getByRole('button', { name: 'Preview Change' }).click()

    await expect(card.getByText('Original')).toBeVisible()
    await expect(card.getByText('Proposed')).toBeVisible()
    // The common prefix "Python" is shown once as unchanged (neutral)
    // context, not duplicated as a removal -- only the new suffix is a
    // green addition. Scoped to the diff cells specifically (by their own
    // background classes, see SideBySideDiff.tsx) since the card's own
    // one-line summary ("Add TypeScript") and reason text also contain
    // the word "TypeScript" and would otherwise match too.
    await expect(card.locator('.bg-emerald-50')).toHaveText('+TypeScript')
    await expect(card.locator('.bg-rose-50')).toHaveCount(0)
  })

  test('shows an addition-only comparator (empty original side) for an insertion', async ({
    page,
  }) => {
    const insertionCard = page
      .locator('li', { has: page.getByText('People-management evidence is missing') })
    await insertionCard.getByRole('button', { name: 'Preview Change' }).click()

    await expect(insertionCard.locator('.bg-emerald-50')).toHaveText(
      '+Led a cross-team migration involving 4 engineers.',
    )
    // A pure addition has nothing on the removed/original side.
    await expect(insertionCard.locator('.bg-rose-50')).toHaveCount(0)
  })

  test('opening a per-suggestion preview never selects the suggestion or calls the network', async ({
    page,
  }) => {
    let applyCalled = false
    await page.route('**/v1/tailoring-suggestions/**/apply', () => {
      applyCalled = true
    })

    const secondCheckbox = page.getByRole('checkbox').nth(1)
    const wasChecked = await secondCheckbox.isChecked()

    await page.getByRole('button', { name: 'Preview Change' }).nth(1).click()
    await expect(page.getByText('Original')).toBeVisible()

    expect(await secondCheckbox.isChecked()).toBe(wasChecked)
    expect(applyCalled).toBe(false)
  })
})

test.describe('Comparator: combined multi-suggestion Preview Changes panel', () => {
  test.beforeEach(async ({ page }) => {
    await seedResumeSession(page)
    await mockApplyEndpoint(page, fixtureTailoringPlan.plan_id)
    await page.goto('/tailored-resume')
    await expect(page.getByRole('heading', { name: 'Review Suggestions' })).toBeVisible()
  })

  test('section tabs switch between sections, each showing only its own hunks', async ({
    page,
  }) => {
    await page.getByRole('button', { name: 'Preview Changes' }).click()
    await expect(page.getByRole('heading', { name: 'Preview Changes' })).toBeVisible()

    // Two sections were touched (Skills, Experience) -- tabs for both exist.
    const skillsTab = page.getByRole('button', { name: /^skills/i })
    const experienceTab = page.getByRole('button', { name: /^experience/i })
    await expect(skillsTab).toBeVisible()
    await expect(experienceTab).toBeVisible()

    await skillsTab.click()
    await expect(page.getByRole('heading', { name: 'Skills' })).toBeVisible()

    await experienceTab.click()
    await expect(page.getByRole('heading', { name: 'Experience' })).toBeVisible()
  })

  test('the panel is read-only: it never applies anything until Apply Now is clicked', async ({
    page,
  }) => {
    await page.getByRole('button', { name: 'Preview Changes' }).click()
    await expect(page.getByRole('button', { name: 'Apply Now' })).toBeVisible()

    // Going back preserves the selection and never shows a committed
    // "Final Resume Preview".
    await page.getByRole('button', { name: 'Back to Suggestions' }).click()
    await expect(page.getByText('Final Resume Preview')).not.toBeVisible()
    await expect(page.getByRole('heading', { name: 'Review Suggestions' })).toBeVisible()
  })

  test('only currently selected suggestions affect the preview', async ({ page }) => {
    // Only suggestion-0 (default-selected) is checked; suggestion-1 is not.
    await page.getByRole('button', { name: 'Preview Changes' }).click()

    await expect(page.getByText(/new in this preview/i)).toBeVisible()
    // The included-suggestions summary only ever lists what's selected.
    await expect(page.getByText('Add TypeScript')).toBeVisible()
    await expect(page.getByText('Add Flask')).not.toBeVisible()
  })
})
