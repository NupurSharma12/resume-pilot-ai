import { useCallback, useEffect, useRef, useState } from 'react'
import { Send } from 'lucide-react'
import { useNavigate, useOutletContext } from 'react-router-dom'
import TopHeader from '../components/TopHeader'
import Button from '../components/Button'
import IndeterminateBar from '../components/IndeterminateBar'
import ConversationQuestionBubble from '../components/ConversationQuestionBubble'
import ConversationAssistantReplyBubble from '../components/ConversationAssistantReplyBubble'
import ConversationAnswerBubble from '../components/ConversationAnswerBubble'
import ConversationLoadingState from '../components/ConversationLoadingState'
import ConversationErrorState from '../components/ConversationErrorState'
import ConversationCompleteCard from '../components/ConversationCompleteCard'
import {
  getCareerConversation,
  startCareerConversation,
  submitCareerConversationAnswer,
} from '../lib/careerConversationApi'
import { ApiError } from '../lib/api'
import { useResumeSession } from '../session/ResumeSessionContext'
import type { ConversationSessionState } from '../data/careerConversationTypes'
import type { DashboardOutletContext } from '../layouts/DashboardLayout'

type ConversationApiStatus = 'starting' | 'ready' | 'submitting' | 'error'
// 'init' covers both "starting a brand new conversation" and "restoring an
// existing one" -- both are retried the same way (see handleRetry): just
// call `initSession` again.
type FailedAction = 'init' | 'submit'

