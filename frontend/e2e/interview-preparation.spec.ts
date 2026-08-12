// Interview Preparation as a first-class part of the active Job
// Preparation flow (not just History -- see history.spec.ts for that
// side): reachable from the Sidebar immediately after Resume Analysis,
// without requiring Career Conversation or Tailoring. Deterministic
// throughout -- a seeded session (see fixtures/session.ts) plus mocked
// GET/POST responses (page.route), matching this suite's existing
// convention (comparator.spec.ts/history.spec.ts et al.), never a live
// LLM call.
import { test, expect } from '@playwright/test'
import { seedResumeSession } from './fixtures/session'

const JOB_PREPARATION_ID = 'e2e-job-preparation-1'

const emptyDetail = {
  id: JOB_PREPARATION_ID,
  job_title: 'Senior Full-Stack Engineer',
  company: 'Acme Corp',
  job_description: 'We are hiring a Senior Full-Stack Engineer.',
  resume_name: 'Backend Engineer Resume',
  status: 'active',
  created_at: '2026-08-01T09:00:00Z',
  updated_at: '2026-08-01T09:00:00Z',
  checkpoints: {
    initial_analysis_completed_at: '2026-08-01T09:00:00Z',
    career_conversation_completed_at: null,
    tailoring_plan_completed_at: null,
    applied_at: null,
    post_apply_analysis_completed_at: null,
  },
  analysis_result: null,
  career_conversation: null,
  tailoring_plan: null,
  applied_resume_text: null,
  post_apply_analysis: null,
  interview_preparation: null,
}

const generatedGuide = {
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
  behavioral_questions: [],
  generated_at: '2026-08-13T10:00:00Z',
  stage: 'initial',
}

test.describe('Interview Preparation Sidebar gating', () => {
  test('is disabled with no resume analysis, and enabled once one exists', async ({ page }) => {
    await page.goto('/')

    const disabledItem = page.getByText('Interview Preparation', { exact: true })
    await expect(disabledItem).toBeVisible()
    await expect(page.getByRole('link', { name: 'Interview Preparation' })).toHaveCount(0)

    await seedResumeSession(page, { jobPreparationId: JOB_PREPARATION_ID })
    await page.route(`**/v1/job-preparations/${JOB_PREPARATION_ID}`, async (route) => {
      await route.fulfill({ json: emptyDetail })
    })
    await page.goto('/')

    await expect(page.getByRole('link', { name: 'Interview Preparation' })).toBeVisible()
  })
})

test.describe('Interview Preparation active flow', () => {
  test('is reachable right after analysis, and generates a guide without Career Conversation or Tailoring', async ({
    page,
  }) => {
    await seedResumeSession(page, { jobPreparationId: JOB_PREPARATION_ID })
    await page.route(`**/v1/job-preparations/${JOB_PREPARATION_ID}`, async (route) => {
      await route.fulfill({ json: emptyDetail })
    })
    await page.route(
      `**/v1/job-preparations/${JOB_PREPARATION_ID}/interview-preparation`,
      async (route) => {
        await route.fulfill({ json: generatedGuide })
      },
    )

    await page.goto('/')
    await page.getByRole('link', { name: 'Interview Preparation' }).click()
    await expect(page).toHaveURL(/\/interview-preparation$/)

    await expect(page.getByText(/no interview preparation guide yet/i)).toBeVisible()
    await page.getByRole('button', { name: 'Generate Interview Preparation' }).click()

    await expect(
      page.getByText('Design a distributed document-analysis pipeline.'),
    ).toBeVisible()
    await expect(page.getByText('Merge Intervals')).toBeVisible()
    await expect(page.getByText('Initial preparation')).toBeVisible()
  })

  test('reflects the persisted stage label for an already-enriched guide, and survives a reload', async ({
    page,
  }) => {
    await seedResumeSession(page, { jobPreparationId: JOB_PREPARATION_ID })
    await page.route(`**/v1/job-preparations/${JOB_PREPARATION_ID}`, async (route) => {
      await route.fulfill({
        json: {
          ...emptyDetail,
          interview_preparation: { ...generatedGuide, stage: 'career_conversation_enriched' },
        },
      })
    })

    await page.goto('/interview-preparation')

    await expect(page.getByText('Updated from Career Conversation')).toBeVisible()
    await expect(
      page.getByRole('button', { name: 'Update Interview Preparation' }),
    ).toBeVisible()

    // Persisted server-side (not in sessionStorage) -- a reload re-fetches
    // the same guide from the backend rather than losing it.
    await page.reload()
    await expect(page.getByText('Updated from Career Conversation')).toBeVisible()
  })
})
