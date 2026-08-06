import { useCallback, useMemo, useRef, useState } from 'react'
import { CheckSquare, RotateCw, Square, Wand2 } from 'lucide-react'
import { useNavigate, useOutletContext } from 'react-router-dom'
import TopHeader from '../components/TopHeader'
import Button from '../components/Button'
import ConversationLoadingState from '../components/ConversationLoadingState'
import TailoringErrorState from '../components/TailoringErrorState'
import TailoringSuggestionCard from '../components/TailoringSuggestionCard'
import TailoringPlanSummaryHeader from '../components/TailoringPlanSummaryHeader'
import TailoringFinalResumeCard from '../components/TailoringFinalResumeCard'
import TailoringDownloadPanel from '../components/TailoringDownloadPanel'
import { getCareerConversation } from '../lib/careerConversationApi'
import {
  buildSectionFallbackOrdinals,
  buildSectionNameMap,
  getReadableSectionName,
} from '../lib/suggestionPresentation'
import {
  applyTailoringSuggestions,
  downloadExportedFile,
  exportTailoredResume,
  generateTailoringSuggestions,
} from '../lib/tailoringSuggestionsApi'
import { ApiError } from '../lib/api'
import { candidateFilenameBase, detectSourceFormatFromFilename } from '../lib/sourceFormat'
import { useResumeSession } from '../session/ResumeSessionContext'
import type { DashboardOutletContext } from '../layouts/DashboardLayout'
import type { ExportFormat } from '../data/tailoringSuggestionsTypes'

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
  } = useResumeSession()

  const [generateError, setGenerateError] = useState('')
  const [isApplying, setIsApplying] = useState(false)
  const [applyError, setApplyError] = useState('')
  const [revalidationErrors, setRevalidationErrors] = useState<Record<string, string>>({})
  const [exportingFormat, setExportingFormat] = useState<ExportFormat | null>(null)
  const [exportError, setExportError] = useState('')

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
      // CareerConversationPage).
      const session = await getCareerConversation(activeCareerConversationSessionId)
      const plan = await generateTailoringSuggestions(
        resume.text,
        jobDescription.text,
        resumeAnalysis,
        session,
        tailoringCustomInstructions,
        resume.fileName,
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
    setTailoringSourceFormat,
  ])

  function toggleSuggestion(suggestionId: string, selected: boolean) {
    setTailoringSelections(
      selected
        ? [...tailoringSelections, suggestionId]
        : tailoringSelections.filter((id) => id !== suggestionId),
    )
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

  const handleApply = useCallback(async () => {
    if (!tailoringPlan) return
    if (isApplyingRef.current) return
    isApplyingRef.current = true
    setIsApplying(true)
    setApplyError('')
    setRevalidationErrors({})
    try {
      const result = await applyTailoringSuggestions(
        tailoringPlan.plan_id,
        tailoringSelections,
        tailoringEditedTexts,
      )
      // Only ever overwritten by a *new* success -- a later failed apply
      // must never clear this, so the last good result stays visible and
      // downloadable (see this feature's docs on why).
      setFinalTailoredResume({
        finalResumeText: result.final_resume_text,
        appliedSuggestionIds: result.applied_suggestion_ids,
      })
      setTailoringValidationReport(result.final_validation)
    } catch (err) {
      if (err instanceof ApiError && err.cause === 'revalidation_failed') {
        const suggestionId = parseRevalidationSuggestionId(err.message)
        if (suggestionId) {
          setRevalidationErrors({ [suggestionId]: err.message })
        } else {
          setApplyError(err.message)
        }
      } else {
        setApplyError(
          err instanceof ApiError ? err.message : 'An unexpected error occurred. Please try again.',
        )
      }
    } finally {
      setIsApplying(false)
      isApplyingRef.current = false
    }
  }, [tailoringPlan, tailoringSelections, tailoringEditedTexts, setFinalTailoredResume, setTailoringValidationReport])

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

  function applyRecommendedSelection() {
    if (!tailoringPlan) return
    setTailoringSelections(
      tailoringPlan.suggestions.filter((s) => s.selected_by_default).map((s) => s.suggestion_id),
    )
  }

  const suggestionsListRef = useRef<HTMLUListElement>(null)
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
                  <ul ref={suggestionsListRef} className="space-y-3">
                    {tailoringPlan.suggestions.map((suggestion) => (
                      <TailoringSuggestionCard
                        key={suggestion.suggestion_id}
                        suggestion={suggestion}
                        sectionName={getReadableSectionName(
                          suggestion,
                          sectionNames,
                          sectionFallbackOrdinals,
                        )}
                        accepted={tailoringSelections.includes(suggestion.suggestion_id)}
                        onToggleAccepted={(accepted) =>
                          toggleSuggestion(suggestion.suggestion_id, accepted)
                        }
                        editedText={tailoringEditedTexts[suggestion.suggestion_id] ?? null}
                        onEditedTextChange={(text) => setEditedText(suggestion.suggestion_id, text)}
                        revalidationError={revalidationErrors[suggestion.suggestion_id] ?? null}
                      />
                    ))}
                  </ul>
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

                {/* Stage 4: Apply Selected Changes */}
                <div className="rounded-2xl border border-gray-200 bg-white p-6">
                  <div className="flex flex-wrap items-center justify-between gap-4">
                    <div>
                      <h3 className="font-semibold text-gray-900">Apply Selected Changes</h3>
                      <p className="mt-1 text-sm text-gray-500">
                        Only the suggestions you selected above will be applied. Nothing else
                        changes.
                      </p>
                    </div>
                    <Button
                      variant="solid"
                      icon={<Wand2 size={16} />}
                      disabled={selectedCount === 0 || isApplying}
                      onClick={handleApply}
                    >
                      {isApplying ? 'Applying…' : 'Apply Selected Changes'}
                    </Button>
                  </div>
                  {applyError && (
                    <div className="mt-4 rounded-xl border border-rose-100 bg-rose-50/60 p-4">
                      <p className="text-sm text-rose-600">{applyError}</p>
                    </div>
                  )}
                </div>

                {/* Stage 5: Preview and Download */}
                {finalTailoredResume && tailoringValidationReport && (
                  <>
                    <TailoringFinalResumeCard
                      finalResumeText={finalTailoredResume.finalResumeText}
                      appliedSuggestionIds={finalTailoredResume.appliedSuggestionIds}
                      allSuggestions={tailoringPlan.suggestions}
                      validationReport={tailoringValidationReport}
                      sectionNames={sectionNames}
                      sectionFallbackOrdinals={sectionFallbackOrdinals}
                    />
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
          </div>
        )}
      </div>
    </>
  )
}
