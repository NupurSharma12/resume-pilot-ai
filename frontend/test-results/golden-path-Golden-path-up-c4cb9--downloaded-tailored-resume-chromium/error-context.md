# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: golden-path.spec.ts >> Golden path: upload through download >> a candidate can go from resume upload to a downloaded tailored resume
- Location: e2e/golden-path.spec.ts:24:3

# Error details

```
Error: expect(locator).toBeVisible() failed

Locator: getByPlaceholder('Share your answer…')
Expected: visible
Timeout: 45000ms
Error: element(s) not found

Call log:
  - Expect "toBeVisible" with timeout 45000ms
  - waiting for getByPlaceholder('Share your answer…')

```

```yaml
- complementary:
  - text: ResumePilotAI
  - navigation:
    - link "Resume":
      - /url: /resume
    - link "Job Description":
      - /url: /job-description
    - link "Dashboard":
      - /url: /
    - link "Tailored Resume":
      - /url: /tailored-resume
    - link "History":
      - /url: /history
    - link "Settings":
      - /url: /settings
  - paragraph: CURRENT CANDIDATE
  - text: NS
  - paragraph: Nupur Sharma
  - text: Adobe 13 yrs Overall Match 0% Weak Match
- main:
  - heading "Career Conversation" [level=1]
  - paragraph: A recruiter-style conversation to recover missing evidence for this role
  - heading "Conversation didn't load" [level=2]
  - paragraph: Could not reach the conversation service. Is the backend running?
  - button "Try Again"
- button "Help"
```

# Test source

