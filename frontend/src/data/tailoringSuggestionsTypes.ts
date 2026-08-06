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
}

export type ExportFormat = 'txt' | 'markdown' | 'docx' | 'pdf'

export type FormatFidelity = 'exact_original' | 'approximate_style' | 'regenerated_template'

// The originally uploaded document's format, as the backend's ingestion
// layer names it (app.ingestion.models.DocumentFormat) — used only to
// label the "default" export option honestly; never used to look up any
// file content, since no original file bytes are retained after upload.
export type SourceFormat = 'pdf' | 'docx' | 'markdown' | 'plain_text'

export interface GenerateSuggestionsResponse {
  plan_id: string
  suggestions: TailoringSuggestion[]
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
