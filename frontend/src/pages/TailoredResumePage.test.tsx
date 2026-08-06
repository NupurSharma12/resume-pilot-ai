import { StrictMode, type ReactNode } from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { MemoryRouter, Route, Routes, Outlet } from 'react-router-dom'
import TailoredResumePage from './TailoredResumePage'
import * as careerConversationApi from '../lib/careerConversationApi'
import * as tailoringSuggestionsApi from '../lib/tailoringSuggestionsApi'
import * as resumeSessionContext from '../session/ResumeSessionContext'
import { ResumeSessionProvider } from '../session/ResumeSessionContext'
import { ApiError } from '../lib/api'
import {
  fixtureApplySuggestionsResponse,
  fixtureGenerateSuggestionsResponse,
  fixtureResume,
  fixtureJobDescription,
  fixtureResumeAnalysis,
  fixtureCompletedSession,
  fixturePersistedSession,
  fixtureSuggestionAppend,
  fixtureSuggestionInsert,
} from '../testFixtures'
import type { DashboardOutletContext } from '../layouts/DashboardLayout'
import type { ResumeSessionContextValue } from '../session/ResumeSessionContext'
import type { PersistedResumeSession, ResumeSessionStorage } from '../session/resumeSessionTypes'

vi.mock('../lib/careerConversationApi')
vi.mock('../lib/tailoringSuggestionsApi')
vi.mock('../session/ResumeSessionContext', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../session/ResumeSessionContext')>()
  // Defaults to the *real* hook (reading from the real `ResumeSessionProvider`),
  // not a bare `vi.fn()` -- the "gating" tests below override it per-test with
  // a static `mockReturnValue`, but the interaction tests
  // (`renderPageWithRealSession`) rely on the real provider actually working,
  // since they need state setters to genuinely re-render the page.
  return { ...actual, useResumeSession: vi.fn(actual.useResumeSession) }
})

const mockedCareerConversationApi = vi.mocked(careerConversationApi)
const mockedTailoringApi = vi.mocked(tailoringSuggestionsApi)
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

// A real `ResumeSessionProvider` (not the mocked hook) so state setters
// genuinely re-render the page -- required for the generate/apply/export
// interaction tests below, where a mocked static `useResumeSession()`
// return value can't reflect a state update in response to the page's
// own action.
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

function renderPageWithRealSession(overrides: Partial<PersistedResumeSession> = {}) {
  const storage = createFakeStorage(
    fixturePersistedSession({
      activeCareerConversationSessionId: 'session-123',
      careerConversationStatus: 'complete',
      ...overrides,
    }),
  )
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
    expect(mockedTailoringApi.generateTailoringSuggestions).not.toHaveBeenCalled()
  })

  it('shows a "complete an analysis first" empty state when there is no analysis context', () => {
    mockedUseResumeSession.mockReturnValue(makeResumeSessionValue())

    renderPage({ resumeAnalysis: null, resume: null, jobDescription: null })

    expect(screen.getByText(/complete a resume analysis first/i)).toBeInTheDocument()
  })

  it('shows a "complete career conversation first" empty state when no session is active', () => {
    mockedUseResumeSession.mockReturnValue(
      makeResumeSessionValue({ activeCareerConversationSessionId: null, careerConversationStatus: null }),
    )

    renderPage()

    expect(screen.getByText(/complete a career conversation first/i)).toBeInTheDocument()
    expect(mockedTailoringApi.generateTailoringSuggestions).not.toHaveBeenCalled()
  })

  it('shows the same gate when a session exists but has not completed yet', () => {
    mockedUseResumeSession.mockReturnValue(
      makeResumeSessionValue({ careerConversationStatus: 'in_progress' }),
    )

    renderPage()

    expect(screen.getByText(/complete a career conversation first/i)).toBeInTheDocument()
  })
})

describe('TailoredResumePage: generation is never automatic', () => {
  it('does not fetch or generate anything on mount, and shows an explicit "Generate" prompt', async () => {
    mockedUseResumeSession.mockReturnValue(makeResumeSessionValue())

    renderPage()

    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(mockedCareerConversationApi.getCareerConversation).not.toHaveBeenCalled()
    expect(mockedTailoringApi.generateTailoringSuggestions).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: /generate tailoring plan/i })).toBeInTheDocument()
  })

  it('shows the existing plan immediately, without re-fetching, when one is already in session', () => {
    mockedUseResumeSession.mockReturnValue(
      makeResumeSessionValue({
        tailoringPlan: fixtureGenerateSuggestionsResponse,
        tailoringSelections: ['suggestion-0', 'suggestion-1'],
        tailoringAvailableExportFormats: fixtureGenerateSuggestionsResponse.available_export_formats,
      }),
    )

    renderPage()

    expect(screen.getByText(fixtureSuggestionAppend.reason)).toBeInTheDocument()
    expect(mockedCareerConversationApi.getCareerConversation).not.toHaveBeenCalled()
    expect(mockedTailoringApi.generateTailoringSuggestions).not.toHaveBeenCalled()
  })
})

