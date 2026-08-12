import { StrictMode, type ReactNode } from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { MemoryRouter, Route, Routes, Outlet } from 'react-router-dom'
import CareerConversationPage from './CareerConversationPage'
import * as careerConversationApi from '../lib/careerConversationApi'
import * as resumeSessionContext from '../session/ResumeSessionContext'
import { ApiError } from '../lib/api'
import {
  fixtureResume,
  fixtureJobDescription,
  fixtureResumeAnalysis,
  fixtureSession,
} from '../testFixtures'
import type { DashboardOutletContext } from '../layouts/DashboardLayout'
import type { ResumeSessionContextValue } from '../session/ResumeSessionContext'

vi.mock('../lib/careerConversationApi')
vi.mock('../session/ResumeSessionContext', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../session/ResumeSessionContext')>()
  return { ...actual, useResumeSession: vi.fn() }
})

const mockedApi = vi.mocked(careerConversationApi)
const mockedUseResumeSession = vi.mocked(resumeSessionContext.useResumeSession)

function makeResumeSessionValue(
  overrides: Partial<ResumeSessionContextValue> = {},
): ResumeSessionContextValue {
  return {
    hydrationStatus: 'hydrated',
    resume: fixtureResume,
    setResume: vi.fn(),
    jobDescription: fixtureJobDescription,
    setJobDescription: vi.fn(),
    resumeAnalysis: fixtureResumeAnalysis,
    setResumeAnalysis: vi.fn(),
    status: 'success',
    setStatus: vi.fn(),
    activeCareerConversationSessionId: null,
    setActiveCareerConversationSessionId: vi.fn(),
    careerConversationStatus: null,
    setCareerConversationStatus: vi.fn(),
    tailoringPlan: null,
    setTailoringPlan: vi.fn(),
    tailoringPlanStatus: 'idle',
    setTailoringPlanStatus: vi.fn(),
    tailoringSelections: [],
    setTailoringSelections: vi.fn(),
    tailoringCustomInstructions: '',
    setTailoringCustomInstructions: vi.fn(),
    tailoringEditedTexts: {},
    setTailoringEditedTexts: vi.fn(),
    finalTailoredResume: null,
    setFinalTailoredResume: vi.fn(),
    tailoringValidationReport: null,
    setTailoringValidationReport: vi.fn(),
    tailoringAvailableExportFormats: [],
    setTailoringAvailableExportFormats: vi.fn(),
    tailoringSourceFormat: null,
    setTailoringSourceFormat: vi.fn(),
    postApplyAnalysis: null,
    setPostApplyAnalysis: vi.fn(),
    postApplyComparison: null,
    setPostApplyComparison: vi.fn(),
    postApplyAnalysisStatus: 'idle',
    setPostApplyAnalysisStatus: vi.fn(),
    jobPreparationId: null,
    setJobPreparationId: vi.fn(),
    clearSession: vi.fn(),
    ...overrides,
  }
}