export default function CareerConversationPage() {
  const navigate = useNavigate()
  const { resumeAnalysis, resume, jobDescription } = useOutletContext<DashboardOutletContext>()
  const {
    hydrationStatus,
    activeCareerConversationSessionId,
    setActiveCareerConversationSessionId,
    setCareerConversationStatus,
    jobPreparationId,
  } = useResumeSession()

  const [session, setSession] = useState<ConversationSessionState | null>(null)
  const [apiStatus, setApiStatus] = useState<ConversationApiStatus>('starting')
  const [errorMessage, setErrorMessage] = useState('')
  const [failedAction, setFailedAction] = useState<FailedAction>('init')
  const [answer, setAnswer] = useState('')

  const activeSectionRef = useRef<HTMLDivElement>(null)

  // A conversation can only be grounded in a completed analysis — this
  // route is only ever linked to from the Dashboard's CTA once one
  // exists (see CareerConversationBanner), but a direct/refreshed visit
  // could still land here with nothing to ground it in. Only meaningful
  // once hydration has resolved -- before that, `resume`/`jobDescription`/
  // `resumeAnalysis` are still `null` regardless of what's actually
  // persisted, and treating that as "no context" would flash the wrong
  // empty state on every reload (see the hydration gate in the render below).
  const hasContext = resumeAnalysis !== null && resume !== null && jobDescription !== null

  // Set synchronously at the top of each in-flight request and cleared
  // in `finally`, so a second invocation arriving before the first
  // resolves — a fast retry click, or two click events dispatched close
  // enough together that React hasn't re-rendered the `disabled` button
  // yet — bails out immediately instead of firing a second request. The
  // `disabled` prop below is still correct UX (it's what the user sees),
  // but a `boolean` derived from React state only takes effect after a
  // render; this ref closes that window at the source rather than
  // relying on render timing. The backend is still the authoritative
  // guard against a duplicate request landing (see
  // `submit_career_conversation_answer`'s in-lock recheck) — this just
  // avoids sending a request that's already known to be redundant.
  const isBusyRef = useRef(false)

  // Either restores the session named by `activeCareerConversationSessionId`
  // (a pure GET -- doesn't create anything, safe to call again on retry) or,
  // if there isn't one, starts a brand new conversation. Whichever path
  // succeeds, `activeCareerConversationSessionId` ends up pointing at the
  // session now shown, so a later reload restores the same conversation
  // instead of silently starting another one.
  const initSession = useCallback(async () => {
    if (!resume || !jobDescription || !resumeAnalysis) return
    if (isBusyRef.current) return
    isBusyRef.current = true
    setApiStatus('starting')
    setErrorMessage('')
    try {
      if (activeCareerConversationSessionId) {
        try {
          const result = await getCareerConversation(activeCareerConversationSessionId)
          setSession(result)
          setCareerConversationStatus(result.status)
          setApiStatus('ready')
          return
        } catch (err) {
          // A 404 means the backend no longer has this session (e.g. it
          // restarted -- sessions are in-memory only). Drop the stale id
          // so a future load doesn't keep retrying it, but don't silently
          // start a replacement conversation here: the user's previous
          // answers are gone, and that's worth surfacing rather than
          // papering over. The analysis context is untouched, so the
          // existing error UI's retry button re-runs `initSession` with
          // no id left -- which starts a fresh conversation on demand.
          if (err instanceof ApiError && err.cause === 'not_found') {
            setActiveCareerConversationSessionId(null)
            setFailedAction('init')
            setErrorMessage('Your previous conversation could not be found. Start a new one below.')
            setApiStatus('error')
            return
          }
          throw err
        }
      }

      const result = await startCareerConversation(
        resume.text,
        jobDescription.text,
        resumeAnalysis,
        jobPreparationId,
      )
      setSession(result)
      setActiveCareerConversationSessionId(result.session_id)
      setCareerConversationStatus(result.status)
      setApiStatus('ready')
    } catch (err) {
      setFailedAction('init')
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
    setActiveCareerConversationSessionId,
    setCareerConversationStatus,
    jobPreparationId,
  ])

  // Initializes (restores or starts) exactly once per page load, and only
  // once hydration has resolved -- `resume`/`jobDescription`/
  // `resumeAnalysis`/`activeCareerConversationSessionId` aren't trustworthy
  // before then. `hasInitializedRef` (not just an empty dependency array)
  // is what makes this a genuine one-shot: without it, React 18
  // StrictMode's dev-only double effect invocation would fire a second
  // POST /v1/career-conversation (or a second GET) on mount. `initSession`
  // is memoized via `useCallback` specifically so it can be listed here as
  // an honest, exhaustive-deps-clean dependency.
  const hasInitializedRef = useRef(false)
  useEffect(() => {
    if (hydrationStatus !== 'hydrated') return
    if (hasInitializedRef.current) return
    hasInitializedRef.current = true
    void initSession()
  }, [hydrationStatus, initSession])

  async function handleSubmitAnswer() {
    if (!session || !answer.trim()) return
    if (isBusyRef.current) return
    isBusyRef.current = true
    setApiStatus('submitting')
    setErrorMessage('')
    try {
      const result = await submitCareerConversationAnswer(session.session_id, answer.trim())
      setSession(result)
      setCareerConversationStatus(result.status)
      setAnswer('')
      setApiStatus('ready')
    } catch (err) {
      // A 409 means the session itself is fine -- it already moved on
      // from the question just answered (it completed, or a concurrent
      // request advanced it first; see `submitCareerConversationAnswer`'s
      // docstring). Treat it as a synchronization event, not a failure:
      // refetch the authoritative state and resume from there instead of
      // showing an error the user would have to manually dismiss. The
      // stale answer text is cleared either way -- whatever question it
      // was written for is no longer the one on screen.
      if (err instanceof ApiError && err.cause === 'conflict') {
        try {
          const latest = await getCareerConversation(session.session_id)
          setSession(latest)
          setCareerConversationStatus(latest.status)
          setAnswer('')
          setApiStatus('ready')
          return
        } catch {
          // Refetching itself failed -- nothing left to silently recover
          // with, fall through to the normal error path below.
        }
      }
      setFailedAction('submit')
      setErrorMessage(
        err instanceof ApiError ? err.message : 'An unexpected error occurred. Please try again.',
      )
      setApiStatus('error')
    } finally {
      isBusyRef.current = false
    }
  }

  function handleRetry() {
    if (failedAction === 'submit') {
      void handleSubmitAnswer()
    } else {
      void initSession()
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
        {hydrationStatus !== 'hydrated' ? (
          // Rehydration is a synchronous sessionStorage read (a single
          // microtask via useEffect) -- this only ever flashes briefly, but
          // rendering it (rather than nothing, or the "no context" empty
          // state below) matters: showing "Complete a resume analysis
          // first" here would be actively wrong on a reload where a
          // completed analysis is about to be restored a moment later.
          <ConversationLoadingState message="Restoring your session…" />
        ) : !hasContext ? (
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
                {exchange.assistant_response && (
                  <ConversationAssistantReplyBubble text={exchange.assistant_response} />
                )}
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
                {session.current_question.assistant_response && (
                  <ConversationAssistantReplyBubble
                    text={session.current_question.assistant_response}
                  />
                )}
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
