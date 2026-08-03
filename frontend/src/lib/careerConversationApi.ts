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

// Calls the backend's POST /v1/career-conversation/{sessionId}/answer and
// returns the updated session — either the next question, or a completed
// session with no current question.
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

  if (!response.ok) {
    throw new ApiError(`Submitting your answer failed (HTTP ${response.status}).`)
  }

  return (await response.json()) as ConversationSessionState
}
