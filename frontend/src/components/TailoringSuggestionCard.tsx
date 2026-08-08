import { useMemo, useState, type ReactNode } from 'react'
import { ChevronDown, ChevronRight, Star } from 'lucide-react'
import Badge from './Badge'
import Button from './Button'
import SideBySideDiff from './SideBySideDiff'
import { buildSuggestionDiffHunks } from '../lib/resumeSectionDiff'
import type { TailoringSuggestion } from '../data/tailoringSuggestionsTypes'
import {
  getImpactLevel,
  groupEvidenceSources,
  IMPACT_LABELS,
  IMPACT_STAR_COUNT,
  OPERATION_ACTION_LABELS,
  summarizeSuggestionChange,
  type ImpactLevel,
} from '../lib/suggestionPresentation'

const IMPACT_BADGE_VARIANT: Record<ImpactLevel, 'green' | 'amber' | 'gray'> = {
  high: 'green',
  medium: 'amber',
  low: 'gray',
}

function ImpactRating({ level }: { level: ImpactLevel }) {
  const filled = IMPACT_STAR_COUNT[level]
  return (
    <span className="flex shrink-0 flex-col items-end gap-1">
      <span className="flex" aria-hidden="true">
        {Array.from({ length: 5 }, (_, i) => (
          <Star
            key={i}
            size={14}
            className={i < filled ? 'fill-current text-amber-400' : 'text-gray-200'}
          />
        ))}
      </span>
      <Badge variant={IMPACT_BADGE_VARIANT[level]}>{IMPACT_LABELS[level]}</Badge>
    </span>
  )
}

