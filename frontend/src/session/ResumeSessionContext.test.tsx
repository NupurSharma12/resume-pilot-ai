import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor, act } from '@testing-library/react'
import { ResumeSessionProvider, useResumeSession } from './ResumeSessionContext'
import type { PersistedResumeSession, ResumeSessionStorage } from './resumeSessionTypes'
import type { ResumeAnalysisComparison } from '../data/postApplyTypes'
import type { JobPreparationDetail } from '../data/jobPreparationHistoryTypes'
import {
  fixtureApplySuggestionsResponse,
  fixtureGenerateSuggestionsResponse,
  fixturePersistedSession,
  fixtureResume,
  fixtureResumeAnalysis,
} from '../testFixtures'

const fixtureJobPreparationDetail: JobPreparationDetail = {
  id: 'history-job-prep',
  job_title: 'Staff Engineer',
  company: 'Globex',
  job_description: 'We are hiring a staff engineer.',
  resume_name: 'Staff Engineer Resume',
  resume_text: 'SUMMARY\nStaff engineer with 10 years of experience.',
  status: 'active',
  created_at: '2026-08-01T09:00:00Z',
  updated_at: '2026-08-12T09:00:00Z',
  checkpoints: {
    initial_analysis_completed_at: '2026-08-01T10:00:00Z',
    career_conversation_completed_at: '2026-08-01T10:05:00Z',
    tailoring_plan_completed_at: null,
    applied_at: null,
    post_apply_analysis_completed_at: null,
  },
  analysis_result: fixtureResumeAnalysis as unknown as Record<string, unknown>,
  career_conversation: { session_id: 'history-conv-1', status: 'complete', history: [] },
  tailoring_plan: null,
  applied_resume_text: null,
  post_apply_analysis: null,
  interview_preparation: null,
}

const fixturePostApplyComparison: ResumeAnalysisComparison = {
  score_before: fixtureResumeAnalysis.overall_assessment.overall_score,
  score_after: 91,
  score_delta: 91 - fixtureResumeAnalysis.overall_assessment.overall_score,
  status: 'improved',
  category_comparisons: [],
  strengths_gained: [],
  strengths_lost: [],
  weaknesses_resolved: [],
  weaknesses_remaining: [],
  new_weaknesses: [],
}

function createFakeStorage(initial: PersistedResumeSession | null = null): ResumeSessionStorage & {
  saves: PersistedResumeSession[]
} {
  let state = initial
  const saves: PersistedResumeSession[] = []
  return {
    saves,
    load: () => state,
    save: (session) => {
      state = session
      saves.push(session)
    },
    clear: () => {
      state = null
    },
  }
}

