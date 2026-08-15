import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import InterviewPreparationPage from './InterviewPreparationPage'
import * as jobPreparationHistoryApi from '../lib/jobPreparationHistoryApi'
import * as resumeSessionContext from '../session/ResumeSessionContext'
import { ApiError } from '../lib/api'
import type { ResumeSessionContextValue } from '../session/ResumeSessionContext'
import type {
  InterviewPreparation,
  JobPreparationDetail,
} from '../data/jobPreparationHistoryTypes'

vi.mock('../lib/jobPreparationHistoryApi')
vi.mock('../session/ResumeSessionContext', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../session/ResumeSessionContext')>()
  return { ...actual, useResumeSession: vi.fn() }
})

const mockedApi = vi.mocked(jobPreparationHistoryApi)
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
    postApplyAnalysis: null,
    setPostApplyAnalysis: vi.fn(),
    postApplyComparison: null,
    setPostApplyComparison: vi.fn(),
    postApplyAnalysisStatus: 'idle',
    setPostApplyAnalysisStatus: vi.fn(),
    jobPreparationId: 'job-prep-1',
    setJobPreparationId: vi.fn(),
    resetForNewAnalysis: vi.fn(),
    rehydrateFromHistory: vi.fn(),
    clearSession: vi.fn(),
    ...overrides,
  }
}

