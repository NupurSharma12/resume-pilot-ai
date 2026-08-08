import { describe, it, expect } from 'vitest'
import { remapSelectionsToNewPlan } from './suggestionRecovery'
import type { TailoringSuggestion } from '../data/tailoringSuggestionsTypes'

function suggestion(overrides: Partial<TailoringSuggestion> = {}): TailoringSuggestion {
  return {
    suggestion_id: 'suggestion-0',
    target_section_id: 'section-1',
    target_item_id: 'section-1-item-0',
    operation: 'append',
    current_text: 'Python',
    suggested_text: 'Python, TypeScript',
    reason: 'TypeScript experience is missing.',
    evidence_ids: [],
    evidence_sources: [],
    confidence: 90,
    selected_by_default: true,
    validation_status: 'supported_by_conversation',
    validation_issues: [],
    conflicts_with: [],
    ...overrides,
  }
}

describe('remapSelectionsToNewPlan', () => {
  it('matches by exact suggestion_id when the new plan happens to still have it', () => {
    const previous = [suggestion({ suggestion_id: 'suggestion-0' })]
    const next = [suggestion({ suggestion_id: 'suggestion-0' })]

    const result = remapSelectionsToNewPlan(previous, ['suggestion-0'], {}, next)

    expect(result.selections).toEqual(['suggestion-0'])
    expect(result.unmatchedSuggestionIds).toEqual([])
  })

  it('falls back to matching by (target_item_id, operation) when ids differ', () => {
    const previous = [
      suggestion({ suggestion_id: 'suggestion-0', target_item_id: 'section-1-item-0', operation: 'append' }),
    ]
    // Regeneration reordered/renumbered everything -- same logical edit,
    // different id, matching real `TailoringSuggestionWorkflow` behavior
    // (ids are assigned by position within one generation call).
    const next = [
      suggestion({ suggestion_id: 'suggestion-2', target_item_id: 'section-9-item-9', operation: 'update' }),
      suggestion({ suggestion_id: 'suggestion-3', target_item_id: 'section-1-item-0', operation: 'append' }),
    ]

    const result = remapSelectionsToNewPlan(previous, ['suggestion-0'], {}, next)

    expect(result.selections).toEqual(['suggestion-3'])
  })

  it('carries edited text forward onto the matched new suggestion id', () => {
    const previous = [
      suggestion({ suggestion_id: 'suggestion-0', target_item_id: 'section-1-item-0', operation: 'append' }),
    ]
    const next = [
      suggestion({ suggestion_id: 'suggestion-5', target_item_id: 'section-1-item-0', operation: 'append' }),
    ]

    const result = remapSelectionsToNewPlan(
      previous,
      ['suggestion-0'],
      { 'suggestion-0': 'Python, TypeScript, and Node.js' },
      next,
    )

    expect(result.editedTexts).toEqual({ 'suggestion-5': 'Python, TypeScript, and Node.js' })
  })

  it('does not carry edited text for a suggestion that was not edited', () => {
    const previous = [suggestion({ suggestion_id: 'suggestion-0' })]
    const next = [suggestion({ suggestion_id: 'suggestion-0' })]

    const result = remapSelectionsToNewPlan(previous, ['suggestion-0'], {}, next)

    expect(result.editedTexts).toEqual({})
  })

  it('reports an unmatched suggestion when the target item no longer exists in the new plan', () => {
    const previous = [
      suggestion({ suggestion_id: 'suggestion-0', target_item_id: 'section-1-item-0', operation: 'append' }),
    ]
    const next = [
      suggestion({ suggestion_id: 'suggestion-7', target_item_id: 'section-2-item-3', operation: 'update' }),
    ]

    const result = remapSelectionsToNewPlan(previous, ['suggestion-0'], {}, next)

    expect(result.selections).toEqual([])
    expect(result.unmatchedSuggestionIds).toEqual(['suggestion-0'])
  })

  it('only restores suggestions that were previously selected, not every previous suggestion', () => {
    const previous = [
      suggestion({ suggestion_id: 'suggestion-0', target_item_id: 'section-1-item-0', operation: 'append' }),
      suggestion({ suggestion_id: 'suggestion-1', target_item_id: 'section-2-item-0', operation: 'update' }),
    ]
    const next = [
      suggestion({ suggestion_id: 'suggestion-0', target_item_id: 'section-1-item-0', operation: 'append' }),
      suggestion({ suggestion_id: 'suggestion-1', target_item_id: 'section-2-item-0', operation: 'update' }),
    ]

    // Only suggestion-0 was selected before -- suggestion-1 must not
    // reappear in the restored selection just because it exists.
    const result = remapSelectionsToNewPlan(previous, ['suggestion-0'], {}, next)

    expect(result.selections).toEqual(['suggestion-0'])
  })

  it('never selects the same new suggestion twice even if two old selections map to it', () => {
    const previous = [
      suggestion({ suggestion_id: 'suggestion-0', target_item_id: 'section-1-item-0', operation: 'append' }),
      suggestion({ suggestion_id: 'suggestion-1', target_item_id: 'section-1-item-0', operation: 'append' }),
    ]
    const next = [
      suggestion({ suggestion_id: 'suggestion-9', target_item_id: 'section-1-item-0', operation: 'append' }),
    ]

    const result = remapSelectionsToNewPlan(previous, ['suggestion-0', 'suggestion-1'], {}, next)

    expect(result.selections).toEqual(['suggestion-9'])
  })

  it('handles an empty previous selection cleanly', () => {
    const result = remapSelectionsToNewPlan([], [], {}, [suggestion()])

    expect(result).toEqual({ selections: [], editedTexts: {}, unmatchedSuggestionIds: [] })
  })

  it('ignores a previously-selected id that no longer exists in the previous suggestions list', () => {
    // Defensive: selections and their suggestion list should never
    // disagree in practice, but a stale id must not throw.
    const result = remapSelectionsToNewPlan([], ['suggestion-0'], {}, [suggestion()])

    expect(result.selections).toEqual([])
    expect(result.unmatchedSuggestionIds).toEqual([])
  })
})
