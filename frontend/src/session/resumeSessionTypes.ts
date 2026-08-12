import type { ResumeAnalysisResult } from '../data/types'
import type { ResumeInputValue } from '../components/ResumeInput'
import type { JobDescriptionInputValue } from '../components/JobDescriptionInput'
import type {
  ExportFormat,
  FinalValidationReport,
  GenerateSuggestionsResponse,
  SourceFormat,
} from '../data/tailoringSuggestionsTypes'
import type { ResumeAnalysisComparison } from '../data/postApplyTypes'

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

// Same 'loading' vs persisted-status split as AnalysisStatus/
// TailoringPlanStatus above, for the same reason: re-analysis cannot
// still be in flight after a reload. 'error' means the last re-analysis
// attempt failed to complete -- distinct from `postApplyComparison`
// being null, which just means no re-analysis has ever succeeded yet
// (see PostApplyComparisonCard's docs on why a failure must never be
// presented as a comparison result).
export type PostApplyAnalysisStatus = 'idle' | 'reanalyzing' | 'error'
export type PersistedPostApplyAnalysisStatus = 'idle' | 'error'

// Bumped from 4: adds `jobPreparationId`, the durable JobPreparation this
// session's backend-persisted history (see docs/persistent-backend-workflow-state.md
// and the Job Preparation Checkpoints work) is recorded against, once
// POST /v1/analyze returns one. Same reasoning as every previous bump: a
// session persisted by a prior build never had this field at all, so it
// must fail `isSupportedPersistedSession` and be discarded rather than
// partially rehydrating into a shape this version doesn't expect.
export const RESUME_SESSION_VERSION = 5 as const

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
  // Post-Apply Analysis Loop state (see docs/features/postapply-analysis-loop.md).
  // `resumeAnalysis` above is deliberately never overwritten or cleared by
  // any of this -- it stays the "before" side of the comparison for the
  // lifetime of the session, exactly as the feature requires.
  postApplyAnalysis: ResumeAnalysisResult | null
  postApplyComparison: ResumeAnalysisComparison | null
  postApplyAnalysisStatus: PersistedPostApplyAnalysisStatus
  // The durable JobPreparation this session is recorded against on the
  // backend, once POST /v1/analyze returns one -- null before the first
  // analysis, or if persistence itself is unavailable. Threaded forward
  // to /career-conversation and /tailoring-suggestions (generate) so
  // their own durable history attaches to the same preparation; never
  // re-derived or guessed, only ever set from a backend response.
  jobPreparationId: string | null
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

export function normalizePostApplyAnalysisStatus(
  status: PostApplyAnalysisStatus,
): PersistedPostApplyAnalysisStatus {
  return status === 'reanalyzing' ? 'idle' : status
}