// One collapsed-by-default disclosure row, shared by Evidence, Preview
// Change, and View Current Resume Text -- all three are the same
// interaction pattern (a small text link that expands a panel), so this
// is written once rather than three times. Nothing is ever expanded by
// default; a candidate scanning 15 cards never has to scroll past a
// panel they didn't ask to see.
function DisclosureRow({
  label,
  isOpen,
  onToggle,
  children,
}: {
  label: string
  isOpen: boolean
  onToggle: () => void
  children: ReactNode
}) {
  return (
    <div>
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={isOpen}
        className="inline-flex items-center gap-1 text-xs font-semibold text-gray-500 hover:text-gray-700"
      >
        {isOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        {label}
      </button>
      {isOpen && <div className="mt-2 rounded-lg border border-gray-100 bg-gray-50 p-3">{children}</div>}
    </div>
  )
}

interface TailoringSuggestionCardProps {
  suggestion: TailoringSuggestion
  // A human-readable heading ("Core Skills," "Adobe Experience") --
  // precomputed once for the whole suggestion list by the parent (see
  // TailoredResumePage/suggestionPresentation.ts) rather than derived
  // per-card, since the mapping needs the *whole* plan's evidence to
  // fill in a section a given suggestion doesn't itself cite resume
  // evidence for. Never the raw `target_section_id`.
  sectionName: string
  accepted: boolean
  onToggleAccepted: (accepted: boolean) => void
  // `null` when the user hasn't edited this suggestion's text -- the
  // original, model-generated `suggestion.suggested_text` is what's
  // actually shown/applied in that case. Editing is only offered at all
  // because the backend contract supports revalidating edited text (see
  // `applyTailoringSuggestions`'s `edited_texts`) -- see this feature's
  // docs for why that's a hard requirement, not a nice-to-have.
  editedText: string | null
  onEditedTextChange: (text: string | null) => void
  revalidationError: string | null
  // Human-readable one-line summaries of the other suggestions this one is
  // mutually exclusive with (see `suggestion.conflicts_with` /
  // `buildConflictSummaries`) -- empty for the common case of no conflict.
  // Selecting this suggestion while one of those is already selected
  // auto-deselects the other (see TailoredResumePage's `toggleSuggestion`);
  // this note explains why, so it never looks like the UI silently
  // unchecked something the candidate picked.
  conflictSummaries: string[]
  // True once this suggestion has actually been committed by a successful
  // "Apply Now" in some earlier phase (see TailoredResumePage's
  // `appliedSuggestionIds`, derived from `finalTailoredResume`) -- distinct
  // from `accepted`, which just means "currently checked." An applied
  // suggestion is always accepted, but stays locked: it can't be
  // unchecked via the checkbox (only reverted, see `onRevertApplied`),
  // and Customize is hidden, since editing text that's already part of
  // the committed resume has no defined meaning here.
  isApplied: boolean
  // Undoes an applied suggestion -- UI-state only (see this feature's
  // docs on why: the backend's apply is a stateless, pure computation
  // from the original resume, so "un-applying" is nothing more than no
  // longer including this id the next time Apply Now runs). Omitted
  // (never called) for a suggestion that isn't applied.
  onRevertApplied: () => void
}

// Renders one suggestion for Stage 2 review as a compact resume-coach
// card, not a diff view. A candidate should be able to answer "do I want
// this?" from the collapsed card alone: section, a one-line human-language
// summary, why, and an impact rating -- in that reading order. Everything
// else (evidence detail, the full generated text, the original resume
// text) is progressive disclosure: collapsed by default, one line/link
// each, never shown unless clicked. Deliberately stateless about
// *acceptance* (fully controlled by the parent via `accepted`/
// `onToggleAccepted`) so TailoredResumePage stays the single source of
// truth, and its checkbox is a real `<input type="checkbox">` so
// Select All/Clear All keep working exactly as they did before this card
// was redesigned.
export default function TailoringSuggestionCard({
  suggestion,
  sectionName,
  accepted,
  onToggleAccepted,
  editedText,
  onEditedTextChange,
  revalidationError,
  conflictSummaries,
  isApplied,
  onRevertApplied,
}: TailoringSuggestionCardProps) {
  const [isEditing, setIsEditing] = useState(false)
  const [isPreviewOpen, setIsPreviewOpen] = useState(false)
  const [isCurrentOpen, setIsCurrentOpen] = useState(false)
  const [isEvidenceOpen, setIsEvidenceOpen] = useState(false)
  const [draftText, setDraftText] = useState(editedText ?? suggestion.suggested_text)

  const impact = getImpactLevel(suggestion)
  const isRemoval = suggestion.operation === 'remove'
  const hasCurrentText = suggestion.current_text !== null
  const evidenceGroups = groupEvidenceSources(suggestion.evidence_sources)
  const displayedText = editedText ?? suggestion.suggested_text
  const isEdited = editedText !== null

  // A read-only, side-by-side comparator for this one suggestion's actual
  // textual transformation -- current_text -> displayedText -- driven only
  // by this suggestion, regardless of whether it's currently selected (see
  // resumeSectionDiff.ts's `buildSuggestionDiffHunks` for exactly how each
  // operation's shape -- append/insert/update/replace/remove/add_emphasis
  // -- turns into hunks).
  const diffHunks = useMemo(
    () => buildSuggestionDiffHunks(suggestion.current_text, displayedText),
    [suggestion.current_text, displayedText],
  )

  function startEditing() {
    setDraftText(displayedText)
    setIsPreviewOpen(true)
    setIsEditing(true)
  }

  function saveEdit() {
    // No-op edit (draft matches the original suggested text) is treated
    // as "not edited" rather than storing a redundant identical override.
    onEditedTextChange(draftText === suggestion.suggested_text ? null : draftText)
    setIsEditing(false)
  }

  function cancelEdit() {
    setDraftText(displayedText)
    setIsEditing(false)
  }

  function resetToOriginal() {
    onEditedTextChange(null)
    setDraftText(suggestion.suggested_text)
    setIsEditing(false)
  }

  return (
    <li
      className={`rounded-2xl border p-5 ${
        isApplied ? 'border-gray-100 bg-gray-50/70 opacity-75' : 'border-gray-200 bg-white'
      }`}
    >
      {/* 1. WHAT changes -- section + a one-line, plain-language summary. */}
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant={isApplied ? 'gray' : 'indigo'}>
              {OPERATION_ACTION_LABELS[suggestion.operation]}
            </Badge>
            <h3 className="text-sm font-semibold text-gray-900">{sectionName}</h3>
            {isApplied && <Badge variant="green">Applied</Badge>}
            {isEdited && !isApplied && <Badge variant="amber">Edited</Badge>}
          </div>
          <p className="mt-1.5 text-sm text-gray-700">{summarizeSuggestionChange(suggestion, displayedText)}</p>
        </div>
        {/* 3. Impact -- the primary visual signal a candidate scans for. */}
        <ImpactRating level={impact} />
      </div>

      {/* 2. WHY it matters. */}
      <div className="mt-3">
        <p className="text-xs font-semibold uppercase tracking-wide text-gray-400">Why?</p>
        <p className="mt-1 text-sm text-gray-600">{suggestion.reason}</p>
      </div>

      {/* Accept (checkbox, keeps Select All/Clear All working) + Customize --
          replaced by a locked "Applied" state + Undo once committed. */}
      <div className="mt-4 flex items-center gap-4">
        <label
          className={`inline-flex items-center gap-2 select-none ${isApplied ? 'cursor-not-allowed' : 'cursor-pointer'}`}
        >
          <input
            type="checkbox"
            checked={accepted}
            disabled={isApplied}
            onChange={(event) => onToggleAccepted(event.target.checked)}
            aria-label={`Accept suggestion: ${summarizeSuggestionChange(suggestion, displayedText)}`}
            className="h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500 disabled:cursor-not-allowed"
          />
          <span className="text-sm font-semibold text-gray-900">
            {isApplied ? 'Applied' : accepted ? 'Accepted' : 'Accept'}
          </span>
        </label>
        {isApplied ? (
          <button
            type="button"
            onClick={onRevertApplied}
            className="text-sm font-medium text-gray-500 hover:text-gray-700"
          >
            Undo
          </button>
        ) : (
          <>
            <button
              type="button"
              onClick={startEditing}
              className="text-sm font-medium text-indigo-600 hover:text-indigo-700"
            >
              Customize
            </button>
            {isEdited && (
              <button
                type="button"
                onClick={resetToOriginal}
                className="text-xs font-medium text-gray-500 hover:text-gray-700"
              >
                Reset
              </button>
            )}
          </>
        )}
      </div>

      {conflictSummaries.length > 0 && (
        <p className="mt-2 text-xs font-medium text-amber-600">
          Choose only one: this conflicts with{' '}
          {conflictSummaries.map((summary, index) => (
            <span key={summary}>
              {index > 0 && ', '}
              &ldquo;{summary}&rdquo;
            </span>
          ))}
        </p>
      )}

      {revalidationError && (
        <p className="mt-2 text-xs font-medium text-rose-600">{revalidationError}</p>
      )}

      {/* Progressive disclosure: evidence, the full generated text, and
          the original resume text are all collapsed until asked for. */}
      <div className="mt-4 space-y-2.5">
        {evidenceGroups.length > 0 && (
          <DisclosureRow label="Evidence" isOpen={isEvidenceOpen} onToggle={() => setIsEvidenceOpen((v) => !v)}>
            <div className="space-y-2">
              {evidenceGroups.map((group) => (
                <div key={group.category}>
                  <p className="text-xs font-semibold text-gray-500">{group.label}</p>
                  <ul className="mt-0.5 space-y-0.5">
                    {group.sources.map((source, index) => (
                      <li key={`${source}-${index}`} className="text-xs text-gray-500">
                        {source}
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          </DisclosureRow>
        )}

        {!isRemoval && (
          <DisclosureRow
            label="Preview Change"
            isOpen={isPreviewOpen || isEditing}
            onToggle={() => setIsPreviewOpen((v) => !v)}
          >
            {isEditing ? (
              <div className="space-y-2">
                <textarea
                  value={draftText}
                  onChange={(event) => setDraftText(event.target.value)}
                  rows={3}
                  autoFocus
                  className="w-full rounded-lg border border-gray-200 bg-white p-2 text-sm text-gray-800 focus:border-indigo-400 focus:outline-none"
                />
                <div className="flex justify-end gap-2">
                  <Button variant="outline" onClick={cancelEdit}>
                    Cancel
                  </Button>
                  <Button variant="solid" onClick={saveEdit}>
                    Save
                  </Button>
                </div>
              </div>
            ) : (
              <SideBySideDiff hunks={diffHunks} />
            )}
          </DisclosureRow>
        )}

        {hasCurrentText && (
          <DisclosureRow
            label="View Current Resume Text"
            isOpen={isCurrentOpen}
            onToggle={() => setIsCurrentOpen((v) => !v)}
          >
            {isRemoval && <p className="mb-1 text-xs font-semibold text-rose-500">This will be removed</p>}
            <p
              className={`text-sm text-gray-600 ${isRemoval ? 'line-through decoration-rose-300' : ''}`}
            >
              {suggestion.current_text}
            </p>
          </DisclosureRow>
        )}
      </div>
    </li>
  )
}
