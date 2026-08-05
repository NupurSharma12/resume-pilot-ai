import { StrictMode, type ReactNode } from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { MemoryRouter, Route, Routes, Outlet } from 'react-router-dom'
import TailoredResumePage from './TailoredResumePage'
import * as careerConversationApi from '../lib/careerConversationApi'
import * as tailorResumeApi from '../lib/tailorResumeApi'
import * as resumeSessionContext from '../session/ResumeSessionContext'
import { ResumeSessionProvider } from '../session/ResumeSessionContext'
import { ApiError } from '../lib/api'
import {
  fixtureResume,
  fixtureJobDescription,
  fixtureResumeAnalysis,
  fixtureCompletedSession,
  fixtureTailorResult,
  fixturePersistedSession,
} from '../testFixtures'
import type { DashboardOutletContext } from '../layouts/DashboardLayout'
import type { ResumeSessionContextValue } from '../session/ResumeSessionContext'
import type { PersistedResumeSession, ResumeSessionStorage } from '../session/resumeSessionTypes'

vi.mock('../lib/careerConversationApi')
vi.mock('../lib/tailorResumeApi')
vi.mock('../session/ResumeSessionContext', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../session/ResumeSessionContext')>()
  // Defaults to the *real* hook (reading from the real `ResumeSessionProvider`),
  // not a bare `vi.fn()` -- the "gating" tests below override it per-test with
  // a static `mockReturnValue`, but the interaction tests
  // (`renderPageWithRealSession`) rely on the real provider actually working,
  // since they need `setTailoredResumeResult` to genuinely re-render the page.
  return { ...actual, useResumeSession: vi.fn(actual.useResumeSession) }
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
    careerConversationStatus: 'complete',
    setCareerConversationStatus: vi.fn(),
    tailoredResumeResult: null,
    setTailoredResumeResult: vi.fn(),
    clearSession: vi.fn(),
    ...overrides,
  }
}

const OUTLET_CONTEXT: DashboardOutletContext = {
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
}

