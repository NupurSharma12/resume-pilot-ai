import { StrictMode, type ReactNode } from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { MemoryRouter, Route, Routes, Outlet } from 'react-router-dom'
import TailoredResumePage from './TailoredResumePage'
import * as careerConversationApi from '../lib/careerConversationApi'
import * as tailoringSuggestionsApi from '../lib/tailoringSuggestionsApi'
import * as postApplyApi from '../lib/postApplyApi'
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
vi.mock('../lib/postApplyApi')
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
const mockedPostApplyApi = vi.mocked(postApplyApi)
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
    postApplyAnalysis: null,
    setPostApplyAnalysis: vi.fn(),
    postApplyComparison: null,
    setPostApplyComparison: vi.fn(),
    postApplyAnalysisStatus: 'idle',
    setPostApplyAnalysisStatus: vi.fn(),
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

  it('shows a previously applied suggestion as already "Applied" and greyed out on a fresh page load, with no click required', () => {
    // Simulates a browser refresh: nothing was clicked this render, the
    // mocked session hook returns exactly what would have been restored
    // from persisted storage (see `finalTailoredResume`'s docstring in
    // resumeSessionTypes.ts -- it's part of the persisted session shape).
    mockedUseResumeSession.mockReturnValue(
      makeResumeSessionValue({
        tailoringPlan: fixtureGenerateSuggestionsResponse,
        tailoringSelections: ['suggestion-0', 'suggestion-1'],
        tailoringAvailableExportFormats: fixtureGenerateSuggestionsResponse.available_export_formats,
        finalTailoredResume: {
          finalResumeText: fixtureApplySuggestionsResponse.final_resume_text,
          appliedSuggestionIds: fixtureApplySuggestionsResponse.applied_suggestion_ids,
        },
        tailoringValidationReport: fixtureApplySuggestionsResponse.final_validation,
      }),
    )

    renderPage()

    // Both the badge and the locked checkbox's own label read "Applied".
    expect(screen.getAllByText('Applied').length).toBeGreaterThanOrEqual(2)
    const appliedCheckbox = screen.getByRole('checkbox', {
      name: /accept suggestion: add typescript/i,
    })
    expect(appliedCheckbox).toBeDisabled()
    expect(appliedCheckbox).toBeChecked()
    // The other, never-applied suggestion looks like a completely normal,
    // still-editable pending suggestion.
    const pendingCheckbox = screen.getByRole('checkbox', {
      name: /accept suggestion: add led the migration/i,
    })
    expect(pendingCheckbox).not.toBeDisabled()
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

  it('opening a per-suggestion Preview Change never calls the apply endpoint', () => {
    renderWithPlan()

    fireEvent.click(screen.getAllByRole('button', { name: /preview change/i })[0])
    fireEvent.click(screen.getAllByRole('button', { name: /preview change/i })[1])

    expect(mockedTailoringApi.applyTailoringSuggestions).not.toHaveBeenCalled()
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
    fireEvent.click(screen.getByRole('button', { name: /preview changes/i }))

    await waitFor(() =>
      expect(mockedTailoringApi.applyTailoringSuggestions).toHaveBeenCalledWith(
        fixtureGenerateSuggestionsResponse.plan_id,
        ['suggestion-0', 'suggestion-1'],
        { 'suggestion-0': 'Python, TypeScript, and GraphQL' },
      ),
    )
  })
})

