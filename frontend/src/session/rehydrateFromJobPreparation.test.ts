import { describe, it, expect } from 'vitest'
import { nextRouteForCheckpoints, rehydrateFromJobPreparation } from './rehydrateFromJobPreparation'
import { ALL_EXPORT_FORMATS } from '../lib/sourceFormat'
import type { CheckpointStatus, JobPreparationDetail } from '../data/jobPreparationHistoryTypes'

const fixtureCheckpoints: CheckpointStatus = {
  initial_analysis_completed_at: '2026-08-01T10:00:00Z',
  career_conversation_completed_at: null,
  tailoring_plan_completed_at: null,
  applied_at: null,
  post_apply_analysis_completed_at: null,
}

// A full, valid `ResumeAnalysisResult` shape -- everything
// `isValidResumeAnalysisResult` requires and everything `insights.ts`'s
// consumers actually read. Deliberately not the old, deliberately-minimal
// `{ overall_assessment: { overall_score, summary } }` fixture this file
// used to have: that shape is exactly what a real persisted row can no
// longer have and still rehydrate (see the malformed-data tests below),
// so a fixture standing in for "a real, valid preparation" needs to
// actually be one.
const fixtureAnalysisResult = {
  overall_assessment: {
    overall_score: 72,
    hiring_recommendation: { decision: 'Proceed', reason: 'Solid fit.' },
    summary: 'Solid backend fit.',
  },
  skill_matches: [],
  matching_projects: [],
  strengths: ['Strong backend ownership.'],
  weaknesses: ['Frontend experience is unclear.'],
  resume_improvements: [],
}

const fixtureDetail: JobPreparationDetail = {
  id: 'job-prep-1',
  job_title: 'Senior Engineer',
  company: 'Adobe',
  job_description: 'We are hiring a senior engineer.',
  resume_name: 'Senior Engineer Resume',
  resume_text: 'SUMMARY\nSenior backend engineer.',
  status: 'active',
  created_at: '2026-08-01T09:00:00Z',
  updated_at: '2026-08-12T09:00:00Z',
  checkpoints: fixtureCheckpoints,
  analysis_result: fixtureAnalysisResult,
  career_conversation: null,
  tailoring_plan: null,
  applied_resume_text: null,
  post_apply_analysis: null,
  interview_preparation: null,
}

describe('nextRouteForCheckpoints', () => {
  it('routes to Career Conversation when it has not completed yet (analysis-only checkpoint)', () => {
    expect(nextRouteForCheckpoints(fixtureCheckpoints)).toBe('/career-conversation')
  })

  it('routes to Tailored Resume once the Career Conversation has completed', () => {
    expect(
      nextRouteForCheckpoints({
        ...fixtureCheckpoints,
        career_conversation_completed_at: '2026-08-01T10:05:00Z',
      }),
    ).toBe('/tailored-resume')
  })

  it('routes to Tailored Resume when a tailoring plan has been generated but not applied', () => {
    expect(
      nextRouteForCheckpoints({
        ...fixtureCheckpoints,
        career_conversation_completed_at: '2026-08-01T10:05:00Z',
        tailoring_plan_completed_at: '2026-08-01T10:10:00Z',
      }),
    ).toBe('/tailored-resume')
  })

  it('routes to Tailored Resume when changes were applied but re-analysis has not run', () => {
    expect(
      nextRouteForCheckpoints({
        ...fixtureCheckpoints,
        career_conversation_completed_at: '2026-08-01T10:05:00Z',
        tailoring_plan_completed_at: '2026-08-01T10:10:00Z',
        applied_at: '2026-08-01T10:15:00Z',
      }),
    ).toBe('/tailored-resume')
  })

  it('routes to Tailored Resume when every checkpoint, including re-analysis, is complete', () => {
    expect(
      nextRouteForCheckpoints({
        ...fixtureCheckpoints,
        career_conversation_completed_at: '2026-08-01T10:05:00Z',
        tailoring_plan_completed_at: '2026-08-01T10:10:00Z',
        applied_at: '2026-08-01T10:15:00Z',
        post_apply_analysis_completed_at: '2026-08-01T10:20:00Z',
      }),
    ).toBe('/tailored-resume')
  })
})

