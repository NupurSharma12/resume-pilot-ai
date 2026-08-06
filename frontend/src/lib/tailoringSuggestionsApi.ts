import type { ResumeAnalysisResult } from '../data/types'
import type { ConversationSessionState } from '../data/careerConversationTypes'
import type {
  ApplySuggestionsResponse,
  ExportFormat,
  FormatFidelity,
  GenerateSuggestionsResponse,
} from '../data/tailoringSuggestionsTypes'
import { ApiError } from './api'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL

// Stable, narrow classification for the status codes the backend
// documents for these three endpoints (see
// src/app/api/v1/endpoints/tailoring_suggestions.py) -- callers branch on
// `err.cause`, not on parsing `err.message`, the same convention
// `careerConversationApi.ts` already established for 404/409.
export type TailoringApiErrorCause =
  | 'not_found'
  | 'unknown_suggestion'
  | 'conflict'
  | 'revalidation_failed'
  | 'unknown'

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

// Calls the backend's POST /v1/tailoring-suggestions to generate a fresh
// suggestion plan. `resumeAnalysis`/`careerConversation` are sent back
// exactly as received from `analyzeResume`/`getCareerConversation` --
// same "no transformation layer" precedent as the superseded
// `tailorResume` -- and `resumeFilename` is passed through only so the
// backend can compute an honest `default_export_format`; the backend
// never reads that file's content (see GenerateSuggestionsRequest's
// docstring), only its extension.
export async function generateTailoringSuggestions(
  resume: string,
  jobDescription: string,
  resumeAnalysis: ResumeAnalysisResult,
  careerConversation: ConversationSessionState,
  customInstructions: string,
  resumeFilename: string | null,
): Promise<GenerateSuggestionsResponse> {
  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}/v1/tailoring-suggestions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        resume,
        job_description: jobDescription,
        resume_analysis: resumeAnalysis,
        career_conversation: careerConversation,
        custom_instructions:
          customInstructions.trim().length > 0 ? customInstructions.trim() : null,
        resume_filename: resumeFilename,
      }),
    })
  } catch {
    throw new ApiError('Could not reach the tailoring service. Is the backend running?')
  }

  if (!response.ok) {
    await throwForFailedResponse(response, `Generating suggestions failed (HTTP ${response.status}).`)
  }

  return (await response.json()) as GenerateSuggestionsResponse
}

// Calls the backend's POST /v1/tailoring-suggestions/{planId}/apply.
// `editedTexts` is only ever populated for suggestion ids also present in
// `selectedSuggestionIds` -- the backend independently enforces the same
// rule (an edit for an unselected suggestion is simply never applied,
// since only selected ids are looked at), but callers should not rely on
// that; see TailoredResumePage's apply handler for how selections and
// edits are kept in sync client-side too.
export async function applyTailoringSuggestions(
  planId: string,
  selectedSuggestionIds: string[],
  editedTexts: Record<string, string>,
): Promise<ApplySuggestionsResponse> {
  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}/v1/tailoring-suggestions/${planId}/apply`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        selected_suggestion_ids: selectedSuggestionIds,
        edited_texts: editedTexts,
      }),
    })
  } catch {
    throw new ApiError('Could not reach the tailoring service. Is the backend running?')
  }

  if (!response.ok) {
    await throwForFailedResponse(response, `Applying changes failed (HTTP ${response.status}).`)
  }

  return (await response.json()) as ApplySuggestionsResponse
}

export interface ExportedTailoredResumeFile {
  blob: Blob
  filename: string
  contentType: string
  fidelity: FormatFidelity | null
}

// Extracts the quoted filename from a `Content-Disposition:
// attachment; filename="X.pdf"` header value. Falls back to a fixed
// default (never an empty string, never anything from elsewhere in the
// header) if the header is missing or doesn't match the expected shape --
// this is only ever used to *suggest* a filename to the browser's save
// dialog, never as a filesystem path, but a sane fallback keeps the
// downloaded file from ending up literally called "undefined".
function parseFilenameFromContentDisposition(headerValue: string | null): string {
  const DEFAULT_FILENAME = 'Tailored_Resume'
  if (!headerValue) return DEFAULT_FILENAME
  const match = /filename="([^"]+)"/.exec(headerValue)
  return match ? match[1] : DEFAULT_FILENAME
}

function isFormatFidelity(value: string | null): value is FormatFidelity {
  return value === 'exact_original' || value === 'approximate_style' || value === 'regenerated_template'
}

// Calls the backend's POST /v1/tailoring-suggestions/{planId}/export and
// returns the downloadable file plus the metadata needed to label and
// save it. Critically, this only ever treats the response body as a file
// when `response.ok` -- an error response is always JSON (`{"detail":
// ...}`), and reading *that* as a blob and offering it for download would
// silently hand the user a corrupt "PDF"/"DOCX" containing an error
// message instead of surfacing the actual failure.
export async function exportTailoredResume(
  planId: string,
  selectedSuggestionIds: string[],
  editedTexts: Record<string, string>,
  format: ExportFormat,
  filenameBase: string | null,
): Promise<ExportedTailoredResumeFile> {
  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}/v1/tailoring-suggestions/${planId}/export`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        selected_suggestion_ids: selectedSuggestionIds,
        edited_texts: editedTexts,
        format,
        filename_base: filenameBase,
      }),
    })
  } catch {
    throw new ApiError('Could not reach the tailoring service. Is the backend running?')
  }

  if (!response.ok) {
    await throwForFailedResponse(response, `Exporting the resume failed (HTTP ${response.status}).`)
  }

  const blob = await response.blob()
  const fidelityHeader = response.headers.get('X-Export-Fidelity')
  return {
    blob,
    filename: parseFilenameFromContentDisposition(response.headers.get('Content-Disposition')),
    contentType: response.headers.get('Content-Type') ?? 'application/octet-stream',
    fidelity: isFormatFidelity(fidelityHeader) ? fidelityHeader : null,
  }
}

// Triggers a browser download for an already-fetched file, then revokes
// the temporary object URL immediately after -- object URLs are
// process-lifetime otherwise, and leaking one per download is exactly
// the kind of small, avoidable resource leak this function exists to
// prevent. Kept separate from `exportTailoredResume` itself so that
// function stays a pure fetch-and-parse (and so it can be unit-tested
// without a real DOM download side effect).
export function downloadExportedFile(file: ExportedTailoredResumeFile): void {
  const url = URL.createObjectURL(file.blob)
  try {
    const link = document.createElement('a')
    link.href = url
    link.download = file.filename
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
  } finally {
    URL.revokeObjectURL(url)
  }
}