describe('TailoredResumePage: section grouping and mutually exclusive suggestions', () => {
  // Three atomic suggestions: two independent appends to the Skills item
  // (never conflict, per app.tailoring.conflicts) plus one Experience
  // insertion in a different section -- covers "multiple atomic
  // suggestions for the same section, individually selectable" and
  // "correct UI grouping."
  const secondAppend = {
    ...fixtureSuggestionAppend,
    suggestion_id: 'suggestion-2',
    reason: 'Django experience is missing from Skills.',
    suggested_text: 'Python, Django',
  }
  const planWithIndependentAppends = {
    ...fixtureGenerateSuggestionsResponse,
    suggestions: [fixtureSuggestionAppend, secondAppend, fixtureSuggestionInsert],
  }

  // Two alternative rewordings of the same Skills item -- mutually
  // exclusive, annotated via `conflicts_with` exactly as
  // `app.tailoring.conflicts.compute_conflicts` would compute it.
  const rewriteA = {
    ...fixtureSuggestionAppend,
    suggestion_id: 'suggestion-a',
    operation: 'update' as const,
    suggested_text: 'Pythonista',
    conflicts_with: ['suggestion-b'],
  }
  const rewriteB = {
    ...fixtureSuggestionAppend,
    suggestion_id: 'suggestion-b',
    operation: 'update' as const,
    suggested_text: 'Python expert',
    conflicts_with: ['suggestion-a'],
  }
  const planWithConflict = {
    ...fixtureGenerateSuggestionsResponse,
    suggestions: [rewriteA, rewriteB],
  }

  it('groups suggestions under one heading per section, keeping each one individually selectable', () => {
    const { container } = renderPageWithRealSession({
      tailoringPlan: planWithIndependentAppends,
      tailoringSelections: [],
      tailoringAvailableExportFormats: planWithIndependentAppends.available_export_formats,
    })

    // One group heading per distinct section -- not one per suggestion --
    // even though the two Skills suggestions target the same section.
    const groupHeadings = Array.from(container.querySelectorAll('h3.mb-2')).map(
      (el) => el.textContent,
    )
    expect(groupHeadings).toEqual(['Resume Section 1', 'Resume Section 2'])

    expect(screen.getByText(fixtureSuggestionAppend.reason)).toBeInTheDocument()
    expect(screen.getByText(secondAppend.reason)).toBeInTheDocument()
    expect(screen.getByText(fixtureSuggestionInsert.reason)).toBeInTheDocument()
  })

  it('selects a subset of same-section suggestions independently, with no conflict between them', () => {
    renderPageWithRealSession({
      tailoringPlan: planWithIndependentAppends,
      tailoringSelections: [],
      tailoringAvailableExportFormats: planWithIndependentAppends.available_export_formats,
    })

    const checkboxes = screen.getAllByRole('checkbox')
    fireEvent.click(checkboxes[0])

    expect(screen.getByText('1 of 3 selected')).toBeInTheDocument()
    // Selecting the first append never touches the others' state.
    expect(checkboxes[1]).not.toBeChecked()
    expect(checkboxes[2]).not.toBeChecked()

    fireEvent.click(checkboxes[1])
    expect(screen.getByText('2 of 3 selected')).toBeInTheDocument()
    expect(checkboxes[0]).toBeChecked()
    expect(checkboxes[1]).toBeChecked()
  })

  it('shows a mutually-exclusive note on suggestions that conflict', () => {
    renderPageWithRealSession({
      tailoringPlan: planWithConflict,
      tailoringSelections: [],
      tailoringAvailableExportFormats: planWithConflict.available_export_formats,
    })

    expect(screen.getAllByText(/choose only one: this conflicts with/i)).toHaveLength(2)
  })

  it('auto-deselects a conflicting suggestion when the other one is selected', () => {
    renderPageWithRealSession({
      tailoringPlan: planWithConflict,
      tailoringSelections: ['suggestion-a'],
      tailoringAvailableExportFormats: planWithConflict.available_export_formats,
    })

    const checkboxes = screen.getAllByRole('checkbox')
    expect(checkboxes[0]).toBeChecked()
    expect(checkboxes[1]).not.toBeChecked()

    fireEvent.click(checkboxes[1])

    expect(checkboxes[1]).toBeChecked()
    expect(checkboxes[0]).not.toBeChecked()
    expect(screen.getByText('1 of 2 selected')).toBeInTheDocument()
  })
})

