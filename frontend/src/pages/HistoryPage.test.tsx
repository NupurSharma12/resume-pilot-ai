import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import HistoryPage from './HistoryPage'
import * as jobPreparationHistoryApi from '../lib/jobPreparationHistoryApi'
import * as resumeSessionContext from '../session/ResumeSessionContext'
import { ApiError } from '../lib/api'
import type {
  CheckpointStatus,
  InterviewPreparation,
  JobPreparationDetail,
  JobPreparationSummary,
} from '../data/jobPreparationHistoryTypes'

vi.mock('../lib/jobPreparationHistoryApi')
vi.mock('../session/ResumeSessionContext', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../session/ResumeSessionContext')>()
  return { ...actual, useResumeSession: vi.fn() }
})

const mockNavigate = vi.fn()
vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>()
  return { ...actual, useNavigate: () => mockNavigate }
})

const mockedApi = vi.mocked(jobPreparationHistoryApi)
const mockedUseResumeSession = vi.mocked(resumeSessionContext.useResumeSession)
const rehydrateFromHistory = vi.fn()

function renderPage() {
  mockedUseResumeSession.mockReturnValue({
    rehydrateFromHistory,
  } as unknown as resumeSessionContext.ResumeSessionContextValue)
  return render(
    <MemoryRouter>
      <HistoryPage />
    </MemoryRouter>,
  )
}

const fixtureCheckpointsAllComplete: CheckpointStatus = {
  initial_analysis_completed_at: '2026-08-01T10:00:00Z',
  career_conversation_completed_at: '2026-08-01T10:05:00Z',
  tailoring_plan_completed_at: '2026-08-01T10:10:00Z',
  applied_at: '2026-08-01T10:15:00Z',
  post_apply_analysis_completed_at: '2026-08-01T10:20:00Z',
}

const fixtureCheckpointsPartial: CheckpointStatus = {
  initial_analysis_completed_at: '2026-08-01T10:00:00Z',
  career_conversation_completed_at: '2026-08-01T10:05:00Z',
  tailoring_plan_completed_at: null,
  applied_at: null,
  post_apply_analysis_completed_at: null,
}

const fixtureSummary: JobPreparationSummary = {
  id: 'job-prep-1',
  job_title: 'Senior Engineer',
  company: 'Adobe',
  resume_name: 'Senior Engineer Resume',
  created_at: '2026-08-01T09:00:00Z',
  updated_at: '2026-08-12T09:00:00Z',
  checkpoints: fixtureCheckpointsAllComplete,
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
  checkpoints: fixtureCheckpointsAllComplete,
  analysis_result: {
    overall_assessment: { overall_score: 72, summary: 'Solid backend fit.' },
  },
  career_conversation: { history: [{ topic: 'Leadership' }], stop_reason: 'Enough evidence.' },
  tailoring_plan: {
    generated_plan: { suggestions: [{ suggestion_id: 's-1' }] },
    selection: { selected_suggestion_ids: ['s-1'] },
  },
  applied_resume_text: 'SUMMARY\nTailored resume text.',
  post_apply_analysis: {
    analysis: { overall_assessment: { overall_score: 85 } },
    comparison: { score_before: 72, score_after: 85, status: 'improved' },
  },
  interview_preparation: null,
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
  behavioral_questions: [
    {
      question: 'Describe a time you led a migration.',
      source: 'career_conversation',
      context: 'I led a 4-engineer migration off a legacy monolith.',
    },
    {
      question: 'Tell me about a recent challenge.',
      source: 'suggested',
      context: null,
    },
  ],
  generated_at: '2026-08-12T10:00:00Z',
  stage: 'career_conversation_enriched',
}