describe('TailoredResumePage: generating suggestions', () => {
  it('fetches the conversation transcript and generates only after the user clicks Generate', async () => {
    mockedCareerConversationApi.getCareerConversation.mockResolvedValue(fixtureCompletedSession)
    mockedTailoringApi.generateTailoringSuggestions.mockResolvedValue(
      fixtureGenerateSuggestionsResponse,
    )

    renderPageWithRealSession()

    expect(mockedTailoringApi.generateTailoringSuggestions).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: /generate tailoring plan/i }))

    await waitFor(() =>
      expect(mockedCareerConversationApi.getCareerConversation).toHaveBeenCalledWith('session-123'),
    )
    expect(mockedTailoringApi.generateTailoringSuggestions).toHaveBeenCalledWith(
      fixtureResume.text,
      fixtureJobDescription.text,
      fixtureResumeAnalysis,
      fixtureCompletedSession,
      '',
      fixtureResume.fileName,
    )

    await waitFor(() =>
      expect(screen.getByText(fixtureSuggestionAppend.reason)).toBeInTheDocument(),
    )
    expect(screen.getByText(fixtureSuggestionInsert.reason)).toBeInTheDocument()
    // Human-language action labels -- never raw backend operation
    // terminology like "Append"/"Insert"/"Rewrite".
    expect(screen.getAllByText('Add').length).toBeGreaterThan(0)
    expect(screen.queryByText(/^append$/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/^insert$/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/^rewrite$/i)).not.toBeInTheDocument()
  })

  it('does not issue duplicate requests under a StrictMode-style double effect invocation', async () => {
    mockedCareerConversationApi.getCareerConversation.mockResolvedValue(fixtureCompletedSession)
    mockedTailoringApi.generateTailoringSuggestions.mockResolvedValue(
      fixtureGenerateSuggestionsResponse,
    )

    function StrictModeHarness({ children }: { children: ReactNode }) {
      return <StrictMode>{children}</StrictMode>
    }
    const storage = createFakeStorage(
      fixturePersistedSession({
        activeCareerConversationSessionId: 'session-123',
        careerConversationStatus: 'complete',
      }),
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

    fireEvent.click(screen.getByRole('button', { name: /generate tailoring plan/i }))

    await waitFor(() =>
      expect(screen.getByText(fixtureSuggestionAppend.reason)).toBeInTheDocument(),
    )
    expect(mockedCareerConversationApi.getCareerConversation).toHaveBeenCalledTimes(1)
    expect(mockedTailoringApi.generateTailoringSuggestions).toHaveBeenCalledTimes(1)
  })

  it('shows an error state with a retry action when generation fails, and retry can succeed', async () => {
    mockedCareerConversationApi.getCareerConversation.mockResolvedValue(fixtureCompletedSession)
    mockedTailoringApi.generateTailoringSuggestions.mockRejectedValueOnce(
      new ApiError('Could not reach the tailoring service. Is the backend running?'),
    )

    renderPageWithRealSession()
    fireEvent.click(screen.getByRole('button', { name: /generate tailoring plan/i }))

    await waitFor(() =>
      expect(screen.getByText(/could not reach the tailoring service/i)).toBeInTheDocument(),
    )
    expect(screen.getByRole('button', { name: /try again/i })).toBeInTheDocument()

    mockedTailoringApi.generateTailoringSuggestions.mockResolvedValueOnce(
      fixtureGenerateSuggestionsResponse,
    )
    fireEvent.click(screen.getByRole('button', { name: /try again/i }))

    await waitFor(() =>
      expect(screen.getByText(fixtureSuggestionAppend.reason)).toBeInTheDocument(),
    )
  })
})