describe('TailoredResumePage: preview-first workflow (Preview Changes then Apply Now)', () => {
  function renderWithPlan(overrides: Partial<PersistedResumeSession> = {}) {
    return renderPageWithRealSession({
      tailoringPlan: fixtureGenerateSuggestionsResponse,
      tailoringSelections: ['suggestion-0', 'suggestion-1'],
      tailoringAvailableExportFormats: fixtureGenerateSuggestionsResponse.available_export_formats,
      ...overrides,
    })
  }

  // "Preview Changes" and "Apply Now" call the exact same backend endpoint
  // (POST .../apply is a pure, stateless computation -- see
  // TailoredResumePage's `attemptApply` docstring) -- only what the
  // frontend does with a successful result differs, so opening the
  // preview never requires a second, different mock.
  async function openPreview() {
    fireEvent.click(screen.getByRole('button', { name: /preview changes/i }))
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /apply now/i })).toBeInTheDocument(),
    )
  }

  it('is disabled when no suggestions are selected', () => {
    renderWithPlan({ tailoringSelections: [] })

    expect(screen.getByRole('button', { name: /preview changes/i })).toBeDisabled()
  })

  it('does not apply anything just from selecting suggestions -- Preview Changes only previews', async () => {
    mockedTailoringApi.applyTailoringSuggestions.mockResolvedValue(fixtureApplySuggestionsResponse)

    renderWithPlan()

    expect(mockedTailoringApi.applyTailoringSuggestions).not.toHaveBeenCalled()
    expect(screen.queryByText(/final resume preview/i)).not.toBeInTheDocument()
  })

  it('sends only the selected suggestion ids, not unselected ones, when previewing', async () => {
    mockedTailoringApi.applyTailoringSuggestions.mockResolvedValue(fixtureApplySuggestionsResponse)

    renderWithPlan()
    // Deselect the second suggestion.
    fireEvent.click(screen.getAllByRole('checkbox')[1])
    fireEvent.click(screen.getByRole('button', { name: /preview changes/i }))

    await waitFor(() =>
      expect(mockedTailoringApi.applyTailoringSuggestions).toHaveBeenCalledWith(
        fixtureGenerateSuggestionsResponse.plan_id,
        ['suggestion-0'],
        {},
      ),
    )
  })

  it('shows a read-only preview panel first, without committing anything', async () => {
    mockedTailoringApi.applyTailoringSuggestions.mockResolvedValue(fixtureApplySuggestionsResponse)

    renderWithPlan()
    await openPreview()

    expect(screen.getByRole('heading', { name: /preview changes/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /back to suggestions/i })).toBeInTheDocument()
    // Nothing is committed yet -- no "Final Resume Preview" (the
    // post-commit card) and no change to what's persisted as applied.
    expect(screen.queryByText(/final resume preview/i)).not.toBeInTheDocument()
  })

  it('returns to the review stage without losing the selection when going back from preview', async () => {
    mockedTailoringApi.applyTailoringSuggestions.mockResolvedValue(fixtureApplySuggestionsResponse)

    renderWithPlan()
    await openPreview()
    fireEvent.click(screen.getByRole('button', { name: /back to suggestions/i }))

    expect(screen.getByText('2 of 2 selected')).toBeInTheDocument()
    expect(screen.getAllByRole('checkbox').every((checkbox) => (checkbox as HTMLInputElement).checked)).toBe(true)
  })

  it('shows the final resume preview and applied-changes summary only after Apply Now is confirmed', async () => {
    mockedTailoringApi.applyTailoringSuggestions.mockResolvedValue(fixtureApplySuggestionsResponse)

    renderWithPlan()
    await openPreview()
    fireEvent.click(screen.getByRole('button', { name: /apply now/i }))

    await waitFor(() => expect(screen.getByText(/final resume preview/i)).toBeInTheDocument())
    expect(
      screen.getByText(
        (_, el) => el?.tagName === 'PRE' && el.textContent === fixtureApplySuggestionsResponse.final_resume_text,
      ),
    ).toBeInTheDocument()
    expect(screen.getByText(/applied changes \(1\)/i)).toBeInTheDocument()
    expect(screen.getByText(/not included \(1\)/i)).toBeInTheDocument()
    // Apply Now commits and returns to the review stage.
    expect(screen.queryByRole('button', { name: /apply now/i })).not.toBeInTheDocument()
  })

  it('marks an applied suggestion as "Applied", greys it out, and locks its checkbox', async () => {
    mockedTailoringApi.applyTailoringSuggestions.mockResolvedValue(fixtureApplySuggestionsResponse)

    renderWithPlan()
    await openPreview()
    fireEvent.click(screen.getByRole('button', { name: /apply now/i }))

    await waitFor(() => expect(screen.getAllByText('Applied').length).toBeGreaterThan(0))
    const appliedCheckbox = screen.getByRole('checkbox', {
      name: /accept suggestion: add typescript/i,
    })
    expect(appliedCheckbox).toBeDisabled()
    expect(appliedCheckbox).toBeChecked()
  })

  it('lets the user undo an applied suggestion, reverting it to a normal pending selection', async () => {
    mockedTailoringApi.applyTailoringSuggestions.mockResolvedValue(fixtureApplySuggestionsResponse)

    renderWithPlan()
    await openPreview()
    fireEvent.click(screen.getByRole('button', { name: /apply now/i }))
    await waitFor(() => expect(screen.getAllByText('Applied').length).toBeGreaterThan(0))

    fireEvent.click(screen.getByRole('button', { name: /^undo$/i }))

    expect(screen.queryByText('Applied')).not.toBeInTheDocument()
    const revertedCheckbox = screen.getByRole('checkbox', {
      name: /accept suggestion: add typescript/i,
    })
    expect(revertedCheckbox).not.toBeDisabled()
    expect(revertedCheckbox).not.toBeChecked()
  })

  it('shows an actionable inline error for a revalidation failure (422) without losing selections', async () => {
    mockedTailoringApi.applyTailoringSuggestions.mockRejectedValue(
      new ApiError("Edited text for suggestion 'suggestion-0' failed validation: Contains Kubernetes.", {
        cause: 'revalidation_failed',
      }),
    )

    renderWithPlan()
    fireEvent.click(screen.getByRole('button', { name: /preview changes/i }))

    await waitFor(() => expect(screen.getByText(/contains kubernetes/i)).toBeInTheDocument())
    expect(screen.getByText('2 of 2 selected')).toBeInTheDocument()
    // The failure happened before any preview could be shown.
    expect(screen.queryByRole('button', { name: /apply now/i })).not.toBeInTheDocument()
  })

  it('preserves the last successful final resume after a later preview failure', async () => {
    // One resolved call for "Preview Changes", one more for "Apply Now".
    mockedTailoringApi.applyTailoringSuggestions
      .mockResolvedValueOnce(fixtureApplySuggestionsResponse)
      .mockResolvedValueOnce(fixtureApplySuggestionsResponse)

    renderWithPlan()
    await openPreview()
    fireEvent.click(screen.getByRole('button', { name: /apply now/i }))
    await waitFor(() =>
      expect(screen.getByText((_, el) => el?.tagName === 'PRE' && el.textContent === fixtureApplySuggestionsResponse.final_resume_text)).toBeInTheDocument(),
    )

    mockedTailoringApi.applyTailoringSuggestions.mockRejectedValueOnce(
      new ApiError('Something went wrong applying changes.'),
    )
    fireEvent.click(screen.getByRole('button', { name: /preview changes/i }))

    await waitFor(() =>
      expect(screen.getByText(/something went wrong applying changes/i)).toBeInTheDocument(),
    )
    // The previously successful final resume must still be visible.
    expect(screen.getByText((_, el) => el?.tagName === 'PRE' && el.textContent === fixtureApplySuggestionsResponse.final_resume_text)).toBeInTheDocument()
  })
})