describe('HistoryPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('shows an empty state when there is no history yet', async () => {
    mockedApi.listJobPreparations.mockResolvedValue([])

    renderPage()

    await waitFor(() =>
      expect(screen.getByText(/analysis history is coming soon/i)).toBeInTheDocument(),
    )
  })

  it('renders each preparation with resume/job/company, last updated, and checkpoints', async () => {
    mockedApi.listJobPreparations.mockResolvedValue([fixtureSummary])

    renderPage()

    await waitFor(() => expect(screen.getByText('Senior Engineer')).toBeInTheDocument())
    expect(screen.getByText(/Senior Engineer Resume/)).toBeInTheDocument()
    expect(screen.getByText(/Adobe/)).toBeInTheDocument()
    expect(screen.getByText(/Last updated/)).toBeInTheDocument()
    // All five checkpoints, per the agreed checkpoint model.
    expect(screen.getByText('Initial Analysis')).toBeInTheDocument()
    expect(screen.getByText('Career Conversation')).toBeInTheDocument()
    expect(screen.getByText('Tailoring Plan')).toBeInTheDocument()
    expect(screen.getByText('Tailored Resume')).toBeInTheDocument()
    expect(screen.getByText('Re-analysis')).toBeInTheDocument()
  })

  it('shows a partially complete preparation honestly -- incomplete checkpoints are never marked done', async () => {
    mockedApi.listJobPreparations.mockResolvedValue([
      { ...fixtureSummary, checkpoints: fixtureCheckpointsPartial },
    ])

    renderPage()

    await waitFor(() => expect(screen.getByText('Senior Engineer')).toBeInTheDocument())
    // Complete checkpoints render with the "complete" text styling;
    // incomplete ones never do -- exactly two of the five here (Initial
    // Analysis, Career Conversation) per fixtureCheckpointsPartial.
    const completeItems = screen.getAllByText(
      /^(Initial Analysis|Career Conversation|Tailoring Plan|Tailored Resume|Re-analysis)$/,
    )
    const completeLabels = completeItems
      .filter((el) => el.className.includes('text-gray-900'))
      .map((el) => el.textContent)
    const incompleteLabels = completeItems
      .filter((el) => el.className.includes('text-gray-400'))
      .map((el) => el.textContent)
    expect(completeLabels.sort()).toEqual(['Career Conversation', 'Initial Analysis'])
    expect(incompleteLabels.sort()).toEqual([
      'Re-analysis',
      'Tailored Resume',
      'Tailoring Plan',
    ])
  })

  it('shows a retryable error state when the list fails to load', async () => {
    mockedApi.listJobPreparations.mockRejectedValue(new ApiError('Could not reach the history service.'))

    renderPage()

    await waitFor(() =>
      expect(screen.getByText('Could not reach the history service.')).toBeInTheDocument(),
    )

    mockedApi.listJobPreparations.mockResolvedValue([fixtureSummary])
    fireEvent.click(screen.getByRole('button', { name: /try again/i }))

    await waitFor(() => expect(screen.getByText('Senior Engineer')).toBeInTheDocument())
  })

  it('opens a preparation and renders its persisted checkpoint data', async () => {
    mockedApi.listJobPreparations.mockResolvedValue([fixtureSummary])
    mockedApi.getJobPreparation.mockResolvedValue(fixtureDetail)

    renderPage()
    await waitFor(() => expect(screen.getByText('Senior Engineer')).toBeInTheDocument())

    fireEvent.click(screen.getByRole('button', { name: 'View Preparation' }))

    await waitFor(() => expect(mockedApi.getJobPreparation).toHaveBeenCalledWith('job-prep-1'))
    // Initial Analysis
    await waitFor(() => expect(screen.getByText('72%')).toBeInTheDocument())
    expect(screen.getByText('Solid backend fit.')).toBeInTheDocument()
    // Career Conversation
    expect(screen.getByText('1 exchange recorded.')).toBeInTheDocument()
    expect(screen.getByText('Enough evidence.')).toBeInTheDocument()
    // Tailoring Plan
    expect(screen.getByText('1 suggestion generated, 1 selected.')).toBeInTheDocument()
    // Tailored Resume
    expect(screen.getByText(/Tailored resume text\./)).toBeInTheDocument()
    // Re-analysis -- scoped to its own card, since "72%" also appears
    // in the Initial Analysis section above.
    const reanalysisHeading = screen.getByText('Re-analysis', { selector: 'h3' })
    const reanalysisCard = reanalysisHeading.closest('div') as HTMLElement
    expect(within(reanalysisCard).getByText(/72%/)).toBeInTheDocument()
    expect(within(reanalysisCard).getByText(/85%/)).toBeInTheDocument()
    expect(within(reanalysisCard).getByText(/improved/)).toBeInTheDocument()
  })

  it('never claims a checkpoint is complete for a section with no persisted payload', async () => {
    mockedApi.listJobPreparations.mockResolvedValue([fixtureSummary])
    mockedApi.getJobPreparation.mockResolvedValue({
      ...fixtureDetail,
      checkpoints: fixtureCheckpointsPartial,
      tailoring_plan: null,
      applied_resume_text: null,
      post_apply_analysis: null,
    })

    renderPage()
    await waitFor(() => expect(screen.getByText('Senior Engineer')).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: 'View Preparation' }))

    await waitFor(() => expect(screen.getByText('72%')).toBeInTheDocument())
    expect(screen.queryByText('Tailoring Plan', { selector: 'h3' })).not.toBeInTheDocument()
    expect(screen.queryByText('Tailored Resume', { selector: 'h3' })).not.toBeInTheDocument()
    expect(screen.queryByText('Re-analysis', { selector: 'h3' })).not.toBeInTheDocument()
  })

  it('shows a retryable error state when opening a preparation fails, and can go back to the list', async () => {
    mockedApi.listJobPreparations.mockResolvedValue([fixtureSummary])
    mockedApi.getJobPreparation.mockRejectedValue(
      new ApiError('This job preparation no longer exists.', { cause: 'not_found' }),
    )

    renderPage()
    await waitFor(() => expect(screen.getByText('Senior Engineer')).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: 'View Preparation' }))

    await waitFor(() =>
      expect(screen.getByText('This job preparation no longer exists.')).toBeInTheDocument(),
    )

    fireEvent.click(screen.getByRole('button', { name: /back to history/i }))

    await waitFor(() => expect(screen.getByText('Senior Engineer')).toBeInTheDocument())
    expect(
      screen.queryByText('This job preparation no longer exists.'),
    ).not.toBeInTheDocument()
  })

  it('shows an empty state with a generate action when no interview preparation exists yet', async () => {
    mockedApi.listJobPreparations.mockResolvedValue([fixtureSummary])
    mockedApi.getJobPreparation.mockResolvedValue(fixtureDetail)

    renderPage()
    await waitFor(() => expect(screen.getByText('Senior Engineer')).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: 'View Preparation' }))

    await waitFor(() => expect(screen.getByText('72%')).toBeInTheDocument())
    expect(screen.getByText(/no interview preparation guide yet/i)).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: 'Generate Interview Preparation' }),
    ).toBeInTheDocument()
  })

  it('renders system design, coding, and behavioral questions once a guide is persisted', async () => {
    mockedApi.listJobPreparations.mockResolvedValue([fixtureSummary])
    mockedApi.getJobPreparation.mockResolvedValue({
      ...fixtureDetail,
      interview_preparation: fixtureInterviewPreparation,
    })

    renderPage()
    await waitFor(() => expect(screen.getByText('Senior Engineer')).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: 'View Preparation' }))

    await waitFor(() =>
      expect(
        screen.getByText('Design a distributed document-analysis pipeline.'),
      ).toBeInTheDocument(),
    )
    expect(screen.getByText('Merge Intervals')).toBeInTheDocument()
    expect(screen.getByText('Describe a time you led a migration.')).toBeInTheDocument()
    expect(screen.getByText('Tell me about a recent challenge.')).toBeInTheDocument()
    expect(screen.getByText('From Career Conversation')).toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: 'Generate Interview Preparation' }),
    ).not.toBeInTheDocument()
  })

  it('generates an interview preparation guide and renders it once the call resolves', async () => {
    mockedApi.listJobPreparations.mockResolvedValue([fixtureSummary])
    mockedApi.getJobPreparation.mockResolvedValue(fixtureDetail)
    let resolveGeneration: (value: InterviewPreparation) => void = () => {}
    mockedApi.generateInterviewPreparation.mockReturnValue(
      new Promise((resolve) => {
        resolveGeneration = resolve
      }),
    )

    renderPage()
    await waitFor(() => expect(screen.getByText('Senior Engineer')).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: 'View Preparation' }))
    await waitFor(() => expect(screen.getByText('72%')).toBeInTheDocument())

    fireEvent.click(screen.getByRole('button', { name: 'Generate Interview Preparation' }))

    await waitFor(() => expect(screen.getByRole('button', { name: /generating/i })).toBeDisabled())
    expect(mockedApi.generateInterviewPreparation).toHaveBeenCalledWith('job-prep-1')

    resolveGeneration(fixtureInterviewPreparation)

    await waitFor(() =>
      expect(
        screen.getByText('Design a distributed document-analysis pipeline.'),
      ).toBeInTheDocument(),
    )
    expect(
      screen.queryByRole('button', { name: /generate interview preparation|generating/i }),
    ).not.toBeInTheDocument()
  })

  it('shows a retryable error state when generation fails', async () => {
    mockedApi.listJobPreparations.mockResolvedValue([fixtureSummary])
    mockedApi.getJobPreparation.mockResolvedValue(fixtureDetail)
    mockedApi.generateInterviewPreparation.mockRejectedValue(
      new ApiError('Generating interview preparation failed.'),
    )

    renderPage()
    await waitFor(() => expect(screen.getByText('Senior Engineer')).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: 'View Preparation' }))
    await waitFor(() => expect(screen.getByText('72%')).toBeInTheDocument())

    fireEvent.click(screen.getByRole('button', { name: 'Generate Interview Preparation' }))

    await waitFor(() =>
      expect(screen.getByText('Generating interview preparation failed.')).toBeInTheDocument(),
    )
    const retryButton = screen.getByRole('button', { name: 'Try Again' })
    expect(retryButton).toBeInTheDocument()

    mockedApi.generateInterviewPreparation.mockResolvedValue(fixtureInterviewPreparation)
    fireEvent.click(retryButton)

    await waitFor(() =>
      expect(
        screen.getByText('Design a distributed document-analysis pipeline.'),
      ).toBeInTheDocument(),
    )
  })

  it('requests only the 10 most recent preparations', async () => {
    mockedApi.listJobPreparations.mockResolvedValue([fixtureSummary])

    renderPage()

    await waitFor(() => expect(mockedApi.listJobPreparations).toHaveBeenCalledWith({ limit: 10 }))
  })

  it('filters the list client-side by job title, company, or resume name', async () => {
    const other: JobPreparationSummary = {
      ...fixtureSummary,
      id: 'job-prep-2',
      job_title: 'Product Manager',
      company: 'Initech',
      resume_name: 'PM Resume',
    }
    mockedApi.listJobPreparations.mockResolvedValue([fixtureSummary, other])

    renderPage()
    await waitFor(() => expect(screen.getByText('Senior Engineer')).toBeInTheDocument())
    expect(screen.getByText('Product Manager')).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText(/search job preparations/i), {
      target: { value: 'initech' },
    })

    await waitFor(() => expect(screen.queryByText('Senior Engineer')).not.toBeInTheDocument())
    expect(screen.getByText('Product Manager')).toBeInTheDocument()
  })

  it('shows a no-match state when the search query matches nothing', async () => {
    mockedApi.listJobPreparations.mockResolvedValue([fixtureSummary])

    renderPage()
    await waitFor(() => expect(screen.getByText('Senior Engineer')).toBeInTheDocument())

    fireEvent.change(screen.getByLabelText(/search job preparations/i), {
      target: { value: 'nonexistent role' },
    })

    await waitFor(() =>
      expect(screen.getByText(/no preparations match/i)).toBeInTheDocument(),
    )
  })

  it('shows both Continue and View for an unfinished preparation', async () => {
    mockedApi.listJobPreparations.mockResolvedValue([
      { ...fixtureSummary, checkpoints: fixtureCheckpointsPartial },
    ])

    renderPage()

    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Continue Preparation' })).toBeInTheDocument(),
    )
    expect(screen.getByRole('button', { name: 'View Preparation' })).toBeInTheDocument()
  })

  it('shows View only (no Continue) for a fully completed preparation', async () => {
    mockedApi.listJobPreparations.mockResolvedValue([fixtureSummary])

    renderPage()

    await waitFor(() => expect(screen.getByText('Senior Engineer')).toBeInTheDocument())
    expect(screen.getByRole('button', { name: 'View Preparation' })).toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: 'Continue Preparation' }),
    ).not.toBeInTheDocument()
  })

  it('opens a confirmation dialog showing completed checkpoints when Continue is clicked', async () => {
    mockedApi.listJobPreparations.mockResolvedValue([
      { ...fixtureSummary, checkpoints: fixtureCheckpointsPartial },
    ])

    renderPage()
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Continue Preparation' })).toBeInTheDocument(),
    )
    fireEvent.click(screen.getByRole('button', { name: 'Continue Preparation' }))

    expect(screen.getByText('Continue this preparation?')).toBeInTheDocument()
    const dialog = screen.getByRole('dialog')
    expect(within(dialog).getByText('Initial Analysis')).toBeInTheDocument()
    expect(within(dialog).getByText('Career Conversation')).toBeInTheDocument()
    expect(mockedApi.getJobPreparation).not.toHaveBeenCalled()
  })

  it('cancelling the confirmation dialog does not rehydrate or navigate', async () => {
    mockedApi.listJobPreparations.mockResolvedValue([
      { ...fixtureSummary, checkpoints: fixtureCheckpointsPartial },
    ])

    renderPage()
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Continue Preparation' })).toBeInTheDocument(),
    )
    fireEvent.click(screen.getByRole('button', { name: 'Continue Preparation' }))
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))

    expect(screen.queryByText('Continue this preparation?')).not.toBeInTheDocument()
    expect(rehydrateFromHistory).not.toHaveBeenCalled()
    expect(mockNavigate).not.toHaveBeenCalled()
  })

  it('confirming Continue fetches the full detail, rehydrates the session, and navigates to the next stage', async () => {
    mockedApi.listJobPreparations.mockResolvedValue([
      { ...fixtureSummary, checkpoints: fixtureCheckpointsPartial },
    ])
    mockedApi.getJobPreparation.mockResolvedValue({
      ...fixtureDetail,
      checkpoints: fixtureCheckpointsPartial,
    })
    rehydrateFromHistory.mockReturnValue({ ok: true, nextRoute: '/tailored-resume' })

    renderPage()
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Continue Preparation' })).toBeInTheDocument(),
    )
    fireEvent.click(screen.getByRole('button', { name: 'Continue Preparation' }))
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }))

    await waitFor(() => expect(mockedApi.getJobPreparation).toHaveBeenCalledWith('job-prep-1'))
    await waitFor(() =>
      expect(rehydrateFromHistory).toHaveBeenCalledWith({
        ...fixtureDetail,
        checkpoints: fixtureCheckpointsPartial,
      }),
    )
    expect(mockNavigate).toHaveBeenCalledWith('/tailored-resume')
    expect(screen.queryByText('Continue this preparation?')).not.toBeInTheDocument()
  })

  it('shows a retryable error in the dialog when fetching the detail fails, without closing it', async () => {
    mockedApi.listJobPreparations.mockResolvedValue([
      { ...fixtureSummary, checkpoints: fixtureCheckpointsPartial },
    ])
    mockedApi.getJobPreparation.mockRejectedValue(
      new ApiError('This job preparation no longer exists.', { cause: 'not_found' }),
    )

    renderPage()
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Continue Preparation' })).toBeInTheDocument(),
    )
    fireEvent.click(screen.getByRole('button', { name: 'Continue Preparation' }))
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }))

    await waitFor(() =>
      expect(screen.getByText('This job preparation no longer exists.')).toBeInTheDocument(),
    )
    expect(screen.getByText('Continue this preparation?')).toBeInTheDocument()
    expect(rehydrateFromHistory).not.toHaveBeenCalled()
    expect(mockNavigate).not.toHaveBeenCalled()
  })

  it('shows a graceful error in the dialog when rehydration itself reports invalid persisted data, without navigating', async () => {
    mockedApi.listJobPreparations.mockResolvedValue([
      { ...fixtureSummary, checkpoints: fixtureCheckpointsPartial },
    ])
    mockedApi.getJobPreparation.mockResolvedValue({
      ...fixtureDetail,
      checkpoints: fixtureCheckpointsPartial,
    })
    rehydrateFromHistory.mockReturnValue({
      ok: false,
      error: "This preparation's saved analysis can't be restored.",
    })

    renderPage()
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Continue Preparation' })).toBeInTheDocument(),
    )
    fireEvent.click(screen.getByRole('button', { name: 'Continue Preparation' }))
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }))

    await waitFor(() =>
      expect(
        screen.getByText("This preparation's saved analysis can't be restored."),
      ).toBeInTheDocument(),
    )
    expect(screen.getByText('Continue this preparation?')).toBeInTheDocument()
    expect(mockNavigate).not.toHaveBeenCalled()
  })

  it('Delete opens a confirmation dialog', async () => {
    mockedApi.listJobPreparations.mockResolvedValue([fixtureSummary])

    renderPage()
    await waitFor(() => expect(screen.getByText('Senior Engineer')).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: 'Delete' }))

    expect(screen.getByText('Delete this preparation?')).toBeInTheDocument()
    expect(screen.getByText('This will remove it from your History.')).toBeInTheDocument()
    expect(mockedApi.deleteJobPreparation).not.toHaveBeenCalled()
  })

  it('Cancel does not delete', async () => {
    mockedApi.listJobPreparations.mockResolvedValue([fixtureSummary])

    renderPage()
    await waitFor(() => expect(screen.getByText('Senior Engineer')).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: 'Delete' }))
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))

    expect(screen.queryByText('Delete this preparation?')).not.toBeInTheDocument()
    expect(mockedApi.deleteJobPreparation).not.toHaveBeenCalled()
    // Still in the list -- nothing was removed.
    expect(screen.getByText('Senior Engineer')).toBeInTheDocument()
  })

  it('Confirm soft-deletes and the preparation disappears from History without a reload', async () => {
    mockedApi.listJobPreparations.mockResolvedValue([fixtureSummary])
    mockedApi.deleteJobPreparation.mockResolvedValue(undefined)

    renderPage()
    await waitFor(() => expect(screen.getByText('Senior Engineer')).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: 'Delete' }))
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Delete' }))

    await waitFor(() => expect(mockedApi.deleteJobPreparation).toHaveBeenCalledWith('job-prep-1'))
    await waitFor(() =>
      expect(screen.queryByText('Delete this preparation?')).not.toBeInTheDocument(),
    )
    expect(screen.queryByText('Senior Engineer')).not.toBeInTheDocument()
    // No second fetch of the list -- removed client-side from the
    // already-loaded items, per the design review's "no full reload".
    expect(mockedApi.listJobPreparations).toHaveBeenCalledTimes(1)
  })

  it('deleting an already-deleted/nonexistent preparation is handled cleanly (treated as success)', async () => {
    mockedApi.listJobPreparations.mockResolvedValue([fixtureSummary])
    mockedApi.deleteJobPreparation.mockRejectedValue(
      new ApiError('This job preparation no longer exists.', { cause: 'not_found' }),
    )

    renderPage()
    await waitFor(() => expect(screen.getByText('Senior Engineer')).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: 'Delete' }))
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Delete' }))

    await waitFor(() =>
      expect(screen.queryByText('Delete this preparation?')).not.toBeInTheDocument(),
    )
    expect(screen.queryByText('Senior Engineer')).not.toBeInTheDocument()
  })

  it('shows an inline error in the dialog when delete fails for another reason, without closing it', async () => {
    mockedApi.listJobPreparations.mockResolvedValue([fixtureSummary])
    mockedApi.deleteJobPreparation.mockRejectedValue(
      new ApiError('Could not reach the history service. Is the backend running?'),
    )

    renderPage()
    await waitFor(() => expect(screen.getByText('Senior Engineer')).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: 'Delete' }))
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Delete' }))

    await waitFor(() =>
      expect(
        screen.getByText('Could not reach the history service. Is the backend running?'),
      ).toBeInTheDocument(),
    )
    expect(screen.getByText('Delete this preparation?')).toBeInTheDocument()
    // Still in the list -- the failed delete never removed it.
    expect(screen.getByText('Senior Engineer')).toBeInTheDocument()
  })
})
