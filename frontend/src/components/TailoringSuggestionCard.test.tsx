import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import TailoringSuggestionCard from './TailoringSuggestionCard'
import { fixtureSuggestionAppend, fixtureSuggestionInsert } from '../testFixtures'
import type { TailoringSuggestion } from '../data/tailoringSuggestionsTypes'

function renderCard(overrides: Partial<Parameters<typeof TailoringSuggestionCard>[0]> = {}) {
  return render(
    <ul>
      <TailoringSuggestionCard
        suggestion={fixtureSuggestionAppend}
        sectionName="Skills"
        accepted={false}
        onToggleAccepted={vi.fn()}
        editedText={null}
        onEditedTextChange={vi.fn()}
        revalidationError={null}
        conflictSummaries={[]}
        isApplied={false}
        onRevertApplied={vi.fn()}
        {...overrides}
      />
    </ul>,
  )
}

describe('TailoringSuggestionCard: Preview Change comparator', () => {
  it('is read-only: opening Preview Change never toggles selection or edits state', () => {
    const onToggleAccepted = vi.fn()
    const onEditedTextChange = vi.fn()
    renderCard({ onToggleAccepted, onEditedTextChange })

    fireEvent.click(screen.getByRole('button', { name: /preview change/i }))

    expect(screen.getByText('TypeScript')).toBeInTheDocument()
    expect(onToggleAccepted).not.toHaveBeenCalled()
    expect(onEditedTextChange).not.toHaveBeenCalled()
  })

  it('shows only this suggestion\'s own change, not another suggestion\'s', () => {
    renderCard({ suggestion: fixtureSuggestionAppend })

    fireEvent.click(screen.getByRole('button', { name: /preview change/i }))

    // fixtureSuggestionAppend: "Python" -> "Python, TypeScript".
    expect(screen.getByText('TypeScript')).toBeInTheDocument()
    // fixtureSuggestionInsert's own text must never leak into this card's
    // comparator.
    expect(screen.queryByText(fixtureSuggestionInsert.suggested_text)).not.toBeInTheDocument()
  })

  it('renders a side-by-side comparator with Original/Proposed columns', () => {
    renderCard()

    fireEvent.click(screen.getByRole('button', { name: /preview change/i }))

    expect(screen.getByText('Original')).toBeInTheDocument()
    expect(screen.getByText('Proposed')).toBeInTheDocument()
  })

  it('splits an append into unchanged context plus a green addition, not a full replace', () => {
    renderCard()

    fireEvent.click(screen.getByRole('button', { name: /preview change/i }))

    // The common prefix "Python" is shown once as context; only the new
    // suffix "TypeScript" is marked as an addition -- never a "-Python"
    // removal, since nothing was actually removed.
    expect(screen.getAllByText('Python').length).toBeGreaterThan(0)
    expect(screen.getByText('TypeScript')).toBeInTheDocument()
    expect(screen.queryByText('Python, TypeScript')).not.toBeInTheDocument()
  })

  it('shows an addition-only comparator for an insertion, with an empty original side', () => {
    renderCard({ suggestion: fixtureSuggestionInsert })

    fireEvent.click(screen.getByRole('button', { name: /preview change/i }))

    expect(screen.getByText(fixtureSuggestionInsert.suggested_text)).toBeInTheDocument()
  })

  it('shows an old-vs-new comparator for an update/replace operation, word-highlighted', () => {
    const updateSuggestion: TailoringSuggestion = {
      ...fixtureSuggestionAppend,
      operation: 'update',
      current_text: 'Backend engineer with 5 years of experience.',
      suggested_text: 'Full-stack engineer with React and Python experience.',
    }
    const { container } = renderCard({ suggestion: updateSuggestion })

    fireEvent.click(screen.getByRole('button', { name: /preview change/i }))

    // Both full sentences are present (now split across highlighted-word
    // spans, so checked via textContent rather than a single getByText
    // match -- see SideBySideDiff's word-level rendering).
    expect(container.textContent).toContain('Backend engineer with 5 years of experience.')
    expect(container.textContent).toContain('Full-stack engineer with React and Python experience.')
    // Only the words that actually changed are highlighted -- the shared
    // words ("engineer", "with", "experience.") are not.
    const marks = Array.from(container.querySelectorAll('mark')).map((el) => el.textContent)
    expect(marks).toEqual(expect.arrayContaining(['Backend', 'Full-stack']))
    expect(marks).not.toEqual(expect.arrayContaining(['engineer']))
  })

  it('previews the edited text, not the original suggested text, once the user has customized it', () => {
    renderCard({ editedText: 'Python, TypeScript, and GraphQL' })

    fireEvent.click(screen.getByRole('button', { name: /preview change/i }))

    expect(screen.getByText('TypeScript, and GraphQL')).toBeInTheDocument()
  })
})
