import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate, useOutletContext } from 'react-router-dom'
import TopHeader from '../components/TopHeader'
import Button from '../components/Button'
import ConversationLoadingState from '../components/ConversationLoadingState'
import TailoringErrorState from '../components/TailoringErrorState'
import TailoringPlanCard from '../components/TailoringPlanCard'
import TailoredResumeView from '../components/TailoredResumeView'
import ValidationReportCard from '../components/ValidationReportCard'
import { getCareerConversation } from '../lib/careerConversationApi'
import { tailorResume } from '../lib/tailorResumeApi'
import { ApiError } from '../lib/api'
import { useResumeSession } from '../session/ResumeSessionContext'
import type { TailorResumeResult } from '../data/tailoringTypes'
import type { DashboardOutletContext } from '../layouts/DashboardLayout'

type TailoringApiStatus = 'generating' | 'ready' | 'error'

export default function TailoredResumePage() {
  const navigate = useNavigate()
  const { resumeAnalysis, resume, jobDescription } = useOutletContext<DashboardOutletContext>()
  const { hydrationStatus, activeCareerConversationSessionId } = useResumeSession()

  const [result, setResult] = useState<TailorResumeResult | null>(null)
  const [apiStatus, setApiStatus] = useState<TailoringApiStatus>('generating')
  const [errorMessage, setErrorMessage] = useState('')

  // A tailored resume can only be grounded in a completed analysis AND an
  // existing Career Conversation session (the backend's
  // `TailorResumeRequest.career_conversation` field is required) — this
  // route is only ever linked to from `ConversationCompleteCard`'s CTA
  // once both exist, but a direct/refreshed visit could still land here
  // with one or both missing. Only meaningful once hydration has
  // resolved — see the hydration gate in the render below, matching
  // CareerConversationPage's identical reasoning.
  const hasContext = resumeAnalysis !== null && resume !== null && jobDescription !== null

  // Same "close the window a render can't close in time" reasoning as
  // CareerConversationPage's `isBusyRef` — see that component's docstring.
  const isBusyRef = useRef(false)

  const generate = useCallback(async () => {
    if (!resume || !jobDescription || !resumeAnalysis || !activeCareerConversationSessionId) return
    if (isBusyRef.current) return
    isBusyRef.current = true
    setApiStatus('generating')
    setErrorMessage('')
    try {
      // The full Career Conversation transcript isn't held anywhere in
      // shared state (only its session id is, via `activeCareerConversation
      // SessionId`) — CareerConversationPage keeps its own session state
      // locally, so it's re-fetched here via the same pure-read GET this
      // app already uses for reload-safety (see CareerConversationPage).
      const session = await getCareerConversation(activeCareerConversationSessionId)
      const tailored = await tailorResume(resume.text, jobDescription.text, resumeAnalysis, session)
      setResult(tailored)
      setApiStatus('ready')
    } catch (err) {
      setErrorMessage(
        err instanceof ApiError ? err.message : 'An unexpected error occurred. Please try again.',
      )
      setApiStatus('error')
    } finally {
      isBusyRef.current = false
    }
  }, [resume, jobDescription, resumeAnalysis, activeCareerConversationSessionId])

  // Generates exactly once per page load, and only once hydration has
  // resolved and both prerequisites are present -- `hasGeneratedRef` (not
  // just an empty dependency array) is what makes this a genuine
  // one-shot under React 18 StrictMode's dev-only double effect
  // invocation, matching CareerConversationPage's `hasInitializedRef`
  // pattern exactly.
  const hasGeneratedRef = useRef(false)
  useEffect(() => {
    if (hydrationStatus !== 'hydrated') return
    if (!hasContext || !activeCareerConversationSessionId) return
    if (hasGeneratedRef.current) return
    hasGeneratedRef.current = true
    void generate()
  }, [hydrationStatus, hasContext, activeCareerConversationSessionId, generate])

  return (
    <>
      <TopHeader
        title="Tailored Resume"
        subtitle="An evidence-based rewrite of your resume for this specific role"
      />

      <div className="p-8">
        {hydrationStatus !== 'hydrated' ? (
          <ConversationLoadingState message="Restoring your session…" />
        ) : !hasContext ? (
          <div className="flex flex-col items-center gap-4 rounded-2xl border border-dashed border-gray-300 bg-white px-8 py-16 text-center">
            <p className="text-sm text-gray-500">
              Complete a resume analysis first to generate a tailored resume.
            </p>
            <Button variant="solid" onClick={() => navigate('/')}>
              Go to Dashboard
            </Button>
          </div>
        ) : !activeCareerConversationSessionId ? (
          <div className="flex flex-col items-center gap-4 rounded-2xl border border-dashed border-gray-300 bg-white px-8 py-16 text-center">
            <p className="text-sm text-gray-500">
              Start a Career Conversation first — the Tailoring Engine only rewrites your resume
              using evidence recovered there, alongside your existing analysis.
            </p>
            <Button variant="solid" onClick={() => navigate('/career-conversation')}>
              Start Career Conversation
            </Button>
          </div>
        ) : apiStatus === 'generating' ? (
          <ConversationLoadingState message="Generating your tailored resume…" />
        ) : apiStatus === 'error' ? (
          <TailoringErrorState message={errorMessage} onRetry={generate} />
        ) : (
          result && (
            <div className="mx-auto max-w-3xl space-y-6">
              <TailoringPlanCard plan={result.tailoring_plan} />
              <TailoredResumeView tailoredResume={result.tailored_resume} />
              <ValidationReportCard report={result.validation_report} />
            </div>
          )
        )}
      </div>
    </>
  )
}