describe('TailoredResumePage: reviewing and selecting suggestions', () => {
  function renderWithPlan(overrides: Partial<PersistedResumeSession> = {}) {
    return renderPageWithRealSession({
      tailoringPlan: fixtureGenerateSuggestionsResponse,
      tailoringSelections: ['suggestion-0', 'suggestion-1'],
      tailoringAvailableExportFormats: fixtureGenerateSuggestionsResponse.available_export_formats,
      ...overrides,
    })
  }

  it('collapses everything but a concise summary for an append suggestion by default', () => {
    renderWithPlan()

    // Only the one-line human-readable summary shows by default -- never
    // the full resulting text, and never the original text unprompted.
    expect(screen.getByText('Add TypeScript')).toBeInTheDocument()
    expect(screen.queryByText('Python, TypeScript')).not.toBeInTheDocument()
    expect(screen.queryByText('Python')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /view current resume text/i }))
    expect(screen.getByText('Python')).toBeInTheDocument()

    fireEvent.click(screen.getAllByRole('button', { name: /preview change/i })[0])
    expect(screen.getByText('TypeScript')).toBeInTheDocument()
  })

  it('shows the suggested text only after Preview Change is clicked, for an insertion operation', () => {
    renderWithPlan()

    expect(screen.queryByText(fixtureSuggestionInsert.suggested_text)).not.toBeInTheDocument()

    fireEvent.click(screen.getAllByRole('button', { name: /preview change/i })[1])

    expect(screen.getByText(fixtureSuggestionInsert.suggested_text)).toBeInTheDocument()
  })

  it('shows a human-readable section name, never the internal section id', () => {
    renderWithPlan()

    expect(screen.queryByText('section-1')).not.toBeInTheDocument()
    expect(screen.queryByText('section-2')).not.toBeInTheDocument()
  })

  it('shows the selected count and toggling one checkbox does not affect the other', () => {
    renderWithPlan()

    expect(screen.getByText('2 of 2 selected')).toBeInTheDocument()

    const checkboxes = screen.getAllByRole('checkbox')
    fireEvent.click(checkboxes[0])

    expect(screen.getByText('1 of 2 selected')).toBeInTheDocument()
    expect(checkboxes[1]).toBeChecked()
  })

  it('Clear All clears every selection, and Select All reselects every suggestion', () => {
    renderWithPlan()

    fireEvent.click(screen.getByRole('button', { name: /clear all/i }))
    expect(screen.getByText('0 of 2 selected')).toBeInTheDocument()
    screen.getAllByRole('checkbox').forEach((checkbox) => expect(checkbox).not.toBeChecked())

    fireEvent.click(screen.getByRole('button', { name: /select all/i }))
    expect(screen.getByText('2 of 2 selected')).toBeInTheDocument()
    screen.getAllByRole('checkbox').forEach((checkbox) => expect(checkbox).toBeChecked())
  })

  it('persists custom instructions as the user types', () => {
    renderWithPlan()

    const textarea = screen.getByPlaceholderText(/optional instructions/i)
    fireEvent.change(textarea, { target: { value: 'Keep the resume under two pages.' } })

    expect(textarea).toHaveValue('Keep the resume under two pages.')
  })

  it('lets a user customize a suggestion, marks it as edited, and Reset restores the original', () => {
    renderWithPlan()

    // Clicking Customize opens the Preview Change panel directly into
    // edit mode. Editing operates on the item's full resulting text
    // (what's actually sent to the backend), even though the card's
    // collapsed summary only ever teases the append delta -- see
    // `computeAppendedDelta`.
    fireEvent.click(screen.getAllByRole('button', { name: /^customize$/i })[0])
    const textarea = screen.getByDisplayValue(fixtureSuggestionAppend.suggested_text)
    fireEvent.change(textarea, { target: { value: 'Python, TypeScript, and GraphQL' } })
    fireEvent.click(screen.getByRole('button', { name: /^save$/i }))

    // The one-line summary reflects the edited text, not the original.
    expect(screen.getByText('Add TypeScript, and GraphQL')).toBeInTheDocument()
    expect(screen.getByText('Edited')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /^reset$/i }))

    expect(screen.getByText('Add TypeScript')).toBeInTheDocument()
    expect(screen.queryByText('Edited')).not.toBeInTheDocument()
  })

  it('sends edited text only for the edited, selected suggestion', async () => {
    mockedTailoringApi.applyTailoringSuggestions.mockResolvedValue(fixtureApplySuggestionsResponse)

    renderWithPlan()
    fireEvent.click(screen.getAllByRole('button', { name: /^customize$/i })[0])
    fireEvent.change(screen.getByDisplayValue(fixtureSuggestionAppend.suggested_text), {
      target: { value: 'Python, TypeScript, and GraphQL' },
    })
    fireEvent.click(screen.getByRole('button', { name: /^save$/i }))
    fireEvent.click(screen.getByRole('button', { name: /apply selected changes/i }))

    await waitFor(() =>
      expect(mockedTailoringApi.applyTailoringSuggestions).toHaveBeenCalledWith(
        fixtureGenerateSuggestionsResponse.plan_id,
        ['suggestion-0', 'suggestion-1'],
        { 'suggestion-0': 'Python, TypeScript, and GraphQL' },
      ),
    )
  })
})

