// The History feature: durable JobPreparation checkpoints, surfaced in
// the frontend. Two concerns, two test groups:
//
// 1. `job_preparation_id` propagation -- proving the id POST /v1/analyze
//    returns actually reaches the later /career-conversation and
//    /tailoring-suggestions requests, which is what makes their own
//    durable history attach to the same JobPreparation (see
//    docs/persistent-backend-workflow-state.md). Drives the real upload
//    UI with every backend call mocked via `page.route` -- deterministic,
//    no live LLM call, matching this suite's existing convention
//    (comparator.spec.ts/selection-phased-apply.spec.ts et al.).
//
// 2. The History screen itself -- list rendering, opening a preparation,
//    and rendering its checkpoint state honestly (partial progress never
//    shown as complete) -- backed entirely by mocked
//    GET /v1/job-preparations[/{id}] responses, since HistoryPage reads
//    only from the backend, never from frontend session state.
import { test, expect } from '@playwright/test'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { fixtureResumeAnalysis } from './fixtures/session'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const SAMPLE_RESUME_PATH = path.join(__dirname, 'fixtures/sample-resume.txt')
const SAMPLE_JOB_DESCRIPTION_TEXT =
  'We are hiring a Senior Full-Stack Engineer with strong TypeScript and React experience.'
const JOB_PREPARATION_ID = 'e2e-job-preparation-1'

test.describe('job_preparation_id propagation', () => {
  test('the id POST /v1/analyze returns is threaded through to career-conversation and tailoring-suggestions', async ({
    page,
  }) => {
    await page.route('**/v1/analyze', async (route) => {
      await route.fulfill({ json: { ...fixtureResumeAnalysis, job_preparation_id: JOB_PREPARATION_ID } })
    })

    const completedSession = {
      session_id: 'e2e-session-1',
      status: 'complete',
      history: [],
      current_question: null,
      stop_reason: 'Enough evidence recovered.',
    }
    let conversationRequestBody: Record<string, unknown> | null = null
    await page.route('**/v1/career-conversation', async (route) => {
      if (route.request().method() !== 'POST') {
        await route.continue()
        return
      }
      conversationRequestBody = route.request().postDataJSON()
      await route.fulfill({ json: completedSession })
    })
    // TailoredResumePage re-fetches the transcript by session id before
    // generating (it isn't held in shared frontend state, only the id
    // is) -- see suggestionRecovery/TailoredResumePage's `generate`.
    await page.route('**/v1/career-conversation/e2e-session-1', async (route) => {
      await route.fulfill({ json: completedSession })
    })

    let generateRequestBody: Record<string, unknown> | null = null
    await page.route('**/v1/tailoring-suggestions', async (route) => {
      if (route.request().method() !== 'POST') {
        await route.continue()
        return
      }
      generateRequestBody = route.request().postDataJSON()
      await route.fulfill({
        json: {
          plan_id: 'e2e-plan-1',
          suggestions: [],
          available_export_formats: ['txt'],
          default_export_format: 'txt',
        },
      })
    })

    await page.goto('/')
    await page.locator('input[type="file"]').first().setInputFiles(SAMPLE_RESUME_PATH)
    await expect(page.getByText('sample-resume.txt')).toBeVisible()
    await page.getByPlaceholder('Paste the Job Description here...').fill(SAMPLE_JOB_DESCRIPTION_TEXT)
    await page.getByRole('button', { name: 'Analyze Resume' }).click()
    await expect(page.getByText('MATCH SCORE')).toBeVisible()

    await page.getByRole('button', { name: 'Start Career Conversation' }).click()
    await expect(page).toHaveURL(/\/career-conversation$/)

    await expect(page.getByRole('heading', { name: /career conversation complete/i })).toBeVisible()
    expect((conversationRequestBody as unknown as { job_preparation_id?: string })?.job_preparation_id).toBe(
      JOB_PREPARATION_ID,
    )

    await page
      .getByRole('button', { name: /generate tailoring plan|review suggestions|view tailored resume/i })
      .click()
    await expect(page).toHaveURL(/\/tailored-resume$/)
    await page.getByRole('button', { name: 'Generate Tailoring Plan' }).click()
    await expect(page.getByRole('heading', { name: 'Review Suggestions' })).toBeVisible()

    expect((generateRequestBody as unknown as { job_preparation_id?: string })?.job_preparation_id).toBe(
      JOB_PREPARATION_ID,
    )
  })
})

const partialSummary = {
  id: JOB_PREPARATION_ID,
  job_title: 'Senior Full-Stack Engineer',
  company: 'Acme Corp',
  resume_name: 'Backend Engineer Resume',
  created_at: '2026-08-01T09:00:00Z',
  updated_at: '2026-08-12T09:00:00Z',
  checkpoints: {
    initial_analysis_completed_at: '2026-08-01T09:00:00Z',
    career_conversation_completed_at: '2026-08-01T09:05:00Z',
    tailoring_plan_completed_at: null,
    applied_at: null,
    post_apply_analysis_completed_at: null,
  },
}

