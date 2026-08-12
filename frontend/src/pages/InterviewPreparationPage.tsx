import { useEffect, useState } from 'react'
import { AlertTriangle, RotateCw, Sparkles } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import TopHeader from '../components/TopHeader'
import Button from '../components/Button'
import ConversationLoadingState from '../components/ConversationLoadingState'
import InterviewPreparationCard from '../components/InterviewPreparationCard'
import {
  generateInterviewPreparation,
  getJobPreparation,
} from '../lib/jobPreparationHistoryApi'
import { ApiError } from '../lib/api'
import { useResumeSession } from '../session/ResumeSessionContext'
import type { InterviewPreparation } from '../data/jobPreparationHistoryTypes'

type DetailStatus = 'loading' | 'success' | 'error'
type GenerationStatus = 'idle' | 'generating' | 'error'

// The active-preparation counterpart to History's own Interview
// Preparation section (see HistoryPage.tsx) -- same persisted guide, same
// shared `InterviewPreparationCard`, but scoped to *this* session's
// current `jobPreparationId` rather than a chosen-from-a-list past
// preparation, and reachable as soon as Resume Analysis completes (see
// Sidebar.tsx's gating), without requiring Career Conversation or
// Tailoring to exist yet. Loads via the existing `GET
// /v1/job-preparations/{id}` and generates/enriches via the existing
// `POST .../interview-preparation` -- no new backend endpoint.
export default function InterviewPreparationPage() {
  const navigate = useNavigate()
  const { hydrationStatus, jobPreparationId } = useResumeSession()

  const [interviewPreparation, setInterviewPreparation] = useState<InterviewPreparation | null>(
    null,
  )
  const [detailStatus, setDetailStatus] = useState<DetailStatus>('loading')
  const [detailError, setDetailError] = useState('')

  const [generationStatus, setGenerationStatus] = useState<GenerationStatus>('idle')
  const [generationError, setGenerationError] = useState('')

  async function loadPersisted(id: string) {
    setDetailStatus('loading')
    setDetailError('')
    try {
      const result = await getJobPreparation(id)
      setInterviewPreparation(result.interview_preparation)
      setDetailStatus('success')
    } catch (err) {
      setDetailError(err instanceof ApiError ? err.message : 'An unexpected error occurred.')
      setDetailStatus('error')
    }
  }

  useEffect(() => {
    // Guarded on `hydrationStatus`, not just `jobPreparationId` -- before
    // hydration resolves, `jobPreparationId` is whatever
    // `ResumeSessionProvider` initializes it to, not yet the real
    // restored value (see DashboardLayout's identical reasoning for why
    // every page gates on this).
    if (hydrationStatus === 'hydrated' && jobPreparationId) {
      void loadPersisted(jobPreparationId)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hydrationStatus, jobPreparationId])

  async function handleGenerate() {
    if (!jobPreparationId) return
    setGenerationStatus('generating')
    setGenerationError('')
    try {
      const result = await generateInterviewPreparation(jobPreparationId)
      setInterviewPreparation(result)
      setGenerationStatus('idle')
    } catch (err) {
      setGenerationError(err instanceof ApiError ? err.message : 'An unexpected error occurred.')
      setGenerationStatus('error')
    }
  }

  const generateButtonLabel =
    generationStatus === 'generating'
      ? 'Generating…'
      : generationStatus === 'error'
        ? 'Try Again'
        : interviewPreparation
          ? 'Update Interview Preparation'
          : 'Generate Interview Preparation'

  return (
    <>
      <TopHeader
        title="Interview Preparation"
        subtitle="System design, coding, and behavioral questions to prepare for -- grounded in your resume, job description, and Career Conversation"
      />

      <div className="p-8">
        {hydrationStatus !== 'hydrated' ? (
          <ConversationLoadingState message="Restoring your session…" />
        ) : !jobPreparationId ? (
          <div className="flex flex-col items-center gap-4 rounded-2xl border border-dashed border-gray-300 bg-white px-8 py-16 text-center">
            <p className="text-sm text-gray-500">
              Complete a resume analysis first to generate an interview preparation guide.
            </p>
            <Button variant="solid" onClick={() => navigate('/')}>
              Go to Dashboard
            </Button>
          </div>
        ) : (
          <div className="mx-auto max-w-3xl space-y-6">
            {detailStatus === 'loading' && (
              <div className="rounded-2xl border border-gray-200 bg-white p-10 text-center text-sm text-gray-500">
                Loading…
              </div>
            )}

            {detailStatus === 'error' && (
              <div className="flex flex-col items-center gap-4 rounded-2xl border border-gray-200 bg-white px-8 py-16 text-center">
                <div className="flex h-12 w-12 items-center justify-center rounded-full bg-rose-50 text-rose-500">
                  <AlertTriangle size={22} />
                </div>
                <p className="text-sm text-gray-500">{detailError}</p>
                <Button
                  variant="outline"
                  icon={<RotateCw size={16} />}
                  onClick={() => loadPersisted(jobPreparationId)}
                >
                  Try Again
                </Button>
              </div>
            )}

            {detailStatus === 'success' && (
              <>
                {interviewPreparation && (
                  <InterviewPreparationCard interviewPreparation={interviewPreparation} />
                )}

                {!interviewPreparation && (
                  <div className="rounded-2xl border border-dashed border-gray-300 bg-white p-6 text-center">
                    <p className="text-sm text-gray-500">No interview preparation guide yet.</p>
                  </div>
                )}

                {generationStatus === 'error' && (
                  <p className="text-center text-sm text-rose-500">{generationError}</p>
                )}

                <div className="flex justify-center">
                  <Button
                    variant="solid"
                    icon={<Sparkles size={16} />}
                    disabled={generationStatus === 'generating'}
                    onClick={handleGenerate}
                  >
                    {generateButtonLabel}
                  </Button>
                </div>
              </>
            )}
          </div>
        )}
      </div>
    </>
  )
}