describe('TailoredResumePage: applying selected changes', () => {
  function renderWithPlan(overrides: Partial<PersistedResumeSession> = {}) {
    return renderPageWithRealSession({
      tailoringPlan: fixtureGenerateSuggestionsResponse,
      tailoringSelections: ['suggestion-0', 'suggestion-1'],
      tailoringAvailableExportFormats: fixtureGenerateSuggestionsResponse.available_export_formats,
      ...overrides,
    })
  }

  it('is disabled when no suggestions are selected', () => {
    renderWithPlan({ tailoringSelections: [] })

    expect(screen.getByRole('button', { name: /apply selected changes/i })).toBeDisabled()
  })

  it('sends only the selected suggestion ids, not unselected ones', async () => {
    mockedTailoringApi.applyTailoringSuggestions.mockResolvedValue(fixtureApplySuggestionsResponse)

    renderWithPlan()
    // Deselect the second suggestion.
    fireEvent.click(screen.getAllByRole('checkbox')[1])
    fireEvent.click(screen.getByRole('button', { name: /apply selected changes/i }))

    await waitFor(() =>
      expect(mockedTailoringApi.applyTailoringSuggestions).toHaveBeenCalledWith(
        fixtureGenerateSuggestionsResponse.plan_id,
        ['suggestion-0'],
        {},
      ),
    )
  })

  it('shows the final resume preview and applied-changes summary after a successful apply', async () => {
    mockedTailoringApi.applyTailoringSuggestions.mockResolvedValue(fixtureApplySuggestionsResponse)

    renderWithPlan()
    fireEvent.click(screen.getByRole('button', { name: /apply selected changes/i }))

    await waitFor(() =>
      expect(screen.getByText(/final resume preview/i)).toBeInTheDocument(),
    )
    expect(screen.getByText((_, el) => el?.tagName === 'PRE' && el.textContent === fixtureApplySuggestionsResponse.final_resume_text)).toBeInTheDocument()
    expect(screen.getByText(/applied changes \(1\)/i)).toBeInTheDocument()
    expect(screen.getByText(/not included \(1\)/i)).toBeInTheDocument()
  })

  it('shows an actionable inline error for a revalidation failure (422) without losing selections', async () => {
    mockedTailoringApi.applyTailoringSuggestions.mockRejectedValue(
      new ApiError("Edited text for suggestion 'suggestion-0' failed validation: Contains Kubernetes.", {
        cause: 'revalidation_failed',
      }),
    )

    renderWithPlan()
    fireEvent.click(screen.getByRole('button', { name: /apply selected changes/i }))

    await waitFor(() => expect(screen.getByText(/contains kubernetes/i)).toBeInTheDocument())
    expect(screen.getByText('2 of 2 selected')).toBeInTheDocument()
  })

  it('preserves the last successful final resume after a later apply failure', async () => {
    mockedTailoringApi.applyTailoringSuggestions.mockResolvedValueOnce(
      fixtureApplySuggestionsResponse,
    )

    renderWithPlan()
    fireEvent.click(screen.getByRole('button', { name: /apply selected changes/i }))
    await waitFor(() =>
      expect(screen.getByText((_, el) => el?.tagName === 'PRE' && el.textContent === fixtureApplySuggestionsResponse.final_resume_text)).toBeInTheDocument(),
    )

    mockedTailoringApi.applyTailoringSuggestions.mockRejectedValueOnce(
      new ApiError('Something went wrong applying changes.'),
    )
    fireEvent.click(screen.getByRole('button', { name: /apply selected changes/i }))

    await waitFor(() =>
      expect(screen.getByText(/something went wrong applying changes/i)).toBeInTheDocument(),
    )
    // The previously successful final resume must still be visible.
    expect(screen.getByText((_, el) => el?.tagName === 'PRE' && el.textContent === fixtureApplySuggestionsResponse.final_resume_text)).toBeInTheDocument()
  })
})