function renderPage(outletContextOverrides: Partial<DashboardOutletContext> = {}) {
  const outletContext: DashboardOutletContext = {
    resumeAnalysis: fixtureResumeAnalysis,
    setResumeAnalysis: vi.fn(),
    resume: fixtureResume,
    onResumeChange: vi.fn(),
    jobDescription: fixtureJobDescription,
    onJobDescriptionChange: vi.fn(),
    status: 'success',
    setStatus: vi.fn(),
    errorMessage: '',
    setErrorMessage: vi.fn(),
    isInputCollapsed: true,
    setIsInputCollapsed: vi.fn(),
    ...outletContextOverrides,
  }

  function TestLayout() {
    return <Outlet context={outletContext} />
  }

  return render(
    <MemoryRouter initialEntries={['/career-conversation']}>
      <Routes>
        <Route element={<TestLayout />}>
          <Route path="/career-conversation" element={<CareerConversationPage />} />
        </Route>
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('CareerConversationPage hydration gating', () => {
  it('shows a rehydrating state, not the "complete an analysis" empty state, while hydration is pending', () => {
    mockedUseResumeSession.mockReturnValue(
      makeResumeSessionValue({ hydrationStatus: 'pending' }),
    )
    renderPage({ resumeAnalysis: null, resume: null, jobDescription: null })

    expect(screen.getByText(/restoring your session/i)).toBeInTheDocument()
    expect(screen.queryByText(/complete a resume analysis first/i)).not.toBeInTheDocument()
    expect(mockedApi.getCareerConversation).not.toHaveBeenCalled()
    expect(mockedApi.startCareerConversation).not.toHaveBeenCalled()
  })

  it('shows the "complete an analysis" empty state once hydrated with no context', () => {
    mockedUseResumeSession.mockReturnValue(makeResumeSessionValue({ hydrationStatus: 'hydrated' }))
    renderPage({ resumeAnalysis: null, resume: null, jobDescription: null })

    expect(screen.getByText(/complete a resume analysis first/i)).toBeInTheDocument()
  })
})

describe('CareerConversationPage restoration', () => {
  it('restores an existing conversation via GET when a session id is already active, and never starts a new one', async () => {
    mockedUseResumeSession.mockReturnValue(
      makeResumeSessionValue({ activeCareerConversationSessionId: 'conv-1' }),
    )
    mockedApi.getCareerConversation.mockResolvedValue(fixtureSession)

    renderPage()

    await waitFor(() => expect(mockedApi.getCareerConversation).toHaveBeenCalledWith('conv-1'))
    expect(mockedApi.startCareerConversation).not.toHaveBeenCalled()
    await waitFor(() =>
      expect(screen.getByText(fixtureSession.current_question!.question)).toBeInTheDocument(),
    )
    // Called exactly once -- no duplicate fetch.
    expect(mockedApi.getCareerConversation).toHaveBeenCalledTimes(1)
  })

  it('starts a new conversation when there is no active session id, and records the returned id', async () => {
    const setActiveCareerConversationSessionId = vi.fn()
    mockedUseResumeSession.mockReturnValue(
      makeResumeSessionValue({
        activeCareerConversationSessionId: null,
        setActiveCareerConversationSessionId,
      }),
    )
    mockedApi.startCareerConversation.mockResolvedValue(fixtureSession)

    renderPage()

    await waitFor(() => expect(mockedApi.startCareerConversation).toHaveBeenCalledTimes(1))
    expect(mockedApi.getCareerConversation).not.toHaveBeenCalled()
    expect(setActiveCareerConversationSessionId).toHaveBeenCalledWith(fixtureSession.session_id)
  })

  it('threads the session jobPreparationId through to startCareerConversation', async () => {
    mockedUseResumeSession.mockReturnValue(
      makeResumeSessionValue({
        activeCareerConversationSessionId: null,
        jobPreparationId: 'job-prep-1',
      }),
    )
    mockedApi.startCareerConversation.mockResolvedValue(fixtureSession)

    renderPage()

    await waitFor(() =>
      expect(mockedApi.startCareerConversation).toHaveBeenCalledWith(
        fixtureResume.text,
        fixtureJobDescription.text,
        fixtureResumeAnalysis,
        'job-prep-1',
      ),
    )
  })

  it('on a stale (404) session id, clears only the id and shows a recovery action instead of silently starting a new conversation', async () => {
    const setActiveCareerConversationSessionId = vi.fn()
    mockedUseResumeSession.mockReturnValue(
      makeResumeSessionValue({
        activeCareerConversationSessionId: 'stale-conv',
        setActiveCareerConversationSessionId,
      }),
    )
    mockedApi.getCareerConversation.mockRejectedValue(
      new ApiError('gone', { cause: 'not_found' }),
    )

    renderPage()

    await waitFor(() => expect(setActiveCareerConversationSessionId).toHaveBeenCalledWith(null))
    expect(screen.getByText(/could not be found/i)).toBeInTheDocument()
    // No auto-start on the user's behalf -- analysis context is preserved
    // (resume/jobDescription/resumeAnalysis untouched) so they can retry.
    expect(mockedApi.startCareerConversation).not.toHaveBeenCalled()
  })

  it('on a non-404 failure (e.g. HTTP 500), preserves the stored session id and shows a retry action instead of clearing it', async () => {
    const setActiveCareerConversationSessionId = vi.fn()
    mockedUseResumeSession.mockReturnValue(
      makeResumeSessionValue({
        activeCareerConversationSessionId: 'conv-1',
        setActiveCareerConversationSessionId,
      }),
    )
    mockedApi.getCareerConversation.mockRejectedValue(
      new ApiError('Restoring the conversation failed (HTTP 500).'),
    )

    renderPage()

    await waitFor(() =>
      expect(screen.getByText(/restoring the conversation failed/i)).toBeInTheDocument(),
    )
    // Unlike the 404/stale-session case, a transient server error must not
    // throw away a perfectly good session id -- the retry button below
    // should re-fetch the same session, not start a brand new one.
    expect(setActiveCareerConversationSessionId).not.toHaveBeenCalled()
    expect(mockedApi.startCareerConversation).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: /try again/i })).toBeInTheDocument()

    // Retrying re-fetches the same session id, not a new conversation.
    mockedApi.getCareerConversation.mockResolvedValueOnce(fixtureSession)
    screen.getByRole('button', { name: /try again/i }).click()

    await waitFor(() =>
      expect(screen.getByText(fixtureSession.current_question!.question)).toBeInTheDocument(),
    )
    expect(mockedApi.getCareerConversation).toHaveBeenLastCalledWith('conv-1')
    expect(mockedApi.startCareerConversation).not.toHaveBeenCalled()
  })

  it('does not issue duplicate restore calls under a StrictMode-style double effect invocation', async () => {
    mockedUseResumeSession.mockReturnValue(
      makeResumeSessionValue({ activeCareerConversationSessionId: 'conv-1' }),
    )
    mockedApi.getCareerConversation.mockResolvedValue(fixtureSession)

    render(
      <StrictModeHarness>
        <MemoryRouter initialEntries={['/career-conversation']}>
          <Routes>
            <Route
              element={
                <Outlet
                  context={{
                    resumeAnalysis: fixtureResumeAnalysis,
                    setResumeAnalysis: vi.fn(),
                    resume: fixtureResume,
                    onResumeChange: vi.fn(),
                    jobDescription: fixtureJobDescription,
                    onJobDescriptionChange: vi.fn(),
                    status: 'success',
                    setStatus: vi.fn(),
                    errorMessage: '',
                    setErrorMessage: vi.fn(),
                    isInputCollapsed: true,
                    setIsInputCollapsed: vi.fn(),
                  } satisfies DashboardOutletContext}
                />
              }
            >
              <Route path="/career-conversation" element={<CareerConversationPage />} />
            </Route>
          </Routes>
        </MemoryRouter>
      </StrictModeHarness>,
    )

    await waitFor(() =>
      expect(screen.getByText(fixtureSession.current_question!.question)).toBeInTheDocument(),
    )
    expect(mockedApi.getCareerConversation).toHaveBeenCalledTimes(1)
  })
})

