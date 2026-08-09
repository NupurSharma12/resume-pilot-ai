// Refresh/recovery behavior: state must survive a real browser reload
// wherever it's persisted, and a genuinely stale/missing backend session
// must degrade to a friendly, recoverable state -- never a raw backend
// error or a blank screen. Deterministic throughout: seeded session state
// plus route interception for the one case (a stale tailoring plan) that
// needs the backend to actually say "not found."
import { test, expect } from '@playwright/test'
import { fixtureTailoringPlan, seedResumeSession } from './fixtures/session'
import {
  mockCareerConversationGet,
  mockGenerateEndpoint,
  mockStalePlanThenRecover,
} from './helpers/mockApply'

test.describe('Refresh during tailoring review', () => {
  test('a reload mid-review restores the plan, selections, and section grouping', async ({
    page,
  }) => {
    await seedResumeSession(page, {
      tailoringSelections: ['suggestion-0'],
    })
    await page.goto('/tailored-resume')
    await expect(page.getByRole('heading', { name: 'Review Suggestions' })).toBeVisible()
    await expect(page.getByText('1 of 3 selected')).toBeVisible()

    await page.reload()

    await expect(page.getByRole('heading', { name: 'Review Suggestions' })).toBeVisible()
    await expect(page.getByText('1 of 3 selected')).toBeVisible()
    await expect(page.getByText('Add TypeScript')).toBeVisible()
  })
})

test.describe('Refresh after apply', () => {
  test('a reload after applying still shows the final resume and the applied badge', async ({
    page,
  }) => {
    await seedResumeSession(page, {
      finalTailoredResume: {
        finalResumeText: 'SUMMARY\nBackend engineer.\n\nSKILLS\nPython, TypeScript\nDjango\n',
        appliedSuggestionIds: ['suggestion-0'],
      },
      tailoringValidationReport: { is_valid: true, messages: [] },
    })
    await page.goto('/tailored-resume')
    await expect(page.getByText('Final Resume Preview')).toBeVisible()
    await expect(page.getByText('Applied', { exact: true }).first()).toBeVisible()

    await page.reload()

    await expect(page.getByText('Final Resume Preview')).toBeVisible()
    await expect(page.getByText('Applied', { exact: true }).first()).toBeVisible()
    const appliedCheckbox = page.getByRole('checkbox').first()
    await expect(appliedCheckbox).toBeDisabled()
    await expect(appliedCheckbox).toBeChecked()
  })
})

test.describe('Refresh during the career conversation', () => {
  test('a made-up/expired conversation id shows a friendly recovery message, never a raw backend error', async ({
    page,
  }) => {
    await seedResumeSession(page, {
      activeCareerConversationSessionId: 'session-that-does-not-exist-on-the-server',
      careerConversationStatus: 'in_progress',
    })
    await page.goto('/career-conversation')

    // This id was never created server-side, so the real backend
    // genuinely 404s -- no mocking needed, this is deterministic by
    // construction.
    await expect(
      page.getByText(/your previous conversation could not be found/i),
    ).toBeVisible({ timeout: 15_000 })
    await expect(page.getByText(/traceback|internal server error|500/i)).toHaveCount(0)
  })
})

test.describe('Stale tailoring plan recovery', () => {
  test('a stale plan_id on Preview Changes recovers automatically without a raw error', async ({
    page,
  }) => {
    await seedResumeSession(page, { tailoringSelections: ['suggestion-0'] })
    // Only the very first apply call against the seeded plan id 404s;
    // the automatic regenerate-and-retry that follows succeeds (see
    // mockStalePlanThenRecover's docstring). Recovery also re-fetches the
    // Career Conversation transcript before regenerating (see
    // mockCareerConversationGet's docstring) -- without mocking that
    // too, a seeded-but-never-real session id would 404 there instead,
    // which is a *different*, already-covered scenario (see "stale state
    // never produces a broken/blank screen" below).
    await mockStalePlanThenRecover(page, fixtureTailoringPlan.plan_id)
    await mockCareerConversationGet(page, 'e2e-fixture-session-1')
    await mockGenerateEndpoint(page)

    await page.goto('/tailored-resume')
    await page.getByRole('button', { name: 'Preview Changes' }).click()

    // The "Refreshing tailoring suggestions…" status is real (see
    // TailoredResumePage's isRecovering state, and the dedicated vitest
    // coverage that holds the regenerate call open to observe it) but,
    // with a mocked network, recovery resolves in well under a render
    // frame -- too fast for this real-browser test to reliably catch
    // mid-flight. What matters here is the outcome: never the raw
    // backend error, and a working preview with no second click.
    await expect(page.getByText(/tailoring suggestion plan not found/i)).toHaveCount(0)
    await expect(page.getByRole('button', { name: 'Apply Now' })).toBeVisible({ timeout: 15_000 })
  })

  test('stale state never produces a broken/blank screen', async ({ page }) => {
    await seedResumeSession(page, { tailoringSelections: ['suggestion-0'] })
    await mockStalePlanThenRecover(page, fixtureTailoringPlan.plan_id)
    // Regeneration itself also fails here -- the one case that's allowed
    // to become a user-facing message (see this feature's docs).
    await page.route('**/v1/tailoring-suggestions', async (route) => {
      if (route.request().method() !== 'POST') {
        await route.continue()
        return
      }
      await route.fulfill({ status: 500, json: { detail: 'boom' } })
    })

    await page.goto('/tailored-resume')
    await page.getByRole('button', { name: 'Preview Changes' }).click()

    await expect(page.getByText(/we need to regenerate your tailoring suggestions/i)).toBeVisible({
      timeout: 15_000,
    })
    await expect(page.getByRole('button', { name: 'Regenerate Suggestions' })).toBeVisible()
    // The page itself is never blank/broken -- the rest of the review UI
    // (the "boom" 500 body) never leaks to the screen.
    await expect(page.getByText('boom')).toHaveCount(0)
  })
})
