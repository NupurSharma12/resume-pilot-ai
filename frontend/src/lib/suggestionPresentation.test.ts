import { describe, it, expect } from 'vitest'
import {
  buildSectionFallbackOrdinals,
  buildSectionNameMap,
  computeAppendedDelta,
  estimateAtsImprovementPercent,
  getImpactLevel,
  getReadableSectionName,
  groupEvidenceSources,
  OPERATION_ACTION_LABELS,
  summarizeSuggestionChange,
  truncateText,
} from './suggestionPresentation'
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
    evidence_ids: ['resume-section-1-item-0'],
    evidence_sources: ['Resume: SKILLS'],
    confidence: 90,
    selected_by_default: true,
    validation_status: 'supported_by_original_resume',
    validation_issues: [],
    ...overrides,
  }
}

describe('section names', () => {
  it('extracts and title-cases a SHOUT-CASE heading from resume evidence', () => {
    const suggestions = [suggestion({ evidence_sources: ['Resume: SKILLS'] })]
    const names = buildSectionNameMap(suggestions)
    expect(names.get('section-1')).toBe('Skills')
  })

  it('leaves an already-mixed-case heading alone', () => {
    const suggestions = [suggestion({ evidence_sources: ['Resume: Adobe Experience'] })]
    const names = buildSectionNameMap(suggestions)
    expect(names.get('section-1')).toBe('Adobe Experience')
  })

  it('reuses a heading found on a different suggestion targeting the same section', () => {
    const withHeading = suggestion({
      suggestion_id: 's1',
      target_section_id: 'section-2',
      evidence_sources: ['Resume: EXPERIENCE'],
    })
    const withoutHeading = suggestion({
      suggestion_id: 's2',
      target_section_id: 'section-2',
      evidence_sources: ['Conversation Turn 1'],
    })
    const names = buildSectionNameMap([withHeading, withoutHeading])
    expect(names.get('section-2')).toBe('Experience')
  })

  it('never exposes the internal section id when no resume evidence names it', () => {
    const suggestions = [
      suggestion({ target_section_id: 'section-0', evidence_sources: ['Conversation Turn 1'] }),
    ]
    const names = buildSectionNameMap(suggestions)
    const ordinals = buildSectionFallbackOrdinals(suggestions)
    const readable = getReadableSectionName(suggestions[0], names, ordinals)
    expect(readable).not.toContain('section-0')
    expect(readable).toBe('Resume Section 1')
  })

  it('ignores the whole-document "Header" label as a section heading', () => {
    const suggestions = [suggestion({ evidence_sources: ['Resume: Header'] })]
    const names = buildSectionNameMap(suggestions)
    expect(names.has('section-1')).toBe(false)
  })

  it('assigns stable, first-seen-order fallback ordinals across distinct sections', () => {
    const suggestions = [
      suggestion({ suggestion_id: 's1', target_section_id: 'section-5', evidence_sources: [] }),
      suggestion({ suggestion_id: 's2', target_section_id: 'section-2', evidence_sources: [] }),
      suggestion({ suggestion_id: 's3', target_section_id: 'section-5', evidence_sources: [] }),
    ]
    const ordinals = buildSectionFallbackOrdinals(suggestions)
    expect(ordinals.get('section-5')).toBe(1)
    expect(ordinals.get('section-2')).toBe(2)
  })
})

describe('impact level', () => {
  it('is high for a well-supported, high-confidence suggestion', () => {
    expect(getImpactLevel(suggestion({ confidence: 95, validation_status: 'supported_by_both' }))).toBe(
      'high',
    )
  })

  it('is medium for a supported, mid-confidence suggestion', () => {
    expect(
      getImpactLevel(suggestion({ confidence: 60, validation_status: 'supported_by_conversation' })),
    ).toBe('medium')
  })

  it('is low for a low-confidence supported suggestion', () => {
    expect(
      getImpactLevel(suggestion({ confidence: 30, validation_status: 'supported_by_original_resume' })),
    ).toBe('low')
  })

  it('is always low for an unsupported suggestion, regardless of confidence', () => {
    expect(getImpactLevel(suggestion({ confidence: 99, validation_status: 'unsupported' }))).toBe('low')
  })

  it('is always low for a structurally invalid suggestion', () => {
    expect(
      getImpactLevel(suggestion({ confidence: 99, validation_status: 'structurally_invalid' })),
    ).toBe('low')
  })
})

describe('estimateAtsImprovementPercent', () => {
  it('is zero when nothing is recommended', () => {
    const suggestions = [suggestion({ selected_by_default: false })]
    expect(estimateAtsImprovementPercent(suggestions)).toBe(0)
  })

  it('grows with more/higher-impact recommended suggestions, capped at 35', () => {
    const many = Array.from({ length: 30 }, (_, i) =>
      suggestion({ suggestion_id: `s${i}`, selected_by_default: true, confidence: 95 }),
    )
    expect(estimateAtsImprovementPercent(many)).toBe(35)
  })

  it('only counts recommended suggestions, not every suggestion in the plan', () => {
    const suggestions = [
      suggestion({ suggestion_id: 's1', selected_by_default: true, confidence: 95 }),
      suggestion({ suggestion_id: 's2', selected_by_default: false, confidence: 95 }),
    ]
    const withBoth = estimateAtsImprovementPercent(suggestions)
    const withOne = estimateAtsImprovementPercent([suggestions[0]])
    expect(withBoth).toBe(withOne)
  })
})

