import { useMemo, useState } from 'react'
import { ArrowLeft, Check, Wand2 } from 'lucide-react'
import Badge from './Badge'
import Button from './Button'
import SideBySideDiff from './SideBySideDiff'
import { buildSectionDiffs } from '../lib/resumeSectionDiff'
import { summarizeSuggestionChange } from '../lib/suggestionPresentation'
import type { TailoringSuggestion } from '../data/tailoringSuggestionsTypes'

interface TailoringPreviewPanelProps {
  // The resume text before this preview's selection was applied, and the
  // previewed (not-yet-committed) result -- both plain text, diffed
  // section by section purely for display (see resumeSectionDiff.ts).
  originalResumeText: string
  previewResumeText: string
  // Every suggestion included in this preview's selection, so the panel
  // can show "what's included" without the candidate having to cross-
  // reference the review list from memory. `alreadyAppliedIds` labels the
  // ones that were committed in an earlier phase, distinct from ones newly
  // selected in this phase -- see this feature's "phased application" docs.
  includedSuggestions: TailoringSuggestion[]
  alreadyAppliedIds: Set<string>
  isApplying: boolean
  applyError: string | null
  onBack: () => void
  onApplyNow: () => void
}

// Stage 2 of the preview-first workflow: a read-only, GitHub-diff-style
// look at what the *currently selected* suggestions would produce, shown
// before anything is actually committed. Deliberately offers no way to
// change the selection here -- the candidate goes "Back to Suggestions" to
// do that, then previews again; keeping this panel read-only means the
// diff on screen can never silently drift out of sync with what "Apply
// Now" is about to commit.
export default function TailoringPreviewPanel({
  originalResumeText,
  previewResumeText,
  includedSuggestions,
  alreadyAppliedIds,
  isApplying,
  applyError,
  onBack,
  onApplyNow,
}: TailoringPreviewPanelProps) {
  const sections = useMemo(
    () => buildSectionDiffs(originalResumeText, previewResumeText),
    [originalResumeText, previewResumeText],
  )
  const firstChangedIndex = sections.findIndex((s) => s.isChanged)
  const [activeIndex, setActiveIndex] = useState(Math.max(firstChangedIndex, 0))
  const activeSection = sections[activeIndex]

  const newlyIncluded = includedSuggestions.filter((s) => !alreadyAppliedIds.has(s.suggestion_id))
  const previouslyApplied = includedSuggestions.filter((s) => alreadyAppliedIds.has(s.suggestion_id))

  return (
    <div className="space-y-6">
      <div className="rounded-2xl border border-gray-200 bg-white p-6">
        <h2 className="font-semibold text-gray-900">Preview Changes</h2>
        <p className="mt-1 text-sm text-gray-500">
          This is what your resume will look like if you apply now. Nothing has been changed yet
          -- go back to adjust your selection, or apply to confirm.
        </p>

        {includedSuggestions.length > 0 && (
          <div className="mt-4 space-y-2">
            {newlyIncluded.length > 0 && (
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-xs font-semibold uppercase tracking-wide text-gray-400">
                  New in this preview
                </span>
                {newlyIncluded.map((suggestion) => (
                  <Badge key={suggestion.suggestion_id} variant="indigo">
                    {summarizeSuggestionChange(suggestion)}
                  </Badge>
                ))}
              </div>
            )}
            {previouslyApplied.length > 0 && (
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-xs font-semibold uppercase tracking-wide text-gray-400">
                  Already applied
                </span>
                {previouslyApplied.map((suggestion) => (
                  <Badge key={suggestion.suggestion_id} variant="gray">
                    {summarizeSuggestionChange(suggestion)}
                  </Badge>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      <div className="rounded-2xl border border-gray-200 bg-white p-6">
        <p className="text-xs font-semibold uppercase tracking-wide text-gray-400">
          Sections ({sections.filter((s) => s.isChanged).length} changed of {sections.length})
        </p>
        <div className="mt-3 flex flex-wrap gap-2">
          {sections.map((section, index) => (
            <button
              key={`${section.sectionId}-${index}`}
              type="button"
              onClick={() => setActiveIndex(index)}
              className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-semibold transition-colors ${
                index === activeIndex
                  ? 'border-indigo-600 bg-indigo-600 text-white'
                  : section.isChanged
                    ? 'border-indigo-200 bg-indigo-50 text-indigo-700 hover:bg-indigo-100'
                    : 'border-gray-200 bg-white text-gray-500 hover:bg-gray-50'
              }`}
            >
              {section.sectionTitle}
              {section.isChanged && <Check size={12} aria-hidden="true" />}
            </button>
          ))}
        </div>

        {activeSection && (
          <div className="mt-4">
            <h3 className="text-sm font-semibold text-gray-900">{activeSection.sectionTitle}</h3>
            <div className="mt-3 max-h-96 overflow-y-auto">
              <SideBySideDiff
                hunks={activeSection.hunks}
                emptyMessage="No changes in this section."
              />
            </div>
          </div>
        )}
      </div>

      <div className="flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-gray-200 bg-white p-6">
        <Button variant="outline" icon={<ArrowLeft size={16} />} onClick={onBack} disabled={isApplying}>
          Back to Suggestions
        </Button>
        <Button variant="solid" icon={<Wand2 size={16} />} onClick={onApplyNow} disabled={isApplying}>
          {isApplying ? 'Applying…' : 'Apply Now'}
        </Button>
      </div>

      {applyError && (
        <div className="rounded-xl border border-rose-100 bg-rose-50/60 p-4">
          <p className="text-sm text-rose-600">{applyError}</p>
        </div>
      )}
    </div>
  )
}
