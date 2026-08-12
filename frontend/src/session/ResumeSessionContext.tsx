import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from 'react'
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
import {
  normalizePostApplyAnalysisStatus,
  normalizeStatus,
  normalizeTailoringPlanStatus,
  RESUME_SESSION_VERSION,
  type AnalysisStatus,
  type CareerConversationStatus,
  type PersistedFinalTailoredResume,
  type PostApplyAnalysisStatus,
  type ResumeSessionStorage,
  type TailoringPlanStatus,
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

  // Interactive Tailoring (see docs/features/interactive-tailored-resume.md).
  // `tailoringPlan` is set once per successful "Generate Tailoring Plan"
  // call and is the single source of truth every review-stage component
  // reads suggestions from -- selections/edits below reference it by
  // `suggestion_id`, never a copy of its content.
  tailoringPlan: GenerateSuggestionsResponse | null
  setTailoringPlan: (plan: GenerateSuggestionsResponse | null) => void
  tailoringPlanStatus: TailoringPlanStatus
  setTailoringPlanStatus: (status: TailoringPlanStatus) => void
  tailoringSelections: string[]
  setTailoringSelections: (selections: string[]) => void
  tailoringCustomInstructions: string
  setTailoringCustomInstructions: (instructions: string) => void
  tailoringEditedTexts: Record<string, string>
  setTailoringEditedTexts: (editedTexts: Record<string, string>) => void
  // Set once an "Apply Selected Changes" call succeeds; deliberately
  // never cleared by a later failed apply/export (mirrors the superseded
  // `tailoredResumeResult`'s exact contract) so a failed retry can't wipe
  // out the last good result. Every download control and the Stage 5
  // preview read this, never a page-local copy.
  finalTailoredResume: PersistedFinalTailoredResume | null
  setFinalTailoredResume: (result: PersistedFinalTailoredResume | null) => void
  tailoringValidationReport: FinalValidationReport | null
  setTailoringValidationReport: (report: FinalValidationReport | null) => void
  tailoringAvailableExportFormats: ExportFormat[]
  setTailoringAvailableExportFormats: (formats: ExportFormat[]) => void
  tailoringSourceFormat: SourceFormat | null
  setTailoringSourceFormat: (format: SourceFormat | null) => void

  // Post-Apply Analysis Loop (see docs/features/postapply-analysis-loop.md).
  // `resumeAnalysis` above remains the "before" side of the comparison
  // for the lifetime of the session -- none of this ever overwrites or
  // clears it (see PostApplyComparisonCard for how a failed re-analysis
  // is surfaced without ever fabricating a comparison).
  postApplyAnalysis: ResumeAnalysisResult | null
  setPostApplyAnalysis: (result: ResumeAnalysisResult | null) => void
  postApplyComparison: ResumeAnalysisComparison | null
  setPostApplyComparison: (comparison: ResumeAnalysisComparison | null) => void
  postApplyAnalysisStatus: PostApplyAnalysisStatus
  setPostApplyAnalysisStatus: (status: PostApplyAnalysisStatus) => void

  // The durable JobPreparation this session is recorded against -- see
  // resumeSessionTypes.ts's `PersistedResumeSession.jobPreparationId`.
  jobPreparationId: string | null
  setJobPreparationId: (id: string | null) => void

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

  const [tailoringPlan, setTailoringPlan] = useState<GenerateSuggestionsResponse | null>(null)
  const [tailoringPlanStatus, setTailoringPlanStatus] = useState<TailoringPlanStatus>('idle')
  const [tailoringSelections, setTailoringSelections] = useState<string[]>([])
  const [tailoringCustomInstructions, setTailoringCustomInstructions] = useState('')
  const [tailoringEditedTexts, setTailoringEditedTexts] = useState<Record<string, string>>({})
  const [finalTailoredResume, setFinalTailoredResume] =
    useState<PersistedFinalTailoredResume | null>(null)
  const [tailoringValidationReport, setTailoringValidationReport] =
    useState<FinalValidationReport | null>(null)
  const [tailoringAvailableExportFormats, setTailoringAvailableExportFormats] = useState<
    ExportFormat[]
  >([])
  const [tailoringSourceFormat, setTailoringSourceFormat] = useState<SourceFormat | null>(null)

  const [postApplyAnalysis, setPostApplyAnalysis] = useState<ResumeAnalysisResult | null>(null)
  const [postApplyComparison, setPostApplyComparison] =
    useState<ResumeAnalysisComparison | null>(null)
  const [postApplyAnalysisStatus, setPostApplyAnalysisStatus] =
    useState<PostApplyAnalysisStatus>('idle')

  const [jobPreparationId, setJobPreparationId] = useState<string | null>(null)

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
      setTailoringPlan(persisted.tailoringPlan)
      setTailoringPlanStatus(persisted.tailoringPlanStatus)
      setTailoringSelections(persisted.tailoringSelections)
      setTailoringCustomInstructions(persisted.tailoringCustomInstructions)
      setTailoringEditedTexts(persisted.tailoringEditedTexts)
      setFinalTailoredResume(persisted.finalTailoredResume)
      setTailoringValidationReport(persisted.tailoringValidationReport)
      setTailoringAvailableExportFormats(persisted.tailoringAvailableExportFormats)
      setTailoringSourceFormat(persisted.tailoringSourceFormat)
      setPostApplyAnalysis(persisted.postApplyAnalysis)
      setPostApplyComparison(persisted.postApplyComparison)
      setPostApplyAnalysisStatus(persisted.postApplyAnalysisStatus)
      setJobPreparationId(persisted.jobPreparationId)
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
      tailoringPlan,
      tailoringPlanStatus: normalizeTailoringPlanStatus(tailoringPlanStatus),
      tailoringSelections,
      tailoringCustomInstructions,
      tailoringEditedTexts,
      finalTailoredResume,
      tailoringValidationReport,
      tailoringAvailableExportFormats,
      tailoringSourceFormat,
      postApplyAnalysis,
      postApplyComparison,
      postApplyAnalysisStatus: normalizePostApplyAnalysisStatus(postApplyAnalysisStatus),
      jobPreparationId,
    })
  }, [
    hydrationStatus,
    resume,
    jobDescription,
    resumeAnalysis,
    status,
    activeCareerConversationSessionId,
    careerConversationStatus,
    tailoringPlan,
    tailoringPlanStatus,
    tailoringSelections,
    tailoringCustomInstructions,
    tailoringEditedTexts,
    finalTailoredResume,
    tailoringValidationReport,
    tailoringAvailableExportFormats,
    tailoringSourceFormat,
    postApplyAnalysis,
    postApplyComparison,
    postApplyAnalysisStatus,
    jobPreparationId,
    storage,
  ])

  function clearSession() {
    setResume(null)
    setJobDescription(null)
    setResumeAnalysis(null)
    setStatus('idle')
    setActiveCareerConversationSessionId(null)
    setCareerConversationStatus(null)
    setTailoringPlan(null)
    setTailoringPlanStatus('idle')
    setTailoringSelections([])
    setTailoringCustomInstructions('')
    setTailoringEditedTexts({})
    setFinalTailoredResume(null)
    setTailoringValidationReport(null)
    setTailoringAvailableExportFormats([])
    setTailoringSourceFormat(null)
    setPostApplyAnalysis(null)
    setPostApplyComparison(null)
    setPostApplyAnalysisStatus('idle')
    setJobPreparationId(null)
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
    tailoringPlan,
    setTailoringPlan,
    tailoringPlanStatus,
    setTailoringPlanStatus,
    tailoringSelections,
    setTailoringSelections,
    tailoringCustomInstructions,
    setTailoringCustomInstructions,
    tailoringEditedTexts,
    setTailoringEditedTexts,
    finalTailoredResume,
    setFinalTailoredResume,
    tailoringValidationReport,
    setTailoringValidationReport,
    tailoringAvailableExportFormats,
    setTailoringAvailableExportFormats,
    tailoringSourceFormat,
    setTailoringSourceFormat,
    postApplyAnalysis,
    setPostApplyAnalysis,
    postApplyComparison,
    setPostApplyComparison,
    postApplyAnalysisStatus,
    setPostApplyAnalysisStatus,
    jobPreparationId,
    setJobPreparationId,
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