describe('TailoredResumePage: stale-plan recovery (backend restart / 404)', () => {
  // A regenerated plan: different plan_id and different suggestion_ids
  // (matching real `TailoringSuggestionWorkflow` behavior -- ids are
  // assigned by position within one generation call, never stable across
  // two calls), but the same target_item_id/operation for the append
  // suggestion, so semantic matching (not exact-id matching) is what
  // restores it.
  const regeneratedPlan = {
    ...fixtureGenerateSuggestionsResponse,
    plan_id: 'plan-456-after-restart',
    suggestions: [
      { ...fixtureSuggestionAppend, suggestion_id: 'suggestion-70' },
      { ...fixtureSuggestionInsert, suggestion_id: 'suggestion-71' },
    ],
  }

  function renderWithPlan(overrides: Partial<PersistedResumeSession> = {}) {
    return renderPageWithRealSession({
      tailoringPlan: fixtureGenerateSuggestionsResponse,
      tailoringSelections: ['suggestion-0', 'suggestion-1'],
      tailoringAvailableExportFormats: fixtureGenerateSuggestionsResponse.available_export_formats,
      ...overrides,
    })
  }

  function mockStalePlan404() {
    mockedTailoringApi.applyTailoringSuggestions.mockRejectedValueOnce(
      new ApiError('Tailoring suggestion plan not found.', { cause: 'not_found' }),
    )
  }

  it('does not show the raw backend error when the plan is stale', async () => {
    mockStalePlan404()
    mockedCareerConversationApi.getCareerConversation.mockResolvedValue(fixtureCompletedSession)
    mockedTailoringApi.generateTailoringSuggestions.mockResolvedValue(regeneratedPlan)
    mockedTailoringApi.applyTailoringSuggestions.mockResolvedValueOnce(fixtureApplySuggestionsResponse)

    renderWithPlan()
    fireEvent.click(screen.getByRole('button', { name: /preview changes/i }))

    await waitFor(() =>
      expect(screen.getByRole('button', { name: /apply now/i })).toBeInTheDocument(),
    )
    expect(screen.queryByText(/tailoring suggestion plan not found/i)).not.toBeInTheDocument()
  })

  it('shows a non-blocking "Refreshing tailoring suggestions…" status, not a red error, while recovering', async () => {
    mockStalePlan404()
    mockedCareerConversationApi.getCareerConversation.mockResolvedValue(fixtureCompletedSession)
    // Held open so the "recovering" state is observable before it resolves.
    let resolveGenerate: (value: typeof regeneratedPlan) => void = () => {}
    mockedTailoringApi.generateTailoringSuggestions.mockReturnValue(
      new Promise((resolve) => {
        resolveGenerate = resolve
      }),
    )

    renderWithPlan()
    fireEvent.click(screen.getByRole('button', { name: /preview changes/i }))

    await waitFor(() =>
      expect(screen.getByText(/refreshing tailoring suggestions/i)).toBeInTheDocument(),
    )
    expect(screen.queryByText(/tailoring suggestion plan not found/i)).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /regenerate suggestions/i })).not.toBeInTheDocument()

    mockedTailoringApi.applyTailoringSuggestions.mockResolvedValueOnce(fixtureApplySuggestionsResponse)
    resolveGenerate(regeneratedPlan)

    await waitFor(() =>
      expect(screen.queryByText(/refreshing tailoring suggestions/i)).not.toBeInTheDocument(),
    )
  })

  it('regenerates automatically, using the resume/JD/conversation/custom instructions already in session', async () => {
    mockStalePlan404()
    mockedCareerConversationApi.getCareerConversation.mockResolvedValue(fixtureCompletedSession)
    mockedTailoringApi.generateTailoringSuggestions.mockResolvedValue(regeneratedPlan)
    mockedTailoringApi.applyTailoringSuggestions.mockResolvedValueOnce(fixtureApplySuggestionsResponse)

    renderWithPlan({ tailoringCustomInstructions: 'Keep it under two pages.' })
    fireEvent.click(screen.getByRole('button', { name: /preview changes/i }))

    await waitFor(() =>
      expect(mockedTailoringApi.generateTailoringSuggestions).toHaveBeenCalledWith(
        fixtureResume.text,
        fixtureJobDescription.text,
        fixtureResumeAnalysis,
        fixtureCompletedSession,
        'Keep it under two pages.',
        fixtureResume.fileName,
      ),
    )
  })

  it('restores selections by semantic match and retries the same request automatically with the new plan id', async () => {
    mockStalePlan404()
    mockedCareerConversationApi.getCareerConversation.mockResolvedValue(fixtureCompletedSession)
    mockedTailoringApi.generateTailoringSuggestions.mockResolvedValue(regeneratedPlan)
    mockedTailoringApi.applyTailoringSuggestions.mockResolvedValueOnce(fixtureApplySuggestionsResponse)

    // Only suggestion-0 (append) selected beforehand.
    renderWithPlan({ tailoringSelections: ['suggestion-0'] })
    fireEvent.click(screen.getByRole('button', { name: /preview changes/i }))

    await waitFor(() =>
      expect(mockedTailoringApi.applyTailoringSuggestions).toHaveBeenLastCalledWith(
        regeneratedPlan.plan_id,
        ['suggestion-70'],
        {},
      ),
    )
    // The user never had to click Preview a second time.
    expect(mockedTailoringApi.applyTailoringSuggestions).toHaveBeenCalledTimes(2)
  })

  it('restores edited suggestion text onto the matched new suggestion id', async () => {
    mockStalePlan404()
    mockedCareerConversationApi.getCareerConversation.mockResolvedValue(fixtureCompletedSession)
    mockedTailoringApi.generateTailoringSuggestions.mockResolvedValue(regeneratedPlan)
    mockedTailoringApi.applyTailoringSuggestions.mockResolvedValueOnce(fixtureApplySuggestionsResponse)

    renderWithPlan({
      tailoringSelections: ['suggestion-0'],
      tailoringEditedTexts: { 'suggestion-0': 'Python, TypeScript, and Node.js' },
    })
    fireEvent.click(screen.getByRole('button', { name: /preview changes/i }))

    await waitFor(() =>
      expect(mockedTailoringApi.applyTailoringSuggestions).toHaveBeenLastCalledWith(
        regeneratedPlan.plan_id,
        ['suggestion-70'],
        { 'suggestion-70': 'Python, TypeScript, and Node.js' },
      ),
    )
  })

  it('shows the preview panel after a successful automatic retry, with no second click', async () => {
    mockStalePlan404()
    mockedCareerConversationApi.getCareerConversation.mockResolvedValue(fixtureCompletedSession)
    mockedTailoringApi.generateTailoringSuggestions.mockResolvedValue(regeneratedPlan)
    mockedTailoringApi.applyTailoringSuggestions.mockResolvedValueOnce(fixtureApplySuggestionsResponse)

    renderWithPlan()
    fireEvent.click(screen.getByRole('button', { name: /preview changes/i }))

    await waitFor(() =>
      expect(screen.getByRole('button', { name: /apply now/i })).toBeInTheDocument(),
    )
  })

  it('shows a friendly recovery message, not the raw backend error, when regeneration itself fails', async () => {
    mockStalePlan404()
    mockedCareerConversationApi.getCareerConversation.mockResolvedValue(fixtureCompletedSession)
    mockedTailoringApi.generateTailoringSuggestions.mockRejectedValue(
      new ApiError('Could not reach the tailoring service. Is the backend running?'),
    )

    renderWithPlan()
    fireEvent.click(screen.getByRole('button', { name: /preview changes/i }))

    await waitFor(() =>
      expect(screen.getByText(/we need to regenerate your tailoring suggestions/i)).toBeInTheDocument(),
    )
    expect(screen.getByText(/your resume and conversation are safe/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /regenerate suggestions/i })).toBeInTheDocument()
    expect(screen.queryByText(/could not reach the tailoring service/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/tailoring suggestion plan not found/i)).not.toBeInTheDocument()
  })

  it('the Regenerate Suggestions button retries the whole recovery flow', async () => {
    mockStalePlan404()
    mockedCareerConversationApi.getCareerConversation.mockResolvedValue(fixtureCompletedSession)
    mockedTailoringApi.generateTailoringSuggestions.mockRejectedValueOnce(
      new ApiError('Network error.'),
    )

    renderWithPlan()
    fireEvent.click(screen.getByRole('button', { name: /preview changes/i }))
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /regenerate suggestions/i })).toBeInTheDocument(),
    )

    mockedTailoringApi.generateTailoringSuggestions.mockResolvedValueOnce(regeneratedPlan)
    mockedTailoringApi.applyTailoringSuggestions.mockResolvedValueOnce(fixtureApplySuggestionsResponse)
    fireEvent.click(screen.getByRole('button', { name: /regenerate suggestions/i }))

    await waitFor(() =>
      expect(screen.getByRole('button', { name: /apply now/i })).toBeInTheDocument(),
    )
  })

  it('does not attempt recovery for a non-404 apply failure', async () => {
    mockedTailoringApi.applyTailoringSuggestions.mockRejectedValueOnce(
      new ApiError('Something went wrong.'),
    )

    renderWithPlan()
    fireEvent.click(screen.getByRole('button', { name: /preview changes/i }))

    await waitFor(() => expect(screen.getByText(/something went wrong\./i)).toBeInTheDocument())
    expect(mockedTailoringApi.generateTailoringSuggestions).not.toHaveBeenCalled()
    expect(screen.queryByRole('button', { name: /regenerate suggestions/i })).not.toBeInTheDocument()
  })

  it('also recovers automatically when Apply Now itself hits a stale plan after a successful preview, ending in a committed final resume', async () => {
    mockedCareerConversationApi.getCareerConversation.mockResolvedValue(fixtureCompletedSession)
    mockedTailoringApi.generateTailoringSuggestions.mockResolvedValue(regeneratedPlan)
    // 1st call (Preview Changes) succeeds; 2nd call (Apply Now) discovers
    // the plan went stale in the meantime; 3rd call is the automatic
    // commit retry against the freshly regenerated plan.
    mockedTailoringApi.applyTailoringSuggestions
      .mockResolvedValueOnce(fixtureApplySuggestionsResponse)
      .mockRejectedValueOnce(new ApiError('Tailoring suggestion plan not found.', { cause: 'not_found' }))
      .mockResolvedValueOnce(fixtureApplySuggestionsResponse)

    renderWithPlan({ tailoringSelections: ['suggestion-0'] })
    fireEvent.click(screen.getByRole('button', { name: /preview changes/i }))
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /apply now/i })).toBeInTheDocument(),
    )
    fireEvent.click(screen.getByRole('button', { name: /apply now/i }))

    await waitFor(() => expect(screen.getByText(/final resume preview/i)).toBeInTheDocument())
    expect(mockedTailoringApi.applyTailoringSuggestions).toHaveBeenLastCalledWith(
      regeneratedPlan.plan_id,
      ['suggestion-70'],
      {},
    )
    expect(mockedTailoringApi.applyTailoringSuggestions).toHaveBeenCalledTimes(3)
    expect(screen.queryByText(/tailoring suggestion plan not found/i)).not.toBeInTheDocument()
  })
})