function Probe() {
  const session = useResumeSession()
  const [nextRoute, setNextRoute] = useState<string | null>(null)
  const [rehydrationError, setRehydrationError] = useState<string | null>(null)
  return (
    <div>
      <span data-testid="hydration">{session.hydrationStatus}</span>
      <span data-testid="resume">{session.resume?.fileName ?? 'none'}</span>
      <span data-testid="jobDescription">{session.jobDescription?.text ?? 'none'}</span>
      <span data-testid="nextRoute">{nextRoute ?? 'none'}</span>
      <span data-testid="rehydrationError">{rehydrationError ?? 'none'}</span>
      <span data-testid="status">{session.status}</span>
      <span data-testid="sessionId">{session.activeCareerConversationSessionId ?? 'none'}</span>
      <span data-testid="conversationStatus">{session.careerConversationStatus ?? 'none'}</span>
      <span data-testid="tailoringPlan">{session.tailoringPlan ? 'present' : 'none'}</span>
      <span data-testid="tailoringSelections">{session.tailoringSelections.join(',')}</span>
      <span data-testid="customInstructions">{session.tailoringCustomInstructions}</span>
      <span data-testid="finalResume">{session.finalTailoredResume ? 'present' : 'none'}</span>
      <span data-testid="postApplyComparison">
        {session.postApplyComparison ? 'present' : 'none'}
      </span>
      <span data-testid="jobPreparationId">{session.jobPreparationId ?? 'none'}</span>
      <span data-testid="resumeAnalysis">{session.resumeAnalysis ? 'present' : 'none'}</span>
      <button onClick={() => session.setResume(fixtureResume)}>set-resume</button>
      <button onClick={() => session.setResumeAnalysis(fixtureResumeAnalysis)}>
        set-resume-analysis
      </button>
      <button onClick={() => session.setJobPreparationId('job-prep-1')}>
        set-job-preparation-id
      </button>
      <button onClick={() => session.setPostApplyComparison(fixturePostApplyComparison)}>
        set-post-apply-comparison
      </button>
      <button onClick={() => session.resetForNewAnalysis()}>reset-for-new-analysis</button>
      <button
        onClick={() => {
          const outcome = session.rehydrateFromHistory(fixtureJobPreparationDetail)
          if (outcome.ok) {
            setNextRoute(outcome.nextRoute)
          } else {
            setRehydrationError(outcome.error)
          }
        }}
      >
        rehydrate-from-history
      </button>
      <button
        onClick={() => {
          const outcome = session.rehydrateFromHistory({
            ...fixtureJobPreparationDetail,
            analysis_result: { overall_assessment: { overall_score: 72 } },
          })
          if (outcome.ok) {
            setNextRoute(outcome.nextRoute)
          } else {
            setRehydrationError(outcome.error)
          }
        }}
      >
        rehydrate-from-history-with-malformed-analysis
      </button>
      <button onClick={() => session.setStatus('loading')}>set-loading</button>
      <button onClick={() => session.setActiveCareerConversationSessionId('conv-1')}>
        set-session-id
      </button>
      <button onClick={() => session.setCareerConversationStatus('complete')}>
        set-conversation-complete
      </button>
      <button onClick={() => session.setTailoringPlan(fixtureGenerateSuggestionsResponse)}>
        set-tailoring-plan
      </button>
      <button onClick={() => session.setTailoringSelections(['suggestion-0'])}>
        set-selections
      </button>
      <button onClick={() => session.setTailoringCustomInstructions('Keep it under two pages.')}>
        set-instructions
      </button>
      <button
        onClick={() =>
          session.setFinalTailoredResume({
            finalResumeText: fixtureApplySuggestionsResponse.final_resume_text,
            appliedSuggestionIds: fixtureApplySuggestionsResponse.applied_suggestion_ids,
          })
        }
      >
        set-final-resume
      </button>
      <button onClick={() => session.clearSession()}>clear</button>
    </div>
  )
}

