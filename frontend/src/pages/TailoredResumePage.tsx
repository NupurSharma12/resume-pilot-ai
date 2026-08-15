import { useCallback, useMemo, useRef, useState } from 'react'
import { BarChart2, CheckSquare, RotateCw, Square, Wand2 } from 'lucide-react'
import { useNavigate, useOutletContext } from 'react-router-dom'
import TopHeader from '../components/TopHeader'
import Button from '../components/Button'
import ConversationLoadingState from '../components/ConversationLoadingState'
import TailoringErrorState from '../components/TailoringErrorState'
import TailoringSuggestionCard from '../components/TailoringSuggestionCard'
import TailoringPlanSummaryHeader from '../components/TailoringPlanSummaryHeader'
import TailoringFinalResumeCard from '../components/TailoringFinalResumeCard'
import TailoringDownloadPanel from '../components/TailoringDownloadPanel'
import TailoringPreviewPanel from '../components/TailoringPreviewPanel'
import PostApplyComparisonCard from '../components/PostApplyComparisonCard'
import { getCareerConversation } from '../lib/careerConversationApi'
import { getJobPreparation } from '../lib/jobPreparationHistoryApi'
import {
  buildConflictSummaries,
  buildSectionFallbackOrdinals,
  buildSectionNameMap,
  groupSuggestionsBySection,
} from '../lib/suggestionPresentation'
import { remapSelectionsToNewPlan } from '../lib/suggestionRecovery'
import {
  applyTailoringSuggestions,
  downloadExportedFile,
  exportTailoredResume,
  generateTailoringSuggestions,
} from '../lib/tailoringSuggestionsApi'
import { reanalyzeAfterApply } from '../lib/postApplyApi'
import { ApiError } from '../lib/api'
import { candidateFilenameBase, detectSourceFormatFromFilename } from '../lib/sourceFormat'
import { useResumeSession } from '../session/ResumeSessionContext'
import type { DashboardOutletContext } from '../layouts/DashboardLayout'
import type {
  ApplySuggestionsResponse,
  ExportFormat,
  GenerateSuggestionsResponse,
} from '../data/tailoringSuggestionsTypes'
import type { ConversationSessionState } from '../data/careerConversationTypes'

const RECOVERY_MESSAGE =
  'We need to regenerate your tailoring suggestions before applying changes.\n\n' +
  'Your resume and conversation are safe.\n\n' +
  'Click Regenerate Suggestions to continue.'

// Parses the suggestion id a 422 revalidation failure names out of the
// backend's error message (see `SuggestionRevalidationFailedError` in
// app.tailoring.applier: "Edited text for suggestion 'suggestion-0'
// failed validation: ..."), so the error can be shown inline on the
// specific suggestion's card rather than only as a generic banner.
// Falls back to `null` (generic banner) if the message doesn't match --
// deliberately tolerant of the backend's exact wording changing, since
// this is a display nicety, not a contract either side depends on.
function parseRevalidationSuggestionId(message: string): string | null {
  const match = /suggestion '([^']+)'/.exec(message)
  return match ? match[1] : null
}

// The live Career Conversation transcript lives in `ConversationSessionStore`
// (in-memory, process-lifetime only -- see that module's own docstring),
// so a backend restart between completing the conversation and generating
// a tailoring plan makes `sessionId` 404. That is recoverable without any
// new backend endpoint: the exact same transcript was already durably
// persisted onto `JobPreparation.career_conversation` the moment the
// conversation completed (see `record_career_conversation` -- only ever
// called once `status` reaches `complete`, so this fallback can only ever
// apply to a genuinely complete conversation, never a half-finished one).
// Falling back here, rather than surfacing the 404 as a hard error, is
// what lets a rehydrated-from-History session (or any session that
// outlives a backend restart) still generate/regenerate a tailoring plan.
async function getCareerConversationOrPersisted(
  sessionId: string,
  jobPreparationId: string | null,
): Promise<ConversationSessionState> {
  try {
    return await getCareerConversation(sessionId)
  } catch (err) {
    if (err instanceof ApiError && err.cause === 'not_found' && jobPreparationId) {
      const jobPreparation = await getJobPreparation(jobPreparationId)
      if (jobPreparation.career_conversation) {
        return jobPreparation.career_conversation as unknown as ConversationSessionState
      }
    }
    throw err
  }
}

