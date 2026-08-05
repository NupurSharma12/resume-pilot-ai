import type { ResumeAnalysisResult } from '../data/types'
import type { ResumeInputValue } from '../components/ResumeInput'
import type { JobDescriptionInputValue } from '../components/JobDescriptionInput'

export type AnalysisStatus = 'idle' | 'loading' | 'success' | 'error'

// Only the stable statuses are ever written to storage — 'loading' describes
// an in-flight request, which cannot possibly still be in flight after a
// reload, so it has no valid persisted meaning (see normalizeStatus).
export type PersistedAnalysisStatus = 'idle' | 'success' | 'error'

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