function StrictModeHarness({ children }: { children: ReactNode }) {
  return <StrictMode>{children}</StrictMode>
}

describe('CareerConversationPage answer submission', () => {
  async function renderReadyPage() {
    mockedUseResumeSession.mockReturnValue(
      makeResumeSessionValue({ activeCareerConversationSessionId: 'conv-1' }),
    )
    mockedApi.getCareerConversation.mockResolvedValue(fixtureSession)
    renderPage()
    await waitFor(() =>
      expect(screen.getByText(fixtureSession.current_question!.question)).toBeInTheDocument(),
    )
  }

  it('submits the answer and shows the next question on success', async () => {
    await renderReadyPage()
    const nextSession = {
      ...fixtureSession,
      history: [
        {
          topic: fixtureSession.current_question!.topic,
          question: fixtureSession.current_question!.question,
          answer: 'I led the migration.',
          assistant_response: null,
        },
      ],
      current_question: {
        topic: 'Ownership',
        question: 'Tell me about your ownership of the project.',
        evidence_goal: 'Assess ownership.',
        estimated_impact: 'high' as const,
        assistant_response: null,
      },
    }
    mockedApi.submitCareerConversationAnswer.mockResolvedValue(nextSession)

    fireEvent.change(screen.getByPlaceholderText(/share your answer/i), {
      target: { value: 'I led the migration.' },
    })
    fireEvent.click(screen.getByRole('button', { name: /continue/i }))

    await waitFor(() =>
      expect(
        screen.getByText('Tell me about your ownership of the project.'),
      ).toBeInTheDocument(),
    )
    expect(screen.getByPlaceholderText(/share your answer/i)).toHaveValue('')
  })

  it('on a 409, automatically refetches and resumes with the authoritative state instead of showing an error', async () => {
    await renderReadyPage()
    const authoritativeSession = {
      ...fixtureSession,
      status: 'complete' as const,
      current_question: null,
      stop_reason: 'Enough evidence recovered.',
      history: [
        {
          topic: fixtureSession.current_question!.topic,
          question: fixtureSession.current_question!.question,
          answer: 'Someone else already answered this.',
          assistant_response: null,
        },
      ],
    }
    mockedApi.submitCareerConversationAnswer.mockRejectedValue(
      new ApiError('This conversation has already moved on from that question.', {
        cause: 'conflict',
      }),
    )
    mockedApi.getCareerConversation.mockResolvedValueOnce(authoritativeSession)

    fireEvent.change(screen.getByPlaceholderText(/share your answer/i), {
      target: { value: 'I led the migration.' },
    })
    fireEvent.click(screen.getByRole('button', { name: /continue/i }))

    await waitFor(() =>
      expect(screen.getByText(/career conversation complete/i)).toBeInTheDocument(),
    )
    // No error state shown at any point -- this was a recoverable sync event.
    expect(screen.queryByText(/conversation didn't load/i)).not.toBeInTheDocument()
    expect(mockedApi.getCareerConversation).toHaveBeenLastCalledWith(fixtureSession.session_id)
  })

  it('falls back to the error state if the post-409 refetch itself also fails', async () => {
    await renderReadyPage()
    mockedApi.submitCareerConversationAnswer.mockRejectedValue(
      new ApiError('conflict', { cause: 'conflict' }),
    )
    mockedApi.getCareerConversation.mockRejectedValueOnce(new ApiError('network down'))

    fireEvent.change(screen.getByPlaceholderText(/share your answer/i), {
      target: { value: 'I led the migration.' },
    })
    fireEvent.click(screen.getByRole('button', { name: /continue/i }))

    await waitFor(() => expect(screen.getByText(/conversation didn't load/i)).toBeInTheDocument())
  })

  it('shows the normal error state (no auto-recovery) for a non-409 failure', async () => {
    await renderReadyPage()
    mockedApi.submitCareerConversationAnswer.mockRejectedValue(
      new ApiError('Submitting your answer failed (HTTP 500).'),
    )

    fireEvent.change(screen.getByPlaceholderText(/share your answer/i), {
      target: { value: 'I led the migration.' },
    })
    fireEvent.click(screen.getByRole('button', { name: /continue/i }))

    await waitFor(() =>
      expect(screen.getByText(/submitting your answer failed/i)).toBeInTheDocument(),
    )
    // Only the initial restore -- no post-failure recovery refetch for a
    // plain (non-409) failure.
    expect(mockedApi.getCareerConversation).toHaveBeenCalledTimes(1)
  })
})
