// Mirrors the FastAPI backend's Interactive Tailoring response shapes
// field-for-field (src/app/api/v1/models/tailoring_suggestions.py),
// snake_case included — same convention as ResumeAnalysisResult/
// ConversationSessionState in types.ts/careerConversationTypes.ts, so a
// real API response body needs no reshaping. Replaces the old, now-dead
// tailoringTypes.ts (the whole-section /v1/tailor-resume contract it
// mirrored no longer exists — see docs/features/tailoring-engine.md's
// "superseded" note).

export type SuggestionOperation =
  | 'append'
  | 'insert_before'
  | 'insert_after'
  | 'update'
  | 'replace'
  | 'remove'
  | 'add_emphasis'

export type SuggestionValidationStatus =
  | 'supported_by_original_resume'
  | 'supported_by_conversation'
  | 'supported_by_both'
  | 'unsupported'
  | 'structurally_invalid'
  | 'conflict'

export interface TailoringSuggestion {
  suggestion_id: string
  target_section_id: string
  target_item_id: string
  operation: SuggestionOperation
  current_text: string | null
  suggested_text: string
  reason: string
  evidence_ids: string[]
  evidence_sources: string[]
  confidence: number
  selected_by_default: boolean
  validation_status: SuggestionValidationStatus
  validation_issues: string[]
  conflicts_with: string[]
}

export type ExportFormat = 'txt' | 'markdown' | 'docx' | 'pdf'

export type FormatFidelity = 'exact_original' | 'approximate_style' | 'regenerated_template'

// The originally uploaded document's format, as the backend's ingestion
// layer names it (app.ingestion.models.DocumentFormat) — used only to
// label the "default" export option honestly; never used to look up any
// file content, since no original file bytes are retained after upload.
export type SourceFormat = 'pdf' | 'docx' | 'markdown' | 'plain_text'

// What's actually durable about a generated plan -- `plan_id` +
// `suggestions` are the only two fields `record_generated_tailoring_plan`
// persists into `job_preparations.tailoring_plan.generated_plan` (see
// `app.api.v1.endpoints.tailoring_suggestions`'s own persistence call,
// which passes `result.plan.model_dump(mode="json")` -- the internal
// `SuggestionPlan` domain object, never the full HTTP response). Session
// state that must survive both a live generation *and* a History
// rehydration (`ResumeSessionContext.tailoringPlan`) is typed as this
// narrower shape, not `GenerateSuggestionsResponse` below -- see
// `rehydrateFromJobPreparation.ts`'s docstring for the bug this fixes.
export interface TailoringPlanContent {
  plan_id: string
  suggestions: TailoringSuggestion[]
}

// The full `POST /v1/tailoring-suggestions` response. `available_export_formats`/
// `default_export_format` are deliberately *not* part of `TailoringPlanContent`
// above: the backend computes both fresh on every response (`_ALL_EXPORT_FORMATS`
// is a constant; `default_export_format` is derived from the resume's
// filename) and never persists either -- see `app.api.v1.endpoints.
// tailoring_suggestions`'s own docstring. Any caller that needs "what
// formats can this be downloaded as" should derive it the same
// stateless way (see `lib/sourceFormat.ts`'s `ALL_EXPORT_FORMATS`/
// `defaultExportFormatForSourceFormat`), not read it off a stored plan.
export interface GenerateSuggestionsResponse extends TailoringPlanContent {
  available_export_formats: ExportFormat[]
  default_export_format: ExportFormat
}

export interface FinalValidationReport {
  is_valid: boolean
  messages: string[]
}

export interface ApplySuggestionsResponse {
  applied_suggestion_ids: string[]
  final_resume_text: string
  final_validation: FinalValidationReport
}
