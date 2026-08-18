// History Resumability: "Continue" rehydrates the active session from a
// past JobPreparation's persisted state and navigates to the right next
// stage, per the design review. Entirely mocked backend (GET
// /v1/job-preparations[/{id}]) -- deterministic, no live LLM call, same
// convention as history.spec.ts. Covers Continue from each of the major
// checkpoint stages: analysis-only, Career-Conversation-complete, a
// generated (unapplied) tailoring plan, and an applied-but-not-yet-
// reanalyzed tailored resume.
import { test, expect } from '@playwright/test'

const RESUME_TEXT = 'SUMMARY\nSenior backend engineer with distributed systems experience.'
const JOB_DESCRIPTION_TEXT = 'We are hiring a Senior Backend Engineer.'

const baseCheckpoints = {
  initial_analysis_completed_at: '2026-08-01T10:00:00Z',
  career_conversation_completed_at: null as string | null,
  tailoring_plan_completed_at: null as string | null,
  applied_at: null as string | null,
  post_apply_analysis_completed_at: null as string | null,
}

const analysisResult = {
  overall_assessment: {
    overall_score: 78,
    hiring_recommendation: { decision: 'Strong Match', reason: 'Solid overlap.' },
    summary: 'A strong candidate overall.',
  },
  skill_matches: [],
  matching_projects: [],
  strengths: [],
  weaknesses: [],
  resume_improvements: [],
}

function summaryFor(id: string, jobTitle: string, checkpoints: typeof baseCheckpoints) {
  return {
    id,
    job_title: jobTitle,
    company: 'Acme Corp',
    resume_name: 'Senior Backend Engineer Resume',
    created_at: '2026-08-01T09:00:00Z',
    updated_at: '2026-08-12T09:00:00Z',
    checkpoints,
  }
}

function detailFor(summary: ReturnType<typeof summaryFor>, overrides: Record<string, unknown>) {
  return {
    ...summary,
    job_description: JOB_DESCRIPTION_TEXT,
    resume_text: RESUME_TEXT,
    status: 'active',
    analysis_result: analysisResult,
    career_conversation: null,
    tailoring_plan: null,
    applied_resume_text: null,
    post_apply_analysis: null,
    interview_preparation: null,
    ...overrides,
  }
}

const analysisOnly = summaryFor('e2e-jp-analysis', 'Continue Analysis Only', baseCheckpoints)
const analysisOnlyDetail = detailFor(analysisOnly, {})

const conversationComplete = summaryFor('e2e-jp-conversation', 'Continue Conversation Complete', {
  ...baseCheckpoints,
  career_conversation_completed_at: '2026-08-01T10:05:00Z',
})
const conversationCompleteDetail = detailFor(conversationComplete, {
  career_conversation: {
    session_id: 'e2e-conv-session-1',
    status: 'complete',
    history: [
      {
        topic: 'Leadership',
        question: 'Tell me about a time you led a project.',
        answer: 'I led a migration to a new platform.',
        assistant_response: null,
      },
    ],
    current_question: null,
    stop_reason: 'Enough evidence recovered.',
  },
})

const generatedPlan = {
  plan_id: 'e2e-plan-1',
  suggestions: [
    {
      suggestion_id: 'e2e-suggestion-0',
      target_section_id: 'section-1',
      target_item_id: 'item-1',
      operation: 'append',
      current_text: 'Python',
      suggested_text: 'Python, TypeScript',
      reason: 'The job description asks for TypeScript.',
      evidence_ids: [],
      evidence_sources: [],
      confidence: 0.9,
      selected_by_default: true,
      validation_status: 'supported_by_original_resume',
      validation_issues: [],
      conflicts_with: [],
    },
  ],
  available_export_formats: ['txt'],
  default_export_format: 'txt',
}

const tailoringPlanGenerated = summaryFor('e2e-jp-tailoring', 'Continue Tailoring Plan', {
  ...baseCheckpoints,
  career_conversation_completed_at: '2026-08-01T10:05:00Z',
  tailoring_plan_completed_at: '2026-08-01T10:10:00Z',
})
const tailoringPlanGeneratedDetail = detailFor(tailoringPlanGenerated, {
  career_conversation: conversationCompleteDetail.career_conversation,
  tailoring_plan: { generated_plan: generatedPlan, selection: null },
})

