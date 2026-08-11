// The Post-Apply Analysis Loop (see docs/features/postapply-analysis-
// loop.md): after a candidate applies tailoring changes, "Re-analyze &
// Compare" must present a truthful improved/unchanged/decreased verdict
// -- never assume applying suggestions means the resume improved.
// Deterministic: starts from an already-applied seeded session (see
// fixtures/session.ts) and mocks POST .../reanalyze (see
// helpers/mockPostApply.ts) -- no live LLM call, matching every other
// spec in this file's family (comparator/selection-phased-apply/
// refresh-recovery).
import { test, expect } from '@playwright/test'
import { fixtureResumeAnalysis, fixtureTailoringPlan, seedResumeSession } from './fixtures/session'
import { mockReanalyzeEndpoint, mockReanalyzeFailure } from './helpers/mockPostApply'
import { mockApplyEndpoint } from './helpers/mockApply'
import type { ReanalyzeResponse } from '../src/data/postApplyTypes'
import type { ResumeAnalysisResult } from '../src/data/types'

// The two score badges (before/after -- see PostApplyComparisonCard)
// render as plain sibling text nodes around an arrow icon with no
// separator, so their combined text content is the two numbers run
// together (e.g. "8085"). Asserting on that exact concatenation is the
// most direct way to prove *both* numbers are actually on screen,
// without over-specifying the icon/markup between them.
function scoreBadgeText(before: number, after: number): string {
  return `${before}${after}`
}

function withOverallScore(score: number): ResumeAnalysisResult {
  return {
    ...fixtureResumeAnalysis,
    overall_assessment: { ...fixtureResumeAnalysis.overall_assessment, overall_score: score },
  }
}

const BEFORE_SCORE = 80

