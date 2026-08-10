import { useMemo, useState } from 'react'
import { ArrowLeft, Check, Wand2 } from 'lucide-react'
import Badge from './Badge'
import Button from './Button'
import SideBySideDiff from './SideBySideDiff'
import { buildSuggestionDiffHunks } from '../lib/resumeSectionDiff'
import {
  buildSectionFallbackOrdinals,
  buildSectionNameMap,
  groupSuggestionsBySection,
  summarizeSuggestionChange,
} from '../lib/suggestionPresentation'
import type { TailoringSuggestion } from '../data/tailoringSuggestionsTypes'

interface TailoringPreviewPanelProps {
  // Every suggestion included in this preview's selection, so the panel
  // can show "what's included" without the candidate having to cross-
  // reference the review list from memory, AND so the diff itself can be
  // built directly from each suggestion's own current_text/suggested_text
  // -- see this component's own docstring for why that replaced diffing
  // the assembled before/after resume text.
  includedSuggestions: TailoringSuggestion[]
  // User-customized replacement text, keyed by suggestion_id -- mirrors
  // TailoredResumePage's `tailoringEditedTexts` exactly, so the preview
  // always diffs against what Apply Now will actually send, the same way
  // TailoringSuggestionCard's own per-suggestion comparator already does.
  editedTexts: Record<string, string>
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
//
// The diff is built directly from each included suggestion's own
// `current_text`/`suggested_text` (via `buildSuggestionDiffHunks`, the
// exact same function TailoringSuggestionCard's own per-suggestion
// comparator already uses), grouped by section via `target_section_id`
// (via `suggestionPresentation.ts`'s `groupSuggestionsBySection` -- the
// same grouping the suggestion review list itself uses). This
// deliberately does NOT diff the assembled original resume text against
// the assembled final resume text: those are two independently-formatted
// blobs (the original is whatever the candidate uploaded/pasted verbatim;
// the final text is the backend's own re-rendering), and matching
// section headings between them by exact string equality turned out to
// be fragile in practice -- a resume whose extracted text didn't line up
// with the backend's rendering (e.g. line breaks lost during PDF/DOCX
// extraction) made every section look "fully added," with no original
// content shown at all, defeating the entire point of a diff. Building
// the diff from suggestions instead sidesteps that completely: a
// suggestion's `current_text`/`suggested_text` are exact, backend-tracked
// values with no re-derivation involved, so the diff is precise
// regardless of how the surrounding document happens to be formatted.
export default function TailoringPreviewPanel({
  includedSuggestions,
  editedTexts,
  alreadyAppliedIds,
  isApplying,
  applyError,
  onBack,
  onApplyNow,
}: TailoringPreviewPanelProps) {
  const sectionGroups = useMemo(() => {
    const sectionNames = buildSectionNameMap(includedSuggestions)
    const sectionFallbackOrdinals = buildSectionFallbackOrdinals(includedSuggestions)
    return groupSuggestionsBySection(includedSuggestions, sectionNames, sectionFallbackOrdinals).map(
      (group) => ({
        ...group,
        hunks: group.suggestions.flatMap((suggestion) =>
          buildSuggestionDiffHunks(
            suggestion.current_text,
            editedTexts[suggestion.suggestion_id] ?? suggestion.suggested_text,
          ),
        ),
      }),
    )
  }, [includedSuggestions, editedTexts])

  const [activeIndex, setActiveIndex] = useState(0)
  const activeSection = sectionGroups[Math.min(activeIndex, sectionGroups.length - 1)]

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
          Sections changed ({sectionGroups.length})
        </p>
        <div className="mt-3 flex flex-wrap gap-2">
          {sectionGroups.map((section, index) => (
            <button
              key={`${section.sectionId}-${index}`}
              type="button"
              onClick={() => setActiveIndex(index)}
              className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-semibold transition-colors ${
                index === activeIndex
                  ? 'border-indigo-600 bg-indigo-600 text-white'
                  : 'border-indigo-200 bg-indigo-50 text-indigo-700 hover:bg-indigo-100'
              }`}
            >
              {section.sectionName}
              <Check size={12} aria-hidden="true" />
            </button>
          ))}
        </div>

        {activeSection && (
          <div className="mt-4">
            <h3 className="text-sm font-semibold text-gray-900">{activeSection.sectionName}</h3>
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
