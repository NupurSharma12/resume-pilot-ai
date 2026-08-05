import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from 'react'
import type { ResumeAnalysisResult } from '../data/types'
import type { ResumeInputValue } from '../components/ResumeInput'
import type { JobDescriptionInputValue } from '../components/JobDescriptionInput'
import type { TailorResumeResult } from '../data/tailoringTypes'
import {
  normalizeStatus,
  RESUME_SESSION_VERSION,
  type AnalysisStatus,
  type CareerConversationStatus,
  type ResumeSessionStorage,
} from './resumeSessionTypes'
import { sessionStorageResumeSessionStorage } from './resumeSessionStorage'

// Distinguishes "haven't looked at storage yet" from "looked, found
// nothing" -- both leave every field `null`/`idle`, but only the latter is
// safe to treat as a real answer (e.g. render CareerConversationPage's
// "no analysis yet" empty state). See ResumeSessionProvider's hydration effect.
export type HydrationStatus = 'pending' | 'hydrated'

export interface ResumeSessionContextValue {
  hydrationStatus: HydrationStatus
  resume: ResumeInputValue | null
  setResume: (value: ResumeInputValue | null) => void
  jobDescription: JobDescriptionInputValue | null
  setJobDescription: (value: JobDescriptionInputValue | null) => void
  resumeAnalysis: ResumeAnalysisResult | null
  setResumeAnalysis: (result: ResumeAnalysisResult) => void
  status: AnalysisStatus
  setStatus: (status: AnalysisStatus) => void
  activeCareerConversationSessionId: string | null
  setActiveCareerConversationSessionId: (sessionId: string | null) => void
  // A lightweight summary signal, not the source of truth for the
  // conversation itself (that stays local to CareerConversationPage) --
  // see resumeSessionTypes.ts's `CareerConversationStatus` docstring for
  // why this exists here at all.
  careerConversationStatus: CareerConversationStatus | null
  setCareerConversationStatus: (status: CareerConversationStatus | null) => void
  // Set once a tailoring run succeeds; deliberately never cleared by a
  // failed regeneration (see TailoredResumePage) so a later failed retry
  // can't wipe out the last good result. Presence of a non-null value is
  // what every "Generate" vs "View Tailored Resume" CTA (TailoredResumeBanner,
  // ConversationCompleteCard, TailoredResumePage itself) checks, so there is
  // exactly one place this is ever set.
  tailoredResumeResult: TailorResumeResult | null
  setTailoredResumeResult: (result: TailorResumeResult) => void
  clearSession: () => void
}

const ResumeSessionContext = createContext<ResumeSessionContextValue | null>(null)

interface ResumeSessionProviderProps {
  children: ReactNode
  // Overridable so tests (and, later, a backend-persisted implementation)
  // can supply a different `ResumeSessionStorage` without the provider's
  // own logic changing.
  storage?: ResumeSessionStorage
}

export function ResumeSessionProvider({
  children,
  storage = sessionStorageResumeSessionStorage,
}: ResumeSessionProviderProps) {
  const [hydrationStatus, setHydrationStatus] = useState<HydrationStatus>('pending')
  const [resume, setResume] = useState<ResumeInputValue | null>(null)
  const [jobDescription, setJobDescription] = useState<JobDescriptionInputValue | null>(null)
  const [resumeAnalysis, setResumeAnalysis] = useState<ResumeAnalysisResult | null>(null)
  const [status, setStatus] = useState<AnalysisStatus>('idle')
  const [activeCareerConversationSessionId, setActiveCareerConversationSessionId] = useState<
    string | null
  >(null)
  const [careerConversationStatus, setCareerConversationStatus] =
    useState<CareerConversationStatus | null>(null)
  const [tailoredResumeResult, setTailoredResumeResult] = useState<TailorResumeResult | null>(
    null,
  )

  // Reads storage exactly once. Guarded with a ref (not just an empty
  // dependency array) so React 18 StrictMode's dev-only double effect
  // invocation can't apply a stale second `storage.load()` result on top --
  // `load()` is a pure read so a second call would be harmless here anyway,
  // but the guard keeps the intent ("hydrate once") explicit and matches
  // the one-shot pattern already used elsewhere in this codebase (see
  // CareerConversationPage's `hasStartedRef`).
  const hasHydratedRef = useRef(false)
  useEffect(() => {
    if (hasHydratedRef.current) return
    hasHydratedRef.current = true

    const persisted = storage.load()
    if (persisted) {
      setResume(persisted.resume)
      setJobDescription(persisted.jobDescription)
      setResumeAnalysis(persisted.resumeAnalysis)
      setStatus(persisted.status)
      setActiveCareerConversationSessionId(persisted.activeCareerConversationSessionId)
      setCareerConversationStatus(persisted.careerConversationStatus)
      setTailoredResumeResult(persisted.tailoredResumeResult)
    }
    setHydrationStatus('hydrated')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Persists on every meaningful change -- but never before hydration has
  // finished. Without the `hydrationStatus` gate, this effect's very first
  // run (with the initial `null`/`idle` state) would write over whatever
  // was already in storage a moment before `storage.load()` got to apply it.
  useEffect(() => {
    if (hydrationStatus !== 'hydrated') return
    storage.save({
      version: RESUME_SESSION_VERSION,
      resume,
      jobDescription,
      resumeAnalysis,
      status: normalizeStatus(status),
      activeCareerConversationSessionId,
      careerConversationStatus,
      tailoredResumeResult,
    })
  }, [
    hydrationStatus,
    resume,
    jobDescription,
    resumeAnalysis,
    status,
    activeCareerConversationSessionId,
    careerConversationStatus,
    tailoredResumeResult,
    storage,
  ])

  function clearSession() {
    setResume(null)
    setJobDescription(null)
    setResumeAnalysis(null)
    setStatus('idle')
    setActiveCareerConversationSessionId(null)
    setCareerConversationStatus(null)
    setTailoredResumeResult(null)
    storage.clear()
  }

  const value: ResumeSessionContextValue = {
    hydrationStatus,
    resume,
    setResume,
    jobDescription,
    setJobDescription,
    resumeAnalysis,
    setResumeAnalysis,
    status,
    setStatus,
    activeCareerConversationSessionId,
    setActiveCareerConversationSessionId,
    careerConversationStatus,
    setCareerConversationStatus,
    tailoredResumeResult,
    setTailoredResumeResult,
    clearSession,
  }

  return <ResumeSessionContext.Provider value={value}>{children}</ResumeSessionContext.Provider>
}

export function useResumeSession(): ResumeSessionContextValue {
  const context = useContext(ResumeSessionContext)
  if (!context) {
    throw new Error('useResumeSession must be used within a ResumeSessionProvider')
  }
  return context
}
