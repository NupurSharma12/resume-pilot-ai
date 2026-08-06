import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import DashboardLayout from './DashboardLayout'
import * as resumeSessionContext from '../session/ResumeSessionContext'
import { fixtureResumeAnalysis } from '../testFixtures'
import type { ResumeSessionContextValue } from '../session/ResumeSessionContext'

vi.mock('../session/ResumeSessionContext', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../session/ResumeSessionContext')>()
  return { ...actual, useResumeSession: vi.fn() }
})

const mockedUseResumeSession = vi.mocked(resumeSessionContext.useResumeSession)

function makeResumeSessionValue(
  overrides: Partial<ResumeSessionContextValue> = {},
): ResumeSessionContextValue {
  return {
    hydrationStatus: 'hydrated',
    resume: null,
    setResume: vi.fn(),
    jobDescription: null,
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
    clearSession: vi.fn(),
    ...overrides,
  }
}

function renderLayout() {
  return render(
    <MemoryRouter initialEntries={['/']}>
      <Routes>
        <Route element={<DashboardLayout />}>
          <Route path="/" element={<div>Page content</div>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('DashboardLayout hydration gating', () => {
  it('shows a full-page loading state, not the Sidebar or the routed page, while hydration is pending', () => {
    mockedUseResumeSession.mockReturnValue(makeResumeSessionValue({ hydrationStatus: 'pending' }))

    renderLayout()

    expect(screen.getByText(/restoring your session/i)).toBeInTheDocument()
    expect(screen.queryByText('Page content')).not.toBeInTheDocument()
    expect(screen.queryByText('ResumePilotAI')).not.toBeInTheDocument()
  })

  it('renders the Sidebar and the routed page once hydration completes', () => {
    mockedUseResumeSession.mockReturnValue(makeResumeSessionValue({ hydrationStatus: 'hydrated' }))

    renderLayout()

    expect(screen.queryByText(/restoring your session/i)).not.toBeInTheDocument()
    expect(screen.getByText('ResumePilotAI')).toBeInTheDocument()
    expect(screen.getByText('Page content')).toBeInTheDocument()
  })

  it('passes the restored resumeAnalysis through to the Sidebar once hydrated', () => {
    mockedUseResumeSession.mockReturnValue(
      makeResumeSessionValue({
        hydrationStatus: 'hydrated',
        resumeAnalysis: fixtureResumeAnalysis,
      }),
    )

    renderLayout()

    // CandidateSummaryCard (which reads Sidebar's `resumeAnalysis` prop)
    // only renders once that prop is non-null -- proof the restored value
    // actually reached the Sidebar, not just the routed page.
    expect(
      screen.getByText(`${fixtureResumeAnalysis.overall_assessment.overall_score}%`),
    ).toBeInTheDocument()
  })

  it('does not render the CandidateSummaryCard when there is no resume analysis yet', () => {
    mockedUseResumeSession.mockReturnValue(
      makeResumeSessionValue({ hydrationStatus: 'hydrated', resumeAnalysis: null }),
    )

    renderLayout()

    expect(screen.queryByText('CURRENT CANDIDATE')).not.toBeInTheDocument()
  })
})