test.describe('Post-Apply Analysis Loop', () => {
  test.beforeEach(async ({ page }) => {
    // Starts from an already-applied state -- this feature only makes
    // sense once a final resume exists, and repeating the full
    // select/preview/apply journey here would only duplicate
    // selection-phased-apply.spec.ts's own coverage of that mechanics.
    await seedResumeSession(page, {
      resumeAnalysis: withOverallScore(BEFORE_SCORE),
      tailoringSelections: ['suggestion-0'],
      finalTailoredResume: {
        finalResumeText:
          'SUMMARY\nBackend engineer with 5 years of experience.\n\nSKILLS\nPython, TypeScript\nDjango\n\nEXPERIENCE\nBuilt internal tools using Python and Django.\n',
        appliedSuggestionIds: ['suggestion-0'],
      },
      tailoringValidationReport: { is_valid: true, messages: [] },
    })
    await page.goto('/tailored-resume')
    await expect(page.getByText('Final Resume Preview')).toBeVisible()
  })

  test('Download is not available until a re-analysis has actually completed', async ({ page }) => {
    // The applied resume is on screen, but nothing has been re-analyzed
    // yet -- Download must not exist at all (not just be disabled/hidden
    // behind a toggle), per the enforced "Apply -> Re-analyze -> Compare
    // -> Download" flow (see docs/features/postapply-analysis-loop.md).
    await expect(page.getByRole('button', { name: /^download txt$/i })).not.toBeVisible()

    const response: ReanalyzeResponse = {
      after_analysis: withOverallScore(85),
      comparison: {
        score_before: 80,
        score_after: 85,
        score_delta: 5,
        status: 'improved',
        category_comparisons: [],
        strengths_gained: [],
        strengths_lost: [],
        weaknesses_resolved: [],
        weaknesses_remaining: [],
        new_weaknesses: [],
      },
    }
    // A real re-analysis can take well over a minute -- delayed here so
    // the "meaningful progress" loading state is actually observable
    // before the response resolves, not just a theoretical instant.
    await mockReanalyzeEndpoint(page, fixtureTailoringPlan.plan_id, response, 300)

    await page.getByRole('button', { name: /re-analyze & compare/i }).click()

    await expect(page.getByText(/re-analyzing your updated resume/i)).toBeVisible()
    await expect(page.getByRole('button', { name: /^download txt$/i })).not.toBeVisible()

    await expect(page.getByText('Match score improved by 5 points')).toBeVisible()
    await expect(page.getByText(/re-analyzing your updated resume/i)).not.toBeVisible()
    await expect(page.getByRole('button', { name: /^download txt$/i })).toBeVisible()
  })

  test('a failed re-analysis leaves Download unavailable', async ({ page }) => {
    await expect(page.getByRole('button', { name: /^download txt$/i })).not.toBeVisible()

    await mockReanalyzeFailure(page, fixtureTailoringPlan.plan_id, 'Re-analysis failed.')
    await page.getByRole('button', { name: /re-analyze & compare/i }).click()

    await expect(
      page.getByText(/applied successfully, but re-analysis could not be completed/i),
    ).toBeVisible()
    await expect(page.getByRole('button', { name: /^download txt$/i })).not.toBeVisible()
  })

  test('a new apply re-locks Download, then a fresh re-analysis unlocks it again with a new comparison', async ({
    page,
  }) => {
    const firstResponse: ReanalyzeResponse = {
      after_analysis: withOverallScore(85),
      comparison: {
        score_before: 80,
        score_after: 85,
        score_delta: 5,
        status: 'improved',
        category_comparisons: [],
        strengths_gained: [],
        strengths_lost: [],
        weaknesses_resolved: [],
        weaknesses_remaining: [],
        new_weaknesses: [],
      },
    }

    await test.step('apply, re-analyze, and confirm Download unlocks', async () => {
      await mockReanalyzeEndpoint(page, fixtureTailoringPlan.plan_id, firstResponse)
      await page.getByRole('button', { name: /re-analyze & compare/i }).click()
      await expect(page.getByText('Match score improved by 5 points')).toBeVisible()
      await expect(page.getByText(scoreBadgeText(80, 85))).toBeVisible()
      await expect(page.getByRole('button', { name: /^download txt$/i })).toBeVisible()
    })

    await test.step('re-apply clears the old comparison and re-locks Download', async () => {
      // Re-apply goes through the same preview-first path as the
      // original apply (see TailoredResumePage's `attemptApply`
      // docstring).
      await mockApplyEndpoint(page, fixtureTailoringPlan.plan_id)
      await page.getByRole('button', { name: /preview changes/i }).click()
      await expect(page.getByRole('button', { name: /apply now/i })).toBeVisible()
      await page.getByRole('button', { name: /apply now/i }).click()

      await expect(page.getByText('Final Resume Preview')).toBeVisible()
      // The prior comparison itself is gone, not just the download
      // button -- a stale comparison must never keep Download unlocked.
      await expect(page.getByText('Match score improved by 5 points')).not.toBeVisible()
      await expect(page.getByRole('button', { name: /^download txt$/i })).not.toBeVisible()
      await expect(page.getByRole('button', { name: /re-analyze & compare/i })).toBeVisible()
    })

    await test.step('a fresh re-analysis produces a new comparison and unlocks Download again', async () => {
      // Deliberately different numbers from the first response, so a
      // pass here proves this is a genuinely new comparison, not a
      // leftover from the first re-analysis.
      const secondResponse: ReanalyzeResponse = {
        after_analysis: withOverallScore(90),
        comparison: {
          score_before: 85,
          score_after: 90,
          score_delta: 5,
          status: 'improved',
          category_comparisons: [],
          strengths_gained: [],
          strengths_lost: [],
          weaknesses_resolved: [],
          weaknesses_remaining: [],
          new_weaknesses: [],
        },
      }
      await mockReanalyzeEndpoint(page, fixtureTailoringPlan.plan_id, secondResponse)
      await page.getByRole('button', { name: /re-analyze & compare/i }).click()

      await expect(page.getByText(scoreBadgeText(85, 90))).toBeVisible()
      await expect(page.getByRole('button', { name: /^download txt$/i })).toBeVisible()
    })
  })

  test('score improves: the result is clearly presented as a measurable improvement', async ({
    page,
  }) => {
    const response: ReanalyzeResponse = {
      after_analysis: withOverallScore(85),
      comparison: {
        score_before: 80,
        score_after: 85,
        score_delta: 5,
        status: 'improved',
        category_comparisons: [
          {
            category: 'Frontend',
            score_before: 40,
            score_after: 60,
            score_delta: 20,
            status: 'improved',
            newly_matched_skills: ['TypeScript'],
            newly_missing_skills: [],
          },
        ],
        strengths_gained: ['Demonstrated frontend work.'],
        strengths_lost: [],
        weaknesses_resolved: ['Frontend experience is unclear.'],
        weaknesses_remaining: [],
        new_weaknesses: [],
      },
    }
    await mockReanalyzeEndpoint(page, fixtureTailoringPlan.plan_id, response)

    await page.getByRole('button', { name: /re-analyze & compare/i }).click()

    // Explicit, unambiguous improvement -- score before/after, delta,
    // and status, all user-visible.
    await expect(page.getByText('Match score improved by 5 points')).toBeVisible()
    await expect(page.getByText(/measurably improved/i)).toBeVisible()
    await expect(page.getByText(scoreBadgeText(80, 85))).toBeVisible()

    // The improvement isn't just a headline -- the underlying evidence
    // (category breakdown, resolved gaps, new strengths) is also shown.
    await expect(page.getByText('Category breakdown')).toBeVisible()
    await expect(page.getByText('Frontend', { exact: true })).toBeVisible()
    await expect(page.getByText('+TypeScript')).toBeVisible()
    await expect(page.getByText('New strengths')).toBeVisible()
    await expect(page.getByText('Demonstrated frontend work.')).toBeVisible()
    await expect(page.getByText('Resolved gaps')).toBeVisible()
    await expect(page.getByText('Frontend experience is unclear.')).toBeVisible()
  })

  test('score is unchanged: applying changes is never presented as success', async ({ page }) => {
    const response: ReanalyzeResponse = {
      after_analysis: withOverallScore(80),
      comparison: {
        score_before: 80,
        score_after: 80,
        score_delta: 0,
        status: 'unchanged',
        category_comparisons: [],
        strengths_gained: [],
        strengths_lost: [],
        weaknesses_resolved: [],
        weaknesses_remaining: ['No people-management evidence.'],
        new_weaknesses: [],
      },
    }
    await mockReanalyzeEndpoint(page, fixtureTailoringPlan.plan_id, response)

    await page.getByRole('button', { name: /re-analyze & compare/i }).click()

    // The headline must say the score did NOT improve -- never a
    // celebratory or generic "success" message.
    await expect(page.getByText('Match score did not improve')).toBeVisible()
    await expect(page.getByText(/stayed the same/i)).toBeVisible()
    await expect(page.getByText(/review the remaining gaps/i)).toBeVisible()
    await expect(page.getByText(scoreBadgeText(80, 80))).toBeVisible()

    // Nothing on screen claims an improvement.
    await expect(page.getByText(/improved by/i)).not.toBeVisible()
    await expect(page.getByText(/decreased by/i)).not.toBeVisible()

    // Remaining-gap guidance is shown, per this feature's requirement
    // that the user still sees what's left to work on.
    await expect(page.getByRole('heading', { name: 'Remaining gaps' })).toBeVisible()
    await expect(page.getByText('No people-management evidence.')).toBeVisible()
  })

  test('score decreases: the regression is reported plainly, never hidden', async ({ page }) => {
    const response: ReanalyzeResponse = {
      after_analysis: withOverallScore(75),
      comparison: {
        score_before: 80,
        score_after: 75,
        score_delta: -5,
        status: 'decreased',
        category_comparisons: [],
        strengths_gained: [],
        strengths_lost: ['Strong backend ownership.'],
        weaknesses_resolved: [],
        weaknesses_remaining: [],
        new_weaknesses: ['Resume no longer demonstrates ownership clearly.'],
      },
    }
    await mockReanalyzeEndpoint(page, fixtureTailoringPlan.plan_id, response)

    await page.getByRole('button', { name: /re-analyze & compare/i }).click()

    await expect(page.getByText('Match score decreased by 5 points')).toBeVisible()
    await expect(page.getByText(/went down/i)).toBeVisible()
    await expect(page.getByText(/further tailoring may be appropriate/i)).toBeVisible()
    await expect(page.getByText(scoreBadgeText(80, 75))).toBeVisible()

    // Not softened into generic success wording, and the regression
    // itself (not just the headline number) is visible. (The static
    // "Re-analyze your updated resume..." button description always
    // mentions "improved" regardless of outcome, so this checks for the
    // improved *headline* specifically, not the word anywhere on the page.)
    await expect(page.getByText('Match score improved by')).not.toBeVisible()
    await expect(page.getByText('Lost strengths')).toBeVisible()
    await expect(page.getByText('Strong backend ownership.')).toBeVisible()
    await expect(page.getByText('New gaps')).toBeVisible()
    await expect(
      page.getByText('Resume no longer demonstrates ownership clearly.'),
    ).toBeVisible()
  })

  test('re-analysis failure: the applied resume stays applied and no score is fabricated', async ({
    page,
  }) => {
    await mockReanalyzeFailure(page, fixtureTailoringPlan.plan_id, 'Re-analysis failed.')

    await page.getByRole('button', { name: /re-analyze & compare/i }).click()

    await expect(
      page.getByText(/applied successfully, but re-analysis could not be completed/i),
    ).toBeVisible()

    // No fabricated verdict of any kind.
    await expect(page.getByText(/improved by/i)).not.toBeVisible()
    await expect(page.getByText(/decreased by/i)).not.toBeVisible()
    await expect(page.getByText('Match score did not improve')).not.toBeVisible()

    // The already-applied resume is completely unaffected by the failure.
    await expect(page.getByText('Final Resume Preview')).toBeVisible()
    await expect(page.getByText('Applied changes (1)')).toBeVisible()
  })

  test('re-analysis failure does not clear a prior good comparison', async ({ page }) => {
    // Seed as if a previous "Re-analyze & Compare" already succeeded.
    await seedResumeSession(page, {
      resumeAnalysis: withOverallScore(BEFORE_SCORE),
      tailoringSelections: ['suggestion-0'],
      finalTailoredResume: {
        finalResumeText:
          'SUMMARY\nBackend engineer with 5 years of experience.\n\nSKILLS\nPython, TypeScript\nDjango\n\nEXPERIENCE\nBuilt internal tools using Python and Django.\n',
        appliedSuggestionIds: ['suggestion-0'],
      },
      tailoringValidationReport: { is_valid: true, messages: [] },
      postApplyAnalysis: withOverallScore(85),
      postApplyComparison: {
        score_before: 80,
        score_after: 85,
        score_delta: 5,
        status: 'improved',
        category_comparisons: [],
        strengths_gained: [],
        strengths_lost: [],
        weaknesses_resolved: [],
        weaknesses_remaining: [],
        new_weaknesses: [],
      },
    })
    await page.goto('/tailored-resume')
    await expect(page.getByText('Match score improved by 5 points')).toBeVisible()

    await mockReanalyzeFailure(page, fixtureTailoringPlan.plan_id, 'Re-analysis failed.')
    // A comparison already exists here, so the button now reads "Re-analyze
    // Again" (see TailoredResumePage.tsx), not the initial "Re-analyze &
    // Compare".
    await page.getByRole('button', { name: /re-analyze again/i }).click()

    await expect(
      page.getByText(/applied successfully, but re-analysis could not be completed/i),
    ).toBeVisible()
    // The last real, successful comparison is still shown -- a failed
    // retry must never clear it.
    await expect(page.getByText('Match score improved by 5 points')).toBeVisible()
  })
})