const applied = summaryFor('e2e-jp-applied', 'Continue Applied Not Reanalyzed', {
  ...baseCheckpoints,
  career_conversation_completed_at: '2026-08-01T10:05:00Z',
  tailoring_plan_completed_at: '2026-08-01T10:10:00Z',
  applied_at: '2026-08-01T10:15:00Z',
})
const appliedDetail = detailFor(applied, {
  career_conversation: conversationCompleteDetail.career_conversation,
  tailoring_plan: {
    generated_plan: generatedPlan,
    selection: { selected_suggestion_ids: ['e2e-suggestion-0'], edited_texts: {} },
  },
  applied_resume_text: 'SUMMARY\nSenior backend engineer with distributed systems experience.\nPython, TypeScript',
})

// A plan the AI generated with zero suggestions: a valid, successful
// outcome (the resume already aligns well with the job description), not
// yet acted on -- distinct from `applied` above, whose plan has a real
// suggestion and an `applied_resume_text`.
const generatedPlanNoChanges = {
  plan_id: 'e2e-plan-no-changes',
  suggestions: [],
  available_export_formats: ['txt'],
  default_export_format: 'txt',
}
const tailoringPlanNoChanges = summaryFor('e2e-jp-no-changes', 'Continue No Changes Recommended', {
  ...baseCheckpoints,
  career_conversation_completed_at: '2026-08-01T10:05:00Z',
  tailoring_plan_completed_at: '2026-08-01T10:10:00Z',
})
const tailoringPlanNoChangesDetail = detailFor(tailoringPlanNoChanges, {
  career_conversation: conversationCompleteDetail.career_conversation,
  tailoring_plan: { generated_plan: generatedPlanNoChanges, selection: null },
})

const allSummaries = [analysisOnly, conversationComplete, tailoringPlanGenerated, applied, tailoringPlanNoChanges]
const detailsById: Record<string, unknown> = {
  [analysisOnly.id]: analysisOnlyDetail,
  [conversationComplete.id]: conversationCompleteDetail,
  [tailoringPlanGenerated.id]: tailoringPlanGeneratedDetail,
  [applied.id]: appliedDetail,
  [tailoringPlanNoChanges.id]: tailoringPlanNoChangesDetail,
}

