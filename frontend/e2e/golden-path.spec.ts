// The golden, fully real, end-to-end journey: resume upload -> JD ->
// analysis -> career conversation -> tailoring suggestions -> select a
// subset -> preview -> apply -> re-analyze & compare -> final resume ->
// download. Every step is a real browser interaction against the real
// backend and whatever LLM provider chain is configured locally (see
// e2e/README.md) -- assertions are deliberately content-agnostic
// (counts, presence, structure) since real model output varies between
// runs. The Post-Apply Analysis Loop step is the one partial exception:
// it reads the real /reanalyze response to assert the UI's displayed
// status/delta are *internally consistent* with whatever the live LLM
// actually returned, without ever asserting a specific score or that the
// score must improve (see docs/features/postapply-analysis-loop.md --
// improved/unchanged/decreased are all valid, truthful outcomes).
//
// This spec exists to prove the *product contract*, not just that each
// screen individually works:
//
//   Preview -> reviewable diff -> Apply -> re-analyze with visible
//   progress -> verified before/after result -> Download
//
// -- never the shortcut "Apply -> Download" the app used to allow. See
// docs/features/postapply-analysis-loop.md's "Download is gated on
// re-analysis" for the enforced rule this test is exercising for real,
// against the real backend, in addition to the deterministic coverage in
// post-apply-analysis.spec.ts.
import { test, expect, type Download } from '@playwright/test'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import {
  completeCareerConversation,
  generateTailoringPlan,
  runResumeAnalysis,
  uploadResumeAndJobDescription,
} from './helpers/tailoringFlow'
import type { ReanalyzeResponse } from '../src/data/postApplyTypes'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const ARTIFACTS_DIR = path.join(__dirname, '..', 'artifacts', 'e2e')
const TAILORING_PREVIEW_SCREENSHOT = path.join(ARTIFACTS_DIR, 'tailoring-preview-diff.png')
const POST_APPLY_COMPARISON_SCREENSHOT = path.join(ARTIFACTS_DIR, 'post-apply-comparison.png')

