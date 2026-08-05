import type { ResumeAnalysisResult } from '../data/types'
import type { ConversationSessionState } from '../data/careerConversationTypes'
import type { TailorResumeResult } from '../data/tailoringTypes'
import { ApiError } from './api'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL

// Calls the backend's POST /v1/tailor-resume and returns its response as-is.
// `resumeAnalysis`/`careerConversation` are sent back exactly as received
// from `analyzeResume`/`getCareerConversation` — the backend's
// `TailorResumeRequest.resume_analysis`/`.career_conversation` reuse the
// same `AnalyzeResumeResponse`/`ConversationSessionResponse` shapes (see
// the endpoint's own docstring), so no mapping is needed here, matching
// `analyzeResume`/`startCareerConversation`'s "no transformation layer"
// precedent.
export async function tailorResume(
  resume: string,
  jobDescription: string,
  resumeAnalysis: ResumeAnalysisResult,
  careerConversation: ConversationSessionState,
): Promise<TailorResumeResult> {
  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}/v1/tailor-resume`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        resume,
        job_description: jobDescription,
        resume_analysis: resumeAnalysis,
        career_conversation: careerConversation,
      }),
    })
  } catch {
    throw new ApiError('Could not reach the tailoring service. Is the backend running?')
  }

  if (!response.ok) {
    throw new ApiError(`Generating the tailored resume failed (HTTP ${response.status}).`)
  }

  return (await response.json()) as TailorResumeResult
}
