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
import { test, expect } from '@playwright/test'
import {
  completeCareerConversation,
  generateTailoringPlan,
  runResumeAnalysis,
  uploadResumeAndJobDescription,
} from './helpers/tailoringFlow'
import type { ReanalyzeResponse } from '../src/data/postApplyTypes'

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

    await test.step('preview the selected change (read-only)', async () => {
      await page.getByRole('button', { name: 'Preview Changes' }).click()
      await expect(page.getByRole('heading', { name: 'Preview Changes' })).toBeVisible()
      await expect(page.getByRole('button', { name: 'Apply Now' })).toBeVisible()
      // Nothing is committed by opening the preview.
      await expect(page.getByText('Final Resume Preview')).not.toBeVisible()
    })

    await test.step('apply the selected change', async () => {
      await page.getByRole('button', { name: 'Apply Now' }).click()
      await expect(page.getByText('Final Resume Preview')).toBeVisible({ timeout: 30_000 })
    })

    await test.step('confirm the updated resume is shown, with the applied change marked', async () => {
      await expect(page.getByText('Applied changes (1)')).toBeVisible()
      await expect(page.getByText('Applied').first()).toBeVisible()
    })

    await test.step('re-analyze the applied resume and verify a truthful comparison', async () => {
      // Reads the real backend response rather than mocking it -- this
      // is the one live-only assertion source of truth for what the LLM
      // actually produced this run; the deterministic three-outcome
      // coverage (improved/unchanged/decreased/failure) already lives in
      // post-apply-analysis.spec.ts and is not duplicated here.
      const reanalyzeResponsePromise = page.waitForResponse(
        (response) => response.url().includes('/reanalyze') && response.request().method() === 'POST',
        { timeout: 120_000 },
      )
      await page.getByRole('button', { name: 'Re-analyze & Compare' }).click()
      const reanalyzeResponse = await reanalyzeResponsePromise
      expect(reanalyzeResponse.ok()).toBe(true)
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
    })

    await test.step('download the final resume', async () => {
      const downloadPromise = page.waitForEvent('download')
      await page.getByRole('button', { name: /^download txt$/i }).click()
      const download = await downloadPromise
      expect(download.suggestedFilename()).toMatch(/\.txt$/i)
      const stream = await download.createReadStream()
      const chunks: Buffer[] = []
      for await (const chunk of stream ?? []) chunks.push(chunk as Buffer)
      const content = Buffer.concat(chunks).toString('utf-8')
      expect(content.length).toBeGreaterThan(0)
    })
  })
})
