import type { ResumeAnalysisResult } from '../data/types'
import type { ResumeInputValue } from '../components/ResumeInput'
import type { JobDescriptionInputValue } from '../components/JobDescriptionInput'
import type {
  ExportFormat,
  FinalValidationReport,
  GenerateSuggestionsResponse,
  SourceFormat,
} from '../data/tailoringSuggestionsTypes'

export type AnalysisStatus = 'idle' | 'loading' | 'success' | 'error'

// Only the stable statuses are ever written to storage — 'loading' describes
// an in-flight request, which cannot possibly still be in flight after a
// reload, so it has no valid persisted meaning (see normalizeStatus).
export type PersistedAnalysisStatus = 'idle' | 'success' | 'error'

// Mirrors the backend's `ConversationSessionStatus` — kept here (not
// imported from careerConversationTypes.ts) as a lightweight, independent
// summary signal: the full session lives locally in CareerConversationPage,
// this is only ever "in_progress" | "complete" | "no conversation started
// yet", exactly the fidelity DashboardPage/ConversationCompleteCard need
// to decide what a Tailored Resume CTA should say, without either of them
// re-fetching the full session just to read one field.
export type CareerConversationStatus = 'in_progress' | 'complete'

// Generation status for the suggestion *plan* only (Stage 1) — applying
// and exporting have their own transient, page-local busy/error state in
// TailoredResumePage, since a failed apply/export must never blot out an
// already-generated plan or already-applied final resume (see that
// page's docstring). Same 'loading' vs persisted-status split as
// AnalysisStatus, for the same reason: 'generating' cannot still be true
// after a reload.
export type TailoringPlanStatus = 'idle' | 'generating' | 'error'
export type PersistedTailoringPlanStatus = 'idle' | 'error'

// Bumped from 1: `TailoringSuggestion` gained a required `conflicts_with`
// field (see docs/features/interactive-tailored-resume.md's atomic-
// suggestions section) that a session persisted by a prior build's
// `tailoringPlan.suggestions` won't carry. `tailoringPlan`'s own content
// is deliberately never deep-validated below (see
// `isSupportedPersistedSession`'s docstring in resumeSessionStorage.ts),
// so an un-bumped version here would have let that stale plan rehydrate
// and crash the page the moment anything read `.conflicts_with` off an
// old suggestion.
export const RESUME_SESSION_VERSION = 3 as const

// A compact record of the last successfully applied final resume —
// deliberately just the rendered text and which suggestions produced it,
// not the full structured resume (the backend re-derives that
// deterministically from the plan + selections whenever it's needed
// again, e.g. for export — see ExportResumeRequest's docstring) and never
// any exported binary (PDF/DOCX bytes never touch storage — see
// resumeSessionStorage.ts's module docstring).
export interface PersistedFinalTailoredResume {
  finalResumeText: string
  appliedSuggestionIds: string[]
}

// The full shape written to storage. Deliberately excludes anything
// transient/UI-only (isInputCollapsed, errorMessage text, loading spinners) —
// those are re-derivable or not worth restoring, and persisting them would
// just be more state to get wrong on schema changes.
export interface PersistedResumeSession {
  version: typeof RESUME_SESSION_VERSION
  resume: ResumeInputValue | null
  jobDescription: JobDescriptionInputValue | null
  resumeAnalysis: ResumeAnalysisResult | null
  status: PersistedAnalysisStatus
  activeCareerConversationSessionId: string | null
  careerConversationStatus: CareerConversationStatus | null
  // Interactive Tailoring state (see docs/features/interactive-tailored-resume.md).
  tailoringPlan: GenerateSuggestionsResponse | null
  tailoringPlanStatus: PersistedTailoringPlanStatus
  tailoringSelections: string[]
  tailoringCustomInstructions: string
  // Keyed by suggestion_id -- only ever contains entries for suggestions
  // the user has actually edited (see Part 6, "Editing individual
  // suggestions"); a suggestion absent from this map still uses its
  // original, model-generated suggested_text.
  tailoringEditedTexts: Record<string, string>
  finalTailoredResume: PersistedFinalTailoredResume | null
  tailoringValidationReport: FinalValidationReport | null
  tailoringAvailableExportFormats: ExportFormat[]
  tailoringSourceFormat: SourceFormat | null
}

// Small and framework-independent on purpose: today's implementation reads
// and writes `sessionStorage` directly, but a future implementation could
// instead call a backend "Analysis Session" API keyed by an id in the URL —
// neither the provider nor any page needs to change for that, only this
// interface's implementation.
export interface ResumeSessionStorage {
  load(): PersistedResumeSession | null
  save(session: PersistedResumeSession): void
  clear(): void
}

export function normalizeStatus(status: AnalysisStatus): PersistedAnalysisStatus {
  return status === 'loading' ? 'idle' : status
}

export function normalizeTailoringPlanStatus(
  status: TailoringPlanStatus,
): PersistedTailoringPlanStatus {
  return status === 'generating' ? 'idle' : status
}
