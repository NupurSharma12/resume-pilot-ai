import { useCallback, useRef, useState } from 'react'
import { RotateCw, Wand2 } from 'lucide-react'
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
import type { DashboardOutletContext } from '../layouts/DashboardLayout'

// Deliberately just 'idle' | 'generating' | 'error' -- there is no 'ready'
// status here. Whether a result exists is read straight from
// `tailoredResumeResult` (shared, via ResumeSessionProvider), not
// duplicated into a second "do we have a result" flag on this page.
type TailoringApiStatus = 'idle' | 'generating' | 'error'

export default function TailoredResumePage() {
  const navigate = useNavigate()
  const { resumeAnalysis, resume, jobDescription } = useOutletContext<DashboardOutletContext>()
  const {
    hydrationStatus,
    activeCareerConversationSessionId,
    tailoredResumeResult,
    setTailoredResumeResult,
  } = useResumeSession()

  const [apiStatus, setApiStatus] = useState<TailoringApiStatus>('idle')
  const [errorMessage, setErrorMessage] = useState('')

  // A tailored resume can only be grounded in a completed analysis AND an
  // existing Career Conversation session (the backend's
  // `TailorResumeRequest.career_conversation` field is required) — this
  // route is only ever linked to from a CTA once both exist, but a
  // direct/refreshed visit could still land here with one or both
  // missing. Only meaningful once hydration has resolved — see the
  // hydration gate in the render below, matching CareerConversationPage's
  // identical reasoning.
  const hasContext = resumeAnalysis !== null && resume !== null && jobDescription !== null

  // Same "close the window a render can't close in time" reasoning as
  // CareerConversationPage's `isBusyRef` — see that component's docstring.
  // There is deliberately no "generate automatically on mount" effect
  // here at all (contrast CareerConversationPage's `hasInitializedRef`):
  // `generate` only ever runs from a user's own click on the "Generate"/
  // "Regenerate" button below, never as a side effect of navigating here
  // or of `tailoredResumeResult` being absent.
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
      // Shared, not local: this is the one place `tailoredResumeResult` is
      // ever set, so every CTA that reads it (TailoredResumeBanner,
      // ConversationCompleteCard, and this page's own render below) stays
      // in sync automatically.
      setTailoredResumeResult(tailored)
      setApiStatus('idle')
    } catch (err) {
      // A failed (re)generation deliberately never clears an existing
      // `tailoredResumeResult` -- see ResumeSessionContext's docstring on
      // why: losing the last good result to a failed retry would be
      // strictly worse than just showing the error with the old result
      // still one click away via "Try Again".
      setErrorMessage(
        err instanceof ApiError ? err.message : 'An unexpected error occurred. Please try again.',
      )
      setApiStatus('error')
    } finally {
      isBusyRef.current = false
    }
  }, [
    resume,
    jobDescription,
    resumeAnalysis,
    activeCareerConversationSessionId,
    setTailoredResumeResult,
  ])

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
        ) : tailoredResumeResult ? (
          <div className="mx-auto max-w-3xl space-y-6">
            <div className="flex justify-end">
              <Button variant="outline" icon={<RotateCw size={16} />} onClick={generate}>
                Regenerate
              </Button>
            </div>
            <TailoringPlanCard plan={tailoredResumeResult.tailoring_plan} />
            <TailoredResumeView tailoredResume={tailoredResumeResult.tailored_resume} />
            <ValidationReportCard report={tailoredResumeResult.validation_report} />
          </div>
        ) : (
          <div className="flex flex-col items-center gap-4 rounded-2xl border border-dashed border-gray-300 bg-white px-8 py-16 text-center">
            <p className="text-sm text-gray-500">
              Generate an evidence-based, tailored version of your resume for this job
              description.
            </p>
            <Button variant="solid" icon={<Wand2 size={16} />} onClick={generate}>
              Generate Tailored Resume
            </Button>
          </div>
        )}
      </div>
    </>
  )
}
