import { StrictMode, type ReactNode } from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes, Outlet } from 'react-router-dom'
import TailoredResumePage from './TailoredResumePage'
import * as careerConversationApi from '../lib/careerConversationApi'
import * as tailorResumeApi from '../lib/tailorResumeApi'
import * as resumeSessionContext from '../session/ResumeSessionContext'
import { ApiError } from '../lib/api'
import {
  fixtureResume,
  fixtureJobDescription,
  fixtureResumeAnalysis,
  fixtureCompletedSession,
  fixtureTailorResult,
} from '../testFixtures'
import type { DashboardOutletContext } from '../layouts/DashboardLayout'
import type { ResumeSessionContextValue } from '../session/ResumeSessionContext'

vi.mock('../lib/careerConversationApi')
vi.mock('../lib/tailorResumeApi')
vi.mock('../session/ResumeSessionContext', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../session/ResumeSessionContext')>()
  return { ...actual, useResumeSession: vi.fn() }
})

const mockedCareerConversationApi = vi.mocked(careerConversationApi)
const mockedTailorResumeApi = vi.mocked(tailorResumeApi)
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
    activeCareerConversationSessionId: 'session-123',
    setActiveCareerConversationSessionId: vi.fn(),
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
    <MemoryRouter initialEntries={['/tailored-resume']}>
      <Routes>
        <Route element={<TestLayout />}>
          <Route path="/tailored-resume" element={<TailoredResumePage />} />
        </Route>
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('TailoredResumePage gating', () => {
  it('shows a rehydrating state while hydration is pending, before any API calls', () => {
    mockedUseResumeSession.mockReturnValue(makeResumeSessionValue({ hydrationStatus: 'pending' }))

    renderPage()

    expect(screen.getByText(/restoring your session/i)).toBeInTheDocument()
    expect(mockedCareerConversationApi.getCareerConversation).not.toHaveBeenCalled()
    expect(mockedTailorResumeApi.tailorResume).not.toHaveBeenCalled()
  })

  it('shows a "complete an analysis first" empty state when there is no analysis context', () => {
    mockedUseResumeSession.mockReturnValue(makeResumeSessionValue())

    renderPage({ resumeAnalysis: null, resume: null, jobDescription: null })

    expect(screen.getByText(/complete a resume analysis first/i)).toBeInTheDocument()
  })

  it('shows a "start a career conversation first" empty state when there is no active session', () => {
    mockedUseResumeSession.mockReturnValue(
      makeResumeSessionValue({ activeCareerConversationSessionId: null }),
    )

    renderPage()

    expect(screen.getByText(/start a career conversation first/i)).toBeInTheDocument()
    expect(mockedTailorResumeApi.tailorResume).not.toHaveBeenCalled()
  })
})

describe('TailoredResumePage generation', () => {
  it('fetches the conversation transcript, generates, and renders plan/resume/validation report', async () => {
    mockedUseResumeSession.mockReturnValue(makeResumeSessionValue())
    mockedCareerConversationApi.getCareerConversation.mockResolvedValue(fixtureCompletedSession)
    mockedTailorResumeApi.tailorResume.mockResolvedValue(fixtureTailorResult)

    renderPage()

    await waitFor(() =>
      expect(mockedCareerConversationApi.getCareerConversation).toHaveBeenCalledWith('session-123'),
    )
    expect(mockedTailorResumeApi.tailorResume).toHaveBeenCalledWith(
      fixtureResume.text,
      fixtureJobDescription.text,
      fixtureResumeAnalysis,
      fixtureCompletedSession,
    )

    await waitFor(() =>
      expect(
        screen.getByText('Led the migration of the dashboard from Angular to React.'),
      ).toBeInTheDocument(),
    )
    expect(screen.getByText(/Recent backend engineering work is missing/)).toBeInTheDocument()
    expect(screen.getByText('1/2 accepted')).toBeInTheDocument()
    expect(
      screen.getByText('Reduced infrastructure costs by 40% using Kubernetes.'),
    ).toBeInTheDocument()
  })

  it('does not issue duplicate requests under a StrictMode-style double effect invocation', async () => {
    mockedUseResumeSession.mockReturnValue(makeResumeSessionValue())
    mockedCareerConversationApi.getCareerConversation.mockResolvedValue(fixtureCompletedSession)
    mockedTailorResumeApi.tailorResume.mockResolvedValue(fixtureTailorResult)

    function StrictModeHarness({ children }: { children: ReactNode }) {
      return <StrictMode>{children}</StrictMode>
    }

    render(
      <StrictModeHarness>
        <MemoryRouter initialEntries={['/tailored-resume']}>
          <Routes>
            <Route
              element={
                <Outlet
                  context={
                    {
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
                    } satisfies DashboardOutletContext
                  }
                />
              }
            >
              <Route path="/tailored-resume" element={<TailoredResumePage />} />
            </Route>
          </Routes>
        </MemoryRouter>
      </StrictModeHarness>,
    )

    await waitFor(() =>
      expect(
        screen.getByText('Led the migration of the dashboard from Angular to React.'),
      ).toBeInTheDocument(),
    )
    expect(mockedCareerConversationApi.getCareerConversation).toHaveBeenCalledTimes(1)
    expect(mockedTailorResumeApi.tailorResume).toHaveBeenCalledTimes(1)
  })
})

describe('TailoredResumePage error handling', () => {
  it('shows an error state with a retry action when generation fails, and retry can succeed', async () => {
    mockedUseResumeSession.mockReturnValue(makeResumeSessionValue())
    mockedCareerConversationApi.getCareerConversation.mockResolvedValue(fixtureCompletedSession)
    mockedTailorResumeApi.tailorResume.mockRejectedValueOnce(
      new ApiError('Could not reach the tailoring service. Is the backend running?'),
    )

    renderPage()

    await waitFor(() =>
      expect(screen.getByText(/could not reach the tailoring service/i)).toBeInTheDocument(),
    )
    expect(screen.getByRole('button', { name: /try again/i })).toBeInTheDocument()

    mockedTailorResumeApi.tailorResume.mockResolvedValueOnce(fixtureTailorResult)
    screen.getByRole('button', { name: /try again/i }).click()

    await waitFor(() =>
      expect(
        screen.getByText('Led the migration of the dashboard from Angular to React.'),
      ).toBeInTheDocument(),
    )
    expect(mockedTailorResumeApi.tailorResume).toHaveBeenCalledTimes(2)
  })

  it('shows an error state when fetching the conversation transcript itself fails', async () => {
    mockedUseResumeSession.mockReturnValue(makeResumeSessionValue())
    mockedCareerConversationApi.getCareerConversation.mockRejectedValue(
      new ApiError('This conversation session no longer exists.', { cause: 'not_found' }),
    )

    renderPage()

    await waitFor(() =>
      expect(screen.getByText(/no longer exists/i)).toBeInTheDocument(),
    )
    expect(mockedTailorResumeApi.tailorResume).not.toHaveBeenCalled()
  })
})
