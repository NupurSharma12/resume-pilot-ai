// Pure remapping logic for stale-plan recovery (see TailoredResumePage's
// `recoverFromStalePlan`). Extracted from the page so the matching
// strategy is independently testable without mounting the whole page or
// mocking network calls.
//
// Why a semantic fallback is necessary, not just nice-to-have:
// `suggestion_id` (`suggestion-0`, `suggestion-1`, ...) is assigned by
// *position* within one generation call (see
// `TailoringSuggestionWorkflow._generate_one_suggestion`), not derived
// from any stable content -- a second generation call against the exact
// same resume/job description/conversation can, and often will, produce
// suggestions in a different order, count, or wording (LLM
// non-determinism), so `suggestion_id` alone essentially never survives
// a regeneration. `target_item_id`, in contrast, comes from
// `ResumeStructureParser`, a deterministic, pure function of the resume
// text alone -- unchanged input text always produces the same item ids.
// Pairing `target_item_id` with `operation` is therefore a much more
// durable notion of "the same logical suggestion" across two generation
// calls than `suggestion_id` ever is.

import type { TailoringSuggestion } from '../data/tailoringSuggestionsTypes'

export interface RemappedSelections {
  selections: string[]
  editedTexts: Record<string, string>
  // Old selected suggestion ids that had no counterpart (by id or by
  // semantic match) in the new plan -- surfaced so a caller can log/
  // display "N suggestions couldn't be restored" rather than silently
  // dropping them with no trace.
  unmatchedSuggestionIds: string[]
}

function semanticKey(suggestion: TailoringSuggestion): string {
  return `${suggestion.target_item_id}::${suggestion.operation}`
}

// Maps a previous plan's selections (and any edited text) onto a freshly
// regenerated plan. Tries, per previously-selected suggestion: (1) the
// exact same `suggestion_id`, in case the new plan happens to still have
// it; (2) the same `(target_item_id, operation)` pair -- the "semantic"
// match described above; (3) otherwise, gives up on restoring that one
// suggestion rather than guessing further. A suggestion with no match at
// all is simply not selected in the new plan -- there is nothing
// meaningful to carry forward for it.
export function remapSelectionsToNewPlan(
  previousSuggestions: TailoringSuggestion[],
  previousSelections: string[],
  previousEditedTexts: Record<string, string>,
  newSuggestions: TailoringSuggestion[],
): RemappedSelections {
  const previousById = new Map(previousSuggestions.map((s) => [s.suggestion_id, s]))
  const newById = new Map(newSuggestions.map((s) => [s.suggestion_id, s]))
  const newBySemanticKey = new Map<string, TailoringSuggestion>()
  for (const suggestion of newSuggestions) {
    const key = semanticKey(suggestion)
    if (!newBySemanticKey.has(key)) {
      newBySemanticKey.set(key, suggestion)
    }
  }

  const selections = new Set<string>()
  const editedTexts: Record<string, string> = {}
  const unmatchedSuggestionIds: string[] = []

  for (const previousId of previousSelections) {
    const previousSuggestion = previousById.get(previousId)
    if (!previousSuggestion) continue

    const matched = newById.get(previousId) ?? newBySemanticKey.get(semanticKey(previousSuggestion))
    if (!matched) {
      unmatchedSuggestionIds.push(previousId)
      continue
    }

    selections.add(matched.suggestion_id)
    const previousEditedText = previousEditedTexts[previousId]
    if (previousEditedText !== undefined) {
      editedTexts[matched.suggestion_id] = previousEditedText
    }
  }

  return { selections: [...selections], editedTexts, unmatchedSuggestionIds }
}
