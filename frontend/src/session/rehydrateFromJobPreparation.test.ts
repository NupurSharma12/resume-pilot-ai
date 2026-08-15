import { describe, it, expect } from 'vitest'
import { nextRouteForCheckpoints, rehydrateFromJobPreparation } from './rehydrateFromJobPreparation'
import type { CheckpointStatus, JobPreparationDetail } from '../data/jobPreparationHistoryTypes'

const fixtureCheckpoints: CheckpointStatus = {
  initial_analysis_completed_at: '2026-08-01T10:00:00Z',
  career_conversation_completed_at: null,
  tailoring_plan_completed_at: null,
  applied_at: null,
  post_apply_analysis_completed_at: null,
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
  analysis_result: {
    overall_assessment: { overall_score: 72, summary: 'Solid backend fit.' },
  },
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
    const result = rehydrateFromJobPreparation(fixtureDetail)

    expect(result.resume).toEqual({ text: 'SUMMARY\nSenior backend engineer.', fileName: 'Senior Engineer Resume' })
    expect(result.jobDescription).toEqual({ text: 'We are hiring a senior engineer.', fileName: null })
    expect(result.resumeAnalysis).toEqual(fixtureDetail.analysis_result)
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

    const result = rehydrateFromJobPreparation(detail)

    expect(result.activeCareerConversationSessionId).toBe('conv-session-1')
    expect(result.careerConversationStatus).toBe('complete')
    expect(result.nextRoute).toBe('/tailored-resume')
  })

  it('rehydrates a generated tailoring plan and its selection', () => {
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
          available_export_formats: ['txt', 'markdown'],
          default_export_format: 'txt',
        },
        selection: { selected_suggestion_ids: ['s-1'], edited_texts: { 's-1': 'Edited text.' } },
      },
    }

    const result = rehydrateFromJobPreparation(detail)

    expect(result.tailoringPlan).toEqual(detail.tailoring_plan?.generated_plan)
    expect(result.tailoringSelections).toEqual(['s-1'])
    expect(result.tailoringEditedTexts).toEqual({ 's-1': 'Edited text.' })
    expect(result.tailoringAvailableExportFormats).toEqual(['txt', 'markdown'])
    expect(result.finalTailoredResume).toBeNull()
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
        generated_plan: {
          plan_id: 'plan-1',
          suggestions: [],
          available_export_formats: ['txt'],
          default_export_format: 'txt',
        },
        selection: { selected_suggestion_ids: ['s-1'], edited_texts: {} },
      },
      applied_resume_text: 'SUMMARY\nTailored resume text.',
    }

    const result = rehydrateFromJobPreparation(detail)

    expect(result.finalTailoredResume).toEqual({
      finalResumeText: 'SUMMARY\nTailored resume text.',
      appliedSuggestionIds: ['s-1'],
    })
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

    const result = rehydrateFromJobPreparation(detail)

    expect(result.postApplyAnalysis).toEqual(detail.post_apply_analysis?.analysis)
    expect(result.postApplyComparison).toEqual(detail.post_apply_analysis?.comparison)
  })
})
