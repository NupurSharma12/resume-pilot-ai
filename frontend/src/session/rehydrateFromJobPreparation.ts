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
// `app.orchestration.job_preparation_persistence`) -- except
// `tailoring_plan.generated_plan`, which is the one payload that is
// *not* a full API-response shape (see `PersistedTailoringPlanContent`
// below), and `analysis_result`, which -- unlike the others -- is
// actually validated before use, not just cast (see
// `isValidResumeAnalysisResult`): persisted JSONB can be of any vintage
// or origin, and this is the one boundary where that risk is checked
// once instead of trusting it silently all the way into `DashboardPage`/
// `insights.ts`.
import type { ResumeAnalysisResult } from '../data/types'
import type { GenerateSuggestionsResponse, TailoringPlanContent } from '../data/tailoringSuggestionsTypes'
import type { ResumeAnalysisComparison } from '../data/postApplyTypes'
import type { CheckpointStatus, JobPreparationDetail } from '../data/jobPreparationHistoryTypes'
import type { CareerConversationStatus, PersistedFinalTailoredResume } from './resumeSessionTypes'
import { ALL_EXPORT_FORMATS, detectSourceFormatFromFilename } from '../lib/sourceFormat'

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

// What `record_generated_tailoring_plan` actually persists into
// `tailoring_plan.generated_plan` -- `result.plan.model_dump(mode="json")`,
// the internal `SuggestionPlan` domain object (app.api.v1.endpoints.
// tailoring_suggestions), never the full `GenerateSuggestionsResponse`.
// Typing this as `GenerateSuggestionsResponse` (as this module used to)
// was a lie: `available_export_formats`/`default_export_format` are
// computed fresh for the HTTP response only and are never part of what's
// stored here, for *any* preparation, not just old ones -- see
// `TailoringPlanContent`'s own docstring.
interface PersistedTailoringPlan {
  generated_plan: TailoringPlanContent
  selection: { selected_suggestion_ids: string[]; edited_texts: Record<string, string> } | null
}

interface PersistedPostApplyAnalysis {
  analysis: ResumeAnalysisResult
  comparison: ResumeAnalysisComparison
}

// Runtime guard for `analysis_result`, the one persisted JSONB payload
// this module actually validates instead of blindly casting -- see this
// module's own docstring. Deliberately shallow (checks presence/type of
// every top-level field `insights.ts`/`DashboardPage` actually read, not
// every nested item's own fields): enough to guarantee `buildExecutiveSummary`
// et al. can't crash on `undefined.slice()`, without turning this into a
// full schema validator this codebase has no other precedent for.
function isValidResumeAnalysisResult(value: unknown): value is ResumeAnalysisResult {
  if (typeof value !== 'object' || value === null) return false
  const record = value as Record<string, unknown>

  const overallAssessment = record.overall_assessment
  if (typeof overallAssessment !== 'object' || overallAssessment === null) return false
  const assessment = overallAssessment as Record<string, unknown>
  if (typeof assessment.overall_score !== 'number') return false
  if (typeof assessment.summary !== 'string') return false

  const hiringRecommendation = assessment.hiring_recommendation
  if (typeof hiringRecommendation !== 'object' || hiringRecommendation === null) return false
  const recommendation = hiringRecommendation as Record<string, unknown>
  if (typeof recommendation.decision !== 'string' || typeof recommendation.reason !== 'string') {
    return false
  }

  return (
    Array.isArray(record.skill_matches) &&
    Array.isArray(record.matching_projects) &&
    Array.isArray(record.strengths) &&
    Array.isArray(record.weaknesses) &&
    Array.isArray(record.resume_improvements)
  )
}

export interface RehydratedSession {
  resume: { text: string; fileName: string }
  jobDescription: { text: string; fileName: null }
  resumeAnalysis: ResumeAnalysisResult
  jobPreparationId: string
  activeCareerConversationSessionId: string | null
  careerConversationStatus: CareerConversationStatus | null
  tailoringPlan: TailoringPlanContent | null
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

// Discriminated union, not a thrown exception: an invalid persisted
// preparation is an expected, recoverable outcome ("Continue" fails
// gracefully with a message in the dialog -- see `HistoryPage`), not a
// programmer error. Every caller must explicitly branch on `ok` before
// touching `session`, so an invalid `analysis_result` can never silently
// flow into `ResumeSessionContext` and crash an unrelated page later
// (see this module's own docstring for the bug this replaces).
export type RehydrationOutcome =
  | { ok: true; session: RehydratedSession }
  | { ok: false; error: string }

export function rehydrateFromJobPreparation(detail: JobPreparationDetail): RehydrationOutcome {
  if (!isValidResumeAnalysisResult(detail.analysis_result)) {
    return {
      ok: false,
      error:
        "This preparation's saved analysis can't be restored -- its data is in a format this " +
        'version no longer supports. Please start a new analysis instead.',
    }
  }

  const careerConversation = detail.career_conversation as PersistedCareerConversation | null
  const tailoringPlan = detail.tailoring_plan as PersistedTailoringPlan | null
  const postApplyAnalysis = detail.post_apply_analysis as PersistedPostApplyAnalysis | null
  const generatedPlan = tailoringPlan?.generated_plan ?? null
  const selection = tailoringPlan?.selection ?? null

  return {
    ok: true,
    session: {
      resume: { text: detail.resume_text, fileName: detail.resume_name },
      jobDescription: { text: detail.job_description, fileName: null },
      resumeAnalysis: detail.analysis_result,
      jobPreparationId: detail.id,
      activeCareerConversationSessionId: careerConversation?.session_id ?? null,
      careerConversationStatus: careerConversation?.status ?? null,
      tailoringPlan: generatedPlan,
      tailoringSelections: selection?.selected_suggestion_ids ?? [],
      tailoringEditedTexts: selection?.edited_texts ?? {},
      // Always the full, constant list once a plan exists -- never read
      // off the persisted plan itself, which never has this field (see
      // `TailoringPlanContent`'s docstring). No plan yet means nothing to
      // download, so `[]` is still correct in that case.
      tailoringAvailableExportFormats: generatedPlan !== null ? ALL_EXPORT_FORMATS : [],
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
    },
  }
}