describe('computeAppendedDelta', () => {
  it('returns only the newly appended portion when current text is a prefix', () => {
    expect(computeAppendedDelta('Python', 'Python, TypeScript')).toBe('TypeScript')
  })

  it('cleans up a leading comma/colon left behind by the split', () => {
    expect(computeAppendedDelta('Led backend development.', 'Led backend development. Owned CI/CD.')).toBe(
      'Owned CI/CD.',
    )
  })

  it('falls back to the full suggested text if current text is not found', () => {
    expect(computeAppendedDelta('Not present', 'Something else entirely')).toBe(
      'Something else entirely',
    )
  })
})

describe('groupEvidenceSources', () => {
  it('groups resume, conversation, and analysis sources under separate labels', () => {
    const groups = groupEvidenceSources([
      'Resume: SKILLS',
      'Conversation Turn 2',
      'Analysis Strength #1',
      'Conversation Turn 5',
    ])
    expect(groups.map((g) => g.label)).toEqual(['Resume', 'Career Conversation', 'Resume Analysis'])
    expect(groups.find((g) => g.category === 'conversation')?.sources).toEqual([
      'Conversation Turn 2',
      'Conversation Turn 5',
    ])
  })

  it('omits a category entirely when no source matches it', () => {
    const groups = groupEvidenceSources(['Resume: SKILLS'])
    expect(groups).toHaveLength(1)
    expect(groups[0].category).toBe('resume')
  })

  it('returns no groups for an empty evidence list', () => {
    expect(groupEvidenceSources([])).toEqual([])
  })
})

describe('OPERATION_ACTION_LABELS', () => {
  it('translates every backend operation into plain, human language', () => {
    expect(OPERATION_ACTION_LABELS.append).toBe('Add')
    expect(OPERATION_ACTION_LABELS.insert_before).toBe('Add')
    expect(OPERATION_ACTION_LABELS.insert_after).toBe('Add')
    expect(OPERATION_ACTION_LABELS.update).toBe('Update')
    expect(OPERATION_ACTION_LABELS.replace).toBe('Update')
    expect(OPERATION_ACTION_LABELS.remove).toBe('Remove')
    expect(OPERATION_ACTION_LABELS.add_emphasis).toBe('Strengthen')
  })
})

describe('truncateText', () => {
  it('leaves short text untouched', () => {
    expect(truncateText('React, TypeScript')).toBe('React, TypeScript')
  })

  it('truncates long text with an ellipsis at the requested length', () => {
    const long = 'a'.repeat(100)
    const result = truncateText(long, 20)
    expect(result).toHaveLength(21)
    expect(result.endsWith('…')).toBe(true)
  })
})

describe('summarizeSuggestionChange', () => {
  it('summarizes an append as "Add <delta>"', () => {
    const s = suggestion({
      operation: 'append',
      current_text: 'Python',
      suggested_text: 'Python, TypeScript, and Node.js',
    })
    expect(summarizeSuggestionChange(s)).toBe('Add TypeScript, and Node.js')
  })

  it('summarizes an insertion as "Add <suggested text>"', () => {
    const s = suggestion({
      operation: 'insert_after',
      current_text: null,
      suggested_text: 'Led the migration to React.',
    })
    expect(summarizeSuggestionChange(s)).toBe('Add Led the migration to React.')
  })

  it('summarizes an update as "Update <suggested text>"', () => {
    const s = suggestion({
      operation: 'update',
      current_text: 'Backend engineer.',
      suggested_text: 'Full-stack engineer with React and Python experience.',
    })
    expect(summarizeSuggestionChange(s)).toBe(
      'Update Full-stack engineer with React and Python experience.',
    )
  })

  it('summarizes add_emphasis as "Strengthen <suggested text>"', () => {
    const s = suggestion({
      operation: 'add_emphasis',
      current_text: 'Worked on backend systems.',
      suggested_text: 'Owned backend systems end to end.',
    })
    expect(summarizeSuggestionChange(s)).toBe('Strengthen Owned backend systems end to end.')
  })

  it('summarizes a removal as "Remove: <current text>"', () => {
    const s = suggestion({
      operation: 'remove',
      current_text: 'Irrelevant certification from 2005.',
      suggested_text: '',
    })
    expect(summarizeSuggestionChange(s)).toBe('Remove: Irrelevant certification from 2005.')
  })

  it('truncates a long summary so the card stays scannable', () => {
    const s = suggestion({
      operation: 'update',
      current_text: 'Short.',
      suggested_text: 'x'.repeat(200),
    })
    expect(summarizeSuggestionChange(s).length).toBeLessThan(90)
  })
})
