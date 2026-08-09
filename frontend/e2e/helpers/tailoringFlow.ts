// Shared real-browser flow, used by the specs that need to be genuinely
// live (golden-path, downloads): upload -> JD -> analyze -> career
// conversation -> generate tailoring suggestions. Nothing here seeds
// state or mocks network calls -- every step is a real DOM interaction
// against the real backend and whatever LLM provider chain is configured
// (see this repo's .env; MAX_CONVERSATION_TURNS=8 on the backend bounds
// the conversation loop below regardless of provider).
import { expect, type Page } from '@playwright/test'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
export const SAMPLE_RESUME_PATH = path.join(__dirname, '../fixtures/sample-resume.txt')
export const SAMPLE_JOB_DESCRIPTION_TEXT =
  'We are hiring a Senior Full-Stack Engineer with strong TypeScript, React, and people-management experience. The ideal candidate has led cross-functional engineering teams and mentored junior engineers.'

const MAX_CONVERSATION_TURNS = 8

// Uploads the resume file and pastes the job description, leaving the
// "Analyze Resume" CTA enabled -- does not click it, so callers can
// assert on the enabled state first if they want to.
export async function uploadResumeAndJobDescription(page: Page): Promise<void> {
  await page.goto('/')
  await page.locator('input[type="file"]').first().setInputFiles(SAMPLE_RESUME_PATH)
  // Client-side text extraction (pdfjs-dist/mammoth) runs even for a
  // plain .txt file -- wait for the "ready" checkmark row instead of a
  // fixed delay.
  await expect(page.getByText('sample-resume.txt')).toBeVisible()

  await page
    .getByPlaceholder('Paste the Job Description here...')
    .fill(SAMPLE_JOB_DESCRIPTION_TEXT)

  await expect(page.getByRole('button', { name: 'Analyze Resume' })).toBeEnabled()
}

// Runs the real analysis call and waits for the results panel.
export async function runResumeAnalysis(page: Page): Promise<void> {
  await page.getByRole('button', { name: 'Analyze Resume' }).click()
  // "MATCH SCORE" is a fixed UI label next to the LLM-generated score --
  // content-agnostic, since the exact score/wording varies by provider.
  await expect(page.getByText('MATCH SCORE')).toBeVisible({ timeout: 45_000 })
}

// Starts (or resumes) the Career Conversation and answers questions with
// a generic-but-substantive reply until the backend marks it complete --
// bounded to MAX_CONVERSATION_TURNS so this can never hang even if the
// live model keeps asking for more detail.
export async function completeCareerConversation(page: Page): Promise<void> {
  await page.getByRole('button', { name: 'Start Career Conversation' }).click()
  await expect(page).toHaveURL(/\/career-conversation$/)

  for (let turn = 0; turn < MAX_CONVERSATION_TURNS; turn++) {
    const completeHeading = page.getByRole('heading', { name: /career conversation complete/i })
    if (await completeHeading.isVisible().catch(() => false)) return

    const answerBox = page.getByPlaceholder('Share your answer…')
    await expect(answerBox).toBeVisible({ timeout: 45_000 })
    await answerBox.fill(
      'I led a team of 4 engineers migrating a legacy billing system to a new stack, ' +
        'mentoring two junior engineers along the way and coordinating with product and design.',
    )
    await page.getByRole('button', { name: 'Continue' }).click()
    // The textarea is reused across turns (disabled, then re-enabled with
    // the next question or replaced by the completion card) rather than
    // unmounted -- waiting for it to detach never resolves. "Sending…"
    // (shown only while this turn's request is in flight) disappearing
    // either way is the reliable per-turn boundary.
    await expect(page.getByRole('button', { name: 'Sending…' })).toHaveCount(0, {
      timeout: 45_000,
    })
  }

  await expect(page.getByRole('heading', { name: /career conversation complete/i })).toBeVisible()
}

// Navigates to the Tailored Resume page and generates a real suggestion
// plan, waiting for the review list to render.
export async function generateTailoringPlan(page: Page): Promise<void> {
  await page
    .getByRole('button', { name: /generate tailoring plan|review suggestions|view tailored resume/i })
    .click()
  await expect(page).toHaveURL(/\/tailored-resume$/)

  const generateButton = page.getByRole('button', { name: 'Generate Tailoring Plan' })
  if (await generateButton.isVisible().catch(() => false)) {
    await generateButton.click()
  }
  // Generation is a multi-call sequence (a Planner call, then one Rewrite
  // call per suggestion -- see TailoringSuggestionWorkflow), genuinely
  // slower than a single LLM round trip; a generous timeout here reflects
  // that real cost, not a bug in the wait itself.
  await expect(page.getByRole('heading', { name: 'Review Suggestions' })).toBeVisible({
    timeout: 120_000,
  })
  await expect(page.getByRole('checkbox').first()).toBeVisible()
}

// The full golden path up through a generated (not yet applied) plan --
// shared by golden-path.spec.ts and downloads.spec.ts so both start from
// the same real state without duplicating every step.
export async function runFullFlowThroughGeneratedPlan(page: Page): Promise<void> {
  await uploadResumeAndJobDescription(page)
  await runResumeAnalysis(page)
  await completeCareerConversation(page)
  await generateTailoringPlan(page)
}
