// The golden, fully real, end-to-end journey: resume upload -> JD ->
// analysis -> career conversation -> tailoring suggestions -> select a
// subset -> preview -> apply -> final resume -> download. Every step is a
// real browser interaction against the real backend and whatever LLM
// provider chain is configured locally (see e2e/README.md) -- assertions
// are deliberately content-agnostic (counts, presence, structure) since
// real model output varies between runs.
import { test, expect } from '@playwright/test'
import {
  completeCareerConversation,
  generateTailoringPlan,
  runResumeAnalysis,
  uploadResumeAndJobDescription,
} from './helpers/tailoringFlow'

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