describe('TailoredResumePage: download options', () => {
  function renderApplied(overrides: Partial<PersistedResumeSession> = {}) {
    return renderPageWithRealSession({
      tailoringPlan: fixtureGenerateSuggestionsResponse,
      tailoringSelections: ['suggestion-0'],
      tailoringAvailableExportFormats: fixtureGenerateSuggestionsResponse.available_export_formats,
      finalTailoredResume: {
        finalResumeText: fixtureApplySuggestionsResponse.final_resume_text,
        appliedSuggestionIds: fixtureApplySuggestionsResponse.applied_suggestion_ids,
      },
      tailoringValidationReport: fixtureApplySuggestionsResponse.final_validation,
      ...overrides,
    })
  }

  it('only shows formats the backend reported as available, and marks the default', () => {
    renderApplied({
      tailoringAvailableExportFormats: ['txt', 'pdf'],
    })

    expect(screen.getByRole('button', { name: /^download txt$/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^download pdf$/i })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^download docx$/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^download markdown$/i })).not.toBeInTheDocument()
    expect(screen.getByText('Default')).toBeInTheDocument()
  })

  it('honestly labels DOCX and PDF as regenerated, never implying original styling is preserved', () => {
    renderApplied()

    expect(screen.getByText(/regenerated pdf/i)).toBeInTheDocument()
    expect(screen.getByText(/regenerated docx/i)).toBeInTheDocument()
    expect(screen.getByText(/^plain text\./i)).toBeInTheDocument()
  })

  it('a failed export leaves the preview visible and shows an inline error', async () => {
    mockedTailoringApi.exportTailoredResume.mockRejectedValue(
      new ApiError('Exporting the resume failed (HTTP 500).'),
    )

    renderApplied()
    fireEvent.click(screen.getByRole('button', { name: /^download txt$/i }))

    await waitFor(() =>
      expect(screen.getByText(/exporting the resume failed/i)).toBeInTheDocument(),
    )
    // The final resume preview must still be visible.
    expect(screen.getByText((_, el) => el?.tagName === 'PRE' && el.textContent === fixtureApplySuggestionsResponse.final_resume_text)).toBeInTheDocument()
  })

  it('a successful export calls downloadExportedFile', async () => {
    mockedTailoringApi.exportTailoredResume.mockResolvedValue({
      blob: new Blob(['content']),
      filename: 'Tailored_Resume.txt',
      contentType: 'text/plain',
      fidelity: 'approximate_style',
    })

    renderApplied()
    fireEvent.click(screen.getByRole('button', { name: /^download txt$/i }))

    await waitFor(() => expect(mockedTailoringApi.downloadExportedFile).toHaveBeenCalled())
  })
})

describe('TailoredResumePage: refresh restores state', () => {
  it('restores the review stage (plan + selections) without any network calls', () => {
    renderPageWithRealSession({
      tailoringPlan: fixtureGenerateSuggestionsResponse,
      tailoringSelections: ['suggestion-0'],
      tailoringAvailableExportFormats: fixtureGenerateSuggestionsResponse.available_export_formats,
    })

    expect(screen.getByText('1 of 2 selected')).toBeInTheDocument()
    expect(mockedTailoringApi.generateTailoringSuggestions).not.toHaveBeenCalled()
  })

  it('restores the final preview/download stage without any network calls', () => {
    renderPageWithRealSession({
      tailoringPlan: fixtureGenerateSuggestionsResponse,
      tailoringSelections: ['suggestion-0'],
      tailoringAvailableExportFormats: fixtureGenerateSuggestionsResponse.available_export_formats,
      finalTailoredResume: {
        finalResumeText: fixtureApplySuggestionsResponse.final_resume_text,
        appliedSuggestionIds: fixtureApplySuggestionsResponse.applied_suggestion_ids,
      },
      tailoringValidationReport: fixtureApplySuggestionsResponse.final_validation,
    })

    expect(screen.getByText((_, el) => el?.tagName === 'PRE' && el.textContent === fixtureApplySuggestionsResponse.final_resume_text)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^download txt$/i })).toBeInTheDocument()
    expect(mockedTailoringApi.generateTailoringSuggestions).not.toHaveBeenCalled()
    expect(mockedTailoringApi.applyTailoringSuggestions).not.toHaveBeenCalled()
  })
})