```ts
  1   | // Shared real-browser flow, used by the specs that need to be genuinely
  2   | // live (golden-path, downloads): upload -> JD -> analyze -> career
  3   | // conversation -> generate tailoring suggestions. Nothing here seeds
  4   | // state or mocks network calls -- every step is a real DOM interaction
  5   | // against the real backend and whatever LLM provider chain is configured
  6   | // (see this repo's .env; MAX_CONVERSATION_TURNS=8 on the backend bounds
  7   | // the conversation loop below regardless of provider).
  8   | import { expect, type Page } from '@playwright/test'
  9   | import path from 'node:path'
  10  | import { fileURLToPath } from 'node:url'
  11  | 
  12  | const __dirname = path.dirname(fileURLToPath(import.meta.url))
  13  | export const SAMPLE_RESUME_PATH = path.join(__dirname, '../fixtures/sample-resume.txt')
  14  | export const SAMPLE_JOB_DESCRIPTION_TEXT =
  15  |   'We are hiring a Senior Full-Stack Engineer with strong TypeScript, React, and people-management experience. The ideal candidate has led cross-functional engineering teams and mentored junior engineers.'
  16  | 
  17  | const MAX_CONVERSATION_TURNS = 8
  18  | 
  19  | // Uploads the resume file and pastes the job description, leaving the
  20  | // "Analyze Resume" CTA enabled -- does not click it, so callers can
  21  | // assert on the enabled state first if they want to.
  22  | export async function uploadResumeAndJobDescription(page: Page): Promise<void> {
  23  |   await page.goto('/')
  24  |   await page.locator('input[type="file"]').first().setInputFiles(SAMPLE_RESUME_PATH)
  25  |   // Client-side text extraction (pdfjs-dist/mammoth) runs even for a
  26  |   // plain .txt file -- wait for the "ready" checkmark row instead of a
  27  |   // fixed delay.
  28  |   await expect(page.getByText('sample-resume.txt')).toBeVisible()
  29  | 
  30  |   await page
  31  |     .getByPlaceholder('Paste the Job Description here...')
  32  |     .fill(SAMPLE_JOB_DESCRIPTION_TEXT)
  33  | 
  34  |   await expect(page.getByRole('button', { name: 'Analyze Resume' })).toBeEnabled()
  35  | }
  36  | 
  37  | // Runs the real analysis call and waits for the results panel.
  38  | export async function runResumeAnalysis(page: Page): Promise<void> {
  39  |   await page.getByRole('button', { name: 'Analyze Resume' }).click()
  40  |   // "MATCH SCORE" is a fixed UI label next to the LLM-generated score --
  41  |   // content-agnostic, since the exact score/wording varies by provider.
  42  |   await expect(page.getByText('MATCH SCORE')).toBeVisible({ timeout: 45_000 })
  43  | }
  44  | 
  45  | // Starts (or resumes) the Career Conversation and answers questions with
  46  | // a generic-but-substantive reply until the backend marks it complete --
  47  | // bounded to MAX_CONVERSATION_TURNS so this can never hang even if the
  48  | // live model keeps asking for more detail.
  49  | export async function completeCareerConversation(page: Page): Promise<void> {
  50  |   await page.getByRole('button', { name: 'Start Career Conversation' }).click()
  51  |   await expect(page).toHaveURL(/\/career-conversation$/)
  52  | 
  53  |   for (let turn = 0; turn < MAX_CONVERSATION_TURNS; turn++) {
  54  |     const completeHeading = page.getByRole('heading', { name: /career conversation complete/i })
  55  |     if (await completeHeading.isVisible().catch(() => false)) return
  56  | 
  57  |     const answerBox = page.getByPlaceholder('Share your answer…')
> 58  |     await expect(answerBox).toBeVisible({ timeout: 45_000 })
      |                             ^ Error: expect(locator).toBeVisible() failed
  59  |     await answerBox.fill(
  60  |       'I led a team of 4 engineers migrating a legacy billing system to a new stack, ' +
  61  |         'mentoring two junior engineers along the way and coordinating with product and design.',
  62  |     )
  63  |     await page.getByRole('button', { name: 'Continue' }).click()
  64  |     // The textarea is reused across turns (disabled, then re-enabled with
  65  |     // the next question or replaced by the completion card) rather than
  66  |     // unmounted -- waiting for it to detach never resolves. "Sending…"
  67  |     // (shown only while this turn's request is in flight) disappearing
  68  |     // either way is the reliable per-turn boundary.
  69  |     await expect(page.getByRole('button', { name: 'Sending…' })).toHaveCount(0, {
  70  |       timeout: 45_000,
  71  |     })
  72  |   }
  73  | 
  74  |   await expect(page.getByRole('heading', { name: /career conversation complete/i })).toBeVisible()
  75  | }
  76  | 
  77  | // Navigates to the Tailored Resume page and generates a real suggestion
  78  | // plan, waiting for the review list to render.
  79  | export async function generateTailoringPlan(page: Page): Promise<void> {
  80  |   await page
  81  |     .getByRole('button', { name: /generate tailoring plan|review suggestions|view tailored resume/i })
  82  |     .click()
  83  |   await expect(page).toHaveURL(/\/tailored-resume$/)
  84  | 
  85  |   const generateButton = page.getByRole('button', { name: 'Generate Tailoring Plan' })
  86  |   if (await generateButton.isVisible().catch(() => false)) {
  87  |     await generateButton.click()
  88  |   }
  89  |   // Generation is a multi-call sequence (a Planner call, then one Rewrite
  90  |   // call per suggestion -- see TailoringSuggestionWorkflow), genuinely
  91  |   // slower than a single LLM round trip; a generous timeout here reflects
  92  |   // that real cost, not a bug in the wait itself.
  93  |   await expect(page.getByRole('heading', { name: 'Review Suggestions' })).toBeVisible({
  94  |     timeout: 120_000,
  95  |   })
  96  |   await expect(page.getByRole('checkbox').first()).toBeVisible()
  97  | }
  98  | 
  99  | // The full golden path up through a generated (not yet applied) plan --
  100 | // shared by golden-path.spec.ts and downloads.spec.ts so both start from
  101 | // the same real state without duplicating every step.
  102 | export async function runFullFlowThroughGeneratedPlan(page: Page): Promise<void> {
  103 |   await uploadResumeAndJobDescription(page)
  104 |   await runResumeAnalysis(page)
  105 |   await completeCareerConversation(page)
  106 |   await generateTailoringPlan(page)
  107 | }
  108 | 
```