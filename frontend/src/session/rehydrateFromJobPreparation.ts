// Maps a `JobPreparationDetail` (GET /v1/job-preparations/{id} -- the same
// call History's detail view already makes) onto the subset of
// `ResumeSessionContext` fields needed to resume an active session, per
// docs/frontend/resume-session-state.md's "A new analysis resets
// downstream state" section and the History Resumability design review.
//
// Deliberately a pure function, no I/O, no React -- `ResumeSessionContext.
// rehydrateFromHistory` is the only caller, and it does nothing but feed
// this function's output into the context's existing setters (the exact
// same "pure mapper + thin setter-calling wrapper" split `resetForNewAnalysis`
// already established).
//
// `analysis_result`/`career_conversation`/`tailoring_plan`/
// `post_apply_analysis` are typed loosely (`Record<string, unknown> |
// null`) on `JobPreparationDetail` itself -- see that module's own
// docstring for why (the backend never re-validates these JSONB payloads
// against a frontend-owned type). This module is the one place that
// re-asserts them back into the stronger domain types every other page
// already expects, since every one of these payloads is written
// field-for-field from that same domain type in the first place (see
// `app.orchestration.job_preparation_persistence`).
import type { ResumeAnalysisResult } from '../data/types'
import type { GenerateSuggestionsResponse } from '../data/tailoringSuggestionsTypes'
import type { ResumeAnalysisComparison } from '../data/postApplyTypes'
import type { CheckpointStatus, JobPreparationDetail } from '../data/jobPreparationHistoryTypes'
import type { CareerConversationStatus, PersistedFinalTailoredResume } from './resumeSessionTypes'
import { detectSourceFormatFromFilename } from '../lib/sourceFormat'

// Where "Continue" should land, derived from which checkpoint is the
// latest one completed -- see the History Resumability design review's
// checkpoint -> destination table. A fully completed preparation (every
// checkpoint done) still resolves to '/tailored-resume': there is no
// dedicated read-only "completed" route today, and the Tailored Resume
// page already renders correctly read-only in that state (final resume +
// comparison, no pending action). Callers that want to distinguish
// "nothing left to do" for a View-only affordance should read
// `checkpoints.post_apply_analysis_completed_at` directly, not this value.
export type NextPreparationRoute = '/career-conversation' | '/tailored-resume'

export function nextRouteForCheckpoints(checkpoints: CheckpointStatus): NextPreparationRoute {
  if (checkpoints.career_conversation_completed_at === null) return '/career-conversation'
  return '/tailored-resume'
}

interface PersistedCareerConversation {
  session_id: string
  status: CareerConversationStatus
}

interface PersistedTailoringPlan {
  generated_plan: GenerateSuggestionsResponse
  selection: { selected_suggestion_ids: string[]; edited_texts: Record<string, string> } | null
}

interface PersistedPostApplyAnalysis {
  analysis: ResumeAnalysisResult
  comparison: ResumeAnalysisComparison
}

export interface RehydratedSession {
  resume: { text: string; fileName: string }
  jobDescription: { text: string; fileName: null }
  resumeAnalysis: ResumeAnalysisResult
  jobPreparationId: string
  activeCareerConversationSessionId: string | null
  careerConversationStatus: CareerConversationStatus | null
  tailoringPlan: GenerateSuggestionsResponse | null
  tailoringSelections: string[]
  tailoringEditedTexts: Record<string, string>
  tailoringAvailableExportFormats: GenerateSuggestionsResponse['available_export_formats']
  tailoringSourceFormat: ReturnType<typeof detectSourceFormatFromFilename>
  // Never rehydrated: `FinalValidationReport` isn't part of the durable
  // `JobPreparation` record at all (only `/apply`'s live response ever
  // carried it) -- see the design review's "Do not persist
  // FinalValidationReport" requirement. `TailoredResumePage` renders its
  // final-resume card on `finalTailoredResume` alone for exactly this
  // reason, tolerating a null validation report after rehydration.
  finalTailoredResume: PersistedFinalTailoredResume | null
  postApplyAnalysis: ResumeAnalysisResult | null
  postApplyComparison: ResumeAnalysisComparison | null
  nextRoute: NextPreparationRoute
}

export function rehydrateFromJobPreparation(detail: JobPreparationDetail): RehydratedSession {
  const careerConversation = detail.career_conversation as PersistedCareerConversation | null
  const tailoringPlan = detail.tailoring_plan as PersistedTailoringPlan | null
  const postApplyAnalysis = detail.post_apply_analysis as PersistedPostApplyAnalysis | null
  const generatedPlan = tailoringPlan?.generated_plan ?? null
  const selection = tailoringPlan?.selection ?? null

  return {
    resume: { text: detail.resume_text, fileName: detail.resume_name },
    jobDescription: { text: detail.job_description, fileName: null },
    resumeAnalysis: detail.analysis_result as unknown as ResumeAnalysisResult,
    jobPreparationId: detail.id,
    activeCareerConversationSessionId: careerConversation?.session_id ?? null,
    careerConversationStatus: careerConversation?.status ?? null,
    tailoringPlan: generatedPlan,
    tailoringSelections: selection?.selected_suggestion_ids ?? [],
    tailoringEditedTexts: selection?.edited_texts ?? {},
    tailoringAvailableExportFormats: generatedPlan?.available_export_formats ?? [],
    tailoringSourceFormat: detectSourceFormatFromFilename(detail.resume_name),
    finalTailoredResume:
      detail.applied_resume_text !== null
        ? {
            finalResumeText: detail.applied_resume_text,
            appliedSuggestionIds: selection?.selected_suggestion_ids ?? [],
          }
        : null,
    postApplyAnalysis: postApplyAnalysis?.analysis ?? null,
    postApplyComparison: postApplyAnalysis?.comparison ?? null,
    nextRoute: nextRouteForCheckpoints(detail.checkpoints),
  }
}
