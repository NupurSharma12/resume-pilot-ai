import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import TailoringPreviewPanel from './TailoringPreviewPanel'
import { fixtureSuggestionAppend, fixtureSuggestionInsert } from '../testFixtures'

const ORIGINAL_TEXT = 'SUMMARY\nBackend engineer.\n\nSKILLS\nPython\nDjango\n\nEXPERIENCE\nBuilt tools.\n'
const PREVIEW_TEXT = 'SUMMARY\nBackend engineer.\n\nSKILLS\nPython, TypeScript\nDjango\n\nEXPERIENCE\nBuilt tools.\n'

function renderPanel(overrides: Partial<Parameters<typeof TailoringPreviewPanel>[0]> = {}) {
  return render(
    <TailoringPreviewPanel
      originalResumeText={ORIGINAL_TEXT}
      previewResumeText={PREVIEW_TEXT}
      includedSuggestions={[fixtureSuggestionAppend]}
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
  it('supports section-by-section navigation, defaulting to the first changed section', () => {
    renderPanel()

    // SKILLS is the only changed section -- shown by default, as a
    // side-by-side comparator (Original/Proposed columns).
    expect(screen.getByRole('heading', { name: 'Skills' })).toBeInTheDocument()
    expect(screen.getByText('Original')).toBeInTheDocument()
    expect(screen.getByText('Proposed')).toBeInTheDocument()
    expect(screen.getByText('TypeScript')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /summary/i }))
    expect(screen.getByRole('heading', { name: 'Summary' })).toBeInTheDocument()
    expect(screen.getByText(/no changes in this section/i)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /experience/i }))
    expect(screen.getByRole('heading', { name: 'Experience' })).toBeInTheDocument()
    expect(screen.getByText(/no changes in this section/i)).toBeInTheDocument()
  })

  it('shows only the changed hunk, never the whole resume/section', () => {
    renderPanel()

    // "Python" -> "Python, TypeScript" is an append: the common prefix
    // "Python" is shown once, as unchanged context; only "TypeScript" is
    // marked as an addition. "Django" (unrelated, unchanged) still shows
    // as nearby context since it's within the default context window.
    expect(screen.getAllByText('Python').length).toBeGreaterThan(0)
    expect(screen.getByText('TypeScript')).toBeInTheDocument()
    expect(screen.getAllByText('Django').length).toBeGreaterThan(0)
    // Never the whole original resume dumped into the panel.
    expect(screen.queryByText(/built tools/i)).not.toBeInTheDocument()
  })

  it('lists included suggestions, separating newly selected from already-applied ones', () => {
    renderPanel({
      includedSuggestions: [fixtureSuggestionAppend, fixtureSuggestionInsert],
      alreadyAppliedIds: new Set([fixtureSuggestionInsert.suggestion_id]),
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