describe('TailoredResumePage: download options', () => {
  // Download only ever renders once a post-apply comparison exists for
  // the *current* final resume (see "TailoredResumePage: Post-Apply
  // Analysis Loop gates Download" below for the gating behavior itself)
  // -- seeded here too so these tests can focus purely on download
  // mechanics (formats/fidelity/export success/failure) without also
  // having to re-derive that precondition in every test.
  const fixturePostApplyComparison = {
    score_before: 72,
    score_after: 81,
    score_delta: 9,
    status: 'improved' as const,
    category_comparisons: [],
    strengths_gained: [],
    strengths_lost: [],
    weaknesses_resolved: [],
    weaknesses_remaining: [],
    new_weaknesses: [],
  }

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
      postApplyAnalysis: fixtureResumeAnalysis,
      postApplyComparison: fixturePostApplyComparison,
      ...overrides,
    })
  }

  it('does not show Download at all until a post-apply re-analysis has completed', () => {
    renderPageWithRealSession({
      tailoringPlan: fixtureGenerateSuggestionsResponse,
      tailoringSelections: ['suggestion-0'],
      tailoringAvailableExportFormats: fixtureGenerateSuggestionsResponse.available_export_formats,
      finalTailoredResume: {
        finalResumeText: fixtureApplySuggestionsResponse.final_resume_text,
        appliedSuggestionIds: fixtureApplySuggestionsResponse.applied_suggestion_ids,
      },
      tailoringValidationReport: fixtureApplySuggestionsResponse.final_validation,
      // No postApplyComparison seeded -- the applied resume is shown, but
      // nothing has been re-analyzed yet.
    })

    expect(screen.getByText(/final resume preview/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^download txt$/i })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /re-analyze & compare/i })).toBeInTheDocument()
  })

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

