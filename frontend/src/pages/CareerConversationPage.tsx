import { useCallback, useEffect, useRef, useState } from 'react'
import { Send } from 'lucide-react'
import { useNavigate, useOutletContext } from 'react-router-dom'
import TopHeader from '../components/TopHeader'
import Button from '../components/Button'
import IndeterminateBar from '../components/IndeterminateBar'
import ConversationQuestionBubble from '../components/ConversationQuestionBubble'
import ConversationAnswerBubble from '../components/ConversationAnswerBubble'
import ConversationLoadingState from '../components/ConversationLoadingState'
import ConversationErrorState from '../components/ConversationErrorState'
import ConversationCompleteCard from '../components/ConversationCompleteCard'
import { startCareerConversation, submitCareerConversationAnswer } from '../lib/careerConversationApi'
import { ApiError } from '../lib/api'
import type { ConversationSessionState } from '../data/careerConversationTypes'
import type { DashboardOutletContext } from '../layouts/DashboardLayout'

type ConversationApiStatus = 'starting' | 'ready' | 'submitting' | 'error'
type FailedAction = 'start' | 'submit'

export default function CareerConversationPage() {
  const navigate = useNavigate()
  const { resumeAnalysis, resume, jobDescription } = useOutletContext<DashboardOutletContext>()

  const [session, setSession] = useState<ConversationSessionState | null>(null)
  const [apiStatus, setApiStatus] = useState<ConversationApiStatus>('starting')
  const [errorMessage, setErrorMessage] = useState('')
  const [failedAction, setFailedAction] = useState<FailedAction>('start')
  const [answer, setAnswer] = useState('')

  const activeSectionRef = useRef<HTMLDivElement>(null)

  // A conversation can only be grounded in a completed analysis — this
  // route is only ever linked to from the Dashboard's CTA once one
  // exists (see CareerConversationBanner), but a direct/refreshed visit
  // could still land here with nothing to ground it in.
  const hasContext = resumeAnalysis !== null && resume !== null && jobDescription !== null

  const startSession = useCallback(async () => {
    if (!resume || !jobDescription || !resumeAnalysis) return
    setApiStatus('starting')
    setErrorMessage('')
    try {
      const result = await startCareerConversation(resume.text, jobDescription.text, resumeAnalysis)
      setSession(result)
      setApiStatus('ready')
    } catch (err) {
      setFailedAction('start')
      setErrorMessage(
        err instanceof ApiError ? err.message : 'An unexpected error occurred. Please try again.',
      )
      setApiStatus('error')
    }
  }, [resume, jobDescription, resumeAnalysis])

  // Creates the session exactly once per page load. `hasStartedRef` (not
  // just an empty dependency array) is what makes this a genuine
  // one-shot: without it, React 18 StrictMode's dev-only double effect
  // invocation would fire a second POST /v1/career-conversation on
  // mount, creating two sessions for one page load (the same class of
  // bug fixed in the upload flow's remount handling — see
  // ResumeInput/JobDescriptionInput). `startSession` is memoized via
  // `useCallback` specifically so it can be listed here as an honest,
  // exhaustive-deps-clean dependency.
  const hasStartedRef = useRef(false)
  useEffect(() => {
    if (hasStartedRef.current) return
    hasStartedRef.current = true
    void startSession()
  }, [startSession])

  async function handleSubmitAnswer() {
    if (!session || !answer.trim()) return
    setApiStatus('submitting')
    setErrorMessage('')
    try {
      const result = await submitCareerConversationAnswer(session.session_id, answer.trim())
      setSession(result)
      setAnswer('')
      setApiStatus('ready')
    } catch (err) {
      setFailedAction('submit')
      setErrorMessage(
        err instanceof ApiError ? err.message : 'An unexpected error occurred. Please try again.',
      )
      setApiStatus('error')
    }
  }

  function handleRetry() {
    if (failedAction === 'start') {
      void startSession()
    } else {
      void handleSubmitAnswer()
    }
  }

  // Scrolls the active section (the open question, or the completion
  // card once there's no open question left) into view whenever it
  // changes — mirrors the Dashboard's "scroll the panel into view"
  // pattern (see DashboardPage).
  useEffect(() => {
    if (session?.current_question || session?.status === 'complete') {
      activeSectionRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
  }, [session?.current_question, session?.status])

  return (
    <>
      <TopHeader
        title="Career Conversation"
        subtitle="A recruiter-style conversation to recover missing evidence for this role"
      />

      <div className="p-8">
        {!hasContext ? (
          <div className="flex flex-col items-center gap-4 rounded-2xl border border-dashed border-gray-300 bg-white px-8 py-16 text-center">
            <p className="text-sm text-gray-500">
              Complete a resume analysis first to start a career conversation.
            </p>
            <Button variant="solid" onClick={() => navigate('/')}>
              Go to Dashboard
            </Button>
          </div>
        ) : (
          <div className="mx-auto max-w-3xl space-y-6">
            {session?.history.map((exchange, index) => (
              <div key={index} className="space-y-4">
                <ConversationQuestionBubble topic={exchange.topic} question={exchange.question} />
                <ConversationAnswerBubble answer={exchange.answer} />
              </div>
            ))}

            {apiStatus === 'starting' && (
              <ConversationLoadingState message="Preparing your first question…" />
            )}

            {apiStatus === 'error' && (
              <ConversationErrorState message={errorMessage} onRetry={handleRetry} />
            )}

            {apiStatus !== 'error' && session?.status === 'in_progress' && session.current_question && (
              <div ref={activeSectionRef} className="animate-panel-fade space-y-4">
                <ConversationQuestionBubble
                  topic={session.current_question.topic}
                  question={session.current_question.question}
                  evidenceGoal={session.current_question.evidence_goal}
                  estimatedImpact={session.current_question.estimated_impact}
                />

                <div className="overflow-hidden rounded-2xl border border-gray-200 bg-white">
                  {apiStatus === 'submitting' && <IndeterminateBar />}
                  <div className="p-4">
                    <textarea
                      value={answer}
                      onChange={(event) => setAnswer(event.target.value)}
                      placeholder="Share your answer…"
                      rows={4}
                      disabled={apiStatus === 'submitting'}
                      className="w-full resize-none rounded-xl border border-gray-200 bg-white p-4 text-sm text-gray-700 placeholder:text-gray-400 focus:border-indigo-400 focus:outline-none disabled:opacity-60"
                    />
                    <div className="mt-3 flex justify-end">
                      <Button
                        variant="solid"
                        icon={<Send size={16} />}
                        disabled={!answer.trim() || apiStatus === 'submitting'}
                        onClick={handleSubmitAnswer}
                      >
                        {apiStatus === 'submitting' ? 'Sending…' : 'Continue'}
                      </Button>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {session?.status === 'complete' && (
              <div ref={activeSectionRef}>
                <ConversationCompleteCard
                  stopReason={session.stop_reason}
                  questionsAnswered={session.history.length}
                />
              </div>
            )}
          </div>
        )}
      </div>
    </>
  )
}