describe('rehydrateFromJobPreparation', () => {
  it('maps resume/job description/analysis/jobPreparationId from an analysis-only preparation', () => {
    const outcome = rehydrateFromJobPreparation(fixtureDetail)

    expect(outcome.ok).toBe(true)
    if (!outcome.ok) return
    const result = outcome.session

    expect(result.resume).toEqual({
      text: 'SUMMARY\nSenior backend engineer.',
      fileName: 'Senior Engineer Resume',
    })
    expect(result.jobDescription).toEqual({ text: 'We are hiring a senior engineer.', fileName: null })
    expect(result.resumeAnalysis).toEqual(fixtureAnalysisResult)
    expect(result.jobPreparationId).toBe('job-prep-1')
    expect(result.activeCareerConversationSessionId).toBeNull()
    expect(result.careerConversationStatus).toBeNull()
    expect(result.tailoringPlan).toBeNull()
    expect(result.tailoringSelections).toEqual([])
    expect(result.tailoringEditedTexts).toEqual({})
    expect(result.finalTailoredResume).toBeNull()
    expect(result.postApplyAnalysis).toBeNull()
    expect(result.postApplyComparison).toBeNull()
    expect(result.nextRoute).toBe('/career-conversation')
  })

  it('rehydrates the Career Conversation session id/status from the persisted transcript', () => {
    const detail: JobPreparationDetail = {
      ...fixtureDetail,
      checkpoints: { ...fixtureCheckpoints, career_conversation_completed_at: '2026-08-01T10:05:00Z' },
      career_conversation: { session_id: 'conv-session-1', status: 'complete', history: [] },
    }

    const outcome = rehydrateFromJobPreparation(detail)

    expect(outcome.ok).toBe(true)
    if (!outcome.ok) return
    expect(outcome.session.activeCareerConversationSessionId).toBe('conv-session-1')
    expect(outcome.session.careerConversationStatus).toBe('complete')
    expect(outcome.session.nextRoute).toBe('/tailored-resume')
  })

  it('rehydrates a generated tailoring plan and its selection from the real persisted shape (plan_id + suggestions only)', () => {
    // Exactly what `record_generated_tailoring_plan` actually persists --
    // no `available_export_formats`/`default_export_format`, for *any*
    // preparation, not just old ones (see PersistedTailoringPlan's own
    // docstring). A test fixture that included those two fields here
    // would misrepresent what real persisted data looks like.
    const detail: JobPreparationDetail = {
      ...fixtureDetail,
      checkpoints: {
        ...fixtureCheckpoints,
        career_conversation_completed_at: '2026-08-01T10:05:00Z',
        tailoring_plan_completed_at: '2026-08-01T10:10:00Z',
      },
      career_conversation: { session_id: 'conv-session-1', status: 'complete', history: [] },
      tailoring_plan: {
        generated_plan: {
          plan_id: 'plan-1',
          suggestions: [{ suggestion_id: 's-1' }],
        },
        selection: { selected_suggestion_ids: ['s-1'], edited_texts: { 's-1': 'Edited text.' } },
      },
    }

    const outcome = rehydrateFromJobPreparation(detail)

    expect(outcome.ok).toBe(true)
    if (!outcome.ok) return
    expect(outcome.session.tailoringPlan).toEqual({
      plan_id: 'plan-1',
      suggestions: [{ suggestion_id: 's-1' }],
    })
    expect(outcome.session.tailoringSelections).toEqual(['s-1'])
    expect(outcome.session.tailoringEditedTexts).toEqual({ 's-1': 'Edited text.' })
    // Derived from the constant, never from the (nonexistent) persisted
    // field -- this is what makes Download work after rehydration.
    expect(outcome.session.tailoringAvailableExportFormats).toEqual(ALL_EXPORT_FORMATS)
    expect(outcome.session.finalTailoredResume).toBeNull()
  })

  it('rehydrates the applied final resume without a selection when applied_resume_text exists', () => {
    const detail: JobPreparationDetail = {
      ...fixtureDetail,
      checkpoints: {
        ...fixtureCheckpoints,
        career_conversation_completed_at: '2026-08-01T10:05:00Z',
        tailoring_plan_completed_at: '2026-08-01T10:10:00Z',
        applied_at: '2026-08-01T10:15:00Z',
      },
      career_conversation: { session_id: 'conv-session-1', status: 'complete', history: [] },
      tailoring_plan: {
        generated_plan: { plan_id: 'plan-1', suggestions: [] },
        selection: { selected_suggestion_ids: ['s-1'], edited_texts: {} },
      },
      applied_resume_text: 'SUMMARY\nTailored resume text.',
    }

    const outcome = rehydrateFromJobPreparation(detail)

    expect(outcome.ok).toBe(true)
    if (!outcome.ok) return
    expect(outcome.session.finalTailoredResume).toEqual({
      finalResumeText: 'SUMMARY\nTailored resume text.',
      appliedSuggestionIds: ['s-1'],
    })
    // Download depends on this, not on any field read off the plan --
    // see TailoringPlanContent's docstring.
    expect(outcome.session.tailoringAvailableExportFormats).toEqual(ALL_EXPORT_FORMATS)
  })

  it('rehydrates post-apply analysis/comparison when re-analysis has completed', () => {
    const detail: JobPreparationDetail = {
      ...fixtureDetail,
      checkpoints: {
        ...fixtureCheckpoints,
        career_conversation_completed_at: '2026-08-01T10:05:00Z',
        tailoring_plan_completed_at: '2026-08-01T10:10:00Z',
        applied_at: '2026-08-01T10:15:00Z',
        post_apply_analysis_completed_at: '2026-08-01T10:20:00Z',
      },
      applied_resume_text: 'SUMMARY\nTailored resume text.',
      post_apply_analysis: {
        analysis: { overall_assessment: { overall_score: 85 } },
        comparison: { score_before: 72, score_after: 85, status: 'improved' },
      },
    }

    const outcome = rehydrateFromJobPreparation(detail)

    expect(outcome.ok).toBe(true)
    if (!outcome.ok) return
    expect(outcome.session.postApplyAnalysis).toEqual(detail.post_apply_analysis?.analysis)
    expect(outcome.session.postApplyComparison).toEqual(detail.post_apply_analysis?.comparison)
  })

  it('no plan yet -- available export formats stay empty, nothing to download', () => {
    const outcome = rehydrateFromJobPreparation(fixtureDetail)

    expect(outcome.ok).toBe(true)
    if (!outcome.ok) return
    expect(outcome.session.tailoringAvailableExportFormats).toEqual([])
  })

  describe('malformed analysis_result -- graceful rehydration failure', () => {
    it('fails when analysis_result is null', () => {
      const outcome = rehydrateFromJobPreparation({ ...fixtureDetail, analysis_result: null })

      expect(outcome.ok).toBe(false)
      if (outcome.ok) return
      expect(outcome.error).toMatch(/can't be restored/i)
    })

    it('fails when analysis_result is missing weaknesses (e.g. a legacy/test-fixture shape)', () => {
      const { weaknesses: _weaknesses, ...withoutWeaknesses } = fixtureAnalysisResult
      const outcome = rehydrateFromJobPreparation({
        ...fixtureDetail,
        analysis_result: withoutWeaknesses,
      })

      expect(outcome.ok).toBe(false)
    })

    it('fails when overall_assessment.hiring_recommendation is missing', () => {
      const outcome = rehydrateFromJobPreparation({
        ...fixtureDetail,
        analysis_result: {
          ...fixtureAnalysisResult,
          overall_assessment: { overall_score: 72, summary: 'Solid backend fit.' },
        },
      })

      expect(outcome.ok).toBe(false)
    })

    it('fails when overall_score is not a number', () => {
      const outcome = rehydrateFromJobPreparation({
        ...fixtureDetail,
        analysis_result: {
          ...fixtureAnalysisResult,
          overall_assessment: { ...fixtureAnalysisResult.overall_assessment, overall_score: '72' },
        },
      })

      expect(outcome.ok).toBe(false)
    })
  })
})
