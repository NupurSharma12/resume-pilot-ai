import type { ResumeAnalysisResult } from '../data/types'
import type { ConversationSessionState } from '../data/careerConversationTypes'
import { ApiError } from './api'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL

// Calls the backend's POST /v1/career-conversation to create a new
// session and return its opening question. `resumeAnalysis` is sent back
// exactly as received from `analyzeResume` — the backend's
// `StartConversationRequest.resume_analysis` reuses the same
// `AnalyzeResumeResponse` shape (see the endpoint's own docstring), so no
// mapping is needed here either, matching `analyzeResume`'s "no
// transformation layer" precedent.
export async function startCareerConversation(
  resume: string,
  jobDescription: string,
  resumeAnalysis: ResumeAnalysisResult,
): Promise<ConversationSessionState> {
  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}/v1/career-conversation`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        resume,
        job_description: jobDescription,
        resume_analysis: resumeAnalysis,
      }),
    })
  } catch {
    throw new ApiError('Could not reach the conversation service. Is the backend running?')
  }

  if (!response.ok) {
    throw new ApiError(`Starting the conversation failed (HTTP ${response.status}).`)
  }

  return (await response.json()) as ConversationSessionState
}

// Calls the backend's GET /v1/career-conversation/{sessionId} to fetch an
// existing session's current state without mutating it -- used to restore a
// conversation after a reload/deep link instead of starting a new one. Safe
// to call repeatedly (the endpoint is a pure read; see its docstring).
// Throws `ApiError` on a 404 (unknown/expired session_id) the same as any
// other non-2xx response -- callers distinguish "stale session" from other
// failures via `err.message` or by checking `response.status` themselves if
// they need to (see CareerConversationPage's restore logic).
export async function getCareerConversation(sessionId: string): Promise<ConversationSessionState> {
  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}/v1/career-conversation/${sessionId}`)
  } catch {
    throw new ApiError('Could not reach the conversation service. Is the backend running?')
  }

  if (response.status === 404) {
    throw new ApiError('This conversation session no longer exists.', { cause: 'not_found' })
  }

  if (!response.ok) {
    throw new ApiError(`Restoring the conversation failed (HTTP ${response.status}).`)
  }

  return (await response.json()) as ConversationSessionState
}

// Calls the backend's POST /v1/career-conversation/{sessionId}/answer and
// returns the updated session — either the next question, or a completed
// session with no current question.
//
// A 409 is classified with `cause: 'conflict'` (mirroring `getCareerConversation`'s
// `cause: 'not_found'` for a 404) so callers can distinguish it from any
// other failure. Per the backend's own documentation of this status code
// (see `submit_career_conversation_answer`'s docstring), a 409 here always
// means the *session itself* is fine — it means this specific answer no
// longer applies to the session's current state (it already completed, or
// a concurrent request already advanced it past the question being
// answered) — never that anything was lost. That's exactly the condition
// under which a caller can safely recover by refetching the session's
// current state instead of surfacing a hard error (see
// `CareerConversationPage.handleSubmitAnswer`).
export async function submitCareerConversationAnswer(
  sessionId: string,
  answer: string,
): Promise<ConversationSessionState> {
  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}/v1/career-conversation/${sessionId}/answer`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ answer }),
    })
  } catch {
    throw new ApiError('Could not reach the conversation service. Is the backend running?')
  }

  if (response.status === 409) {
    throw new ApiError('This conversation has already moved on from that question.', {
      cause: 'conflict',
    })
  }

  if (!response.ok) {
    throw new ApiError(`Submitting your answer failed (HTTP ${response.status}).`)
  }

  return (await response.json()) as ConversationSessionState
}