test.describe('History Resumability: Continue', () => {
  test.beforeEach(async ({ page }) => {
    await page.route('**/v1/job-preparations*', async (route) => {
      if (route.request().method() !== 'GET') {
        await route.continue()
        return
      }
      // Mirrors the real backend's server-side search (case-insensitive
      // substring match against job_title) -- History's search box now
      // round-trips through this route instead of filtering client-side,
      // so `openContinueDialog` below (which searches to narrow down to
      // one row before clicking) needs the mock to actually filter too.
      const search = new URL(route.request().url()).searchParams.get('search')
      const items = search
        ? allSummaries.filter((s) => s.job_title.toLowerCase().includes(search.toLowerCase()))
        : allSummaries
      await route.fulfill({ json: { items, total: items.length, limit: 10, offset: 0 } })
    })
    for (const summary of allSummaries) {
      await page.route(`**/v1/job-preparations/${summary.id}`, async (route) => {
        await route.fulfill({ json: detailsById[summary.id] })
      })
    }
    // No live conversation session survives across these mocked
    // preparations -- generation falls back to the persisted transcript
    // (see TailoredResumePage's getCareerConversationOrPersisted).
    await page.route('**/v1/career-conversation/e2e-conv-session-1', async (route) => {
      await route.fulfill({ status: 404, json: { detail: 'Not found.' } })
    })
    await page.route('**/v1/career-conversation', async (route) => {
      if (route.request().method() !== 'POST') {
        await route.continue()
        return
      }
      await route.fulfill({
        json: {
          session_id: 'e2e-new-conv-session',
          status: 'in_progress',
          history: [],
          current_question: {
            topic: 'Leadership',
            question: 'Tell me about a time you led a project.',
            evidence_goal: 'Assess leadership evidence.',
            estimated_impact: 'high',
            assistant_response: null,
          },
          stop_reason: null,
        },
      })
    })
  })

  async function openContinueDialog(page: import('@playwright/test').Page, jobTitle: string) {
    await page.goto('/history')
    const main = page.locator('main')
    await expect(main.getByText(jobTitle)).toBeVisible()
    await page.getByLabel('Search job preparations').fill(jobTitle)
    // Search is server-side and debounced (see HistoryPage) -- give the
    // debounced request time to land and narrow the list down to one
    // row before clicking, rather than racing it.
    const continueButton = main.getByRole('button', { name: 'Continue Preparation' })
    await expect(continueButton).toHaveCount(1)
    await continueButton.click()
    await expect(page.getByText('Continue this preparation?')).toBeVisible()
  }

  test('continuing an analysis-only preparation lands on Career Conversation', async ({ page }) => {
    await openContinueDialog(page, analysisOnly.job_title)
    await page.getByRole('dialog').getByRole('button', { name: 'Continue' }).click()

    await expect(page).toHaveURL(/\/career-conversation$/)
    // No persisted transcript to restore, so a brand-new conversation
    // starts, grounded in the rehydrated resume/JD/analysis.
    await expect(page.getByText('Tell me about a time you led a project.')).toBeVisible()
  })

  test('continuing a Career-Conversation-complete preparation lands on Tailored Resume with no plan generated yet', async ({
    page,
  }) => {
    await openContinueDialog(page, conversationComplete.job_title)
    await page.getByRole('dialog').getByRole('button', { name: 'Continue' }).click()

    await expect(page).toHaveURL(/\/tailored-resume$/)
    await expect(page.getByRole('button', { name: 'Generate Tailoring Plan' })).toBeVisible()
  })

  test('continuing a preparation with a generated tailoring plan lands on Tailored Resume with suggestions already shown', async ({
    page,
  }) => {
    await openContinueDialog(page, tailoringPlanGenerated.job_title)
    await page.getByRole('dialog').getByRole('button', { name: 'Continue' }).click()

    await expect(page).toHaveURL(/\/tailored-resume$/)
    await expect(page.getByText('The job description asks for TypeScript.')).toBeVisible()
    // Exact match: 'Generate Tailoring Plan' is a substring of the CTA that
    // *does* render here, 'Regenerate Tailoring Plan' (see
    // TailoredResumePage's shared instructionsCard).
    await expect(
      page.getByRole('button', { name: 'Generate Tailoring Plan', exact: true }),
    ).not.toBeVisible()
    await expect(page.getByRole('button', { name: 'Regenerate Tailoring Plan' })).toBeVisible()
  })

  test('continuing a preparation with a zero-suggestion plan offers "Continue with Current Resume", distinct from awaiting-review and no-plan states', async ({
    page,
  }) => {
    await openContinueDialog(page, tailoringPlanNoChanges.job_title)
    await page.getByRole('dialog').getByRole('button', { name: 'Continue' }).click()

    await expect(page).toHaveURL(/\/tailored-resume$/)
    await expect(page.getByText(/no changes recommended/i)).toBeVisible()
    await expect(page.getByRole('button', { name: 'Continue with Current Resume' })).toBeVisible()
    // Not the "no plan yet" state, and not the suggestion-review UI.
    await expect(
      page.getByRole('button', { name: 'Generate Tailoring Plan', exact: true }),
    ).not.toBeVisible()
    await expect(page.getByRole('heading', { name: 'Review Suggestions' })).not.toBeVisible()

    let applyRequestBody: Record<string, unknown> | null = null
    await page.route('**/v1/tailoring-suggestions/e2e-plan-no-changes/apply', async (route) => {
      applyRequestBody = route.request().postDataJSON()
      await route.fulfill({
        json: {
          applied_suggestion_ids: [],
          final_resume_text: RESUME_TEXT,
          final_validation: { is_valid: true, messages: [] },
        },
      })
    })

    await page.getByRole('button', { name: 'Continue with Current Resume' }).click()

    await expect(page.getByText(/final resume preview/i)).toBeVisible()
    await expect(page.getByRole('button', { name: /re-analyze & compare/i })).toBeVisible()
    await expect(page.getByRole('button', { name: /^download txt$/i })).not.toBeVisible()
    await expect(page.getByText(/no changes recommended/i)).not.toBeVisible()
    expect((applyRequestBody as unknown as { selected_suggestion_ids?: string[] })?.selected_suggestion_ids).toEqual(
      [],
    )
  })

  test('continuing an applied-but-not-reanalyzed preparation lands on Tailored Resume showing the final resume and a Re-analyze prompt', async ({
    page,
  }) => {
    await openContinueDialog(page, applied.job_title)
    await page.getByRole('dialog').getByRole('button', { name: 'Continue' }).click()

    await expect(page).toHaveURL(/\/tailored-resume$/)
    await expect(page.getByText(/final resume preview/i)).toBeVisible()
    await expect(page.getByRole('button', { name: /re-analyze & compare/i })).toBeVisible()
    await expect(page.getByRole('button', { name: /^download txt$/i })).not.toBeVisible()
  })

  test('Cancel closes the dialog without navigating away from History', async ({ page }) => {
    await openContinueDialog(page, conversationComplete.job_title)
    await page.getByRole('button', { name: 'Cancel' }).click()

    await expect(page.getByText('Continue this preparation?')).not.toBeVisible()
    await expect(page).toHaveURL(/\/history$/)
  })
})
