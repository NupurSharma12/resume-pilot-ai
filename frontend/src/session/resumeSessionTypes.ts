import type { ResumeAnalysisResult } from '../data/types'
import type { ResumeInputValue } from '../components/ResumeInput'
import type { JobDescriptionInputValue } from '../components/JobDescriptionInput'
import type { TailorResumeResult } from '../data/tailoringTypes'

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

export const RESUME_SESSION_VERSION = 1 as const

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
  tailoredResumeResult: TailorResumeResult | null
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