const fixtureInterviewPreparation: InterviewPreparation = {
  system_design_questions: [
    {
      question: 'Design a distributed document-analysis pipeline.',
      rationale: 'The resume shows large-scale backend systems experience.',
    },
  ],
  coding_questions: [
    {
      title: 'Merge Intervals',
      topic: 'Sorting',
      difficulty: 'medium',
      relevance: 'The role involves scheduling logic.',
    },
  ],
  behavioral_questions: [],
  generated_at: '2026-08-13T10:00:00Z',
  stage: 'initial',
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
  checkpoints: {
    initial_analysis_completed_at: '2026-08-01T09:00:00Z',
    career_conversation_completed_at: null,
    tailoring_plan_completed_at: null,
    applied_at: null,
    post_apply_analysis_completed_at: null,
  },
  analysis_result: null,
  career_conversation: null,
  tailoring_plan: null,
  applied_resume_text: null,
  post_apply_analysis: null,
  interview_preparation: null,
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/interview-preparation']}>
      <Routes>
        <Route path="/interview-preparation" element={<InterviewPreparationPage />} />
        <Route path="/" element={<div>Dashboard Page</div>} />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('InterviewPreparationPage hydration/context gating', () => {
  it('shows a rehydrating state while hydration is pending', () => {
    mockedUseResumeSession.mockReturnValue(makeResumeSessionValue({ hydrationStatus: 'pending' }))

    renderPage()

    expect(screen.getByText(/restoring your session/i)).toBeInTheDocument()
    expect(mockedApi.getJobPreparation).not.toHaveBeenCalled()
  })

  it('shows a "complete an analysis" empty state once hydrated with no jobPreparationId', () => {
    mockedUseResumeSession.mockReturnValue(makeResumeSessionValue({ jobPreparationId: null }))

    renderPage()

    expect(screen.getByText(/complete a resume analysis first/i)).toBeInTheDocument()
    expect(mockedApi.getJobPreparation).not.toHaveBeenCalled()
  })

  it('navigates to the dashboard from the empty state', () => {
    mockedUseResumeSession.mockReturnValue(makeResumeSessionValue({ jobPreparationId: null }))

    renderPage()
    fireEvent.click(screen.getByRole('button', { name: /go to dashboard/i }))

    expect(screen.getByText('Dashboard Page')).toBeInTheDocument()
  })
})

describe('InterviewPreparationPage loading persisted state', () => {
  it('loads the persisted guide via GET /v1/job-preparations/{id} on mount', async () => {
    mockedUseResumeSession.mockReturnValue(makeResumeSessionValue())
    mockedApi.getJobPreparation.mockResolvedValue({
      ...fixtureDetail,
      interview_preparation: fixtureInterviewPreparation,
    })

    renderPage()

    await waitFor(() => expect(mockedApi.getJobPreparation).toHaveBeenCalledWith('job-prep-1'))
    expect(
      screen.getByText('Design a distributed document-analysis pipeline.'),
    ).toBeInTheDocument()
    expect(screen.getByText('Initial preparation')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Update Interview Preparation' })).toBeInTheDocument()
  })

  it('shows an empty state with a generate action when no guide has been persisted yet', async () => {
    mockedUseResumeSession.mockReturnValue(makeResumeSessionValue())
    mockedApi.getJobPreparation.mockResolvedValue(fixtureDetail)

    renderPage()

    await waitFor(() => expect(screen.getByText(/no interview preparation guide yet/i)).toBeInTheDocument())
    expect(screen.getByRole('button', { name: 'Generate Interview Preparation' })).toBeInTheDocument()
  })

  it('shows a retryable error state when loading fails', async () => {
    mockedUseResumeSession.mockReturnValue(makeResumeSessionValue())
    mockedApi.getJobPreparation.mockRejectedValue(new ApiError('Could not reach the history service.'))

    renderPage()

    await waitFor(() =>
      expect(screen.getByText('Could not reach the history service.')).toBeInTheDocument(),
    )

    mockedApi.getJobPreparation.mockResolvedValue(fixtureDetail)
    fireEvent.click(screen.getByRole('button', { name: /try again/i }))

    await waitFor(() => expect(screen.getByText(/no interview preparation guide yet/i)).toBeInTheDocument())
  })
})

describe('InterviewPreparationPage generation', () => {
  it('generates a guide and renders it once the call resolves', async () => {
    mockedUseResumeSession.mockReturnValue(makeResumeSessionValue())
    mockedApi.getJobPreparation.mockResolvedValue(fixtureDetail)
    let resolveGeneration: (value: InterviewPreparation) => void = () => {}
    mockedApi.generateInterviewPreparation.mockReturnValue(
      new Promise((resolve) => {
        resolveGeneration = resolve
      }),
    )

    renderPage()
    await waitFor(() => expect(screen.getByText(/no interview preparation guide yet/i)).toBeInTheDocument())

    fireEvent.click(screen.getByRole('button', { name: 'Generate Interview Preparation' }))

    await waitFor(() => expect(screen.getByRole('button', { name: /generating/i })).toBeDisabled())
    expect(mockedApi.generateInterviewPreparation).toHaveBeenCalledWith('job-prep-1')

    resolveGeneration(fixtureInterviewPreparation)

    await waitFor(() =>
      expect(
        screen.getByText('Design a distributed document-analysis pipeline.'),
      ).toBeInTheDocument(),
    )
  })

  it('shows a retryable error state when generation fails, and preserves the retry as the same action', async () => {
    mockedUseResumeSession.mockReturnValue(makeResumeSessionValue())
    mockedApi.getJobPreparation.mockResolvedValue(fixtureDetail)
    mockedApi.generateInterviewPreparation.mockRejectedValue(
      new ApiError('Generating interview preparation failed.'),
    )

    renderPage()
    await waitFor(() => expect(screen.getByText(/no interview preparation guide yet/i)).toBeInTheDocument())

    fireEvent.click(screen.getByRole('button', { name: 'Generate Interview Preparation' }))

    await waitFor(() =>
      expect(screen.getByText('Generating interview preparation failed.')).toBeInTheDocument(),
    )
    const retryButton = screen.getByRole('button', { name: 'Try Again' })

    mockedApi.generateInterviewPreparation.mockResolvedValue(fixtureInterviewPreparation)
    fireEvent.click(retryButton)

    await waitFor(() =>
      expect(
        screen.getByText('Design a distributed document-analysis pipeline.'),
      ).toBeInTheDocument(),
    )
  })

  it('shows an "Update" action and re-renders the guide once a preparation already exists', async () => {
    mockedUseResumeSession.mockReturnValue(makeResumeSessionValue())
    mockedApi.getJobPreparation.mockResolvedValue({
      ...fixtureDetail,
      interview_preparation: fixtureInterviewPreparation,
    })
    const enriched: InterviewPreparation = {
      ...fixtureInterviewPreparation,
      stage: 'career_conversation_enriched',
    }
    mockedApi.generateInterviewPreparation.mockResolvedValue(enriched)

    renderPage()
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Update Interview Preparation' })).toBeInTheDocument(),
    )

    fireEvent.click(screen.getByRole('button', { name: 'Update Interview Preparation' }))

    await waitFor(() => expect(screen.getByText('Updated from Career Conversation')).toBeInTheDocument())
  })
})
