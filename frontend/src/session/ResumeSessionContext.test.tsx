import { describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor, act } from '@testing-library/react'
import { ResumeSessionProvider, useResumeSession } from './ResumeSessionContext'
import type { PersistedResumeSession, ResumeSessionStorage } from './resumeSessionTypes'
import {
  fixtureApplySuggestionsResponse,
  fixtureGenerateSuggestionsResponse,
  fixturePersistedSession,
  fixtureResume,
} from '../testFixtures'

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
  return (
    <div>
      <span data-testid="hydration">{session.hydrationStatus}</span>
      <span data-testid="resume">{session.resume?.fileName ?? 'none'}</span>
      <span data-testid="status">{session.status}</span>
      <span data-testid="sessionId">{session.activeCareerConversationSessionId ?? 'none'}</span>
      <span data-testid="conversationStatus">{session.careerConversationStatus ?? 'none'}</span>
      <span data-testid="tailoringPlan">{session.tailoringPlan ? 'present' : 'none'}</span>
      <span data-testid="tailoringSelections">{session.tailoringSelections.join(',')}</span>
      <span data-testid="customInstructions">{session.tailoringCustomInstructions}</span>
      <span data-testid="finalResume">{session.finalTailoredResume ? 'present' : 'none'}</span>
      <button onClick={() => session.setResume(fixtureResume)}>set-resume</button>
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