test.describe('Golden path: upload through download', () => {
  test('a candidate can go from resume upload to a downloaded tailored resume', async ({
    page,
  }) => {
    // This test makes several sequential real LLM calls (career-
    // conversation start/turns, tailoring-suggestion generation) against
    // whatever provider chain is configured locally -- any one of those
    // can take 10-25+ seconds on its own, so Playwright's global 30s
    // default (playwright.config.ts is intentionally left untouched) is
    // nowhere near enough. Scoped to just this test, not the config,
    // since the deterministic specs genuinely don't need it.
    test.setTimeout(300_000)

    await test.step('upload a resume and paste a job description', async () => {
      await uploadResumeAndJobDescription(page)
    })

    await test.step('run resume analysis', async () => {
      await runResumeAnalysis(page)
      // The five fixed skill-match categories/metric cards render
      // regardless of exact LLM content.
      await expect(page.getByText('MATCH SCORE')).toBeVisible()
    })

    await test.step('complete the career conversation', async () => {
      await completeCareerConversation(page)
    })

    await test.step('generate tailoring suggestions', async () => {
      await generateTailoringPlan(page)
    })

    const totalCount = await page.getByRole('checkbox').count()
    expect(totalCount).toBeGreaterThan(0)

    await test.step('select a subset of suggestions', async () => {
      // Start from a clean slate, then select only the first suggestion --
      // proves selection state actually drives what gets previewed/applied,
      // not "whatever the model recommended by default."
      await page.getByRole('button', { name: 'Clear All' }).click()
      await expect(page.getByText(/^0 of \d+ selected$/)).toBeVisible()

      await page.getByRole('checkbox').first().check()
      await expect(page.getByText(/^1 of \d+ selected$/)).toBeVisible()
    })

    await test.step('preview tailoring changes', async () => {
      await page.getByRole('button', { name: 'Preview Changes' }).click()
      await expect(page.getByRole('heading', { name: 'Preview Changes' })).toBeVisible()
      await expect(page.getByRole('button', { name: 'Apply Now' })).toBeVisible()
      // Nothing is committed by opening the preview.
      await expect(page.getByText('Final Resume Preview')).not.toBeVisible()

      // The reviewable, GitHub-style split diff is the whole point of
      // "Preview" -- it must actually be on screen before Apply, not just
      // a generic "changes ready" message.
      await expect(page.getByText(/sections changed/i)).toBeVisible()
    })

    await test.step('capture tailoring preview', async () => {
      // Scoped to the diff card itself (not the full viewport) so the
      // screenshot is a focused, reviewable artifact of the split
      // view/section grouping -- see this file's header for why this
      // exists (human inspection, not a functional assertion; the DOM
      // assertions above and below remain authoritative).
      const diffCard = page.locator('.rounded-2xl', { hasText: /sections changed/i }).first()
      await diffCard.screenshot({ path: TAILORING_PREVIEW_SCREENSHOT })
    })

    await test.step('apply selected changes', async () => {
      await page.getByRole('button', { name: 'Apply Now' }).click()
      await expect(page.getByText('Final Resume Preview')).toBeVisible({ timeout: 30_000 })
      await expect(page.getByText('Applied changes (1)')).toBeVisible()
      await expect(page.getByText('Applied').first()).toBeVisible()
    })

    await test.step('verify download is gated', async () => {
      // The core enforced UX this test exists to prove: Apply alone is
      // never enough to unlock Download -- see docs/features/postapply-
      // analysis-loop.md's "Download is gated on re-analysis". No
      // download button exists anywhere on the page yet, in any format.
      await expect(
        page.getByRole('button', { name: /^download (txt|markdown|docx|pdf)$/i }),
      ).toHaveCount(0)
      await expect(page.getByRole('button', { name: 'Re-analyze & Compare' })).toBeVisible()
    })

    let reanalyzeResponse: Awaited<ReturnType<typeof page.waitForResponse>>
    await test.step('verify re-analysis progress', async () => {
      const reanalyzeResponsePromise = page.waitForResponse(
        (response) => response.url().includes('/reanalyze') && response.request().method() === 'POST',
        { timeout: 120_000 },
      )
      await page.getByRole('button', { name: 'Re-analyze & Compare' }).click()

      // A real re-analysis call can take a good while -- confirm the
      // "meaningful progress" state (the application's own
      // ConversationLoadingState copy, not an invented selector or a
      // fabricated percentage) is what the candidate actually sees
      // during that wait, and that Download stays gated throughout it.
      await expect(page.getByText(/re-analyzing your updated resume/i)).toBeVisible()
      await expect(
        page.getByRole('button', { name: /^download (txt|markdown|docx|pdf)$/i }),
      ).toHaveCount(0)

      reanalyzeResponse = await reanalyzeResponsePromise
      expect(reanalyzeResponse.ok()).toBe(true)

      // The loading state clears once the real response has landed.
      await expect(page.getByText(/re-analyzing your updated resume/i)).not.toBeVisible()
    })

    await test.step('verify post-apply comparison', async () => {
      const body = (await reanalyzeResponse.json()) as ReanalyzeResponse
      const { score_before, score_after, score_delta, status } = body.comparison

      // Sanity on the shape of a real response -- never a specific value.
      expect(Number.isInteger(score_before)).toBe(true)
      expect(Number.isInteger(score_after)).toBe(true)
      expect(score_before).toBeGreaterThanOrEqual(0)
      expect(score_before).toBeLessThanOrEqual(100)
      expect(score_after).toBeGreaterThanOrEqual(0)
      expect(score_after).toBeLessThanOrEqual(100)

      // The comparison must be deterministic domain logic, not an LLM
      // opinion -- verify the backend's own math/verdict is internally
      // consistent with the two real scores it just produced.
      expect(score_delta).toBe(score_after - score_before)
      const expectedStatus =
        score_after > score_before ? 'improved' : score_after < score_before ? 'decreased' : 'unchanged'
      expect(status).toBe(expectedStatus)

      // Diagnostic output for a headed/manual run -- this is intentionally
      // the real numbers, not a hard-coded expectation.
      console.log(
        [
          'Post-Apply Analysis',
          `Before score: ${score_before}`,
          `After score: ${score_after}`,
          `Delta: ${score_delta >= 0 ? '+' : ''}${score_delta}`,
          `Status: ${status}`,
        ].join('\n'),
      )

      // The UI must display this exact truthful outcome -- using the
      // application's own existing wording (PostApplyComparisonCard),
      // never inventing new copy to match against.
      if (status === 'improved') {
        await expect(
          page.getByText(
            `Match score improved by ${score_delta} point${score_delta === 1 ? '' : 's'}`,
          ),
        ).toBeVisible()
      } else if (status === 'decreased') {
        const magnitude = Math.abs(score_delta)
        await expect(
          page.getByText(`Match score decreased by ${magnitude} point${magnitude === 1 ? '' : 's'}`),
        ).toBeVisible()
      } else {
        await expect(page.getByText('Match score did not improve')).toBeVisible()
      }

      // Both real scores are visibly present on screen (see the score
      // badge in PostApplyComparisonCard -- the two numbers render as
      // adjacent text nodes around an arrow icon with no separator).
      await expect(page.getByText(`${score_before}${score_after}`)).toBeVisible()

      // Download only becomes available now that a valid comparison
      // actually exists -- the whole point of this test.
      await expect(page.getByRole('button', { name: /^download txt$/i })).toBeVisible()
    })

    await test.step('capture post-apply comparison', async () => {
      // Full page (not the whole OS window -- Playwright's page
      // screenshot excludes browser chrome), so the reviewable artifact
      // shows the comparison card, its surrounding UX, and the now-
      // available Download CTA together, not just the comparison numbers
      // in isolation.
      await page.screenshot({ path: POST_APPLY_COMPARISON_SCREENSHOT, fullPage: true })
    })

    let download: Download
    await test.step('download final resume', async () => {
      const downloadPromise = page.waitForEvent('download')
      await page.getByRole('button', { name: /^download txt$/i }).click()
      download = await downloadPromise
    })

    await test.step('verify downloaded artifact', async () => {
      expect(download.suggestedFilename()).toMatch(/\.txt$/i)
      const stream = await download.createReadStream()
      const chunks: Buffer[] = []
      for await (const chunk of stream ?? []) chunks.push(chunk as Buffer)
      const content = Buffer.concat(chunks).toString('utf-8')
      expect(content.length).toBeGreaterThan(0)
    })
  })
})
