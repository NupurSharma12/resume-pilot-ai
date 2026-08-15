import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { MemoryRouter, Route, Routes, Outlet } from 'react-router-dom'
import DashboardPage from './DashboardPage'
import * as api from '../lib/api'
import * as resumeSessionContext from '../session/ResumeSessionContext'
import { fixtureResume, fixtureJobDescription, fixtureResumeAnalysis } from '../testFixtures'
import type { DashboardOutletContext } from '../layouts/DashboardLayout'
import type { ResumeSessionContextValue } from '../session/ResumeSessionContext'
import type { ResumeAnalysisComparison } from '../data/postApplyTypes'

vi.mock('../lib/api')
vi.mock('../session/ResumeSessionContext', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../session/ResumeSessionContext')>()
  return { ...actual, useResumeSession: vi.fn() }
})

const mockedApi = vi.mocked(api)
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
    resumeAnalysis: null,
    setResumeAnalysis: vi.fn(),
    status: 'idle',
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
    resetForNewAnalysis: vi.fn(),
    rehydrateFromHistory: vi.fn(),
    clearSession: vi.fn(),
    ...overrides,
  }
}

function renderPage(outletContextOverrides: Partial<DashboardOutletContext> = {}) {
  const outletContext: DashboardOutletContext = {
    resumeAnalysis: null,
    setResumeAnalysis: vi.fn(),
    resume: fixtureResume,
    onResumeChange: vi.fn(),
    jobDescription: fixtureJobDescription,
    onJobDescriptionChange: vi.fn(),
    status: 'idle',
    setStatus: vi.fn(),
    errorMessage: '',
    setErrorMessage: vi.fn(),
    isInputCollapsed: false,
    setIsInputCollapsed: vi.fn(),
    ...outletContextOverrides,
  }

  function TestLayout() {
    return <Outlet context={outletContext} />
  }

  return render(
    <MemoryRouter initialEntries={['/']}>
      <Routes>
        <Route element={<TestLayout />}>
          <Route path="/" element={<DashboardPage />} />
        </Route>
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('DashboardPage handleAnalyze', () => {
  it('resets Career Conversation/tailoring/post-apply session state before recording the new analysis', async () => {
    const sessionValue = makeResumeSessionValue()
    mockedUseResumeSession.mockReturnValue(sessionValue)
    mockedApi.analyzeResume.mockResolvedValue({
      analysis: fixtureResumeAnalysis,
      jobPreparationId: 'new-job-prep',
    })

    renderPage()
    fireEvent.click(screen.getByRole('button', { name: /analyze resume/i }))

    await waitFor(() => expect(mockedApi.analyzeResume).toHaveBeenCalled())

    // The stale-session bug this guards against: a brand-new analysis
    // must clear whatever Career Conversation/tailoring/post-apply state
    // is still lingering from a *previous*, unrelated JobPreparation --
    // otherwise, e.g., the Sidebar's candidate score keeps showing an old
    // post-apply comparison instead of this fresh analysis's own score.
    expect(sessionValue.resetForNewAnalysis).toHaveBeenCalled()
    expect(sessionValue.setJobPreparationId).toHaveBeenCalledWith('new-job-prep')

    const resetOrder = vi.mocked(sessionValue.resetForNewAnalysis).mock.invocationCallOrder[0]
    const setJobPreparationIdOrder = vi.mocked(sessionValue.setJobPreparationId).mock
      .invocationCallOrder[0]
    expect(resetOrder).toBeLessThan(setJobPreparationIdOrder)
  })
})

describe('DashboardPage score consistency', () => {
  const fixtureOriginalAnalysis = {
    ...fixtureResumeAnalysis,
    overall_assessment: { ...fixtureResumeAnalysis.overall_assessment, overall_score: 92 },
  }

  const fixturePostApplyComparison: ResumeAnalysisComparison = {
    score_before: 92,
    score_after: 93,
    score_delta: 1,
    status: 'improved',
    category_comparisons: [],
    strengths_gained: [],
    strengths_lost: [],
    weaknesses_resolved: [],
    weaknesses_remaining: [],
    new_weaknesses: [],
  }

  it('shows the post-apply score (93), not the original analysis score (92), once a re-analysis exists', () => {
    mockedUseResumeSession.mockReturnValue(
      makeResumeSessionValue({ postApplyComparison: fixturePostApplyComparison }),
    )

    renderPage({ resumeAnalysis: fixtureOriginalAnalysis, status: 'success' })

    expect(screen.getByText('93%')).toBeInTheDocument()
    expect(screen.queryByText('92%')).not.toBeInTheDocument()
  })

  it('shows the original analysis score (92) before any re-analysis exists', () => {
    mockedUseResumeSession.mockReturnValue(makeResumeSessionValue({ postApplyComparison: null }))

    renderPage({ resumeAnalysis: fixtureOriginalAnalysis, status: 'success' })

    expect(screen.getByText('92%')).toBeInTheDocument()
    expect(screen.queryByText('93%')).not.toBeInTheDocument()
  })

  it("does not mutate resumeAnalysis itself -- it stays the immutable 'before' snapshot", () => {
    const sessionValue = makeResumeSessionValue({ postApplyComparison: fixturePostApplyComparison })
    mockedUseResumeSession.mockReturnValue(sessionValue)

    renderPage({ resumeAnalysis: fixtureOriginalAnalysis, status: 'success' })

    expect(screen.getByText('93%')).toBeInTheDocument()
    // The session's own resumeAnalysis object is never reassigned to
    // reflect the post-apply score -- only what CandidateHeroCard is
    // handed for *display* changes (see DashboardPage's
    // `displayedOverallAssessment`).
    expect(sessionValue.setResumeAnalysis).not.toHaveBeenCalled()
  })

  it('existing fresh-session behavior (no post-apply state at all) is unchanged', () => {
    mockedUseResumeSession.mockReturnValue(makeResumeSessionValue())

    renderPage({ resumeAnalysis: fixtureResumeAnalysis, status: 'success' })

    expect(
      screen.getByText(`${fixtureResumeAnalysis.overall_assessment.overall_score}%`),
    ).toBeInTheDocument()
  })
})
