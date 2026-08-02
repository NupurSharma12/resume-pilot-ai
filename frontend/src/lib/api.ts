import type { ResumeAnalysisResult } from '../data/types'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL

// Thrown for both network failures and non-2xx responses, so callers can
// catch one error type regardless of cause.
export class ApiError extends Error {}

// Calls the backend's POST /v1/analyze and returns its response as-is.
// `ResumeAnalysisResult` (data/types.ts) already mirrors the backend's
// AnalyzeResumeResponse field-for-field (verified during the integration
// investigation), so the JSON body is returned directly — no mapping or
// transformation layer, per the integration requirements.
export async function analyzeResume(
  resume: string,
  jobDescription: string,
): Promise<ResumeAnalysisResult> {
  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}/v1/analyze`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ resume, job_description: jobDescription }),
    })
  } catch {
    throw new ApiError('Could not reach the analysis service. Is the backend running?')
  }

  if (!response.ok) {
    throw new ApiError(`Analysis request failed (HTTP ${response.status}).`)
  }

  return (await response.json()) as ResumeAnalysisResult
}
