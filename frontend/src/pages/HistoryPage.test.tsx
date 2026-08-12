import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent, within } from '@testing-library/react'
import HistoryPage from './HistoryPage'
import * as jobPreparationHistoryApi from '../lib/jobPreparationHistoryApi'
import { ApiError } from '../lib/api'
import type {
  CheckpointStatus,
  InterviewPreparation,
  JobPreparationDetail,
  JobPreparationSummary,
} from '../data/jobPreparationHistoryTypes'

vi.mock('../lib/jobPreparationHistoryApi')

const mockedApi = vi.mocked(jobPreparationHistoryApi)

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

    render(<HistoryPage />)

    await waitFor(() =>
      expect(screen.getByText(/analysis history is coming soon/i)).toBeInTheDocument(),
    )
  })

  it('renders each preparation with resume/job/company, last updated, and checkpoints', async () => {
    mockedApi.listJobPreparations.mockResolvedValue([fixtureSummary])

    render(<HistoryPage />)

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

    render(<HistoryPage />)

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

    render(<HistoryPage />)

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

    render(<HistoryPage />)
    await waitFor(() => expect(screen.getByText('Senior Engineer')).toBeInTheDocument())

    fireEvent.click(screen.getByText('Senior Engineer'))

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

    render(<HistoryPage />)
    await waitFor(() => expect(screen.getByText('Senior Engineer')).toBeInTheDocument())
    fireEvent.click(screen.getByText('Senior Engineer'))

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

    render(<HistoryPage />)
    await waitFor(() => expect(screen.getByText('Senior Engineer')).toBeInTheDocument())
    fireEvent.click(screen.getByText('Senior Engineer'))

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

    render(<HistoryPage />)
    await waitFor(() => expect(screen.getByText('Senior Engineer')).toBeInTheDocument())
    fireEvent.click(screen.getByText('Senior Engineer'))

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

    render(<HistoryPage />)
    await waitFor(() => expect(screen.getByText('Senior Engineer')).toBeInTheDocument())
    fireEvent.click(screen.getByText('Senior Engineer'))

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

    render(<HistoryPage />)
    await waitFor(() => expect(screen.getByText('Senior Engineer')).toBeInTheDocument())
    fireEvent.click(screen.getByText('Senior Engineer'))
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

    render(<HistoryPage />)
    await waitFor(() => expect(screen.getByText('Senior Engineer')).toBeInTheDocument())
    fireEvent.click(screen.getByText('Senior Engineer'))
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
})