export default function TailoredResumePage() {
  const navigate = useNavigate()
  const { resumeAnalysis, resume, jobDescription } = useOutletContext<DashboardOutletContext>()
  const {
    hydrationStatus,
    activeCareerConversationSessionId,
    careerConversationStatus,
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
    postApplyComparison,
    setPostApplyAnalysis,
    setPostApplyComparison,
    postApplyAnalysisStatus,
    setPostApplyAnalysisStatus,
    jobPreparationId,
  } = useResumeSession()

  const [generateError, setGenerateError] = useState('')
  const [isApplying, setIsApplying] = useState(false)
  const [applyError, setApplyError] = useState('')
  const [revalidationErrors, setRevalidationErrors] = useState<Record<string, string>>({})
  const [exportingFormat, setExportingFormat] = useState<ExportFormat | null>(null)
  const [exportError, setExportError] = useState('')
  const [reanalyzeError, setReanalyzeError] = useState('')
  // Stale-plan recovery (see `recoverFromStalePlan`) is deliberately
  // page-local, transient UI state -- never persisted through
  // ResumeSessionProvider. It only ever describes "what this page is
  // doing right now in response to a 404," which has no meaning across a
  // reload; the frontend orchestration layer owns this end to end, per
  // this feature's explicit "keep the backend stateless" requirement.
  const [isRecovering, setIsRecovering] = useState(false)
  const [recoveryError, setRecoveryError] = useState('')
  // Preview-first workflow state (see docs/features/interactive-tailored-
  // resume.md's "Preview-first workflow"): also page-local/transient, not
  // persisted -- a refresh always lands back on the review stage, never
  // mid-preview, which is the same "no meaning across a reload" reasoning
  // as isRecovering/recoveryError above. The one thing that DOES need to
  // survive a refresh -- which suggestions are already applied -- is
  // derived from the already-persisted `finalTailoredResume`, not from
  // anything declared here (see `appliedIds` below).
  const [isPreviewOpen, setIsPreviewOpen] = useState(false)
  const [isPreviewing, setIsPreviewing] = useState(false)
  const [previewResult, setPreviewResult] = useState<ApplySuggestionsResponse | null>(null)
  // "Preview Changes" and "Apply Now" are the exact same backend call
  // (POST .../apply is a pure, stateless computation from the plan's
  // original structured resume -- see that endpoint's docstring) --
  // only what the frontend *does* with a successful result differs. This
  // ref (not state -- it's read synchronously inside `attemptApply`,
  // never rendered) records which of the two is in flight so one shared
  // function can serve both, including through stale-plan recovery's own
  // retry.
  const pendingIntentRef = useRef<'preview' | 'commit'>('preview')

  // A tailored resume can only be grounded in a completed analysis AND a
  // *completed* Career Conversation (evidence recovery finishes there) --
  // this route is only ever linked to from a CTA once both are true, but
  // a direct/refreshed visit could still land here with one or more
  // missing. Only meaningful once hydration has resolved -- see the
  // hydration gate in the render below, matching CareerConversationPage's
  // identical reasoning.
  const hasContext = resumeAnalysis !== null && resume !== null && jobDescription !== null
  const isConversationComplete =
    activeCareerConversationSessionId !== null && careerConversationStatus === 'complete'

  // Same "close the window a render can't close in time" reasoning as
  // CareerConversationPage's `isBusyRef` -- see that component's
  // docstring. There is deliberately no "generate automatically on
  // mount" effect anywhere on this page: `generate` only ever runs from a
  // user's own click on "Generate Tailoring Plan" below, never as a side
  // effect of navigating here, of refreshing, or of no plan existing yet.
  const isGeneratingRef = useRef(false)
  const isApplyingRef = useRef(false)
  const isReanalyzingRef = useRef(false)

  function closePreview() {
    setIsPreviewOpen(false)
    setPreviewResult(null)
  }

  const generate = useCallback(async () => {
    if (!resume || !jobDescription || !resumeAnalysis || !activeCareerConversationSessionId) return
    if (isGeneratingRef.current) return
    isGeneratingRef.current = true
    setTailoringPlanStatus('generating')
    setGenerateError('')
    try {
      // The full Career Conversation transcript isn't held anywhere in
      // shared state (only its session id is) -- re-fetched here via the
      // same pure-read GET this app already uses for reload-safety (see
      // CareerConversationPage), falling back to the durably persisted
      // copy if the in-memory session itself is gone (see
      // getCareerConversationOrPersisted's docstring).
      const session = await getCareerConversationOrPersisted(
        activeCareerConversationSessionId,
        jobPreparationId,
      )
      const plan = await generateTailoringSuggestions(
        resume.text,
        jobDescription.text,
        resumeAnalysis,
        session,
        tailoringCustomInstructions,
        resume.fileName,
        jobPreparationId,
      )
      setTailoringPlan(plan)
      setTailoringPlanStatus('idle')
      // A fresh plan's suggestion ids don't correspond to whatever was
      // selected/edited/applied against a *previous* plan -- reset all of
      // that so nothing stale lingers pointing at ids that no longer exist.
      setTailoringSelections(
        plan.suggestions.filter((s) => s.selected_by_default).map((s) => s.suggestion_id),
      )
      setTailoringEditedTexts({})
      setFinalTailoredResume(null)
      setTailoringValidationReport(null)
      setTailoringAvailableExportFormats(plan.available_export_formats)
      setTailoringSourceFormat(detectSourceFormatFromFilename(resume.fileName))
      setIsPreviewOpen(false)
      setPreviewResult(null)
      // A fresh plan means a fresh final resume (or none, until applied
      // again) -- any prior post-apply comparison was measuring the
      // *previous* plan's applied resume and no longer describes
      // anything real.
      setPostApplyAnalysis(null)
      setPostApplyComparison(null)
      setPostApplyAnalysisStatus('idle')
      setReanalyzeError('')
    } catch (err) {
      setGenerateError(
        err instanceof ApiError ? err.message : 'An unexpected error occurred. Please try again.',
      )
      setTailoringPlanStatus('error')
    } finally {
      isGeneratingRef.current = false
    }
  }, [
    resume,
    jobDescription,
    resumeAnalysis,
    activeCareerConversationSessionId,
    tailoringCustomInstructions,
    setTailoringPlan,
    setTailoringPlanStatus,
    setTailoringSelections,
    setTailoringEditedTexts,
    setFinalTailoredResume,
    setTailoringValidationReport,
    setTailoringAvailableExportFormats,
    setPostApplyAnalysis,
    setPostApplyComparison,
    setPostApplyAnalysisStatus,
    setTailoringSourceFormat,
    jobPreparationId,
  ])

  // Selecting a suggestion that's mutually exclusive with one already
  // selected (see `TailoringSuggestion.conflicts_with`) auto-deselects the
  // other one, rather than letting the candidate reach an invalid
  // combination that would only 409 once they click Apply -- the card's
  // "Choose only one" note (see `buildConflictSummaries`) explains why a
  // checkbox they didn't touch just unchecked itself.
  function toggleSuggestion(suggestionId: string, selected: boolean) {
    if (!selected) {
      setTailoringSelections(tailoringSelections.filter((id) => id !== suggestionId))
      return
    }
    const suggestion = tailoringPlan?.suggestions.find((s) => s.suggestion_id === suggestionId)
    const conflictIds = new Set(suggestion?.conflicts_with ?? [])
    const withoutConflicts = tailoringSelections.filter((id) => !conflictIds.has(id))
    setTailoringSelections([...withoutConflicts, suggestionId])
  }

  function selectAll() {
    if (!tailoringPlan) return
    setTailoringSelections(tailoringPlan.suggestions.map((s) => s.suggestion_id))
  }

  function clearAll() {
    setTailoringSelections([])
  }

  function setEditedText(suggestionId: string, text: string | null) {
    const next = { ...tailoringEditedTexts }
    if (text === null) {
      delete next[suggestionId]
    } else {
      next[suggestionId] = text
    }
    setTailoringEditedTexts(next)
    // An edit changes what would be revalidated, so a stale revalidation
    // error for this suggestion no longer necessarily applies.
    if (revalidationErrors[suggestionId]) {
      const nextErrors = { ...revalidationErrors }
      delete nextErrors[suggestionId]
      setRevalidationErrors(nextErrors)
    }
  }

  // Runs the actual apply call and routes its result according to
  // `pendingIntentRef`: a 'preview' call never touches the committed
  // `finalTailoredResume` -- it only stores the result for the read-only
  // preview panel to render -- while a 'commit' call is the one and only
  // place `finalTailoredResume` (the actually-applied resume) is written.
  // Throws on failure either way -- callers decide what a failure means
  // (a hard error vs. a recoverable stale-plan 404).
  const attemptApply = useCallback(
    async (planId: string, selections: string[], editedTexts: Record<string, string>) => {
      const result = await applyTailoringSuggestions(planId, selections, editedTexts)
      if (pendingIntentRef.current === 'preview') {
        setPreviewResult(result)
        setIsPreviewOpen(true)
        return
      }
      // Only ever overwritten by a *new* success -- a later failed apply
      // must never clear this, so the last good result stays visible and
      // downloadable (see this feature's docs on why).
      setFinalTailoredResume({
        finalResumeText: result.final_resume_text,
        appliedSuggestionIds: result.applied_suggestion_ids,
      })
      setTailoringValidationReport(result.final_validation)
      setIsPreviewOpen(false)
      setPreviewResult(null)
      // A new commit supersedes whatever final resume any earlier
      // post-apply comparison was measuring -- see docs/features/
      // postapply-analysis-loop.md's "Download requires re-analyzing the
      // *current* final resume" requirement. Re-locking here, on every
      // successful commit (not just the first), is what makes that
      // requirement hold after a second/third phased apply too: without
      // this, a comparison from an earlier phase would keep Download
      // unlocked for a resume that itself was never actually re-analyzed.
      setPostApplyAnalysis(null)
      setPostApplyComparison(null)
      setPostApplyAnalysisStatus('idle')
      setReanalyzeError('')
    },
    [
      setFinalTailoredResume,
      setTailoringValidationReport,
      setPostApplyAnalysis,
      setPostApplyComparison,
      setPostApplyAnalysisStatus,
    ],
  )

  // Shared by both the direct-failure path (handleApply's own catch) and
  // the post-recovery retry's own catch -- a non-404 failure is handled
  // identically either way, so this is written once.
  function classifyAndSetApplyError(err: unknown) {
    if (err instanceof ApiError && err.cause === 'revalidation_failed') {
      const suggestionId = parseRevalidationSuggestionId(err.message)
      if (suggestionId) {
        setRevalidationErrors({ [suggestionId]: err.message })
        return
      }
    }
    setApplyError(
      err instanceof ApiError ? err.message : 'An unexpected error occurred. Please try again.',
    )
  }

  // Apply's stale-plan recovery: the backend's `TailoringPlanStore` is
  // deliberately in-memory only (see `docs/features/
  // interactive-tailored-resume.md`'s "Trust boundary") -- a restart
  // between generating a plan and applying it is expected, recoverable
  // behavior, not a bug, and the backend stays exactly as stateless as
  // before. Everything here is frontend orchestration: regenerate a
  // fresh plan from the same resume/job description/conversation/custom
  // instructions already held in session, remap the previous selections
  // onto it (`remapSelectionsToNewPlan`), and retry the apply the user
  // actually asked for -- automatically, without a second click.
  async function recoverFromStalePlan() {
    // A stale plan invalidates whatever the (now-abandoned) preview call
    // was based on -- always drop back to the review stage first, where
    // the familiar "Refreshing tailoring suggestions…" banner below
    // already handles both intents identically.
    closePreview()
    if (!resume || !jobDescription || !resumeAnalysis || !activeCareerConversationSessionId) {
      // No context left to regenerate from (e.g. the session itself was
      // cleared) -- nothing left to try automatically.
      setRecoveryError(RECOVERY_MESSAGE)
      return
    }

    setApplyError('')
    setRevalidationErrors({})
    setRecoveryError('')
    setIsRecovering(true)

    let newPlan: GenerateSuggestionsResponse
    try {
      const session = await getCareerConversationOrPersisted(
        activeCareerConversationSessionId,
        jobPreparationId,
      )
      newPlan = await generateTailoringSuggestions(
        resume.text,
        jobDescription.text,
        resumeAnalysis,
        session,
        tailoringCustomInstructions,
        resume.fileName,
        jobPreparationId,
      )
    } catch {
      // Regeneration itself failed -- this is the one case the user
      // should see something, per this feature's explicit requirement
      // that only a failed *regeneration* (not the original 404) becomes
      // user-facing.
      setIsRecovering(false)
      setRecoveryError(RECOVERY_MESSAGE)
      return
    }

    const remapped = remapSelectionsToNewPlan(
      tailoringPlan?.suggestions ?? [],
      tailoringSelections,
      tailoringEditedTexts,
      newPlan.suggestions,
    )
    setTailoringPlan(newPlan)
    setTailoringPlanStatus('idle')
    setTailoringSelections(remapped.selections)
    setTailoringEditedTexts(remapped.editedTexts)
    setTailoringAvailableExportFormats(newPlan.available_export_formats)
    setTailoringSourceFormat(detectSourceFormatFromFilename(resume.fileName))
    setIsRecovering(false)

    try {
      await attemptApply(newPlan.plan_id, remapped.selections, remapped.editedTexts)
    } catch (err) {
      // A second failure at this point (even another 404) is treated as
      // a real error -- no further automatic recovery, so this can never
      // loop.
      classifyAndSetApplyError(err)
    }
  }

  // Drives both "Preview Changes" (intent: 'preview') and "Apply Now"
  // (intent: 'commit') -- see `attemptApply`'s docstring for why one
  // function can serve both. A non-404 failure of a 'commit' call closes
  // the preview panel so the failure is shown where a candidate would
  // look for it (the per-suggestion revalidation note or the review
  // stage's error banner) rather than leaving them stranded in a preview
  // that no longer reflects reality; `finalTailoredResume` from any
  // earlier successful apply is never touched by a failed attempt either
  // way, so the last good result stays visible and downloadable.
  const runApplyFlow = useCallback(
    async (intent: 'preview' | 'commit') => {
      if (!tailoringPlan) return
      if (isApplyingRef.current) return
      isApplyingRef.current = true
      pendingIntentRef.current = intent
      if (intent === 'preview') setIsPreviewing(true)
      else setIsApplying(true)
      setApplyError('')
      setRevalidationErrors({})
      setRecoveryError('')
      try {
        await attemptApply(tailoringPlan.plan_id, tailoringSelections, tailoringEditedTexts)
      } catch (err) {
        if (err instanceof ApiError && err.cause === 'not_found') {
          await recoverFromStalePlan()
        } else {
          if (intent === 'commit') closePreview()
          classifyAndSetApplyError(err)
        }
      } finally {
        setIsApplying(false)
        setIsPreviewing(false)
        isApplyingRef.current = false
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [tailoringPlan, tailoringSelections, tailoringEditedTexts, attemptApply],
  )

  function revertAppliedSuggestion(suggestionId: string) {
    setTailoringSelections(tailoringSelections.filter((id) => id !== suggestionId))
  }

  const handleDownload = useCallback(
    async (format: ExportFormat) => {
      if (!tailoringPlan) return
      setExportingFormat(format)
      setExportError('')
      try {
        const file = await exportTailoredResume(
          tailoringPlan.plan_id,
          tailoringSelections,
          tailoringEditedTexts,
          format,
          candidateFilenameBase(resume?.fileName ?? null),
        )
        // A failed export must never clear finalTailoredResume -- the
        // preview above stays visible either way, this only affects the
        // download panel's own inline error.
        downloadExportedFile(file)
      } catch (err) {
        setExportError(
          err instanceof ApiError ? err.message : 'An unexpected error occurred. Please try again.',
        )
      } finally {
        setExportingFormat(null)
      }
    },
    [tailoringPlan, tailoringSelections, tailoringEditedTexts, resume],
  )

  // The Post-Apply Analysis Loop (see
  // docs/features/postapply-analysis-loop.md): re-analyzes the resume
  // that the current selection/edits would produce against the same job
  // description the plan was generated against (the backend re-derives
  // both server-side -- see reanalyzeAfterApply's docs), and
  // deterministically compares it against `resumeAnalysis`, the
  // original analysis, which this never overwrites. Mirrors
  // handleDownload's own choice to use the *current* tailoringSelections/
  // tailoringEditedTexts rather than only `finalTailoredResume`'s
  // last-applied snapshot, for the same reason: both describe "what the
  // review stage is configured to produce right now."
  //
  // On failure, only `reanalyzeError`/`postApplyAnalysisStatus` change --
  // `postApplyComparison` is never cleared or fabricated, so the last
  // real comparison (if any) stays visible exactly like a failed
  // export/apply never clears its own last good result.
  const handleReanalyze = useCallback(async () => {
    if (!tailoringPlan || !resumeAnalysis) return
    if (isReanalyzingRef.current) return
    isReanalyzingRef.current = true
    setPostApplyAnalysisStatus('reanalyzing')
    setReanalyzeError('')
    try {
      const result = await reanalyzeAfterApply(
        tailoringPlan.plan_id,
        resumeAnalysis,
        tailoringSelections,
        tailoringEditedTexts,
      )
      setPostApplyAnalysis(result.after_analysis)
      setPostApplyComparison(result.comparison)
      setPostApplyAnalysisStatus('idle')
    } catch (err) {
      setReanalyzeError(
        err instanceof ApiError ? err.message : 'An unexpected error occurred. Please try again.',
      )
      setPostApplyAnalysisStatus('error')
    } finally {
      isReanalyzingRef.current = false
    }
  }, [
    tailoringPlan,
    resumeAnalysis,
    tailoringSelections,
    tailoringEditedTexts,
    setPostApplyAnalysis,
    setPostApplyComparison,
    setPostApplyAnalysisStatus,
  ])

  const selectedCount = tailoringSelections.length
  const totalCount = tailoringPlan?.suggestions.length ?? 0
  const recommendedCount = useMemo(
    () => tailoringPlan?.suggestions.filter((s) => s.selected_by_default).length ?? 0,
    [tailoringPlan],
  )
  // Precomputed once for the whole list (not per-card): the section-name
  // map needs every suggestion's evidence to fill in a heading a given
  // suggestion doesn't itself cite resume evidence for -- see
  // suggestionPresentation.ts's `buildSectionNameMap`.
  const sectionNames = useMemo(
    () => buildSectionNameMap(tailoringPlan?.suggestions ?? []),
    [tailoringPlan],
  )
  const sectionFallbackOrdinals = useMemo(
    () => buildSectionFallbackOrdinals(tailoringPlan?.suggestions ?? []),
    [tailoringPlan],
  )
  const suggestionGroups = useMemo(
    () =>
      groupSuggestionsBySection(
        tailoringPlan?.suggestions ?? [],
        sectionNames,
        sectionFallbackOrdinals,
      ),
    [tailoringPlan, sectionNames, sectionFallbackOrdinals],
  )
  const conflictSummaries = useMemo(
    () => buildConflictSummaries(tailoringPlan?.suggestions ?? []),
    [tailoringPlan],
  )
  // The set of suggestion ids actually committed by the last successful
  // "Apply Now" -- deliberately *not* separate page state: since apply is
  // a pure recomputation from the plan's original structured resume (see
  // attemptApply's docstring), `finalTailoredResume.appliedSuggestionIds`
  // is always already the full, current, phased-apply history, and it's
  // already persisted through `ResumeSessionProvider` for free. A
  // suggestion only counts as "Applied" in the UI while it's *also* still
  // selected -- Undo (`revertAppliedSuggestion`) removes it from
  // `tailoringSelections`, which is enough to make it look pending again
  // immediately, even before the next Preview/Apply catches the resume
  // text itself up.
  const appliedIds = useMemo(
    () => new Set(finalTailoredResume?.appliedSuggestionIds ?? []),
    [finalTailoredResume],
  )

  function applyRecommendedSelection() {
    if (!tailoringPlan) return
    setTailoringSelections(
      tailoringPlan.suggestions.filter((s) => s.selected_by_default).map((s) => s.suggestion_id),
    )
  }

  const suggestionsListRef = useRef<HTMLDivElement>(null)
  function scrollToSuggestions() {
    suggestionsListRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  const availableFormats = useMemo(
    () => tailoringAvailableExportFormats,
    [tailoringAvailableExportFormats],
  )

  return (
    <>
      <TopHeader
        title="Tailored Resume"
        subtitle="Small, evidence-backed edits you review and approve -- never an automatic rewrite"
      />

      <div className="p-8">
        {hydrationStatus !== 'hydrated' ? (
          <ConversationLoadingState message="Restoring your session…" />
        ) : !hasContext ? (
          <div className="flex flex-col items-center gap-4 rounded-2xl border border-dashed border-gray-300 bg-white px-8 py-16 text-center">
            <p className="text-sm text-gray-500">
              Complete a resume analysis first to generate tailoring suggestions.
            </p>
            <Button variant="solid" onClick={() => navigate('/')}>
              Go to Dashboard
            </Button>
          </div>
        ) : !isConversationComplete ? (
          <div className="flex flex-col items-center gap-4 rounded-2xl border border-dashed border-gray-300 bg-white px-8 py-16 text-center">
            <p className="text-sm text-gray-500">
              Complete a Career Conversation first -- suggestions are grounded only in evidence
              from your original resume and what you share there.
            </p>
            <Button variant="solid" onClick={() => navigate('/career-conversation')}>
              Start Career Conversation
            </Button>
          </div>
        ) : (
          <div className="mx-auto max-w-3xl space-y-6">
            {/* Stage 1: Generate Tailoring Plan */}
            {tailoringPlanStatus === 'generating' ? (
              <ConversationLoadingState message="Generating tailoring suggestions…" />
            ) : tailoringPlanStatus === 'error' && !tailoringPlan ? (
              <TailoringErrorState message={generateError} onRetry={generate} />
            ) : !tailoringPlan ? (
              <div className="flex flex-col items-center gap-4 rounded-2xl border border-dashed border-gray-300 bg-white px-8 py-16 text-center">
                <p className="max-w-md text-sm text-gray-500">
                  Nothing about your resume changes yet. We'll suggest small, evidence-backed edits
                  for you to review -- you decide which ones to apply.
                </p>
                <Button variant="solid" icon={<Wand2 size={16} />} onClick={generate}>
                  Generate Tailoring Plan
                </Button>
              </div>
            ) : isPreviewOpen && previewResult ? (
              // Stage: Preview Changes -- a focused, read-only look at what
              // the current selection would produce, deliberately the only
              // thing on screen (see requirement "do not overload the page
              // with too much text at once"). Selection can't change here;
              // "Back to Suggestions" is the only way out other than
              // committing.
              <TailoringPreviewPanel
                includedSuggestions={tailoringPlan.suggestions.filter((s) =>
                  tailoringSelections.includes(s.suggestion_id),
                )}
                editedTexts={tailoringEditedTexts}
                alreadyAppliedIds={appliedIds}
                isApplying={isApplying || isRecovering}
                applyError={applyError || null}
                onBack={closePreview}
                onApplyNow={() => runApplyFlow('commit')}
              />
            ) : (
              <>
                <TailoringPlanSummaryHeader
                  totalCount={totalCount}
                  recommendedCount={recommendedCount}
                  onApplyRecommended={applyRecommendedSelection}
                  onCustomize={scrollToSuggestions}
                />

                <div className="flex items-center justify-between gap-4">
                  <div>
                    <h2 className="font-semibold text-gray-900">Review Suggestions</h2>
                    <p className="mt-1 text-sm text-gray-500">
                      {selectedCount} of {totalCount} selected
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <Button variant="outline" icon={<CheckSquare size={14} />} onClick={selectAll}>
                      Select All
                    </Button>
                    <Button variant="outline" icon={<Square size={14} />} onClick={clearAll}>
                      Clear All
                    </Button>
                    <Button variant="outline" icon={<RotateCw size={14} />} onClick={generate}>
                      Regenerate
                    </Button>
                  </div>
                </div>

                {tailoringPlan.suggestions.length === 0 ? (
                  <p className="rounded-2xl border border-dashed border-gray-300 bg-white px-6 py-10 text-center text-sm text-gray-500">
                    No suggestions were proposed for this resume and job description.
                  </p>
                ) : (
                  <div ref={suggestionsListRef} className="space-y-6">
                    {suggestionGroups.map((group) => (
                      <div key={group.sectionId}>
                        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-400">
                          {group.sectionName}
                        </h3>
                        <ul className="space-y-3">
                          {group.suggestions.map((suggestion) => (
                            <TailoringSuggestionCard
                              key={suggestion.suggestion_id}
                              suggestion={suggestion}
                              sectionName={group.sectionName}
                              accepted={tailoringSelections.includes(suggestion.suggestion_id)}
                              onToggleAccepted={(accepted) =>
                                toggleSuggestion(suggestion.suggestion_id, accepted)
                              }
                              editedText={tailoringEditedTexts[suggestion.suggestion_id] ?? null}
                              onEditedTextChange={(text) =>
                                setEditedText(suggestion.suggestion_id, text)
                              }
                              revalidationError={revalidationErrors[suggestion.suggestion_id] ?? null}
                              conflictSummaries={
                                conflictSummaries.get(suggestion.suggestion_id) ?? []
                              }
                              isApplied={
                                appliedIds.has(suggestion.suggestion_id) &&
                                tailoringSelections.includes(suggestion.suggestion_id)
                              }
                              onRevertApplied={() => revertAppliedSuggestion(suggestion.suggestion_id)}
                            />
                          ))}
                        </ul>
                      </div>
                    ))}
                  </div>
                )}

                {/* Stage 3: Custom Instructions */}
                <div className="rounded-2xl border border-gray-200 bg-white p-6">
                  <h3 className="font-semibold text-gray-900">Anything else you want to change?</h3>
                  <p className="mt-1 text-sm text-gray-500">
                    Instructions control style and priorities -- they can never add experience,
                    skills, or claims that aren't already supported by your resume or conversation.
                    For example: "Keep the resume under two pages," "Make the summary more
                    engineering-focused," "Preserve all Adobe experience," "Do not change
                    employment dates."
                  </p>
                  <textarea
                    value={tailoringCustomInstructions}
                    onChange={(event) => setTailoringCustomInstructions(event.target.value)}
                    rows={3}
                    placeholder="Optional instructions for the next plan you generate…"
                    className="mt-3 w-full rounded-xl border border-gray-200 p-3 text-sm text-gray-800 focus:border-indigo-400 focus:outline-none"
                  />
                  <p className="mt-2 text-xs text-gray-400">
                    Applies the next time you generate or regenerate a plan.
                  </p>
                </div>

                {/* Stage 2: Preview Changes -- the only way into applying;
                    there is no direct "apply" action from this stage
                    anymore (see this feature's "Preview-first workflow"
                    docs for why). */}
                <div className="rounded-2xl border border-gray-200 bg-white p-6">
                  <div className="flex flex-wrap items-center justify-between gap-4">
                    <div>
                      <h3 className="font-semibold text-gray-900">Preview Changes</h3>
                      <p className="mt-1 text-sm text-gray-500">
                        See exactly what your resume will look like before anything is applied.
                      </p>
                    </div>
                    <Button
                      variant="solid"
                      icon={<Wand2 size={16} />}
                      disabled={selectedCount === 0 || isPreviewing || isApplying}
                      onClick={() => runApplyFlow('preview')}
                    >
                      {isRecovering
                        ? 'Applying…'
                        : isPreviewing
                          ? 'Loading preview…'
                          : 'Preview Changes'}
                    </Button>
                  </div>
                  {isRecovering && (
                    <p aria-live="polite" className="mt-4 text-sm text-gray-500">
                      Refreshing tailoring suggestions…
                    </p>
                  )}
                  {!isRecovering && recoveryError && (
                    <div className="mt-4 rounded-xl border border-amber-100 bg-amber-50/60 p-4">
                      <p className="whitespace-pre-line text-sm text-amber-700">{recoveryError}</p>
                      <Button
                        variant="outline"
                        icon={<RotateCw size={14} />}
                        className="mt-3"
                        onClick={recoverFromStalePlan}
                      >
                        Regenerate Suggestions
                      </Button>
                    </div>
                  )}
                  {!isRecovering && !recoveryError && applyError && (
                    <div className="mt-4 rounded-xl border border-rose-100 bg-rose-50/60 p-4">
                      <p className="text-sm text-rose-600">{applyError}</p>
                    </div>
                  )}
                </div>

                {/* Stage 4: Final Resume -> Re-analyze -> Compare -> Download.
                    A strict, enforced order (see docs/features/postapply-
                    analysis-loop.md's "Download is gated on re-analysis"):
                    the updated resume is shown immediately, but Download
                    itself does not render at all until a real comparison
                    exists for *this* final resume -- there is no disabled/
                    ghost download button, it simply isn't part of the page
                    yet. `attemptApply` resets `postApplyComparison` to null
                    on every new commit, so a second/third phased apply
                    re-locks Download until re-analyzed again, the same way
                    the first apply does. */}
                {finalTailoredResume && (
                  <>
                    <TailoringFinalResumeCard
                      finalResumeText={finalTailoredResume.finalResumeText}
                      appliedSuggestionIds={finalTailoredResume.appliedSuggestionIds}
                      allSuggestions={tailoringPlan.suggestions}
                      validationReport={tailoringValidationReport}
                      sectionNames={sectionNames}
                      sectionFallbackOrdinals={sectionFallbackOrdinals}
                      onContinueEditing={scrollToSuggestions}
                    />

                    {/* Stage 5: Post-Apply Analysis Loop -- see
                        docs/features/postapply-analysis-loop.md. While a
                        re-analysis is in flight, this replaces itself with
                        a section-level loading state (the same pattern
                        "Generating tailoring suggestions…" uses above) --
                        real re-analysis calls can take well over a minute,
                        so a mere button-label swap is not "meaningful
                        progress" for a wait that long. */}
                    {postApplyAnalysisStatus === 'reanalyzing' ? (
                      <ConversationLoadingState message="Re-analyzing your updated resume against the job description…" />
                    ) : (
                      <div className="rounded-2xl border border-gray-200 bg-white p-6">
                        <div className="flex flex-wrap items-center justify-between gap-4">
                          <div>
                            <h3 className="font-semibold text-gray-900">How much did this help?</h3>
                            <p className="mt-1 text-sm text-gray-500">
                              Re-analyze your updated resume against the same job description to see
                              whether the applied changes actually improved your match --
                              {postApplyComparison
                                ? ' your download stays available below.'
                                : ' this unlocks your download.'}
                            </p>
                          </div>
                          <Button
                            variant="outline"
                            icon={<BarChart2 size={16} />}
                            onClick={handleReanalyze}
                          >
                            {postApplyComparison ? 'Re-analyze Again' : 'Re-analyze & Compare'}
                          </Button>
                        </div>
                        {postApplyAnalysisStatus === 'error' && reanalyzeError && (
                          <div className="mt-4 rounded-xl border border-amber-100 bg-amber-50/60 p-4">
                            <p className="text-sm text-amber-700">
                              Your resume changes were applied successfully, but re-analysis could
                              not be completed, so improvement could not be measured: {reanalyzeError}
                            </p>
                          </div>
                        )}
                      </div>
                    )}

                    {postApplyComparison && (
                      <>
                        <PostApplyComparisonCard comparison={postApplyComparison} />
                        {availableFormats.length > 0 && (
                          <TailoringDownloadPanel
                            availableFormats={availableFormats}
                            defaultFormat={tailoringPlan.default_export_format}
                            sourceFormat={tailoringSourceFormat}
                            exportingFormat={exportingFormat}
                            exportError={exportError || null}
                            onDownload={handleDownload}
                          />
                        )}
                      </>
                    )}
                  </>
                )}
              </>
            )}
          </div>
        )}
      </div>
    </>
  )
}
