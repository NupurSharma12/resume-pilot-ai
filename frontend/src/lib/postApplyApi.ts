import type { ResumeAnalysisResult } from '../data/types'
import type { ReanalyzeResponse } from '../data/postApplyTypes'
import { ApiError } from './api'
import type { TailoringApiErrorCause } from './tailoringSuggestionsApi'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL

async function readErrorDetail(response: Response): Promise<string | null> {
  try {
    const body = (await response.json()) as { detail?: unknown }
    return typeof body.detail === 'string' ? body.detail : null
  } catch {
    return null
  }
}

function classifyStatus(status: number): TailoringApiErrorCause {
  if (status === 404) return 'not_found'
  if (status === 400) return 'unknown_suggestion'
  if (status === 409) return 'conflict'
  if (status === 422) return 'revalidation_failed'
  return 'unknown'
}

async function throwForFailedResponse(response: Response, fallbackMessage: string): Promise<never> {
  const detail = await readErrorDetail(response)
  throw new ApiError(detail ?? fallbackMessage, { cause: classifyStatus(response.status) })
}

// Calls the backend's POST /v1/tailoring-suggestions/{planId}/reanalyze --
// the Post-Apply Analysis Loop (see docs/features/postapply-analysis-loop.md).
// Deliberately takes no jobDescription: the backend always re-analyzes
// against the job description `planId` was originally generated against
// (stored server-side on StoredPlan), never a client-supplied one, so the
// "before"/"after" comparison can never silently drift onto a different
// job description than the one `previousAnalysis` was scored against.
//
// A failed call here means "re-analysis could not be completed" -- it
// never fabricates a comparison; the caller must render a distinct
// failure message (see PostApplyComparisonCard's docs), not attempt to
// derive an improved/unchanged/decreased verdict from a partial result.
export async function reanalyzeAfterApply(
  planId: string,
  previousAnalysis: ResumeAnalysisResult,
  selectedSuggestionIds: string[],
  editedTexts: Record<string, string>,
): Promise<ReanalyzeResponse> {
  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}/v1/tailoring-suggestions/${planId}/reanalyze`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        previous_analysis: previousAnalysis,
        selected_suggestion_ids: selectedSuggestionIds,
        edited_texts: editedTexts,
      }),
    })
  } catch {
    throw new ApiError('Could not reach the re-analysis service. Is the backend running?')
  }

  if (!response.ok) {
    await throwForFailedResponse(response, `Re-analysis failed (HTTP ${response.status}).`)
  }

  return (await response.json()) as ReanalyzeResponse
}