const partialDetail = {
  ...partialSummary,
  job_description: 'We are hiring a Senior Full-Stack Engineer.',
  status: 'active',
  analysis_result: {
    overall_assessment: { overall_score: 78, summary: 'Strong backend foundation.' },
  },
  career_conversation: { history: [{ topic: 'Leadership' }], stop_reason: 'Enough evidence.' },
  tailoring_plan: null,
  applied_resume_text: null,
  post_apply_analysis: null,
  interview_preparation: null,
}

const fixtureInterviewPreparation = {
  system_design_questions: [
    {
      question: 'Design a distributed document-analysis pipeline.',
      rationale: 'The resume shows large-scale backend systems experience.',
    },
  ],
  coding_questions: [
    {
      title: 'Merge Intervals',
      topic: 'Sorting',
      difficulty: 'medium',
      relevance: 'The role involves scheduling logic.',
    },
  ],
  behavioral_questions: [
    {
      question: 'Describe a time you led a migration.',
      source: 'career_conversation',
      context: 'Led a 4-engineer migration off a legacy monolith.',
    },
  ],
  generated_at: '2026-08-12T10:00:00Z',
}

test.describe('History screen', () => {
  test('shows partial checkpoint progress honestly in both the list and the opened preparation, and survives a reload', async ({
    page,
  }) => {
    await page.route('**/v1/job-preparations', async (route) => {
      await route.fulfill({ json: { items: [partialSummary] } })
    })
    await page.route(`**/v1/job-preparations/${JOB_PREPARATION_ID}`, async (route) => {
      await route.fulfill({ json: partialDetail })
    })

    await page.goto('/')
    await page.getByRole('link', { name: 'History' }).click()
    await expect(page).toHaveURL(/\/history$/)

    // Scoped to <main> throughout -- "Tailored Resume" (and other
    // checkpoint labels) also appear in the Sidebar's own nav, which
    // would otherwise make these locators ambiguous.
    const main = page.locator('main')

    await expect(main.getByText('Senior Full-Stack Engineer')).toBeVisible()
    await expect(main.getByText(/Acme Corp/)).toBeVisible()

    // Two checkpoints complete, three not -- never all five, since the
    // fixture only completed Initial Analysis and Career Conversation.
    await expect(main.getByText('Initial Analysis')).toBeVisible()
    await expect(main.getByText('Career Conversation')).toBeVisible()
    await expect(main.getByText('Tailoring Plan')).toBeVisible()
    await expect(main.getByText('Tailored Resume')).toBeVisible()
    await expect(main.getByText('Re-analysis')).toBeVisible()

    await main.getByText('Senior Full-Stack Engineer').click()

    await expect(main.getByText('78%')).toBeVisible()
    await expect(main.getByText('Strong backend foundation.')).toBeVisible()
    await expect(main.getByText('1 exchange recorded.')).toBeVisible()
    // Never fabricated: no Tailoring Plan/Tailored Resume/Re-analysis
    // section renders at all, since their payloads are null.
    await expect(main.getByRole('heading', { name: 'Tailoring Plan' })).not.toBeVisible()
    await expect(main.getByRole('heading', { name: 'Tailored Resume' })).not.toBeVisible()
    await expect(main.getByRole('heading', { name: 'Re-analysis' })).not.toBeVisible()

    // Reload -- History re-fetches from the (mocked) backend rather than
    // relying on any client-side state, so the same detail reappears
    // only once the user re-opens it; the persisted data itself survives
    // the reload because it was never client-side to begin with.
    await page.reload()
    await expect(main.getByText('Senior Full-Stack Engineer')).toBeVisible()
    await main.getByText('Senior Full-Stack Engineer').click()
    await expect(main.getByText('78%')).toBeVisible()
    await expect(main.getByText('Strong backend foundation.')).toBeVisible()
  })

  test('generates and displays an Interview Preparation guide, deterministically mocked', async ({
    page,
  }) => {
    await page.route('**/v1/job-preparations', async (route) => {
      await route.fulfill({ json: { items: [partialSummary] } })
    })
    await page.route(`**/v1/job-preparations/${JOB_PREPARATION_ID}`, async (route) => {
      await route.fulfill({ json: partialDetail })
    })
    await page.route(
      `**/v1/job-preparations/${JOB_PREPARATION_ID}/interview-preparation`,
      async (route) => {
        await route.fulfill({ json: fixtureInterviewPreparation })
      },
    )

    await page.goto('/')
    await page.getByRole('link', { name: 'History' }).click()
    await expect(page).toHaveURL(/\/history$/)

    const main = page.locator('main')
    await main.getByText('Senior Full-Stack Engineer').click()

    await expect(main.getByText(/no interview preparation guide yet/i)).toBeVisible()
    await main.getByRole('button', { name: 'Generate Interview Preparation' }).click()

    await expect(
      main.getByText('Design a distributed document-analysis pipeline.'),
    ).toBeVisible()
    await expect(main.getByText('Merge Intervals')).toBeVisible()
    await expect(main.getByText('Describe a time you led a migration.')).toBeVisible()
    await expect(main.getByText('From Career Conversation')).toBeVisible()
  })

  test('shows an empty state when there is no history yet', async ({ page }) => {
    await page.route('**/v1/job-preparations', async (route) => {
      await route.fulfill({ json: { items: [] } })
    })

    await page.goto('/history')

    await expect(page.getByText(/analysis history is coming soon/i)).toBeVisible()
  })
})
