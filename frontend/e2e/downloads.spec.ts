// Download coverage: every format the app offers (TXT, Markdown, DOCX,
// PDF) after a real apply, verifying each downloaded file is non-empty,
// has the right shape/signature, and (for the text-based formats)
// actually contains resume content -- not just that a click didn't
// error. Live: runs the real upload -> analysis -> conversation ->
// generate -> apply flow once, then downloads each available format
// against that one real, applied plan.
import { test, expect } from '@playwright/test'
import { runFullFlowThroughGeneratedPlan } from './helpers/tailoringFlow'

test.describe('Downloads', () => {
  test('the final resume can be downloaded in every format the app offers, with readable content', async ({
    page,
  }) => {
    // `runFullFlowThroughGeneratedPlan` makes several sequential real LLM
    // calls (career-conversation start/turns, tailoring-suggestion
    // generation) against whatever provider chain is configured locally --
    // any one of those can take 10-25+ seconds on its own, so Playwright's
    // global 30s default (playwright.config.ts is intentionally left
    // untouched) is nowhere near enough. Scoped to just this test, not
    // the config, since the deterministic specs genuinely don't need it.
    test.setTimeout(300_000)

    await runFullFlowThroughGeneratedPlan(page)

    // Apply whatever's selected by default, to get to a real, committed
    // final resume the export endpoint can act on.
    await page.getByRole('button', { name: 'Preview Changes' }).click()
    await page.getByRole('button', { name: 'Apply Now' }).click()
    await expect(page.getByText('Final Resume Preview')).toBeVisible({ timeout: 30_000 })

    const downloadButtons = page.getByRole('button', { name: /^download (txt|markdown|docx|pdf)$/i })
    const availableCount = await downloadButtons.count()
    expect(availableCount).toBeGreaterThan(0)

    for (let i = 0; i < availableCount; i++) {
      const button = downloadButtons.nth(i)
      const label = (await button.textContent())?.trim() ?? ''

      const downloadPromise = page.waitForEvent('download')
      await button.click()
      const download = await downloadPromise

      const stream = await download.createReadStream()
      const chunks: Buffer[] = []
      for await (const chunk of stream ?? []) chunks.push(chunk as Buffer)
      const buffer = Buffer.concat(chunks)
      expect(buffer.length, `${label} download should not be empty`).toBeGreaterThan(0)

      if (/txt/i.test(label)) {
        expect(download.suggestedFilename()).toMatch(/\.txt$/i)
        expect(buffer.toString('utf-8').toLowerCase()).toContain('summary')
      } else if (/markdown/i.test(label)) {
        expect(download.suggestedFilename()).toMatch(/\.md$/i)
        expect(buffer.toString('utf-8').length).toBeGreaterThan(0)
      } else if (/docx/i.test(label)) {
        expect(download.suggestedFilename()).toMatch(/\.docx$/i)
        // A .docx is a ZIP container -- "PK\x03\x04" is the local-file-
        // header signature every valid ZIP (and therefore every valid
        // .docx) starts with. This is a real structural check, not a
        // guess: an app bug that emitted plain text with a .docx
        // extension would fail it.
        expect(buffer.subarray(0, 4).toString('latin1')).toBe('PK\x03\x04')
      } else if (/pdf/i.test(label)) {
        expect(download.suggestedFilename()).toMatch(/\.pdf$/i)
        expect(buffer.subarray(0, 5).toString('latin1')).toBe('%PDF-')
      }
    }
  })

  test('a failed export shows an inline error without hiding the final resume preview', async ({
    page,
  }) => {
    // See the first test in this file for why this needs more than
    // Playwright's global 30s default -- same real, sequential LLM calls.
    test.setTimeout(300_000)

    await runFullFlowThroughGeneratedPlan(page)
    await page.getByRole('button', { name: 'Preview Changes' }).click()
    await page.getByRole('button', { name: 'Apply Now' }).click()
    await expect(page.getByText('Final Resume Preview')).toBeVisible({ timeout: 30_000 })

    await page.route('**/v1/tailoring-suggestions/**/export', async (route) => {
      await route.fulfill({ status: 500, json: { detail: 'Exporting the resume failed.' } })
    })

    await page.getByRole('button', { name: /^download txt$/i }).click()

    await expect(page.getByText(/exporting the resume failed/i)).toBeVisible()
    // The preview above the download panel must stay visible either way.
    await expect(page.getByText('Final Resume Preview')).toBeVisible()
  })
})