function renderPage(outletContextOverrides: Partial<DashboardOutletContext> = {}) {
  const outletContext: DashboardOutletContext = { ...OUTLET_CONTEXT, ...outletContextOverrides }

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

// A real `ResumeSessionProvider` (not the mocked hook) so `setTailoredResumeResult`
// genuinely re-renders the page with new data -- required for the
// generate/regenerate interaction tests below, where a mocked static
// `useResumeSession()` return value can't reflect a state update in
// response to the page's own action.
function createFakeStorage(initial: PersistedResumeSession | null): ResumeSessionStorage {
  let state = initial
  return {
    load: () => state,
    save: (session) => {
      state = session
    },
    clear: () => {
      state = null
    },
  }
}

function renderPageWithRealSession(
  overrides: Partial<PersistedResumeSession> = { activeCareerConversationSessionId: 'session-123' },
) {
  const storage = createFakeStorage(fixturePersistedSession(overrides))
  function TestLayout() {
    return <Outlet context={OUTLET_CONTEXT} />
  }

  return render(
    <ResumeSessionProvider storage={storage}>
      <MemoryRouter initialEntries={['/tailored-resume']}>
        <Routes>
          <Route element={<TestLayout />}>
            <Route path="/tailored-resume" element={<TailoredResumePage />} />
          </Route>
        </Routes>
      </MemoryRouter>
    </ResumeSessionProvider>,
  )
}

beforeEach(async () => {
  vi.clearAllMocks()
  // `clearAllMocks` clears call history but not a previously-set
  // `mockReturnValue`/`mockImplementation` -- without this, a "gating" test
  // that overrides `useResumeSession` would leak its static value into
  // whichever test runs next, silently breaking any test relying on the
  // real provider (see the mock factory above). `vi.importActual` (not a
  // module-level variable captured inside the `vi.mock` factory -- vitest
  // forbids that, since factories are hoisted above other top-level code)
  // is what gets the real, unmocked implementation back here.
  const actual = await vi.importActual<typeof import('../session/ResumeSessionContext')>(
    '../session/ResumeSessionContext',
  )
  mockedUseResumeSession.mockImplementation(actual.useResumeSession)
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

describe('TailoredResumePage: generation is never automatic', () => {
  it('does not fetch or generate anything on mount, and shows an explicit "Generate" prompt', async () => {
    mockedUseResumeSession.mockReturnValue(makeResumeSessionValue())

    renderPage()

    // Give any accidental effect a chance to fire before asserting it didn't.
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(mockedCareerConversationApi.getCareerConversation).not.toHaveBeenCalled()
    expect(mockedTailorResumeApi.tailorResume).not.toHaveBeenCalled()
    expect(
      screen.getByRole('button', { name: /generate tailored resume/i }),
    ).toBeInTheDocument()
  })

  it('shows the existing result immediately, without re-fetching, when one is already in session', () => {
    mockedUseResumeSession.mockReturnValue(
      makeResumeSessionValue({ tailoredResumeResult: fixtureTailorResult }),
    )

    renderPage()

    expect(
      screen.getByText('Led the migration of the dashboard from Angular to React.'),
    ).toBeInTheDocument()
    expect(mockedCareerConversationApi.getCareerConversation).not.toHaveBeenCalled()
    expect(mockedTailorResumeApi.tailorResume).not.toHaveBeenCalled()
  })
})

describe('TailoredResumePage: explicit generation', () => {
  it('fetches the conversation transcript and generates only after the user clicks Generate', async () => {
    mockedCareerConversationApi.getCareerConversation.mockResolvedValue(fixtureCompletedSession)
    mockedTailorResumeApi.tailorResume.mockResolvedValue(fixtureTailorResult)

    renderPageWithRealSession()

    expect(mockedTailorResumeApi.tailorResume).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: /generate tailored resume/i }))

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
    mockedCareerConversationApi.getCareerConversation.mockResolvedValue(fixtureCompletedSession)
    mockedTailorResumeApi.tailorResume.mockResolvedValue(fixtureTailorResult)

    function StrictModeHarness({ children }: { children: ReactNode }) {
      return <StrictMode>{children}</StrictMode>
    }
    const storage = createFakeStorage(
      fixturePersistedSession({ activeCareerConversationSessionId: 'session-123' }),
    )

    render(
      <StrictModeHarness>
        <ResumeSessionProvider storage={storage}>
          <MemoryRouter initialEntries={['/tailored-resume']}>
            <Routes>
              <Route element={<Outlet context={OUTLET_CONTEXT} />}>
                <Route path="/tailored-resume" element={<TailoredResumePage />} />
              </Route>
            </Routes>
          </MemoryRouter>
        </ResumeSessionProvider>
      </StrictModeHarness>,
    )

    fireEvent.click(screen.getByRole('button', { name: /generate tailored resume/i }))

    await waitFor(() =>
      expect(
        screen.getByText('Led the migration of the dashboard from Angular to React.'),
      ).toBeInTheDocument(),
    )
    expect(mockedCareerConversationApi.getCareerConversation).toHaveBeenCalledTimes(1)
    expect(mockedTailorResumeApi.tailorResume).toHaveBeenCalledTimes(1)
  })

  it('regenerating an existing result calls the API again and replaces it', async () => {
    mockedCareerConversationApi.getCareerConversation.mockResolvedValue(fixtureCompletedSession)
    mockedTailorResumeApi.tailorResume.mockResolvedValue(fixtureTailorResult)

    renderPageWithRealSession({
      activeCareerConversationSessionId: 'session-123',
      tailoredResumeResult: fixtureTailorResult,
    })

    expect(mockedTailorResumeApi.tailorResume).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: /regenerate/i }))

    await waitFor(() => expect(mockedTailorResumeApi.tailorResume).toHaveBeenCalledTimes(1))
  })
})

describe('TailoredResumePage error handling', () => {
  it('shows an error state with a retry action when generation fails, and retry can succeed', async () => {
    mockedCareerConversationApi.getCareerConversation.mockResolvedValue(fixtureCompletedSession)
    mockedTailorResumeApi.tailorResume.mockRejectedValueOnce(
      new ApiError('Could not reach the tailoring service. Is the backend running?'),
    )

    renderPageWithRealSession()
    fireEvent.click(screen.getByRole('button', { name: /generate tailored resume/i }))

    await waitFor(() =>
      expect(screen.getByText(/could not reach the tailoring service/i)).toBeInTheDocument(),
    )
    expect(screen.getByRole('button', { name: /try again/i })).toBeInTheDocument()

    mockedTailorResumeApi.tailorResume.mockResolvedValueOnce(fixtureTailorResult)
    fireEvent.click(screen.getByRole('button', { name: /try again/i }))

    await waitFor(() =>
      expect(
        screen.getByText('Led the migration of the dashboard from Angular to React.'),
      ).toBeInTheDocument(),
    )
    expect(mockedTailorResumeApi.tailorResume).toHaveBeenCalledTimes(2)
  })

  it('shows an error state when fetching the conversation transcript itself fails', async () => {
    mockedCareerConversationApi.getCareerConversation.mockRejectedValue(
      new ApiError('This conversation session no longer exists.', { cause: 'not_found' }),
    )

    renderPageWithRealSession()
    fireEvent.click(screen.getByRole('button', { name: /generate tailored resume/i }))

    await waitFor(() => expect(screen.getByText(/no longer exists/i)).toBeInTheDocument())
    expect(mockedTailorResumeApi.tailorResume).not.toHaveBeenCalled()
  })
})
