import type { ResumeAnalysisResult } from '../data/types'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL

// Thrown for both network failures and non-2xx responses, so callers can
// catch one error type regardless of cause.
export class ApiError extends Error {}

// `analyzeResume`'s full result: the analysis itself, plus the durable
// JobPreparation id the backend recorded it against (see
// docs/persistent-backend-workflow-state.md) -- additive on the backend's
// `AnalyzeResumeResponse`, so this is a thin wrapper around the same JSON
// body, not a reshaping of it. `jobPreparationId` is `null` only if the
// backend response omitted it (an older/misconfigured backend), never
// guessed or derived client-side.
export interface AnalyzeResumeResult {
  analysis: ResumeAnalysisResult
  jobPreparationId: string | null
}

// Calls the backend's POST /v1/analyze. `ResumeAnalysisResult`
// (data/types.ts) already mirrors the backend's AnalyzeResumeResponse
// field-for-field (verified during the integration investigation), so
// the JSON body is returned directly as `analysis` — no mapping or
// transformation layer, per the integration requirements. Only
// `job_preparation_id` is pulled out separately, since it isn't part of
// the domain-model shape `ResumeAnalysisResult` mirrors.
export async function analyzeResume(
  resume: string,
  jobDescription: string,
): Promise<AnalyzeResumeResult> {
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

  const { job_preparation_id: jobPreparationId, ...analysis } = (await response.json()) as ResumeAnalysisResult & {
    job_preparation_id?: string | null
  }
  return { analysis, jobPreparationId: jobPreparationId ?? null }
}