describe('TailoredResumePage: Post-Apply Analysis Loop', () => {
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

  it('does not call reanalyze on its own -- only from the explicit button', () => {
    renderApplied()
    expect(mockedPostApplyApi.reanalyzeAfterApply).not.toHaveBeenCalled()
  })

  it('shows the improved outcome honestly, with the score delta', async () => {
    mockedPostApplyApi.reanalyzeAfterApply.mockResolvedValue({
      after_analysis: fixtureResumeAnalysis,
      comparison: {
        score_before: 72,
        score_after: 81,
        score_delta: 9,
        status: 'improved',
        category_comparisons: [],
        strengths_gained: [],
        strengths_lost: [],
        weaknesses_resolved: [],
        weaknesses_remaining: [],
        new_weaknesses: [],
      },
    })
    renderApplied()

    fireEvent.click(screen.getByRole('button', { name: /re-analyze & compare/i }))

    await waitFor(() => expect(screen.getByText(/improved by 9 points/i)).toBeInTheDocument())
    expect(mockedPostApplyApi.reanalyzeAfterApply).toHaveBeenCalledWith(
      fixtureGenerateSuggestionsResponse.plan_id,
      fixtureResumeAnalysis,
      ['suggestion-0'],
      {},
    )
  })

  it('never presents an unchanged score as a success', async () => {
    mockedPostApplyApi.reanalyzeAfterApply.mockResolvedValue({
      after_analysis: fixtureResumeAnalysis,
      comparison: {
        score_before: 78,
        score_after: 78,
        score_delta: 0,
        status: 'unchanged',
        category_comparisons: [],
        strengths_gained: [],
        strengths_lost: [],
        weaknesses_resolved: [],
        weaknesses_remaining: [],
        new_weaknesses: [],
      },
    })
    renderApplied()

    fireEvent.click(screen.getByRole('button', { name: /re-analyze & compare/i }))

    await waitFor(() => expect(screen.getByText(/did not improve/i)).toBeInTheDocument())
  })

  it('never hides a decreased score, and reports a re-analysis failure without fabricating a comparison', async () => {
    mockedPostApplyApi.reanalyzeAfterApply.mockRejectedValue(
      new ApiError('Could not reach the re-analysis service.'),
    )
    renderApplied()

    fireEvent.click(screen.getByRole('button', { name: /re-analyze & compare/i }))

    await waitFor(() =>
      expect(screen.getByText(/re-analysis could not be completed/i)).toBeInTheDocument(),
    )
    // No fabricated comparison of any kind is shown.
    expect(screen.queryByText(/improved by/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/decreased by/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/did not improve/i)).not.toBeInTheDocument()
    // The applied resume itself is unaffected by the failure.
    expect(
      screen.getByText(
        (_, el) => el?.tagName === 'PRE' && el.textContent === fixtureApplySuggestionsResponse.final_resume_text,
      ),
    ).toBeInTheDocument()
  })

  it('a later successful re-analyze after a failure clears the failure message', async () => {
    mockedPostApplyApi.reanalyzeAfterApply.mockRejectedValueOnce(
      new ApiError('Could not reach the re-analysis service.'),
    )
    renderApplied()
    fireEvent.click(screen.getByRole('button', { name: /re-analyze & compare/i }))
    await waitFor(() =>
      expect(screen.getByText(/re-analysis could not be completed/i)).toBeInTheDocument(),
    )

    mockedPostApplyApi.reanalyzeAfterApply.mockResolvedValueOnce({
      after_analysis: fixtureResumeAnalysis,
      comparison: {
        score_before: 78,
        score_after: 74,
        score_delta: -4,
        status: 'decreased',
        category_comparisons: [],
        strengths_gained: [],
        strengths_lost: [],
        weaknesses_resolved: [],
        weaknesses_remaining: [],
        new_weaknesses: [],
      },
    })
    fireEvent.click(screen.getByRole('button', { name: /re-analyze & compare/i }))

    await waitFor(() => expect(screen.getByText(/decreased by 4 points/i)).toBeInTheDocument())
    expect(screen.queryByText(/re-analysis could not be completed/i)).not.toBeInTheDocument()
  })

  it('hides Download until re-analysis succeeds, then shows it once a comparison exists', async () => {
    mockedPostApplyApi.reanalyzeAfterApply.mockResolvedValue({
      after_analysis: fixtureResumeAnalysis,
      comparison: {
        score_before: 72,
        score_after: 81,
        score_delta: 9,
        status: 'improved',
        category_comparisons: [],
        strengths_gained: [],
        strengths_lost: [],
        weaknesses_resolved: [],
        weaknesses_remaining: [],
        new_weaknesses: [],
      },
    })
    renderApplied()

    expect(screen.queryByRole('button', { name: /^download txt$/i })).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /re-analyze & compare/i }))

    await waitFor(() => expect(screen.getByText(/improved by 9 points/i)).toBeInTheDocument())
    expect(screen.getByRole('button', { name: /^download txt$/i })).toBeInTheDocument()
  })

  it('keeps Download hidden after a failed re-analysis -- no comparison, no download', async () => {
    mockedPostApplyApi.reanalyzeAfterApply.mockRejectedValue(
      new ApiError('Could not reach the re-analysis service.'),
    )
    renderApplied()

    fireEvent.click(screen.getByRole('button', { name: /re-analyze & compare/i }))

    await waitFor(() =>
      expect(screen.getByText(/re-analysis could not be completed/i)).toBeInTheDocument(),
    )
    expect(screen.queryByRole('button', { name: /^download txt$/i })).not.toBeInTheDocument()
  })

  it('shows a meaningful progress indicator while re-analysis is running, not just a disabled button', async () => {
    let resolveReanalyze: (value: Awaited<ReturnType<typeof mockedPostApplyApi.reanalyzeAfterApply>>) => void =
      () => {}
    mockedPostApplyApi.reanalyzeAfterApply.mockReturnValue(
      new Promise((resolve) => {
        resolveReanalyze = resolve
      }),
    )
    renderApplied()

    fireEvent.click(screen.getByRole('button', { name: /re-analyze & compare/i }))

    await waitFor(() =>
      expect(screen.getByText(/re-analyzing your updated resume/i)).toBeInTheDocument(),
    )
    expect(screen.queryByRole('button', { name: /^download txt$/i })).not.toBeInTheDocument()

    resolveReanalyze({
      after_analysis: fixtureResumeAnalysis,
      comparison: {
        score_before: 72,
        score_after: 81,
        score_delta: 9,
        status: 'improved',
        category_comparisons: [],
        strengths_gained: [],
        strengths_lost: [],
        weaknesses_resolved: [],
        weaknesses_remaining: [],
        new_weaknesses: [],
      },
    })

    await waitFor(() => expect(screen.getByText(/improved by 9 points/i)).toBeInTheDocument())
    expect(screen.queryByText(/re-analyzing your updated resume/i)).not.toBeInTheDocument()
  })

  it('re-locks Download after a new apply, even if a prior re-analysis had unlocked it', async () => {
    mockedPostApplyApi.reanalyzeAfterApply.mockResolvedValue({
      after_analysis: fixtureResumeAnalysis,
      comparison: {
        score_before: 72,
        score_after: 81,
        score_delta: 9,
        status: 'improved',
        category_comparisons: [],
        strengths_gained: [],
        strengths_lost: [],
        weaknesses_resolved: [],
        weaknesses_remaining: [],
        new_weaknesses: [],
      },
    })
    renderApplied({
      finalTailoredResume: {
        finalResumeText: fixtureApplySuggestionsResponse.final_resume_text,
        appliedSuggestionIds: fixtureApplySuggestionsResponse.applied_suggestion_ids,
      },
      postApplyAnalysis: fixtureResumeAnalysis,
      postApplyComparison: {
        score_before: 72,
        score_after: 81,
        score_delta: 9,
        status: 'improved',
        category_comparisons: [],
        strengths_gained: [],
        strengths_lost: [],
        weaknesses_resolved: [],
        weaknesses_remaining: [],
        new_weaknesses: [],
      },
    })

    expect(screen.getByRole('button', { name: /^download txt$/i })).toBeInTheDocument()

    // Re-apply goes through the same preview-first path as the first
    // apply (see `attemptApply`'s docstring) -- "Preview Changes" then
    // "Apply Now" from within the preview panel, not a direct action from
    // the suggestions list.
    mockedTailoringApi.applyTailoringSuggestions.mockResolvedValue(fixtureApplySuggestionsResponse)
    fireEvent.click(screen.getByRole('button', { name: /preview changes/i }))
    await waitFor(() => expect(mockedTailoringApi.applyTailoringSuggestions).toHaveBeenCalled())
    const applyNowButton = await screen.findByRole('button', { name: /apply now/i })
    fireEvent.click(applyNowButton)

    await waitFor(() =>
      expect(mockedTailoringApi.applyTailoringSuggestions).toHaveBeenCalledTimes(2),
    )
    expect(screen.queryByRole('button', { name: /^download txt$/i })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /re-analyze & compare/i })).toBeInTheDocument()
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
      postApplyAnalysis: fixtureResumeAnalysis,
      postApplyComparison: {
        score_before: 72,
        score_after: 81,
        score_delta: 9,
        status: 'improved',
        category_comparisons: [],
        strengths_gained: [],
        strengths_lost: [],
        weaknesses_resolved: [],
        weaknesses_remaining: [],
        new_weaknesses: [],
      },
    })

    expect(screen.getByText((_, el) => el?.tagName === 'PRE' && el.textContent === fixtureApplySuggestionsResponse.final_resume_text)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^download txt$/i })).toBeInTheDocument()
    expect(mockedTailoringApi.generateTailoringSuggestions).not.toHaveBeenCalled()
    expect(mockedTailoringApi.applyTailoringSuggestions).not.toHaveBeenCalled()
  })
})
