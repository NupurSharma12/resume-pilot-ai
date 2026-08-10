import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import TailoringPreviewPanel from './TailoringPreviewPanel'
import type { TailoringSuggestion } from '../data/tailoringSuggestionsTypes'

// Deliberately carries real `Resume: {heading}` evidence, so
// `buildSectionNameMap` (suggestionPresentation.ts) resolves an actual
// section name rather than a "Resume Section N" fallback -- exercising
// the same section-naming path the suggestion review list itself uses.
const skillsSuggestion: TailoringSuggestion = {
  suggestion_id: 'suggestion-0',
  target_section_id: 'section-skills',
  target_item_id: 'section-skills-item-0',
  operation: 'append',
  current_text: 'Python',
  suggested_text: 'Python, TypeScript',
  reason: 'TypeScript experience is missing from Skills.',
  evidence_ids: ['resume-skills-0'],
  evidence_sources: ['Resume: SKILLS'],
  confidence: 90,
  selected_by_default: true,
  validation_status: 'supported_by_original_resume',
  validation_issues: [],
  conflicts_with: [],
}

const experienceSuggestion: TailoringSuggestion = {
  suggestion_id: 'suggestion-1',
  target_section_id: 'section-experience',
  target_item_id: 'section-experience-item-0',
  operation: 'insert_after',
  current_text: null,
  suggested_text: 'Led a cross-team migration involving 4 engineers.',
  reason: 'People-management evidence is missing from Experience.',
  evidence_ids: ['conversation-turn-1'],
  evidence_sources: ['Conversation Turn 1', 'Resume: EXPERIENCE'],
  confidence: 85,
  selected_by_default: true,
  validation_status: 'supported_by_conversation',
  validation_issues: [],
  conflicts_with: [],
}

function renderPanel(overrides: Partial<Parameters<typeof TailoringPreviewPanel>[0]> = {}) {
  return render(
    <TailoringPreviewPanel
      includedSuggestions={[skillsSuggestion]}
      editedTexts={{}}
      alreadyAppliedIds={new Set()}
      isApplying={false}
      applyError={null}
      onBack={vi.fn()}
      onApplyNow={vi.fn()}
      {...overrides}
    />,
  )
}

describe('TailoringPreviewPanel', () => {
  it('builds the diff directly from the suggestion, not a diffed original/preview document', () => {
    renderPanel()

    expect(screen.getByRole('heading', { name: 'Skills' })).toBeInTheDocument()
    expect(screen.getByText('Original')).toBeInTheDocument()
    expect(screen.getByText('Proposed')).toBeInTheDocument()
    expect(screen.getByText('TypeScript')).toBeInTheDocument()
  })

  it('only shows tabs for sections that actually have an included suggestion', () => {
    renderPanel({ includedSuggestions: [skillsSuggestion, experienceSuggestion] })

    expect(screen.getByRole('button', { name: /skills/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /experience/i })).toBeInTheDocument()
    // No suggestion targets Summary -- unlike the old whole-document diff,
    // there is nothing to show for it, so no tab is rendered at all.
    expect(screen.queryByRole('button', { name: /summary/i })).not.toBeInTheDocument()
  })

  it('switches between sections, each showing only its own suggestions', () => {
    renderPanel({ includedSuggestions: [skillsSuggestion, experienceSuggestion] })

    expect(screen.getByRole('heading', { name: 'Skills' })).toBeInTheDocument()
    expect(screen.getByText('TypeScript')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /experience/i }))

    expect(screen.getByRole('heading', { name: 'Experience' })).toBeInTheDocument()
    // Appears both in the diff cell and the "New in this preview" badge
    // summary -- getAllByText, not getByText, is expected here.
    expect(screen.getAllByText(/led a cross-team migration/i).length).toBeGreaterThan(0)
    expect(screen.queryByText('TypeScript')).not.toBeInTheDocument()
  })

  it('diffs the edited text, not the original suggested text, once the user has customized it', () => {
    renderPanel({ editedTexts: { [skillsSuggestion.suggestion_id]: 'Python, TypeScript, and GraphQL' } })

    expect(screen.getByText('TypeScript, and GraphQL')).toBeInTheDocument()
  })

  it('lists included suggestions, separating newly selected from already-applied ones', () => {
    renderPanel({
      includedSuggestions: [skillsSuggestion, experienceSuggestion],
      alreadyAppliedIds: new Set([experienceSuggestion.suggestion_id]),
    })

    expect(screen.getByText(/new in this preview/i)).toBeInTheDocument()
    expect(screen.getByText(/already applied/i)).toBeInTheDocument()
  })

  it('calls onBack and onApplyNow from their respective buttons, never touching selection itself', () => {
    const onBack = vi.fn()
    const onApplyNow = vi.fn()
    renderPanel({ onBack, onApplyNow })

    fireEvent.click(screen.getByRole('button', { name: /back to suggestions/i }))
    expect(onBack).toHaveBeenCalledTimes(1)

    fireEvent.click(screen.getByRole('button', { name: /apply now/i }))
    expect(onApplyNow).toHaveBeenCalledTimes(1)
  })

  it('disables both actions while applying', () => {
    renderPanel({ isApplying: true })

    expect(screen.getByRole('button', { name: /back to suggestions/i })).toBeDisabled()
    expect(screen.getByRole('button', { name: /applying/i })).toBeDisabled()
  })

  it('shows an apply error inline when one is passed', () => {
    renderPanel({ applyError: 'Something went wrong applying changes.' })

    expect(screen.getByText(/something went wrong applying changes/i)).toBeInTheDocument()
  })
})