describe('ResumeSessionProvider', () => {
  it('starts pending, then hydrates with no data when storage is empty', async () => {
    const storage = createFakeStorage(null)
    render(
      <ResumeSessionProvider storage={storage}>
        <Probe />
      </ResumeSessionProvider>,
    )

    await waitFor(() => expect(screen.getByTestId('hydration').textContent).toBe('hydrated'))
    expect(screen.getByTestId('resume').textContent).toBe('none')
  })

  it('rehydrates an existing valid session from storage', async () => {
    const storage = createFakeStorage(
      fixturePersistedSession({ activeCareerConversationSessionId: 'conv-99' }),
    )
    render(
      <ResumeSessionProvider storage={storage}>
        <Probe />
      </ResumeSessionProvider>,
    )

    await waitFor(() => expect(screen.getByTestId('hydration').textContent).toBe('hydrated'))
    expect(screen.getByTestId('resume').textContent).toBe('resume.txt')
    expect(screen.getByTestId('sessionId').textContent).toBe('conv-99')
  })

  it('does not write the initial null/idle state to storage before hydration finishes', async () => {
    const storage = createFakeStorage(
      fixturePersistedSession({ activeCareerConversationSessionId: 'conv-99' }),
    )
    render(
      <ResumeSessionProvider storage={storage}>
        <Probe />
      </ResumeSessionProvider>,
    )

    await waitFor(() => expect(screen.getByTestId('hydration').textContent).toBe('hydrated'))

    // Every save that did happen (if any, from post-hydration effects) must
    // reflect the restored data, never the pre-hydration null/idle shape.
    for (const saved of storage.saves) {
      expect(saved.activeCareerConversationSessionId).toBe('conv-99')
    }
  })

  it('persists state changes after hydration', async () => {
    const storage = createFakeStorage(null)
    render(
      <ResumeSessionProvider storage={storage}>
        <Probe />
      </ResumeSessionProvider>,
    )
    await waitFor(() => expect(screen.getByTestId('hydration').textContent).toBe('hydrated'))

    await act(async () => {
      screen.getByText('set-session-id').click()
    })

    await waitFor(() => {
      const last = storage.saves.at(-1)
      expect(last?.activeCareerConversationSessionId).toBe('conv-1')
    })
  })

  it('normalizes a "loading" status to "idle" before persisting', async () => {
    const storage = createFakeStorage(null)
    render(
      <ResumeSessionProvider storage={storage}>
        <Probe />
      </ResumeSessionProvider>,
    )
    await waitFor(() => expect(screen.getByTestId('hydration').textContent).toBe('hydrated'))

    await act(async () => {
      screen.getByText('set-loading').click()
    })

    expect(screen.getByTestId('status').textContent).toBe('loading')
    await waitFor(() => {
      const last = storage.saves.at(-1)
      expect(last?.status).toBe('idle')
    })
  })

  it('clearSession clears storage and resets in-memory state, including tailoring state', async () => {
    const storage = createFakeStorage(
      fixturePersistedSession({
        activeCareerConversationSessionId: 'conv-1',
        tailoringPlan: fixtureGenerateSuggestionsResponse,
        tailoringSelections: ['suggestion-0'],
        tailoringCustomInstructions: 'Keep it short.',
        finalTailoredResume: {
          finalResumeText: fixtureApplySuggestionsResponse.final_resume_text,
          appliedSuggestionIds: fixtureApplySuggestionsResponse.applied_suggestion_ids,
        },
      }),
    )
    const clearSpy = vi.spyOn(storage, 'clear')
    render(
      <ResumeSessionProvider storage={storage}>
        <Probe />
      </ResumeSessionProvider>,
    )
    await waitFor(() => expect(screen.getByTestId('resume').textContent).toBe('resume.txt'))
    expect(screen.getByTestId('tailoringPlan').textContent).toBe('present')

    await act(async () => {
      screen.getByText('clear').click()
    })

    expect(clearSpy).toHaveBeenCalled()
    expect(screen.getByTestId('resume').textContent).toBe('none')
    expect(screen.getByTestId('sessionId').textContent).toBe('none')
    expect(screen.getByTestId('conversationStatus').textContent).toBe('none')
    expect(screen.getByTestId('tailoringPlan').textContent).toBe('none')
    expect(screen.getByTestId('tailoringSelections').textContent).toBe('')
    expect(screen.getByTestId('customInstructions').textContent).toBe('')
    expect(screen.getByTestId('finalResume').textContent).toBe('none')
  })

  it('resetForNewAnalysis clears Career Conversation/tailoring/post-apply state but preserves resume/analysis/jobPreparationId', async () => {
    const storage = createFakeStorage(
      fixturePersistedSession({
        activeCareerConversationSessionId: 'conv-1',
        careerConversationStatus: 'complete',
        tailoringPlan: fixtureGenerateSuggestionsResponse,
        tailoringSelections: ['suggestion-0'],
        tailoringCustomInstructions: 'Keep it short.',
        finalTailoredResume: {
          finalResumeText: fixtureApplySuggestionsResponse.final_resume_text,
          appliedSuggestionIds: fixtureApplySuggestionsResponse.applied_suggestion_ids,
        },
        jobPreparationId: 'previous-job-prep',
      }),
    )
    render(
      <ResumeSessionProvider storage={storage}>
        <Probe />
      </ResumeSessionProvider>,
    )
    await waitFor(() => expect(screen.getByTestId('resume').textContent).toBe('resume.txt'))
    await act(async () => {
      screen.getByText('set-post-apply-comparison').click()
    })
    expect(screen.getByTestId('postApplyComparison').textContent).toBe('present')

    await act(async () => {
      screen.getByText('reset-for-new-analysis').click()
    })

    // Career Conversation, tailoring, and post-apply state all belonged
    // to the *previous* analysis's JobPreparation -- gone.
    expect(screen.getByTestId('sessionId').textContent).toBe('none')
    expect(screen.getByTestId('conversationStatus').textContent).toBe('none')
    expect(screen.getByTestId('tailoringPlan').textContent).toBe('none')
    expect(screen.getByTestId('tailoringSelections').textContent).toBe('')
    expect(screen.getByTestId('customInstructions').textContent).toBe('')
    expect(screen.getByTestId('finalResume').textContent).toBe('none')
    expect(screen.getByTestId('postApplyComparison').textContent).toBe('none')
    // But `resume`/`resumeAnalysis`/`jobPreparationId` are untouched --
    // `DashboardPage.handleAnalyze` is the one that overwrites these,
    // immediately after calling resetForNewAnalysis, with the *new*
    // analysis's own values; resetForNewAnalysis itself must never race
    // or clobber that.
    expect(screen.getByTestId('resume').textContent).toBe('resume.txt')
    expect(screen.getByTestId('jobPreparationId').textContent).toBe('previous-job-prep')
  })

  it('rehydrates tailoring plan, selections, custom instructions, and final resume from storage', async () => {
    const storage = createFakeStorage(
      fixturePersistedSession({
        careerConversationStatus: 'complete',
        tailoringPlan: fixtureGenerateSuggestionsResponse,
        tailoringSelections: ['suggestion-0'],
        tailoringCustomInstructions: 'Keep it under two pages.',
        finalTailoredResume: {
          finalResumeText: fixtureApplySuggestionsResponse.final_resume_text,
          appliedSuggestionIds: fixtureApplySuggestionsResponse.applied_suggestion_ids,
        },
      }),
    )
    render(
      <ResumeSessionProvider storage={storage}>
        <Probe />
      </ResumeSessionProvider>,
    )

    await waitFor(() => expect(screen.getByTestId('hydration').textContent).toBe('hydrated'))
    expect(screen.getByTestId('conversationStatus').textContent).toBe('complete')
    expect(screen.getByTestId('tailoringPlan').textContent).toBe('present')
    expect(screen.getByTestId('tailoringSelections').textContent).toBe('suggestion-0')
    expect(screen.getByTestId('customInstructions').textContent).toBe('Keep it under two pages.')
    expect(screen.getByTestId('finalResume').textContent).toBe('present')
  })

  it('persists tailoring plan, selections, custom instructions, and final resume after they are set', async () => {
    const storage = createFakeStorage(null)
    render(
      <ResumeSessionProvider storage={storage}>
        <Probe />
      </ResumeSessionProvider>,
    )
    await waitFor(() => expect(screen.getByTestId('hydration').textContent).toBe('hydrated'))

    await act(async () => {
      screen.getByText('set-conversation-complete').click()
    })
    await act(async () => {
      screen.getByText('set-tailoring-plan').click()
    })
    await act(async () => {
      screen.getByText('set-selections').click()
    })
    await act(async () => {
      screen.getByText('set-instructions').click()
    })
    await act(async () => {
      screen.getByText('set-final-resume').click()
    })

    expect(screen.getByTestId('conversationStatus').textContent).toBe('complete')
    expect(screen.getByTestId('tailoringPlan').textContent).toBe('present')
    expect(screen.getByTestId('finalResume').textContent).toBe('present')
    await waitFor(() => {
      const last = storage.saves.at(-1)
      expect(last?.careerConversationStatus).toBe('complete')
      expect(last?.tailoringPlan).toEqual(fixtureGenerateSuggestionsResponse)
      expect(last?.tailoringSelections).toEqual(['suggestion-0'])
      expect(last?.tailoringCustomInstructions).toBe('Keep it under two pages.')
      expect(last?.finalTailoredResume).toEqual({
        finalResumeText: fixtureApplySuggestionsResponse.final_resume_text,
        appliedSuggestionIds: fixtureApplySuggestionsResponse.applied_suggestion_ids,
      })
    })
  })

  it('rehydrateFromHistory populates session fields from a JobPreparationDetail and returns the next route', async () => {
    const storage = createFakeStorage(null)
    render(
      <ResumeSessionProvider storage={storage}>
        <Probe />
      </ResumeSessionProvider>,
    )
    await waitFor(() => expect(screen.getByTestId('hydration').textContent).toBe('hydrated'))

    await act(async () => {
      screen.getByText('rehydrate-from-history').click()
    })

    expect(screen.getByTestId('resume').textContent).toBe('Staff Engineer Resume')
    expect(screen.getByTestId('jobDescription').textContent).toBe(
      'We are hiring a staff engineer.',
    )
    expect(screen.getByTestId('resumeAnalysis').textContent).toBe('present')
    expect(screen.getByTestId('jobPreparationId').textContent).toBe('history-job-prep')
    expect(screen.getByTestId('sessionId').textContent).toBe('history-conv-1')
    expect(screen.getByTestId('conversationStatus').textContent).toBe('complete')
    expect(screen.getByTestId('status').textContent).toBe('success')
    // No tailoring plan was persisted for this fixture's checkpoint state.
    expect(screen.getByTestId('tailoringPlan').textContent).toBe('none')
    expect(screen.getByTestId('finalResume').textContent).toBe('none')
    expect(screen.getByTestId('postApplyComparison').textContent).toBe('none')
    // Career Conversation is complete but Tailoring Plan is not -- Continue
    // should land on Tailored Resume next (see nextRouteForCheckpoints).
    expect(screen.getByTestId('nextRoute').textContent).toBe('/tailored-resume')
  })

  it('rehydrateFromHistory fails gracefully on a malformed analysis_result, leaving state untouched', async () => {
    const storage = createFakeStorage(
      fixturePersistedSession({ jobPreparationId: 'previous-job-prep' }),
    )
    render(
      <ResumeSessionProvider storage={storage}>
        <Probe />
      </ResumeSessionProvider>,
    )
    await waitFor(() => expect(screen.getByTestId('hydration').textContent).toBe('hydrated'))
    expect(screen.getByTestId('jobPreparationId').textContent).toBe('previous-job-prep')

    await act(async () => {
      screen.getByText('rehydrate-from-history-with-malformed-analysis').click()
    })

    expect(screen.getByTestId('rehydrationError').textContent).toMatch(/can't be restored/i)
    // Nothing was mutated -- the previous session's own state (unrelated
    // to this failed rehydration attempt) is exactly as it was before.
    expect(screen.getByTestId('jobPreparationId').textContent).toBe('previous-job-prep')
    expect(screen.getByTestId('nextRoute').textContent).toBe('none')
  })

  it('throws a clear error if useResumeSession is used outside the provider', () => {
    function Bare() {
      useResumeSession()
      return null
    }
    // Suppress React's expected console.error for the thrown-during-render case.
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    expect(() => render(<Bare />)).toThrow(/useResumeSession must be used within/)
    spy.mockRestore()
  })
})
